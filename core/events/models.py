# core/events/models.py
"""
Event models for the ARISE event bus system.

Provides the core Event dataclass with priority, serialization,
and correlation tracing capabilities.
"""

from __future__ import annotations
import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import IntEnum
from typing import Any, Optional


class EventPriority(IntEnum):
    """Event priority levels (higher = more urgent)."""
    LOW = 0
    NORMAL = 50
    HIGH = 100
    CRITICAL = 200


@dataclass
class Event:
    """
    Core event structure for the ARISE event bus.

    All events flowing through the system use this format.
    Supports priority queue ordering, correlation tracing,
    and full JSON serialization.
    """
    # Core identification
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: str = ""  # e.g., "task.created", "agent.health_check"

    # Payload
    payload: dict[str, Any] = field(default_factory=dict)

    # Priority for queue ordering
    priority: EventPriority = EventPriority.NORMAL

    # Correlation & tracing
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    causation_id: Optional[str] = None  # ID of event that caused this one

    # Context
    source: str = ""  # Component that emitted the event
    task_id: Optional[str] = None
    agent_id: Optional[str] = None
    session_id: Optional[str] = None

    # Timestamps
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None  # Optional TTL

    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    # Retry tracking (for dead letter handling)
    retry_count: int = 0
    max_retries: int = 3

    def __post_init__(self):
        """Validate required fields after initialization."""
        if not self.type:
            raise ValueError("Event type is required")
        if not self.source:
            raise ValueError("Event source is required")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = asdict(self)
        # Convert enums and datetime to serializable formats
        data["priority"] = int(self.priority)
        data["timestamp"] = self.timestamp.isoformat()
        if self.expires_at:
            data["expires_at"] = self.expires_at.isoformat()
        else:
            data["expires_at"] = None
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Event:
        """Create Event from dictionary."""
        # Handle priority conversion
        if "priority" in data and isinstance(data["priority"], int):
            data["priority"] = EventPriority(data["priority"])

        # Handle datetime conversion
        if "timestamp" in data and isinstance(data["timestamp"], str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        if "expires_at" in data and data["expires_at"] and isinstance(data["expires_at"], str):
            data["expires_at"] = datetime.fromisoformat(data["expires_at"])

        return cls(**data)

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), default=str)

    @classmethod
    def from_json(cls, json_str: str) -> Event:
        """Deserialize from JSON string."""
        return cls.from_dict(json.loads(json_str))

    def is_expired(self) -> bool:
        """Check if event has expired."""
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at

    def with_correlation(self, correlation_id: str) -> Event:
        """Create a new event with updated correlation ID (for chaining)."""
        new_event = Event(
            id=str(uuid.uuid4()),
            type=self.type,
            payload=self.payload.copy(),
            priority=self.priority,
            correlation_id=correlation_id,
            causation_id=self.id,
            source=self.source,
            task_id=self.task_id,
            agent_id=self.agent_id,
            session_id=self.session_id,
            timestamp=datetime.now(timezone.utc),
            metadata=self.metadata.copy(),
        )
        return new_event

    def __lt__(self, other: Event) -> bool:
        """Compare by priority for PriorityQueue (higher priority first)."""
        if not isinstance(other, Event):
            return NotImplemented
        # Higher priority value = higher priority
        # For same priority, earlier timestamp comes first
        if self.priority != other.priority:
            return self.priority > other.priority
        return self.timestamp < other.timestamp


# Common event type constants
class EventTypes:
    """Standard event type prefixes for consistency."""

    # Task events
    TASK_CREATED = "task.created"
    TASK_QUEUED = "task.queued"
    TASK_STARTED = "task.started"
    TASK_PROGRESS = "task.progress"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    TASK_CANCELLED = "task.cancelled"
    TASK_CHECKPOINT = "task.checkpoint"
    TASK_RETRY = "task.retry"

    # Task step events
    TASK_STEP_STARTED = "task.step.started"
    TASK_STEP_COMPLETED = "task.step.completed"
    TASK_STEP_FAILED = "task.step.failed"

    # Agent events
    AGENT_REGISTERED = "agent.registered"
    AGENT_HEARTBEAT = "agent.heartbeat"
    AGENT_HEALTH_CHANGED = "agent.health_changed"
    AGENT_DELEGATION_STARTED = "agent.delegation.started"
    AGENT_DELEGATION_COMPLETED = "agent.delegation.completed"
    AGENT_DELEGATION_FAILED = "agent.delegation.failed"
    AGENT_VERIFICATION_STARTED = "agent.verification.started"
    AGENT_VERIFICATION_COMPLETED = "agent.verification.completed"
    AGENT_SHUTDOWN = "agent.shutdown"

    # Policy events
    POLICY_EVALUATED = "policy.evaluated"
    POLICY_APPROVAL_REQUESTED = "policy.approval.requested"
    POLICY_APPROVAL_GRANTED = "policy.approval.granted"
    POLICY_APPROVAL_DENIED = "policy.approval.denied"
    POLICY_APPROVAL_EXPIRED = "policy.approval.expired"
    POLICY_GRANT_CREATED = "policy.grant.created"
    POLICY_GRANT_REVOKED = "policy.grant.revoked"

    # Model events
    MODEL_REQUEST = "model.request"
    MODEL_RESPONSE = "model.response"
    MODEL_STREAM_CHUNK = "model.stream_chunk"
    MODEL_ERROR = "model.error"
    MODEL_CIRCUIT_OPEN = "model.circuit_open"
    MODEL_CIRCUIT_CLOSED = "model.circuit_closed"

    # Memory events
    MEMORY_STORED = "memory.stored"
    MEMORY_QUERIED = "memory.queried"
    MEMORY_UPDATED = "memory.updated"
    MEMORY_DELETED = "memory.deleted"
    MEMORY_CONSOLIDATION_STARTED = "memory.consolidation.started"
    MEMORY_CONSOLIDATION_COMPLETED = "memory.consolidation.completed"

    # Voice events
    VOICE_SESSION_STARTED = "voice.session.started"
    VOICE_WAKE_WORD_DETECTED = "voice.wake_word.detected"
    VOICE_ASR_RESULT = "voice.asr.result"
    VOICE_TTS_STARTED = "voice.tts.started"
    VOICE_TTS_COMPLETED = "voice.tts.completed"
    VOICE_BARGE_IN = "voice.barge_in"
    VOICE_SESSION_ENDED = "voice.session.ended"

    # Automation events
    AUTOMATION_ACTION_STARTED = "automation.action.started"
    AUTOMATION_ACTION_COMPLETED = "automation.action.completed"
    AUTOMATION_ACTION_FAILED = "automation.action.failed"
    AUTOMATION_ELEMENT_FOUND = "automation.element.found"
    AUTOMATION_SCREENSHOT = "automation.screenshot"
    AUTOMATION_OCR_RESULT = "automation.ocr.result"

    # Config events
    CONFIG_CHANGED = "config.changed"
    CONFIG_RELOADED = "config.reloaded"
    SECRET_STORED = "secret.stored"
    SECRET_ROTATED = "secret.rotated"

    # Security events
    SECURITY_CREDENTIAL_ACCESSED = "security.credential.accessed"
    SECURITY_NETWORK_BLOCKED = "security.network.blocked"
    SECURITY_PROMPT_INJECTION = "security.prompt_injection.detected"
    SECURITY_AUDIT_TAMPERED = "security.audit.tampered"

    # System events
    SYSTEM_STARTUP = "system.startup"
    SYSTEM_SHUTDOWN = "system.shutdown"
    SYSTEM_HEALTH_CHECK = "system.health_check"
    SYSTEM_ERROR = "system.error"


# Type alias for event handlers
EventHandler = Any  # Will be refined in handlers.py