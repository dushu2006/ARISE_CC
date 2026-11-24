# core/runtime/http_error_handler.py
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from core.errors.base import AriseError, ErrorCode, ErrorContext
import logging

logger = logging.getLogger(__name__)


async def arise_error_handler(request: Request, exc: AriseError) -> JSONResponse:
    """Convert AriseError to HTTP response"""
    status_code = _map_status_code(exc.code)

    # Ensure context has timestamp
    if not exc.context.timestamp:
        from datetime import datetime, timezone
        exc.context.timestamp = datetime.now(timezone.utc).isoformat()

    return JSONResponse(
        status_code=status_code,
        content=exc.to_dict()["error"],
        headers={
            "X-Error-ID": exc.context.error_id,
            "X-Error-Code": exc.code.value,
        },
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Convert HTTPException to standard format"""
    from core.errors.base import AriseError, ErrorCode
    from datetime import datetime, timezone

    arise_error = AriseError(
        code=ErrorCode.INVALID_REQUEST if exc.status_code == 400 else ErrorCode.INTERNAL_ERROR,
        message=str(exc.detail),
        context=ErrorContext(
            component="http",
            operation=request.url.path,
            timestamp=datetime.now(timezone.utc).isoformat(),
        ),
    )

    return JSONResponse(
        status_code=exc.status_code,
        content=arise_error.to_dict()["error"],
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for unexpected exceptions"""
    logger.exception(f"Unhandled exception in {request.url.path}")

    from core.errors.base import AriseError, ErrorCode
    from datetime import datetime, timezone

    arise_error = AriseError(
        code=ErrorCode.INTERNAL_ERROR,
        message="Internal server error",
        context=ErrorContext(
            component="http",
            operation=request.url.path,
            timestamp=datetime.now(timezone.utc).isoformat(),
        ),
    )

    return JSONResponse(
        status_code=500,
        content=arise_error.to_dict()["error"],
    )


def _map_status_code(code: ErrorCode) -> int:
    mapping = {
        ErrorCode.INVALID_REQUEST: 400,
        ErrorCode.UNAUTHORIZED: 401,
        ErrorCode.FORBIDDEN: 403,
        ErrorCode.NOT_FOUND: 404,
        ErrorCode.CONFLICT: 409,
        ErrorCode.RATE_LIMITED: 429,
        ErrorCode.INTERNAL_ERROR: 500,
        ErrorCode.SERVICE_UNAVAILABLE: 503,
        ErrorCode.TIMEOUT: 504,
    }
    return mapping.get(code, 500)


def register_error_handlers(app):
    """Register all error handlers with FastAPI app"""
    app.add_exception_handler(AriseError, arise_error_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)


# Alias for backward compatibility
register_http_exception_handlers = register_error_handlers


# Middleware for request correlation ID
from starlette.middleware.base import BaseHTTPMiddleware
import uuid


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """Add correlation ID to requests"""

    async def dispatch(self, request: Request, call_next):
        correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4())[:12])

        # Add to request state for access in handlers
        request.state.correlation_id = correlation_id

        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        return response


# Context manager for getting correlation ID from request
def get_correlation_id(request: Request) -> str:
    """Get correlation ID from request state"""
    return getattr(request.state, "correlation_id", "")


# Helper to add error context from request
def error_context_from_request(request: Request, component: str = "", operation: str = "") -> ErrorContext:
    """Create ErrorContext from request"""
    return ErrorContext(
        component=component or "http",
        operation=operation or request.url.path,
        correlation_id=get_correlation_id(request),
    )