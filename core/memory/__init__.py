"""
Memory System Package.

Exports:
- MemorySystem: Main facade
- MemoryStore implementations
- ConsolidationPipeline
- GovernanceManager
- Models: Memory, MemoryQuery, MemoryResult, etc.
"""

from core.memory.models import (
    Memory,
    MemorySource,
    MemoryKind,
    MemoryQuery,
    MemoryResult,
    ConsolidationResult,
)

from core.memory.store import (
    MemoryStore,
    ChromaDBStore,
    SQLiteFTSStore,
    HybridMemoryStore,
    create_memory_store,
)

from core.memory.consolidation import (
    ConsolidationPipeline,
    ConsolidationConfig,
)

from core.memory.governance import (
    PIIDetector,
    PIIMatch,
    PIIAction,
    GovernanceManager,
)

from core.memory.system import (
    MemorySystem,
    get_memory_system,
    init_memory_system,
    shutdown_memory_system,
)

__all__ = [
    # Models
    "Memory",
    "MemorySource",
    "MemoryKind",
    "MemoryQuery",
    "MemoryResult",
    "ConsolidationResult",
    # Stores
    "MemoryStore",
    "ChromaDBStore",
    "SQLiteFTSStore",
    "HybridMemoryStore",
    "create_memory_store",
    # Consolidation
    "ConsolidationPipeline",
    "ConsolidationConfig",
    # Governance
    "PIIDetector",
    "PIIMatch",
    "PIIAction",
    "GovernanceManager",
    # System
    "MemorySystem",
    "get_memory_system",
    "init_memory_system",
    "shutdown_memory_system",
]