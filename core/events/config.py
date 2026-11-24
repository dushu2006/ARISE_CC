# core/events/config.py
"""
EventsConfig - Configuration for the event bus system.

Provides Pydantic models for configuring:
- LocalEventBus settings
- DistributedEventBus (Redis) settings
- EventStore settings
- Projection settings
- Metrics and tracing settings
"""

from __future__ import annotations
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class LocalEventBusConfig(BaseModel):
    """Configuration for LocalEventBus."""

    enabled: bool = True
    worker_count: int = Field(default=4, ge=1, le=32)
    queue_maxsize: int = Field(default=10000, ge=100, le=1000000)
    dead_letter_maxsize: int = Field(default=1000, ge=100, le=100000)
    default_retry_delay: float = Field(default=1.0, ge=0.1, le=60.0)
    max_retry_delay: float = Field(default=60.0, ge=1.0, le=3600.0)

    # Subscription defaults
    default_handler_priority: int = 0
    max_wildcard_subscriptions: int = Field(default=1000, ge=0, le=10000)


class DistributedEventBusConfig(BaseModel):
    """Configuration for DistributedEventBus (Redis Streams)."""

    enabled: bool = False
    redis_url: str = "redis://localhost:6379"
    stream_name: str = "arise:events"
    consumer_group: str = "arise-consumers"
    consumer_name: str = ""  # Auto-generated if empty
    block_ms: int = Field(default=5000, ge=100, le=60000)
    count: int = Field(default=100, ge=1, le=1000)
    max_stream_length: int = Field(default=100000, ge=1000, le=10000000)

    # Connection settings
    connection_timeout: float = Field(default=5.0, ge=1.0, le=30.0)
    socket_keepalive: bool = True
    retry_on_timeout: bool = True
    max_connections: int = Field(default=50, ge=10, le=200)


class HybridEventBusConfig(BaseModel):
    """Configuration for HybridEventBus (local + distributed)."""

    enabled: bool = True
    local: LocalEventBusConfig = Field(default_factory=LocalEventBusConfig)
    distributed: DistributedEventBusConfig = Field(default_factory=DistributedEventBusConfig)

    # Event types that should go to distributed bus
    distributed_patterns: list[str] = Field(default=[
        "task.*",
        "agent.*",
        "policy.*",
        "model.*",
        "memory.*",
        "voice.*",
        "automation.*",
        "security.*",
    ])

    # Fallback behavior
    fallback_to_local: bool = True
    require_distributed_for_patterns: bool = False


class EventStoreConfig(BaseModel):
    """Configuration for EventStore."""

    enabled: bool = True
    db_path: str = "./data/events.db"
    wal_mode: bool = True
    max_batch_size: int = Field(default=1000, ge=1, le=10000)
    snapshot_interval: int = Field(default=100, ge=10, le=10000)

    # Retention
    event_retention_days: int = Field(default=30, ge=1, le=365)
    dead_letter_retention_days: int = Field(default=90, ge=1, le=365)
    snapshot_retention_count: int = Field(default=10, ge=1, le=100)

    # Performance
    cache_size_mb: int = Field(default=32, ge=8, le=512)
    mmap_size_mb: int = Field(default=256, ge=64, le=2048)
    busy_timeout_ms: int = Field(default=5000, ge=1000, le=30000)


class ProjectionConfig(BaseModel):
    """Configuration for projections."""

    enabled: bool = True
    snapshot_interval: int = Field(default=100, ge=10, le=10000)
    rebuild_batch_size: int = Field(default=1000, ge=100, le=10000)

    # Default projections to enable
    enable_task_status: bool = True
    enable_agent_health: bool = True
    enable_model_usage: bool = True

    # Task status projection
    task_history_limit: int = Field(default=1000, ge=100, le=10000)

    # Agent health projection
    agent_stale_threshold_seconds: int = Field(default=60, ge=10, le=3600)


class EventMetricsConfig(BaseModel):
    """Configuration for event metrics."""

    enabled: bool = True
    collection_interval_seconds: int = Field(default=10, ge=1, le=300)
    export_port: int = Field(default=9090, ge=1024, le=65535)
    export_path: str = "/metrics"


class EventTracingConfig(BaseModel):
    """Configuration for event tracing."""

    enabled: bool = True
    service_name: str = "arise"
    default_correlation_id: Optional[str] = None

    # W3C TraceContext
    trace_header_name: str = "traceparent"
    trace_state_header_name: str = "tracestate"

    # Sampling
    sample_rate: float = Field(default=1.0, ge=0.0, le=1.0)

    # Logging
    log_trace_context: bool = True
    log_level: str = "DEBUG"


class EventsConfig(BaseModel):
    """
    Main configuration for the entire event bus system.

    All event-related configuration is centralized here.
    """

    # Bus configuration
    hybrid_bus: HybridEventBusConfig = Field(default_factory=HybridEventBusConfig)

    # Store configuration
    event_store: EventStoreConfig = Field(default_factory=EventStoreConfig)

    # Projection configuration
    projections: ProjectionConfig = Field(default_factory=ProjectionConfig)

    # Metrics configuration
    metrics: EventMetricsConfig = Field(default_factory=EventMetricsConfig)

    # Tracing configuration
    tracing: EventTracingConfig = Field(default_factory=EventTracingConfig)

    # Global settings
    enabled: bool = True
    log_level: str = "INFO"

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid:
            raise ValueError(f"log_level must be one of {valid}")
        return v.upper()

    def get_local_bus_config(self) -> LocalEventBusConfig:
        """Get local bus configuration."""
        return self.hybrid_bus.local

    def get_distributed_bus_config(self) -> DistributedEventBusConfig:
        """Get distributed bus configuration."""
        return self.hybrid_bus.distributed

    def is_distributed_enabled(self) -> bool:
        """Check if distributed bus is enabled."""
        return self.hybrid_bus.enabled and self.hybrid_bus.distributed.enabled

    def get_distributed_patterns(self) -> list[str]:
        """Get patterns for distributed events."""
        return self.hybrid_bus.distributed_patterns


# Default configuration instance
DEFAULT_EVENTS_CONFIG = EventsConfig()


def load_events_config(config_dict: Optional[dict[str, Any]] = None) -> EventsConfig:
    """
    Load events configuration from dictionary.

    Args:
        config_dict: Configuration dictionary (typically from YAML)

    Returns:
        EventsConfig instance
    """
    if config_dict is None:
        return DEFAULT_EVENTS_CONFIG

    return EventsConfig(**config_dict)


# Example YAML configuration
EXAMPLE_CONFIG_YAML = """
events:
  enabled: true
  log_level: "INFO"

  hybrid_bus:
    enabled: true
    local:
      enabled: true
      worker_count: 4
      queue_maxsize: 10000
      dead_letter_maxsize: 1000
      default_retry_delay: 1.0
      max_retry_delay: 60.0
    distributed:
      enabled: false
      redis_url: "redis://localhost:6379"
      stream_name: "arise:events"
      consumer_group: "arise-consumers"
      block_ms: 5000
      count: 100
      max_stream_length: 100000
    distributed_patterns:
      - "task.*"
      - "agent.*"
      - "policy.*"
      - "model.*"
      - "memory.*"
      - "voice.*"
      - "automation.*"
      - "security.*"
    fallback_to_local: true
    require_distributed_for_patterns: false

  event_store:
    enabled: true
    db_path: "./data/events.db"
    wal_mode: true
    max_batch_size: 1000
    snapshot_interval: 100
    event_retention_days: 30
    dead_letter_retention_days: 90
    cache_size_mb: 32
    mmap_size_mb: 256

  projections:
    enabled: true
    snapshot_interval: 100
    rebuild_batch_size: 1000
    enable_task_status: true
    enable_agent_health: true
    enable_model_usage: true
    task_history_limit: 1000
    agent_stale_threshold_seconds: 60

  metrics:
    enabled: true
    collection_interval_seconds: 10
    export_port: 9090
    export_path: "/metrics"

  tracing:
    enabled: true
    service_name: "arise"
    trace_header_name: "traceparent"
    trace_state_header_name: "tracestate"
    sample_rate: 1.0
    log_trace_context: true
    log_level: "DEBUG"
"""


if __name__ == "__main__":
    # Test configuration loading
    import yaml

    config = yaml.safe_load(EXAMPLE_CONFIG_YAML)
    events_config = load_events_config(config["events"])

    print("EventsConfig loaded successfully:")
    print(f"  Hybrid bus enabled: {events_config.hybrid_bus.enabled}")
    print(f"  Local bus workers: {events_config.hybrid_bus.local.worker_count}")
    print(f"  Distributed bus enabled: {events_config.is_distributed_enabled()}")
    print(f"  Event store path: {events_config.event_store.db_path}")
    print(f"  Projections enabled: {events_config.projections.enabled}")
    print(f"  Metrics enabled: {events_config.metrics.enabled}")
    print(f"  Tracing enabled: {events_config.tracing.enabled}")