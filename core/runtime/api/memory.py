# core/runtime/api/memory.py
"""
Memory System API Endpoints.

Provides REST API for memory management per OpenAPI spec.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from core.memory import (
    MemoryKind,
    MemoryQuery,
    MemorySystem,
    get_memory_system,
    ConsolidationResult,
)

router = APIRouter(prefix="/memory", tags=["memory"])


# ============================================================
# Request/Response Models
# ============================================================

class MemoryStoreRequest(BaseModel):
    """Request to store a memory."""
    kind: str = Field(..., description="Memory kind (semantic, episodic, procedural, preference, working)")
    content: str = Field(..., description="Memory content")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional metadata")
    tags: Optional[List[str]] = Field(default=None, description="Tags for categorization")
    ttl_seconds: Optional[int] = Field(default=None, ge=0, description="Time to live in seconds")


class MemoryQueryRequest(BaseModel):
    """Request to query memories."""
    query: str = Field(..., description="Search query")
    kind: Optional[str] = Field(default=None, description="Filter by memory kind")
    kinds: Optional[List[str]] = Field(default=None, description="Filter by multiple memory kinds")
    limit: int = Field(default=10, ge=1, le=100, description="Maximum results")
    offset: int = Field(default=0, ge=0, description="Offset for pagination")
    filters: Optional[Dict[str, Any]] = Field(default=None, description="Metadata filters")
    min_confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Minimum confidence threshold")
    include_archived: bool = Field(default=False, description="Include archived memories")
    include_expired: bool = Field(default=False, description="Include expired memories")
    tags: Optional[List[str]] = Field(default=None, description="Filter by tags")
    similarity_threshold: float = Field(default=0.7, ge=0.0, le=1.0, description="Similarity threshold for vector search")


class MemoryResponse(BaseModel):
    """Memory response model."""
    memory_id: str
    kind: str
    content: str
    confidence: float
    metadata: Dict[str, Any]
    tags: List[str]
    ttl_seconds: Optional[int] = None
    source: str
    created_at: str
    updated_at: str
    accessed_at: Optional[str] = None
    access_count: int = 0
    version: int = 1
    is_archived: bool = False
    pii_detected: bool = False
    pii_types: List[str] = []


class MemoryQueryResponse(BaseModel):
    """Memory query response."""
    results: List[MemoryResponse]
    total: int
    query_time_ms: float
    search_type: str


class ConsolidationRequest(BaseModel):
    """Request to trigger consolidation."""
    kind: Optional[str] = Field(default=None, description="Specific kind to consolidate (working_to_episodic, episodic_to_semantic, preference_extraction, procedural_learning)")


class ConsolidationResponse(BaseModel):
    """Consolidation response."""
    kind: str
    status: str
    input_count: int = 0
    output_count: int = 0
    error: Optional[str] = None
    duration_seconds: float = 0.0


class GovernanceStatsResponse(BaseModel):
    """Governance statistics response."""
    pii_detection_enabled: bool
    pii_action: str
    encryption_enabled: bool
    lru_eviction_enabled: bool
    max_memories_per_kind: int
    kind_stats: Dict[str, Any]


class MemoryStatsResponse(BaseModel):
    """Memory system statistics response."""
    initialized: bool
    store_healthy: bool
    counts: Dict[str, int]
    total: int
    governance: Dict[str, Any]


# ============================================================
# Dependency
# ============================================================

async def get_memory_sys() -> MemorySystem:
    """Get memory system instance."""
    system = await get_memory_system()
    if not system or not system.is_initialized:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Memory system not initialized",
        )
    return system


# ============================================================
# Endpoints
# ============================================================

@router.post(
    "",
    response_model=MemoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Store a memory",
    description="Store a new memory in the specified memory store.",
)
async def store_memory(
    request: MemoryStoreRequest,
    memory_sys: MemorySystem = Depends(get_memory_sys),
) -> MemoryResponse:
    """Store a memory."""
    try:
        # Validate kind
        try:
            kind = MemoryKind(request.kind.upper())
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid memory kind: {request.kind}. Valid kinds: {[k.value for k in MemoryKind]}",
            )

        memory_id = await memory_sys.store(
            kind=kind,
            content=request.content,
            confidence=request.confidence,
            metadata=request.metadata,
            tags=request.tags,
            ttl_seconds=request.ttl_seconds,
        )

        # Get the stored memory to return full details
        memory = await memory_sys.get(memory_id)
        if not memory:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve stored memory",
            )

        return MemoryResponse(
            memory_id=memory.id,
            kind=memory.kind.value,
            content=memory.content,
            confidence=memory.confidence,
            metadata=memory.metadata,
            tags=memory.tags,
            ttl_seconds=memory.ttl_seconds,
            source=memory.source.value,
            created_at=memory.created_at.isoformat(),
            updated_at=memory.updated_at.isoformat(),
            accessed_at=memory.accessed_at.isoformat() if memory.accessed_at else None,
            access_count=memory.access_count,
            version=memory.version,
            is_archived=memory.is_archived,
            pii_detected=memory.pii_detected,
            pii_types=memory.pii_types,
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to store memory: {str(e)}",
        )


@router.get(
    "",
    response_model=MemoryQueryResponse,
    summary="Query memories",
    description="Search memories using vector similarity and/or full-text search.",
)
async def query_memories(
    query: str = Query(..., description="Search query"),
    kind: Optional[str] = Query(None, description="Filter by memory kind"),
    kinds: Optional[str] = Query(None, description="Comma-separated list of memory kinds"),
    limit: int = Query(10, ge=1, le=100, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    min_confidence: float = Query(0.0, ge=0.0, le=1.0, description="Minimum confidence threshold"),
    include_archived: bool = Query(False, description="Include archived memories"),
    include_expired: bool = Query(False, description="Include expired memories"),
    tags: Optional[str] = Query(None, description="Comma-separated list of tags"),
    similarity_threshold: float = Query(0.7, ge=0.0, le=1.0, description="Similarity threshold for vector search"),
    memory_sys: MemorySystem = Depends(get_memory_sys),
) -> MemoryQueryResponse:
    """Query memories."""
    try:
        # Parse kinds
        kind_enum = None
        if kind:
            try:
                kind_enum = MemoryKind(kind.upper())
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid memory kind: {kind}",
                )

        kinds_enum = None
        if kinds:
            kinds_list = [k.strip() for k in kinds.split(",")]
            kinds_enum = []
            for k in kinds_list:
                try:
                    kinds_enum.append(MemoryKind(k.upper()))
                except ValueError:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Invalid memory kind: {k}",
                    )

        # Parse tags
        tags_list = None
        if tags:
            tags_list = [t.strip() for t in tags.split(",")]

        memory_query = MemoryQuery(
            query=query,
            kind=kind_enum,
            kinds=kinds_enum,
            limit=limit,
            offset=offset,
            min_confidence=min_confidence,
            include_archived=include_archived,
            include_expired=include_expired,
            tags=tags_list,
            similarity_threshold=similarity_threshold,
        )

        result = await memory_sys.query(memory_query)

        return MemoryQueryResponse(
            results=[
                MemoryResponse(
                    memory_id=m.id,
                    kind=m.kind.value,
                    content=m.content,
                    confidence=m.confidence,
                    metadata=m.metadata,
                    tags=m.tags,
                    ttl_seconds=m.ttl_seconds,
                    source=m.source.value,
                    created_at=m.created_at.isoformat(),
                    updated_at=m.updated_at.isoformat(),
                    accessed_at=m.accessed_at.isoformat() if m.accessed_at else None,
                    access_count=m.access_count,
                    version=m.version,
                    is_archived=m.is_archived,
                    pii_detected=m.pii_detected,
                    pii_types=m.pii_types,
                )
                for m in result.memories
            ],
            total=result.total,
            query_time_ms=result.query_time_ms,
            search_type=result.search_type,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to query memories: {str(e)}",
        )


@router.get(
    "/{memory_id}",
    response_model=MemoryResponse,
    summary="Get memory by ID",
    description="Retrieve a specific memory by its ID.",
)
async def get_memory(
    memory_id: str,
    memory_sys: MemorySystem = Depends(get_memory_sys),
) -> MemoryResponse:
    """Get memory by ID."""
    try:
        memory = await memory_sys.get(memory_id)
        if not memory:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Memory not found: {memory_id}",
            )

        return MemoryResponse(
            memory_id=memory.id,
            kind=memory.kind.value,
            content=memory.content,
            confidence=memory.confidence,
            metadata=memory.metadata,
            tags=memory.tags,
            ttl_seconds=memory.ttl_seconds,
            source=memory.source.value,
            created_at=memory.created_at.isoformat(),
            updated_at=memory.updated_at.isoformat(),
            accessed_at=memory.accessed_at.isoformat() if memory.accessed_at else None,
            access_count=memory.access_count,
            version=memory.version,
            is_archived=memory.is_archived,
            pii_detected=memory.pii_detected,
            pii_types=memory.pii_types,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get memory: {str(e)}",
        )


@router.patch(
    "/{memory_id}",
    response_model=MemoryResponse,
    summary="Update memory",
    description="Update an existing memory.",
)
async def update_memory(
    memory_id: str,
    updates: Dict[str, Any],
    memory_sys: MemorySystem = Depends(get_memory_sys),
) -> MemoryResponse:
    """Update a memory."""
    try:
        success = await memory_sys.update(memory_id, updates)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Memory not found: {memory_id}",
            )

        memory = await memory_sys.get(memory_id)
        if not memory:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Memory not found after update: {memory_id}",
            )

        return MemoryResponse(
            memory_id=memory.id,
            kind=memory.kind.value,
            content=memory.content,
            confidence=memory.confidence,
            metadata=memory.metadata,
            tags=memory.tags,
            ttl_seconds=memory.ttl_seconds,
            source=memory.source.value,
            created_at=memory.created_at.isoformat(),
            updated_at=memory.updated_at.isoformat(),
            accessed_at=memory.accessed_at.isoformat() if memory.accessed_at else None,
            access_count=memory.access_count,
            version=memory.version,
            is_archived=memory.is_archived,
            pii_detected=memory.pii_detected,
            pii_types=memory.pii_types,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update memory: {str(e)}",
        )


@router.delete(
    "/{memory_id}",
    summary="Delete memory",
    description="Delete a memory by ID.",
)
async def delete_memory(
    memory_id: str,
    memory_sys: MemorySystem = Depends(get_memory_sys),
):
    """Delete a memory."""
    try:
        success = await memory_sys.delete(memory_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Memory not found: {memory_id}",
            )

        return {"status": "deleted", "memory_id": memory_id}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete memory: {str(e)}",
        )


@router.post(
    "/consolidate",
    response_model=List[ConsolidationResponse],
    summary="Trigger consolidation",
    description="Manually trigger memory consolidation for a specific kind or all kinds.",
)
async def trigger_consolidation(
    request: ConsolidationRequest,
    memory_sys: MemorySystem = Depends(get_memory_sys),
) -> List[ConsolidationResponse]:
    """Trigger memory consolidation."""
    try:
        results = await memory_sys.trigger_consolidation(request.kind)

        return [
            ConsolidationResponse(
                kind=r.kind,
                status=r.status,
                input_count=r.input_count,
                output_count=r.output_count,
                error=r.error,
                duration_seconds=r.duration_seconds,
            )
            for r in results
        ]

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to trigger consolidation: {str(e)}",
        )


@router.get(
    "/consolidate/status",
    summary="Get consolidation status",
    description="Get the status of the consolidation pipeline.",
)
async def get_consolidation_status(
    memory_sys: MemorySystem = Depends(get_memory_sys),
):
    """Get consolidation status."""
    try:
        return await memory_sys.get_consolidation_status()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get consolidation status: {str(e)}",
        )


@router.post(
    "/governance/ttl",
    summary="Enforce TTL",
    description="Manually trigger TTL enforcement to archive expired memories.",
)
async def enforce_ttl(
    memory_sys: MemorySystem = Depends(get_memory_sys),
):
    """Enforce TTL."""
    try:
        archived = await memory_sys.enforce_ttl()
        return {"status": "completed", "archived_count": archived}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to enforce TTL: {str(e)}",
        )


@router.post(
    "/governance/lru",
    summary="Enforce LRU eviction",
    description="Manually trigger LRU eviction when memory limits are exceeded.",
)
async def enforce_lru(
    memory_sys: MemorySystem = Depends(get_memory_sys),
):
    """Enforce LRU eviction."""
    try:
        evicted = await memory_sys.enforce_lru()
        return {"status": "completed", "evicted_count": evicted}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to enforce LRU: {str(e)}",
        )


@router.get(
    "/governance/stats",
    response_model=GovernanceStatsResponse,
    summary="Get governance statistics",
    description="Get memory governance statistics including PII detection, TTL, and LRU settings.",
)
async def get_governance_stats(
    memory_sys: MemorySystem = Depends(get_memory_sys),
) -> GovernanceStatsResponse:
    """Get governance statistics."""
    try:
        stats = await memory_sys.get_governance_stats()
        return GovernanceStatsResponse(**stats)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get governance stats: {str(e)}",
        )


@router.get(
    "/stats",
    response_model=MemoryStatsResponse,
    summary="Get memory system statistics",
    description="Get comprehensive memory system statistics.",
)
async def get_memory_stats(
    memory_sys: MemorySystem = Depends(get_memory_sys),
) -> MemoryStatsResponse:
    """Get memory system statistics."""
    try:
        stats = await memory_sys.get_stats()
        return MemoryStatsResponse(**stats)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get memory stats: {str(e)}",
        )


@router.get(
    "/health",
    summary="Memory system health check",
    description="Check if the memory system is healthy.",
)
async def memory_health(
    memory_sys: MemorySystem = Depends(get_memory_sys),
):
    """Memory system health check."""
    healthy = await memory_sys.health_check()
    return {
        "healthy": healthy,
        "service": "memory",
    }