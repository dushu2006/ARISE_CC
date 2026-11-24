"""
Task Engine Package.

Main exports for the task engine subsystem.
"""

from core.task_engine.models import (
    Task,
    TaskStep,
    TaskCheckpoint,
    TaskResult,
    TaskKind,
    TaskPriority,
    TaskStatus,
    ResourceLimits,
    TaskStateMachine,
)

from core.task_engine.state_machine import (
    AdvancedTaskStateMachine,
    TransitionEvent,
    TransitionType,
    default_state_machine,
    transition_task,
    validate_transition,
    generate_mermaid_diagram,
)

from core.task_engine.queue import (
    TaskQueue,
    QueueEntry,
    get_task_queue,
    init_task_queue,
    shutdown_task_queue,
)

from core.task_engine.checkpoint import (
    CheckpointManager,
    CheckpointConfig,
    get_checkpoint_manager,
    init_checkpoint_manager,
    shutdown_checkpoint_manager,
)

from core.task_engine.executor import (
    TaskExecutor,
    ToolExecutor,
    ShellExecutor,
    FilesystemExecutor,
    HttpExecutor,
    SandboxRunner,
    DirectRunner,
    DockerRunner,
    SandboxConfig,
    SandboxType,
    ExecutionResult,
)

from core.task_engine.engine import (
    TaskEngine,
    TaskEngineConfig,
    get_task_engine,
    init_task_engine,
    shutdown_task_engine,
)

from core.task_engine.kinds import (
    create_step_from_kind,
    create_task_from_kind,
    create_shell_task,
    create_file_read_task,
    create_file_write_task,
    create_file_list_task,
    create_http_task,
    create_browser_navigate_task,
    create_browser_click_task,
    create_browser_extract_task,
    create_uia_find_task,
    create_uia_click_task,
    create_uia_input_task,
    create_memory_store_task,
    create_memory_query_task,
    create_agent_delegate_task,
    create_agent_verify_task,
)

__all__ = [
    # Models
    "Task",
    "TaskStep",
    "TaskCheckpoint",
    "TaskResult",
    "TaskKind",
    "TaskPriority",
    "TaskStatus",
    "ResourceLimits",
    "TaskStateMachine",
    # State Machine
    "AdvancedTaskStateMachine",
    "TransitionEvent",
    "TransitionType",
    "default_state_machine",
    "transition_task",
    "validate_transition",
    "generate_mermaid_diagram",
    # Queue
    "TaskQueue",
    "QueueEntry",
    "get_task_queue",
    "init_task_queue",
    "shutdown_task_queue",
    # Checkpoint
    "CheckpointManager",
    "CheckpointConfig",
    "get_checkpoint_manager",
    "init_checkpoint_manager",
    "shutdown_checkpoint_manager",
    # Executor
    "TaskExecutor",
    "ToolExecutor",
    "ShellExecutor",
    "FilesystemExecutor",
    "HttpExecutor",
    "SandboxRunner",
    "DirectRunner",
    "DockerRunner",
    "SandboxConfig",
    "SandboxType",
    "ExecutionResult",
    # Engine
    "TaskEngine",
    "TaskEngineConfig",
    "get_task_engine",
    "init_task_engine",
    "shutdown_task_engine",
    # Kinds
    "create_step_from_kind",
    "create_task_from_kind",
    "create_shell_task",
    "create_file_read_task",
    "create_file_write_task",
    "create_file_list_task",
    "create_http_task",
    "create_browser_navigate_task",
    "create_browser_click_task",
    "create_browser_extract_task",
    "create_uia_find_task",
    "create_uia_click_task",
    "create_uia_input_task",
    "create_memory_store_task",
    "create_memory_query_task",
    "create_agent_delegate_task",
    "create_agent_verify_task",
]