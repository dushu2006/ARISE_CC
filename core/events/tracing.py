# core/events/tracing.py
"""
Event Tracing - Correlation ID propagation and distributed tracing.

Provides:
- EventTracer for managing correlation/causation IDs
- Context managers for trace context
- Integration with logging and metrics
- W3C TraceContext compatible headers
"""

from __future__ import annotations
import contextvars
import logging
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from core.events.models import Event

logger = logging.getLogger(__name__)

# Context variables for trace propagation
_correlation_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "correlation_id", default=None
)
_causation_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "causation_id", default=None
)
_trace_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "trace_id", default=None
)
_span_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "span_id", default=None
)
_trace_parent_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "trace_parent", default=None
)
_trace_state_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "trace_state", default=None
)


@dataclass
class TraceContext:
    """Complete trace context for distributed tracing."""
    trace_id: str
    span_id: str
    parent_span_id: Optional[str] = None
    trace_flags: str = "01"  # 01 = sampled
    trace_state: Optional[str] = None

    @property
    def trace_parent(self) -> str:
        """W3C TraceParent header value."""
        return f"00-{self.trace_id}-{self.span_id}-{self.trace_flags}"

    @classmethod
    def from_trace_parent(cls, trace_parent: str) -> Optional["TraceContext"]:
        """Parse W3C TraceParent header."""
        # Format: version-trace-id-span-id-flags
        parts = trace_parent.split("-")
        if len(parts) != 4:
            return None

        version, trace_id, span_id, flags = parts
        if version != "00":
            return None

        return cls(
            trace_id=trace_id,
            span_id=span_id,
            trace_flags=flags,
        )

    def new_child_span(self) -> "TraceContext":
        """Create a new child span."""
        return TraceContext(
            trace_id=self.trace_id,
            span_id=uuid.uuid4().hex[:16],
            parent_span_id=self.span_id,
            trace_flags=self.trace_flags,
            trace_state=self.trace_state,
        )


def get_correlation_id() -> Optional[str]:
    """Get current correlation ID from context."""
    return _correlation_id_var.get()


def set_correlation_id(correlation_id: str) -> contextvars.Token:
    """Set correlation ID in context."""
    return _correlation_id_var.set(correlation_id)


def get_causation_id() -> Optional[str]:
    """Get current causation ID from context."""
    return _causation_id_var.get()


def set_causation_id(causation_id: str) -> contextvars.Token:
    """Set causation ID in context."""
    return _causation_id_var.set(causation_id)


def get_trace_context() -> Optional[TraceContext]:
    """Get current trace context."""
    trace_id = _trace_id_var.get()
    span_id = _span_id_var.get()

    if trace_id and span_id:
        return TraceContext(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=_causation_id_var.get(),
            trace_flags="01",
            trace_state=_trace_state_var.get(),
        )
    return None


def set_trace_context(context: TraceContext) -> list[contextvars.Token]:
    """Set trace context in context variables."""
    tokens = []
    tokens.append(_trace_id_var.set(context.trace_id))
    tokens.append(_span_id_var.set(context.span_id))
    if context.parent_span_id:
        tokens.append(_causation_id_var.set(context.parent_span_id))
    if context.trace_state:
        tokens.append(_trace_state_var.set(context.trace_state))
    return tokens


def clear_trace_context(tokens: list[contextvars.Token]) -> None:
    """Clear trace context using tokens."""
    for token in reversed(tokens):
        # Determine which var to reset based on token
        try:
            _trace_id_var.reset(token)
        except ValueError:
            try:
                _span_id_var.reset(token)
            except ValueError:
                try:
                    _causation_id_var.reset(token)
                except ValueError:
                    _trace_state_var.reset(token)


@contextmanager
def correlation_context(correlation_id: Optional[str] = None):
    """
    Context manager for correlation ID.

    Usage:
        with correlation_context("my-correlation-id"):
            # All events created here will have this correlation_id
            event = Event(type="task.started", ...)
    """
    cid = correlation_id or str(uuid.uuid4())[:12]
    token = _correlation_id_var.set(cid)
    try:
        yield cid
    finally:
        _correlation_id_var.reset(token)


@contextmanager
def causation_context(causation_id: str):
    """
    Context manager for causation ID (parent event ID).

    Usage:
        with causation_context(parent_event.id):
            # Child events will have this causation_id
            child_event = Event(type="task.step.started", ...)
    """
    token = _causation_id_var.set(causation_id)
    try:
        yield causation_id
    finally:
        _causation_id_var.reset(token)


@contextmanager
def trace_context(trace_context: Optional[TraceContext] = None):
    """
    Context manager for full trace context.

    Usage:
        with trace_context(TraceContext(...)):
            # All events will have trace context
            event = Event(type="task.started", ...)
    """
    if trace_context is None:
        trace_context = TraceContext(
            trace_id=uuid.uuid4().hex[:32],
            span_id=uuid.uuid4().hex[:16],
        )

    tokens = set_trace_context(trace_context)
    # Also set correlation/causation for backward compatibility
    corr_token = _correlation_id_var.set(trace_context.trace_id[:12])
    if trace_context.parent_span_id:
        caus_token = _causation_id_var.set(trace_context.parent_span_id)
        tokens.extend([corr_token, caus_token])
    else:
        tokens.append(corr_token)

    try:
        yield trace_context
    finally:
        clear_trace_context(tokens)


def create_trace_context(
    trace_parent: Optional[str] = None,
    trace_state: Optional[str] = None,
) -> TraceContext:
    """
    Create trace context from headers or generate new.

    Args:
        trace_parent: W3C TraceParent header
        trace_state: W3C TraceState header

    Returns:
        TraceContext instance
    """
    if trace_parent:
        parsed = TraceContext.from_trace_parent(trace_parent)
        if parsed:
            if trace_state:
                parsed.trace_state = trace_state
            return parsed.new_child_span()

    # Generate new trace
    return TraceContext(
        trace_id=uuid.uuid4().hex[:32],
        span_id=uuid.uuid4().hex[:16],
        trace_state=trace_state,
    )


def inject_trace_headers(headers: dict[str, str], trace_context: Optional[TraceContext] = None) -> None:
    """Inject trace context into HTTP headers."""
    ctx = trace_context or get_trace_context()
    if ctx:
        headers["traceparent"] = ctx.trace_parent
        if ctx.trace_state:
            headers["tracestate"] = ctx.trace_state


def extract_trace_context(headers: dict[str, str]) -> Optional[TraceContext]:
    """Extract trace context from HTTP headers."""
    trace_parent = headers.get("traceparent") or headers.get("TraceParent")
    trace_state = headers.get("tracestate") or headers.get("TraceState")

    if trace_parent:
        return create_trace_context(trace_parent, trace_state)
    return None


class EventTracer:
    """
    Event tracer for correlation ID management and distributed tracing.

    Features:
    - Automatic correlation ID generation and propagation
    - Causation chain tracking
    - W3C TraceContext compatibility
    - Integration with Event creation
    - Trace context logging
    """

    def __init__(
        self,
        service_name: str = "arise",
        default_correlation_id: Optional[str] = None,
    ):
        self.service_name = service_name
        self.default_correlation_id = default_correlation_id
        self._active_traces: dict[str, TraceContext] = {}

    def start_trace(
        self,
        operation: str,
        correlation_id: Optional[str] = None,
        trace_parent: Optional[str] = None,
        trace_state: Optional[str] = None,
        attributes: Optional[dict[str, Any]] = None,
    ) -> TraceContext:
        """
        Start a new trace.

        Args:
            operation: Name of the operation being traced
            correlation_id: Optional existing correlation ID
            trace_parent: Incoming W3C TraceParent header
            trace_state: Incoming W3C TraceState header
            attributes: Additional attributes for the trace

        Returns:
            TraceContext for the new trace
        """
        trace_ctx = create_trace_context(trace_parent, trace_state)

        # Use provided correlation_id or extract from trace
        if correlation_id:
            trace_ctx.trace_id = correlation_id + "0" * (32 - len(correlation_id))
            trace_ctx.span_id = uuid.uuid4().hex[:16]

        # Store active trace
        self._active_traces[trace_ctx.trace_id] = trace_ctx

        # Log trace start
        logger.debug(
            f"Trace started: {operation}",
            extra={
                "trace_id": trace_ctx.trace_id,
                "span_id": trace_ctx.span_id,
                "operation": operation,
                "attributes": attributes or {},
            },
        )

        return trace_ctx

    def end_trace(
        self,
        trace_context: TraceContext,
        status: str = "ok",
        attributes: Optional[dict[str, Any]] = None,
    ) -> None:
        """
        End a trace.

        Args:
            trace_context: TraceContext to end
            status: "ok" or "error"
            attributes: Final attributes
        """
        self._active_traces.pop(trace_context.trace_id, None)

        logger.debug(
            f"Trace ended: {status}",
            extra={
                "trace_id": trace_context.trace_id,
                "span_id": trace_context.span_id,
                "status": status,
                "attributes": attributes or {},
            },
        )

    def create_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        source: str,
        priority = None,
        task_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        session_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
        causation_id: Optional[str] = None,
    ) -> Event:
        """
        Create an event with automatic trace context propagation.

        Uses context variables for correlation/causation IDs if not explicitly provided.
        """
        from core.events.models import EventPriority

        # Get correlation/causation from context
        ctx_correlation = correlation_id or get_correlation_id()
        ctx_causation = causation_id or get_causation_id()
        trace_ctx = get_trace_context()

        # Use trace context if available
        if trace_ctx and not ctx_correlation:
            ctx_correlation = trace_ctx.trace_id[:12]
        if trace_ctx and not ctx_causation:
            ctx_causation = trace_ctx.parent_span_id

        # Generate correlation ID if none
        if not ctx_correlation:
            ctx_correlation = self.default_correlation_id or str(uuid.uuid4())[:12]

        # Build metadata with trace info
        event_metadata = metadata or {}
        if trace_ctx:
            event_metadata["trace_id"] = trace_ctx.trace_id
            event_metadata["span_id"] = trace_ctx.span_id
        event_metadata["service"] = self.service_name

        return Event(
            type=event_type,
            payload=payload,
            priority=priority or EventPriority.NORMAL,
            correlation_id=ctx_correlation,
            causation_id=ctx_causation,
            source=source,
            task_id=task_id,
            agent_id=agent_id,
            session_id=session_id,
            metadata=event_metadata,
        )

    @contextmanager
    def trace_operation(
        self,
        operation: str,
        correlation_id: Optional[str] = None,
        attributes: Optional[dict[str, Any]] = None,
    ):
        """
        Context manager for tracing an operation.

        Usage:
            with tracer.trace_operation("task.execute", task_id="123") as trace:
                # Do work
                event = tracer.create_event("task.step", ..., source="task_engine")
        """
        trace_ctx = self.start_trace(operation, correlation_id, attributes=attributes)

        # Set context variables
        tokens = set_trace_context(trace_ctx)
        corr_token = _correlation_id_var.set(trace_ctx.trace_id[:12])
        tokens.append(corr_token)

        try:
            yield trace_ctx
        except Exception as e:
            self.end_trace(trace_ctx, status="error", attributes={"error": str(e)})
            raise
        else:
            self.end_trace(trace_ctx, status="ok", attributes=attributes)
        finally:
            clear_trace_context(tokens)

    def get_active_traces(self) -> dict[str, TraceContext]:
        """Get all active traces."""
        return self._active_traces.copy()

    def add_event_to_trace(
        self,
        trace_context: TraceContext,
        event: Event,
    ) -> None:
        """Associate an event with a trace for debugging."""
        # This could be extended to store event references in trace
        logger.debug(
            f"Event added to trace: {event.type}",
            extra={
                "trace_id": trace_context.trace_id,
                "span_id": trace_context.span_id,
                "event_type": event.type,
                "event_id": event.id,
            },
        )


# Global tracer instance
_event_tracer: Optional[EventTracer] = None


def get_event_tracer(service_name: str = "arise") -> EventTracer:
    """Get global event tracer."""
    global _event_tracer
    if _event_tracer is None:
        _event_tracer = EventTracer(service_name)
    return _event_tracer


def init_event_tracer(service_name: str = "arise") -> EventTracer:
    """Initialize global event tracer."""
    global _event_tracer
    _event_tracer = EventTracer(service_name)
    return _event_tracer


# Convenience functions for common patterns

@contextmanager
def traced_operation(
    operation: str,
    tracer: Optional[EventTracer] = None,
    correlation_id: Optional[str] = None,
    attributes: Optional[dict[str, Any]] = None,
):
    """Context manager for traced operation using global tracer."""
    t = tracer or get_event_tracer()
    with t.trace_operation(operation, correlation_id, attributes) as trace:
        yield trace


def create_traced_event(
    event_type: str,
    payload: dict[str, Any],
    source: str,
    tracer: Optional[EventTracer] = None,
    **kwargs,
) -> Event:
    """Create an event with trace context from global tracer."""
    t = tracer or get_event_tracer()
    return t.create_event(event_type, payload, source, **kwargs)


# Logging filter to add trace context to log records
class TraceContextFilter(logging.Filter):
    """Logging filter that adds trace context to log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        # Add correlation ID
        correlation_id = get_correlation_id()
        if correlation_id:
            record.correlation_id = correlation_id
        else:
            record.correlation_id = "-"

        # Add trace context if available
        trace_ctx = get_trace_context()
        if trace_ctx:
            record.trace_id = trace_ctx.trace_id
            record.span_id = trace_ctx.span_id
        else:
            record.trace_id = "-"
            record.span_id = "-"

        return True


def setup_trace_logging() -> None:
    """Add trace context filter to root logger."""
    root_logger = logging.getLogger()
    root_logger.addFilter(TraceContextFilter())


# FastAPI/Starlette middleware for automatic trace context
class TraceMiddleware:
    """
    ASGI middleware for automatic trace context extraction/injection.

    Usage:
        app.add_middleware(TraceMiddleware)
    """

    def __init__(self, app, tracer: Optional[EventTracer] = None):
        self.app = app
        self.tracer = tracer or get_event_tracer()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Extract trace context from headers
        headers = dict(scope.get("headers", []))
        # Convert bytes to strings
        str_headers = {
            k.decode("latin-1"): v.decode("latin-1")
            for k, v in headers
        }

        trace_ctx = extract_trace_context(str_headers)

        if trace_ctx:
            # Start trace for this request
            with self.tracer.trace_operation(
                f"{scope['method']} {scope['path']}",
                attributes={"http.method": scope["method"], "http.path": scope["path"]},
            ) as trace:
                # Inject trace headers into response
                async def send_wrapper(message):
                    if message["type"] == "http.response.start":
                        response_headers = list(message.get("headers", []))
                        inject_trace_headers(
                            {k.decode("latin-1"): v.decode("latin-1") for k, v in response_headers},
                            trace,
                        )
                    await send(message)

                await self.app(scope, receive, send_wrapper)
        else:
            await self.app(scope, receive, send)