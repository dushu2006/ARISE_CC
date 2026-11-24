"""
Policy Engine Core.

Implements capability-based security with:
- Risk evaluation (R0-R4)
- Approval workflow with WebSocket UI
- Capability grants with TTL and scoping
- Tamper-evident audit logging
"""

from __future__ import annotations
import asyncio
import hashlib
import json
import os
import uuid
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable, Awaitable

from core.policy_engine.models import (
    RiskLevel,
    Capability,
    CapabilityGrant,
    ApprovalRequest,
    ApprovalDecision,
    PolicyAuditEntry,
    PolicyEvaluationResult,
    Decision,
    ApprovalStatus,
    ResourceSensitivity,
    DEFAULT_RISK_LEVEL_CONFIG,
    get_base_risk_level,
    adjust_risk_for_sensitivity,
)
from core.config import load_config
from core.events import get_event_bus
from core.events.models import Event, EventPriority
from core.structured_logging import get_logger, log_structured
import logging

logger = get_logger(__name__)


class PolicyEngineConfig:
    """Policy engine configuration."""

    def __init__(
        self,
        risk_levels: Optional[Dict[RiskLevel, Dict[str, Any]]] = None,
        capabilities: Optional[List[str]] = None,
        default_risk_level: RiskLevel = RiskLevel.R1,
        approval_ui_enabled: bool = True,
        audit_enabled: bool = True,
        audit_persistence_path: str = "./data/policy_audit",
    ):
        self.risk_levels = risk_levels or {}
        self.capabilities = capabilities or [c.value for c in Capability]
        self.default_risk_level = default_risk_level
        self.approval_ui_enabled = approval_ui_enabled
        self.audit_enabled = audit_enabled
        self.audit_persistence_path = audit_persistence_path


class PolicyEngine:
    """
    Main policy engine for capability-based security.

    Features:
    - Risk evaluation with R0-R4 levels
    - Approval workflow with timeout and MFA support
    - Capability grants with scoping and TTL
    - Tamper-evident audit logging
    - WebSocket-based approval UI integration
    """

    def __init__(self, config: PolicyEngineConfig):
        self.config = config
        self._grants: Dict[str, CapabilityGrant] = {}
        self._approvals: Dict[str, ApprovalRequest] = {}
        self._audit_log: List[PolicyAuditEntry] = []
        self._audit_file: Optional[Path] = None
        self._approval_callbacks: List[Callable[[ApprovalRequest], Awaitable[None]]] = []
        self._running = False
        self._cleanup_task: Optional[asyncio.Task] = None
        self._previous_audit_hash = ""

    async def initialize(self) -> None:
        """Initialize the policy engine."""
        log_structured(logger, logging.INFO, "Initializing Policy Engine")

        # Setup audit persistence
        if self.config.audit_enabled:
            self._audit_file = Path(self.config.audit_persistence_path) / "audit.log"
            self._audit_file.parent.mkdir(parents=True, exist_ok=True)
            await self._load_audit_log()

        # Start cleanup task
        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

        log_structured(logger, logging.INFO, "Policy Engine initialized")

    async def shutdown(self) -> None:
        """Shutdown the policy engine."""
        log_structured(logger, logging.INFO, "Shutting down Policy Engine")
        self._running = False

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        # Save audit log
        if self.config.audit_enabled:
            await self._save_audit_log()

        log_structured(logger, logging.INFO, "Policy Engine stopped")

    def register_approval_callback(self, callback: Callable[[ApprovalRequest], Awaitable[None]]) -> None:
        """Register a callback for approval requests (e.g., WebSocket UI)."""
        self._approval_callbacks.append(callback)

    # =========================================================================
    # Risk Evaluation
    # =========================================================================

    async def evaluate(
        self,
        capability: Capability,
        context: Optional[Dict[str, Any]] = None,
        resource_sensitivity: ResourceSensitivity = ResourceSensitivity.MEDIUM,
        subject: str = "system",
        resource: str = "",
    ) -> PolicyEvaluationResult:
        """
        Evaluate a capability request against policy.

        Args:
            capability: The capability being requested
            context: Additional context for evaluation
            resource_sensitivity: Sensitivity of the target resource
            subject: Who is requesting (user, agent, etc.)
            resource: The specific resource being accessed

        Returns:
            PolicyEvaluationResult with decision and reasoning
        """
        context = context or {}

        # Check existing grants first
        matching_grants = self._find_matching_grants(capability, resource, subject)
        if matching_grants:
            grant = matching_grants[0]
            result = PolicyEvaluationResult(
                capability=capability,
                risk_level=RiskLevel.R0,  # Granted = lowest risk
                decision=Decision.ALLOW,
                reasoning=f"Granted by existing grant {grant.grant_id}",
                grants_matched=[g.grant_id for g in matching_grants],
            )
            await self._audit(
                event_type="evaluation",
                capability=capability,
                subject=subject,
                resource=resource,
                result="allow",
                details={"grants_matched": [g.grant_id for g in matching_grants], "context": context},
            )
            return result

        # Get base risk level
        base_risk = get_base_risk_level(capability)

        # Adjust for resource sensitivity
        risk_level = adjust_risk_for_sensitivity(base_risk, resource_sensitivity)

        # Determine decision based on risk level
        decision, required_approvals, reasoning = self._make_decision(risk_level, capability, context)

        result = PolicyEvaluationResult(
            capability=capability,
            risk_level=risk_level,
            decision=decision,
            required_approvals=required_approvals,
            reasoning=reasoning,
        )

        # Audit the evaluation
        await self._audit(
            event_type="evaluation",
            capability=capability,
            subject=subject,
            resource=resource,
            result=decision.value,
            details={"risk_level": risk_level.value, "reasoning": reasoning, "context": context},
        )

        # If approval required, create approval request
        if decision == Decision.REQUIRE_APPROVAL:
            approval = await self._create_approval_request(
                capability=capability,
                context=context,
                subject=subject,
                resource=resource,
                risk_level=risk_level,
            )
            result.required_approvals = [approval.approval_id]
            result.expires_at = approval.expires_at

        return result

    def _find_matching_grants(
        self,
        capability: Capability,
        resource: str,
        subject: str,
    ) -> List[CapabilityGrant]:
        """Find grants that match the capability, resource, and subject."""
        matches = []
        for grant in self._grants.values():
            if grant.revoked:
                continue
            if grant.capability != capability:
                continue
            if grant.granted_to and grant.granted_to != subject:
                continue
            if grant.is_valid(resource):
                matches.append(grant)
        return matches

    def _make_decision(
        self,
        risk_level: RiskLevel,
        capability: Capability,
        context: Dict[str, Any],
    ) -> tuple[Decision, List[str], str]:
        """Make a decision based on risk level."""
        risk_config = self.config.risk_levels.get(risk_level, {})
        # risk_config is a dict (from model_dump()), not an object
        auto_approve = risk_config.get("auto_approve", False)
        requires_mfa = risk_config.get("requires_mfa", False)
        timeout_seconds = risk_config.get("timeout_seconds", 300)

        if auto_approve:
            return Decision.ALLOW, [], f"Auto-approved (risk level {risk_level.value})"

        if risk_level == RiskLevel.R4:
            return Decision.DENY, [], f"Denied by default (critical risk level {risk_level.value})"

        # Require approval
        approval_type = "MFA" if requires_mfa else "standard"
        return Decision.REQUIRE_APPROVAL, [approval_type], f"Requires {approval_type} approval (risk level {risk_level.value})"

    async def _create_approval_request(
        self,
        capability: Capability,
        context: Dict[str, Any],
        subject: str,
        resource: str,
        risk_level: RiskLevel,
    ) -> ApprovalRequest:
        """Create an approval request."""
        risk_config = self.config.risk_levels.get(risk_level, {})
        ttl_seconds = risk_config.get("timeout_seconds", 300)

        approval = ApprovalRequest(
            approval_id="",
            task_id=context.get("task_id", str(uuid.uuid4())[:8]),
            capability=capability,
            context=context,
            requested_by=subject,
            ttl_seconds=ttl_seconds,
        )

        self._approvals[approval.approval_id] = approval

        # Audit
        await self._audit(
            event_type="approval_requested",
            capability=capability,
            subject=subject,
            resource=resource,
            result="pending",
            details={"approval_id": approval.approval_id, "ttl_seconds": ttl_seconds, "risk_level": risk_level.value},
        )

        # Notify callbacks (WebSocket UI, etc.)
        for callback in self._approval_callbacks:
            try:
                await callback(approval)
            except Exception as e:
                log_structured(logger, logging.ERROR, "Approval callback failed", error=str(e))

        return approval

    # =========================================================================
    # Approval Management
    # =========================================================================

    async def decide_approval(
        self,
        approval_id: str,
        decision: Decision,
        decided_by: str,
        ttl_seconds: Optional[int] = None,
    ) -> ApprovalDecision:
        """Record a decision on an approval request."""
        approval = self._approvals.get(approval_id)
        if not approval:
            raise ValueError(f"Approval not found: {approval_id}")

        if approval.status != ApprovalStatus.PENDING:
            raise ValueError(f"Approval already decided: {approval.status.value}")

        if approval.is_expired():
            approval.status = ApprovalStatus.EXPIRED
            raise ValueError("Approval has expired")

        # Update approval
        approval.status = ApprovalStatus.GRANTED if decision == Decision.ALLOW else ApprovalStatus.DENIED
        approval.decided_at = datetime.now(timezone.utc)
        approval.decided_by = decided_by
        approval.decision = decision

        # If granted with TTL, create a temporary grant
        if decision == Decision.ALLOW and ttl_seconds:
            grant = CapabilityGrant(
                grant_id="",
                capability=approval.capability,
                scope=approval.context.get("scope", {}),
                conditions={"approval_id": approval_id},
                ttl_seconds=ttl_seconds,
                granted_to=approval.requested_by,
            )
            self._grants[grant.grant_id] = grant

            await self._audit(
                event_type="grant_created",
                capability=approval.capability,
                subject=decided_by,
                resource=approval.context.get("resource", ""),
                result="created",
                details={"grant_id": grant.grant_id, "approval_id": approval_id, "ttl_seconds": ttl_seconds},
            )

        # Audit decision
        await self._audit(
            event_type="approval_decided",
            capability=approval.capability,
            subject=decided_by,
            resource=approval.context.get("resource", ""),
            result=decision.value,
            details={"approval_id": approval_id, "original_requester": approval.requested_by},
        )

        return ApprovalDecision(
            approval_id=approval_id,
            status=approval.status,
            decided_at=approval.decided_at,
            decided_by=decided_by,
            decision=decision,
            ttl_seconds=ttl_seconds,
        )

    def get_approval(self, approval_id: str) -> Optional[ApprovalRequest]:
        """Get an approval request by ID."""
        return self._approvals.get(approval_id)

    def list_pending_approvals(self) -> List[ApprovalRequest]:
        """List all pending approval requests."""
        return [a for a in self._approvals.values() if a.status == ApprovalStatus.PENDING and not a.is_expired()]

    # =========================================================================
    # Grant Management
    # =========================================================================

    async def create_grant(
        self,
        capability: Capability,
        scope: Dict[str, Any],
        granted_to: str,
        conditions: Optional[Dict[str, Any]] = None,
        ttl_seconds: Optional[int] = None,
    ) -> CapabilityGrant:
        """Create a new capability grant."""
        grant = CapabilityGrant(
            grant_id="",
            capability=capability,
            scope=scope,
            conditions=conditions or {},
            ttl_seconds=ttl_seconds,
            granted_to=granted_to,
        )

        self._grants[grant.grant_id] = grant

        await self._audit(
            event_type="grant_created",
            capability=capability,
            subject=granted_to,
            resource=scope.get("resource", ""),
            result="created",
            details={"grant_id": grant.grant_id, "ttl_seconds": ttl_seconds, "scope": scope},
        )

        return grant

    async def revoke_grant(self, grant_id: str, revoked_by: str) -> bool:
        """Revoke a capability grant."""
        grant = self._grants.get(grant_id)
        if not grant:
            return False

        grant.revoked = True
        grant.revoked_at = datetime.now(timezone.utc)
        grant.revoked_by = revoked_by

        await self._audit(
            event_type="grant_revoked",
            capability=grant.capability,
            subject=revoked_by,
            resource=grant.scope.get("resource", ""),
            result="revoked",
            details={"grant_id": grant_id, "granted_to": grant.granted_to},
        )

        return True

    def get_grant(self, grant_id: str) -> Optional[CapabilityGrant]:
        """Get a grant by ID."""
        return self._grants.get(grant_id)

    def list_grants(
        self,
        capability: Optional[Capability] = None,
        granted_to: Optional[str] = None,
        include_revoked: bool = False,
    ) -> List[CapabilityGrant]:
        """List grants with optional filters."""
        grants = list(self._grants.values())

        if capability:
            grants = [g for g in grants if g.capability == capability]
        if granted_to:
            grants = [g for g in grants if g.granted_to == granted_to]
        if not include_revoked:
            grants = [g for g in grants if not g.revoked]

        return grants

    # =========================================================================
    # Audit Logging
    # =========================================================================

    async def _audit(
        self,
        event_type: str,
        capability: Capability,
        subject: str,
        resource: str,
        result: str,
        details: Dict[str, Any],
    ) -> None:
        """Create an audit log entry."""
        if not self.config.audit_enabled:
            return

        entry = PolicyAuditEntry(
            id="",
            timestamp=datetime.now(timezone.utc),
            event_type=event_type,
            capability=capability,
            subject=subject,
            resource=resource,
            result=result,
            details=details,
            previous_hash=self._previous_audit_hash,
        )

        self._audit_log.append(entry)
        self._previous_audit_hash = entry.hash

        # Publish event
        try:
            bus = await get_event_bus()
            if bus:
                event = Event(
                    type=f"policy.{event_type}",
                    payload={
                        "audit_id": entry.id,
                        "event_type": event_type,
                        "capability": capability.value,
                        "subject": subject,
                        "resource": resource,
                        "result": result,
                        "details": details,
                    },
                    priority=EventPriority.NORMAL,
                )
                await bus.publish(event)
        except Exception as e:
            log_structured(logger, logging.DEBUG, "Failed to publish audit event", error=str(e))

    async def query_audit(
        self,
        event_type: Optional[str] = None,
        capability: Optional[Capability] = None,
        subject: Optional[str] = None,
        resource: Optional[str] = None,
        result: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[PolicyAuditEntry]:
        """Query the audit log with filters."""
        results = self._audit_log

        if event_type:
            results = [e for e in results if e.event_type == event_type]
        if capability:
            results = [e for e in results if e.capability == capability]
        if subject:
            results = [e for e in results if e.subject == subject]
        if resource:
            results = [e for e in results if resource in e.resource]
        if result:
            results = [e for e in results if e.result == result]
        if start_date:
            results = [e for e in results if e.timestamp >= start_date]
        if end_date:
            results = [e for e in results if e.timestamp <= end_date]

        # Return newest first
        return list(reversed(results))[:limit]

    def verify_audit_integrity(self) -> tuple[bool, List[str]]:
        """Verify the integrity of the audit log chain."""
        errors = []
        previous_hash = ""

        for i, entry in enumerate(self._audit_log):
            if entry.previous_hash != previous_hash:
                errors.append(f"Entry {i} ({entry.id}): hash chain broken")
            if not entry.verify(previous_hash):
                errors.append(f"Entry {i} ({entry.id}): hash verification failed")
            previous_hash = entry.hash

        return len(errors) == 0, errors

    async def _save_audit_log(self) -> None:
        """Save audit log to disk."""
        if not self._audit_file:
            return

        try:
            temp_path = self._audit_file.with_suffix(".tmp")
            with open(temp_path, "w") as f:
                for entry in self._audit_log:
                    f.write(json.dumps(entry.to_dict()) + "\n")
            os.replace(temp_path, self._audit_file)
        except Exception as e:
            log_structured(logger, logging.ERROR, "Failed to save audit log", error=str(e))

    async def _load_audit_log(self) -> None:
        """Load audit log from disk."""
        if not self._audit_file or not self._audit_file.exists():
            return

        try:
            with open(self._audit_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    entry = PolicyAuditEntry.from_dict(json.loads(line))
                    self._audit_log.append(entry)
                    self._previous_audit_hash = entry.hash
        except Exception as e:
            log_structured(logger, logging.ERROR, "Failed to load audit log", error=str(e))

    async def _cleanup_loop(self) -> None:
        """Periodic cleanup of expired approvals and grants."""
        while self._running:
            try:
                await asyncio.sleep(60)  # Run every minute

                # Clean up expired approvals
                expired_approvals = [
                    aid for aid, a in self._approvals.items()
                    if a.status == ApprovalStatus.PENDING and a.is_expired()
                ]
                for aid in expired_approvals:
                    self._approvals[aid].status = ApprovalStatus.EXPIRED
                    log_structured(logger, logging.INFO, "Approval expired", approval_id=aid)

                # Clean up expired grants
                expired_grants = [
                    gid for gid, g in self._grants.items()
                    if not g.revoked and g.expires_at and datetime.now(timezone.utc) > g.expires_at
                ]
                for gid in expired_grants:
                    self._grants[gid].revoked = True
                    self._grants[gid].revoked_at = datetime.now(timezone.utc)
                    self._grants[gid].revoked_by = "system"
                    log_structured(logger, logging.INFO, "Grant expired", grant_id=gid)

            except asyncio.CancelledError:
                break
            except Exception as e:
                log_structured(logger, logging.ERROR, "Cleanup loop error", error=str(e))


# Global policy engine instance
_policy_engine: Optional[PolicyEngine] = None


async def get_policy_engine() -> Optional[PolicyEngine]:
    """Get the global policy engine instance."""
    return _policy_engine


async def init_policy_engine(config=None) -> PolicyEngine:
    """Initialize the global policy engine."""
    global _policy_engine

    if config is None:
        app_config = load_config()
        policy_config = app_config.policy_engine

        config = PolicyEngineConfig(
            risk_levels={RiskLevel(k): v.model_dump() for k, v in policy_config.risk_levels.items()},
            capabilities=policy_config.capabilities,
            default_risk_level=policy_config.default_risk_level,
            approval_ui_enabled=policy_config.approval_ui_enabled,
            audit_enabled=policy_config.audit_enabled,
        )
    else:
        # Config passed from main.py (AppConfig.policy_engine)
        # Convert from config model to engine config
        if hasattr(config, 'risk_levels') and hasattr(config, 'capabilities'):
            config = PolicyEngineConfig(
                risk_levels={RiskLevel(k): v.model_dump() for k, v in config.risk_levels.items()},
                capabilities=config.capabilities,
                default_risk_level=config.default_risk_level,
                approval_ui_enabled=config.approval_ui_enabled,
                audit_enabled=config.audit_enabled,
            )

    _policy_engine = PolicyEngine(config)
    await _policy_engine.initialize()
    return _policy_engine


async def shutdown_policy_engine() -> None:
    """Shutdown the global policy engine."""
    global _policy_engine
    if _policy_engine:
        await _policy_engine.shutdown()
        _policy_engine = None