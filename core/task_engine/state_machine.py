"""
Task Engine State Machine.

Dedicated state machine module with advanced features:
- Transition validation with detailed error messages
- State entry/exit hooks
- Transition history tracking
- Visualization support (Mermaid/GraphViz)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Dict, List, Optional, Set

from core.task_engine.models import Task, TaskStateMachine, TaskStatus


# =============================================================================
# Transition Events
# =============================================================================

class TransitionType(Enum):
    """Type of transition."""
    NORMAL = "normal"
    FORCED = "forced"  # Admin override
    TIMEOUT = "timeout"
    ERROR = "error"
    CANCELLATION = "cancellation"


@dataclass
class TransitionEvent:
    """Record of a state transition."""
    from_state: TaskStatus
    to_state: TaskStatus
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    transition_type: TransitionType = TransitionType.NORMAL
    reason: str = ""
    metadata: Dict[str, any] = field(default_factory=dict)


# =============================================================================
# Advanced State Machine
# =============================================================================

class AdvancedTaskStateMachine:
    """
    Advanced task state machine with hooks, history, and validation.
    """

    def __init__(self):
        self._entry_hooks: Dict[TaskStatus, List[Callable[[Task], None]]] = {}
        self._exit_hooks: Dict[TaskStatus, List[Callable[[Task], None]]] = {}
        self._transition_hooks: List[Callable[[Task, TaskStatus, TaskStatus], None]] = []

    def register_entry_hook(self, state: TaskStatus, hook: Callable[[Task], None]) -> None:
        """Register a hook to run when entering a state."""
        if state not in self._entry_hooks:
            self._entry_hooks[state] = []
        self._entry_hooks[state].append(hook)

    def register_exit_hook(self, state: TaskStatus, hook: Callable[[Task], None]) -> None:
        """Register a hook to run when exiting a state."""
        if state not in self._exit_hooks:
            self._exit_hooks[state] = []
        self._exit_hooks[state].append(hook)

    def register_transition_hook(
        self, hook: Callable[[Task, TaskStatus, TaskStatus], None]
    ) -> None:
        """Register a hook to run on any transition."""
        self._transition_hooks.append(hook)

    def _run_entry_hooks(self, task: Task, state: TaskStatus) -> None:
        """Run all entry hooks for a state."""
        for hook in self._entry_hooks.get(state, []):
            try:
                hook(task)
            except Exception as e:
                # Log but don't fail the transition
                import logging
                logging.getLogger(__name__).warning(
                    f"Entry hook failed for {state.value}: {e}"
                )

    def _run_exit_hooks(self, task: Task, state: TaskStatus) -> None:
        """Run all exit hooks for a state."""
        for hook in self._exit_hooks.get(state, []):
            try:
                hook(task)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(
                    f"Exit hook failed for {state.value}: {e}"
                )

    def _run_transition_hooks(
        self, task: Task, from_state: TaskStatus, to_state: TaskStatus
    ) -> None:
        """Run all transition hooks."""
        for hook in self._transition_hooks:
            try:
                hook(task, from_state, to_state)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(
                    f"Transition hook failed: {e}"
                )

    def transition(
        self,
        task: Task,
        new_status: TaskStatus,
        transition_type: TransitionType = TransitionType.NORMAL,
        reason: str = "",
        metadata: Optional[Dict[str, any]] = None,
        force: bool = False,
    ) -> TransitionEvent:
        """
        Perform a state transition with hooks and history.

        Args:
            task: The task to transition
            new_status: The new status
            transition_type: Type of transition
            reason: Reason for transition
            metadata: Additional metadata
            force: If True, bypass validation (admin use only)

        Returns:
            TransitionEvent recording the transition

        Raises:
            ValueError: If transition is invalid and not forced
        """
        old_status = task.status

        # Validate transition
        if not force and not TaskStateMachine.can_transition(old_status, new_status):
            valid = TaskStateMachine.get_valid_transitions(old_status)
            raise ValueError(
                f"Invalid transition from {old_status.value} to {new_status.value}. "
                f"Valid transitions: {[s.value for s in valid]}"
            )

        # Create transition event
        event = TransitionEvent(
            from_state=old_status,
            to_state=new_status,
            transition_type=transition_type,
            reason=reason,
            metadata=metadata or {},
        )

        # Run exit hooks for old state
        self._run_exit_hooks(task, old_status)

        # Run transition hooks
        self._run_transition_hooks(task, old_status, new_status)

        # Update task state
        task.status = new_status
        task.updated_at = datetime.now(timezone.utc)

        # Set timestamps for key transitions
        if new_status == TaskStatus.RUNNING and task.started_at is None:
            task.started_at = task.updated_at
        elif TaskStateMachine.is_terminal(new_status) and task.completed_at is None:
            task.completed_at = task.updated_at

        # Run entry hooks for new state
        self._run_entry_hooks(task, new_status)

        # Add to task history if available
        if hasattr(task, "transition_history"):
            task.transition_history.append(event)

        return event

    def can_transition(self, from_state: TaskStatus, to_state: TaskStatus) -> bool:
        """Check if transition is valid."""
        return TaskStateMachine.can_transition(from_state, to_state)

    def get_valid_transitions(self, state: TaskStatus) -> List[TaskStatus]:
        """Get valid transitions from a state."""
        return TaskStateMachine.get_valid_transitions(state)

    def is_terminal(self, state: TaskStatus) -> bool:
        """Check if state is terminal."""
        return TaskStateMachine.is_terminal(state)

    def is_waiting(self, state: TaskStatus) -> bool:
        """Check if state is a waiting state."""
        return TaskStateMachine.is_waiting(state)

    def get_reachable_states(self, from_state: TaskStatus, max_depth: int = 10) -> Set[TaskStatus]:
        """Get all states reachable from a given state."""
        reachable = set()
        visited = set()

        def dfs(state: TaskStatus, depth: int):
            if depth >= max_depth or state in visited:
                return
            visited.add(state)
            for next_state in TaskStateMachine.get_valid_transitions(state):
                reachable.add(next_state)
                dfs(next_state, depth + 1)

        dfs(from_state, 0)
        return reachable

    def find_path(self, from_state: TaskStatus, to_state: TaskStatus) -> Optional[List[TaskStatus]]:
        """Find a valid transition path between states (BFS)."""
        from collections import deque

        queue = deque([(from_state, [from_state])])
        visited = {from_state}

        while queue:
            current, path = queue.popleft()
            if current == to_state:
                return path

            for next_state in TaskStateMachine.get_valid_transitions(current):
                if next_state not in visited:
                    visited.add(next_state)
                    queue.append((next_state, path + [next_state]))

        return None


# =============================================================================
# Default Instance
# =============================================================================

# Global default state machine instance
default_state_machine = AdvancedTaskStateMachine()


# =============================================================================
# Convenience Functions
# =============================================================================

def transition_task(
    task: Task,
    new_status: TaskStatus,
    reason: str = "",
    force: bool = False,
) -> TransitionEvent:
    """Convenience function to transition a task using the default state machine."""
    return default_state_machine.transition(task, new_status, reason=reason, force=force)


def validate_transition(from_state: TaskStatus, to_state: TaskStatus) -> bool:
    """Validate a transition using the default state machine."""
    return default_state_machine.can_transition(from_state, to_state)


# =============================================================================
# Visualization
# =============================================================================

def generate_mermaid_diagram() -> str:
    """Generate Mermaid diagram for the state machine."""
    lines = [
        "stateDiagram-v2",
        "    [*] --> CREATED",
        "    CREATED --> QUEUED",
        "    CREATED --> UNDERSTANDING",
        "    CREATED --> CANCELLED",
        "    QUEUED --> UNDERSTANDING",
        "    QUEUED --> CANCELLED",
        "    QUEUED --> PAUSED",
        "    UNDERSTANDING --> PLANNING",
        "    UNDERSTANDING --> CANCELLED",
        "    UNDERSTANDING --> FAILED",
        "    UNDERSTANDING --> PAUSED",
        "    PLANNING --> READY",
        "    PLANNING --> CANCELLED",
        "    PLANNING --> FAILED",
        "    PLANNING --> PAUSED",
        "    READY --> RUNNING",
        "    READY --> CANCELLED",
        "    READY --> PAUSED",
        "    RUNNING --> WAITING_APPROVAL",
        "    RUNNING --> WAITING_TOOL",
        "    RUNNING --> WAITING_MODEL",
        "    RUNNING --> WAITING_RESOURCE",
        "    RUNNING --> WAITING_HUMAN",
        "    RUNNING --> WAITING_AGENT",
        "    RUNNING --> VERIFYING",
        "    RUNNING --> COMPLETED",
        "    RUNNING --> FAILED",
        "    RUNNING --> CANCELLED",
        "    RUNNING --> PAUSED",
        "    RUNNING --> RETRYING",
        "    RUNNING --> CHECKPOINTING",
        "    RUNNING --> DELEGATING",
        "    WAITING_APPROVAL --> RUNNING",
        "    WAITING_APPROVAL --> CANCELLED",
        "    WAITING_APPROVAL --> FAILED",
        "    WAITING_APPROVAL --> TIMEOUT",
        "    WAITING_APPROVAL --> PAUSED",
        "    WAITING_TOOL --> RUNNING",
        "    WAITING_TOOL --> CANCELLED",
        "    WAITING_TOOL --> FAILED",
        "    WAITING_TOOL --> TIMEOUT",
        "    WAITING_TOOL --> PAUSED",
        "    WAITING_MODEL --> RUNNING",
        "    WAITING_MODEL --> CANCELLED",
        "    WAITING_MODEL --> FAILED",
        "    WAITING_MODEL --> TIMEOUT",
        "    WAITING_MODEL --> PAUSED",
        "    WAITING_RESOURCE --> RUNNING",
        "    WAITING_RESOURCE --> CANCELLED",
        "    WAITING_RESOURCE --> FAILED",
        "    WAITING_RESOURCE --> TIMEOUT",
        "    WAITING_RESOURCE --> PAUSED",
        "    WAITING_HUMAN --> RUNNING",
        "    WAITING_HUMAN --> CANCELLED",
        "    WAITING_HUMAN --> FAILED",
        "    WAITING_HUMAN --> TIMEOUT",
        "    WAITING_HUMAN --> PAUSED",
        "    WAITING_AGENT --> RUNNING",
        "    WAITING_AGENT --> CANCELLED",
        "    WAITING_AGENT --> FAILED",
        "    WAITING_AGENT --> TIMEOUT",
        "    WAITING_AGENT --> PAUSED",
        "    VERIFYING --> COMPLETED",
        "    VERIFYING --> FAILED",
        "    VERIFYING --> RETRYING",
        "    VERIFYING --> CANCELLED",
        "    VERIFYING --> PAUSED",
        "    COMPLETED --> ARCHIVING",
        "    COMPLETED --> EXPIRED",
        "    FAILED --> RETRYING",
        "    FAILED --> CANCELLED",
        "    FAILED --> ARCHIVING",
        "    FAILED --> EXPIRED",
        "    CANCELLED --> ARCHIVING",
        "    CANCELLED --> EXPIRED",
        "    PAUSED --> RUNNING",
        "    PAUSED --> CANCELLED",
        "    PAUSED --> EXPIRED",
        "    RETRYING --> RUNNING",
        "    RETRYING --> FAILED",
        "    RETRYING --> CANCELLED",
        "    RETRYING --> PAUSED",
        "    CHECKPOINTING --> RUNNING",
        "    CHECKPOINTING --> FAILED",
        "    CHECKPOINTING --> CANCELLED",
        "    RESTORING --> RUNNING",
        "    RESTORING --> FAILED",
        "    RESTORING --> CANCELLED",
        "    DELEGATING --> RUNNING",
        "    DELEGATING --> AGGREGATING",
        "    DELEGATING --> FAILED",
        "    DELEGATING --> CANCELLED",
        "    DELEGATING --> PAUSED",
        "    AGGREGATING --> SYNTHESIZING",
        "    AGGREGATING --> FAILED",
        "    AGGREGATING --> CANCELLED",
        "    AGGREGATING --> PAUSED",
        "    SYNTHESIZING --> VALIDATING",
        "    SYNTHESIZING --> FAILED",
        "    SYNTHESIZING --> CANCELLED",
        "    SYNTHESIZING --> PAUSED",
        "    VALIDATING --> VERIFYING",
        "    VALIDATING --> FAILED",
        "    VALIDATING --> CANCELLED",
        "    VALIDATING --> PAUSED",
        "    ARCHIVING --> EXPIRED",
        "    TIMEOUT --> RETRYING",
        "    TIMEOUT --> FAILED",
        "    TIMEOUT --> CANCELLED",
        "    UNKNOWN --> CANCELLED",
        "    UNKNOWN --> FAILED",
        "    EXPIRED --> [*]",
    ]
    return "\n".join(f"    {line}" for line in lines)


# =============================================================================
# Export
# =============================================================================

__all__ = [
    "AdvancedTaskStateMachine",
    "TransitionEvent",
    "TransitionType",
    "default_state_machine",
    "transition_task",
    "validate_transition",
    "generate_mermaid_diagram",
]