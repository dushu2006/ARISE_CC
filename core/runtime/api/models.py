# core/runtime/api/models.py
"""
Model Router API Endpoints.

Provides REST API for model management per OpenAPI spec.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

router = APIRouter(prefix="/models", tags=["models"])


# ============================================================
# Request/Response Models
# ============================================================

class CompletionRequest(BaseModel):
    """Model completion request."""
    prompt: str = Field(..., description="Prompt text")
    provider: Optional[str] = Field(default=None, description="Specific provider (optional)")
    model: Optional[str] = Field(default=None, description="Specific model (optional)")
    task_type: Optional[str] = Field(default="general", description="Task type for routing")
    max_tokens: Optional[int] = Field(default=None, ge=1, le=100000, description="Max tokens")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="Temperature")
    top_p: float = Field(default=1.0, ge=0.0, le=1.0, description="Top-p sampling")
    stream: bool = Field(default=False, description="Stream response")
    privacy_mode: str = Field(default="off", description="Privacy mode: off, redact, local_only")


class CompletionResponse(BaseModel):
    """Model completion response."""
    text: str
    provider: str
    model: str
    usage: Dict[str, int]
    cost: float
    latency_ms: float
    finish_reason: str


class StreamChunk(BaseModel):
    """Streaming chunk."""
    delta: str
    finish_reason: Optional[str] = None


class ProviderInfo(BaseModel):
    """Provider information."""
    name: str
    models: List[str]
    healthy: bool
    latency_ms: Optional[float] = None
    error: Optional[str] = None


class ProvidersResponse(BaseModel):
    """Providers list response."""
    providers: List[ProviderInfo]


class UsageStatsResponse(BaseModel):
    """Usage statistics response."""
    total_requests: int
    total_tokens: int
    total_cost: float
    by_provider: Dict[str, Dict[str, Any]]
    by_model: Dict[str, Dict[str, Any]]
    by_task_type: Dict[str, Dict[str, Any]]


# ============================================================
# Endpoints
# ============================================================

@router.post(
    "/complete",
    response_model=CompletionResponse,
    summary="Non-streaming completion",
    description="Get a completion from the model router.",
)
async def complete(request: CompletionRequest) -> CompletionResponse:
    """Non-streaming model completion."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Model router not yet implemented",
    )


@router.post(
    "/stream",
    summary="Streaming completion (SSE)",
    description="Get a streaming completion via Server-Sent Events.",
)
async def stream_complete(request: CompletionRequest):
    """Streaming model completion."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Model router not yet implemented",
    )


@router.get(
    "/providers",
    response_model=ProvidersResponse,
    summary="List providers",
    description="List all configured model providers with health status.",
)
async def list_providers() -> ProvidersResponse:
    """List model providers."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Model router not yet implemented",
    )


@router.get(
    "/usage",
    response_model=UsageStatsResponse,
    summary="Get usage stats",
    description="Get model usage statistics and costs.",
)
async def get_usage_stats(
    start_date: Optional[str] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[str] = Query(None, description="End date (ISO format)"),
) -> UsageStatsResponse:
    """Get usage statistics."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Model router not yet implemented",
    )