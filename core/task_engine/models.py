"""
Task Engine Models.

Core data structures for the 28-state task lifecycle, task kinds,
priorities, checkpoints, and results.
"""

from __future__ import annotations
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from core.config.models import TaskKind, TaskPriority, TaskStatus


# =============================================================================
# Enums (also available from config.models for shared use)
# =============================================================================

class ResourceLimits:
    """Resource limits for task execution."""

    def __init__(
        self,
        memory_mb: int = 512,
        cpu_percent: int = 50,
        disk_mb: int = 1024,
        timeout_seconds: int = 300,
    ):
        self.memory_mb = memory_mb
        self.cpu_percent = cpu_percent
        self.disk_mb = disk_mb
        self.timeout_seconds = timeout_seconds

    def to_dict(self) -> Dict[str, Any]:
        return {
            "memory_mb": self.memory_mb,
            "cpu_percent": self.cpu_percent,
            "disk_mb": self.disk_mb,
            "timeout_seconds": self.timeout_seconds,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResourceLimits":
        return cls(
            memory_mb=data.get("memory_mb", 512),
            cpu_percent=data.get("cpu_percent", 50),
            disk_mb=data.get("disk_mb", 1024),
            timeout_seconds=data.get("timeout_seconds", 300),
        )


# =============================================================================
# Task Data Classes
# =============================================================================

@dataclass
class TaskStep:
    """A single step in task execution."""

    step_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    kind: TaskKind = TaskKind.SHELL_EXEC
    name: str = ""
    description: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    status: TaskStatus = TaskStatus.CREATED
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "kind": self.kind.value,
            "name": self.name,
            "description": self.description,
            "payload": self.payload,
            "status": self.status.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "result": self.result,
            "error": self.error,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskStep":
        step = cls(
            step_id=data.get("step_id", str(uuid.uuid4())[:12]),
            kind=TaskKind(data["kind"]),
            name=data.get("name", ""),
            description=data.get("description", ""),
            payload=data.get("payload", {}),
            status=TaskStatus(data.get("status", "CREATED")),
            retry_count=data.get("retry_count", 0),
            max_retries=data.get("max_retries", 3),
        )
        if data.get("started_at"):
            step.started_at = datetime.fromisoformat(data["started_at"])
        if data.get("completed_at"):
            step.completed_at = datetime.fromisoformat(data["completed_at"])
        step.result = data.get("result")
        step.error = data.get("error")
        return step


@dataclass
class TaskCheckpoint:
    """Task checkpoint for resume capability."""

    checkpoint_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    task_id: str = ""
    step_index: int = 0
    task_status: TaskStatus = TaskStatus.CREATED
    step_statuses: Dict[str, TaskStatus] = field(default_factory=dict)
    step_results: Dict[str, Any] = field(default_factory=dict)
    variables: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "task_id": self.task_id,
            "step_index": self.step_index,
            "task_status": self.task_status.value,
            "step_statuses": {k: v.value for k, v in self.step_statuses.items()},
            "step_results": self.step_results,
            "variables": self.variables,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskCheckpoint":
        cp = cls(
            checkpoint_id=data.get("checkpoint_id", str(uuid.uuid4())[:12]),
            task_id=data.get("task_id", ""),
            step_index=data.get("step_index", 0),
            task_status=TaskStatus(data.get("task_status", "CREATED")),
            step_results=data.get("step_results", {}),
            variables=data.get("variables", {}),
        )
        cp.step_statuses = {
            k: TaskStatus(v) for k, v in data.get("step_statuses", {}).items()
        }
        if data.get("created_at"):
            cp.created_at = datetime.fromisoformat(data["created_at"])
        return cp


@dataclass
class TaskResult:
    """Result of task execution."""

    task_id: str
    status: TaskStatus
    output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    steps: List[TaskStep] = field(default_factory=list)
    checkpoints: List[TaskCheckpoint] = field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "output": self.output,
            "error": self.error,
            "steps": [s.to_dict() for s in self.steps],
            "checkpoints": [c.to_dict() for c in self.checkpoints],
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskResult":
        result = cls(
            task_id=data["task_id"],
            status=TaskStatus(data["status"]),
            output=data.get("output"),
            error=data.get("error"),
            duration_ms=data.get("duration_ms"),
            metadata=data.get("metadata", {}),
        )
        result.steps = [TaskStep.from_dict(s) for s in data.get("steps", [])]
        result.checkpoints = [TaskCheckpoint.from_dict(c) for c in data.get("checkpoints", [])]
        if data.get("started_at"):
            result.started_at = datetime.fromisoformat(data["started_at"])
        if data.get("completed_at"):
            result.completed_at = datetime.fromisoformat(data["completed_at"])
        return result


@dataclass
class Task:
    """Main task entity with full lifecycle state."""

    task_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    kind: TaskKind = TaskKind.SHELL_EXEC
    name: str = ""
    description: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    priority: TaskPriority = TaskPriority.NORMAL
    status: TaskStatus = TaskStatus.CREATED
    resource_limits: ResourceLimits = field(default_factory=ResourceLimits)
    steps: List[TaskStep] = field(default_factory=list)
    current_step_index: int = 0
    result: Optional[TaskResult] = None
    checkpoints: List[TaskCheckpoint] = field(default_factory=list)
    parent_task_id: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    correlation_id: Optional[str] = None
    trace_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "kind": self.kind.value,
            "name": self.name,
            "description": self.description,
            "payload": self.payload,
            "priority": self.priority.value,
            "status": self.status.value,
            "resource_limits": self.resource_limits.to_dict(),
            "steps": [s.to_dict() for s in self.steps],
            "current_step_index": self.current_step_index,
            "result": self.result.to_dict() if self.result else None,
            "checkpoints": [c.to_dict() for c in self.checkpoints],
            "parent_task_id": self.parent_task_id,
            "tags": self.tags,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "correlation_id": self.correlation_id,
            "trace_id": self.trace_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Task":
        task = cls(
            task_id=data.get("task_id", str(uuid.uuid4())[:12]),
            kind=TaskKind(data["kind"]),
            name=data.get("name", ""),
            description=data.get("description", ""),
            payload=data.get("payload", {}),
            priority=TaskPriority(data.get("priority", 5)),
            status=TaskStatus(data.get("status", "CREATED")),
            resource_limits=ResourceLimits.from_dict(data.get("resource_limits", {})),
            current_step_index=data.get("current_step_index", 0),
            parent_task_id=data.get("parent_task_id"),
            tags=data.get("tags", []),
            metadata=data.get("metadata", {}),
            correlation_id=data.get("correlation_id"),
            trace_id=data.get("trace_id"),
        )
        task.steps = [TaskStep.from_dict(s) for s in data.get("steps", [])]
        task.checkpoints = [TaskCheckpoint.from_dict(c) for c in data.get("checkpoints", [])]
        if data.get("result"):
            task.result = TaskResult.from_dict(data["result"])
        for dt_field in ["created_at", "updated_at", "started_at", "completed_at"]:
            if data.get(dt_field):
                setattr(task, dt_field, datetime.fromisoformat(data[dt_field]))
        return task

    def get_current_step(self) -> Optional[TaskStep]:
        """Get the currently executing step."""
        if 0 <= self.current_step_index < len(self.steps):
            return self.steps[self.current_step_index]
        return None

    def is_terminal(self) -> bool:
        """Check if task is in a terminal state."""
        return self.status in {
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
            TaskStatus.EXPIRED,
            TaskStatus.TIMEOUT,
        }

    def can_transition_to(self, new_status: TaskStatus) -> bool:
        """Check if transition to new status is valid."""
        return TaskStateMachine.can_transition(self.status, new_status)


# =============================================================================
# Task State Machine - 28 States with Valid Transitions
# =============================================================================

class TaskStateMachine:
    """
    Task state machine with 28 states and validated transitions.

    States (grouped by phase):
    - Initialization: CREATED, QUEUED
    - Understanding: UNDERSTANDING
    - Planning: PLANNING
    - Ready: READY
    - Execution: RUNNING, WAITING_APPROVAL, WAITING_TOOL, WAITING_MODEL,
                WAITING_RESOURCE, WAITING_HUMAN, WAITING_AGENT
    - Verification: VERIFYING
    - Completion: COMPLETED, FAILED, CANCELLED
    - Control: PAUSED, RETRYING, CHECKPOINTING, RESTORING
    - Delegation: DELEGATING, AGGREGATING, SYNTHESIZING, VALIDATING
    - Cleanup: ARCHIVING
    - Terminal: EXPIRED, TIMEOUT, UNKNOWN
    """

    # Define all valid state transitions
    VALID_TRANSITIONS: Dict[TaskStatus, List[TaskStatus]] = {
        TaskStatus.CREATED: [
            TaskStatus.QUEUED,
            TaskStatus.UNDERSTANDING,
            TaskStatus.CANCELLED,
        ],
        TaskStatus.QUEUED: [
            TaskStatus.UNDERSTANDING,
            TaskStatus.CANCELLED,
            TaskStatus.PAUSED,
        ],
        TaskStatus.UNDERSTANDING: [
            TaskStatus.PLANNING,
            TaskStatus.CANCELLED,
            TaskStatus.FAILED,
            TaskStatus.PAUSED,
        ],
        TaskStatus.PLANNING: [
            TaskStatus.READY,
            TaskStatus.CANCELLED,
            TaskStatus.FAILED,
            TaskStatus.PAUSED,
        ],
        TaskStatus.READY: [
            TaskStatus.RUNNING,
            TaskStatus.CANCELLED,
            TaskStatus.PAUSED,
        ],
        TaskStatus.RUNNING: [
            TaskStatus.WAITING_APPROVAL,
            TaskStatus.WAITING_TOOL,
            TaskStatus.WAITING_MODEL,
            TaskStatus.WAITING_RESOURCE,
            TaskStatus.WAITING_HUMAN,
            TaskStatus.WAITING_AGENT,
            TaskStatus.VERIFYING,
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
            TaskStatus.PAUSED,
            TaskStatus.RETRYING,
            TaskStatus.CHECKPOINTING,
            TaskStatus.DELEGATING,
        ],
        TaskStatus.WAITING_APPROVAL: [
            TaskStatus.RUNNING,
            TaskStatus.CANCELLED,
            TaskStatus.FAILED,
            TaskStatus.TIMEOUT,
            TaskStatus.PAUSED,
        ],
        TaskStatus.WAITING_TOOL: [
            TaskStatus.RUNNING,
            TaskStatus.CANCELLED,
            TaskStatus.FAILED,
            TaskStatus.TIMEOUT,
            TaskStatus.PAUSED,
        ],
        TaskStatus.WAITING_MODEL: [
            TaskStatus.RUNNING,
            TaskStatus.CANCELLED,
            TaskStatus.FAILED,
            TaskStatus.TIMEOUT,
            TaskStatus.PAUSED,
        ],
        TaskStatus.WAITING_RESOURCE: [
            TaskStatus.RUNNING,
            TaskStatus.CANCELLED,
            TaskStatus.FAILED,
            TaskStatus.TIMEOUT,
            TaskStatus.PAUSED,
        ],
        TaskStatus.WAITING_HUMAN: [
            TaskStatus.RUNNING,
            TaskStatus.CANCELLED,
            TaskStatus.FAILED,
            TaskStatus.TIMEOUT,
            TaskStatus.PAUSED,
        ],
        TaskStatus.WAITING_AGENT: [
            TaskStatus.RUNNING,
            TaskStatus.CANCELLED,
            TaskStatus.FAILED,
            TaskStatus.TIMEOUT,
            TaskStatus.PAUSED,
        ],
        TaskStatus.VERIFYING: [
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.RETRYING,
            TaskStatus.CANCELLED,
            TaskStatus.PAUSED,
        ],
        TaskStatus.COMPLETED: [
            TaskStatus.ARCHIVING,
            TaskStatus.EXPIRED,
        ],
        TaskStatus.FAILED: [
            TaskStatus.RETRYING,
            TaskStatus.CANCELLED,
            TaskStatus.ARCHIVING,
            TaskStatus.EXPIRED,
        ],
        TaskStatus.CANCELLED: [
            TaskStatus.ARCHIVING,
            TaskStatus.EXPIRED,
        ],
        TaskStatus.PAUSED: [
            TaskStatus.RUNNING,
            TaskStatus.CANCELLED,
            TaskStatus.EXPIRED,
        ],
        TaskStatus.RETRYING: [
            TaskStatus.RUNNING,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
            TaskStatus.PAUSED,
        ],
        TaskStatus.CHECKPOINTING: [
            TaskStatus.RUNNING,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        ],
        TaskStatus.RESTORING: [
            TaskStatus.RUNNING,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        ],
        TaskStatus.DELEGATING: [
            TaskStatus.RUNNING,
            TaskStatus.AGGREGATING,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
            TaskStatus.PAUSED,
        ],
        TaskStatus.AGGREGATING: [
            TaskStatus.SYNTHESIZING,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
            TaskStatus.PAUSED,
        ],
        TaskStatus.SYNTHESIZING: [
            TaskStatus.VALIDATING,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
            TaskStatus.PAUSED,
        ],
        TaskStatus.VALIDATING: [
            TaskStatus.VERIFYING,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
            TaskStatus.PAUSED,
        ],
        TaskStatus.ARCHIVING: [
            TaskStatus.EXPIRED,
        ],
        TaskStatus.EXPIRED: [],
        TaskStatus.TIMEOUT: [
            TaskStatus.RETRYING,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        ],
        TaskStatus.UNKNOWN: [
            TaskStatus.CANCELLED,
            TaskStatus.FAILED,
        ],
    }

    @classmethod
    def can_transition(cls, from_state: TaskStatus, to_state: TaskStatus) -> bool:
        """Check if a state transition is valid."""
        if from_state == to_state:
            return True  # No-op transition allowed
        valid_targets = cls.VALID_TRANSITIONS.get(from_state, [])
        return to_state in valid_targets

    @classmethod
    def get_valid_transitions(cls, state: TaskStatus) -> List[TaskStatus]:
        """Get all valid transitions from a state."""
        return cls.VALID_TRANSITIONS.get(state, [])

    @classmethod
    def get_terminal_states(cls) -> List[TaskStatus]:
        """Get all terminal states."""
        return [
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
            TaskStatus.EXPIRED,
            TaskStatus.TIMEOUT,
        ]

    @classmethod
    def get_waiting_states(cls) -> List[TaskStatus]:
        """Get all waiting states."""
        return [
            TaskStatus.WAITING_APPROVAL,
            TaskStatus.WAITING_TOOL,
            TaskStatus.WAITING_MODEL,
            TaskStatus.WAITING_RESOURCE,
            TaskStatus.WAITING_HUMAN,
            TaskStatus.WAITING_AGENT,
        ]

    @classmethod
    def is_terminal(cls, state: TaskStatus) -> bool:
        """Check if state is terminal."""
        return state in cls.get_terminal_states()

    @classmethod
    def is_waiting(cls, state: TaskStatus) -> bool:
        """Check if state is a waiting state."""
        return state in cls.get_waiting_states()

    @classmethod
    def transition(cls, task: Task, new_status: TaskStatus) -> bool:
        """
        Perform a state transition on a task.

        Args:
            task: The task to transition
            new_status: The new status

        Returns:
            True if transition was successful

        Raises:
            ValueError: If transition is invalid
        """
        if not cls.can_transition(task.status, new_status):
            valid = cls.get_valid_transitions(task.status)
            raise ValueError(
                f"Invalid transition from {task.status.value} to {new_status.value}. "
                f"Valid transitions: {[s.value for s in valid]}"
            )

        task.status = new_status
        task.updated_at = datetime.now(timezone.utc)

        # Set timestamps for key transitions
        if new_status == TaskStatus.RUNNING and task.started_at is None:
            task.started_at = task.updated_at
        elif cls.is_terminal(new_status) and task.completed_at is None:
            task.completed_at = task.updated_at

        return True


# =============================================================================
# Export
# =============================================================================

__all__ = [
    "Task",
    "TaskStep",
    "TaskCheckpoint",
    "TaskResult",
    "TaskStateMachine",
    "ResourceLimits",
]