"""
Security Audit Logger.

Extends policy audit with security-specific events:
- Credential access logging
- Network block events
- Prompt injection detection events
- Tamper detection (hash chains)
"""

from __future__ import annotations
import asyncio
import hashlib
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from core.config import load_config
from core.config.models import SecurityConfig, SecurityAuditConfig
from core.database import get_session
from core.database.models import SecurityAuditLog, SecuritySeverity, SecurityEvent
from core.structured_logging import get_logger, log_structured

logger = get_logger(__name__)


class SecurityEventCategory(str, Enum):
    """Security event categories."""
    PROMPT_INJECTION = "prompt_injection"
    CREDENTIAL_ACCESS = "credential_access"
    NETWORK_BLOCK = "network_block"
    NETWORK_ALLOW = "network_allow"
    UNAUTHORIZED_ACCESS = "unauthorized_access"
    POLICY_VIOLATION = "policy_violation"
    CONFIG_CHANGE = "config_change"
    SYSTEM_EVENT = "system_event"


@dataclass
class SecurityAuditEntry:
    """Security audit log entry with tamper-evident hash chain."""
    id: str = field(default_factory=lambda: f"sec_{uuid.uuid4().hex[:16]}")
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    category: SecurityEventCategory = SecurityEventCategory.SYSTEM_EVENT
    severity: SecuritySeverity = SecuritySeverity.LOW
    user_id: Optional[str] = None
    agent_id: Optional[str] = None
    task_id: Optional[str] = None
    action: str = ""
    resource: Optional[str] = None
    capability: Optional[str] = None
    risk_level: Optional[str] = None
    success: bool = True
    error: Optional[str] = None
    source_ip: Optional[str] = None
    user_agent: Optional[str] = None
    mitre_technique: Optional[str] = None
    response_action: Optional[str] = None
    acknowledged: bool = False
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    previous_hash: str = ""
    entry_hash: str = ""

    def __post_init__(self):
        self.entry_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        """Compute tamper-evident hash including previous entry hash."""
        data = {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "category": self.category.value,
            "severity": self.severity.value,
            "user_id": self.user_id,
            "agent_id": self.agent_id,
            "task_id": self.task_id,
            "action": self.action,
            "resource": self.resource,
            "capability": self.capability,
            "risk_level": self.risk_level,
            "success": self.success,
            "error": self.error,
            "source_ip": self.source_ip,
            "user_agent": self.user_agent,
            "mitre_technique": self.mitre_technique,
            "response_action": self.response_action,
            "acknowledged": self.acknowledged,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "acknowledged_by": self.acknowledged_by,
            "context": self.context,
            "previous_hash": self.previous_hash,
        }
        # Sort keys for deterministic hashing
        serialized = json.dumps(data, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(serialized.encode()).hexdigest()

    def verify(self, previous_hash: str = "") -> bool:
        """Verify the integrity of this audit entry."""
        expected_hash = self._compute_hash()
        return self.entry_hash == expected_hash and self.previous_hash == previous_hash

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "category": self.category.value,
            "severity": self.severity.value,
            "user_id": self.user_id,
            "agent_id": self.agent_id,
            "task_id": self.task_id,
            "action": self.action,
            "resource": self.resource,
            "capability": self.capability,
            "risk_level": self.risk_level,
            "success": self.success,
            "error": self.error,
            "source_ip": self.source_ip,
            "user_agent": self.user_agent,
            "mitre_technique": self.mitre_technique,
            "response_action": self.response_action,
            "acknowledged": self.acknowledged,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "acknowledged_by": self.acknowledged_by,
            "context": self.context,
            "previous_hash": self.previous_hash,
            "hash": self.entry_hash,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SecurityAuditEntry":
        entry = cls(
            id=data.get("id", ""),
            timestamp=datetime.fromisoformat(data["timestamp"]) if data.get("timestamp") else datetime.now(timezone.utc),
            category=SecurityEventCategory(data.get("category", "system_event")),
            severity=SecuritySeverity(data.get("severity", "low")),
            user_id=data.get("user_id"),
            agent_id=data.get("agent_id"),
            task_id=data.get("task_id"),
            action=data.get("action", ""),
            resource=data.get("resource"),
            capability=data.get("capability"),
            risk_level=data.get("risk_level"),
            success=data.get("success", True),
            error=data.get("error"),
            source_ip=data.get("source_ip"),
            user_agent=data.get("user_agent"),
            mitre_technique=data.get("mitre_technique"),
            response_action=data.get("response_action"),
            acknowledged=data.get("acknowledged", False),
            acknowledged_at=datetime.fromisoformat(data["acknowledged_at"]) if data.get("acknowledged_at") else None,
            acknowledged_by=data.get("acknowledged_by"),
            context=data.get("context", {}),
            previous_hash=data.get("previous_hash", ""),
            entry_hash=data.get("hash", ""),
        )
        return entry


class SecurityAuditLogger:
    """
    Security audit logger with tamper-evident hash chain.

    Logs security events:
    - Credential access (read/write/delete)
    - Network egress blocks/allows
    - Prompt injection detections
    - Policy violations
    - Unauthorized access attempts
    """

    def __init__(self, config: Optional[SecurityAuditConfig] = None):
        self.config = config or load_config().security.audit
        self._last_hash = ""
        self._initialized = False
        self._buffer: List[SecurityAuditEntry] = []
        self._flush_task: Optional[asyncio.Task] = None
        self._buffer_size = 100
        self._flush_interval = 5  # seconds

    async def initialize(self) -> None:
        """Initialize audit logger and load last hash."""
        log_structured(logger, logging.INFO, "Initializing Security Audit Logger")

        # Load last hash from database
        await self._load_last_hash()

        # Start background flush task
        self._flush_task = asyncio.create_task(self._flush_loop())

        self._initialized = True
        log_structured(logger, logging.INFO, "Security Audit Logger initialized")

    async def _load_last_hash(self) -> None:
        """Load the last hash from the database."""
        try:
            async with get_session() as session:
                from sqlalchemy import select, desc
                result = await session.execute(
                    select(SecurityAuditLog).order_by(desc(SecurityAuditLog.created_at)).limit(1)
                )
                last_log = result.scalar_one_or_none()
                if last_log and last_log.context_json.get("entry_hash"):
                    self._last_hash = last_log.context_json["entry_hash"]
                    log_structured(logger, logging.DEBUG, "Loaded last audit hash", hash=self._last_hash[:16])
        except Exception as e:
            log_structured(logger, logging.WARNING, "Failed to load last audit hash", error=str(e))

    async def _flush_loop(self) -> None:
        """Background task to flush buffer to database."""
        while self._initialized:
            try:
                await asyncio.sleep(self._flush_interval)
                if self._buffer:
                    await self._flush_buffer()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log_structured(logger, logging.ERROR, "Audit flush loop error", error=str(e))

    async def _flush_buffer(self) -> None:
        """Flush buffered entries to database."""
        if not self._buffer:
            return

        entries = self._buffer.copy()
        self._buffer.clear()

        try:
            async with get_session() as session:
                for entry in entries:
                    audit_log = SecurityAuditLog(
                        id=entry.id,
                        event_type=entry.category.value,
                        severity=entry.severity,
                        user_id=entry.user_id,
                        agent_id=entry.agent_id,
                        task_id=entry.task_id,
                        action=entry.action,
                        resource=entry.resource,
                        capability=entry.capability,
                        risk_level=entry.risk_level,
                        success=entry.success,
                        error=entry.error,
                        source_ip=entry.source_ip,
                        user_agent=entry.user_agent,
                        mitre_technique=entry.mitre_technique,
                        response_action=entry.response_action,
                        acknowledged=entry.acknowledged,
                        acknowledged_at=entry.acknowledged_at,
                        acknowledged_by=entry.acknowledged_by,
                        context_json={
                            **entry.context,
                            "previous_hash": entry.previous_hash,
                            "entry_hash": entry.entry_hash,
                        },
                        created_at=entry.timestamp,
                    )
                    session.add(audit_log)

                await session.commit()
                log_structured(logger, logging.DEBUG, "Flushed audit entries", count=len(entries))

        except Exception as e:
            log_structured(logger, logging.ERROR, "Failed to flush audit buffer", error=str(e))
            # Re-add to buffer for retry
            self._buffer = entries + self._buffer

    def _create_entry(
        self,
        category: SecurityEventCategory,
        action: str,
        severity: SecuritySeverity = SecuritySeverity.LOW,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        task_id: Optional[str] = None,
        resource: Optional[str] = None,
        capability: Optional[str] = None,
        risk_level: Optional[str] = None,
        success: bool = True,
        error: Optional[str] = None,
        source_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
        mitre_technique: Optional[str] = None,
        response_action: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> SecurityAuditEntry:
        """Create a new audit entry with hash chain."""
        entry = SecurityAuditEntry(
            category=category,
            severity=severity,
            user_id=user_id or "local_user",
            agent_id=agent_id,
            task_id=task_id,
            action=action,
            resource=resource,
            capability=capability,
            risk_level=risk_level,
            success=success,
            error=error,
            source_ip=source_ip,
            user_agent=user_agent,
            mitre_technique=mitre_technique,
            response_action=response_action,
            context=context or {},
            previous_hash=self._last_hash,
        )

        # Update last hash for next entry
        self._last_hash = entry.entry_hash

        return entry

    def log(
        self,
        category: SecurityEventCategory,
        action: str,
        severity: SecuritySeverity = SecuritySeverity.LOW,
        **kwargs
    ) -> SecurityAuditEntry:
        """
        Log a security event.

        Args:
            category: Event category
            action: Action description
            severity: Event severity
            **kwargs: Additional fields

        Returns:
            Created audit entry
        """
        if not self._initialized:
            # Lazy init for synchronous logging
            pass

        entry = self._create_entry(category, action, severity, **kwargs)

        # Buffer for async flush
        self._buffer.append(entry)

        # Also log structured
        log_structured(logger, logging.INFO if success else logging.WARNING, "Security audit event",
            category=category.value,
            action=action,
            severity=severity.value,
            **{k: v for k, v in kwargs.items() if v is not None}
        )

        return entry

    async def log_async(
        self,
        category: SecurityEventCategory,
        action: str,
        severity: SecuritySeverity = SecuritySeverity.LOW,
        **kwargs
    ) -> SecurityAuditEntry:
        """Async log a security event (alias for log)."""
        return self.log(category, action, severity, **kwargs)

    # Convenience methods for common events

    def log_credential_access(
        self,
        action: str,  # read, write, delete
        category: str,
        key: str,
        success: bool = True,
        user_id: Optional[str] = None,
        error: Optional[str] = None,
    ) -> SecurityAuditEntry:
        """Log credential access event."""
        return self.log(
            category=SecurityEventCategory.CREDENTIAL_ACCESS,
            action=f"credential_{action}",
            severity=SecuritySeverity.HIGH if not success else SecuritySeverity.MEDIUM,
            user_id=user_id,
            resource=f"{category}/{key}",
            success=success,
            error=error,
            context={"credential_category": category, "credential_key": key},
        )

    def log_network_event(
        self,
        action: str,  # allow, deny, log
        destination: str,
        port: int,
        protocol: str = "tcp",
        capability: Optional[str] = None,
        task_id: Optional[str] = None,
        success: bool = True,
        rule_name: Optional[str] = None,
    ) -> SecurityAuditEntry:
        """Log network egress event."""
        category = SecurityEventCategory.NETWORK_BLOCK if action == "deny" else SecurityEventCategory.NETWORK_ALLOW
        severity = SecuritySeverity.HIGH if action == "deny" else SecuritySeverity.LOW

        return self.log(
            category=category,
            action=f"network_{action}",
            severity=severity,
            task_id=task_id,
            capability=capability,
            resource=f"{destination}:{port}/{protocol}",
            success=success,
            context={
                "destination": destination,
                "port": port,
                "protocol": protocol,
                "rule_name": rule_name,
            },
        )

    def log_prompt_injection(
        self,
        injection_type: str,
        severity: str,
        confidence: float,
        integration_point: str,
        text_preview: str,
        action_taken: str,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> SecurityAuditEntry:
        """Log prompt injection detection."""
        sev_map = {
            "low": SecuritySeverity.LOW,
            "medium": SecuritySeverity.MEDIUM,
            "high": SecuritySeverity.HIGH,
            "critical": SecuritySeverity.CRITICAL,
        }

        return self.log(
            category=SecurityEventCategory.PROMPT_INJECTION,
            action="prompt_injection_detected",
            severity=sev_map.get(severity.lower(), SecuritySeverity.HIGH),
            user_id=user_id,
            agent_id=agent_id,
            task_id=task_id,
            success=True,
            context={
                "injection_type": injection_type,
                "confidence": confidence,
                "integration_point": integration_point,
                "text_preview": text_preview[:200],
                "action_taken": action_taken,
            },
        )

    def log_policy_violation(
        self,
        capability: str,
        resource: str,
        risk_level: str,
        decision: str,  # denied, deferred
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> SecurityAuditEntry:
        """Log policy violation."""
        return self.log(
            category=SecurityEventCategory.POLICY_VIOLATION,
            action="policy_violation",
            severity=SecuritySeverity.HIGH,
            user_id=user_id,
            agent_id=agent_id,
            task_id=task_id,
            capability=capability,
            resource=resource,
            risk_level=risk_level,
            success=False,
            context={"decision": decision},
        )

    def log_unauthorized_access(
        self,
        resource: str,
        action: str,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        task_id: Optional[str] = None,
        source_ip: Optional[str] = None,
    ) -> SecurityAuditEntry:
        """Log unauthorized access attempt."""
        return self.log(
            category=SecurityEventCategory.UNAUTHORIZED_ACCESS,
            action=f"unauthorized_{action}",
            severity=SecuritySeverity.CRITICAL,
            user_id=user_id,
            agent_id=agent_id,
            task_id=task_id,
            resource=resource,
            success=False,
            source_ip=source_ip,
        )

    def log_config_change(
        self,
        config_key: str,
        old_value: Any,
        new_value: Any,
        changed_by: str,
        is_sensitive: bool = False,
    ) -> SecurityAuditEntry:
        """Log configuration change."""
        severity = SecuritySeverity.HIGH if is_sensitive else SecuritySeverity.MEDIUM

        return self.log(
            category=SecurityEventCategory.CONFIG_CHANGE,
            action="config_changed",
            severity=severity,
            user_id=changed_by,
            resource=config_key,
            success=True,
            context={
                "old_value": str(old_value) if not is_sensitive else "[REDACTED]",
                "new_value": str(new_value) if not is_sensitive else "[REDACTED]",
                "is_sensitive": is_sensitive,
            },
        )

    async def query(
        self,
        category: Optional[SecurityEventCategory] = None,
        severity: Optional[SecuritySeverity] = None,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        task_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
        acknowledged_only: bool = False,
    ) -> List[SecurityAuditEntry]:
        """
        Query security audit logs.

        Returns:
            List of SecurityAuditEntry objects
        """
        try:
            async with get_session() as session:
                from sqlalchemy import select, and_, desc

                query = select(SecurityAuditLog)

                conditions = []
                if category:
                    conditions.append(SecurityAuditLog.event_type == category.value)
                if severity:
                    conditions.append(SecurityAuditLog.severity == severity)
                if user_id:
                    conditions.append(SecurityAuditLog.user_id == user_id)
                if agent_id:
                    conditions.append(SecurityAuditLog.agent_id == agent_id)
                if task_id:
                    conditions.append(SecurityAuditLog.task_id == task_id)
                if start_time:
                    conditions.append(SecurityAuditLog.created_at >= start_time)
                if end_time:
                    conditions.append(SecurityAuditLog.created_at <= end_time)
                if acknowledged_only:
                    conditions.append(SecurityAuditLog.acknowledged == True)

                if conditions:
                    query = query.where(and_(*conditions))

                query = query.order_by(desc(SecurityAuditLog.created_at)).limit(limit).offset(offset)

                result = await session.execute(query)
                logs = result.scalars().all()

                entries = []
                for log in logs:
                    entry = SecurityAuditEntry.from_dict({
                        "id": log.id,
                        "timestamp": log.created_at,
                        "category": log.event_type,
                        "severity": log.severity.value,
                        "user_id": log.user_id,
                        "agent_id": log.agent_id,
                        "task_id": log.task_id,
                        "action": log.action,
                        "resource": log.resource,
                        "capability": log.capability,
                        "risk_level": log.risk_level,
                        "success": log.success,
                        "error": log.error,
                        "source_ip": log.source_ip,
                        "user_agent": log.user_agent,
                        "mitre_technique": log.mitre_technique,
                        "response_action": log.response_action,
                        "acknowledged": log.acknowledged,
                        "acknowledged_at": log.acknowledged_at,
                        "acknowledged_by": log.acknowledged_by,
                        "context": log.context_json or {},
                        "previous_hash": (log.context_json or {}).get("previous_hash", ""),
                        "hash": (log.context_json or {}).get("entry_hash", ""),
                    })
                    entries.append(entry)

                return entries

        except Exception as e:
            log_structured(logger, logging.ERROR, "Audit query failed", error=str(e))
            return []

    async def acknowledge(self, entry_id: str, acknowledged_by: str) -> bool:
        """Acknowledge a security event."""
        try:
            async with get_session() as session:
                from sqlalchemy import select
                result = await session.execute(select(SecurityAuditLog).where(SecurityAuditLog.id == entry_id))
                log = result.scalar_one_or_none()
                if log:
                    log.acknowledged = True
                    log.acknowledged_at = datetime.now(timezone.utc)
                    log.acknowledged_by = acknowledged_by
                    await session.commit()
                    return True
        except Exception as e:
            log_structured(logger, logging.ERROR, "Failed to acknowledge event", error=str(e))
        return False

    async def verify_chain(self, limit: int = 1000) -> Dict[str, Any]:
        """
        Verify the hash chain integrity.

        Returns:
            Verification result with any anomalies
        """
        try:
            entries = await self.query(limit=limit)

            if not entries:
                return {"verified": True, "entries_checked": 0, "anomalies": []}

            anomalies = []
            prev_hash = ""

            for entry in reversed(entries):  # Oldest first
                if not entry.verify(prev_hash):
                    anomalies.append({
                        "entry_id": entry.id,
                        "timestamp": entry.timestamp.isoformat(),
                        "issue": "Hash chain broken",
                    })
                prev_hash = entry.entry_hash

            return {
                "verified": len(anomalies) == 0,
                "entries_checked": len(entries),
                "anomalies": anomalies,
                "last_hash": self._last_hash,
            }

        except Exception as e:
            log_structured(logger, logging.ERROR, "Chain verification failed", error=str(e))
            return {"verified": False, "error": str(e)}

    async def shutdown(self) -> None:
        """Shutdown audit logger."""
        self._initialized = False

        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass

        # Flush remaining buffer
        if self._buffer:
            await self._flush_buffer()

        log_structured(logger, logging.INFO, "Security Audit Logger shutdown")


# Global audit logger instance
_security_audit_logger: Optional[SecurityAuditLogger] = None


async def get_security_audit_logger() -> Optional[SecurityAuditLogger]:
    """Get the global security audit logger instance."""
    return _security_audit_logger


async def init_security_audit_logger(config: Optional[SecurityAuditConfig] = None) -> SecurityAuditLogger:
    """Initialize the global security audit logger."""
    global _security_audit_logger
    _security_audit_logger = SecurityAuditLogger(config)
    await _security_audit_logger.initialize()
    return _security_audit_logger


async def shutdown_security_audit_logger() -> None:
    """Shutdown the global security audit logger."""
    global _security_audit_logger
    if _security_audit_logger:
        await _security_audit_logger.shutdown()
        _security_audit_logger = None


__all__ = [
    "SecurityAuditLogger",
    "SecurityAuditEntry",
    "SecurityEventCategory",
    "get_security_audit_logger",
    "init_security_audit_logger",
    "shutdown_security_audit_logger",
]