"""
Policy Engine Models.

Defines core data structures for the policy engine:
- Risk levels (R0-R4)
- Capabilities (30+ system capabilities)
- Capability grants with TTL and scoping
- Approval requests and decisions
- Audit log entries with tamper-evident hashing
"""

from __future__ import annotations
import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    """Risk levels for capability evaluation."""
    R0 = "R0"  # Read-only, auto-approve
    R1 = "R1"  # Local write, auto-approve with notification
    R2 = "R2"  # System change, requires approval
    R3 = "R3"  # External communication, requires MFA approval
    R4 = "R4"  # Irreversible/critical, deny by default


class Capability(str, Enum):
    """System capabilities that require policy evaluation."""
    # Task capabilities
    TASK_EXECUTE = "task.execute"
    TASK_CANCEL = "task.cancel"
    TASK_DELEGATE = "task.delegate"

    # Filesystem capabilities
    FILESYSTEM_READ = "filesystem.read"
    FILESYSTEM_WRITE = "filesystem.write"
    FILESYSTEM_DELETE = "filesystem.delete"
    FILESYSTEM_LIST = "filesystem.list"

    # Shell capabilities
    SHELL_EXEC = "shell.exec"
    SHELL_INTERACTIVE = "shell.interactive"

    # Network capabilities
    NETWORK_HTTP = "network.http"
    NETWORK_WEBSOCKET = "network.websocket"
    NETWORK_RAW = "network.raw"
    NETWORK_EGRESS = "network.egress"

    # Browser capabilities
    BROWSER_NAVIGATE = "browser.navigate"
    BROWSER_CLICK = "browser.click"
    BROWSER_EXTRACT = "browser.extract"
    BROWSER_SCREENSHOT = "browser.screenshot"
    BROWSER_SCRIPT = "browser.script"

    # UIA capabilities
    UIA_FIND = "uia.find"
    UIA_CLICK = "uia.click"
    UIA_INPUT = "uia.input"
    UIA_SCROLL = "uia.scroll"

    # Memory capabilities
    MEMORY_STORE = "memory.store"
    MEMORY_QUERY = "memory.query"
    MEMORY_DELETE = "memory.delete"
    MEMORY_CONSOLIDATE = "memory.consolidate"

    # Voice capabilities
    VOICE_LISTEN = "voice.listen"
    VOICE_SPEAK = "voice.speak"
    VOICE_WAKE_WORD = "voice.wake_word"
    VOICE_BARGE_IN = "voice.barge_in"

    # Agent capabilities
    AGENT_DELEGATE = "agent.delegate"
    AGENT_VERIFY = "agent.verify"
    AGENT_SPAWN = "agent.spawn"

    # Configuration capabilities
    CONFIG_READ = "config.read"
    CONFIG_WRITE = "config.write"

    # Secrets capabilities
    SECRETS_READ = "secrets.read"
    SECRETS_WRITE = "secrets.write"

    # System capabilities
    SYSTEM_SHUTDOWN = "system.shutdown"
    SYSTEM_REBOOT = "system.reboot"
    SYSTEM_UPDATE = "system.update"

    # Credential capabilities
    CREDENTIALS_READ = "credentials.read"
    CREDENTIALS_WRITE = "credentials.write"

    # Security capabilities
    SECURITY_AUDIT = "security.audit"
    SECURITY_POLICY_WRITE = "security.policy.write"

    # Model capabilities
    MODEL_ACCESS = "model.access"
    MODEL_TRAIN = "model.train"


class ApprovalStatus(str, Enum):
    """Approval request status."""
    PENDING = "pending"
    GRANTED = "granted"
    DENIED = "denied"
    EXPIRED = "expired"


class Decision(str, Enum):
    """Policy evaluation decision."""
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"


@dataclass
class CapabilityGrant:
    """A granted capability with scope, conditions, and TTL."""
    grant_id: str
    capability: Capability
    scope: Dict[str, Any]  # Resource patterns, paths, etc.
    conditions: Dict[str, Any] = field(default_factory=dict)
    ttl_seconds: Optional[int] = None
    granted_to: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
    revoked: bool = False
    revoked_at: Optional[datetime] = None
    revoked_by: Optional[str] = None

    def __post_init__(self):
        if self.expires_at is None and self.ttl_seconds:
            from datetime import timedelta
            self.expires_at = self.created_at + timedelta(seconds=self.ttl_seconds)
        if not self.grant_id:
            self.grant_id = f"grant_{uuid.uuid4().hex[:12]}"

    def is_valid(self, resource: Optional[str] = None) -> bool:
        """Check if grant is still valid for a resource."""
        if self.revoked:
            return False
        if self.expires_at and datetime.now(timezone.utc) > self.expires_at:
            return False
        if resource and not self._matches_scope(resource):
            return False
        return True

    def _matches_scope(self, resource: str) -> bool:
        """Check if resource matches grant scope patterns."""
        patterns = self.scope.get("patterns", [])
        if not patterns:
            return True
        import fnmatch
        return any(fnmatch.fnmatch(resource, pattern) for pattern in patterns)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "grant_id": self.grant_id,
            "capability": self.capability.value,
            "scope": self.scope,
            "conditions": self.conditions,
            "ttl_seconds": self.ttl_seconds,
            "granted_to": self.granted_to,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "revoked": self.revoked,
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None,
            "revoked_by": self.revoked_by,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CapabilityGrant":
        grant = cls(
            grant_id=data.get("grant_id", ""),
            capability=Capability(data["capability"]),
            scope=data.get("scope", {}),
            conditions=data.get("conditions", {}),
            ttl_seconds=data.get("ttl_seconds"),
            granted_to=data.get("granted_to", ""),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(timezone.utc),
            expires_at=datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None,
            revoked=data.get("revoked", False),
            revoked_at=datetime.fromisoformat(data["revoked_at"]) if data.get("revoked_at") else None,
            revoked_by=data.get("revoked_by"),
        )
        return grant


@dataclass
class ApprovalRequest:
    """A request for capability approval."""
    approval_id: str
    task_id: str
    capability: Capability
    context: Dict[str, Any]
    requested_by: str
    ttl_seconds: int = 300
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
    decided_at: Optional[datetime] = None
    decided_by: Optional[str] = None
    decision: Optional[Decision] = None

    def __post_init__(self):
        if self.expires_at is None:
            from datetime import timedelta
            self.expires_at = self.created_at + timedelta(seconds=self.ttl_seconds)
        if not self.approval_id:
            self.approval_id = f"approval_{uuid.uuid4().hex[:12]}"

    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) > self.expires_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "approval_id": self.approval_id,
            "task_id": self.task_id,
            "capability": self.capability.value,
            "context": self.context,
            "requested_by": self.requested_by,
            "ttl_seconds": self.ttl_seconds,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "decided_at": self.decided_at.isoformat() if self.decided_at else None,
            "decided_by": self.decided_by,
            "decision": self.decision.value if self.decision else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ApprovalRequest":
        return cls(
            approval_id=data.get("approval_id", ""),
            task_id=data["task_id"],
            capability=Capability(data["capability"]),
            context=data.get("context", {}),
            requested_by=data["requested_by"],
            ttl_seconds=data.get("ttl_seconds", 300),
            status=ApprovalStatus(data.get("status", "pending")),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(timezone.utc),
            expires_at=datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None,
            decided_at=datetime.fromisoformat(data["decided_at"]) if data.get("decided_at") else None,
            decided_by=data.get("decided_by"),
            decision=Decision(data["decision"]) if data.get("decision") else None,
        )


@dataclass
class ApprovalDecision:
    """Result of an approval decision."""
    approval_id: str
    status: ApprovalStatus
    decided_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    decided_by: str = ""
    decision: Optional[Decision] = None
    ttl_seconds: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "approval_id": self.approval_id,
            "status": self.status.value,
            "decided_at": self.decided_at.isoformat(),
            "decided_by": self.decided_by,
            "decision": self.decision.value if self.decision else None,
            "ttl_seconds": self.ttl_seconds,
        }


@dataclass
class PolicyEvaluationResult:
    """Result of a policy evaluation."""
    capability: Capability
    risk_level: RiskLevel
    decision: Decision
    required_approvals: List[str] = field(default_factory=list)
    reasoning: str = ""
    expires_at: Optional[datetime] = None
    grants_matched: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "capability": self.capability.value,
            "risk_level": self.risk_level.value,
            "decision": self.decision.value,
            "required_approvals": self.required_approvals,
            "reasoning": self.reasoning,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "grants_matched": self.grants_matched,
        }


@dataclass
class PolicyAuditEntry:
    """Tamper-evident audit log entry."""
    id: str
    timestamp: datetime
    event_type: str  # evaluation, approval_requested, approval_decided, grant_created, grant_revoked
    capability: Capability
    subject: str  # Who performed the action (user, agent, system)
    resource: str  # Resource affected
    result: str  # allow, deny, require_approval, granted, denied, created, revoked
    details: Dict[str, Any]
    previous_hash: str = ""
    hash: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = f"audit_{uuid.uuid4().hex[:16]}"
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc)
        self.hash = self._compute_hash()

    def _compute_hash(self) -> str:
        """Compute tamper-evident hash including previous entry hash."""
        data = {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type,
            "capability": self.capability.value,
            "subject": self.subject,
            "resource": self.resource,
            "result": self.result,
            "details": self.details,
            "previous_hash": self.previous_hash,
        }
        # Sort keys for deterministic hashing
        serialized = json.dumps(data, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(serialized.encode()).hexdigest()

    def verify(self, previous_hash: str = "") -> bool:
        """Verify the integrity of this audit entry."""
        expected_hash = self._compute_hash()
        return self.hash == expected_hash and self.previous_hash == previous_hash

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type,
            "capability": self.capability.value,
            "subject": self.subject,
            "resource": self.resource,
            "result": self.result,
            "details": self.details,
            "previous_hash": self.previous_hash,
            "hash": self.hash,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PolicyAuditEntry":
        return cls(
            id=data.get("id", ""),
            timestamp=datetime.fromisoformat(data["timestamp"]) if data.get("timestamp") else datetime.now(timezone.utc),
            event_type=data["event_type"],
            capability=Capability(data["capability"]),
            subject=data["subject"],
            resource=data["resource"],
            result=data["result"],
            details=data.get("details", {}),
            previous_hash=data.get("previous_hash", ""),
            hash=data.get("hash", ""),
        )


# Risk level configurations
DEFAULT_RISK_LEVEL_CONFIG = {
    Capability.TASK_EXECUTE: RiskLevel.R1,
    Capability.TASK_CANCEL: RiskLevel.R1,
    Capability.TASK_DELEGATE: RiskLevel.R2,

    Capability.FILESYSTEM_READ: RiskLevel.R0,
    Capability.FILESYSTEM_WRITE: RiskLevel.R1,
    Capability.FILESYSTEM_DELETE: RiskLevel.R2,
    Capability.FILESYSTEM_LIST: RiskLevel.R0,

    Capability.SHELL_EXEC: RiskLevel.R2,
    Capability.SHELL_INTERACTIVE: RiskLevel.R3,

    Capability.NETWORK_HTTP: RiskLevel.R1,
    Capability.NETWORK_WEBSOCKET: RiskLevel.R1,
    Capability.NETWORK_RAW: RiskLevel.R3,
    Capability.NETWORK_EGRESS: RiskLevel.R2,

    Capability.BROWSER_NAVIGATE: RiskLevel.R1,
    Capability.BROWSER_CLICK: RiskLevel.R1,
    Capability.BROWSER_EXTRACT: RiskLevel.R1,
    Capability.BROWSER_SCREENSHOT: RiskLevel.R0,
    Capability.BROWSER_SCRIPT: RiskLevel.R3,

    Capability.UIA_FIND: RiskLevel.R0,
    Capability.UIA_CLICK: RiskLevel.R1,
    Capability.UIA_INPUT: RiskLevel.R2,
    Capability.UIA_SCROLL: RiskLevel.R0,

    Capability.MEMORY_STORE: RiskLevel.R1,
    Capability.MEMORY_QUERY: RiskLevel.R0,
    Capability.MEMORY_DELETE: RiskLevel.R2,
    Capability.MEMORY_CONSOLIDATE: RiskLevel.R1,

    Capability.VOICE_LISTEN: RiskLevel.R1,
    Capability.VOICE_SPEAK: RiskLevel.R1,
    Capability.VOICE_WAKE_WORD: RiskLevel.R0,
    Capability.VOICE_BARGE_IN: RiskLevel.R1,

    Capability.AGENT_DELEGATE: RiskLevel.R2,
    Capability.AGENT_VERIFY: RiskLevel.R1,
    Capability.AGENT_SPAWN: RiskLevel.R3,

    Capability.CONFIG_READ: RiskLevel.R0,
    Capability.CONFIG_WRITE: RiskLevel.R3,

    Capability.SECRETS_READ: RiskLevel.R2,
    Capability.SECRETS_WRITE: RiskLevel.R4,

    Capability.SYSTEM_SHUTDOWN: RiskLevel.R4,
    Capability.SYSTEM_REBOOT: RiskLevel.R4,
    Capability.SYSTEM_UPDATE: RiskLevel.R4,

    Capability.CREDENTIALS_READ: RiskLevel.R3,
    Capability.CREDENTIALS_WRITE: RiskLevel.R4,

    Capability.SECURITY_AUDIT: RiskLevel.R0,
    Capability.SECURITY_POLICY_WRITE: RiskLevel.R4,

    Capability.MODEL_ACCESS: RiskLevel.R1,
    Capability.MODEL_TRAIN: RiskLevel.R3,
}


# Resource sensitivity levels
class ResourceSensitivity(str, Enum):
    """Resource sensitivity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# Capability to risk mapping based on resource sensitivity
RISK_ADJUSTMENT = {
    ResourceSensitivity.LOW: {RiskLevel.R0: RiskLevel.R0, RiskLevel.R1: RiskLevel.R0, RiskLevel.R2: RiskLevel.R1, RiskLevel.R3: RiskLevel.R2, RiskLevel.R4: RiskLevel.R3},
    ResourceSensitivity.MEDIUM: {RiskLevel.R0: RiskLevel.R0, RiskLevel.R1: RiskLevel.R1, RiskLevel.R2: RiskLevel.R2, RiskLevel.R3: RiskLevel.R3, RiskLevel.R4: RiskLevel.R4},
    ResourceSensitivity.HIGH: {RiskLevel.R0: RiskLevel.R1, RiskLevel.R1: RiskLevel.R2, RiskLevel.R2: RiskLevel.R3, RiskLevel.R3: RiskLevel.R4, RiskLevel.R4: RiskLevel.R4},
    ResourceSensitivity.CRITICAL: {RiskLevel.R0: RiskLevel.R2, RiskLevel.R1: RiskLevel.R3, RiskLevel.R2: RiskLevel.R4, RiskLevel.R3: RiskLevel.R4, RiskLevel.R4: RiskLevel.R4},
}


def get_base_risk_level(capability: Capability) -> RiskLevel:
    """Get the base risk level for a capability."""
    return DEFAULT_RISK_LEVEL_CONFIG.get(capability, RiskLevel.R1)


def adjust_risk_for_sensitivity(base_risk: RiskLevel, sensitivity: ResourceSensitivity) -> RiskLevel:
    """Adjust risk level based on resource sensitivity."""
    return RISK_ADJUSTMENT.get(sensitivity, {}).get(base_risk, base_risk)