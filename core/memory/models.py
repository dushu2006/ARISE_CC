"""
Memory System Models.

Core data structures for the 5 memory kinds:
- SEMANTIC: Facts, knowledge, concepts
- EPISODIC: Events, experiences, interactions
- PROCEDURAL: Skills, procedures, how-to
- PREFERENCE: User preferences, settings
- WORKING: Short-term, transient context
"""

from __future__ import annotations
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from core.config.models import MemoryKind


class MemorySource(str, Enum):
    """Memory source."""
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"
    CONSOLIDATION = "consolidation"
    IMPORT = "import"


@dataclass
class Memory:
    """Memory entity with full metadata."""
    id: str = field(default_factory=lambda: f"mem_{uuid.uuid4().hex[:16]}")
    kind: MemoryKind = MemoryKind.WORKING
    content: str = ""
    embedding: Optional[List[float]] = None
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    ttl_seconds: Optional[int] = None
    source: MemorySource = MemorySource.SYSTEM
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    accessed_at: Optional[datetime] = None
    access_count: int = 0
    version: int = 1
    previous_version_id: Optional[str] = None
    is_archived: bool = False
    pii_detected: bool = False
    pii_types: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind.value,
            "content": self.content,
            "embedding": self.embedding,
            "confidence": self.confidence,
            "metadata": self.metadata,
            "tags": self.tags,
            "ttl_seconds": self.ttl_seconds,
            "source": self.source.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "accessed_at": self.accessed_at.isoformat() if self.accessed_at else None,
            "access_count": self.access_count,
            "version": self.version,
            "previous_version_id": self.previous_version_id,
            "is_archived": self.is_archived,
            "pii_detected": self.pii_detected,
            "pii_types": self.pii_types,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Memory":
        mem = cls(
            id=data.get("id", f"mem_{uuid.uuid4().hex[:16]}"),
            kind=MemoryKind(data.get("kind", "WORKING")),
            content=data.get("content", ""),
            embedding=data.get("embedding"),
            confidence=data.get("confidence", 1.0),
            metadata=data.get("metadata", {}),
            tags=data.get("tags", []),
            ttl_seconds=data.get("ttl_seconds"),
            source=MemorySource(data.get("source", "system")),
            access_count=data.get("access_count", 0),
            version=data.get("version", 1),
            previous_version_id=data.get("previous_version_id"),
            is_archived=data.get("is_archived", False),
            pii_detected=data.get("pii_detected", False),
            pii_types=data.get("pii_types", []),
        )
        for dt_field in ["created_at", "updated_at", "accessed_at"]:
            if data.get(dt_field):
                setattr(mem, dt_field, datetime.fromisoformat(data[dt_field]))
        return mem

    def is_expired(self) -> bool:
        """Check if memory has expired based on TTL."""
        if self.ttl_seconds is None:
            return False
        elapsed = (datetime.now(timezone.utc) - self.created_at).total_seconds()
        return elapsed > self.ttl_seconds

    def touch(self) -> None:
        """Update access time and count."""
        self.accessed_at = datetime.now(timezone.utc)
        self.access_count += 1


@dataclass
class MemoryQuery:
    """Query for memory retrieval."""
    query: str = ""
    kind: Optional[MemoryKind] = None
    kinds: Optional[List[MemoryKind]] = None
    limit: int = 10
    offset: int = 0
    filters: Dict[str, Any] = field(default_factory=dict)
    min_confidence: float = 0.0
    include_archived: bool = False
    include_expired: bool = False
    tags: Optional[List[str]] = None
    similarity_threshold: float = 0.7

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "kind": self.kind.value if self.kind else None,
            "kinds": [k.value for k in self.kinds] if self.kinds else None,
            "limit": self.limit,
            "offset": self.offset,
            "filters": self.filters,
            "min_confidence": self.min_confidence,
            "include_archived": self.include_archived,
            "include_expired": self.include_expired,
            "tags": self.tags,
            "similarity_threshold": self.similarity_threshold,
        }


@dataclass
class MemoryResult:
    """Result from a memory query."""
    memories: List[Memory] = field(default_factory=list)
    total: int = 0
    query_time_ms: float = 0.0
    search_type: str = "hybrid"  # vector, fts, hybrid


@dataclass
class ConsolidationResult:
    """Result of a consolidation run."""
    kind: str
    input_count: int = 0
    output_count: int = 0
    status: str = "completed"
    error: Optional[str] = None
    duration_seconds: float = 0.0
    created_memories: List[str] = field(default_factory=list)
    archived_memories: List[str] = field(default_factory=list)


__all__ = [
    "Memory",
    "MemorySource",
    "MemoryQuery",
    "MemoryResult",
    "ConsolidationResult",
]