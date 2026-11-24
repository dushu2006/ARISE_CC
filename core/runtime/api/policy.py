"""
Policy Engine API Endpoints.

Provides REST API for policy management per OpenAPI spec.
"""

from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from core.policy_engine import get_policy_engine
from core.policy_engine.models import (
    Capability,
    Decision,
    ResourceSensitivity,
)

router = APIRouter(prefix="/policy", tags=["policy"])


# ============================================================
# Request/Response Models
# ============================================================

class EvaluateRequest(BaseModel):
    """Risk evaluation request."""
    capability: str = Field(..., description="Capability to evaluate")
    context: Optional[Dict[str, Any]] = Field(default=None, description="Evaluation context")
    resource_sensitivity: Optional[str] = Field(default="medium", description="Resource sensitivity")


class EvaluateResponse(BaseModel):
    """Risk evaluation response."""
    risk_level: str
    decision: str  # allow, deny, require_approval
    required_approvals: List[str]
    reasoning: str
    expires_at: Optional[str] = None


class ApprovalRequestModel(BaseModel):
    """Approval request."""
    task_id: str
    capability: str
    context: Dict[str, Any]
    requested_by: str
    ttl_seconds: int = Field(default=300, ge=60, le=86400)


class ApprovalResponse(BaseModel):
    """Approval response."""
    approval_id: str
    status: str  # pending, granted, denied, expired
    created_at: str
    expires_at: str


class ApprovalDecisionRequest(BaseModel):
    """Approval decision request."""
    decision: str = Field(..., description="Decision: grant, deny")
    granted_by: str
    ttl_seconds: Optional[int] = Field(default=None, ge=60, le=86400)


class ApprovalDecisionResponse(BaseModel):
    """Approval decision response."""
    approval_id: str
    status: str
    decided_at: str


class GrantRequest(BaseModel):
    """Capability grant request."""
    capability: str
    scope: Dict[str, Any] = Field(..., description="Resource scope/patterns")
    conditions: Optional[Dict[str, Any]] = Field(default=None, description="Grant conditions")
    ttl_seconds: Optional[int] = Field(default=None, ge=60, le=2592000, description="TTL in seconds")
    granted_to: str


class GrantResponse(BaseModel):
    """Capability grant response."""
    grant_id: str
    capability: str
    scope: Dict[str, Any]
    conditions: Optional[Dict[str, Any]] = None
    ttl_seconds: Optional[int] = None
    granted_to: str
    created_at: str
    expires_at: Optional[str] = None


class GrantListResponse(BaseModel):
    """Grant list response."""
    grants: List[GrantResponse]
    total: int


class AuditQueryRequest(BaseModel):
    """Audit log query request."""
    event_type: Optional[str] = Field(default=None, description="Filter by event type")
    start_date: Optional[str] = Field(default=None, description="Start date (ISO format)")
    end_date: Optional[str] = Field(default=None, description="End date (ISO format)")
    capability: Optional[str] = Field(default=None, description="Filter by capability")
    result: Optional[str] = Field(default=None, description="Filter by result")
    limit: int = Field(default=100, ge=1, le=1000, description="Maximum results")


class AuditEntryResponse(BaseModel):
    """Audit entry response."""
    id: str
    timestamp: str
    event_type: str
    capability: str
    subject: str
    resource: str
    result: str
    details: Dict[str, Any]


class AuditQueryResponse(BaseModel):
    """Audit query response."""
    entries: List[AuditEntryResponse]
    total: int


# ============================================================
# Dependencies
# ============================================================

async def get_policy_engine_dep():
    """Get policy engine instance."""
    engine = await get_policy_engine()
    if not engine:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Policy engine not initialized",
        )
    return engine


# ============================================================
# Endpoints
# ============================================================

@router.post(
    "/evaluate",
    response_model=EvaluateResponse,
    summary="Evaluate risk",
    description="Evaluate the risk level for a capability request.",
)
async def evaluate_risk(request: EvaluateRequest, engine=Depends(get_policy_engine_dep)) -> EvaluateResponse:
    """Evaluate risk for a capability."""
    try:
        capability = Capability(request.capability)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid capability: {request.capability}",
        )

    try:
        sensitivity = ResourceSensitivity(request.resource_sensitivity.lower())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid resource sensitivity: {request.resource_sensitivity}",
        )

    result = await engine.evaluate(
        capability=capability,
        context=request.context,
        resource_sensitivity=sensitivity,
    )

    return EvaluateResponse(
        risk_level=result.risk_level.value,
        decision=result.decision.value,
        required_approvals=result.required_approvals,
        reasoning=result.reasoning,
        expires_at=result.expires_at.isoformat() if result.expires_at else None,
    )


@router.post(
    "/approvals",
    response_model=ApprovalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Request approval",
    description="Request approval for a capability.",
)
async def request_approval(request: ApprovalRequestModel, engine=Depends(get_policy_engine_dep)) -> ApprovalResponse:
    """Request approval."""
    try:
        capability = Capability(request.capability)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid capability: {request.capability}",
        )

    # Create approval request through evaluation
    result = await engine.evaluate(
        capability=capability,
        context=request.context,
        subject=request.requested_by,
    )

    if result.decision != Decision.REQUIRE_APPROVAL:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Capability does not require approval: {result.decision.value}",
        )

    # Get the approval that was created
    if not result.required_approvals:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Approval required but none created",
        )

    approval = engine.get_approval(result.required_approvals[0])
    if not approval:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Created approval not found",
        )

    return ApprovalResponse(
        approval_id=approval.approval_id,
        status=approval.status.value,
        created_at=approval.created_at.isoformat(),
        expires_at=approval.expires_at.isoformat() if approval.expires_at else "",
    )


@router.get(
    "/approvals/{approval_id}",
    response_model=ApprovalResponse,
    summary="Get approval status",
    description="Get the status of an approval request.",
)
async def get_approval(approval_id: str, engine=Depends(get_policy_engine_dep)) -> ApprovalResponse:
    """Get approval status."""
    approval = engine.get_approval(approval_id)
    if not approval:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Approval not found: {approval_id}",
        )

    return ApprovalResponse(
        approval_id=approval.approval_id,
        status=approval.status.value,
        created_at=approval.created_at.isoformat(),
        expires_at=approval.expires_at.isoformat() if approval.expires_at else "",
    )


@router.post(
    "/approvals/{approval_id}/decide",
    response_model=ApprovalDecisionResponse,
    summary="Decide on approval",
    description="User decision on an approval request.",
)
async def decide_approval(
    approval_id: str,
    request: ApprovalDecisionRequest,
    engine=Depends(get_policy_engine_dep),
) -> ApprovalDecisionResponse:
    """Decide on approval."""
    try:
        decision = Decision(request.decision)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid decision: {request.decision}. Must be 'allow' or 'deny'",
        )

    try:
        result = await engine.decide_approval(
            approval_id=approval_id,
            decision=decision,
            decided_by=request.granted_by,
            ttl_seconds=request.ttl_seconds,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return ApprovalDecisionResponse(
        approval_id=result.approval_id,
        status=result.status.value,
        decided_at=result.decided_at.isoformat(),
    )


@router.get(
    "/grants",
    response_model=GrantListResponse,
    summary="List capability grants",
    description="List all active capability grants.",
)
async def list_grants(
    capability: Optional[str] = Query(None, description="Filter by capability"),
    granted_to: Optional[str] = Query(None, description="Filter by grantee"),
    engine=Depends(get_policy_engine_dep),
) -> GrantListResponse:
    """List capability grants."""
    cap_filter = None
    if capability:
        try:
            cap_filter = Capability(capability)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid capability: {capability}",
            )

    grants = engine.list_grants(capability=cap_filter, granted_to=granted_to)

    return GrantListResponse(
        grants=[
            GrantResponse(
                grant_id=g.grant_id,
                capability=g.capability.value,
                scope=g.scope,
                conditions=g.conditions,
                ttl_seconds=g.ttl_seconds,
                granted_to=g.granted_to,
                created_at=g.created_at.isoformat(),
                expires_at=g.expires_at.isoformat() if g.expires_at else None,
            )
            for g in grants
        ],
        total=len(grants),
    )


@router.post(
    "/grants",
    response_model=GrantResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create capability grant",
    description="Create a new capability grant.",
)
async def create_grant(request: GrantRequest, engine=Depends(get_policy_engine_dep)) -> GrantResponse:
    """Create capability grant."""
    try:
        capability = Capability(request.capability)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid capability: {request.capability}",
        )

    grant = await engine.create_grant(
        capability=capability,
        scope=request.scope,
        granted_to=request.granted_to,
        conditions=request.conditions,
        ttl_seconds=request.ttl_seconds,
    )

    return GrantResponse(
        grant_id=grant.grant_id,
        capability=grant.capability.value,
        scope=grant.scope,
        conditions=grant.conditions,
        ttl_seconds=grant.ttl_seconds,
        granted_to=grant.granted_to,
        created_at=grant.created_at.isoformat(),
        expires_at=grant.expires_at.isoformat() if grant.expires_at else None,
    )


@router.delete(
    "/grants/{grant_id}",
    summary="Revoke capability grant",
    description="Revoke an active capability grant.",
)
async def revoke_grant(grant_id: str, revoked_by: str = Query(..., description="Who is revoking"), engine=Depends(get_policy_engine_dep)):
    """Revoke capability grant."""
    success = await engine.revoke_grant(grant_id, revoked_by)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Grant not found: {grant_id}",
        )


@router.post(
    "/audit",
    response_model=AuditQueryResponse,
    summary="Query audit log",
    description="Query the policy audit log.",
)
async def query_audit(request: AuditQueryRequest, engine=Depends(get_policy_engine_dep)) -> AuditQueryResponse:
    """Query audit log."""
    start_date = None
    if request.start_date:
        try:
            start_date = datetime.fromisoformat(request.start_date)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid start_date format, use ISO format",
            )

    end_date = None
    if request.end_date:
        try:
            end_date = datetime.fromisoformat(request.end_date)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid end_date format, use ISO format",
            )

    capability = None
    if request.capability:
        try:
            capability = Capability(request.capability)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid capability: {request.capability}",
            )

    entries = await engine.query_audit(
        event_type=request.event_type,
        capability=capability,
        subject=None,  # Not in query model
        resource=None,  # Not in query model
        result=request.result,
        start_date=start_date,
        end_date=end_date,
        limit=request.limit,
    )

    return AuditQueryResponse(
        entries=[
            AuditEntryResponse(
                id=e.id,
                timestamp=e.timestamp.isoformat(),
                event_type=e.event_type,
                capability=e.capability.value,
                subject=e.subject,
                resource=e.resource,
                result=e.result,
                details=e.details,
            )
            for e in entries
        ],
        total=len(entries),
    )


# Import datetime for query endpoint - moved to top