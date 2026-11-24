"""
ARISE Database Models

All SQLAlchemy 2.0 models for ARISE entities:
- Tasks (with 28-state enum, checkpoints, priorities)
- Agents (specialists, coordinator, registry)
- Memories (5 kinds: semantic, episodic, procedural, preference, working)
- Events (event store, projections)
- Policies (risk levels, capabilities, grants, audit logs)
- Model Router (providers, usage, costs)
- Voice (sessions, transcripts)
- Automation (workflows, UI elements)
- Security (credentials, network rules, audit)
- Configuration (versioned configs)
- Feature Flags
- Users/Sessions
- API Keys
- Audit Logs
"""

import enum
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database.base import Base, TimestampMixin, UUIDMixin


# =============================================================================
# Enums
# =============================================================================

class TaskStatus(str, enum.Enum):
    """28-state task status enum."""
    # Initial states
    CREATED = "CREATED"
    QUEUED = "QUEUED"
    UNDERSTANDING = "UNDERSTANDING"
    PLANNING = "PLANNING"
    READY = "READY"

    # Execution states
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    WAITING_CAPABILITY = "WAITING_CAPABILITY"
    WAITING_RESOURCE = "WAITING_RESOURCE"
    WAITING_EXTERNAL = "WAITING_EXTERNAL"

    # Verification states
    VERIFYING = "VERIFYING"
    VERIFICATION_PASSED = "VERIFICATION_PASSED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"

    # Completion states
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"

    # Recovery states
    RETRYING = "RETRYING"
    ROLLING_BACK = "ROLLING_BACK"
    ROLLED_BACK = "ROLLED_BACK"
    COMPENSATING = "COMPENSATING"
    COMPENSATED = "COMPENSATED"

    # Special states
    SUSPENDED = "SUSPENDED"
    ARCHIVED = "ARCHIVED"
    DELETED = "DELETED"


class TaskPriority(int, enum.Enum):
    """Task priority levels."""
    LOW = -1
    NORMAL = 0
    HIGH = 1
    CRITICAL = 2


class RiskLevel(str, enum.Enum):
    """Risk levels R0-R4."""
    R0 = "R0"  # Read-only, safe
    R1 = "R1"  # Local write, no network
    R2 = "R2"  # Network access, file modify
    R3 = "R3"  # System modification, credentials
    R4 = "R4"  # Destructive, admin


class AgentType(str, enum.Enum):
    """Agent types."""
    COORDINATOR = "coordinator"
    RESEARCH = "research"
    CODING = "coding"
    BROWSER = "browser"
    ANALYSIS = "analysis"
    CREATIVE = "creative"
    AUTOMATION = "automation"
    MEMORY = "memory"
    SECURITY = "security"
    REVIEWER = "reviewer"
    COMMUNICATOR = "communicator"
    SCHEDULER = "scheduler"
    CUSTOM = "custom"


class AgentStatus(str, enum.Enum):
    """Agent health status."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"
    STARTING = "starting"
    STOPPING = "stopping"
    STOPPED = "stopped"


class MemoryKind(str, enum.Enum):
    """Memory kinds (5 types)."""
    SEMANTIC = "semantic"
    EPISODIC = "episodic"
    PROCEDURAL = "procedural"
    PREFERENCE = "preference"
    WORKING = "working"


class MemorySource(str, enum.Enum):
    """Memory source."""
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"
    CONSOLIDATION = "consolidation"
    IMPORT = "import"


class EventType(str, enum.Enum):
    """Event types for event store."""
    TASK_CREATED = "task_created"
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    TASK_CANCELLED = "task_cancelled"
    CHECKPOINT_CREATED = "checkpoint_created"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_GRANTED = "approval_granted"
    APPROVAL_DENIED = "approval_denied"
    AGENT_DELEGATED = "agent_delegated"
    AGENT_COMPLETED = "agent_completed"
    MEMORY_STORED = "memory_stored"
    MEMORY_CONSOLIDATED = "memory_consolidated"
    VOICE_SESSION_STARTED = "voice_session_started"
    VOICE_INTERACTION = "voice_interaction"
    WORKFLOW_STARTED = "workflow_started"
    WORKFLOW_COMPLETED = "workflow_completed"
    POLICY_EVALUATED = "policy_evaluated"
    CAPABILITY_GRANTED = "capability_granted"
    CAPABILITY_REVOKED = "capability_revoked"
    AUDIT_LOGGED = "audit_logged"
    SECURITY_EVENT = "security_event"
    CONFIG_CHANGED = "config_changed"
    FEATURE_FLAG_CHANGED = "feature_flag_changed"


class PolicyRiskLevel(str, enum.Enum):
    """Policy risk levels."""
    R0 = "R0"
    R1 = "R1"
    R2 = "R2"
    R3 = "R3"
    R4 = "R4"


class ProviderType(str, enum.Enum):
    """Model provider types."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    OLLAMA = "ollama"
    AZURE_OPENAI = "azure_openai"
    VERTEX_AI = "vertex_ai"
    LOCAL = "local"


class VoiceSessionStatus(str, enum.Enum):
    """Voice session status."""
    ACTIVE = "active"
    EXPIRED = "expired"
    ENDED = "ended"
    ERROR = "error"


class PrivacyMode(str, enum.Enum):
    """Voice privacy modes."""
    STANDARD = "standard"
    PRIVATE = "private"
    LOCAL_ONLY = "local_only"
    OFFLINE = "offline"


class WorkflowStatus(str, enum.Enum):
    """Workflow status."""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CredentialCategory(str, enum.Enum):
    """Credential categories."""
    API_KEYS = "api_keys"
    GRANTS = "grants"
    OAUTH_TOKENS = "oauth_tokens"
    SSH_KEYS = "ssh_keys"
    CERTIFICATES = "certificates"
    PASSWORDS = "passwords"


class NetworkAction(str, enum.Enum):
    """Network rule actions."""
    ALLOW = "allow"
    DENY = "deny"
    LOG = "log"


class SettingCategory(str, enum.Enum):
    """Setting categories."""
    APP = "app"
    SECURITY = "security"
    POLICY = "policy"
    MODEL_ROUTER = "model_router"
    VOICE = "voice"
    MEMORY = "memory"
    PERFORMANCE = "performance"
    AUTOMATION = "automation"
    AGENTS = "agents"


class FlagType(str, enum.Enum):
    """Feature flag types."""
    BOOLEAN = "boolean"
    STRING = "string"
    NUMBER = "number"
    JSON = "json"


class APIKeyScope(str, enum.Enum):
    """API key scopes."""
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"
    FULL = "full"


class AuditEventType(str, enum.Enum):
    """Audit event types."""
    TASK_OPERATION = "task_operation"
    AGENT_ACTION = "agent_action"
    MEMORY_ACCESS = "memory_access"
    VOICE_INTERACTION = "voice_interaction"
    AUTOMATION_ACTION = "automation_action"
    POLICY_EVALUATION = "policy_evaluation"
    CAPABILITY_GRANT = "capability_grant"
    CREDENTIAL_ACCESS = "credential_access"
    NETWORK_ACCESS = "network_access"
    CONFIG_CHANGE = "config_change"
    USER_ACTION = "user_action"
    SYSTEM_EVENT = "system_event"
    SECURITY_INCIDENT = "security_incident"


class SecuritySeverity(str, enum.Enum):
    """Security event severity."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class EvidenceType(str, enum.Enum):
    """Evidence types."""
    SCREENSHOT = "screenshot"
    LOG = "log"
    NETWORK_TRACE = "network_trace"
    FILE_DIFF = "file_diff"
    CLIPBOARD = "clipboard"
    UI_TREE = "ui_tree"
    AUDIO = "audio"
    VIDEO = "video"
    METADATA = "metadata"


# =============================================================================
# Task Engine Models
# =============================================================================

class Task(Base, UUIDMixin, TimestampMixin):
    """Main task table with 28-state enum, checkpoints, priorities."""

    # Core fields
    objective: Mapped[str] = mapped_column(Text, nullable=False, doc="User's objective")
    context_json: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict, doc="Full context as JSON"
    )
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus), nullable=False, default=TaskStatus.CREATED, doc="28-state enum"
    )
    risk_level: Mapped[RiskLevel] = mapped_column(
        Enum(RiskLevel), nullable=False, default=RiskLevel.R1, doc="R0-R4"
    )
    required_capabilities_json: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list, doc="JSON array of required capabilities"
    )
    granted_capabilities_json: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list, doc="JSON array of granted capabilities"
    )
    result_json: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, doc="Task result as JSON"
    )
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True, doc="Error message if failed")

    # Hierarchy
    parent_task_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("tasks.id"), nullable=True, index=True, doc="For subtasks"
    )
    root_task_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("tasks.id"), nullable=True, index=True, doc="Top-level task"
    )

    # Priority and timing
    priority: Mapped[TaskPriority] = mapped_column(
        Enum(TaskPriority), nullable=False, default=TaskPriority.NORMAL, doc="-1=low, 0=normal, 1=high, 2=critical"
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, doc="ISO 8601 UTC"
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, doc="ISO 8601 UTC"
    )
    timeout_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, doc="ISO 8601 UTC"
    )

    # Retry and saga
    retry_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, doc="Number of retries attempted"
    )
    max_retries: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3, doc="Maximum retries allowed"
    )
    saga_compensation_json: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, doc="Compensation steps as JSON"
    )
    metadata_json: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict, doc="Extensible metadata"
    )

    # Relationships
    parent_task: Mapped[Optional["Task"]] = relationship(
        "Task", foreign_keys=[parent_task_id], remote_side="Task.id", back_populates="subtasks"
    )
    subtasks: Mapped[list["Task"]] = relationship(
        "Task", foreign_keys=[parent_task_id], back_populates="parent_task", cascade="all, delete-orphan"
    )
    root_task: Mapped[Optional["Task"]] = relationship(
        "Task", foreign_keys=[root_task_id], remote_side="Task.id", back_populates="root_subtasks"
    )
    root_subtasks: Mapped[list["Task"]] = relationship(
        "Task", foreign_keys=[root_task_id], back_populates="root_task", cascade="all, delete-orphan"
    )
    checkpoints: Mapped[list["TaskCheckpoint"]] = relationship(
        "TaskCheckpoint", back_populates="task", cascade="all, delete-orphan"
    )
    dependencies: Mapped[list["TaskDependency"]] = relationship(
        "TaskDependency", foreign_keys="TaskDependency.task_id", back_populates="task", cascade="all, delete-orphan"
    )
    dependents: Mapped[list["TaskDependency"]] = relationship(
        "TaskDependency", foreign_keys="TaskDependency.depends_on_task_id", back_populates="depends_on_task"
    )
    approvals: Mapped[list["TaskApproval"]] = relationship(
        "TaskApproval", back_populates="task", cascade="all, delete-orphan"
    )
    events: Mapped[list["TaskEvent"]] = relationship(
        "TaskEvent", back_populates="task", cascade="all, delete-orphan"
    )

    # Indexes
    __table_args__ = (
        Index("idx_tasks_status", "status"),
        Index("idx_tasks_root", "root_task_id"),
        Index("idx_tasks_parent", "parent_task_id"),
        Index("idx_tasks_created", "created_at"),
        Index("idx_tasks_status_risk", "status", "risk_level"),
    )


class TaskCheckpoint(Base, UUIDMixin, TimestampMixin):
    """Checkpoints for crash recovery."""

    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step: Mapped[int] = mapped_column(Integer, nullable=False, doc="Step number")
    state: Mapped[str] = mapped_column(String(50), nullable=False, doc="State at checkpoint")
    context_json: Mapped[dict] = mapped_column(JSON, nullable=False, doc="Full context snapshot")
    executed_actions_json: Mapped[list] = mapped_column(JSON, nullable=False, doc="Actions executed so far")
    is_latest: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, doc="Flag for latest checkpoint"
    )

    # Relationship
    task: Mapped["Task"] = relationship("Task", back_populates="checkpoints")

    __table_args__ = (
        Index("idx_checkpoints_task", "task_id"),
        Index("idx_checkpoints_latest", "task_id", "is_latest"),
        Index("idx_checkpoints_step", "task_id", "step"),
    )


class TaskDependency(Base, TimestampMixin):
    """Task dependencies for DAG execution."""

    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, primary_key=True
    )
    depends_on_task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, primary_key=True
    )
    dependency_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="sequential", doc="sequential, parallel, conditional"
    )
    condition_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, doc="Condition for conditional deps")

    # Relationships
    task: Mapped["Task"] = relationship("Task", foreign_keys=[task_id], back_populates="dependencies")
    depends_on_task: Mapped["Task"] = relationship("Task", foreign_keys=[depends_on_task_id], back_populates="dependents")


class TaskApproval(Base, UUIDMixin, TimestampMixin):
    """Task approvals for capabilities."""

    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    capability: Mapped[str] = mapped_column(String(100), nullable=False, doc="Capability requested")
    risk_level: Mapped[RiskLevel] = mapped_column(Enum(RiskLevel), nullable=False, doc="R2-R4")
    resource: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, doc="Target resource")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True, doc="Human-readable description")
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, doc="ISO 8601 UTC")
    responded_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, doc="ISO 8601 UTC"
    )
    approved: Mapped[Optional[bool]] = mapped_column(
        Boolean, nullable=True, doc="1=approved, 0=denied, NULL=pending"
    )
    granted_by: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, doc="user, system, policy")
    grant_scope: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, doc="task, session, permanent")
    grant_duration_hours: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, doc="For temporary grants")
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, doc="ISO 8601 UTC")
    grant_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, doc="Reference to capability grant")

    # Relationship
    task: Mapped["Task"] = relationship("Task", back_populates="approvals")

    __table_args__ = (
        Index("idx_approvals_task", "task_id"),
        Index("idx_approvals_pending", "approved", postgresql_where=approved.is_(None)),
    )


class ScheduledTask(Base, UUIDMixin, TimestampMixin):
    """Scheduled tasks with cron expressions."""

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, doc="Unique schedule name")
    cron_expression: Mapped[str] = mapped_column(String(100), nullable=False, doc="5-field cron")
    objective: Mapped[str] = mapped_column(Text, nullable=False, doc="Task objective")
    context_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, doc="1=enabled, 0=disabled")
    next_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, doc="ISO 8601 UTC")
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, doc="ISO 8601 UTC")
    last_task_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, doc="Reference to last created task")
    timezone: Mapped[str] = mapped_column(String(50), nullable=False, default="local", doc="IANA timezone")
    max_catchup_runs: Mapped[int] = mapped_column(Integer, nullable=False, default=1, doc="For missed runs")
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        Index("idx_scheduled_next_run", "next_run_at", postgresql_where=enabled.is_(True)),
    )


class TaskEvent(Base, UUIDMixin, TimestampMixin):
    """Task events for debugging/replay."""

    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    from_state: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    to_state: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    step: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    details_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Relationship
    task: Mapped["Task"] = relationship("Task", back_populates="events")

    __table_args__ = (
        Index("idx_events_task", "task_id", "created_at"),
    )


# =============================================================================
# Agent Models
# =============================================================================

class Agent(Base, UUIDMixin, TimestampMixin):
    """Registered agents."""

    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    type: Mapped[AgentType] = mapped_column(Enum(AgentType), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    module_path: Mapped[str] = mapped_column(String(255), nullable=False, doc="Python import path")
    class_name: Mapped[str] = mapped_column(String(100), nullable=False)
    capabilities_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list, doc="JSON array of AgentCapability")
    config_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, doc="Agent-specific config")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Relationships
    health: Mapped[Optional["AgentHealth"]] = relationship(
        "AgentHealth", back_populates="agent", uselist=False, cascade="all, delete-orphan"
    )
    executions: Mapped[list["AgentExecution"]] = relationship(
        "AgentExecution", back_populates="agent", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_agents_type", "type"),
        Index("idx_agents_enabled", "enabled", postgresql_where=enabled.is_(True)),
    )


class AgentHealth(Base, TimestampMixin):
    """Agent health tracking."""

    __tablename__ = "agent_health"

    agent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[AgentStatus] = mapped_column(Enum(AgentStatus), nullable=False, default=AgentStatus.UNKNOWN)
    last_heartbeat: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_executions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    successful_executions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_execution_time_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_error_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    cpu_percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    memory_mb: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Relationship
    agent: Mapped["Agent"] = relationship("Agent", back_populates="health")

    __table_args__ = (
        Index("idx_health_status", "status"),
    )


class AgentExecution(Base, UUIDMixin, TimestampMixin):
    """Agent execution history."""

    agent_id: Mapped[str] = mapped_column(String(36), ForeignKey("agents.id"), nullable=False, index=True)
    task_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("tasks.id"), nullable=True, index=True)
    delegation_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, doc="From coordinator")
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, doc="completed, failed, cancelled")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    execution_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    result_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    verification_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, doc="verified, failed, pending")
    verification_issues_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Relationships
    agent: Mapped["Agent"] = relationship("Agent", back_populates="executions")

    __table_args__ = (
        Index("idx_executions_agent", "agent_id", "started_at"),
        Index("idx_executions_task", "task_id"),
    )


# =============================================================================
# Memory Models
# =============================================================================

class MemoryMetadata(Base, UUIDMixin, TimestampMixin):
    """Memory metadata for governance."""

    __tablename__ = "memory_metadata"

    kind: Mapped[MemoryKind] = mapped_column(Enum(MemoryKind), nullable=False, index=True)
    source: Mapped[MemorySource] = mapped_column(Enum(MemorySource), nullable=False, default=MemorySource.SYSTEM)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0, doc="0.0-1.0")
    pii_detected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, doc="1=PII flagged")
    pii_types_json: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, doc="JSON array of PII types")
    retention_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    access_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_accessed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    previous_version_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, doc="For corrections")
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        Index("idx_memory_metadata_kind", "kind"),
        Index("idx_memory_metadata_pii", "pii_detected", postgresql_where=pii_detected.is_(True)),
        Index("idx_memory_metadata_expires", "retention_expires_at", postgresql_where=retention_expires_at.is_not(None)),
        Index("idx_memory_metadata_accessed", "last_accessed_at"),
    )


class ConsolidationRun(Base, UUIDMixin, TimestampMixin):
    """Consolidation tracking."""

    kind: Mapped[str] = mapped_column(String(50), nullable=False, index=True, doc="working_to_episodic, episodic_summarization, etc.")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    input_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, doc="running, completed, failed")
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    config_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, doc="Consolidation config used")

    __table_args__ = (
        Index("idx_consolidation_kind", "kind", "started_at"),
    )


# =============================================================================
# Event Store Models
# =============================================================================

class Event(Base, UUIDMixin, TimestampMixin):
    """Event store for event sourcing."""

    __tablename__ = "events"

    event_type: Mapped[EventType] = mapped_column(Enum(EventType), nullable=False, index=True)
    aggregate_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True, doc="Entity ID (task, agent, etc.)")
    aggregate_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True, doc="task, agent, memory, etc.")
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, doc="Event payload")
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, doc="Event metadata")
    correlation_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True, doc="Correlation ID for tracing")
    causation_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, doc="Causation ID")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, doc="Event schema version")

    __table_args__ = (
        Index("idx_events_aggregate", "aggregate_type", "aggregate_id"),
        Index("idx_events_correlation", "correlation_id"),
        Index("idx_events_type_time", "event_type", "created_at"),
    )


class EventProjection(Base, UUIDMixin, TimestampMixin):
    """Event projections for read models."""

    __tablename__ = "event_projections"

    projection_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    last_event_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    last_processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    checkpoint_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        UniqueConstraint("projection_name", name="uq_projection_name"),
    )


# =============================================================================
# Policy Models
# =============================================================================

class Policy(Base, UUIDMixin, TimestampMixin):
    """Policies with risk levels and capabilities."""

    __tablename__ = "policies"

    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    risk_level: Mapped[PolicyRiskLevel] = mapped_column(Enum(PolicyRiskLevel), nullable=False)
    capabilities_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list, doc="Allowed capabilities")
    conditions_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, doc="Policy conditions")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0, doc="Higher = more specific")

    # Relationships
    grants: Mapped[list["CapabilityGrant"]] = relationship(
        "CapabilityGrant", back_populates="policy", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list["PolicyAuditLog"]] = relationship(
        "PolicyAuditLog", back_populates="policy", cascade="all, delete-orphan"
    )


class CapabilityGrant(Base, UUIDMixin, TimestampMixin):
    """Capability grants."""

    __tablename__ = "capability_grants"

    policy_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("policies.id"), nullable=True)
    capability: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    granted_to: Mapped[str] = mapped_column(String(100), nullable=False, index=True, doc="user, agent, task, role")
    granted_by: Mapped[str] = mapped_column(String(100), nullable=False)
    scope: Mapped[str] = mapped_column(String(20), nullable=False, doc="task, session, permanent")
    duration_hours: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    conditions_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Relationship
    policy: Mapped[Optional["Policy"]] = relationship("Policy", back_populates="grants")

    __table_args__ = (
        Index("idx_grants_active", "is_active", "expires_at", postgresql_where=is_active.is_(True)),
    )


class PolicyAuditLog(Base, UUIDMixin, TimestampMixin):
    """Policy evaluation audit logs."""

    __tablename__ = "policy_audit_logs"

    policy_id: Mapped[str] = mapped_column(String(36), ForeignKey("policies.id"), nullable=False, index=True)
    capability: Mapped[str] = mapped_column(String(100), nullable=False)
    resource: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    requested_by: Mapped[str] = mapped_column(String(100), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False, doc="granted, denied, deferred")
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    context_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # Relationship
    policy: Mapped["Policy"] = relationship("Policy", back_populates="audit_logs")


# =============================================================================
# Model Router Models
# =============================================================================

class ModelProvider(Base, UUIDMixin, TimestampMixin):
    """Model provider configurations."""

    __tablename__ = "model_providers"

    name: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    type: Mapped[ProviderType] = mapped_column(Enum(ProviderType), nullable=False)
    api_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    base_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    organization: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    default_model: Mapped[str] = mapped_column(String(100), nullable=False)
    models_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, doc="Model-specific configs")
    max_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=4096)
    timeout: Mapped[float] = mapped_column(Float, nullable=False, default=60.0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    supports_streaming: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    supports_functions: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    supports_vision: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    supports_audio: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cost_per_1k_input: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    cost_per_1k_output: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    rpm_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    tpm_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=100000)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Relationships
    usage_records: Mapped[list["ModelUsage"]] = relationship(
        "ModelUsage", back_populates="provider", cascade="all, delete-orphan"
    )
    cost_records: Mapped[list["ModelCost"]] = relationship(
        "ModelCost", back_populates="provider", cascade="all, delete-orphan"
    )


class ModelUsage(Base, UUIDMixin, TimestampMixin):
    """Model usage tracking."""

    __tablename__ = "model_usages"

    provider_id: Mapped[str] = mapped_column(String(36), ForeignKey("model_providers.id"), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    task_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationship
    provider: Mapped["ModelProvider"] = relationship("ModelProvider", back_populates="usage_records")

    __table_args__ = (
        Index("idx_usage_provider_model", "provider_id", "model"),
        Index("idx_usage_task", "task_id"),
        Index("idx_usage_created", "created_at"),
    )


class ModelCost(Base, UUIDMixin, TimestampMixin):
    """Model cost tracking."""

    __tablename__ = "model_costs"

    provider_id: Mapped[str] = mapped_column(String(36), ForeignKey("model_providers.id"), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    date: Mapped[str] = mapped_column(String(10), nullable=False, index=True, doc="YYYY-MM-DD")
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input_cost: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    output_cost: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_cost: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Relationship
    provider: Mapped["ModelProvider"] = relationship("ModelProvider", back_populates="cost_records")

    __table_args__ = (
        UniqueConstraint("provider_id", "model", "date", name="uq_provider_model_date"),
        Index("idx_cost_date", "date"),
    )


# =============================================================================
# Voice Models
# =============================================================================

class VoiceSession(Base, UUIDMixin, TimestampMixin):
    """Voice sessions."""

    user_id: Mapped[str] = mapped_column(String(100), nullable=False, default="local_user", index=True)
    privacy_mode: Mapped[PrivacyMode] = mapped_column(Enum(PrivacyMode), nullable=False)
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
    wake_word_used: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    total_interactions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_audio_duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[VoiceSessionStatus] = mapped_column(Enum(VoiceSessionStatus), nullable=False, default=VoiceSessionStatus.ACTIVE)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # Relationships
    interactions: Mapped[list["VoiceInteraction"]] = relationship(
        "VoiceInteraction", back_populates="session", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_voice_sessions_user", "user_id", "started_at"),
    )


class VoiceInteraction(Base, UUIDMixin, TimestampMixin):
    """Voice interactions (per command)."""

    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("voice_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, doc="Order in session")
    wake_word_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    asr_transcript: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    asr_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    asr_language: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    asr_duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    intent_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    intent_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    intent_entities_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    intent_duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    risk_level: Mapped[Optional[RiskLevel]] = mapped_column(Enum(RiskLevel), nullable=True)
    task_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    tts_provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    tts_duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tts_audio_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    barge_in: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    total_duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Relationship
    session: Mapped["VoiceSession"] = relationship("VoiceSession", back_populates="interactions")

    __table_args__ = (
        Index("idx_voice_interactions_session", "session_id", "sequence"),
        Index("idx_voice_interactions_task", "task_id"),
    )


# =============================================================================
# Automation Models
# =============================================================================

class Workflow(Base, UUIDMixin, TimestampMixin):
    """Automation workflows."""

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    steps_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list, doc="Workflow steps")
    status: Mapped[WorkflowStatus] = mapped_column(Enum(WorkflowStatus), nullable=False, default=WorkflowStatus.PENDING)
    task_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    current_step: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # Relationships
    ui_elements: Mapped[list["UIElement"]] = relationship(
        "UIElement", back_populates="workflow", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_workflows_task", "task_id"),
        Index("idx_workflows_status", "status"),
    )


class UIElement(Base, UUIDMixin, TimestampMixin):
    """UI elements for automation."""

    __tablename__ = "ui_elements"

    workflow_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("workflows.id"), nullable=True)
    selector: Mapped[str] = mapped_column(String(500), nullable=False, doc="UIA/Playwright selector")
    element_type: Mapped[str] = mapped_column(String(50), nullable=False, doc="button, input, link, etc.")
    text: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    attributes_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    bounding_box_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, doc="x, y, width, height")
    screenshot_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_interactive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)

    # Relationship
    workflow: Mapped[Optional["Workflow"]] = relationship("Workflow", back_populates="ui_elements")


# =============================================================================
# Security Models
# =============================================================================

class CredentialMetadata(Base, UUIDMixin, TimestampMixin):
    """Local metadata for credential management."""

    __tablename__ = "credential_metadata"

    category: Mapped[CredentialCategory] = mapped_column(Enum(CredentialCategory), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    target_name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, doc="Full CM target name")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    rotation_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint("category", "key", name="uq_cred_category_key"),
        Index("idx_cred_meta_category", "category"),
        Index("idx_cred_meta_expires", "expires_at", postgresql_where=expires_at.is_not(None)),
    )


class NetworkRule(Base, UUIDMixin, TimestampMixin):
    """Network access rules."""

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[NetworkAction] = mapped_column(Enum(NetworkAction), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False, doc="inbound, outbound")
    protocol: Mapped[str] = mapped_column(String(10), nullable=False, doc="tcp, udp, icmp")
    port: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    destination: Mapped[str] = mapped_column(String(255), nullable=False, doc="IP, CIDR, or domain")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index("idx_network_rules_active", "is_active", "priority"),
    )


class SecurityAuditLog(Base, UUIDMixin, TimestampMixin):
    """Security audit logs."""

    __tablename__ = "security_audit_logs"

    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    severity: Mapped[SecuritySeverity] = mapped_column(Enum(SecuritySeverity), nullable=False, index=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    agent_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    task_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    capability: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    risk_level: Mapped[Optional[RiskLevel]] = mapped_column(Enum(RiskLevel), nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    mitre_technique: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    response_action: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, doc="blocked, logged, alerted, lockdown")
    acknowledged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    context_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        Index("idx_security_audit_severity", "severity"),
        Index("idx_security_audit_category", "event_type"),
        Index("idx_security_audit_ack", "acknowledged", postgresql_where=acknowledged.is_(False)),
    )


# =============================================================================
# Configuration Models
# =============================================================================

class Setting(Base, TimestampMixin):
    """Application settings with versioning."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(255), primary_key=True, doc="Dot notation: voice.wake_word.sensitivity")
    value_json: Mapped[dict] = mapped_column(JSON, nullable=False, doc="JSON value")
    value_type: Mapped[str] = mapped_column(String(20), nullable=False, doc="string, number, boolean, object, array")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[SettingCategory] = mapped_column(Enum(SettingCategory), nullable=False, index=True)
    is_sensitive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, doc="1=contains secrets")
    is_runtime_mutable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, doc="1=can change without restart")
    validation_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, doc="JSON Schema for validation")
    default_value_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, doc="Default value")
    updated_by: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, doc="user, system, migration")

    # Relationships
    history: Mapped[list["SettingHistory"]] = relationship(
        "SettingHistory", back_populates="setting", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_settings_category", "category"),
        Index("idx_settings_sensitive", "is_sensitive", postgresql_where=is_sensitive.is_(True)),
    )


class SettingHistory(Base, UUIDMixin, TimestampMixin):
    """Settings history for rollback."""

    __tablename__ = "setting_history"

    key: Mapped[str] = mapped_column(String(255), ForeignKey("settings.key"), nullable=False, index=True)
    old_value_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    new_value_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    changed_by: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationship
    setting: Mapped["Setting"] = relationship("Setting", back_populates="history")


# =============================================================================
# Feature Flag Models
# =============================================================================

class FeatureFlag(Base, UUIDMixin, TimestampMixin):
    """Feature flags."""

    key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    flag_type: Mapped[FlagType] = mapped_column(Enum(FlagType), nullable=False, default=FlagType.BOOLEAN)
    default_value: Mapped[Any] = mapped_column(JSON, nullable=False, default=False)
    value: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    rollout_percentage: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)
    targeting_rules_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


# =============================================================================
# API Key Models
# =============================================================================

class APIKey(Base, UUIDMixin, TimestampMixin):
    """API Keys."""

    __tablename__ = "api_keys"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, doc="SHA256 hash of the key")
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False, doc="First 8 chars for identification")
    scopes_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list, doc="APIKeyScope array")
    user_id: Mapped[Optional[str]] = mapped_column(String(100), ForeignKey("users.id"), nullable=True, index=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        Index("idx_api_keys_user", "user_id"),
        Index("idx_api_keys_active", "is_active", "expires_at", postgresql_where=is_active.is_(True)),
    )


# =============================================================================
# User/Session Models
# =============================================================================

class User(Base, UUIDMixin):
    """Users."""

    username: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, unique=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    hashed_password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    sessions: Mapped[list["UserSession"]] = relationship(
        "UserSession", back_populates="user", cascade="all, delete-orphan"
    )
    api_keys: Mapped[list["APIKey"]] = relationship(
        "APIKey", foreign_keys="APIKey.user_id", back_populates="user", cascade="all, delete-orphan"
    )


class UserSession(Base, UUIDMixin, TimestampMixin):
    """User sessions."""

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    session_token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # Relationship
    user: Mapped["User"] = relationship("User", back_populates="sessions")


# Add back reference for APIKey
APIKey.user = relationship("User", back_populates="api_keys", foreign_keys=[APIKey.user_id])


# =============================================================================
# Audit Log Models
# =============================================================================

class AuditLog(Base, UUIDMixin, TimestampMixin):
    """Immutable audit log with hash chain."""

    __tablename__ = "audit_log"

    event_type: Mapped[AuditEventType] = mapped_column(Enum(AuditEventType), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(100), nullable=False, default="local_user")
    session_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    task_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    agent_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    capability: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    risk_level: Mapped[Optional[RiskLevel]] = mapped_column(Enum(RiskLevel), nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    context_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, doc="Sanitized context (no secrets)")
    previous_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, doc="Hash of previous event")
    event_hash: Mapped[str] = mapped_column(String(64), nullable=False, doc="SHA256 of this event")

    __table_args__ = (
        Index("idx_audit_timestamp", "timestamp"),
        Index("idx_audit_task", "task_id"),
        Index("idx_audit_type", "event_type"),
        Index("idx_audit_user", "user_id"),
        Index("idx_audit_hash_chain", "previous_hash"),
    )


class SecurityEvent(Base, UUIDMixin, TimestampMixin):
    """Security events (high-priority subset)."""

    event_id: Mapped[str] = mapped_column(String(36), ForeignKey("audit_log.id"), nullable=False, unique=True)
    severity: Mapped[SecuritySeverity] = mapped_column(Enum(SecuritySeverity), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True, doc="injection, auth, network, data, config")
    source_ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    mitre_technique: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    response_action: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, doc="blocked, logged, alerted, lockdown")
    acknowledged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    __table_args__ = (
        Index("idx_security_severity", "severity"),
        Index("idx_security_category", "category"),
        Index("idx_security_ack", "acknowledged", postgresql_where=acknowledged.is_(False)),
    )


# =============================================================================
# Evidence Models
# =============================================================================

class Evidence(Base, UUIDMixin, TimestampMixin):
    """Evidence records for audit and debugging."""

    __tablename__ = "evidence"

    task_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    agent_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    interaction_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    type: Mapped[EvidenceType] = mapped_column(Enum(EvidenceType), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False, doc="Relative to evidence root")
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mime_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False, doc="For integrity")
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, doc="Coordinates, selectors, URLs, etc.")

    # Relationships
    chain_links: Mapped[list["EvidenceChainLink"]] = relationship(
        "EvidenceChainLink", back_populates="evidence", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_evidence_task", "task_id"),
        Index("idx_evidence_agent", "agent_id"),
        Index("idx_evidence_type", "type"),
        Index("idx_evidence_created", "created_at"),
    )


class EvidenceChain(Base, UUIDMixin, TimestampMixin):
    """Evidence chains for multi-step operations."""

    task_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Relationships
    links: Mapped[list["EvidenceChainLink"]] = relationship(
        "EvidenceChainLink", back_populates="chain", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_evidence_chain_task", "task_id"),
    )


class EvidenceChainLink(Base, TimestampMixin):
    """Links between evidence and chains."""

    chain_id: Mapped[str] = mapped_column(String(36), ForeignKey("evidence_chains.id", ondelete="CASCADE"), nullable=False, primary_key=True)
    evidence_id: Mapped[str] = mapped_column(String(36), ForeignKey("evidence.id", ondelete="CASCADE"), nullable=False, primary_key=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)

    # Relationships
    chain: Mapped["EvidenceChain"] = relationship("EvidenceChain", back_populates="links")
    evidence: Mapped["Evidence"] = relationship("Evidence", back_populates="chain_links")

    __table_args__ = (
        # Primary key is (chain_id, sequence) implicitly via primary_key=True on both
    )