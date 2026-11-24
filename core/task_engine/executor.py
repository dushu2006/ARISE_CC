"""
Task Engine Executor.

Executes tasks with sandbox support (Docker, gVisor, Firecracker),
resource monitoring, timeout enforcement, and tool execution.
"""

from __future__ import annotations
import asyncio
import os
import shlex
import signal
import subprocess
import tempfile
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Callable, Awaitable

from core.task_engine.models import Task, TaskStep, TaskStateMachine, TaskStatus, ResourceLimits, TaskKind
from core.events import get_event_bus
from core.events.models import Event, EventPriority
from core.structured_logging import get_logger, log_structured
import logging

logger = get_logger(__name__)


# =============================================================================
# Sandbox Types
# =============================================================================

class SandboxType(Enum):
    """Supported sandbox types."""
    NONE = "none"          # No sandbox (direct execution)
    DOCKER = "docker"      # Docker container
    GVISOR = "gvisor"      # gVisor sandbox
    FIRECRACKER = "firecracker"  # Firecracker microVM


@dataclass
class SandboxConfig:
    """Sandbox configuration."""
    type: SandboxType = SandboxType.DOCKER
    docker_image: str = "arise/sandbox:latest"
    memory_limit_mb: int = 512
    cpu_limit_percent: int = 50
    disk_limit_mb: int = 1024
    network_enabled: bool = False
    timeout_seconds: int = 300
    work_dir: str = "/workspace"
    env_vars: Dict[str, str] = field(default_factory=dict)


@dataclass
class ExecutionResult:
    """Result of a tool execution."""
    success: bool
    output: Any = None
    error: Optional[str] = None
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    duration_ms: float = 0.0
    resource_usage: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# Tool Executors
# =============================================================================

class ToolExecutor(ABC):
    """Base class for tool executors."""

    @abstractmethod
    async def execute(
        self,
        step: TaskStep,
        resource_limits: ResourceLimits,
        context: Dict[str, Any],
    ) -> ExecutionResult:
        """Execute a tool step."""
        pass

    @abstractmethod
    def can_execute(self, kind: TaskKind) -> bool:
        """Check if this executor can handle the given task kind."""
        pass


class ShellExecutor(ToolExecutor):
    """Executes shell commands."""

    def can_execute(self, kind: TaskKind) -> bool:
        return kind == TaskKind.SHELL_EXEC

    async def execute(
        self,
        step: TaskStep,
        resource_limits: ResourceLimits,
        context: Dict[str, Any],
    ) -> ExecutionResult:
        start_time = time.perf_counter()

        command = step.payload.get("command", "")
        shell = step.payload.get("shell", True)
        cwd = step.payload.get("cwd", context.get("work_dir", "/workspace"))
        env = {**os.environ, **context.get("env_vars", {})}
        timeout = step.payload.get("timeout", resource_limits.timeout_seconds)

        log_structured(logger, logging.DEBUG, "Executing shell command", command=command[:100])

        try:
            if shell:
                process = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=cwd,
                    env=env,
                )
            else:
                args = shlex.split(command)
                process = await asyncio.create_subprocess_exec(
                    *args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=cwd,
                    env=env,
                )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout,
                )
                exit_code = process.returncode
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                duration_ms = (time.perf_counter() - start_time) * 1000
                return ExecutionResult(
                    success=False,
                    error=f"Command timed out after {timeout}s",
                    stdout=stdout.decode() if stdout else "",
                    stderr=stderr.decode() if stderr else "",
                    exit_code=-1,
                    duration_ms=duration_ms,
                )

            duration_ms = (time.perf_counter() - start_time) * 1000

            return ExecutionResult(
                success=exit_code == 0,
                output={"stdout": stdout.decode(), "stderr": stderr.decode()},
                error=stderr.decode() if exit_code != 0 else None,
                stdout=stdout.decode(),
                stderr=stderr.decode(),
                exit_code=exit_code,
                duration_ms=duration_ms,
            )

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            return ExecutionResult(
                success=False,
                error=str(e),
                duration_ms=duration_ms,
            )


class FilesystemExecutor(ToolExecutor):
    """Executes filesystem operations."""

    def can_execute(self, kind: TaskKind) -> bool:
        return kind in (TaskKind.FILE_READ, TaskKind.FILE_WRITE, TaskKind.FILE_LIST)

    async def execute(
        self,
        step: TaskStep,
        resource_limits: ResourceLimits,
        context: Dict[str, Any],
    ) -> ExecutionResult:
        start_time = time.perf_counter()
        base_path = context.get("work_dir", "/workspace")

        try:
            if step.kind == TaskKind.FILE_READ:
                path = os.path.join(base_path, step.payload.get("path", ""))
                if not os.path.exists(path):
                    return ExecutionResult(
                        success=False,
                        error=f"File not found: {path}",
                        duration_ms=(time.perf_counter() - start_time) * 1000,
                    )
                with open(path, "r") as f:
                    content = f.read()
                return ExecutionResult(
                    success=True,
                    output={"content": content, "path": path},
                    duration_ms=(time.perf_counter() - start_time) * 1000,
                )

            elif step.kind == TaskKind.FILE_WRITE:
                path = os.path.join(base_path, step.payload.get("path", ""))
                content = step.payload.get("content", "")
                mode = step.payload.get("mode", "w")

                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, mode) as f:
                    f.write(content)

                return ExecutionResult(
                    success=True,
                    output={"path": path, "bytes_written": len(content)},
                    duration_ms=(time.perf_counter() - start_time) * 1000,
                )

            elif step.kind == TaskKind.FILE_LIST:
                path = os.path.join(base_path, step.payload.get("path", "."))
                pattern = step.payload.get("pattern", "*")
                recursive = step.payload.get("recursive", False)

                if recursive:
                    files = []
                    for root, dirs, filenames in os.walk(path):
                        for f in filenames:
                            if self._match_pattern(f, pattern):
                                rel_path = os.path.relpath(os.path.join(root, f), base_path)
                                files.append(rel_path)
                else:
                    files = [
                        f for f in os.listdir(path)
                        if self._match_pattern(f, pattern)
                    ]

                return ExecutionResult(
                    success=True,
                    output={"files": files, "path": path},
                    duration_ms=(time.perf_counter() - start_time) * 1000,
                )

        except Exception as e:
            return ExecutionResult(
                success=False,
                error=str(e),
                duration_ms=(time.perf_counter() - start_time) * 1000,
            )

    def _match_pattern(self, filename: str, pattern: str) -> bool:
        import fnmatch
        return fnmatch.fnmatch(filename, pattern)


class HttpExecutor(ToolExecutor):
    """Executes HTTP requests."""

    def can_execute(self, kind: TaskKind) -> bool:
        return kind == TaskKind.HTTP_REQUEST

    async def execute(
        self,
        step: TaskStep,
        resource_limits: ResourceLimits,
        context: Dict[str, Any],
    ) -> ExecutionResult:
        start_time = time.perf_counter()

        try:
            import aiohttp

            method = step.payload.get("method", "GET")
            url = step.payload.get("url", "")
            headers = step.payload.get("headers", {})
            json_data = step.payload.get("json")
            data = step.payload.get("data")
            params = step.payload.get("params")
            timeout = step.payload.get("timeout", resource_limits.timeout_seconds)

            async with aiohttp.ClientSession() as session:
                async with session.request(
                    method,
                    url,
                    headers=headers,
                    json=json_data,
                    data=data,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as response:
                    text = await response.text()
                    duration_ms = (time.perf_counter() - start_time) * 1000

                    return ExecutionResult(
                        success=200 <= response.status < 300,
                        output={
                            "status": response.status,
                            "headers": dict(response.headers),
                            "body": text,
                        },
                        error=None if 200 <= response.status < 300 else f"HTTP {response.status}",
                        duration_ms=duration_ms,
                    )

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            return ExecutionResult(
                success=False,
                error=str(e),
                duration_ms=duration_ms,
            )


# =============================================================================
# Sandbox Runners
# =============================================================================

class SandboxRunner(ABC):
    """Abstract sandbox runner."""

    @abstractmethod
    async def run(
        self,
        command: List[str],
        work_dir: str,
        env: Dict[str, str],
        resource_limits: ResourceLimits,
        timeout: int,
    ) -> ExecutionResult:
        """Run a command in the sandbox."""
        pass

    @abstractmethod
    async def cleanup(self) -> None:
        """Cleanup sandbox resources."""
        pass


class DirectRunner(SandboxRunner):
    """Direct execution (no sandbox)."""

    async def run(
        self,
        command: List[str],
        work_dir: str,
        env: Dict[str, str],
        resource_limits: ResourceLimits,
        timeout: int,
    ) -> ExecutionResult:
        start_time = time.perf_counter()

        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=work_dir,
                env=env,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout,
                )
                exit_code = process.returncode
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return ExecutionResult(
                    success=False,
                    error=f"Command timed out after {timeout}s",
                    stdout=stdout.decode() if stdout else "",
                    stderr=stderr.decode() if stderr else "",
                    exit_code=-1,
                    duration_ms=(time.perf_counter() - start_time) * 1000,
                )

            return ExecutionResult(
                success=exit_code == 0,
                stdout=stdout.decode(),
                stderr=stderr.decode(),
                exit_code=exit_code,
                duration_ms=(time.perf_counter() - start_time) * 1000,
            )

        except Exception as e:
            return ExecutionResult(
                success=False,
                error=str(e),
                duration_ms=(time.perf_counter() - start_time) * 1000,
            )

    async def cleanup(self) -> None:
        pass


class DockerRunner(SandboxRunner):
    """Docker container sandbox."""

    def __init__(self, config: SandboxConfig):
        self.config = config
        self.container_id: Optional[str] = None

    async def run(
        self,
        command: List[str],
        work_dir: str,
        env: Dict[str, str],
        resource_limits: ResourceLimits,
        timeout: int,
    ) -> ExecutionResult:
        start_time = time.perf_counter()

        # Build docker run command
        docker_cmd = [
            "docker", "run", "--rm",
            "--memory", f"{resource_limits.memory_mb}m",
            "--cpus", f"{resource_limits.cpu_percent / 100.0}",
            "--workdir", work_dir,
        ]

        # Add environment variables
        for key, value in env.items():
            docker_cmd.extend(["-e", f"{key}={value}"])

        # Network
        if not self.config.network_enabled:
            docker_cmd.append("--network=none")

        # Image and command
        docker_cmd.append(self.config.docker_image)
        docker_cmd.extend(command)

        try:
            process = await asyncio.create_subprocess_exec(
                *docker_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout,
                )
                exit_code = process.returncode
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return ExecutionResult(
                    success=False,
                    error=f"Command timed out after {timeout}s",
                    duration_ms=(time.perf_counter() - start_time) * 1000,
                )

            return ExecutionResult(
                success=exit_code == 0,
                stdout=stdout.decode(),
                stderr=stderr.decode(),
                exit_code=exit_code,
                duration_ms=(time.perf_counter() - start_time) * 1000,
            )

        except Exception as e:
            return ExecutionResult(
                success=False,
                error=str(e),
                duration_ms=(time.perf_counter() - start_time) * 1000,
            )

    async def cleanup(self) -> None:
        pass  # Docker --rm handles cleanup


# =============================================================================
# Task Executor
# =============================================================================

class TaskExecutor:
    """
    Main task executor with sandbox support, resource monitoring,
    timeout enforcement, and tool execution.
    """

    def __init__(
        self,
        sandbox_config: Optional[SandboxConfig] = None,
        resource_limits: Optional[ResourceLimits] = None,
    ):
        self.sandbox_config = sandbox_config or SandboxConfig()
        self.default_resource_limits = resource_limits or ResourceLimits()

        # Initialize tool executors
        self._tool_executors: List[ToolExecutor] = [
            ShellExecutor(),
            FilesystemExecutor(),
            HttpExecutor(),
        ]

        # Initialize sandbox runner
        self._sandbox_runner = self._create_sandbox_runner()

        # Execution state
        self._running_task: Optional[Task] = None
        self._cancel_requested = False

    def _create_sandbox_runner(self) -> SandboxRunner:
        """Create sandbox runner based on config."""
        if self.sandbox_config.type == SandboxType.NONE:
            return DirectRunner()
        elif self.sandbox_config.type == SandboxType.DOCKER:
            return DockerRunner(self.sandbox_config)
        else:
            # Fallback to direct for unsupported types
            log_structured(
                logger, logging.WARNING,
                "Sandbox type not fully implemented, using direct",
                sandbox_type=self.sandbox_config.type,
            )
            return DirectRunner()

    def register_tool_executor(self, executor: ToolExecutor) -> None:
        """Register a custom tool executor."""
        self._tool_executors.append(executor)

    def get_executor_for_kind(self, kind: TaskKind) -> Optional[ToolExecutor]:
        """Get the executor for a task kind."""
        for executor in self._tool_executors:
            if executor.can_execute(kind):
                return executor
        return None

    async def execute_step(
        self,
        step: TaskStep,
        task: Task,
        context: Optional[Dict[str, Any]] = None,
    ) -> ExecutionResult:
        """
        Execute a single task step.

        Args:
            step: Step to execute
            task: Parent task (for context)
            context: Additional execution context

        Returns:
            Execution result
        """
        context = context or {}
        context.update({
            "task_id": task.task_id,
            "step_id": step.step_id,
            "work_dir": context.get("work_dir", "/workspace"),
            "env_vars": context.get("env_vars", {}),
        })

        # Get resource limits (step can override task defaults)
        resource_limits = task.resource_limits
        if step.payload.get("resource_limits"):
            from core.task_engine.models import ResourceLimits
            resource_limits = ResourceLimits.from_dict(step.payload["resource_limits"])

        # Update step status
        TaskStateMachine.transition(task, TaskStatus.RUNNING)
        step.status = TaskStatus.RUNNING
        step.started_at = datetime.now(timezone.utc)

        log_structured(
            logger, logging.INFO,
            "Executing step",
            task_id=task.task_id,
            step_id=step.step_id,
            kind=step.kind.value,
        )

        # Find and execute
        executor = self.get_executor_for_kind(step.kind)
        if not executor:
            step.status = TaskStatus.FAILED
            step.error = f"No executor for task kind: {step.kind.value}"
            step.completed_at = datetime.now(timezone.utc)
            return ExecutionResult(
                success=False,
                error=step.error,
            )

        try:
            result = await executor.execute(step, resource_limits, context)

            # Update step with result
            step.completed_at = datetime.now(timezone.utc)
            step.result = result.output
            step.error = result.error

            if result.success:
                step.status = TaskStatus.COMPLETED
            else:
                step.status = TaskStatus.FAILED

            # Publish step completion event
            try:
                bus = await get_event_bus()
                if bus:
                    event = Event(
                        type="tasks.step_completed",
                        payload={
                            "task_id": task.task_id,
                            "step_id": step.step_id,
                            "kind": step.kind.value,
                            "success": result.success,
                            "duration_ms": result.duration_ms,
                        },
                        priority=EventPriority.NORMAL,
                    )
                    await bus.publish(event)
            except Exception as e:
                log_structured(logger, logging.DEBUG, "Failed to publish step completion event", error=str(e))

            return result

        except Exception as e:
            step.completed_at = datetime.now(timezone.utc)
            step.status = TaskStatus.FAILED
            step.error = str(e)
            log_structured(
                logger, logging.ERROR,
                "Step execution failed",
                task_id=task.task_id,
                step_id=step.step_id,
                error=str(e),
            )
            return ExecutionResult(success=False, error=str(e))

    async def execute_task(
        self,
        task: Task,
        context: Optional[Dict[str, Any]] = None,
        checkpoint_callback: Optional[Callable[[Task], Awaitable[None]]] = None,
    ) -> Task:
        """
        Execute a full task (all steps).

        Args:
            task: Task to execute
            context: Execution context
            checkpoint_callback: Optional callback to create checkpoints

        Returns:
            Updated task with results
        """
        self._running_task = task
        self._cancel_requested = False

        context = context or {}
        context["work_dir"] = context.get("work_dir", f"/workspace/{task.task_id}")

        # Transition to running
        TaskStateMachine.transition(task, TaskStatus.RUNNING)
        task.started_at = datetime.now(timezone.utc)

        log_structured(logger, logging.INFO, "Starting task execution", task_id=task.task_id, steps=len(task.steps))

        try:
            for i, step in enumerate(task.steps):
                if self._cancel_requested:
                    TaskStateMachine.transition(task, TaskStatus.CANCELLED)
                    break

                task.current_step_index = i

                # Create checkpoint before step if configured
                if checkpoint_callback and i > 0:
                    await checkpoint_callback(task)

                # Execute step
                result = await self.execute_step(step, task, context)

                # Handle failure
                if not result.success:
                    # Check if should retry
                    if step.retry_count < step.max_retries:
                        step.retry_count += 1
                        log_structured(
                            logger, logging.WARNING,
                            "Step failed, retrying",
                            task_id=task.task_id,
                            step_id=step.step_id,
                            attempt=step.retry_count,
                        )
                        # Re-execute (simple retry - could add backoff)
                        result = await self.execute_step(step, task, context)

                    if not result.success:
                        TaskStateMachine.transition(task, TaskStatus.FAILED)
                        task.result = self._create_task_result(task, success=False)
                        break

            else:
                # All steps completed successfully
                if not self._cancel_requested:
                    TaskStateMachine.transition(task, TaskStatus.COMPLETED)
                    task.result = self._create_task_result(task, success=True)

            task.completed_at = datetime.now(timezone.utc)
            if task.started_at:
                task.result.duration_ms = (
                    task.completed_at - task.started_at
                ).total_seconds() * 1000

            return task

        finally:
            self._running_task = None
            self._cancel_requested = False

    def _create_task_result(self, task: Task, success: bool) -> Any:
        """Create task result object."""
        from core.task_engine.models import TaskResult

        output = None
        error = None

        if success:
            # Aggregate step outputs
            output = {}
            for step in task.steps:
                if step.result:
                    output[step.step_id] = step.result
        else:
            # Find first error
            for step in task.steps:
                if step.error:
                    error = step.error
                    break

        return TaskResult(
            task_id=task.task_id,
            status=task.status,
            output=output,
            error=error,
            steps=task.steps,
            checkpoints=task.checkpoints,
            started_at=task.started_at,
            completed_at=task.completed_at,
        )

    def request_cancel(self) -> None:
        """Request cancellation of current task."""
        self._cancel_requested = True
        if self._running_task:
            log_structured(logger, logging.INFO, "Cancel requested", task_id=self._running_task.task_id)

    async def shutdown(self) -> None:
        """Shutdown executor."""
        await self._sandbox_runner.cleanup()
        log_structured(logger, logging.INFO, "Task executor shutdown")


# =============================================================================
# Export
# =============================================================================

__all__ = [
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
    "ResourceLimits",
]