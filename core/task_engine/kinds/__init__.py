"""
Task Engine Kinds - Factory Functions.

Creates task steps from task kind specifications.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional

from core.task_engine.models import Task, TaskStep, TaskKind, TaskPriority, TaskStatus, ResourceLimits


# =============================================================================
# Step Creation Functions
# =============================================================================

def create_step_from_kind(kind: TaskKind, payload: Dict[str, Any]) -> TaskStep:
    """
    Create a task step from a task kind and payload.

    Args:
        kind: The task kind
        payload: Task-specific payload

    Returns:
        Configured TaskStep
    """
    step = TaskStep(
        kind=kind,
        name=kind.value,
        payload=payload,
        status=TaskStatus.CREATED,
    )

    # Set kind-specific defaults
    if kind == TaskKind.SHELL_EXEC:
        step.name = "Shell Command"
        step.description = payload.get("description", "Execute shell command")
        step.payload.setdefault("shell", True)
        step.payload.setdefault("timeout", 300)

    elif kind == TaskKind.FILE_READ:
        step.name = "Read File"
        step.description = f"Read file: {payload.get('path', 'unknown')}"
        step.payload.setdefault("encoding", "utf-8")

    elif kind == TaskKind.FILE_WRITE:
        step.name = "Write File"
        step.description = f"Write file: {payload.get('path', 'unknown')}"
        step.payload.setdefault("mode", "w")

    elif kind == TaskKind.FILE_LIST:
        step.name = "List Files"
        step.description = f"List files in: {payload.get('path', '.')}"
        step.payload.setdefault("pattern", "*")
        step.payload.setdefault("recursive", False)

    elif kind == TaskKind.HTTP_REQUEST:
        step.name = "HTTP Request"
        step.description = f"{payload.get('method', 'GET')} {payload.get('url', 'unknown')}"
        step.payload.setdefault("method", "GET")
        step.payload.setdefault("timeout", 30)

    elif kind == TaskKind.BROWSER_NAVIGATE:
        step.name = "Browser Navigate"
        step.description = f"Navigate to: {payload.get('url', 'unknown')}"
        step.payload.setdefault("wait_until", "networkidle")

    elif kind == TaskKind.BROWSER_CLICK:
        step.name = "Browser Click"
        step.description = f"Click: {payload.get('selector', 'unknown')}"
        step.payload.setdefault("button", "left")

    elif kind == TaskKind.BROWSER_EXTRACT:
        step.name = "Browser Extract"
        step.description = f"Extract: {payload.get('selector', 'unknown')}"
        step.payload.setdefault("attribute", "textContent")

    elif kind == TaskKind.UIA_FIND:
        step.name = "UIA Find Element"
        step.description = f"Find: {payload.get('selector', 'unknown')}"
        step.payload.setdefault("timeout", 5000)

    elif kind == TaskKind.UIA_CLICK:
        step.name = "UIA Click"
        step.description = f"Click: {payload.get('selector', 'unknown')}"

    elif kind == TaskKind.UIA_INPUT:
        step.name = "UIA Input Text"
        step.description = f"Input: {payload.get('text', '')[:50]}"
        step.payload.setdefault("clear_first", True)

    elif kind == TaskKind.MEMORY_STORE:
        step.name = "Store Memory"
        step.description = f"Store {payload.get('kind', 'unknown')} memory"
        step.payload.setdefault("confidence", 0.8)

    elif kind == TaskKind.MEMORY_QUERY:
        step.name = "Query Memory"
        step.description = f"Query: {payload.get('query', 'unknown')[:50]}"
        step.payload.setdefault("limit", 10)

    elif kind == TaskKind.AGENT_DELEGATE:
        step.name = "Delegate to Agent"
        step.description = f"Delegate to: {payload.get('role', 'unknown')}"
        step.payload.setdefault("timeout", 300)

    elif kind == TaskKind.AGENT_VERIFY:
        step.name = "Verify Agent Result"
        step.description = "Verify delegated task result"

    return step


def create_task_from_kind(
    kind: TaskKind,
    payload: Dict[str, Any],
    name: str = "",
    description: str = "",
    priority: TaskPriority = TaskPriority.NORMAL,
    resource_limits: Optional[ResourceLimits] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Task:
    """
    Create a complete task from a kind and payload.

    Args:
        kind: Task kind
        payload: Task payload
        name: Optional task name
        description: Optional description
        priority: Task priority
        resource_limits: Resource limits
        metadata: Additional metadata

    Returns:
        Configured Task ready for submission
    """
    step = create_step_from_kind(kind, payload)

    return Task(
        kind=kind,
        name=name or kind.value,
        description=description,
        payload=payload,
        priority=priority,
        resource_limits=resource_limits or ResourceLimits(),
        steps=[step],
        metadata=metadata or {},
    )


# =============================================================================
# Composite Task Builders
# =============================================================================

def create_shell_task(
    command: str,
    name: str = "",
    cwd: str = "/workspace",
    timeout: int = 300,
    shell: bool = True,
    **kwargs,
) -> Task:
    """Create a shell execution task."""
    return create_task_from_kind(
        TaskKind.SHELL_EXEC,
        {"command": command, "cwd": cwd, "timeout": timeout, "shell": shell},
        name=name or f"Shell: {command[:50]}",
        **kwargs,
    )


def create_file_read_task(path: str, **kwargs) -> Task:
    """Create a file read task."""
    return create_task_from_kind(
        TaskKind.FILE_READ,
        {"path": path},
        name=f"Read: {path}",
        **kwargs,
    )


def create_file_write_task(path: str, content: str, mode: str = "w", **kwargs) -> Task:
    """Create a file write task."""
    return create_task_from_kind(
        TaskKind.FILE_WRITE,
        {"path": path, "content": content, "mode": mode},
        name=f"Write: {path}",
        **kwargs,
    )


def create_file_list_task(path: str = ".", pattern: str = "*", recursive: bool = False, **kwargs) -> Task:
    """Create a file list task."""
    return create_task_from_kind(
        TaskKind.FILE_LIST,
        {"path": path, "pattern": pattern, "recursive": recursive},
        name=f"List: {path}",
        **kwargs,
    )


def create_http_task(
    method: str,
    url: str,
    headers: Optional[Dict[str, str]] = None,
    json_data: Optional[Dict] = None,
    data: Optional[str] = None,
    params: Optional[Dict] = None,
    timeout: int = 30,
    **kwargs,
) -> Task:
    """Create an HTTP request task."""
    payload = {"method": method, "url": url, "timeout": timeout}
    if headers:
        payload["headers"] = headers
    if json_data:
        payload["json"] = json_data
    if data:
        payload["data"] = data
    if params:
        payload["params"] = params

    return create_task_from_kind(
        TaskKind.HTTP_REQUEST,
        payload,
        name=f"{method} {url}",
        **kwargs,
    )


def create_browser_navigate_task(url: str, wait_until: str = "networkidle", **kwargs) -> Task:
    """Create a browser navigate task."""
    return create_task_from_kind(
        TaskKind.BROWSER_NAVIGATE,
        {"url": url, "wait_until": wait_until},
        name=f"Navigate: {url}",
        **kwargs,
    )


def create_browser_click_task(selector: str, button: str = "left", **kwargs) -> Task:
    """Create a browser click task."""
    return create_task_from_kind(
        TaskKind.BROWSER_CLICK,
        {"selector": selector, "button": button},
        name=f"Click: {selector}",
        **kwargs,
    )


def create_browser_extract_task(
    selector: str,
    attribute: str = "textContent",
    multiple: bool = False,
    **kwargs,
) -> Task:
    """Create a browser extract task."""
    return create_task_from_kind(
        TaskKind.BROWSER_EXTRACT,
        {"selector": selector, "attribute": attribute, "multiple": multiple},
        name=f"Extract: {selector}",
        **kwargs,
    )


def create_uia_find_task(
    selector: Dict[str, Any],
    timeout: int = 5000,
    **kwargs,
) -> Task:
    """Create a UIA find element task."""
    return create_task_from_kind(
        TaskKind.UIA_FIND,
        {"selector": selector, "timeout": timeout},
        name=f"UIA Find: {selector}",
        **kwargs,
    )


def create_uia_click_task(selector: Dict[str, Any], **kwargs) -> Task:
    """Create a UIA click task."""
    return create_task_from_kind(
        TaskKind.UIA_CLICK,
        {"selector": selector},
        name=f"UIA Click: {selector}",
        **kwargs,
    )


def create_uia_input_task(
    selector: Dict[str, Any],
    text: str,
    clear_first: bool = True,
    **kwargs,
) -> Task:
    """Create a UIA input text task."""
    return create_task_from_kind(
        TaskKind.UIA_INPUT,
        {"selector": selector, "text": text, "clear_first": clear_first},
        name=f"UIA Input: {text[:30]}",
        **kwargs,
    )


def create_memory_store_task(
    kind: str,
    content: str,
    confidence: float = 0.8,
    metadata: Optional[Dict] = None,
    tags: Optional[List[str]] = None,
    ttl_days: Optional[int] = None,
    **kwargs,
) -> Task:
    """Create a memory store task."""
    return create_task_from_kind(
        TaskKind.MEMORY_STORE,
        {
            "kind": kind,
            "content": content,
            "confidence": confidence,
            "metadata": metadata or {},
            "tags": tags or [],
            "ttl_days": ttl_days,
        },
        name=f"Store {kind} memory",
        **kwargs,
    )


def create_memory_query_task(
    query: str,
    kind: Optional[str] = None,
    limit: int = 10,
    filters: Optional[Dict] = None,
    **kwargs,
) -> Task:
    """Create a memory query task."""
    payload = {"query": query, "limit": limit}
    if kind:
        payload["kind"] = kind
    if filters:
        payload["filters"] = filters

    return create_task_from_kind(
        TaskKind.MEMORY_QUERY,
        payload,
        name=f"Query memory: {query[:50]}",
        **kwargs,
    )


def create_agent_delegate_task(
    role: str,
    task_description: str,
    context: Optional[Dict] = None,
    timeout: int = 300,
    **kwargs,
) -> Task:
    """Create an agent delegation task."""
    return create_task_from_kind(
        TaskKind.AGENT_DELEGATE,
        {
            "role": role,
            "task_description": task_description,
            "context": context or {},
            "timeout": timeout,
        },
        name=f"Delegate to {role}",
        **kwargs,
    )


def create_agent_verify_task(
    delegation_id: str,
    criteria: Optional[List[str]] = None,
    **kwargs,
) -> Task:
    """Create an agent verification task."""
    return create_task_from_kind(
        TaskKind.AGENT_VERIFY,
        {
            "delegation_id": delegation_id,
            "criteria": criteria or ["completeness", "correctness", "safety"],
        },
        name=f"Verify: {delegation_id}",
        **kwargs,
    )


# =============================================================================
# Export
# =============================================================================

__all__ = [
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