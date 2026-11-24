# core/runtime/health.py
"""
Health Check Endpoints - Kubernetes-ready health probes.

Provides:
- /health - Comprehensive health check (DB, Redis, models, disk, memory, event bus)
- /ready - Kubernetes readiness probe (DB + Redis only)
- /live - Kubernetes liveness probe (basic process health)
"""

from __future__ import annotations
import asyncio
import os
import platform
import shutil
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from core.database import get_session_factory, check_database_health as db_health_check
from core.events import get_event_bus, LocalEventBus
from core.structured_logging import log_structured
from core.metrics import get_metrics_registry

# Try to import Redis, but don't fail if not available
try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

# Try to import psutil for process metrics
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

router = APIRouter(prefix="/api/v1/health", tags=["health"])


class HealthStatus(str, Enum):
    """Health status levels."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class ComponentHealth(BaseModel):
    """Health status for a single component."""
    name: str
    status: HealthStatus
    message: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)
    latency_ms: Optional[float] = None


class HealthResponse(BaseModel):
    """Full health check response."""
    status: HealthStatus
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    version: str = "1.0.0"
    uptime_seconds: float
    components: List[ComponentHealth] = Field(default_factory=list)
    system: Dict[str, Any] = Field(default_factory=dict)


class ReadinessResponse(BaseModel):
    """Readiness probe response."""
    ready: bool
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    checks: Dict[str, bool] = Field(default_factory=dict)


class LivenessResponse(BaseModel):
    """Liveness probe response."""
    alive: bool
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    pid: int


@dataclass
class HealthChecker:
    """Performs health checks on all system components."""

    start_time: float = field(default_factory=time.time)
    redis_url: str = "redis://localhost:6379"
    redis_client: Optional[Any] = None

    async def check_database(self) -> ComponentHealth:
        """Check database connectivity and basic query."""
        start = time.perf_counter()
        try:
            healthy = await db_health_check()
            latency = (time.perf_counter() - start) * 1000

            if healthy:
                return ComponentHealth(
                    name="database",
                    status=HealthStatus.HEALTHY,
                    message="Database connection successful",
                    latency_ms=latency,
                )
            else:
                return ComponentHealth(
                    name="database",
                    status=HealthStatus.UNHEALTHY,
                    message="Database health check failed",
                    latency_ms=latency,
                )
        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            return ComponentHealth(
                name="database",
                status=HealthStatus.UNHEALTHY,
                message=f"Database error: {str(e)}",
                latency_ms=latency,
            )

    async def check_redis(self) -> ComponentHealth:
        """Check Redis connectivity."""
        if not REDIS_AVAILABLE:
            return ComponentHealth(
                name="redis",
                status=HealthStatus.DEGRADED,
                message="Redis client not installed",
            )

        start = time.perf_counter()
        try:
            if self.redis_client is None:
                self.redis_client = redis.from_url(
                    self.redis_url,
                    socket_connect_timeout=2,
                    socket_timeout=2,
                )

            await self.redis_client.ping()
            latency = (time.perf_counter() - start) * 1000

            return ComponentHealth(
                name="redis",
                status=HealthStatus.HEALTHY,
                message="Redis connection successful",
                latency_ms=latency,
            )
        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            return ComponentHealth(
                name="redis",
                status=HealthStatus.UNHEALTHY,
                message=f"Redis error: {str(e)}",
                latency_ms=latency,
            )

    async def check_event_bus(self) -> ComponentHealth:
        """Check local event bus health."""
        start = time.perf_counter()
        try:
            bus = get_event_bus()
            if bus is None:
                return ComponentHealth(
                    name="event_bus",
                    status=HealthStatus.DEGRADED,
                    message="Event bus not initialized",
                )

            # Check queue depth
            queue_size = bus.queue.qsize() if hasattr(bus, 'queue') else 0
            worker_count = len(bus._workers) if hasattr(bus, '_workers') else 0
            active_workers = sum(1 for w in bus._workers if not w.done()) if hasattr(bus, '_workers') else 0

            latency = (time.perf_counter() - start) * 1000

            if active_workers > 0:
                status = HealthStatus.HEALTHY
                message = f"Event bus running ({active_workers}/{worker_count} workers active)"
            else:
                status = HealthStatus.DEGRADED
                message = f"Event bus has no active workers ({worker_count} configured)"

            return ComponentHealth(
                name="event_bus",
                status=status,
                message=message,
                details={
                    "queue_size": queue_size,
                    "configured_workers": worker_count,
                    "active_workers": active_workers,
                },
                latency_ms=latency,
            )
        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            return ComponentHealth(
                name="event_bus",
                status=HealthStatus.UNHEALTHY,
                message=f"Event bus error: {str(e)}",
                latency_ms=latency,
            )

    async def check_disk_space(self) -> ComponentHealth:
        """Check available disk space."""
        start = time.perf_counter()
        try:
            # Check current working directory disk
            usage = shutil.disk_usage(".")
            free_gb = usage.free / (1024**3)
            total_gb = usage.total / (1024**3)
            used_percent = (usage.used / usage.total) * 100

            latency = (time.perf_counter() - start) * 1000

            if used_percent > 95:
                status = HealthStatus.UNHEALTHY
                message = f"Critical: {used_percent:.1f}% disk used ({free_gb:.1f}GB free)"
            elif used_percent > 85:
                status = HealthStatus.DEGRADED
                message = f"Warning: {used_percent:.1f}% disk used ({free_gb:.1f}GB free)"
            else:
                status = HealthStatus.HEALTHY
                message = f"Disk OK: {used_percent:.1f}% used ({free_gb:.1f}GB free)"

            return ComponentHealth(
                name="disk",
                status=status,
                message=message,
                details={
                    "total_gb": round(total_gb, 2),
                    "used_gb": round((usage.used / (1024**3)), 2),
                    "free_gb": round(free_gb, 2),
                    "used_percent": round(used_percent, 1),
                },
                latency_ms=latency,
            )
        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            return ComponentHealth(
                name="disk",
                status=HealthStatus.UNHEALTHY,
                message=f"Disk check error: {str(e)}",
                latency_ms=latency,
            )

    async def check_memory(self) -> ComponentHealth:
        """Check system memory."""
        if not PSUTIL_AVAILABLE:
            return ComponentHealth(
                name="memory",
                status=HealthStatus.DEGRADED,
                message="psutil not available for memory check",
            )

        start = time.perf_counter()
        try:
            mem = psutil.virtual_memory()
            used_percent = mem.percent
            available_gb = mem.available / (1024**3)
            total_gb = mem.total / (1024**3)

            latency = (time.perf_counter() - start) * 1000

            if used_percent > 95:
                status = HealthStatus.UNHEALTHY
                message = f"Critical: {used_percent:.1f}% memory used ({available_gb:.1f}GB available)"
            elif used_percent > 85:
                status = HealthStatus.DEGRADED
                message = f"Warning: {used_percent:.1f}% memory used ({available_gb:.1f}GB available)"
            else:
                status = HealthStatus.HEALTHY
                message = f"Memory OK: {used_percent:.1f}% used ({available_gb:.1f}GB available)"

            return ComponentHealth(
                name="memory",
                status=status,
                message=message,
                details={
                    "total_gb": round(total_gb, 2),
                    "available_gb": round(available_gb, 2),
                    "used_percent": round(used_percent, 1),
                },
                latency_ms=latency,
            )
        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            return ComponentHealth(
                name="memory",
                status=HealthStatus.UNHEALTHY,
                message=f"Memory check error: {str(e)}",
                latency_ms=latency,
            )

    async def check_model_providers(self) -> ComponentHealth:
        """Check model provider availability (placeholder)."""
        start = time.perf_counter()
        try:
            # This would check actual provider health in a real implementation
            # For now, return healthy as a placeholder
            latency = (time.perf_counter() - start) * 1000

            return ComponentHealth(
                name="model_providers",
                status=HealthStatus.HEALTHY,
                message="Model providers configured (health checks not implemented)",
                details={
                    "providers": ["openai", "anthropic", "gemini", "ollama"],
                    "note": "Health checks implemented in model router",
                },
                latency_ms=latency,
            )
        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            return ComponentHealth(
                name="model_providers",
                status=HealthStatus.DEGRADED,
                message=f"Model provider check error: {str(e)}",
                latency_ms=latency,
            )

    async def check_task_engine(self) -> ComponentHealth:
        """Check task engine status (placeholder)."""
        start = time.perf_counter()
        try:
            latency = (time.perf_counter() - start) * 1000

            return ComponentHealth(
                name="task_engine",
                status=HealthStatus.HEALTHY,
                message="Task engine initialized (detailed health in task engine metrics)",
                latency_ms=latency,
            )
        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            return ComponentHealth(
                name="task_engine",
                status=HealthStatus.DEGRADED,
                message=f"Task engine check error: {str(e)}",
                latency_ms=latency,
            )

    def get_system_info(self) -> Dict[str, Any]:
        """Get system information."""
        info = {
            "platform": platform.platform(),
            "python_version": sys.version.split()[0],
            "hostname": platform.node(),
            "pid": os.getpid(),
            "cpu_count": os.cpu_count(),
        }

        if PSUTIL_AVAILABLE:
            try:
                process = psutil.Process(os.getpid())
                info.update({
                    "process_memory_mb": round(process.memory_info().rss / (1024**2), 2),
                    "process_cpu_percent": process.cpu_percent(),
                    "thread_count": process.num_threads(),
                    "open_files": len(process.open_files()),
                })
            except Exception:
                pass

        return info

    async def run_all_checks(self) -> List[ComponentHealth]:
        """Run all health checks in parallel."""
        checks = await asyncio.gather(
            self.check_database(),
            self.check_redis(),
            self.check_event_bus(),
            self.check_disk_space(),
            self.check_memory(),
            self.check_model_providers(),
            self.check_task_engine(),
            return_exceptions=True,
        )

        results = []
        for check in checks:
            if isinstance(check, ComponentHealth):
                results.append(check)
            elif isinstance(check, Exception):
                results.append(ComponentHealth(
                    name="unknown",
                    status=HealthStatus.UNHEALTHY,
                    message=f"Check failed with exception: {str(check)}",
                ))

        return results

    def calculate_overall_status(self, components: List[ComponentHealth]) -> HealthStatus:
        """Calculate overall health status from components."""
        if any(c.status == HealthStatus.UNHEALTHY for c in components):
            return HealthStatus.UNHEALTHY
        if any(c.status == HealthStatus.DEGRADED for c in components):
            return HealthStatus.DEGRADED
        return HealthStatus.HEALTHY


# Global health checker instance
_health_checker: Optional[HealthChecker] = None


def get_health_checker() -> HealthChecker:
    """Get global health checker instance."""
    global _health_checker
    if _health_checker is None:
        _health_checker = HealthChecker()
    return _health_checker


# ============================================================
# API Endpoints
# ============================================================

@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Comprehensive health check",
    description="Full system health check including database, Redis, event bus, disk, memory, and model providers.",
)
async def health_endpoint(
    checker: HealthChecker = Depends(get_health_checker),
) -> HealthResponse:
    """
    Comprehensive health check endpoint.

    Returns detailed status of all system components.
    Use for monitoring dashboards and detailed diagnostics.
    """
    components = await checker.run_all_checks()
    overall_status = checker.calculate_overall_status(components)
    uptime = time.time() - checker.start_time

    response = HealthResponse(
        status=overall_status,
        uptime_seconds=uptime,
        components=components,
        system=checker.get_system_info(),
    )

    # Log health check
    import logging
    logger = logging.getLogger("arise.health")
    log_structured(
        logger,
        logging.INFO,
        "Health check completed",
        status=overall_status.value,
        components={c.name: c.status.value for c in components},
        uptime_seconds=uptime,
    )

    # Set HTTP status based on health
    if overall_status == HealthStatus.UNHEALTHY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=response.model_dump(),
        )
    elif overall_status == HealthStatus.DEGRADED:
        # Still return 200 but with degraded status
        pass

    return response


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Kubernetes readiness probe",
    description="Lightweight readiness check - only verifies database and Redis connectivity.",
)
async def readiness_endpoint(
    checker: HealthChecker = Depends(get_health_checker),
) -> ReadinessResponse:
    """
    Kubernetes readiness probe.

    Only checks critical dependencies (DB + Redis).
    Returns 200 if ready, 503 if not ready.
    """
    # Run only critical checks
    db_check = await checker.check_database()
    redis_check = await checker.check_redis()

    checks = {
        "database": db_check.status == HealthStatus.HEALTHY,
        "redis": redis_check.status == HealthStatus.HEALTHY,
    }

    ready = all(checks.values())

    response = ReadinessResponse(
        ready=ready,
        checks=checks,
    )

    if not ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=response.model_dump(),
        )

    return response


@router.get(
    "/live",
    response_model=LivenessResponse,
    summary="Kubernetes liveness probe",
    description="Basic liveness check - verifies process is alive and responsive.",
)
async def liveness_endpoint() -> LivenessResponse:
    """
    Kubernetes liveness probe.

    Minimal check - just verifies the process is running.
    Should never fail unless the process is dead.
    """
    return LivenessResponse(
        alive=True,
        pid=os.getpid(),
    )


@router.get(
    "/metrics",
    summary="Prometheus metrics endpoint",
    description="Prometheus metrics in OpenMetrics format.",
)
async def metrics_endpoint() -> Response:
    """Prometheus metrics endpoint for scraping."""
    from core.metrics import generate_latest, CONTENT_TYPE_LATEST, get_metrics_registry

    return Response(
        content=generate_latest(get_metrics_registry()),
        media_type=CONTENT_TYPE_LATEST,
    )


# ============================================================
# Legacy endpoint aliases (for compatibility)
# ============================================================

@router.get(
    "/",
    response_model=HealthResponse,
    summary="Health check (alias)",
    include_in_schema=False,
)
async def health_root(
    checker: HealthChecker = Depends(get_health_checker),
) -> HealthResponse:
    """Alias for /health endpoint."""
    return await health_endpoint(checker)


# Export for easy inclusion
__all__ = [
    "router",
    "HealthStatus",
    "ComponentHealth",
    "HealthResponse",
    "ReadinessResponse",
    "LivenessResponse",
    "HealthChecker",
    "get_health_checker",
]