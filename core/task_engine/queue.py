"""
Task Engine Queue.

Priority-based task queue with fairness, persistence, and async operations.
"""

from __future__ import annotations
import asyncio
import heapq
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from core.task_engine.models import Task, TaskPriority, TaskStateMachine, TaskStatus
from core.events import get_event_bus
from core.structured_logging import get_logger, log_structured
import logging

logger = get_logger(__name__)


# =============================================================================
# Queue Entry
# =============================================================================

@dataclass(order=True)
class QueueEntry:
    """Queue entry with priority ordering."""
    # Sort key: (negative priority, sequence number) - higher priority first, FIFO within priority
    sort_key: tuple = field(compare=True, repr=False)
    task: Task = field(compare=False)
    enqueued_at: datetime = field(compare=False, default_factory=lambda: datetime.now(timezone.utc))
    attempts: int = field(compare=False, default=0)
    max_attempts: int = field(compare=False, default=3)

    def __post_init__(self):
        if not hasattr(self, 'sort_key') or self.sort_key is None:
            # Higher priority = smaller negative = comes first in min-heap
            # Sequence ensures FIFO within same priority
            self.sort_key = (-self.task.priority.value, self.enqueued_at.timestamp())


# =============================================================================
# Task Queue
# =============================================================================

class TaskQueue:
    """
    Priority-based task queue with:
    - 10 priority levels (1-10, higher = more urgent)
    - Fair scheduling within priority (FIFO)
    - Persistence to SQLite
    - Async operations
    """

    def __init__(
        self,
        priority_levels: int = 10,
        persistence_path: Optional[str] = None,
        fair_scheduling: bool = True,
    ):
        self.priority_levels = priority_levels
        self.fair_scheduling = fair_scheduling
        self.persistence_path = persistence_path or "./data/task_queue.json"

        # Main queue (heap)
        self._queue: List[QueueEntry] = []
        self._sequence = 0

        # Task tracking
        self._task_map: Dict[str, QueueEntry] = {}  # task_id -> entry
        self._processing: Set[str] = set()  # Currently processing task_ids

        # Persistence
        self._persist_interval = 30  # seconds
        self._persist_task: Optional[asyncio.Task] = None

        # Metrics
        self._enqueued_count = 0
        self._dequeued_count = 0
        self._requeued_count = 0
        self._completed_count = 0
        self._failed_count = 0

    async def initialize(self) -> None:
        """Initialize queue, load persisted tasks."""
        await self._load_persisted()
        self._persist_task = asyncio.create_task(self._persist_loop())
        log_structured(logger, logging.INFO, "Task queue initialized", queue_size=len(self._queue))

    async def shutdown(self) -> None:
        """Shutdown queue, persist remaining tasks."""
        if self._persist_task:
            self._persist_task.cancel()
            try:
                await self._persist_task
            except asyncio.CancelledError:
                pass
        await self._save_persisted()
        log_structured(logger, logging.INFO, "Task queue shutdown", remaining=len(self._queue))

    # =========================================================================
    # Core Queue Operations
    # =========================================================================

    def enqueue(self, task: Task, max_attempts: int = 3) -> str:
        """
        Add a task to the queue.

        Args:
            task: Task to enqueue
            max_attempts: Maximum execution attempts

        Returns:
            Task ID
        """
        # Validate task state
        if task.status not in (TaskStatus.CREATED, TaskStatus.QUEUED, TaskStatus.PAUSED):
            raise ValueError(f"Cannot enqueue task in state {task.status.value}")

        # Update task status
        TaskStateMachine.transition(task, TaskStatus.QUEUED)

        # Create queue entry
        self._sequence += 1
        entry = QueueEntry(
            sort_key=(-task.priority.value, self._sequence),
            task=task,
            max_attempts=max_attempts,
        )

        # Add to queue and map
        heapq.heappush(self._queue, entry)
        self._task_map[task.task_id] = entry
        self._enqueued_count += 1

        # Publish event
        asyncio.create_task(self._publish_enqueue_event(task))

        log_structured(
            logger, logging.INFO,
            "Task enqueued",
            task_id=task.task_id,
            priority=task.priority.value,
            queue_size=len(self._queue),
        )

        return task.task_id

    def dequeue(self) -> Optional[Task]:
        """
        Remove and return the highest priority task.

        Returns:
            Next task to execute, or None if queue empty
        """
        while self._queue:
            entry = heapq.heappop(self._queue)

            # Skip if already processing (shouldn't happen but safety)
            if entry.task.task_id in self._processing:
                continue

            # Check if task still exists in map (may have been removed)
            if entry.task.task_id not in self._task_map:
                continue

            # Remove from map
            del self._task_map[entry.task.task_id]

            # Mark as processing
            self._processing.add(entry.task.task_id)
            entry.attempts += 1

            # Update task status
            TaskStateMachine.transition(entry.task, TaskStatus.RUNNING)
            entry.task.started_at = datetime.now(timezone.utc)

            self._dequeued_count += 1

            log_structured(
                logger, logging.INFO,
                "Task dequeued",
                task_id=entry.task.task_id,
                attempt=entry.attempts,
                queue_size=len(self._queue),
            )

            return entry.task

        return None

    def requeue(self, task: Task, reason: str = "") -> bool:
        """
        Re-queue a task (e.g., after retry or waiting).

        Args:
            task: Task to requeue
            reason: Reason for requeue

        Returns:
            True if requeued successfully
        """
        if task.task_id in self._processing:
            self._processing.discard(task.task_id)

        # Reset status if needed
        if task.status in (TaskStatus.RUNNING, TaskStatus.WAITING_APPROVAL,
                          TaskStatus.WAITING_TOOL, TaskStatus.WAITING_MODEL,
                          TaskStatus.WAITING_RESOURCE, TaskStatus.WAITING_HUMAN,
                          TaskStatus.WAITING_AGENT):
            TaskStateMachine.transition(task, TaskStatus.QUEUED)
        elif task.status == TaskStatus.RETRYING:
            TaskStateMachine.transition(task, TaskStatus.QUEUED)

        # Re-enqueue with incremented sequence for fairness
        self._sequence += 1
        entry = QueueEntry(
            sort_key=(-task.priority.value, self._sequence),
            task=task,
            max_attempts=task.metadata.get("max_attempts", 3),
        )
        entry.attempts = task.metadata.get("attempts", 0)

        heapq.heappush(self._queue, entry)
        self._task_map[task.task_id] = entry
        self._requeued_count += 1

        log_structured(
            logger, logging.INFO,
            "Task requeued",
            task_id=task.task_id,
            reason=reason,
            attempt=entry.attempts,
            queue_size=len(self._queue),
        )

        return True

    def remove(self, task_id: str) -> bool:
        """
        Remove a task from the queue.

        Args:
            task_id: Task to remove

        Returns:
            True if task was found and removed
        """
        # Remove from processing set
        self._processing.discard(task_id)

        # Remove from map (lazy removal from heap)
        if task_id in self._task_map:
            del self._task_map[task_id]
            log_structured(logger, logging.INFO, "Task removed from queue", task_id=task_id)
            return True

        return False

    def get_task(self, task_id: str) -> Optional[Task]:
        """Get a task by ID (if in queue)."""
        entry = self._task_map.get(task_id)
        return entry.task if entry else None

    def get_queue_size(self) -> int:
        """Get current queue size."""
        return len(self._queue)

    def get_processing_count(self) -> int:
        """Get number of tasks currently processing."""
        return len(self._processing)

    def get_tasks_by_status(self, status: TaskStatus) -> List[Task]:
        """Get all tasks in queue with a specific status."""
        return [
            entry.task for entry in self._task_map.values()
            if entry.task.status == status
        ]

    def get_all_queued_tasks(self) -> List[Task]:
        """Get all tasks currently in queue (for persistence/admin)."""
        return [entry.task for entry in self._task_map.values()]

    # =========================================================================
    # Persistence
    # =========================================================================

    async def _save_persisted(self) -> None:
        """Save queue state to disk."""
        try:
            data = {
                "sequence": self._sequence,
                "tasks": [],
            }

            for entry in self._task_map.values():
                data["tasks"].append({
                    "task": entry.task.to_dict(),
                    "attempts": entry.attempts,
                    "max_attempts": entry.max_attempts,
                    "enqueued_at": entry.enqueued_at.isoformat(),
                })

            # Ensure directory exists
            os.makedirs(os.path.dirname(self.persistence_path), exist_ok=True)

            # Write atomically
            temp_path = self.persistence_path + ".tmp"
            with open(temp_path, "w") as f:
                json.dump(data, f, indent=2)
            os.replace(temp_path, self.persistence_path)

            log_structured(logger, logging.DEBUG, "Queue persisted", task_count=len(data["tasks"]))

        except Exception as e:
            log_structured(logger, logging.ERROR, "Failed to persist queue", error=str(e))

    async def _load_persisted(self) -> None:
        """Load queue state from disk."""
        try:
            if not os.path.exists(self.persistence_path):
                return

            with open(self.persistence_path, "r") as f:
                data = json.load(f)

            self._sequence = data.get("sequence", 0)

            for task_data in data.get("tasks", []):
                task = Task.from_dict(task_data["task"])
                entry = QueueEntry(
                    sort_key=(-task.priority.value, self._sequence),
                    task=task,
                    attempts=task_data.get("attempts", 0),
                    max_attempts=task_data.get("max_attempts", 3),
                )
                if task_data.get("enqueued_at"):
                    entry.enqueued_at = datetime.fromisoformat(task_data["enqueued_at"])

                heapq.heappush(self._queue, entry)
                self._task_map[task.task_id] = entry

            log_structured(logger, logging.INFO, "Queue loaded from persistence", task_count=len(self._task_map))

        except Exception as e:
            log_structured(logger, logging.ERROR, "Failed to load persisted queue", error=str(e))

    async def _persist_loop(self) -> None:
        """Periodic persistence loop."""
        while True:
            try:
                await asyncio.sleep(self._persist_interval)
                await self._save_persisted()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log_structured(logger, logging.ERROR, "Persist loop error", error=str(e))

    # =========================================================================
    # Event Publishing
    # =========================================================================

    async def _publish_enqueue_event(self, task: Task) -> None:
        """Publish task enqueued event."""
        try:
            bus = await get_event_bus()
            from core.events.models import Event, EventPriority
            event = Event(
                type="tasks.enqueued",
                payload={
                    "task_id": task.task_id,
                    "kind": task.kind.value,
                    "priority": task.priority.value,
                    "status": task.status.value,
                },
                priority=EventPriority.NORMAL,
            )
            await bus.publish(event)
        except Exception as e:
            log_structured(logger, logging.DEBUG, "Failed to publish enqueue event", error=str(e))

    # =========================================================================
    # Metrics
    # =========================================================================

    def get_metrics(self) -> Dict[str, Any]:
        """Get queue metrics."""
        return {
            "queue_size": len(self._queue),
            "processing_count": len(self._processing),
            "enqueued_total": self._enqueued_count,
            "dequeued_total": self._dequeued_count,
            "requeued_total": self._requeued_count,
            "completed_total": self._completed_count,
            "failed_total": self._failed_count,
            "priority_distribution": self._get_priority_distribution(),
        }

    def _get_priority_distribution(self) -> Dict[int, int]:
        """Get count of tasks per priority level."""
        dist = {i: 0 for i in range(1, self.priority_levels + 1)}
        for entry in self._task_map.values():
            dist[entry.task.priority.value] += 1
        return dist

    def record_completion(self, task_id: str, success: bool = True) -> None:
        """Record task completion for metrics."""
        self._processing.discard(task_id)
        if success:
            self._completed_count += 1
        else:
            self._failed_count += 1


# =============================================================================
# Global Queue Instance
# =============================================================================

_task_queue: Optional[TaskQueue] = None


def get_task_queue() -> Optional[TaskQueue]:
    """Get the global task queue instance."""
    return _task_queue


def init_task_queue(
    priority_levels: int = 10,
    persistence_path: Optional[str] = None,
    fair_scheduling: bool = True,
) -> TaskQueue:
    """Initialize the global task queue."""
    global _task_queue
    _task_queue = TaskQueue(
        priority_levels=priority_levels,
        persistence_path=persistence_path,
        fair_scheduling=fair_scheduling,
    )
    return _task_queue


async def shutdown_task_queue() -> None:
    """Shutdown the global task queue."""
    global _task_queue
    if _task_queue:
        await _task_queue.shutdown()
        _task_queue = None


# =============================================================================
# Export
# =============================================================================

__all__ = [
    "TaskQueue",
    "QueueEntry",
    "get_task_queue",
    "init_task_queue",
    "shutdown_task_queue",
]