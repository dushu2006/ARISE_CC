# core/runtime/main.py
"""
ARISE FastAPI Application - Main entry point.

Provides:
- FastAPI app with lifespan management
- All middleware (CORS, correlation ID, error handling)
- API router registration
- Startup/shutdown event handlers
"""

from __future__ import annotations
import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

from core.config import get_config_loader
from core.database import close_db as close_database, init_db as init_database
from core.errors.factory import (
    AriseError,
    capability_denied,
    create_error_context,
)
from core.errors.result import Result
from core.events import (
    close_event_store,
    get_event_bus,
    get_event_store,
    get_event_tracer,
    init_event_bus,
    init_event_store,
    init_event_tracer,
    shutdown_event_bus,
)
from core.structured_logging import log_structured, setup_logging
from core.metrics import get_metrics_registry, metrics_endpoint
from core.runtime.config_api import router as config_router
from core.runtime.health import router as health_router
from core.runtime.http_error_handler import register_http_exception_handlers
from core.runtime.ws_error_handler import register_websocket_exception_handlers
from core.runtime.websocket import websocket_endpoint, start_event_forwarding, stop_event_forwarding

# Import API routers
from core.runtime.api.tasks import router as tasks_router
from core.runtime.api.memory import router as memory_router
from core.runtime.api.voice import router as voice_router
from core.runtime.api.agents import router as agents_router
from core.runtime.api.automation import router as automation_router
from core.runtime.api.models import router as models_router
from core.runtime.api.policy import router as policy_router

# Task Engine
from core.task_engine import init_task_engine, shutdown_task_engine, TaskEngineConfig
from core.task_engine.executor import SandboxConfig

# Policy Engine
from core.policy_engine import init_policy_engine, shutdown_policy_engine

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager.

    Handles startup and shutdown of all core services.
    """
    import logging
    logger = logging.getLogger("arise.runtime")

    # Startup
    log_structured(logger, logging.INFO, "Starting ARISE application")

    try:
        # Load configuration
        config_loader = get_config_loader()
        config = config_loader.load()
        log_structured(logger, logging.INFO, "Configuration loaded", environment=config.environment.value)

        # Setup logging
        setup_logging(
            level=config.telemetry.logging.level.value,
            json_output=config.telemetry.logging.format == "json",
            log_file=config.telemetry.logging.output if config.telemetry.logging.output != "stdout" else None,
        )
        log_structured(logger, logging.INFO, "Logging configured")

        # Initialize database
        await init_database(config.database.url)
        log_structured(logger, logging.INFO, "Database initialized")

        # Initialize event store
        from core.events.store import EventStoreConfig as StoreEventStoreConfig
        store_config = StoreEventStoreConfig(
            db_path=config.events.store.path,
            wal_mode=config.events.store.wal_mode,
        )
        init_event_store(store_config)
        log_structured(logger, logging.INFO, "Event store initialized")

        # Initialize event bus
        await init_event_bus(
            worker_count=config.events.local.worker_count,
            queue_maxsize=config.events.local.queue_size,
            dead_letter_maxsize=config.events.local.dead_letter_queue_size,
        )
        log_structured(logger, logging.INFO, "Event bus initialized")

        # Initialize event tracer
        init_event_tracer(config.events.tracing.service_name)
        log_structured(logger, logging.INFO, "Event tracer initialized")

        # Start event bus workers
        bus = await get_event_bus()
        if bus:
            log_structured(logger, logging.INFO, "Event bus workers started", worker_count=bus.worker_count)

        # Initialize projections
        from core.events import init_projections
        await init_projections()
        log_structured(logger, logging.INFO, "Projections initialized")

        # Register default event handlers
        from core.events import register_default_handlers
        register_default_handlers()
        log_structured(logger, logging.INFO, "Default event handlers registered")

        # Initialize Task Engine
        task_engine_config = TaskEngineConfig(
            max_concurrent_tasks=config.task_engine.max_concurrent_tasks,
            default_priority=config.task_engine.default_priority,
            checkpoint_interval_seconds=config.task_engine.checkpoint_interval_seconds,
            max_checkpoints_per_task=config.task_engine.max_checkpoints_per_task,
            task_timeout_seconds=config.task_engine.task_timeout_seconds,
            sandbox=SandboxConfig(
                type=config.task_engine.sandbox.type,
                docker_image=config.task_engine.sandbox.docker_image,
                memory_limit_mb=config.task_engine.sandbox.memory_limit_mb,
                cpu_limit_percent=config.task_engine.sandbox.cpu_limit_percent,
                disk_limit_mb=config.task_engine.sandbox.disk_limit_mb,
                network_enabled=config.task_engine.sandbox.network_enabled,
                timeout_seconds=config.task_engine.sandbox.timeout_seconds,
            ),
            queue_priority_levels=config.task_engine.queue_priority_levels,
            fair_scheduling=config.task_engine.fair_scheduling,
            persistence_enabled=config.task_engine.persistence_enabled,
        )
        await init_task_engine(task_engine_config)
        log_structured(logger, logging.INFO, "Task engine initialized")

        # Initialize Policy Engine
        policy_engine_config = config.policy_engine
        await init_policy_engine(policy_engine_config)
        log_structured(logger, logging.INFO, "Policy engine initialized")

        # Store config in app state for access in routes
        app.state.config = config
        app.state.config_loader = config_loader

        log_structured(logger, logging.INFO, "ARISE application startup complete")

    except Exception as e:
        log_structured(logger, logging.ERROR, "Startup failed", error=str(e))
        raise

    yield

    # Shutdown
    log_structured(logger, logging.INFO, "Shutting down ARISE application")

    try:
        # Shutdown Policy Engine
        await shutdown_policy_engine()
        log_structured(logger, logging.INFO, "Policy engine stopped")

        # Shutdown Task Engine
        await shutdown_task_engine()
        log_structured(logger, logging.INFO, "Task engine stopped")

        # Stop event bus
        await shutdown_event_bus()
        log_structured(logger, logging.INFO, "Event bus stopped")

        # Close event store
        close_event_store()
        log_structured(logger, logging.INFO, "Event store closed")

        # Close database
        await close_database()
        log_structured(logger, logging.INFO, "Database closed")

        log_structured(logger, logging.INFO, "ARISE application shutdown complete")

    except Exception as e:
        log_structured(logger, logging.ERROR, "Shutdown error", error=str(e))


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.

    Returns:
        Configured FastAPI instance
    """
    # Load config early for app metadata
    config_loader = get_config_loader()
    config = config_loader.load()

    app = FastAPI(
        title="ARISE API",
        description="ARISE - AI-Powered Automation Platform",
        version="1.0.0",
        docs_url="/docs" if config.environment != "production" else None,
        redoc_url="/redoc" if config.environment != "production" else None,
        openapi_url="/openapi.json" if config.environment != "production" else None,
        lifespan=lifespan,
    )

    # Store config in app state
    app.state.config = config
    app.state.config_loader = config_loader

    # ============================================================
    # Middleware (order matters - first added = outermost)
    # ============================================================

    # Trusted host middleware (security)
    if config.security.trusted_hosts:
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=config.security.trusted_hosts,
        )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.security.cors_origins or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Correlation-ID", "X-Request-ID"],
    )

    # Correlation ID middleware
    @app.middleware("http")
    async def correlation_id_middleware(request: Request, call_next):
        """Add correlation ID to request and response headers."""
        import uuid
        from core.events.tracing import correlation_context, inject_trace_headers

        # Extract or generate correlation ID
        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())[:12]

        # Set in context
        with correlation_context(correlation_id):
            # Process request
            response = await call_next(request)

            # Add to response headers
            response.headers["X-Correlation-ID"] = correlation_id

            return response

    # Request logging middleware
    @app.middleware("http")
    async def request_logging_middleware(request: Request, call_next):
        """Log all HTTP requests."""
        import time
        import logging
        logger = logging.getLogger("arise.runtime")

        start_time = time.perf_counter()

        # Log request
        log_structured(
            logger,
            logging.INFO,
            "HTTP request",
            method=request.method,
            path=request.url.path,
            query_params=dict(request.query_params),
            client_host=request.client.host if request.client else None,
        )

        try:
            response = await call_next(request)

            # Log response
            duration_ms = (time.perf_counter() - start_time) * 1000
            log_structured(
                logger,
                logging.INFO,
                "HTTP response",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=round(duration_ms, 2),
            )

            return response

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            log_structured(
                logger,
                logging.ERROR,
                "HTTP request failed",
                method=request.method,
                path=request.url.path,
                error=str(e),
                duration_ms=round(duration_ms, 2),
            )
            raise

    # ============================================================
    # Exception Handlers
    # ============================================================

    # Register HTTP exception handlers
    register_http_exception_handlers(app)

    # Register WebSocket exception handlers
    register_websocket_exception_handlers(app)

    # Generic exception handler for unhandled errors
    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Handle any unhandled exceptions."""
        from core.events.tracing import get_correlation_id
        import logging

        correlation_id = get_correlation_id() or "unknown"
        logger = logging.getLogger("arise.runtime")

        log_structured(
            logger,
            logging.ERROR,
            "Unhandled exception",
            path=request.url.path,
            method=request.method,
            error=str(exc),
            correlation_id=correlation_id,
        )

        # Don't expose internal errors in production
        if config.environment == "production":
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Internal server error",
                    "correlation_id": correlation_id,
                },
            )
        else:
            return JSONResponse(
                status_code=500,
                content={
                    "error": str(exc),
                    "type": type(exc).__name__,
                    "correlation_id": correlation_id,
                },
            )

    # ============================================================
    # API Routers
    # ============================================================

    # Health and metrics (always available)
    app.include_router(health_router)
    app.include_router(config_router)

    # Metrics endpoint (Prometheus)
    app.add_api_route(
        "/metrics",
        metrics_endpoint,
        methods=["GET"],
        include_in_schema=False,
    )

    # Core API routers
    app.include_router(tasks_router, prefix="/api/v1")
    app.include_router(memory_router, prefix="/api/v1")
    app.include_router(voice_router, prefix="/api/v1")
    app.include_router(agents_router, prefix="/api/v1")
    app.include_router(automation_router, prefix="/api/v1")
    app.include_router(models_router, prefix="/api/v1")
    app.include_router(policy_router, prefix="/api/v1")

    # ============================================================
    # Root Endpoints
    # ============================================================

    @app.get("/", include_in_schema=False)
    async def root():
        """Root endpoint with basic info."""
        return {
            "name": "ARISE API",
            "version": "1.0.0",
            "description": "AI-Powered Automation Platform",
            "docs": "/docs",
            "health": "/api/v1/health/health",
            "metrics": "/metrics",
        }

    @app.get("/version", include_in_schema=False)
    async def version():
        """Version endpoint."""
        return {
            "version": "1.0.0",
            "build": os.getenv("BUILD_VERSION", "dev"),
            "commit": os.getenv("BUILD_COMMIT", "unknown"),
        }

    # ============================================================
    # WebSocket endpoint
    # ============================================================

    @app.websocket("/ws")
    async def websocket_route(websocket):
        await websocket_endpoint(websocket)

    # Start event forwarding on startup
    @app.on_event("startup")
    async def start_event_forwarding_task():
        await start_event_forwarding()

    # Stop event forwarding on shutdown
    @app.on_event("shutdown")
    async def stop_event_forwarding_task():
        await stop_event_forwarding()

    return app


# Create the app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    config_loader = get_config_loader()
    config = config_loader.load()

    uvicorn.run(
        "core.runtime.main:app",
        host=config.server.host,
        port=config.server.port,
        reload=config.environment == "development",
        log_config=None,  # We use our own logging
    )