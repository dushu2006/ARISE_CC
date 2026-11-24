"""
ARISE Database Package

SQLAlchemy 2.0 async database layer with models for all ARISE entities.
"""

from core.database.base import (
    Base,
    AsyncSessionLocal,
    get_async_engine,
    get_async_session_factory,
    get_async_session,
    init_db,
    close_db,
    DatabaseManager,
    get_database_manager,
    get_engine,
    get_session_factory,
    get_session,
    run_migrations,
    check_database_health,
    drop_all_tables,
    get_or_create,
    bulk_insert,
    get_table_names,
)
from core.database.models import (
    # Enums
    TaskStatus,
    TaskPriority,
    RiskLevel,
    AgentType,
    AgentStatus,
    MemoryKind,
    MemorySource,
    EventType,
    PolicyRiskLevel,
    ProviderType,
    VoiceSessionStatus,
    PrivacyMode,
    WorkflowStatus,
    CredentialCategory,
    NetworkAction,
    SettingCategory,
    FlagType,
    APIKeyScope,
    AuditEventType,
    SecuritySeverity,
    EvidenceType,
    # Task models
    Task,
    TaskCheckpoint,
    TaskDependency,
    TaskApproval,
    ScheduledTask,
    TaskEvent,
    # Agent models
    Agent,
    AgentHealth,
    AgentExecution,
    # Memory models
    MemoryMetadata,
    ConsolidationRun,
    # Voice models
    VoiceSession,
    VoiceInteraction,
    # Security models
    CredentialMetadata,
    # Configuration models
    Setting,
    SettingHistory,
    # Feature Flag models
    FeatureFlag,
    # API Key models
    APIKey,
    # User/Session models
    User,
    UserSession,
    # Audit Log models
    AuditLog,
    SecurityEvent,
    # Evidence models
    Evidence,
    EvidenceChain,
    EvidenceChainLink,
)

__version__ = "1.0.0"

__all__ = [
    # Base components
    "Base",
    "AsyncSessionLocal",
    "get_async_engine",
    "get_async_session_factory",
    "get_async_session",
    "init_db",
    "close_db",
    "DatabaseManager",
    "get_database_manager",
    "get_engine",
    "get_session_factory",
    "get_session",
    "run_migrations",
    "check_database_health",
    "drop_all_tables",
    "get_or_create",
    "bulk_insert",
    "get_table_names",
    # Enums
    "TaskStatus",
    "TaskPriority",
    "RiskLevel",
    "AgentType",
    "AgentStatus",
    "MemoryKind",
    "MemorySource",
    "EventType",
    "PolicyRiskLevel",
    "ProviderType",
    "VoiceSessionStatus",
    "PrivacyMode",
    "WorkflowStatus",
    "CredentialCategory",
    "NetworkAction",
    "SettingCategory",
    "FlagType",
    "APIKeyScope",
    "AuditEventType",
    "SecuritySeverity",
    "EvidenceType",
    # Tasks
    "Task",
    "TaskCheckpoint",
    "TaskDependency",
    "TaskApproval",
    "ScheduledTask",
    "TaskEvent",
    # Agents
    "Agent",
    "AgentHealth",
    "AgentExecution",
    # Memories
    "MemoryMetadata",
    "ConsolidationRun",
    # Voice
    "VoiceSession",
    "VoiceInteraction",
    # Security
    "CredentialMetadata",
    # Configuration
    "Setting",
    "SettingHistory",
    # Feature Flags
    "FeatureFlag",
    # API Keys
    "APIKey",
    # Users/Sessions
    "User",
    "UserSession",
    # Audit Logs
    "AuditLog",
    "SecurityEvent",
    # Evidence
    "Evidence",
    "EvidenceChain",
    "EvidenceChainLink",
]