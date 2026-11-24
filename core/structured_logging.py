# core/logging.py
"""
Structured Logging - JSON-formatted logging with context variables.

Provides:
- StructuredFormatter for JSON output
- Context variables: correlation_id, task_id, agent_id, session_id
- Context managers for automatic context propagation
- setup_logging for configuring logging across the application
"""

from __future__ import annotations
import contextvars
import json
import logging
import logging.config
import sys
import traceback
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from pythonjsonlogger import jsonlogger

# Context variables for structured logging
_correlation_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "correlation_id", default=None
)
_task_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "task_id", default=None
)
_agent_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "agent_id", default=None
)
_session_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "session_id", default=None
)
_request_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "request_id", default=None
)
_user_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "user_id", default=None
)


class StructuredFormatter(jsonlogger.JsonFormatter):
    """
    JSON log formatter with automatic context variable inclusion.

    Adds standard fields:
    - timestamp: ISO format timestamp
    - level: Log level name
    - logger: Logger name
    - message: Log message
    - correlation_id: From context
    - task_id: From context
    - agent_id: From context
    - session_id: From context
    - request_id: From context
    - user_id: From context
    - extra: Any additional fields from log record
    """

    def __init__(
        self,
        fmt: str = "%(timestamp)s %(level)s %(logger)s %(message)s",
        include_extra: bool = True,
        **kwargs,
    ):
        super().__init__(fmt, **kwargs)
        self.include_extra = include_extra

    def add_fields(self, log_record: dict[str, Any], record: logging.LogRecord, message_dict: dict[str, Any]) -> None:
        super().add_fields(log_record, record, message_dict)

        # Add standard fields
        log_record["timestamp"] = datetime.now(timezone.utc).isoformat()
        log_record["level"] = record.levelname
        log_record["logger"] = record.name

        # Add context variables
        log_record["correlation_id"] = get_correlation_id() or "-"
        log_record["task_id"] = get_task_id() or "-"
        log_record["agent_id"] = get_agent_id() or "-"
        log_record["session_id"] = get_session_id() or "-"
        log_record["request_id"] = get_request_id() or "-"
        log_record["user_id"] = get_user_id() or "-"

        # Add exception info if present
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)

        # Add extra fields from record
        if self.include_extra:
            for key, value in record.__dict__.items():
                if key not in {
                    "name", "msg", "args", "levelname", "levelno", "pathname",
                    "filename", "module", "lineno", "funcName", "created",
                    "msecs", "relativeCreated", "thread", "threadName",
                    "processName", "process", "exc_info", "exc_text",
                    "stack_info", "getMessage",
                }:
                    log_record[key] = value


class StructuredLogRecord(logging.LogRecord):
    """Log record that automatically includes context variables."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Context variables are added by the formatter


def get_correlation_id() -> Optional[str]:
    """Get current correlation ID from context."""
    return _correlation_id_var.get()


def set_correlation_id(correlation_id: str) -> contextvars.Token:
    """Set correlation ID in context."""
    return _correlation_id_var.set(correlation_id)


def get_task_id() -> Optional[str]:
    """Get current task ID from context."""
    return _task_id_var.get()


def set_task_id(task_id: str) -> contextvars.Token:
    """Set task ID in context."""
    return _task_id_var.set(task_id)


def get_agent_id() -> Optional[str]:
    """Get current agent ID from context."""
    return _agent_id_var.get()


def set_agent_id(agent_id: str) -> contextvars.Token:
    """Set agent ID in context."""
    return _agent_id_var.set(agent_id)


def get_session_id() -> Optional[str]:
    """Get current session ID from context."""
    return _session_id_var.get()


def set_session_id(session_id: str) -> contextvars.Token:
    """Set session ID in context."""
    return _session_id_var.set(session_id)


def get_request_id() -> Optional[str]:
    """Get current request ID from context."""
    return _request_id_var.get()


def set_request_id(request_id: str) -> contextvars.Token:
    """Set request ID in context."""
    return _request_id_var.set(request_id)


def get_user_id() -> Optional[str]:
    """Get current user ID from context."""
    return _user_id_var.get()


def set_user_id(user_id: str) -> contextvars.Token:
    """Set user ID in context."""
    return _user_id_var.set(user_id)


def get_all_context() -> dict[str, Optional[str]]:
    """Get all context variables as a dictionary."""
    return {
        "correlation_id": get_correlation_id(),
        "task_id": get_task_id(),
        "agent_id": get_agent_id(),
        "session_id": get_session_id(),
        "request_id": get_request_id(),
        "user_id": get_user_id(),
    }


def set_all_context(context: dict[str, str]) -> list[contextvars.Token]:
    """Set all context variables from a dictionary."""
    tokens = []
    if "correlation_id" in context:
        tokens.append(set_correlation_id(context["correlation_id"]))
    if "task_id" in context:
        tokens.append(set_task_id(context["task_id"]))
    if "agent_id" in context:
        tokens.append(set_agent_id(context["agent_id"]))
    if "session_id" in context:
        tokens.append(set_session_id(context["session_id"]))
    if "request_id" in context:
        tokens.append(set_request_id(context["request_id"]))
    if "user_id" in context:
        tokens.append(set_user_id(context["user_id"]))
    return tokens


def clear_context(tokens: list[contextvars.Token]) -> None:
    """Clear context variables using tokens."""
    for token in reversed(tokens):
        try:
            _correlation_id_var.reset(token)
        except ValueError:
            try:
                _task_id_var.reset(token)
            except ValueError:
                try:
                    _agent_id_var.reset(token)
                except ValueError:
                    try:
                        _session_id_var.reset(token)
                    except ValueError:
                        try:
                            _request_id_var.reset(token)
                        except ValueError:
                            _user_id_var.reset(token)


@contextmanager
def correlation_context(correlation_id: Optional[str] = None):
    """
    Context manager for correlation ID.

    Usage:
        with correlation_context("req-123"):
            logger.info("Processing request")
            # All logs in this block will have correlation_id="req-123"
    """
    cid = correlation_id or f"corr-{datetime.now(timezone.utc).timestamp()}"
    token = set_correlation_id(cid)
    try:
        yield cid
    finally:
        _correlation_id_var.reset(token)


@contextmanager
def task_context(task_id: str, correlation_id: Optional[str] = None):
    """
    Context manager for task execution context.

    Usage:
        with task_context("task-456", correlation_id="corr-123"):
            logger.info("Task started")
            # All logs will have task_id and correlation_id
    """
    tokens = []
    tokens.append(set_task_id(task_id))
    if correlation_id:
        tokens.append(set_correlation_id(correlation_id))
    elif not get_correlation_id():
        tokens.append(set_correlation_id(f"task-{task_id}"))

    try:
        yield task_id
    finally:
        clear_context(tokens)


@contextmanager
def agent_context(agent_id: str, task_id: Optional[str] = None, correlation_id: Optional[str] = None):
    """
    Context manager for agent execution context.

    Usage:
        with agent_context("agent-789", task_id="task-456"):
            logger.info("Agent processing")
    """
    tokens = []
    tokens.append(set_agent_id(agent_id))
    if task_id:
        tokens.append(set_task_id(task_id))
    if correlation_id:
        tokens.append(set_correlation_id(correlation_id))
    elif not get_correlation_id():
        tokens.append(set_correlation_id(f"agent-{agent_id}"))

    try:
        yield agent_id
    finally:
        clear_context(tokens)


@contextmanager
def session_context(session_id: str, user_id: Optional[str] = None, correlation_id: Optional[str] = None):
    """
    Context manager for user session context.

    Usage:
        with session_context("sess-abc", user_id="user-123"):
            logger.info("Session started")
    """
    tokens = []
    tokens.append(set_session_id(session_id))
    if user_id:
        tokens.append(set_user_id(user_id))
    if correlation_id:
        tokens.append(set_correlation_id(correlation_id))
    elif not get_correlation_id():
        tokens.append(set_correlation_id(f"session-{session_id}"))

    try:
        yield session_id
    finally:
        clear_context(tokens)


@contextmanager
def request_context(request_id: str, correlation_id: Optional[str] = None, user_id: Optional[str] = None):
    """
    Context manager for HTTP request context.

    Usage:
        with request_context("req-xyz", user_id="user-123"):
            logger.info("Request received")
    """
    tokens = []
    tokens.append(set_request_id(request_id))
    if correlation_id:
        tokens.append(set_correlation_id(correlation_id))
    elif not get_correlation_id():
        tokens.append(set_correlation_id(f"req-{request_id}"))
    if user_id:
        tokens.append(set_user_id(user_id))

    try:
        yield request_id
    finally:
        clear_context(tokens)


@contextmanager
def logging_context(**context_vars: str):
    """
    Generic context manager for setting multiple logging context variables.

    Usage:
        with logging_context(correlation_id="abc", task_id="123"):
            logger.info("Context set")
    """
    tokens = set_all_context(context_vars)
    try:
        yield
    finally:
        clear_context(tokens)


class LoggingConfig:
    """Configuration for structured logging setup."""

    def __init__(
        self,
        level: str = "INFO",
        json_output: bool = True,
        include_extra: bool = True,
        log_file: Optional[str] = None,
        log_format: Optional[str] = None,
        disable_existing_loggers: bool = False,
    ):
        self.level = level.upper()
        self.json_output = json_output
        self.include_extra = include_extra
        self.log_file = log_file
        self.log_format = log_format
        self.disable_existing_loggers = disable_existing_loggers

    def get_logging_config(self) -> dict[str, Any]:
        """Generate logging configuration dictionary."""
        formatters = {
            "json": {
                "()": "core.structured_logging.StructuredFormatter",
                "include_extra": self.include_extra,
            },
            "console": {
                "format": "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        }

        if self.log_format:
            formatters["custom"] = {"format": self.log_format}

        handlers = {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "json" if self.json_output else "console",
                "stream": "ext://sys.stdout",
            },
        }

        if self.log_file:
            handlers["file"] = {
                "class": "logging.handlers.RotatingFileHandler",
                "formatter": "json" if self.json_output else "console",
                "filename": self.log_file,
                "maxBytes": 10 * 1024 * 1024,  # 10MB
                "backupCount": 5,
                "encoding": "utf-8",
            }

        return {
            "version": 1,
            "disable_existing_loggers": self.disable_existing_loggers,
            "formatters": formatters,
            "handlers": handlers,
            "root": {
                "level": self.level,
                "handlers": list(handlers.keys()),
            },
            "loggers": {
                "uvicorn": {"level": "INFO", "propagate": True},
                "uvicorn.access": {"level": "INFO", "propagate": True},
                "sqlalchemy.engine": {"level": "WARNING", "propagate": True},
                "redis": {"level": "WARNING", "propagate": True},
                "httpx": {"level": "WARNING", "propagate": True},
                "httpcore": {"level": "WARNING", "propagate": True},
            },
        }


def setup_logging(
    level: str = "INFO",
    json_output: bool = True,
    log_file: Optional[str] = None,
    include_extra: bool = True,
    disable_existing_loggers: bool = False,
) -> None:
    """
    Configure structured logging for the application.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_output: If True, output JSON logs; otherwise plain text
        log_file: Optional file path for log file (also logs to console)
        include_extra: Include extra fields from log records
        disable_existing_loggers: Disable loggers configured before this call
    """
    config = LoggingConfig(
        level=level,
        json_output=json_output,
        include_extra=include_extra,
        log_file=log_file,
        disable_existing_loggers=disable_existing_loggers,
    )

    logging.config.dictConfig(config.get_logging_config())

    # Log startup message
    logger = logging.getLogger("arise.logging")
    logger.info(
        "Structured logging initialized",
        extra={
            "level": level,
            "json_output": json_output,
            "log_file": log_file,
        },
    )


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the standard ARISE configuration."""
    return logging.getLogger(name)


# Convenience function for structured logging
def log_structured(
    logger: logging.Logger,
    level: int,
    message: str,
    **extra_fields: Any,
) -> None:
    """
    Log a message with structured extra fields.

    Usage:
        log_structured(logger, logging.INFO, "Task completed", task_id="123", duration=1.5)
    """
    logger.log(level, message, extra=extra_fields)


# Pre-configured log levels for convenience
def log_debug(logger: logging.Logger, message: str, **extra: Any) -> None:
    log_structured(logger, logging.DEBUG, message, **extra)


def log_info(logger: logging.Logger, message: str, **extra: Any) -> None:
    log_structured(logger, logging.INFO, message, **extra)


def log_warning(logger: logging.Logger, message: str, **extra: Any) -> None:
    log_structured(logger, logging.WARNING, message, **extra)


def log_error(logger: logging.Logger, message: str, **extra: Any) -> None:
    log_structured(logger, logging.ERROR, message, **extra)


def log_critical(logger: logging.Logger, message: str, **extra: Any) -> None:
    log_structured(logger, logging.CRITICAL, message, **extra)


def log_exception(logger: logging.Logger, message: str, **extra: Any) -> None:
    """Log an exception with full traceback."""
    logger.exception(message, extra=extra)


# Context manager for timed operations
@contextmanager
def log_timing(
    logger: logging.Logger,
    operation: str,
    level: int = logging.INFO,
    **extra: Any,
):
    """
    Context manager that logs timing for an operation.

    Usage:
        with log_timing(logger, "database_query", query="SELECT * FROM users"):
            result = db.execute(query)
    """
    import time
    start_time = time.perf_counter()
    log_structured(logger, level, f"{operation} started", **extra)

    try:
        yield
        duration = time.perf_counter() - start_time
        log_structured(
            logger, level,
            f"{operation} completed",
            duration_ms=round(duration * 1000, 2),
            **extra,
        )
    except Exception as e:
        duration = time.perf_counter() - start_time
        log_structured(
            logger, logging.ERROR,
            f"{operation} failed",
            duration_ms=round(duration * 1000, 2),
            error_type=type(e).__name__,
            error_message=str(e),
            **extra,
        )
        raise


# Filter to add context to all log records
class ContextFilter(logging.Filter):
    """Filter that adds context variables to all log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = get_correlation_id() or "-"
        record.task_id = get_task_id() or "-"
        record.agent_id = get_agent_id() or "-"
        record.session_id = get_session_id() or "-"
        record.request_id = get_request_id() or "-"
        record.user_id = get_user_id() or "-"
        return True


def add_context_filter(logger: Optional[logging.Logger] = None) -> None:
    """Add context filter to a logger (or root logger if None)."""
    target = logger or logging.getLogger()
    target.addFilter(ContextFilter())


# Example usage and testing
if __name__ == "__main__":
    # Test logging setup
    setup_logging(level="DEBUG", json_output=True)

    logger = get_logger("test")

    print("=== Basic logging ===")
    log_info(logger, "Application started", version="1.0.0")

    print("\n=== With correlation context ===")
    with correlation_context("req-abc-123"):
        log_info(logger, "Processing request", endpoint="/api/tasks")

        print("\n=== With task context ===")
        with task_context("task-456"):
            log_info(logger, "Task started", task_type="shell.exec")
            log_info(logger, "Task progress", progress=0.5, step="executing")
            log_info(logger, "Task completed", result="success")

    print("\n=== With agent context ===")
    with agent_context("agent-coder", task_id="task-789"):
        log_info(logger, "Agent executing", capability="code_generation")

    print("\n=== With session context ===")
    with session_context("sess-xyz", user_id="user-123"):
        log_info(logger, "User session started", ip="192.168.1.1")

    print("\n=== With timing ===")
    with log_timing(logger, "database_operation", query="SELECT 1"):
        import time
        time.sleep(0.1)

    print("\n=== Exception logging ===")
    try:
        raise ValueError("Test error")
    except ValueError:
        log_exception(logger, "Operation failed", operation="test")