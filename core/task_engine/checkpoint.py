"""
Task Engine Checkpoint Manager.

Handles interval-based checkpointing, save/restore of task state,
and resume from last checkpoint.
"""

from __future__ import annotations
import asyncio
import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.task_engine.models import Task, TaskCheckpoint, TaskStateMachine, TaskStatus
from core.events import get_event_bus
from core.events.models import Event, EventPriority
from core.structured_logging import get_logger, log_structured
import logging

logger = get_logger(__name__)


# =============================================================================
# Checkpoint Manager
# =============================================================================

@dataclass
class CheckpointConfig:
    """Configuration for checkpoint manager."""
    interval_seconds: int = 30
    max_checkpoints_per_task: int = 100
    persistence_path: str = "./data/checkpoints"
    auto_cleanup: bool = True
    cleanup_interval_hours: int = 24


class CheckpointManager:
    """
    Manages task checkpoints for resume capability.

    Features:
    - Interval-based automatic checkpointing
    - Manual checkpoint triggers
    - Task state + step outputs persistence
    - Resume from last checkpoint
    - Automatic cleanup of old checkpoints
    """

    def __init__(self, config: Optional[CheckpointConfig] = None):
        self.config = config or CheckpointConfig()
        self._checkpoints: Dict[str, List[TaskCheckpoint]] = {}  # task_id -> checkpoints
        self._checkpoint_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False

    async def initialize(self) -> None:
        """Initialize checkpoint manager."""
        os.makedirs(self.config.persistence_path, exist_ok=True)
        await self._load_checkpoints()
        self._running = True

        # Start periodic checkpoint task
        self._checkpoint_task = asyncio.create_task(self._checkpoint_loop())

        # Start cleanup task
        if self.config.auto_cleanup:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

        log_structured(logger, logging.INFO, "Checkpoint manager initialized")

    async def shutdown(self) -> None:
        """Shutdown checkpoint manager."""
        self._running = False

        if self._checkpoint_task:
            self._checkpoint_task.cancel()
            try:
                await self._checkpoint_task
            except asyncio.CancelledError:
                pass

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        # Save all checkpoints
        await self._save_all_checkpoints()
        log_structured(logger, logging.INFO, "Checkpoint manager shutdown")

    # =========================================================================
    # Checkpoint Operations
    # =========================================================================

    def create_checkpoint(
        self,
        task: Task,
        step_index: Optional[int] = None,
        trigger: str = "auto",
    ) -> TaskCheckpoint:
        """
        Create a checkpoint for a task.

        Args:
            task: Task to checkpoint
            step_index: Current step index (defaults to task.current_step_index)
            trigger: What triggered this checkpoint (auto, manual, pre_wait, etc.)

        Returns:
            Created checkpoint
        """
        if step_index is None:
            step_index = task.current_step_index

        # Collect step statuses
        step_statuses = {}
        step_results = {}
        for i, step in enumerate(task.steps):
            step_statuses[step.step_id] = step.status
            if step.result:
                step_results[step.step_id] = step.result

        # Collect variables from task metadata
        variables = {
            "current_step_index": task.current_step_index,
            "priority": task.priority.value,
            "resource_limits": task.resource_limits.to_dict(),
            "tags": task.tags,
            "metadata": task.metadata,
            "correlation_id": task.correlation_id,
            "trace_id": task.trace_id,
        }

        checkpoint = TaskCheckpoint(
            checkpoint_id=str(uuid.uuid4())[:12],
            task_id=task.task_id,
            step_index=step_index,
            task_status=task.status,
            step_statuses=step_statuses,
            step_results=step_results,
            variables=variables,
            created_at=datetime.now(timezone.utc),
        )

        # Store in memory
        if task.task_id not in self._checkpoints:
            self._checkpoints[task.task_id] = []
        self._checkpoints[task.task_id].append(checkpoint)

        # Enforce max checkpoints per task
        if len(self._checkpoints[task.task_id]) > self.config.max_checkpoints_per_task:
            self._checkpoints[task.task_id] = self._checkpoints[task.task_id][
                -self.config.max_checkpoints_per_task :
            ]

        # Add to task's checkpoint list
        task.checkpoints.append(checkpoint)

        # Persist immediately for critical checkpoints
        if trigger in ("pre_wait", "manual", "pre_delegate"):
            asyncio.create_task(self._save_checkpoint(task.task_id, checkpoint))

        log_structured(
            logger, logging.DEBUG,
            "Checkpoint created",
            task_id=task.task_id,
            checkpoint_id=checkpoint.checkpoint_id,
            step_index=step_index,
            trigger=trigger,
        )

        return checkpoint

    def get_latest_checkpoint(self, task_id: str) -> Optional[TaskCheckpoint]:
        """Get the most recent checkpoint for a task."""
        checkpoints = self._checkpoints.get(task_id, [])
        return checkpoints[-1] if checkpoints else None

    def get_checkpoints(self, task_id: str) -> List[TaskCheckpoint]:
        """Get all checkpoints for a task."""
        return self._checkpoints.get(task_id, [])

    def restore_from_checkpoint(self, task: Task, checkpoint: TaskCheckpoint) -> bool:
        """
        Restore task state from a checkpoint.

        Args:
            task: Task to restore
            checkpoint: Checkpoint to restore from

        Returns:
            True if restore successful
        """
        try:
            # Restore task status
            TaskStateMachine.transition(task, checkpoint.task_status, force=True)

            # Restore step statuses and results
            for step in task.steps:
                if step.step_id in checkpoint.step_statuses:
                    step.status = checkpoint.step_statuses[step.step_id]
                if step.step_id in checkpoint.step_results:
                    step.result = checkpoint.step_results[step.step_id]

            # Restore variables
            task.current_step_index = checkpoint.variables.get("current_step_index", 0)
            task.priority = task.priority.__class__(checkpoint.variables.get("priority", 5))
            task.tags = checkpoint.variables.get("tags", [])
            task.metadata = checkpoint.variables.get("metadata", {})
            task.correlation_id = checkpoint.variables.get("correlation_id")
            task.trace_id = checkpoint.variables.get("trace_id")

            # Restore resource limits if present
            if "resource_limits" in checkpoint.variables:
                from core.task_engine.models import ResourceLimits
                task.resource_limits = ResourceLimits.from_dict(
                    checkpoint.variables["resource_limits"]
                )

            # Update task timestamps
            task.updated_at = datetime.now(timezone.utc)

            log_structured(
                logger, logging.INFO,
                "Task restored from checkpoint",
                task_id=task.task_id,
                checkpoint_id=checkpoint.checkpoint_id,
                step_index=checkpoint.step_index,
            )

            return True

        except Exception as e:
            log_structured(
                logger, logging.ERROR,
                "Failed to restore from checkpoint",
                task_id=task.task_id,
                checkpoint_id=checkpoint.checkpoint_id,
                error=str(e),
            )
            return False

    def restore_latest(self, task: Task) -> Optional[TaskCheckpoint]:
        """Restore task from its latest checkpoint."""
        checkpoint = self.get_latest_checkpoint(task.task_id)
        if checkpoint:
            success = self.restore_from_checkpoint(task, checkpoint)
            return checkpoint if success else None
        return None

    def delete_checkpoints(self, task_id: str) -> int:
        """Delete all checkpoints for a task."""
        count = len(self._checkpoints.get(task_id, []))
        if task_id in self._checkpoints:
            del self._checkpoints[task_id]

        # Also delete from disk
        filepath = os.path.join(self.config.persistence_path, f"{task_id}.json")
        if os.path.exists(filepath):
            os.remove(filepath)

        log_structured(logger, logging.INFO, "Checkpoints deleted", task_id=task_id, count=count)
        return count

    # =========================================================================
    # Periodic Checkpointing
    # =========================================================================

    async def _checkpoint_loop(self) -> None:
        """Periodic checkpoint loop for active tasks."""
        while self._running:
            try:
                await asyncio.sleep(self.config.interval_seconds)

                # Checkpoint all active tasks
                # This would be called by the task engine for running tasks
                # For now, we just ensure periodic persistence
                await self._save_all_checkpoints()

            except asyncio.CancelledError:
                break
            except Exception as e:
                log_structured(logger, logging.ERROR, "Checkpoint loop error", error=str(e))

    async def _save_all_checkpoints(self) -> None:
        """Save all checkpoints to disk."""
        for task_id, checkpoints in self._checkpoints.items():
            if checkpoints:
                await self._save_checkpoint(task_id, checkpoints[-1])

    async def _save_checkpoint(self, task_id: str, checkpoint: TaskCheckpoint) -> None:
        """Save a single checkpoint to disk."""
        try:
            filepath = os.path.join(self.config.persistence_path, f"{task_id}.json")

            # Load existing data
            data = {"checkpoints": []}
            if os.path.exists(filepath):
                with open(filepath, "r") as f:
                    data = json.load(f)

            # Add/update checkpoint
            cp_data = checkpoint.to_dict()
            # Replace if exists, otherwise append
            existing_idx = next(
                (i for i, c in enumerate(data["checkpoints"]) if c["checkpoint_id"] == checkpoint.checkpoint_id),
                None,
            )
            if existing_idx is not None:
                data["checkpoints"][existing_idx] = cp_data
            else:
                data["checkpoints"].append(cp_data)

            # Enforce max checkpoints
            if len(data["checkpoints"]) > self.config.max_checkpoints_per_task:
                data["checkpoints"] = data["checkpoints"][
                    -self.config.max_checkpoints_per_task :
                ]

            # Write atomically
            temp_path = filepath + ".tmp"
            with open(temp_path, "w") as f:
                json.dump(data, f, indent=2)
            os.replace(temp_path, filepath)

        except Exception as e:
            log_structured(logger, logging.ERROR, "Failed to save checkpoint", task_id=task_id, error=str(e))

    async def _load_checkpoints(self) -> None:
        """Load checkpoints from disk."""
        try:
            for filename in os.listdir(self.config.persistence_path):
                if not filename.endswith(".json"):
                    continue

                task_id = filename[:-5]  # Remove .json
                filepath = os.path.join(self.config.persistence_path, filename)

                with open(filepath, "r") as f:
                    data = json.load(f)

                checkpoints = [
                    TaskCheckpoint.from_dict(cp) for cp in data.get("checkpoints", [])
                ]
                if checkpoints:
                    self._checkpoints[task_id] = checkpoints

            log_structured(
                logger, logging.INFO,
                "Checkpoints loaded",
                task_count=len(self._checkpoints),
                total_checkpoints=sum(len(c) for c in self._checkpoints.values()),
            )

        except Exception as e:
            log_structured(logger, logging.ERROR, "Failed to load checkpoints", error=str(e))

    # =========================================================================
    # Cleanup
    # =========================================================================

    async def _cleanup_loop(self) -> None:
        """Periodic cleanup of old checkpoints."""
        while self._running:
            try:
                await asyncio.sleep(self.config.cleanup_interval_hours * 3600)
                await self._cleanup_old_checkpoints()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log_structured(logger, logging.ERROR, "Cleanup loop error", error=str(e))

    async def _cleanup_old_checkpoints(self) -> None:
        """Remove checkpoints for completed/failed tasks older than threshold."""
        # This would need task status info - for now just clean empty dirs
        # In practice, the task engine would call delete_checkpoints on task completion
        pass


# =============================================================================
# Global Instance
# =============================================================================

_checkpoint_manager: Optional[CheckpointManager] = None


def get_checkpoint_manager() -> Optional[CheckpointManager]:
    """Get the global checkpoint manager instance."""
    return _checkpoint_manager


def init_checkpoint_manager(config: Optional[CheckpointConfig] = None) -> CheckpointManager:
    """Initialize the global checkpoint manager."""
    global _checkpoint_manager
    _checkpoint_manager = CheckpointManager(config)
    return _checkpoint_manager


async def shutdown_checkpoint_manager() -> None:
    """Shutdown the global checkpoint manager."""
    global _checkpoint_manager
    if _checkpoint_manager:
        await _checkpoint_manager.shutdown()
        _checkpoint_manager = None


# =============================================================================
# Export
# =============================================================================

__all__ = [
    "CheckpointManager",
    "CheckpointConfig",
    "get_checkpoint_manager",
    "init_checkpoint_manager",
    "shutdown_checkpoint_manager",
]