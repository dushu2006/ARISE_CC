"""
Task Engine Facade.

Main entry point for task management:
- Task submission and lifecycle management
- Queue integration
- Checkpoint integration
- WebSocket-based wait for completion
- Execution trace/history
"""

from __future__ import annotations
import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Callable, Awaitable

from core.task_engine.models import (
    Task, TaskStep, TaskKind, TaskPriority, TaskStatus,
    TaskStateMachine, TaskResult, ResourceLimits, TaskCheckpoint
)
from core.task_engine.queue import TaskQueue, init_task_queue, get_task_queue, shutdown_task_queue
from core.task_engine.checkpoint import CheckpointManager, CheckpointConfig, init_checkpoint_manager, get_checkpoint_manager, shutdown_checkpoint_manager
from core.task_engine.executor import TaskExecutor, SandboxConfig
from core.task_engine.kinds import create_step_from_kind
from core.events import get_event_bus
from core.events.models import Event, EventPriority
from core.structured_logging import get_logger, log_structured
import logging

logger = get_logger(__name__)


# =============================================================================
# Task Engine Configuration
# =============================================================================

@dataclass
class TaskEngineConfig:
    """Task engine configuration."""
    max_concurrent_tasks: int = 10
    default_priority: TaskPriority = TaskPriority.NORMAL
    checkpoint_interval_seconds: int = 30
    max_checkpoints_per_task: int = 100
    task_timeout_seconds: int = 3600
    sandbox: SandboxConfig = field(default_factory=SandboxConfig)
    queue_priority_levels: int = 10
    fair_scheduling: bool = True
    persistence_enabled: bool = True
    queue_persistence_path: str = "./data/task_queue.json"
    checkpoint_persistence_path: str = "./data/checkpoints"


# =============================================================================
# Task Engine
# =============================================================================

class TaskEngine:
    """
    Main Task Engine facade.

    Provides high-level API for:
    - Submitting tasks (sync and async)
    - Querying task status
    - Cancelling tasks
    - Waiting for completion (with WebSocket support)
    - Getting execution traces
    - Graceful shutdown
    """

    def __init__(self, config: Optional[TaskEngineConfig] = None):
        self.config = config or TaskEngineConfig()
        self._queue: Optional[TaskQueue] = None
        self._checkpoint_manager: Optional[CheckpointManager] = None
        self._executor: Optional[TaskExecutor] = None
        self._worker_tasks: List[asyncio.Task] = []
        self._running = False
        self._task_results: Dict[str, TaskResult] = {}
        self._waiters: Dict[str, List[asyncio.Future]] = {}

    async def initialize(self) -> None:
        """Initialize all components."""
        log_structured(logger, logging.INFO, "Initializing Task Engine")

        # Initialize queue
        self._queue = init_task_queue(
            priority_levels=self.config.queue_priority_levels,
            persistence_path=self.config.queue_persistence_path if self.config.persistence_enabled else None,
            fair_scheduling=self.config.fair_scheduling,
        )
        await self._queue.initialize()

        # Initialize checkpoint manager
        checkpoint_config = CheckpointConfig(
            interval_seconds=self.config.checkpoint_interval_seconds,
            max_checkpoints_per_task=self.config.max_checkpoints_per_task,
            persistence_path=self.config.checkpoint_persistence_path,
        )
        self._checkpoint_manager = init_checkpoint_manager(checkpoint_config)
        await self._checkpoint_manager.initialize()

        # Initialize executor
        self._executor = TaskExecutor(
            sandbox_config=self.config.sandbox,
            resource_limits=ResourceLimits(
                memory_mb=self.config.sandbox.memory_limit_mb,
                cpu_percent=self.config.sandbox.cpu_limit_percent,
                disk_mb=self.config.sandbox.disk_limit_mb,
                timeout_seconds=self.config.sandbox.timeout_seconds,
            ),
        )

        # Start worker tasks
        self._running = True
        for i in range(self.config.max_concurrent_tasks):
            task = asyncio.create_task(self._worker_loop(f"worker-{i}"))
            self._worker_tasks.append(task)

        log_structured(
            logger, logging.INFO,
            "Task Engine initialized",
            workers=self.config.max_concurrent_tasks,
            queue_persistence=self.config.persistence_enabled,
        )

    async def shutdown(self) -> None:
        """Graceful shutdown."""
        log_structured(logger, logging.INFO, "Shutting down Task Engine")
        self._running = False

        # Cancel all workers
        for worker in self._worker_tasks:
            worker.cancel()

        # Wait for workers to finish
        if self._worker_tasks:
            await asyncio.gather(*self._worker_tasks, return_exceptions=True)

        # Shutdown components
        if self._executor:
            await self._executor.shutdown()

        await shutdown_checkpoint_manager()
        await shutdown_task_queue()

        # Notify all waiters
        for futures in self._waiters.values():
            for fut in futures:
                if not fut.done():
                    fut.cancel()

        log_structured(logger, logging.INFO, "Task Engine shutdown complete")

    # =========================================================================
    # Task Submission
    # =========================================================================

    def submit(self, task: Task) -> str:
        """
        Submit a task for execution.

        Args:
            task: Task to submit

        Returns:
            Task ID
        """
        if not self._queue:
            raise RuntimeError("Task engine not initialized")

        # Ensure task has required fields
        if not task.task_id:
            task.task_id = str(uuid.uuid4())[:12]

        if not task.steps:
            # Create a single step from the task kind
            step = create_step_from_kind(task.kind, task.payload)
            task.steps = [step]

        # Set defaults
        if task.priority == TaskPriority.NORMAL and task.priority != self.config.default_priority:
            task.priority = self.config.default_priority

        # Set correlation/trace IDs if not present
        if not task.correlation_id:
            task.correlation_id = str(uuid.uuid4())[:12]
        if not task.trace_id:
            task.trace_id = str(uuid.uuid4())[:12]

        # Enqueue
        task_id = self._queue.enqueue(task)

        log_structured(logger, logging.INFO, "Task submitted", task_id=task_id, kind=task.kind.value)

        return task_id

    async def submit_and_wait(
        self,
        task: Task,
        timeout: Optional[float] = None,
    ) -> TaskResult:
        """
        Submit a task and wait for completion.

        Args:
            task: Task to submit
            timeout: Maximum time to wait (seconds)

        Returns:
            TaskResult with final status and output
        """
        task_id = self.submit(task)

        return await self.wait_for_task(task_id, timeout)

    # =========================================================================
    # Task Querying
    # =========================================================================

    def get_task(self, task_id: str) -> Optional[Task]:
        """Get a task by ID (from queue or results)."""
        if self._queue:
            task = self._queue.get_task(task_id)
            if task:
                return task

        # Check completed tasks
        if task_id in self._task_results:
            return self._task_results[task_id].__dict__.get("_task")  # Not ideal but works

        return None

    def get_task_status(self, task_id: str) -> Optional[TaskStatus]:
        """Get task status."""
        task = self.get_task(task_id)
        return task.status if task else None

    def get_task_result(self, task_id: str) -> Optional[TaskResult]:
        """Get task result (for completed tasks)."""
        return self._task_results.get(task_id)

    def list_tasks(
        self,
        status_filter: Optional[TaskStatus] = None,
        kind_filter: Optional[TaskKind] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """List tasks with filters."""
        if not self._queue:
            return {"tasks": [], "total": 0, "page": page, "page_size": page_size}

        all_tasks = self._queue.get_all_queued_tasks()

        # Add completed tasks from results
        for result in self._task_results.values():
            # We'd need to store the full task - for now just return queued
            pass

        # Apply filters
        if status_filter:
            all_tasks = [t for t in all_tasks if t.status == status_filter]
        if kind_filter:
            all_tasks = [t for t in all_tasks if t.kind == kind_filter]

        total = len(all_tasks)
        start = (page - 1) * page_size
        end = start + page_size
        tasks = all_tasks[start:end]

        return {
            "tasks": [t.to_dict() for t in tasks],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    # =========================================================================
    # Task Control
    # =========================================================================

    def cancel_task(self, task_id: str) -> bool:
        """Request cancellation of a task."""
        if not self._queue:
            return False

        # If in queue, remove it
        if self._queue.remove(task_id):
            log_structured(logger, logging.INFO, "Task cancelled (removed from queue)", task_id=task_id)
            return True

        # If running, request cancel via executor
        # This would need access to the specific executor running the task
        # For now, mark as cancelled in results if found
        log_structured(logger, logging.INFO, "Cancel requested for task", task_id=task_id)
        return True

    # =========================================================================
    # Wait for Completion
    # =========================================================================

    async def wait_for_task(
        self,
        task_id: str,
        timeout: Optional[float] = None,
    ) -> TaskResult:
        """
        Wait for a task to complete.

        Args:
            task_id: Task to wait for
            timeout: Maximum wait time in seconds

        Returns:
            TaskResult when complete

        Raises:
            asyncio.TimeoutError: If timeout exceeded
        """
        # Check if already complete
        result = self._task_results.get(task_id)
        if result:
            return result

        # Create future for this task
        future = asyncio.get_event_loop().create_future()
        if task_id not in self._waiters:
            self._waiters[task_id] = []
        self._waiters[task_id].append(future)

        try:
            if timeout:
                result = await asyncio.wait_for(future, timeout=timeout)
            else:
                result = await future
            return result
        except asyncio.TimeoutError:
            raise
        finally:
            # Clean up waiter
            if task_id in self._waiters:
                self._waiters[task_id].remove(future)
                if not self._waiters[task_id]:
                    del self._waiters[task_id]

    def _notify_waiters(self, task_id: str, result: TaskResult) -> None:
        """Notify all waiters for a task."""
        if task_id in self._waiters:
            for future in self._waiters[task_id]:
                if not future.done():
                    future.set_result(result)
            del self._waiters[task_id]

    # =========================================================================
    # Execution Trace
    # =========================================================================

    def get_execution_trace(self, task_id: str) -> List[Dict[str, Any]]:
        """Get execution trace for a task."""
        task = self.get_task(task_id)
        if not task:
            return []

        trace = []
        for step in task.steps:
            trace.append({
                "step_id": step.step_id,
                "kind": step.kind.value,
                "name": step.name,
                "status": step.status.value,
                "started_at": step.started_at.isoformat() if step.started_at else None,
                "completed_at": step.completed_at.isoformat() if step.completed_at else None,
                "result": step.result,
                "error": step.error,
                "retry_count": step.retry_count,
            })

        # Add checkpoint info
        for cp in task.checkpoints:
            trace.append({
                "type": "checkpoint",
                "checkpoint_id": cp.checkpoint_id,
                "step_index": cp.step_index,
                "task_status": cp.task_status.value,
                "created_at": cp.created_at.isoformat(),
            })

        return trace

    # =========================================================================
    # Worker Loop
    # =========================================================================

    async def _worker_loop(self, worker_name: str) -> None:
        """Main worker loop."""
        log_structured(logger, logging.INFO, "Worker started", worker=worker_name)

        while self._running:
            try:
                # Dequeue next task
                task = self._queue.dequeue()
                if not task:
                    await asyncio.sleep(0.5)  # Brief pause when queue empty
                    continue

                log_structured(logger, logging.INFO, "Worker picked up task", worker=worker_name, task_id=task.task_id)

                # Execute task
                await self._execute_task_with_checkpoints(task)

            except asyncio.CancelledError:
                break
            except Exception as e:
                log_structured(logger, logging.ERROR, "Worker error", worker=worker_name, error=str(e))
                await asyncio.sleep(1)  # Back off on error

        log_structured(logger, logging.INFO, "Worker stopped", worker=worker_name)

    async def _execute_task_with_checkpoints(self, task: Task) -> None:
        """Execute a task with checkpointing."""

        # Checkpoint callback
        async def checkpoint_callback(t: Task):
            if self._checkpoint_manager:
                self._checkpoint_manager.create_checkpoint(t, trigger="periodic")

        try:
            # Execute
            completed_task = await self._executor.execute_task(
                task,
                checkpoint_callback=checkpoint_callback if self._checkpoint_manager else None,
            )

            # Create final checkpoint
            if self._checkpoint_manager:
                self._checkpoint_manager.create_checkpoint(completed_task, trigger="completion")

            # Create result
            result = self._create_task_result(completed_task)

            # Store result
            self._task_results[task.task_id] = result

            # Record queue metrics
            self._queue.record_completion(task.task_id, success=completed_task.status == TaskStatus.COMPLETED)

            # Publish completion event
            try:
                bus = await get_event_bus()
                if bus:
                    event = Event(
                        type="tasks.completed",
                        payload={
                            "task_id": task.task_id,
                            "status": completed_task.status.value,
                            "duration_ms": result.duration_ms,
                        },
                        priority=EventPriority.NORMAL,
                    )
                    await bus.publish(event)
            except Exception as e:
                log_structured(logger, logging.DEBUG, "Failed to publish completion event", error=str(e))

            # Notify waiters
            self._notify_waiters(task.task_id, result)

            log_structured(
                logger, logging.INFO,
                "Task completed",
                task_id=task.task_id,
                status=completed_task.status.value,
                duration_ms=result.duration_ms,
            )

        except Exception as e:
            log_structured(logger, logging.ERROR, "Task execution failed", task_id=task.task_id, error=str(e))

            # Create failed result
            result = TaskResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                error=str(e),
                steps=task.steps,
                checkpoints=task.checkpoints,
                started_at=task.started_at,
                completed_at=datetime.now(timezone.utc),
            )
            self._task_results[task.task_id] = result
            self._queue.record_completion(task.task_id, success=False)
            self._notify_waiters(task.task_id, result)

    def _create_task_result(self, task: Task) -> TaskResult:
        """Create TaskResult from completed task."""
        output = None
        error = None

        if task.status == TaskStatus.COMPLETED:
            output = {}
            for step in task.steps:
                if step.result:
                    output[step.step_id] = step.result
        else:
            for step in task.steps:
                if step.error:
                    error = step.error
                    break

        duration_ms = None
        if task.started_at and task.completed_at:
            duration_ms = (task.completed_at - task.started_at).total_seconds() * 1000

        return TaskResult(
            task_id=task.task_id,
            status=task.status,
            output=output,
            error=error,
            steps=task.steps,
            checkpoints=task.checkpoints,
            started_at=task.started_at,
            completed_at=task.completed_at,
            duration_ms=duration_ms,
        )

    # =========================================================================
    # Metrics
    # =========================================================================

    def get_metrics(self) -> Dict[str, Any]:
        """Get engine metrics."""
        queue_metrics = self._queue.get_metrics() if self._queue else {}

        return {
            "running": self._running,
            "workers": len(self._worker_tasks),
            "waiting_tasks": len(self._waiters),
            "completed_tasks": len(self._task_results),
            "queue": queue_metrics,
        }


# =============================================================================
# Global Instance
# =============================================================================

_task_engine: Optional[TaskEngine] = None


def get_task_engine() -> Optional[TaskEngine]:
    """Get the global task engine instance."""
    return _task_engine


async def init_task_engine(config: Optional[TaskEngineConfig] = None) -> TaskEngine:
    """Initialize the global task engine."""
    global _task_engine
    _task_engine = TaskEngine(config)
    await _task_engine.initialize()
    return _task_engine


async def shutdown_task_engine() -> None:
    """Shutdown the global task engine."""
    global _task_engine
    if _task_engine:
        await _task_engine.shutdown()
        _task_engine = None


# =============================================================================
# Export
# =============================================================================

__all__ = [
    "TaskEngine",
    "TaskEngineConfig",
    "get_task_engine",
    "init_task_engine",
    "shutdown_task_engine",
]