"""
Memory Store Implementations.

Provides multiple storage backends for different query patterns:
- ChromaDBStore: Vector similarity search with metadata filtering
- SQLiteFTSStore: Full-text search with SQLite FTS5
- MemoryStore: Abstract base class
"""

from __future__ import annotations
import asyncio
import hashlib
import json
import logging
import os
import sqlite3
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from core.config import load_config
from core.config.models import MemoryConfig
from core.database import get_session
from core.database.models import MemoryMetadata, ConsolidationRun, MemoryKind as DBMemoryKind, MemorySource as DBMemorySource
from core.structured_logging import get_logger, log_structured
from core.memory.models import Memory, MemorySource, MemoryQuery, MemoryResult, ConsolidationResult, MemoryKind
from sqlalchemy import select, func, and_, or_, text
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

logger = get_logger(__name__)


class MemoryStore(ABC):
    """Abstract base class for memory stores."""

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the store."""
        pass

    @abstractmethod
    async def shutdown(self) -> None:
        """Shutdown the store."""
        pass

    @abstractmethod
    async def store(self, memory: Memory) -> str:
        """Store a memory and return its ID."""
        pass

    @abstractmethod
    async def get(self, memory_id: str) -> Optional[Memory]:
        """Retrieve a memory by ID."""
        pass

    @abstractmethod
    async def update(self, memory_id: str, updates: Dict[str, Any]) -> bool:
        """Update a memory."""
        pass

    @abstractmethod
    async def delete(self, memory_id: str) -> bool:
        """Delete a memory."""
        pass

    @abstractmethod
    async def query(self, query: MemoryQuery) -> MemoryResult:
        """Query memories."""
        pass

    @abstractmethod
    async def count(self, kind: Optional[MemoryKind] = None) -> int:
        """Count memories, optionally filtered by kind."""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check store health."""
        pass


class ChromaDBStore(MemoryStore):
    """ChromaDB vector store for semantic similarity search."""

    def __init__(self, config: MemoryConfig):
        self.config = config
        self.chroma_config = config.stores.get("chromadb", {})
        self._client = None
        self._collection = None
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize ChromaDB client and collection."""
        try:
            import chromadb
            from chromadb.config import Settings

            persist_dir = self.chroma_config.get("persist_directory", "./data/chromadb")
            Path(persist_dir).mkdir(parents=True, exist_ok=True)

            self._client = chromadb.PersistentClient(
                path=persist_dir,
                settings=Settings(anonymized_telemetry=False)
            )

            collection_name = self.chroma_config.get("collection_name", "arise_memories")
            self._collection = self._client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"}
            )

            self._initialized = True
            log_structured(logger, logging.INFO, "ChromaDB store initialized",
                          persist_dir=persist_dir, collection=collection_name)

        except ImportError:
            log_structured(logger, logging.WARNING, "ChromaDB not available, store disabled")
            self._initialized = False
        except Exception as e:
            log_structured(logger, logging.ERROR, "Failed to initialize ChromaDB", error=str(e))
            self._initialized = False

    async def shutdown(self) -> None:
        """Shutdown ChromaDB client."""
        if self._client:
            # ChromaDB PersistentClient doesn't have explicit close
            self._client = None
            self._collection = None
            self._initialized = False

    def _memory_to_chroma(self, memory: Memory) -> Tuple[str, Dict[str, Any], List[float], Dict[str, Any]]:
        """Convert Memory to ChromaDB format."""
        # Prepare metadata (ChromaDB doesn't support nested dicts, flatten)
        metadata = {
            "kind": memory.kind.value,
            "source": memory.source.value,
            "confidence": memory.confidence,
            "created_at": memory.created_at.isoformat(),
            "updated_at": memory.updated_at.isoformat(),
            "access_count": memory.access_count,
            "version": memory.version,
            "is_archived": str(memory.is_archived).lower(),
            "pii_detected": str(memory.pii_detected).lower(),
        }
        if memory.ttl_seconds:
            metadata["ttl_seconds"] = str(memory.ttl_seconds)
        if memory.tags:
            metadata["tags"] = ",".join(memory.tags)
        if memory.pii_types:
            metadata["pii_types"] = ",".join(memory.pii_types)
        # Add custom metadata
        for k, v in memory.metadata.items():
            if isinstance(v, (str, int, float, bool)):
                metadata[f"meta_{k}"] = str(v)

        # Generate embedding if not present
        embedding = memory.embedding
        if embedding is None:
            embedding = self._generate_embedding(memory.content)

        return memory.id, metadata, embedding, {"content": memory.content}

    def _generate_embedding(self, text: str) -> List[float]:
        """Generate a simple embedding for text (placeholder for sentence-transformers)."""
        # This is a placeholder - in production use sentence-transformers
        # For now, use a simple hash-based embedding
        hash_obj = hashlib.sha256(text.encode())
        hash_bytes = hash_obj.digest()
        # Convert to 384-dim vector (all-MiniLM-L6-v2 dimension)
        embedding = []
        for i in range(0, min(len(hash_bytes), 384), 1):
            embedding.append(hash_bytes[i] / 255.0)
        # Pad or truncate to 384
        while len(embedding) < 384:
            embedding.extend(embedding[:min(len(embedding), 384 - len(embedding))])
        return embedding[:384]

    def _chroma_to_memory(self, id: str, metadata: Dict[str, Any], document: str, embedding: List[float]) -> Memory:
        """Convert ChromaDB result to Memory."""
        kind_str = metadata.get("kind", "WORKING")
        try:
            kind = MemoryKind(kind_str)
        except ValueError:
            kind = MemoryKind.WORKING

        source_str = metadata.get("source", "system")
        try:
            source = MemorySource(source_str)
        except ValueError:
            source = MemorySource.SYSTEM

        tags = []
        if metadata.get("tags"):
            tags = metadata["tags"].split(",")

        pii_types = []
        if metadata.get("pii_types"):
            pii_types = metadata["pii_types"].split(",")

        # Extract custom metadata
        custom_metadata = {}
        for k, v in metadata.items():
            if k.startswith("meta_"):
                custom_metadata[k[5:]] = v

        return Memory(
            id=id,
            kind=kind,
            content=document,
            embedding=embedding,
            confidence=float(metadata.get("confidence", 1.0)),
            metadata=custom_metadata,
            tags=tags,
            ttl_seconds=int(metadata["ttl_seconds"]) if metadata.get("ttl_seconds") else None,
            source=source,
            created_at=datetime.fromisoformat(metadata["created_at"]) if metadata.get("created_at") else datetime.now(timezone.utc),
            updated_at=datetime.fromisoformat(metadata["updated_at"]) if metadata.get("updated_at") else datetime.now(timezone.utc),
            access_count=int(metadata.get("access_count", 0)),
            version=int(metadata.get("version", 1)),
            is_archived=metadata.get("is_archived", "false").lower() == "true",
            pii_detected=metadata.get("pii_detected", "false").lower() == "true",
            pii_types=pii_types,
        )

    async def store(self, memory: Memory) -> str:
        """Store a memory in ChromaDB."""
        if not self._initialized:
            raise RuntimeError("ChromaDB store not initialized")

        memory_id, metadata, embedding, document = self._memory_to_chroma(memory)

        # Upsert (add or update)
        self._collection.upsert(
            ids=[memory_id],
            embeddings=[embedding],
            metadatas=[metadata],
            documents=[document["content"]]
        )

        return memory_id

    async def get(self, memory_id: str) -> Optional[Memory]:
        """Get a memory by ID."""
        if not self._initialized:
            return None

        try:
            result = self._collection.get(
                ids=[memory_id],
                include=["embeddings", "metadatas", "documents"]
            )
            if result["ids"]:
                return self._chroma_to_memory(
                    result["ids"][0],
                    result["metadatas"][0],
                    result["documents"][0],
                    result["embeddings"][0]
                )
        except Exception as e:
            log_structured(logger, logging.ERROR, "ChromaDB get failed", memory_id=memory_id, error=str(e))
        return None

    async def update(self, memory_id: str, updates: Dict[str, Any]) -> bool:
        """Update a memory."""
        if not self._initialized:
            return False

        try:
            # Get existing
            existing = await self.get(memory_id)
            if not existing:
                return False

            # Apply updates
            for key, value in updates.items():
                if hasattr(existing, key):
                    setattr(existing, key, value)
            existing.updated_at = datetime.now(timezone.utc)
            existing.version += 1

            # Re-store
            await self.store(existing)
            return True
        except Exception as e:
            log_structured(logger, logging.ERROR, "ChromaDB update failed", memory_id=memory_id, error=str(e))
            return False

    async def delete(self, memory_id: str) -> bool:
        """Delete a memory."""
        if not self._initialized:
            return False

        try:
            self._collection.delete(ids=[memory_id])
            return True
        except Exception as e:
            log_structured(logger, logging.ERROR, "ChromaDB delete failed", memory_id=memory_id, error=str(e))
            return False

    async def query(self, query: MemoryQuery) -> MemoryResult:
        """Query memories using vector similarity."""
        if not self._initialized:
            return MemoryResult(search_type="vector")

        import time
        start = time.perf_counter()

        try:
            # Build where clause for metadata filtering
            where = {}
            if query.kind:
                where["kind"] = query.kind.value
            elif query.kinds:
                where["kind"] = {"$in": [k.value for k in query.kinds]}
            if not query.include_archived:
                where["is_archived"] = "false"
            if query.min_confidence > 0:
                where["confidence"] = {"$gte": query.min_confidence}
            if query.tags:
                # ChromaDB doesn't support array contains, use multiple conditions
                # For simplicity, skip tag filtering in vector search
                pass

            # Generate query embedding
            query_embedding = self._generate_embedding(query.query)

            # Execute search
            results = self._collection.query(
                query_embeddings=[query_embedding],
                n_results=query.limit,
                where=where if where else None,
                include=["embeddings", "metadatas", "documents", "distances"]
            )

            memories = []
            if results["ids"] and results["ids"][0]:
                for i, mem_id in enumerate(results["ids"][0]):
                    memory = self._chroma_to_memory(
                        mem_id,
                        results["metadatas"][0][i],
                        results["documents"][0][i],
                        results["embeddings"][0][i]
                    )
                    # Filter by similarity threshold
                    distance = results["distances"][0][i]
                    similarity = 1.0 - distance
                    if similarity >= query.similarity_threshold:
                        # Check TTL
                        if not query.include_expired and memory.is_expired():
                            continue
                        memories.append(memory)

            query_time = (time.perf_counter() - start) * 1000

            # Get total count
            total = self._collection.count()

            return MemoryResult(
                memories=memories,
                total=total,
                query_time_ms=query_time,
                search_type="vector"
            )

        except Exception as e:
            log_structured(logger, logging.ERROR, "ChromaDB query failed", error=str(e))
            return MemoryResult(search_type="vector")

    async def count(self, kind: Optional[MemoryKind] = None) -> int:
        """Count memories."""
        if not self._initialized:
            return 0

        try:
            if kind:
                result = self._collection.get(where={"kind": kind.value}, include=[])
                return len(result["ids"])
            return self._collection.count()
        except Exception:
            return 0

    async def health_check(self) -> bool:
        """Check ChromaDB health."""
        if not self._initialized:
            return False
        try:
            self._collection.count()
            return True
        except Exception:
            return False


class SQLiteFTSStore(MemoryStore):
    """SQLite FTS5 store for full-text search."""

    def __init__(self, config: MemoryConfig):
        self.config = config
        self.fts_config = config.stores.get("sqlite_fts", {})
        self._db_path = self.fts_config.get("database_path", "./data/memory_fts.db")
        self._conn = None
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize SQLite database with FTS5."""
        try:
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row

            # Enable WAL mode
            self._conn.execute("PRAGMA journal_mode=WAL")

            # Create main table
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 1.0,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    ttl_seconds INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    accessed_at TEXT,
                    access_count INTEGER NOT NULL DEFAULT 0,
                    version INTEGER NOT NULL DEFAULT 1,
                    previous_version_id TEXT,
                    is_archived INTEGER NOT NULL DEFAULT 0,
                    pii_detected INTEGER NOT NULL DEFAULT 0,
                    pii_types_json TEXT NOT NULL DEFAULT '[]'
                )
            """)

            # Create FTS5 virtual table
            self._conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                    content,
                    metadata_json,
                    tags_json,
                    content='memories',
                    content_rowid='id'
                )
            """)

            # Create triggers for FTS sync
            self._conn.execute("""
                CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
                    INSERT INTO memories_fts(rowid, content, metadata_json, tags_json)
                    VALUES (new.id, new.content, new.metadata_json, new.tags_json);
                END
            """)

            self._conn.execute("""
                CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
                    INSERT INTO memories_fts(memories_fts, rowid, content, metadata_json, tags_json)
                    VALUES ('delete', old.id, old.content, old.metadata_json, old.tags_json);
                END
            """)

            self._conn.execute("""
                CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
                    INSERT INTO memories_fts(memories_fts, rowid, content, metadata_json, tags_json)
                    VALUES ('delete', old.id, old.content, old.metadata_json, old.tags_json);
                    INSERT INTO memories_fts(rowid, content, metadata_json, tags_json)
                    VALUES (new.id, new.content, new.metadata_json, new.tags_json);
                END
            """)

            # Create indexes
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_kind ON memories(kind)")
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at)")
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_archived ON memories(is_archived)")
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_pii ON memories(pii_detected)")
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_source ON memories(source)")

            self._conn.commit()
            self._initialized = True

            log_structured(logger, logging.INFO, "SQLite FTS store initialized", db_path=self._db_path)

        except Exception as e:
            log_structured(logger, logging.ERROR, "Failed to initialize SQLite FTS", error=str(e))
            self._initialized = False

    async def shutdown(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
            self._initialized = False

    def _row_to_memory(self, row: sqlite3.Row) -> Memory:
        """Convert SQLite row to Memory."""
        kind_str = row["kind"]
        try:
            kind = MemoryKind(kind_str)
        except ValueError:
            kind = MemoryKind.WORKING

        source_str = row["source"]
        try:
            source = MemorySource(source_str)
        except ValueError:
            source = MemorySource.SYSTEM

        return Memory(
            id=row["id"],
            kind=kind,
            content=row["content"],
            embedding=None,  # SQLite FTS doesn't store embeddings
            confidence=row["confidence"],
            metadata=json.loads(row["metadata_json"]) if row["metadata_json"] else {},
            tags=json.loads(row["tags_json"]) if row["tags_json"] else [],
            ttl_seconds=row["ttl_seconds"] if row["ttl_seconds"] else None,
            source=source,
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.now(timezone.utc),
            updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else datetime.now(timezone.utc),
            accessed_at=datetime.fromisoformat(row["accessed_at"]) if row["accessed_at"] else None,
            access_count=row["access_count"],
            version=row["version"],
            previous_version_id=row["previous_version_id"],
            is_archived=bool(row["is_archived"]),
            pii_detected=bool(row["pii_detected"]),
            pii_types=json.loads(row["pii_types_json"]) if row["pii_types_json"] else [],
        )

    async def store(self, memory: Memory) -> str:
        """Store a memory in SQLite."""
        if not self._initialized:
            raise RuntimeError("SQLite FTS store not initialized")

        self._conn.execute("""
            INSERT OR REPLACE INTO memories (
                id, kind, content, source, confidence, metadata_json, tags_json,
                ttl_seconds, created_at, updated_at, accessed_at, access_count,
                version, previous_version_id, is_archived, pii_detected, pii_types_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            memory.id,
            memory.kind.value,
            memory.content,
            memory.source.value,
            memory.confidence,
            json.dumps(memory.metadata),
            json.dumps(memory.tags),
            memory.ttl_seconds,
            memory.created_at.isoformat(),
            memory.updated_at.isoformat(),
            memory.accessed_at.isoformat() if memory.accessed_at else None,
            memory.access_count,
            memory.version,
            memory.previous_version_id,
            1 if memory.is_archived else 0,
            1 if memory.pii_detected else 0,
            json.dumps(memory.pii_types),
        ))
        self._conn.commit()
        return memory.id

    async def get(self, memory_id: str) -> Optional[Memory]:
        """Get a memory by ID."""
        if not self._initialized:
            return None

        cursor = self._conn.execute("SELECT * FROM memories WHERE id = ?", (memory_id,))
        row = cursor.fetchone()
        if row:
            return self._row_to_memory(row)
        return None

    async def update(self, memory_id: str, updates: Dict[str, Any]) -> bool:
        """Update a memory."""
        if not self._initialized:
            return False

        try:
            # Build dynamic update
            set_clauses = []
            params = []

            for key, value in updates.items():
                if key == "metadata":
                    set_clauses.append("metadata_json = ?")
                    params.append(json.dumps(value))
                elif key == "tags":
                    set_clauses.append("tags_json = ?")
                    params.append(json.dumps(value))
                elif key == "pii_types":
                    set_clauses.append("pii_types_json = ?")
                    params.append(json.dumps(value))
                elif key in ["created_at", "updated_at", "accessed_at"] and isinstance(value, datetime):
                    set_clauses.append(f"{key} = ?")
                    params.append(value.isoformat())
                elif hasattr(Memory, key):
                    set_clauses.append(f"{key} = ?")
                    params.append(value)

            if not set_clauses:
                return False

            # Always update updated_at and version
            set_clauses.append("updated_at = ?")
            params.append(datetime.now(timezone.utc).isoformat())
            set_clauses.append("version = version + 1")

            params.append(memory_id)

            self._conn.execute(f"UPDATE memories SET {', '.join(set_clauses)} WHERE id = ?", params)
            self._conn.commit()
            return self._conn.total_changes > 0

        except Exception as e:
            log_structured(logger, logging.ERROR, "SQLite update failed", memory_id=memory_id, error=str(e))
            return False

    async def delete(self, memory_id: str) -> bool:
        """Delete a memory."""
        if not self._initialized:
            return False

        try:
            self._conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            self._conn.commit()
            return self._conn.total_changes > 0
        except Exception as e:
            log_structured(logger, logging.ERROR, "SQLite delete failed", memory_id=memory_id, error=str(e))
            return False

    async def query(self, query: MemoryQuery) -> MemoryResult:
        """Query memories using FTS5."""
        if not self._initialized:
            return MemoryResult(search_type="fts")

        import time
        start = time.perf_counter()

        try:
            # Build query
            where_clauses = []
            params = []

            if query.kind:
                where_clauses.append("kind = ?")
                params.append(query.kind.value)
            elif query.kinds:
                placeholders = ",".join("?" * len(query.kinds))
                where_clauses.append(f"kind IN ({placeholders})")
                params.extend([k.value for k in query.kinds])

            if not query.include_archived:
                where_clauses.append("is_archived = 0")

            if query.min_confidence > 0:
                where_clauses.append("confidence >= ?")
                params.append(query.min_confidence)

            if query.tags:
                # Simple tag matching - in production use json_each
                tag_conditions = []
                for tag in query.tags:
                    tag_conditions.append("tags_json LIKE ?")
                    params.append(f"%{tag}%")
                where_clauses.append(f"({' OR '.join(tag_conditions)})")

            where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

            # FTS search
            if query.query:
                # Use FTS5 MATCH
                fts_query = query.query.replace('"', '""')
                sql = f"""
                    SELECT m.*, bm25(memories_fts) as rank
                    FROM memories m
                    JOIN memories_fts f ON m.id = f.rowid
                    WHERE f.content MATCH ? AND {where_sql}
                    ORDER BY rank
                    LIMIT ? OFFSET ?
                """
                params = [fts_query] + params + [query.limit, query.offset]
            else:
                # No text query, just filter
                sql = f"""
                    SELECT *
                    FROM memories
                    WHERE {where_sql}
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                """
                params = params + [query.limit, query.offset]

            cursor = self._conn.execute(sql, params)
            rows = cursor.fetchall()
            memories = [self._row_to_memory(row) for row in rows]

            # Filter expired
            if not query.include_expired:
                memories = [m for m in memories if not m.is_expired()]

            # Get total count
            count_sql = f"SELECT COUNT(*) FROM memories WHERE {where_sql}"
            count_params = params[:-2] if query.query else params[:-2]
            total = self._conn.execute(count_sql, count_params).fetchone()[0]

            query_time = (time.perf_counter() - start) * 1000

            return MemoryResult(
                memories=memories,
                total=total,
                query_time_ms=query_time,
                search_type="fts"
            )

        except Exception as e:
            log_structured(logger, logging.ERROR, "SQLite FTS query failed", error=str(e))
            return MemoryResult(search_type="fts")

    async def count(self, kind: Optional[MemoryKind] = None) -> int:
        """Count memories."""
        if not self._initialized:
            return 0

        try:
            if kind:
                return self._conn.execute("SELECT COUNT(*) FROM memories WHERE kind = ?", (kind.value,)).fetchone()[0]
            return self._conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        except Exception:
            return 0

    async def health_check(self) -> bool:
        """Check SQLite health."""
        if not self._initialized:
            return False
        try:
            self._conn.execute("SELECT 1")
            return True
        except Exception:
            return False


class HybridMemoryStore(MemoryStore):
    """Hybrid store combining ChromaDB (vector) + SQLite FTS (full-text)."""

    def __init__(self, config: MemoryConfig):
        self.config = config
        self.chroma_store = ChromaDBStore(config)
        self.sqlite_store = SQLiteFTSStore(config)
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize both stores."""
        await asyncio.gather(
            self.chroma_store.initialize(),
            self.sqlite_store.initialize()
        )
        self._initialized = True
        log_structured(logger, logging.INFO, "Hybrid memory store initialized")

    async def shutdown(self) -> None:
        """Shutdown both stores."""
        await asyncio.gather(
            self.chroma_store.shutdown(),
            self.sqlite_store.shutdown()
        )
        self._initialized = False

    async def store(self, memory: Memory) -> str:
        """Store in both stores."""
        # Store in both concurrently
        await asyncio.gather(
            self.chroma_store.store(memory),
            self.sqlite_store.store(memory)
        )
        return memory.id

    async def get(self, memory_id: str) -> Optional[Memory]:
        """Get from ChromaDB first (has embeddings), fallback to SQLite."""
        memory = await self.chroma_store.get(memory_id)
        if memory:
            return memory
        return await self.sqlite_store.get(memory_id)

    async def update(self, memory_id: str, updates: Dict[str, Any]) -> bool:
        """Update in both stores."""
        results = await asyncio.gather(
            self.chroma_store.update(memory_id, updates),
            self.sqlite_store.update(memory_id, updates),
            return_exceptions=True
        )
        return any(r is True for r in results if not isinstance(r, Exception))

    async def delete(self, memory_id: str) -> bool:
        """Delete from both stores."""
        results = await asyncio.gather(
            self.chroma_store.delete(memory_id),
            self.sqlite_store.delete(memory_id),
            return_exceptions=True
        )
        return any(r is True for r in results if not isinstance(r, Exception))

    async def query(self, query: MemoryQuery) -> MemoryResult:
        """Hybrid query: combine vector + FTS results."""
        if not query.query:
            # No text query, just use SQLite for metadata filtering
            return await self.sqlite_store.query(query)

        # Run both searches concurrently
        vector_result, fts_result = await asyncio.gather(
            self.chroma_store.query(query),
            self.sqlite_store.query(query)
        )

        # Merge results (deduplicate by ID)
        seen_ids = set()
        merged_memories = []

        # Add vector results first (higher relevance for semantic search)
        for mem in vector_result.memories:
            if mem.id not in seen_ids:
                seen_ids.add(mem.id)
                merged_memories.append(mem)

        # Add FTS results
        for mem in fts_result.memories:
            if mem.id not in seen_ids:
                seen_ids.add(mem.id)
                merged_memories.append(mem)

        # Sort by relevance (vector results already sorted by similarity)
        # For now, keep vector-first ordering
        merged_memories = merged_memories[:query.limit]

        return MemoryResult(
            memories=merged_memories,
            total=max(vector_result.total, fts_result.total),
            query_time_ms=max(vector_result.query_time_ms, fts_result.query_time_ms),
            search_type="hybrid"
        )

    async def count(self, kind: Optional[MemoryKind] = None) -> int:
        """Count from primary store."""
        return await self.chroma_store.count(kind)

    async def health_check(self) -> bool:
        """Check both stores."""
        chroma_healthy = await self.chroma_store.health_check()
        sqlite_healthy = await self.sqlite_store.health_check()
        return chroma_healthy or sqlite_healthy  # At least one working


def create_memory_store(config: MemoryConfig) -> MemoryStore:
    """Factory function to create the appropriate memory store."""
    stores_config = config.stores

    # Determine which stores are enabled
    chroma_enabled = stores_config.get("chromadb", {}).get("enabled", True)
    sqlite_enabled = stores_config.get("sqlite_fts", {}).get("enabled", True)

    if chroma_enabled and sqlite_enabled:
        return HybridMemoryStore(config)
    elif chroma_enabled:
        return ChromaDBStore(config)
    elif sqlite_enabled:
        return SQLiteFTSStore(config)
    else:
        # Fallback to hybrid anyway
        return HybridMemoryStore(config)


__all__ = [
    "MemoryStore",
    "ChromaDBStore",
    "SQLiteFTSStore",
    "HybridMemoryStore",
    "create_memory_store",
]