# core/events/metrics.py
"""
Event Metrics - Prometheus metrics for event bus monitoring.

Provides comprehensive metrics for:
- Event throughput (published, processed, failed)
- Queue depths and latency
- Handler execution times
- Dead letter queue status
- Distributed bus metrics
"""

from __future__ import annotations
import time
from functools import wraps
from typing import Any, Callable, Optional

from prometheus_client import Counter, Gauge, Histogram, Summary, CollectorRegistry

# Create a dedicated registry for event metrics
event_metrics_registry = CollectorRegistry()


# ============================================================
# Local Event Bus Metrics
# ============================================================

# Event throughput
events_published_total = Counter(
    "arise_events_published_total",
    "Total number of events published to the local bus",
    ["event_type", "source"],
    registry=event_metrics_registry,
)

events_processed_total = Counter(
    "arise_events_processed_total",
    "Total number of events successfully processed",
    ["event_type", "handler"],
    registry=event_metrics_registry,
)

events_failed_total = Counter(
    "arise_events_failed_total",
    "Total number of events that failed processing",
    ["event_type", "handler", "error_type"],
    registry=event_metrics_registry,
)

events_retried_total = Counter(
    "arise_events_retried_total",
    "Total number of event retries",
    ["event_type", "retry_count"],
    registry=event_metrics_registry,
)

# Queue metrics
queue_size = Gauge(
    "arise_event_queue_size",
    "Current number of events in the queue",
    registry=event_metrics_registry,
)

queue_max_size = Gauge(
    "arise_event_queue_max_size",
    "Maximum queue size",
    registry=event_metrics_registry,
)

queue_enqueue_latency_seconds = Histogram(
    "arise_event_queue_enqueue_latency_seconds",
    "Time spent enqueueing events",
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
    registry=event_metrics_registry,
)

# Event processing latency
event_processing_latency_seconds = Histogram(
    "arise_event_processing_latency_seconds",
    "End-to-end event processing latency",
    ["event_type"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
    registry=event_metrics_registry,
)

handler_execution_latency_seconds = Histogram(
    "arise_handler_execution_latency_seconds",
    "Individual handler execution latency",
    ["event_type", "handler"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
    registry=event_metrics_registry,
)

# Subscription metrics
active_subscriptions = Gauge(
    "arise_active_subscriptions",
    "Number of active subscriptions",
    ["pattern_type"],  # exact or wildcard
    registry=event_metrics_registry,
)

# Dead letter metrics
dead_letter_size = Gauge(
    "arise_dead_letter_size",
    "Current number of events in dead letter queue",
    registry=event_metrics_registry,
)

dead_letter_max_size = Gauge(
    "arise_dead_letter_max_size",
    "Maximum dead letter queue size",
    registry=event_metrics_registry,
)

dead_letter_events_total = Counter(
    "arise_dead_letter_events_total",
    "Total events moved to dead letter queue",
    ["event_type", "error_type"],
    registry=event_metrics_registry,
)

dead_letter_replayed_total = Counter(
    "arise_dead_letter_replayed_total",
    "Total events replayed from dead letter queue",
    registry=event_metrics_registry,
)

# Worker metrics
active_workers = Gauge(
    "arise_active_workers",
    "Number of active worker tasks",
    registry=event_metrics_registry,
)

worker_events_processed = Counter(
    "arise_worker_events_processed_total",
    "Events processed per worker",
    ["worker_id"],
    registry=event_metrics_registry,
)


# ============================================================
# Distributed Event Bus Metrics
# ============================================================

distributed_events_published_total = Counter(
    "arise_distributed_events_published_total",
    "Total events published to Redis Streams",
    ["stream_name", "event_type"],
    registry=event_metrics_registry,
)

distributed_events_received_total = Counter(
    "arise_distributed_events_received_total",
    "Total events received from Redis Streams",
    ["stream_name", "consumer_group", "event_type"],
    registry=event_metrics_registry,
)

distributed_events_processed_total = Counter(
    "arise_distributed_events_processed_total",
    "Total events processed from Redis Streams",
    ["stream_name", "consumer_group", "event_type"],
    registry=event_metrics_registry,
)

distributed_events_failed_total = Counter(
    "arise_distributed_events_failed_total",
    "Total events failed from Redis Streams",
    ["stream_name", "consumer_group", "event_type", "error_type"],
    registry=event_metrics_registry,
)

distributed_consumer_lag = Gauge(
    "arise_distributed_consumer_lag",
    "Consumer lag (pending messages)",
    ["stream_name", "consumer_group", "consumer_name"],
    registry=event_metrics_registry,
)

distributed_stream_length = Gauge(
    "arise_distributed_stream_length",
    "Current stream length",
    ["stream_name"],
    registry=event_metrics_registry,
)

distributed_redis_latency_seconds = Histogram(
    "arise_distributed_redis_latency_seconds",
    "Redis operation latency",
    ["operation"],  # xadd, xreadgroup, xack
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
    registry=event_metrics_registry,
)

distributed_reconnects_total = Counter(
    "arise_distributed_reconnects_total",
    "Total Redis reconnections",
    ["reason"],
    registry=event_metrics_registry,
)


# ============================================================
# Event Store Metrics
# ============================================================

event_store_events_total = Counter(
    "arise_event_store_events_total",
    "Total events in event store",
    ["event_type"],
    registry=event_metrics_registry,
)

event_store_append_latency_seconds = Histogram(
    "arise_event_store_append_latency_seconds",
    "Event store append latency",
    ["operation"],  # single, batch
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
    registry=event_metrics_registry,
)

event_store_query_latency_seconds = Histogram(
    "arise_event_store_query_latency_seconds",
    "Event store query latency",
    ["query_type"],  # by_correlation, by_type, recent, count
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
    registry=event_metrics_registry,
)

event_store_snapshots_total = Gauge(
    "arise_event_store_snapshots_total",
    "Total snapshots stored",
    ["projection_name"],
    registry=event_metrics_registry,
)

event_store_dead_letter_total = Gauge(
    "arise_event_store_dead_letter_total",
    "Total events in dead letter table",
    registry=event_metrics_registry,
)

event_store_db_size_bytes = Gauge(
    "arise_event_store_db_size_bytes",
    "Event store database size in bytes",
    registry=event_metrics_registry,
)


# ============================================================
# Projection Metrics
# ============================================================

projection_events_processed_total = Counter(
    "arise_projection_events_processed_total",
    "Total events processed by projection",
    ["projection_name", "event_type"],
    registry=event_metrics_registry,
)

projection_rebuild_total = Counter(
    "arise_projection_rebuild_total",
    "Total projection rebuilds",
    ["projection_name"],
    registry=event_metrics_registry,
)

projection_rebuild_duration_seconds = Histogram(
    "arise_projection_rebuild_duration_seconds",
    "Projection rebuild duration",
    ["projection_name"],
    buckets=[1, 5, 10, 30, 60, 120, 300, 600],
    registry=event_metrics_registry,
)

projection_snapshot_latency_seconds = Histogram(
    "arise_projection_snapshot_latency_seconds",
    "Projection snapshot save latency",
    ["projection_name"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
    registry=event_metrics_registry,
)

projection_state_size = Gauge(
    "arise_projection_state_size",
    "Projection state size (number of keys)",
    ["projection_name"],
    registry=event_metrics_registry,
)


# ============================================================
# Handler Decorator for Metrics
# ============================================================

def track_handler_metrics(event_type: str, handler_name: str) -> Callable:
    """
    Decorator to track handler execution metrics.

    Usage:
        @track_handler_metrics("task.created", "my_handler")
        async def my_handler(event: Event):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(event: Event) -> Any:
            start_time = time.perf_counter()
            error_type = None
            try:
                result = await func(event)
                return result
            except Exception as e:
                error_type = type(e).__name__
                events_failed_total.labels(
                    event_type=event_type,
                    handler=handler_name,
                    error_type=error_type,
                ).inc()
                raise
            finally:
                duration = time.perf_counter() - start_time
                handler_execution_latency_seconds.labels(
                    event_type=event_type,
                    handler=handler_name,
                ).observe(duration)

                if error_type is None:
                    events_processed_total.labels(
                        event_type=event_type,
                        handler=handler_name,
                    ).inc()

        @wraps(func)
        def sync_wrapper(event: Event) -> Any:
            start_time = time.perf_counter()
            error_type = None
            try:
                result = func(event)
                return result
            except Exception as e:
                error_type = type(e).__name__
                events_failed_total.labels(
                    event_type=event_type,
                    handler=handler_name,
                    error_type=error_type,
                ).inc()
                raise
            finally:
                duration = time.perf_counter() - start_time
                handler_execution_latency_seconds.labels(
                    event_type=event_type,
                    handler=handler_name,
                ).observe(duration)

                if error_type is None:
                    events_processed_total.labels(
                        event_type=event_type,
                        handler=handler_name,
                    ).inc()

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


# ============================================================
# Metrics Collection Helpers
# ============================================================

class EventMetricsCollector:
    """Collect and expose metrics from event bus components."""

    def __init__(
        self,
        local_bus=None,
        distributed_bus=None,
        event_store=None,
        projection_registry=None,
    ):
        self.local_bus = local_bus
        self.distributed_bus = distributed_bus
        self.event_store = event_store
        self.projection_registry = projection_registry

    def collect_local_bus_metrics(self) -> None:
        """Update metrics from local event bus."""
        if not self.local_bus:
            return

        stats = self.local_bus.get_stats()

        queue_size.set(stats["queue_size"])
        queue_max_size.set(stats["queue_maxsize"])
        active_workers.set(stats["worker_count"] if stats["running"] else 0)

        exact_subs = stats["subscriptions_exact"]
        wildcard_subs = stats["subscriptions_wildcard"]
        active_subscriptions.labels(pattern_type="exact").set(exact_subs)
        active_subscriptions.labels(pattern_type="wildcard").set(wildcard_subs)

        dead_letter_size.set(stats["dead_letter_size"])
        dead_letter_max_size.set(stats["dead_letter_maxsize"])

    def collect_distributed_bus_metrics(self) -> None:
        """Update metrics from distributed event bus."""
        if not self.distributed_bus:
            return

        stats = self.distributed_bus.get_stats()

        # Note: Detailed stream info would require async call
        # This is a placeholder for sync metrics

    def collect_event_store_metrics(self) -> None:
        """Update metrics from event store."""
        if not self.event_store:
            return

        stats = self.event_store.get_stats()

        event_store_db_size_bytes.set(stats.get("db_size_bytes", 0))
        event_store_dead_letter_total.set(stats.get("dead_letter_count", 0))
        event_store_snapshots_total.labels(projection_name="total").set(
            stats.get("snapshot_count", 0)
        )

        for event_type, count in stats.get("events_by_type", {}).items():
            event_store_events_total.labels(event_type=event_type).set(count)

    def collect_projection_metrics(self) -> None:
        """Update metrics from projections."""
        if not self.projection_registry:
            return

        for name, projection in self.projection_registry._projections.items():
            checkpoint = projection.get_checkpoint()
            if checkpoint:
                projection_state_size.labels(projection_name=name).set(
                    len(projection.get_state()) if isinstance(projection.get_state(), dict) else 0
                )

    def collect_all(self) -> None:
        """Collect all metrics."""
        self.collect_local_bus_metrics()
        self.collect_distributed_bus_metrics()
        self.collect_event_store_metrics()
        self.collect_projection_metrics()


# Global metrics collector
_metrics_collector: Optional[EventMetricsCollector] = None


def get_metrics_collector(
    local_bus=None,
    distributed_bus=None,
    event_store=None,
    projection_registry=None,
) -> EventMetricsCollector:
    """Get global metrics collector."""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = EventMetricsCollector(
            local_bus, distributed_bus, event_store, projection_registry
        )
    return _metrics_collector


def init_metrics_collector(
    local_bus=None,
    distributed_bus=None,
    event_store=None,
    projection_registry=None,
) -> EventMetricsCollector:
    """Initialize global metrics collector."""
    global _metrics_collector
    _metrics_collector = EventMetricsCollector(
        local_bus, distributed_bus, event_store, projection_registry
    )
    return _metrics_collector


# ============================================================
# Middleware for Automatic Metrics
# ============================================================

class EventMetricsMiddleware:
    """
    Middleware to automatically track event bus metrics.

    Usage:
        bus = LocalEventBus()
        middleware = EventMetricsMiddleware(bus)
        await middleware.start()
    """

    def __init__(self, local_bus):
        self.local_bus = local_bus
        self._collect_task: Optional[asyncio.Task] = None
        self._interval = 10  # seconds

    async def start(self, interval: int = 10) -> None:
        """Start periodic metrics collection."""
        self._interval = interval
        self._collect_task = asyncio.create_task(self._collect_loop())

    async def stop(self) -> None:
        """Stop metrics collection."""
        if self._collect_task:
            self._collect_task.cancel()
            try:
                await self._collect_task
            except asyncio.CancelledError:
                pass

    async def _collect_loop(self) -> None:
        """Periodic metrics collection loop."""
        while True:
            try:
                await asyncio.sleep(self._interval)
                collector = get_metrics_collector(local_bus=self.local_bus)
                collector.collect_all()
            except asyncio.CancelledError:
                break
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Metrics collection error: {e}")


# ============================================================
# Utility Functions
# ============================================================

def record_event_published(event_type: str, source: str) -> None:
    """Record an event publication."""
    events_published_total.labels(event_type=event_type, source=source).inc()


def record_event_processed(event_type: str, handler: str, duration: float) -> None:
    """Record successful event processing."""
    events_processed_total.labels(event_type=event_type, handler=handler).inc()
    event_processing_latency_seconds.labels(event_type=event_type).observe(duration)


def record_event_failed(event_type: str, handler: str, error_type: str) -> None:
    """Record event processing failure."""
    events_failed_total.labels(
        event_type=event_type,
        handler=handler,
        error_type=error_type,
    ).inc()


def record_event_retried(event_type: str, retry_count: int) -> None:
    """Record event retry."""
    events_retried_total.labels(
        event_type=event_type,
        retry_count=str(retry_count),
    ).inc()


def record_dead_letter(event_type: str, error_type: str) -> None:
    """Record event moved to dead letter queue."""
    dead_letter_events_total.labels(
        event_type=event_type,
        error_type=error_type,
    ).inc()


def record_dead_letter_replayed() -> None:
    """Record dead letter replay."""
    dead_letter_replayed_total.inc()