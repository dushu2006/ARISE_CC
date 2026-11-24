# core/errors/base.py
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum
import traceback
import uuid
import time


class ErrorCode(str, Enum):
    # System
    INVALID_REQUEST = "INVALID_REQUEST"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    TIMEOUT = "TIMEOUT"

    # Task
    TASK_NOT_FOUND = "TASK_NOT_FOUND"
    TASK_NOT_CANCELLABLE = "TASK_NOT_CANCELLABLE"
    TASK_ALREADY_COMPLETED = "TASK_ALREADY_COMPLETED"
    TASK_DEPENDENCY_FAILED = "TASK_DEPENDENCY_FAILED"
    TASK_TIMEOUT = "TASK_TIMEOUT"
    TASK_SAGA_COMPENSATION_FAILED = "TASK_SAGA_COMPENSATION_FAILED"

    # Policy
    APPROVAL_EXPIRED = "APPROVAL_EXPIRED"
    APPROVAL_DENIED = "APPROVAL_DENIED"
    CAPABILITY_DENIED = "CAPABILITY_DENIED"
    RISK_TOO_HIGH = "RISK_TOO_HIGH"
    GRANT_EXPIRED = "GRANT_EXPIRED"
    POLICY_NOT_FOUND = "POLICY_NOT_FOUND"
    POLICY_CONFLICT = "POLICY_CONFLICT"

    # Model
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    CIRCUIT_OPEN = "CIRCUIT_OPEN"
    MODEL_TIMEOUT = "MODEL_TIMEOUT"
    TOKEN_LIMIT_EXCEEDED = "TOKEN_LIMIT_EXCEEDED"
    CONTENT_FILTERED = "CONTENT_FILTERED"
    MODEL_NOT_FOUND = "MODEL_NOT_FOUND"
    PROVIDER_AUTH_FAILED = "PROVIDER_AUTH_FAILED"
    PROVIDER_RATE_LIMITED = "PROVIDER_RATE_LIMITED"

    # Voice
    WAKE_WORD_NOT_LOADED = "WAKE_WORD_NOT_LOADED"
    ASR_FAILED = "ASR_FAILED"
    TTS_FAILED = "TTS_FAILED"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    AUDIO_DEVICE_ERROR = "AUDIO_DEVICE_ERROR"
    VOICE_PIPELINE_ERROR = "VOICE_PIPELINE_ERROR"
    BARGE_IN_FAILED = "BARGE_IN_FAILED"

    # Memory
    MEMORY_STORE_FULL = "MEMORY_STORE_FULL"
    PII_DETECTED = "PII_DETECTED"
    MEMORY_NOT_FOUND = "MEMORY_NOT_FOUND"
    CONSOLIDATION_FAILED = "CONSOLIDATION_FAILED"
    EMBEDDING_FAILED = "EMBEDDING_FAILED"
    VECTOR_STORE_ERROR = "VECTOR_STORE_ERROR"
    RETENTION_POLICY_VIOLATION = "RETENTION_POLICY_VIOLATION"

    # Agent
    AGENT_UNHEALTHY = "AGENT_UNHEALTHY"
    AGENT_TIMEOUT = "AGENT_TIMEOUT"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    DELEGATION_FAILED = "DELEGATION_FAILED"
    AGENT_NOT_FOUND = "AGENT_NOT_FOUND"
    COORDINATOR_UNAVAILABLE = "COORDINATOR_UNAVAILABLE"

    # Automation
    UIA_ELEMENT_NOT_FOUND = "UIA_ELEMENT_NOT_FOUND"
    PLAYWRIGHT_NAVIGATION_FAILED = "PLAYWRIGHT_NAVIGATION_FAILED"
    CV_OCR_LOW_CONFIDENCE = "CV_OCR_LOW_CONFIDENCE"
    AUTOMATION_TIMEOUT = "AUTOMATION_TIMEOUT"
    APPLICATION_NOT_FOUND = "APPLICATION_NOT_FOUND"
    PERMISSION_DENIED = "PERMISSION_DENIED"

    # Security
    CREDENTIAL_NOT_FOUND = "CREDENTIAL_NOT_FOUND"
    NETWORK_BLOCKED = "NETWORK_BLOCKED"
    AUDIT_TAMPERED = "AUDIT_TAMPERED"
    PROMPT_INJECTION_DETECTED = "PROMPT_INJECTION_DETECTED"
    ENCRYPTION_FAILED = "ENCRYPTION_FAILED"
    KEY_ROTATION_FAILED = "KEY_ROTATION_FAILED"

    # Configuration
    CONFIG_VALIDATION_FAILED = "CONFIG_VALIDATION_FAILED"
    SECRET_NOT_FOUND = "SECRET_NOT_FOUND"
    FEATURE_FLAG_NOT_FOUND = "FEATURE_FLAG_NOT_FOUND"
    MIGRATION_FAILED = "MIGRATION_FAILED"

    # Events
    EVENT_STORE_ERROR = "EVENT_STORE_ERROR"
    PROJECTION_ERROR = "PROJECTION_ERROR"
    DEAD_LETTER_QUEUE_FULL = "DEAD_LETTER_QUEUE_FULL"

    # Database
    DATABASE_CONNECTION_FAILED = "DATABASE_CONNECTION_FAILED"
    MIGRATION_ERROR = "MIGRATION_ERROR"
    CONSTRAINT_VIOLATION = "CONSTRAINT_VIOLATION"


@dataclass
class ErrorContext:
    """Structured error context for debugging"""
    error_id: str = field(default_factory=lambda: f"err_{uuid.uuid4().hex[:12]}")
    timestamp: str = ""  # ISO 8601
    component: str = ""
    operation: str = ""
    correlation_id: str = ""
    causation_id: str = ""
    user_id: str = "local_user"
    session_id: str = ""
    task_id: str = ""
    agent_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    stack_trace: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_id": self.error_id,
            "timestamp": self.timestamp,
            "component": self.component,
            "operation": self.operation,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "metadata": self.metadata,
        }


class AriseError(Exception):
    """Base exception for all ARISE errors"""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        context: Optional[ErrorContext] = None,
        recoverable: bool = False,
        retry_after: Optional[float] = None,
        suggested_actions: List[str] = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.context = context or ErrorContext()
        self.recoverable = recoverable
        self.retry_after = retry_after
        self.suggested_actions = suggested_actions or []

        # Auto-capture stack trace
        if not self.context.stack_trace:
            self.context.stack_trace = "".join(traceback.format_stack()[:-1])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": {
                "code": self.code.value,
                "message": self.message,
                "recoverable": self.recoverable,
                "retry_after": self.retry_after,
                "suggested_actions": self.suggested_actions,
                "context": self.context.to_dict(),
            }
        }

    def to_json(self) -> str:
        import json
        return json.dumps(self.to_dict(), default=str)


# Domain-specific exceptions

class TaskError(AriseError):
    """Task engine errors"""
    pass


class PolicyError(AriseError):
    """Policy engine errors"""
    pass


class ModelError(AriseError):
    """Model router errors"""
    pass


class VoiceError(AriseError):
    """Voice pipeline errors"""
    pass


class MemoryError(AriseError):
    """Memory system errors"""
    pass


class AgentError(AriseError):
    """Agent system errors"""
    pass


class AutomationError(AriseError):
    """Desktop automation errors"""
    pass


class SecurityError(AriseError):
    """Security system errors"""
    pass


class ConfigurationError(AriseError):
    """Configuration errors"""
    pass


class EventError(AriseError):
    """Event bus errors"""
    pass


class DatabaseError(AriseError):
    """Database errors"""
    pass