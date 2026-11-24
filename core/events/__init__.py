# core/events/__init__.py
"""
ARISE Event Bus Package

A comprehensive event-driven architecture with:
- LocalEventBus: In-process async event bus with priority queue
- DistributedEventBus: Redis Streams for multi-node deployments
- HybridEventBus: Combines local + distributed for optimal performance
- EventStore: Persistent SQLite storage with WAL mode
- Projections: Materialized views with checkpointing
- Handlers: Declarative event handler registration
- Metrics: Prometheus instrumentation
- Tracing: W3C TraceContext correlation IDs
"""

from core.events.models import (
    Event,
    EventPriority,
    EventTypes,
    EventHandler,
)

from core.events.bus import (
    LocalEventBus,
    Subscription,
    DeadLetterEntry,
    get_event_bus,
    init_event_bus,
    shutdown_event_bus,
)

from core.events.distributed_bus import (
    DistributedEventBus,
    StreamConfig,
    HybridEventBus,
)

from core.events.store import (
    EventStore,
    EventStoreConfig,
    get_event_store,
    init_event_store,
    close_event_store,
)

from core.events.projections import (
    Projection,
    ProjectionCheckpoint,
    TaskStatusProjection,
    AgentHealthProjection,
    ModelUsageProjection,
    ProjectionRegistry,
    get_projection_registry,
    init_projections,
)

from core.events.handlers import (
    EventHandlerRegistry,
    HandlerRegistration,
    get_handler_registry,
    init_handler_registry,
    event_handler,
    auto_register_handlers,
    register_default_handlers,
    TaskEventHandlers,
    MemoryEventHandlers,
    AgentEventHandlers,
    PolicyEventHandlers,
    ModelEventHandlers,
    SecurityEventHandlers,
)

from core.events.metrics import (
    event_metrics_registry,
    EventMetricsCollector,
    get_metrics_collector,
    init_metrics_collector,
    EventMetricsMiddleware,
    record_event_published,
    record_event_processed,
    record_event_failed,
    record_event_retried,
    record_dead_letter,
    record_dead_letter_replayed,
)

from core.events.tracing import (
    TraceContext,
    get_correlation_id,
    set_correlation_id,
    get_causation_id,
    set_causation_id,
    get_trace_context,
    set_trace_context,
    correlation_context,
    causation_context,
    trace_context,
    create_trace_context,
    inject_trace_headers,
    extract_trace_context,
    EventTracer,
    get_event_tracer,
    init_event_tracer,
    traced_operation,
    create_traced_event,
    TraceContextFilter,
    setup_trace_logging,
    TraceMiddleware,
)

from core.events.config import (
    EventsConfig,
    LocalEventBusConfig,
    DistributedEventBusConfig,
    HybridEventBusConfig,
    EventStoreConfig,
    ProjectionConfig,
    EventMetricsConfig,
    EventTracingConfig,
    load_events_config,
    DEFAULT_EVENTS_CONFIG,
    EXAMPLE_CONFIG_YAML,
)

__all__ = [
    # Models
    "Event",
    "EventPriority",
    "EventTypes",
    "EventHandler",

    # Local Bus
    "LocalEventBus",
    "Subscription",
    "DeadLetterEntry",
    "get_event_bus",
    "init_event_bus",
    "shutdown_event_bus",

    # Distributed Bus
    "DistributedEventBus",
    "StreamConfig",
    "HybridEventBus",

    # Store
    "EventStore",
    "EventStoreConfig",
    "get_event_store",
    "init_event_store",
    "close_event_store",

    # Projections
    "Projection",
    "ProjectionCheckpoint",
    "TaskStatusProjection",
    "AgentHealthProjection",
    "ModelUsageProjection",
    "ProjectionRegistry",
    "get_projection_registry",
    "init_projections",

    # Handlers
    "EventHandlerRegistry",
    "HandlerRegistration",
    "get_handler_registry",
    "init_handler_registry",
    "event_handler",
    "auto_register_handlers",
    "register_default_handlers",
    "TaskEventHandlers",
    "MemoryEventHandlers",
    "AgentEventHandlers",
    "PolicyEventHandlers",
    "ModelEventHandlers",
    "SecurityEventHandlers",

    # Metrics
    "event_metrics_registry",
    "EventMetricsCollector",
    "get_metrics_collector",
    "init_metrics_collector",
    "EventMetricsMiddleware",
    "record_event_published",
    "record_event_processed",
    "record_event_failed",
    "record_event_retried",
    "record_dead_letter",
    "record_dead_letter_replayed",

    # Tracing
    "TraceContext",
    "get_correlation_id",
    "set_correlation_id",
    "get_causation_id",
    "set_causation_id",
    "get_trace_context",
    "set_trace_context",
    "correlation_context",
    "causation_context",
    "trace_context",
    "create_trace_context",
    "inject_trace_headers",
    "extract_trace_context",
    "EventTracer",
    "get_event_tracer",
    "init_event_tracer",
    "traced_operation",
    "create_traced_event",
    "TraceContextFilter",
    "setup_trace_logging",
    "TraceMiddleware",

    # Config
    "EventsConfig",
    "LocalEventBusConfig",
    "DistributedEventBusConfig",
    "HybridEventBusConfig",
    "EventStoreConfig",
    "ProjectionConfig",
    "EventMetricsConfig",
    "EventTracingConfig",
    "load_events_config",
    "DEFAULT_EVENTS_CONFIG",
    "EXAMPLE_CONFIG_YAML",
]

# Version
__version__ = "1.0.0"