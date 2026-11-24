"""
Policy Engine Package.

Provides capability-based security with risk evaluation, approvals, grants, and audit logging.
"""

from __future__ import annotations

from core.policy_engine.models import (
    RiskLevel,
    Capability,
    CapabilityGrant,
    ApprovalRequest,
    ApprovalDecision,
    PolicyAuditEntry,
    PolicyEvaluationResult,
)

from core.policy_engine.engine import PolicyEngine, get_policy_engine, init_policy_engine, shutdown_policy_engine

__all__ = [
    "RiskLevel",
    "Capability",
    "CapabilityGrant",
    "ApprovalRequest",
    "ApprovalDecision",
    "PolicyAuditEntry",
    "PolicyEvaluationResult",
    "PolicyEngine",
    "get_policy_engine",
    "init_policy_engine",
    "shutdown_policy_engine",
]