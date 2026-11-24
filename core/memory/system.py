"""
Memory System Facade.

High-level interface for the memory system combining:
- Multi-store (ChromaDB + SQLite FTS)
- Consolidation pipeline
- Governance (PII, TTL, LRU)
"""

from __future__ import annotations
import asyncio
import logging
from typing import Any, Dict, List, Optional

from core.config import load_config
from core.config.models import MemoryConfig
from core.memory.models import Memory, MemoryKind, MemoryQuery, MemoryResult, MemorySource, ConsolidationResult
from core.memory.store import MemoryStore, create_memory_store
from core.memory.consolidation import ConsolidationPipeline, ConsolidationConfig
from core.memory.governance import GovernanceManager
from core.structured_logging import get_logger, log_structured

logger = get_logger(__name__)


class MemorySystem:
    """
    Main memory system facade.

    Provides a unified interface for:
    - Storing memories (with governance)
    - Querying memories (hybrid vector + FTS)
    - Managing consolidation
    - Governance operations
    """

    def __init__(self, config: Optional[MemoryConfig] = None):
        self.config = config or load_config().memory
        self._store: Optional[MemoryStore] = None
        self._consolidation: Optional[ConsolidationPipeline] = None
        self._governance: Optional[GovernanceManager] = None
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize all memory system components."""
        log_structured(logger, logging.INFO, "Initializing Memory System")

        # Create store
        self._store = create_memory_store(self.config)
        await self._store.initialize()

        # Create governance manager
        self._governance = GovernanceManager(self._store, self.config)
        await self._governance.initialize()

        # Create consolidation pipeline
        consolidation_config = ConsolidationConfig(
            enabled=self.config.consolidation.enabled,
            interval_hours=self.config.consolidation.interval_hours,
            working_to_episodic_threshold=self.config.consolidation.working_to_episodic_threshold,
            episodic_to_semantic_threshold=self.config.consolidation.episodic_to_semantic_threshold,
            preference_extraction_enabled=self.config.consolidation.preference_extraction_enabled,
            procedural_learning_enabled=self.config.consolidation.procedural_learning_enabled,
        )
        self._consolidation = ConsolidationPipeline(
            memory_store=self._store,
            config=consolidation_config,
        )
        await self._consolidation.initialize()

        self._initialized = True
        log_structured(logger, logging.INFO, "Memory System initialized")

    async def shutdown(self) -> None:
        """Shutdown all memory system components."""
        log_structured(logger, logging.INFO, "Shutting down Memory System")

        if self._consolidation:
            await self._consolidation.shutdown()

        if self._governance:
            await self._governance.shutdown()

        if self._store:
            await self._store.shutdown()

        self._initialized = False
        log_structured(logger, logging.INFO, "Memory System stopped")

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    # =========================================================================
    # Core Memory Operations
    # =========================================================================

    async def store(
        self,
        kind: MemoryKind,
        content: str,
        confidence: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        ttl_seconds: Optional[int] = None,
        source: MemorySource = MemorySource.SYSTEM,
        embedding: Optional[List[float]] = None,
    ) -> str:
        """
        Store a new memory.

        Args:
            kind: Memory kind (SEMANTIC, EPISODIC, PROCEDURAL, PREFERENCE, WORKING)
            content: Memory content text
            confidence: Confidence score (0.0-1.0)
            metadata: Additional metadata
            tags: Tags for categorization
            ttl_seconds: Time to live in seconds (None for default based on kind)
            source: Memory source
            embedding: Pre-computed embedding (optional)

        Returns:
            Memory ID
        """
        if not self._initialized:
            raise RuntimeError("Memory system not initialized")

        memory = Memory(
            kind=kind,
            content=content,
            embedding=embedding,
            confidence=confidence,
            metadata=metadata or {},
            tags=tags or [],
            ttl_seconds=ttl_seconds,
            source=source,
        )

        # Process through governance
        memory = await self._governance.process_memory(memory)

        # Store
        memory_id = await self._store.store(memory)

        log_structured(logger, logging.DEBUG, "Memory stored",
                      memory_id=memory_id, kind=kind.value, length=len(content))

        return memory_id

    async def query(self, query: MemoryQuery) -> MemoryResult:
        """
        Query memories.

        Args:
            query: MemoryQuery with search parameters

        Returns:
            MemoryResult with matching memories
        """
        if not self._initialized:
            raise RuntimeError("Memory system not initialized")

        result = await self._store.query(query)

        # Touch accessed memories (update access time)
        for memory in result.memories:
            memory.touch()
            await self._store.update(memory.id, {
                "accessed_at": memory.accessed_at,
                "access_count": memory.access_count,
            })

        return result

    async def get(self, memory_id: str) -> Optional[Memory]:
        """Get a memory by ID."""
        if not self._initialized:
            raise RuntimeError("Memory system not initialized")

        memory = await self._store.get(memory_id)

        if memory:
            # Touch
            memory.touch()
            await self._store.update(memory.id, {
                "accessed_at": memory.accessed_at,
                "access_count": memory.access_count,
            })

        return memory

    async def update(self, memory_id: str, updates: Dict[str, Any]) -> bool:
        """Update a memory."""
        if not self._initialized:
            raise RuntimeError("Memory system not initialized")

        # If content is being updated, re-process through governance
        if "content" in updates:
            memory = await self._store.get(memory_id)
            if memory:
                memory.content = updates["content"]
                memory = await self._governance.process_memory(memory)
                updates["content"] = memory.content
                updates["pii_detected"] = memory.pii_detected
                updates["pii_types"] = memory.pii_types

        return await self._store.update(memory_id, updates)

    async def delete(self, memory_id: str) -> bool:
        """Delete a memory."""
        if not self._initialized:
            raise RuntimeError("Memory system not initialized")

        return await self._store.delete(memory_id)

    # =========================================================================
    # Consolidation Operations
    # =========================================================================

    async def trigger_consolidation(self, kind: Optional[str] = None) -> List[ConsolidationResult]:
        """
        Manually trigger consolidation.

        Args:
            kind: Specific consolidation kind, or None for all

        Returns:
            List of consolidation results
        """
        if not self._initialized:
            raise RuntimeError("Memory system not initialized")

        log_structured(logger, logging.INFO, "Manual consolidation triggered", kind=kind)
        return await self._consolidation.run_consolidation(kind)

    async def get_consolidation_status(self) -> Dict[str, Any]:
        """Get consolidation pipeline status."""
        if not self._initialized:
            raise RuntimeError("Memory system not initialized")

        return {
            "running": self._consolidation._running if self._consolidation else False,
            "interval_hours": self.config.consolidation.interval_hours,
            "enabled": self.config.consolidation.enabled,
        }

    # =========================================================================
    # Governance Operations
    # =========================================================================

    async def enforce_ttl(self) -> int:
        """Manually trigger TTL enforcement."""
        if not self._initialized:
            raise RuntimeError("Memory system not initialized")

        return await self._governance.enforce_ttl()

    async def enforce_lru(self) -> int:
        """Manually trigger LRU eviction."""
        if not self._initialized:
            raise RuntimeError("Memory system not initialized")

        return await self._governance.enforce_lru()

    async def get_governance_stats(self) -> Dict[str, Any]:
        """Get governance statistics."""
        if not self._initialized:
            raise RuntimeError("Memory system not initialized")

        return await self._governance.get_stats()

    # =========================================================================
    # Utility Operations
    # =========================================================================

    async def count(self, kind: Optional[MemoryKind] = None) -> int:
        """Count memories, optionally filtered by kind."""
        if not self._initialized:
            raise RuntimeError("Memory system not initialized")

        return await self._store.count(kind)

    async def health_check(self) -> bool:
        """Check memory system health."""
        if not self._initialized:
            return False

        return await self._store.health_check()

    async def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive memory system statistics."""
        if not self._initialized:
            return {"initialized": False}

        stats = {
            "initialized": True,
            "store_healthy": await self._store.health_check(),
            "counts": {},
            "governance": await self._governance.get_stats(),
        }

        for kind in MemoryKind:
            stats["counts"][kind.value] = await self._store.count(kind)

        stats["total"] = sum(stats["counts"].values())

        return stats


# Global memory system instance
_memory_system: Optional[MemorySystem] = None


async def get_memory_system() -> Optional[MemorySystem]:
    """Get the global memory system instance."""
    return _memory_system


async def init_memory_system(config: Optional[MemoryConfig] = None) -> MemorySystem:
    """Initialize the global memory system."""
    global _memory_system
    _memory_system = MemorySystem(config)
    await _memory_system.initialize()
    return _memory_system


async def shutdown_memory_system() -> None:
    """Shutdown the global memory system."""
    global _memory_system
    if _memory_system:
        await _memory_system.shutdown()
        _memory_system = None


__all__ = [
    "MemorySystem",
    "get_memory_system",
    "init_memory_system",
    "shutdown_memory_system",
]