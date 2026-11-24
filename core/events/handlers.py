# core/events/handlers.py
"""
Event Handler Registry - Centralized event handler management with decorators.

Provides:
- EventHandlerRegistry for registering and dispatching handlers
- @event_handler decorator for declarative handler registration
- Example handler implementations for Task and Memory events
- Auto-registration utility for discovering handlers
"""

from __future__ import annotations
import asyncio
import functools
import inspect
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, get_type_hints

from core.events.models import Event, EventTypes
from core.events.bus import LocalEventBus, get_event_bus
from core.events.store import EventStore, get_event_store
from core.errors.base import AriseError, ErrorCode

logger = logging.getLogger(__name__)


# Type alias for event handlers
EventHandler = Callable[[Event], Any]


@dataclass
class HandlerRegistration:
    """Registration info for an event handler."""
    handler: EventHandler
    event_type: str
    priority: int = 0
    description: str = ""
    filters: dict[str, Any] = field(default_factory=dict)


class EventHandlerRegistry:
    """
    Registry for event handlers with decorator support.

    Features:
    - Declarative handler registration via @event_handler decorator
    - Priority-based handler ordering
    - Event filtering (by correlation_id, task_id, etc.)
    - Automatic subscription to LocalEventBus
    - Handler metadata for introspection
    """

    def __init__(
        self,
        event_bus: Optional[LocalEventBus] = None,
        event_store: Optional[EventStore] = None,
    ):
        self.event_bus = event_bus
        self.event_store = event_store
        self._handlers: dict[str, list[HandlerRegistration]] = defaultdict(list)
        self._handler_metadata: dict[str, dict[str, Any]] = {}
        self._subscription_ids: dict[str, str] = {}  # handler_name -> subscription_id

    def register(
        self,
        event_type: str,
        handler: EventHandler,
        priority: int = 0,
        description: str = "",
        filters: Optional[dict[str, Any]] = None,
    ) -> str:
        """
        Register an event handler.

        Args:
            event_type: Event type to handle (supports wildcards)
            handler: Async function to handle events
            priority: Handler priority (higher runs first)
            description: Human-readable description
            filters: Optional filters (e.g., {"task_id": "specific-id"})

        Returns:
            Handler registration ID
        """
        registration = HandlerRegistration(
            handler=handler,
            event_type=event_type,
            priority=priority,
            description=description,
            filters=filters or {},
        )

        self._handlers[event_type].append(registration)
        # Sort by priority (highest first)
        self._handlers[event_type].sort(key=lambda r: -r.priority)

        # Store metadata
        handler_name = getattr(handler, "__name__", str(handler))
        self._handler_metadata[handler_name] = {
            "event_type": event_type,
            "priority": priority,
            "description": description,
            "filters": filters or {},
            "is_async": asyncio.iscoroutinefunction(handler),
        }

        logger.debug(f"Registered handler {handler_name} for {event_type}")
        return handler_name

    def unregister(self, handler_name: str) -> bool:
        """Unregister a handler by name."""
        # Find and remove from handlers
        for event_type, registrations in self._handlers.items():
            for i, reg in enumerate(registrations):
                if getattr(reg.handler, "__name__", str(reg.handler)) == handler_name:
                    registrations.pop(i)
                    if not registrations:
                        del self._handlers[event_type]

                    # Remove metadata
                    self._handler_metadata.pop(handler_name, None)

                    # Unsubscribe from event bus
                    if handler_name in self._subscription_ids:
                        sub_id = self._subscription_ids.pop(handler_name)
                        if self.event_bus:
                            asyncio.create_task(self.event_bus.unsubscribe(sub_id))

                    logger.debug(f"Unregistered handler {handler_name}")
                    return True

        return False

    def get_handlers(self, event_type: str) -> list[HandlerRegistration]:
        """Get all handlers for an event type (including wildcard matches)."""
        handlers = []

        # Exact matches
        if event_type in self._handlers:
            handlers.extend(self._handlers[event_type])

        # Wildcard matches
        import re
        for pattern, registrations in self._handlers.items():
            if "*" in pattern or "?" in pattern:
                regex = pattern.replace(".", r"\.")
                regex = regex.replace("**", ".*")
                regex = regex.replace("*", "[^.]*")
                regex = regex.replace("?", ".")
                if re.match(f"^{regex}$", event_type):
                    handlers.extend(registrations)

        # Sort by priority
        handlers.sort(key=lambda r: -r.priority)
        return handlers

    async def subscribe_all(self, event_bus: Optional[LocalEventBus] = None) -> None:
        """Subscribe all registered handlers to the event bus."""
        bus = event_bus or self.event_bus or await get_event_bus()

        for event_type, registrations in self._handlers.items():
            for reg in registrations:
                handler_name = getattr(reg.handler, "__name__", str(reg.handler))

                # Create wrapper that applies filters
                async def make_wrapper(registration: HandlerRegistration):
                    async def wrapper(event: Event):
                        # Apply filters
                        for key, expected in registration.filters.items():
                            actual = getattr(event, key, None)
                            if actual != expected:
                                return

                        try:
                            if asyncio.iscoroutinefunction(registration.handler):
                                await registration.handler(event)
                            else:
                                await asyncio.get_event_loop().run_in_executor(
                                    None, registration.handler, event
                                )
                        except Exception as e:
                            logger.error(f"Handler {handler_name} failed: {e}")
                            raise

                    return wrapper

                wrapper_fn = await make_wrapper(reg)
                sub_id = await bus.subscribe(event_type, wrapper_fn, priority=reg.priority)
                self._subscription_ids[handler_name] = sub_id

        logger.info(f"Subscribed {len(self._subscription_ids)} handlers to event bus")

    async def unsubscribe_all(self, event_bus: Optional[LocalEventBus] = None) -> None:
        """Unsubscribe all handlers from the event bus."""
        bus = event_bus or self.event_bus
        if bus:
            for handler_name, sub_id in self._subscription_ids.items():
                await bus.unsubscribe(sub_id)
        self._subscription_ids.clear()

    def list_handlers(self) -> list[dict[str, Any]]:
        """List all registered handlers with metadata."""
        result = []
        for event_type, registrations in self._handlers.items():
            for reg in registrations:
                handler_name = getattr(reg.handler, "__name__", str(reg.handler))
                meta = self._handler_metadata.get(handler_name, {})
                result.append({
                    "name": handler_name,
                    "event_type": event_type,
                    "priority": reg.priority,
                    "description": reg.description,
                    "filters": reg.filters,
                    **meta,
                })
        return result


# Global registry instance
_handler_registry: Optional[EventHandlerRegistry] = None


def get_handler_registry(
    event_bus: Optional[LocalEventBus] = None,
    event_store: Optional[EventStore] = None,
) -> EventHandlerRegistry:
    """Get global handler registry."""
    global _handler_registry
    if _handler_registry is None:
        _handler_registry = EventHandlerRegistry(event_bus, event_store)
    return _handler_registry


def init_handler_registry(
    event_bus: Optional[LocalEventBus] = None,
    event_store: Optional[EventStore] = None,
) -> EventHandlerRegistry:
    """Initialize global handler registry."""
    global _handler_registry
    _handler_registry = EventHandlerRegistry(event_bus, event_store)
    return _handler_registry


def event_handler(
    event_type: str,
    priority: int = 0,
    description: str = "",
    filters: Optional[dict[str, Any]] = None,
    registry: Optional[EventHandlerRegistry] = None,
) -> Callable:
    """
    Decorator to register an event handler.

    Usage:
        @event_handler("task.created", priority=10)
        async def handle_task_created(event: Event):
            ...

    Args:
        event_type: Event type pattern (supports wildcards)
        priority: Handler priority (higher runs first)
        description: Human-readable description
        filters: Optional event attribute filters
        registry: Registry to use (defaults to global)

    Returns:
        Decorated function
    """
    def decorator(func: EventHandler) -> EventHandler:
        reg = registry or get_handler_registry()
        handler_name = reg.register(
            event_type=event_type,
            handler=func,
            priority=priority,
            description=description or func.__doc__ or "",
            filters=filters,
        )

        # Attach metadata to function for introspection
        func._event_handler_info = {
            "event_type": event_type,
            "priority": priority,
            "description": description,
            "filters": filters or {},
            "handler_name": handler_name,
        }

        @functools.wraps(func)
        async def wrapper(event: Event):
            return await func(event)

        # Copy metadata to wrapper
        wrapper._event_handler_info = func._event_handler_info
        return wrapper

    return decorator


def auto_register_handlers(module_or_class, registry: Optional[EventHandlerRegistry] = None) -> int:
    """
    Automatically register all @event_handler decorated functions in a module or class.

    Args:
        module_or_class: Module or class to scan for handlers
        registry: Registry to use (defaults to global)

    Returns:
        Number of handlers registered
    """
    reg = registry or get_handler_registry()
    count = 0

    # Get all members
    if inspect.ismodule(module_or_class):
        members = inspect.getmembers(module_or_class, inspect.isfunction)
    else:
        members = inspect.getmembers(module_or_class, inspect.isfunction)
        # Also check class methods
        members.extend(inspect.getmembers(module_or_class, inspect.ismethod))

    for name, func in members:
        if hasattr(func, "_event_handler_info"):
            info = func._event_handler_info
            reg.register(
                event_type=info["event_type"],
                handler=func,
                priority=info["priority"],
                description=info["description"],
                filters=info["filters"],
            )
            count += 1
            logger.debug(f"Auto-registered handler {name} for {info['event_type']}")

    return count


# ============================================================
# Example Handlers
# ============================================================

class TaskEventHandlers:
    """Example handlers for task events."""

    @event_handler(EventTypes.TASK_CREATED, priority=100, description="Log task creation")
    async def on_task_created(event: Event):
        """Log when a task is created."""
        logger.info(f"Task created: {event.task_id} (correlation: {event.correlation_id})")

    @event_handler(EventTypes.TASK_STARTED, priority=50, description="Track task start time")
    async def on_task_started(event: Event):
        """Track task execution start."""
        logger.info(f"Task started: {event.task_id}")

    @event_handler(EventTypes.TASK_PROGRESS, priority=10, description="Log task progress")
    async def on_task_progress(event: Event):
        """Log task progress updates."""
        progress = event.payload.get("progress", 0)
        step = event.payload.get("step", "unknown")
        logger.debug(f"Task {event.task_id} progress: {progress:.1%} at step {step}")

    @event_handler(EventTypes.TASK_COMPLETED, priority=100, description="Handle task completion")
    async def on_task_completed(event: Event):
        """Handle task completion - store results, trigger notifications."""
        result = event.payload.get("result")
        logger.info(f"Task completed: {event.task_id} - result: {result is not None}")

        # Could trigger: notifications, webhooks, downstream tasks

    @event_handler(EventTypes.TASK_FAILED, priority=100, description="Handle task failure")
    async def on_task_failed(event: Event):
        """Handle task failure - alert, retry logic, compensation."""
        error = event.payload.get("error")
        logger.error(f"Task failed: {event.task_id} - {error}")

        # Could trigger: alerting, saga compensation, retry scheduling

    @event_handler(EventTypes.TASK_CANCELLED, priority=100, description="Handle task cancellation")
    async def on_task_cancelled(event: Event):
        """Handle task cancellation."""
        logger.warning(f"Task cancelled: {event.task_id}")


class MemoryEventHandlers:
    """Example handlers for memory events."""

    @event_handler(EventTypes.MEMORY_STORED, priority=50, description="Index stored memory")
    async def on_memory_stored(event: Event):
        """Index memory for search."""
        memory_id = event.payload.get("memory_id")
        kind = event.payload.get("kind")
        logger.debug(f"Memory stored: {memory_id} ({kind})")

    @event_handler(EventTypes.MEMORY_CONSOLIDATION_STARTED, priority=10, description="Log consolidation start")
    async def on_consolidation_started(event: Event):
        """Log consolidation start."""
        kind = event.payload.get("kind")
        logger.info(f"Memory consolidation started for {kind}")

    @event_handler(EventTypes.MEMORY_CONSOLIDATION_COMPLETED, priority=10, description="Log consolidation complete")
    async def on_consolidation_completed(event: Event):
        """Log consolidation completion."""
        kind = event.payload.get("kind")
        count = event.payload.get("count", 0)
        logger.info(f"Memory consolidation completed for {kind}: {count} memories processed")


class AgentEventHandlers:
    """Example handlers for agent events."""

    @event_handler(EventTypes.AGENT_REGISTERED, priority=100, description="Register agent in registry")
    async def on_agent_registered(event: Event):
        """Handle agent registration."""
        agent_id = event.agent_id
        role = event.payload.get("role")
        logger.info(f"Agent registered: {agent_id} ({role})")

    @event_handler(EventTypes.AGENT_HEARTBEAT, priority=10, description="Update agent health")
    async def on_agent_heartbeat(event: Event):
        """Update agent health from heartbeat."""
        health_score = event.payload.get("health_score", 1.0)
        if health_score < 0.5:
            logger.warning(f"Agent {event.agent_id} health degraded: {health_score}")

    @event_handler(EventTypes.AGENT_DELEGATION_STARTED, priority=50, description="Track delegation")
    async def on_delegation_started(event: Event):
        """Track agent delegation."""
        target_agent = event.payload.get("target_agent")
        logger.info(f"Delegation started: {event.agent_id} -> {target_agent}")

    @event_handler(EventTypes.AGENT_VERIFICATION_COMPLETED, priority=50, description="Process verification result")
    async def on_verification_completed(event: Event):
        """Process verification result."""
        passed = event.payload.get("passed", False)
        severity = event.payload.get("severity", "info")
        logger.info(f"Verification {'passed' if passed else 'failed'} ({severity}) for task {event.task_id}")


class PolicyEventHandlers:
    """Example handlers for policy events."""

    @event_handler(EventTypes.POLICY_APPROVAL_REQUESTED, priority=100, description="Notify for approval")
    async def on_approval_requested(event: Event):
        """Notify user/system that approval is needed."""
        approval_id = event.payload.get("approval_id")
        capability = event.payload.get("capability")
        logger.warning(f"Approval requested: {approval_id} for capability {capability}")

        # Could trigger: WebSocket notification, email, UI toast

    @event_handler(EventTypes.POLICY_APPROVAL_GRANTED, priority=50, description="Process granted approval")
    async def on_approval_granted(event: Event):
        """Process granted approval."""
        approval_id = event.payload.get("approval_id")
        ttl = event.payload.get("ttl")
        logger.info(f"Approval granted: {approval_id} (TTL: {ttl}s)")

    @event_handler(EventTypes.POLICY_APPROVAL_DENIED, priority=50, description="Process denied approval")
    async def on_approval_denied(event: Event):
        """Process denied approval."""
        approval_id = event.payload.get("approval_id")
        reason = event.payload.get("reason")
        logger.warning(f"Approval denied: {approval_id} - {reason}")


class ModelEventHandlers:
    """Example handlers for model events."""

    @event_handler(EventTypes.MODEL_CIRCUIT_OPEN, priority=100, description="Alert on circuit breaker open")
    async def on_circuit_open(event: Event):
        """Alert when circuit breaker opens."""
        provider = event.payload.get("provider")
        logger.error(f"Circuit breaker OPEN for provider: {provider}")

        # Could trigger: alerts, fallback activation

    @event_handler(EventTypes.MODEL_CIRCUIT_CLOSED, priority=50, description="Log circuit breaker close")
    async def on_circuit_closed(event: Event):
        """Log when circuit breaker closes."""
        provider = event.payload.get("provider")
        logger.info(f"Circuit breaker CLOSED for provider: {provider}")


class SecurityEventHandlers:
    """Example handlers for security events."""

    @event_handler(EventTypes.SECURITY_PROMPT_INJECTION, priority=200, description="Handle prompt injection")
    async def on_prompt_injection(event: Event):
        """Handle detected prompt injection attempt."""
        source = event.payload.get("source")
        content_preview = event.payload.get("content", "")[:100]
        logger.critical(f"PROMPT INJECTION DETECTED from {source}: {content_preview}")

        # Could trigger: immediate blocking, alerting, audit log

    @event_handler(EventTypes.SECURITY_NETWORK_BLOCKED, priority=100, description="Log blocked network access")
    async def on_network_blocked(event: Event):
        """Log blocked network access attempt."""
        domain = event.payload.get("domain")
        capability = event.payload.get("capability")
        logger.warning(f"Network access blocked: {domain} (capability: {capability})")

    @event_handler(EventTypes.SECURITY_CREDENTIAL_ACCESSED, priority=50, description="Audit credential access")
    async def on_credential_accessed(event: Event):
        """Audit credential access."""
        category = event.payload.get("category")
        key = event.payload.get("key")
        logger.info(f"Credential accessed: {category}.{key} by {event.source}")


# Convenience function to register all example handlers
def register_default_handlers(registry: Optional[EventHandlerRegistry] = None) -> int:
    """Register all default example handlers."""
    reg = registry or get_handler_registry()

    # Auto-register from handler classes
    total = 0
    for handler_class in [
        TaskEventHandlers,
        MemoryEventHandlers,
        AgentEventHandlers,
        PolicyEventHandlers,
        ModelEventHandlers,
        SecurityEventHandlers,
    ]:
        total += auto_register_handlers(handler_class, reg)

    logger.info(f"Registered {total} default event handlers")
    return total