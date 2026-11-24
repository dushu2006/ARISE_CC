"""
Task Engine API Endpoints.

Provides REST API for task management per OpenAPI spec.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from core.task_engine import get_task_engine
from core.task_engine.models import TaskKind, TaskPriority, TaskStatus
from core.events import get_event_bus
from core.events.models import Event, EventPriority

router = APIRouter(prefix="/tasks", tags=["tasks"])


# ============================================================
# Request/Response Models
# ============================================================

class TaskCreateRequest(BaseModel):
    """Request to create a new task."""
    kind: str = Field(..., description="Task kind (shell.exec, filesystem.read, etc.)")
    payload: Dict[str, Any] = Field(..., description="Task-specific payload")
    priority: int = Field(default=5, ge=1, le=10, description="Priority 1-10")
    resource_limits: Optional[Dict[str, Any]] = Field(default=None, description="Resource limits")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional metadata")


class TaskResponse(BaseModel):
    """Task response model."""
    task_id: str
    kind: str
    status: str
    priority: int
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    progress: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TaskListResponse(BaseModel):
    """Paginated task list response."""
    tasks: List[TaskResponse]
    total: int
    page: int
    page_size: int


class TaskTraceResponse(BaseModel):
    """Task execution trace response."""
    task_id: str
    trace: List[Dict[str, Any]]


class TaskCancelResponse(BaseModel):
    """Task cancellation response."""
    task_id: str
    status: str
    message: str


# ============================================================
# Dependencies
# ============================================================

def get_task_engine_dep():
    """Get task engine instance."""
    engine = get_task_engine()
    if not engine:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Task engine not initialized",
        )
    return engine


# ============================================================
# Helper Functions
# ============================================================

def _task_to_response(task) -> TaskResponse:
    """Convert task to response model."""
    from core.task_engine.models import TaskResult

    progress = None
    if task.steps:
        completed = sum(1 for s in task.steps if s.status == TaskStatus.COMPLETED)
        progress = completed / len(task.steps) * 100

    result_dict = None
    if task.result:
        if isinstance(task.result, TaskResult):
            result_dict = task.result.to_dict()
        else:
            result_dict = task.result

    return TaskResponse(
        task_id=task.task_id,
        kind=task.kind.value,
        status=task.status.value,
        priority=task.priority.value,
        created_at=task.created_at.isoformat(),
        started_at=task.started_at.isoformat() if task.started_at else None,
        completed_at=task.completed_at.isoformat() if task.completed_at else None,
        result=result_dict,
        error=task.result.error if task.result and hasattr(task.result, 'error') else None,
        progress=progress,
        metadata=task.metadata,
    )


# ============================================================
# Endpoints
# ============================================================

@router.post(
    "",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new task",
    description="Submit a new task for execution.",
)
async def create_task(
    request: TaskCreateRequest,
    engine=Depends(get_task_engine_dep),
) -> TaskResponse:
    """
    Create a new task.

    Submits a task to the task engine for execution.
    Returns the task ID immediately; use GET /tasks/{task_id} to poll for status.
    """
    # Validate kind
    try:
        kind = TaskKind(request.kind)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid task kind: {request.kind}",
        )

    # Build task
    from core.task_engine.kinds import create_task_from_kind
    from core.task_engine.models import ResourceLimits, TaskPriority

    resource_limits = None
    if request.resource_limits:
        resource_limits = ResourceLimits.from_dict(request.resource_limits)

    task = create_task_from_kind(
        kind=kind,
        payload=request.payload,
        priority=TaskPriority(request.priority),
        resource_limits=resource_limits,
        metadata=request.metadata or {},
    )

    # Submit to engine
    task_id = engine.submit(task)

    # Get the task back
    submitted_task = engine.get_task(task_id)
    if not submitted_task:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Task submitted but not found in queue",
        )

    return _task_to_response(submitted_task)


@router.get(
    "/{task_id}",
    response_model=TaskResponse,
    summary="Get task by ID",
    description="Retrieve current status and result of a task.",
)
async def get_task(
    task_id: str,
    engine=Depends(get_task_engine_dep),
) -> TaskResponse:
    """Get task by ID."""
    task = engine.get_task(task_id)
    if not task:
        # Check completed tasks
        result = engine.get_task_result(task_id)
        if result:
            # Create a minimal task-like object for response
            from core.task_engine.models import Task
            task = Task(
                task_id=task_id,
                kind=TaskKind.SHELL_EXEC,  # placeholder
                status=result.status,
                priority=TaskPriority.NORMAL,
                created_at=result.started_at or result.completed_at,
                result=result,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Task not found: {task_id}",
            )

    return _task_to_response(task)


@router.get(
    "",
    response_model=TaskListResponse,
    summary="List tasks",
    description="List tasks with optional filters.",
)
async def list_tasks(
    engine=Depends(get_task_engine_dep),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
    kind: Optional[str] = Query(None, description="Filter by task kind"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size"),
) -> TaskListResponse:
    """List tasks with filters."""
    status_enum = None
    if status_filter:
        try:
            status_enum = TaskStatus(status_filter)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status_filter}",
            )

    kind_enum = None
    if kind:
        try:
            kind_enum = TaskKind(kind)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid kind: {kind}",
            )

    result = engine.list_tasks(
        status_filter=status_enum,
        kind_filter=kind_enum,
        page=page,
        page_size=page_size,
    )

    return TaskListResponse(
        tasks=[_task_to_response(t) for t in result["tasks"]],
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
    )


@router.post(
    "/{task_id}/cancel",
    response_model=TaskCancelResponse,
    summary="Cancel a task",
    description="Request cancellation of a running or queued task.",
)
async def cancel_task(
    task_id: str,
    engine=Depends(get_task_engine_dep),
) -> TaskCancelResponse:
    """Cancel a task."""
    success = engine.cancel_task(task_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task not found or cannot be cancelled: {task_id}",
        )

    return TaskCancelResponse(
        task_id=task_id,
        status="cancelled",
        message="Cancellation requested",
    )


@router.get(
    "/{task_id}/trace",
    response_model=TaskTraceResponse,
    summary="Get task execution trace",
    description="Get detailed execution trace with all state transitions.",
)
async def get_task_trace(
    task_id: str,
    engine=Depends(get_task_engine_dep),
) -> TaskTraceResponse:
    """Get task execution trace."""
    trace = engine.get_execution_trace(task_id)

    if not trace:
        # Check if task exists
        task = engine.get_task(task_id)
        if not task:
            result = engine.get_task_result(task_id)
            if not result:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Task not found: {task_id}",
                )

    return TaskTraceResponse(
        task_id=task_id,
        trace=trace,
    )


# ============================================================
# WebSocket endpoint for real-time progress
# ============================================================

@router.websocket("/ws/tasks/{task_id}")
async def websocket_task_progress(websocket: WebSocket, task_id: str):
    """WebSocket for real-time task progress updates."""
    await websocket.accept()

    engine = get_task_engine()
    if not engine:
        await websocket.send_json({"error": "Task engine not available"})
        await websocket.close()
        return

    try:
        # Send initial status
        task = engine.get_task(task_id)
        if task:
            await websocket.send_json({
                "type": "status",
                "task_id": task_id,
                "status": task.status.value,
                "progress": _calculate_progress(task),
            })

        # Subscribe to task events
        event_queue = asyncio.Queue()
        subscription_id = None

        async def event_handler(event):
            await event_queue.put(event)

        # Subscribe to task events
        bus = await get_event_bus()
        if bus:
            subscription_id = await bus.subscribe(f"tasks.{task_id}", event_handler)

        # Send events to websocket
        while True:
            try:
                event = await asyncio.wait_for(event_queue.get(), timeout=30.0)
                await websocket.send_json(event)
            except asyncio.TimeoutError:
                # Send heartbeat
                await websocket.send_json({"type": "heartbeat"})
            except WebSocketDisconnect:
                break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        await websocket.send_json({"error": str(e)})
    finally:
        # Unsubscribe
        try:
            bus = await get_event_bus()
            if bus and subscription_id:
                await bus.unsubscribe(subscription_id)
        except:
            pass


def _calculate_progress(task) -> float:
    """Calculate task progress percentage."""
    if not task.steps:
        return 0.0
    completed = sum(1 for s in task.steps if s.status == TaskStatus.COMPLETED)
    return completed / len(task.steps) * 100


# ============================================================
# Import asyncio for websocket
# ============================================================

import asyncio