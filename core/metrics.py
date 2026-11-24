# core/metrics.py
"""
Prometheus Metrics - Comprehensive metrics for ARISE observability.

Provides:
- All Prometheus metrics from 13_Performance_and_Resource_Management.md
- Decorators for automatic metric instrumentation
- /metrics endpoint for Prometheus scraping
"""

from __future__ import annotations
import functools
import time
from contextlib import contextmanager
from typing import Any, Callable, Optional

from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    Summary,
    CollectorRegistry,
    generate_latest,
    CONTENT_TYPE_LATEST,
)
from fastapi import Response

# Create dedicated registry for ARISE metrics
metrics_registry = CollectorRegistry()


# ============================================================
# HTTP Metrics
# ============================================================

http_requests_total = Counter(
    "arise_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
    registry=metrics_registry,
)

http_request_duration_seconds = Histogram(
    "arise_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
    registry=metrics_registry,
)

http_request_size_bytes = Histogram(
    "arise_http_request_size_bytes",
    "HTTP request size in bytes",
    ["method", "endpoint"],
    buckets=[100, 1000, 10000, 100000, 1000000],
    registry=metrics_registry,
)

http_response_size_bytes = Histogram(
    "arise_http_response_size_bytes",
    "HTTP response size in bytes",
    ["method", "endpoint"],
    buckets=[100, 1000, 10000, 100000, 1000000],
    registry=metrics_registry,
)

http_requests_in_flight = Gauge(
    "arise_http_requests_in_flight",
    "Current HTTP requests being processed",
    ["method", "endpoint"],
    registry=metrics_registry,
)


# ============================================================
# Task Engine Metrics
# ============================================================

task_submitted_total = Counter(
    "arise_task_submitted_total",
    "Total tasks submitted",
    ["task_kind", "priority"],
    registry=metrics_registry,
)

task_completed_total = Counter(
    "arise_task_completed_total",
    "Total tasks completed",
    ["task_kind", "status"],  # status: completed, failed, cancelled
    registry=metrics_registry,
)

task_duration_seconds = Histogram(
    "arise_task_duration_seconds",
    "Task execution duration in seconds",
    ["task_kind", "status"],
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0],
    registry=metrics_registry,
)

task_queue_depth = Gauge(
    "arise_task_queue_depth",
    "Current task queue depth",
    ["priority"],
    registry=metrics_registry,
)

task_active_total = Gauge(
    "arise_task_active_total",
    "Currently active (running) tasks",
    ["task_kind"],
    registry=metrics_registry,
)

task_retries_total = Counter(
    "arise_task_retries_total",
    "Total task retries",
    ["task_kind", "retry_reason"],
    registry=metrics_registry,
)

task_checkpoints_total = Counter(
    "arise_task_checkpoints_total",
    "Total task checkpoints saved",
    ["task_kind"],
    registry=metrics_registry,
)

task_checkpoint_duration_seconds = Histogram(
    "arise_task_checkpoint_duration_seconds",
    "Task checkpoint save duration",
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
    registry=metrics_registry,
)


# ============================================================
# Policy Engine Metrics
# ============================================================

policy_evaluations_total = Counter(
    "arise_policy_evaluations_total",
    "Total policy evaluations",
    ["result"],  # allow, deny, require_approval
    registry=metrics_registry,
)

policy_evaluation_duration_seconds = Histogram(
    "arise_policy_evaluation_duration_seconds",
    "Policy evaluation latency",
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
    registry=metrics_registry,
)

policy_approvals_total = Counter(
    "arise_policy_approvals_total",
    "Total approval requests",
    ["decision"],  # granted, denied, expired
    registry=metrics_registry,
)

policy_approval_duration_seconds = Histogram(
    "arise_policy_approval_duration_seconds",
    "Approval request duration (request to decision)",
    buckets=[1, 5, 10, 30, 60, 120, 300, 600, 1800, 3600],
    registry=metrics_registry,
)

policy_grants_active = Gauge(
    "arise_policy_grants_active",
    "Currently active capability grants",
    ["capability"],
    registry=metrics_registry,
)

policy_audit_entries_total = Counter(
    "arise_policy_audit_entries_total",
    "Total audit log entries",
    ["event_type"],
    registry=metrics_registry,
)


# ============================================================
# Model Router Metrics
# ============================================================

model_requests_total = Counter(
    "arise_model_requests_total",
    "Total model requests",
    ["provider", "model", "result"],  # result: success, error, filtered
    registry=metrics_registry,
)

model_request_duration_seconds = Histogram(
    "arise_model_request_duration_seconds",
    "Model request latency",
    ["provider", "model"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 20.0, 30.0, 60.0, 120.0],
    registry=metrics_registry,
)

model_stream_duration_seconds = Histogram(
    "arise_model_stream_duration_seconds",
    "Model streaming duration (first token to last)",
    ["provider", "model"],
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0],
    registry=metrics_registry,
)

model_tokens_total = Counter(
    "arise_model_tokens_total",
    "Total tokens processed",
    ["provider", "model", "type"],  # type: input, output
    registry=metrics_registry,
)

model_cost_total = Counter(
    "arise_model_cost_total",
    "Total model cost in USD",
    ["provider", "model"],
    registry=metrics_registry,
)

model_circuit_breaker_state = Gauge(
    "arise_model_circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=half-open, 2=open)",
    ["provider"],
    registry=metrics_registry,
)

model_fallback_total = Counter(
    "arise_model_fallback_total",
    "Total fallback activations",
    ["from_provider", "to_provider", "reason"],
    registry=metrics_registry,
)

model_privacy_redactions_total = Counter(
    "arise_model_privacy_redactions_total",
    "Total PII redactions applied",
    ["provider", "model"],
    registry=metrics_registry,
)


# ============================================================
# Memory System Metrics
# ============================================================

memory_operations_total = Counter(
    "arise_memory_operations_total",
    "Total memory operations",
    ["operation", "kind", "result"],  # operation: store, query, update, delete, consolidate
    registry=metrics_registry,
)

memory_store_duration_seconds = Histogram(
    "arise_memory_store_duration_seconds",
    "Memory store operation latency",
    ["kind"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
    registry=metrics_registry,
)

memory_query_duration_seconds = Histogram(
    "arise_memory_query_duration_seconds",
    "Memory query latency",
    ["kind"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5],
    registry=metrics_registry,
)

memory_total_count = Gauge(
    "arise_memory_total_count",
    "Total memories stored",
    ["kind"],
    registry=metrics_registry,
)

memory_vector_dimensions = Gauge(
    "arise_memory_vector_dimensions",
    "Vector embedding dimensions",
    ["kind"],
    registry=metrics_registry,
)

memory_consolidation_total = Counter(
    "arise_memory_consolidation_total",
    "Total consolidation runs",
    ["kind", "result"],  # result: success, partial, failed
    registry=metrics_registry,
)

memory_consolidation_duration_seconds = Histogram(
    "arise_memory_consolidation_duration_seconds",
    "Consolidation run duration",
    ["kind"],
    buckets=[1, 5, 10, 30, 60, 120, 300, 600, 1800, 3600],
    registry=metrics_registry,
)

memory_pii_detections_total = Counter(
    "arise_memory_pii_detections_total",
    "Total PII detections",
    ["kind", "action"],  # action: flagged, redacted, blocked
    registry=metrics_registry,
)

memory_evictions_total = Counter(
    "arise_memory_evictions_total",
    "Total LRU evictions",
    ["kind"],
    registry=metrics_registry,
)


# ============================================================
# Voice Pipeline Metrics
# ============================================================

voice_sessions_total = Counter(
    "arise_voice_sessions_total",
    "Total voice sessions",
    ["result"],  # completed, failed, timeout
    registry=metrics_registry,
)

voice_session_duration_seconds = Histogram(
    "arise_voice_session_duration_seconds",
    "Voice session duration",
    buckets=[1, 5, 10, 30, 60, 120, 300, 600, 1800, 3600],
    registry=metrics_registry,
)

voice_wake_word_detections_total = Counter(
    "arise_voice_wake_word_detections_total",
    "Total wake word detections",
    ["result"],  # true_positive, false_positive
    registry=metrics_registry,
)

voice_asr_duration_seconds = Histogram(
    "arise_voice_asr_duration_seconds",
    "ASR processing duration",
    ["provider"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 20.0],
    registry=metrics_registry,
)

voice_asr_confidence = Histogram(
    "arise_voice_asr_confidence",
    "ASR confidence scores",
    ["provider"],
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99],
    registry=metrics_registry,
)

voice_tts_duration_seconds = Histogram(
    "arise_voice_tts_duration_seconds",
    "TTS generation duration",
    ["provider"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 20.0],
    registry=metrics_registry,
)

voice_tts_characters_total = Counter(
    "arise_voice_tts_characters_total",
    "Total TTS characters generated",
    ["provider"],
    registry=metrics_registry,
)

voice_barge_in_total = Counter(
    "arise_voice_barge_in_total",
    "Total barge-in events",
    registry=metrics_registry,
)

voice_audio_level = Gauge(
    "arise_voice_audio_level",
    "Current audio input level (0-1)",
    registry=metrics_registry,
)


# ============================================================
# Automation Metrics
# ============================================================

automation_actions_total = Counter(
    "arise_automation_actions_total",
    "Total automation actions",
    ["backend", "action", "result"],  # backend: uia, playwright, cv_ocr
    registry=metrics_registry,
)

automation_action_duration_seconds = Histogram(
    "arise_automation_action_duration_seconds",
    "Automation action duration",
    ["backend", "action"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
    registry=metrics_registry,
)

automation_element_confidence = Histogram(
    "arise_automation_element_confidence",
    "Element detection confidence",
    ["backend"],
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99],
    registry=metrics_registry,
)

automation_fallback_total = Counter(
    "arise_automation_fallback_total",
    "Total perception fallback activations",
    ["from_backend", "to_backend", "reason"],
    registry=metrics_registry,
)

automation_screenshots_total = Counter(
    "arise_automation_screenshots_total",
    "Total screenshots captured",
    ["backend"],
    registry=metrics_registry,
)

automation_ocr_total = Counter(
    "arise_automation_ocr_total",
    "Total OCR operations",
    ["backend", "result"],
    registry=metrics_registry,
)


# ============================================================
# Agent System Metrics
# ============================================================

agent_delegations_total = Counter(
    "arise_agent_delegations_total",
    "Total agent delegations",
    ["from_role", "to_role", "result"],
    registry=metrics_registry,
)

agent_delegation_duration_seconds = Histogram(
    "arise_agent_delegation_duration_seconds",
    "Agent delegation duration",
    ["from_role", "to_role"],
    buckets=[0.5, 1, 2.5, 5, 10, 30, 60, 120, 300, 600],
    registry=metrics_registry,
)

agent_verifications_total = Counter(
    "arise_agent_verifications_total",
    "Total agent verifications",
    ["verifier_role", "result"],  # result: passed, failed, warning
    registry=metrics_registry,
)

agent_verification_duration_seconds = Histogram(
    "arise_agent_verification_duration_seconds",
    "Agent verification duration",
    ["verifier_role"],
    buckets=[1, 5, 10, 30, 60, 120, 300, 600],
    registry=metrics_registry,
)

agent_health = Gauge(
    "arise_agent_health",
    "Agent health score (0-1)",
    ["agent_id", "role"],
    registry=metrics_registry,
)

agent_load = Gauge(
    "arise_agent_load",
    "Agent current load",
    ["agent_id", "role"],
    registry=metrics_registry,
)

agent_restarts_total = Counter(
    "arise_agent_restarts_total",
    "Total agent restarts",
    ["role", "reason"],
    registry=metrics_registry,
)

agent_coordinator_tasks_total = Counter(
    "arise_agent_coordinator_tasks_total",
    "Tasks handled by coordinator",
    ["result"],
    registry=metrics_registry,
)


# ============================================================
# Database Metrics
# ============================================================

db_connections_active = Gauge(
    "arise_db_connections_active",
    "Active database connections",
    ["pool"],
    registry=metrics_registry,
)

db_connections_idle = Gauge(
    "arise_db_connections_idle",
    "Idle database connections",
    ["pool"],
    registry=metrics_registry,
)

db_query_duration_seconds = Histogram(
    "arise_db_query_duration_seconds",
    "Database query duration",
    ["operation", "table"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
    registry=metrics_registry,
)

db_query_total = Counter(
    "arise_db_query_total",
    "Total database queries",
    ["operation", "table", "result"],
    registry=metrics_registry,
)

db_migration_duration_seconds = Histogram(
    "arise_db_migration_duration_seconds",
    "Database migration duration",
    buckets=[1, 5, 10, 30, 60, 120, 300, 600],
    registry=metrics_registry,
)


# ============================================================
# Event Bus Metrics
# ============================================================

event_bus_events_published_total = Counter(
    "arise_event_bus_events_published_total",
    "Total events published to event bus",
    ["event_type", "bus_type"],  # bus_type: local, distributed
    registry=metrics_registry,
)

event_bus_events_processed_total = Counter(
    "arise_event_bus_events_processed_total",
    "Total events processed",
    ["event_type", "handler", "result"],
    registry=metrics_registry,
)

event_bus_processing_duration_seconds = Histogram(
    "arise_event_bus_processing_duration_seconds",
    "Event processing duration",
    ["event_type"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
    registry=metrics_registry,
)

event_bus_queue_depth = Gauge(
    "arise_event_bus_queue_depth",
    "Event bus queue depth",
    ["bus_type"],
    registry=metrics_registry,
)

event_bus_dead_letter_size = Gauge(
    "arise_event_bus_dead_letter_size",
    "Dead letter queue size",
    ["bus_type"],
    registry=metrics_registry,
)


# ============================================================
# Resource Metrics
# ============================================================

process_cpu_seconds_total = Counter(
    "arise_process_cpu_seconds_total",
    "Total CPU time used",
    ["mode"],  # user, system
    registry=metrics_registry,
)

process_memory_bytes = Gauge(
    "arise_process_memory_bytes",
    "Process memory usage",
    ["type"],  # rss, vms, heap
    registry=metrics_registry,
)

process_open_fds = Gauge(
    "arise_process_open_fds",
    "Open file descriptors",
    registry=metrics_registry,
)

process_threads = Gauge(
    "arise_process_threads",
    "Number of threads",
    registry=metrics_registry,
)

disk_usage_bytes = Gauge(
    "arise_disk_usage_bytes",
    "Disk usage",
    ["path", "type"],  # type: total, used, free
    registry=metrics_registry,
)

network_bytes_total = Counter(
    "arise_network_bytes_total",
    "Network bytes transferred",
    ["direction", "interface"],  # direction: sent, received
    registry=metrics_registry,
)


# ============================================================
# Error Metrics
# ============================================================

errors_total = Counter(
    "arise_errors_total",
    "Total errors by type",
    ["component", "error_code", "recoverable"],
    registry=metrics_registry,
)

error_recovery_total = Counter(
    "arise_error_recovery_total",
    "Total error recovery attempts",
    ["component", "error_code", "result"],
    registry=metrics_registry,
)

retry_attempts_total = Counter(
    "arise_retry_attempts_total",
    "Total retry attempts",
    ["component", "attempt"],
    registry=metrics_registry,
)

circuit_breaker_state = Gauge(
    "arise_circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=half-open, 2=open)",
    ["circuit_name"],
    registry=metrics_registry,
)

circuit_breaker_transitions_total = Counter(
    "arise_circuit_breaker_transitions_total",
    "Circuit breaker state transitions",
    ["circuit_name", "from_state", "to_state"],
    registry=metrics_registry,
)

saga_executions_total = Counter(
    "arise_saga_executions_total",
    "Total saga executions",
    ["saga_name", "result"],
    registry=metrics_registry,
)

saga_compensations_total = Counter(
    "arise_saga_compensations_total",
    "Total saga compensations",
    ["saga_name", "step"],
    registry=metrics_registry,
)


# ============================================================
# Metric Decorators
# ============================================================

def track_http_metrics(
    method: str = "",
    endpoint: str = "",
) -> Callable:
    """
    Decorator to track HTTP request metrics.

    Usage:
        @app.get("/api/tasks")
        @track_http_metrics("GET", "/api/tasks")
        async def get_tasks():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract request if available
            request = kwargs.get("request")
            if request:
                actual_method = request.method
                actual_endpoint = request.url.path
            else:
                actual_method = method or "UNKNOWN"
                actual_endpoint = endpoint or "UNKNOWN"

            http_requests_in_flight.labels(
                method=actual_method,
                endpoint=actual_endpoint,
            ).inc()

            start_time = time.perf_counter()
            status = 500

            try:
                result = await func(*args, **kwargs)

                # Extract status code from response
                if hasattr(result, "status_code"):
                    status = result.status_code
                elif isinstance(result, tuple) and len(result) == 2:
                    status = result[1] if isinstance(result[1], int) else 200
                else:
                    status = 200

                return result

            except Exception as e:
                status = getattr(e, "status_code", 500)
                raise

            finally:
                duration = time.perf_counter() - start_time

                http_requests_in_flight.labels(
                    method=actual_method,
                    endpoint=actual_endpoint,
                ).dec()

                http_requests_total.labels(
                    method=actual_method,
                    endpoint=actual_endpoint,
                    status=str(status),
                ).inc()

                http_request_duration_seconds.labels(
                    method=actual_method,
                    endpoint=actual_endpoint,
                ).observe(duration)

        return wrapper
    return decorator


def track_task_metrics(task_kind: str = "") -> Callable:
    """
    Decorator to track task execution metrics.

    Usage:
        @track_task_metrics("shell.exec")
        async def execute_shell_task(task):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            kind = task_kind or func.__name__

            task_active_total.labels(task_kind=kind).inc()
            start_time = time.perf_counter()
            status = "failed"

            try:
                result = await func(*args, **kwargs)
                status = "completed"
                return result

            except Exception as e:
                status = "failed"
                raise

            finally:
                duration = time.perf_counter() - start_time
                task_active_total.labels(task_kind=kind).dec()
                task_duration_seconds.labels(
                    task_kind=kind,
                    status=status,
                ).observe(duration)
                task_completed_total.labels(
                    task_kind=kind,
                    status=status,
                ).inc()

        return wrapper
    return decorator


def track_model_metrics(provider: str = "", model: str = "") -> Callable:
    """
    Decorator to track model request metrics.

    Usage:
        @track_model_metrics("openai", "gpt-4o")
        async def call_model(prompt):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            prov = provider or "unknown"
            mod = model or "unknown"

            start_time = time.perf_counter()
            result = "error"
            tokens = 0
            cost = 0.0

            try:
                response = await func(*args, **kwargs)
                result = "success"

                # Extract token/cost info if available
                if hasattr(response, "usage"):
                    tokens = getattr(response.usage, "total_tokens", 0)
                if hasattr(response, "cost"):
                    cost = response.cost

                return response

            except Exception as e:
                result = "error"
                raise

            finally:
                duration = time.perf_counter() - start_time

                model_request_duration_seconds.labels(
                    provider=prov,
                    model=mod,
                ).observe(duration)

                model_requests_total.labels(
                    provider=prov,
                    model=mod,
                    result=result,
                ).inc()

                if tokens:
                    model_tokens_total.labels(
                        provider=prov,
                        model=mod,
                        type="total",
                    ).inc(tokens)

                if cost:
                    model_cost_total.labels(
                        provider=prov,
                        model=mod,
                    ).inc(cost)

        return wrapper
    return decorator


# ============================================================
# Context Managers for Timing
# ============================================================

@contextmanager
def measure_http_latency(method: str, endpoint: str):
    """Context manager to measure HTTP request latency."""
    start_time = time.perf_counter()
    http_requests_in_flight.labels(method=method, endpoint=endpoint).inc()
    try:
        yield
    finally:
        duration = time.perf_counter() - start_time
        http_requests_in_flight.labels(method=method, endpoint=endpoint).dec()
        http_request_duration_seconds.labels(method=method, endpoint=endpoint).observe(duration)


@contextmanager
def measure_task_duration(task_kind: str, status: str = "completed"):
    """Context manager to measure task duration."""
    start_time = time.perf_counter()
    task_active_total.labels(task_kind=task_kind).inc()
    try:
        yield
    finally:
        duration = time.perf_counter() - start_time
        task_active_total.labels(task_kind=task_kind).dec()
        task_duration_seconds.labels(task_kind=task_kind, status=status).observe(duration)
        task_completed_total.labels(task_kind=task_kind, status=status).inc()


@contextmanager
def measure_model_latency(provider: str, model: str, result: str = "success"):
    """Context manager to measure model request latency."""
    start_time = time.perf_counter()
    try:
        yield
    finally:
        duration = time.perf_counter() - start_time
        model_request_duration_seconds.labels(provider=provider, model=model).observe(duration)
        model_requests_total.labels(provider=provider, model=model, result=result).inc()


# ============================================================
# Metrics Endpoint
# ============================================================

async def metrics_endpoint() -> Response:
    """Prometheus metrics endpoint."""
    return Response(
        content=generate_latest(metrics_registry),
        media_type=CONTENT_TYPE_LATEST,
    )


def get_metrics_registry() -> CollectorRegistry:
    """Get the metrics registry."""
    return metrics_registry


# ============================================================
# Resource Metrics Collection
# ============================================================

def collect_process_metrics() -> None:
    """Collect process-level metrics (CPU, memory, etc.)."""
    try:
        import psutil
        import os

        process = psutil.Process(os.getpid())

        # CPU
        cpu_times = process.cpu_times()
        process_cpu_seconds_total.labels(mode="user").inc(cpu_times.user)
        process_cpu_seconds_total.labels(mode="system").inc(cpu_times.system)

        # Memory
        mem_info = process.memory_info()
        process_memory_bytes.labels(type="rss").set(mem_info.rss)
        process_memory_bytes.labels(type="vms").set(mem_info.vms)

        # File descriptors (Unix only)
        try:
            process_open_fds.set(process.num_fds())
        except AttributeError:
            pass  # Windows doesn't have num_fds

        # Threads
        process_threads.set(process.num_threads())

    except ImportError:
        pass  # psutil not available
    except Exception:
        pass  # Ignore collection errors


def collect_disk_metrics(path: str = ".") -> None:
    """Collect disk usage metrics."""
    try:
        import shutil
        usage = shutil.disk_usage(path)
        disk_usage_bytes.labels(path=path, type="total").set(usage.total)
        disk_usage_bytes.labels(path=path, type="used").set(usage.used)
        disk_usage_bytes.labels(path=path, type="free").set(usage.free)
    except Exception:
        pass


# ============================================================
# Startup/Shutdown Helpers
# ============================================================

async def start_metrics_collection(interval: int = 30) -> None:
    """Start periodic metrics collection."""
    import asyncio

    async def collect_loop():
        while True:
            try:
                collect_process_metrics()
                collect_disk_metrics()
            except Exception:
                pass
            await asyncio.sleep(interval)

    task = asyncio.create_task(collect_loop())
    return task


# Example usage
if __name__ == "__main__":
    # Test metrics
    import asyncio

    async def test():
        # Track HTTP
        with measure_http_latency("GET", "/api/test"):
            await asyncio.sleep(0.1)

        # Track task
        with measure_task_duration("shell.exec"):
            await asyncio.sleep(0.05)

        # Track model
        with measure_model_latency("openai", "gpt-4o"):
            await asyncio.sleep(0.2)

        # Check metrics output
        from prometheus_client import generate_latest
        print(generate_latest(metrics_registry).decode())

    asyncio.run(test())