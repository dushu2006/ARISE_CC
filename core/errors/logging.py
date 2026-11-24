# core/errors/logging.py
import logging
import json
from typing import Optional
from core.errors.base import AriseError, ErrorContext


class ErrorLogger:
    """Structured error logging"""

    def __init__(self, logger: logging.Logger = None):
        self.logger = logger or logging.getLogger("arise.errors")

    def log_error(self, error: AriseError, level: int = logging.ERROR):
        """Log error with full context"""
        extra = {
            "error_id": error.context.error_id,
            "error_code": error.code.value,
            "component": error.context.component,
            "operation": error.context.operation,
            "correlation_id": error.context.correlation_id,
            "task_id": error.context.task_id,
            "agent_id": error.context.agent_id,
            "session_id": error.context.session_id,
            "recoverable": error.recoverable,
            "metadata": error.context.metadata,
        }

        self.logger.log(
            level,
            f"{error.code.value}: {error.message}",
            extra=extra,
            exc_info=not error.recoverable,  # Stack trace only for non-recoverable
        )

    def log_recovery(self, error: AriseError, action: str):
        """Log recovery attempt"""
        self.logger.info(
            f"Recovery attempt for {error.code.value}: {action}",
            extra={
                "error_id": error.context.error_id,
                "recovery_action": action,
            },
        )

    def log_retry(self, error: AriseError, attempt: int, max_attempts: int):
        """Log retry attempt"""
        self.logger.warning(
            f"Retry {attempt}/{max_attempts} for {error.code.value}: {error.message}",
            extra={
                "error_id": error.context.error_id,
                "attempt": attempt,
                "max_attempts": max_attempts,
            },
        )

    def log_circuit_state(self, name: str, state: str, failure_count: int = 0):
        """Log circuit breaker state change"""
        self.logger.warning(
            f"Circuit breaker {name} state: {state} (failures: {failure_count})",
            extra={
                "circuit_name": name,
                "circuit_state": state,
                "failure_count": failure_count,
            },
        )


# Global error logger instance
error_logger = ErrorLogger()


# Convenience functions
def log_error(error: AriseError, level: int = logging.ERROR):
    """Log error using global logger"""
    error_logger.log_error(error, level)


def log_recovery(error: AriseError, action: str):
    """Log recovery using global logger"""
    error_logger.log_recovery(error, action)


def log_retry(error: AriseError, attempt: int, max_attempts: int):
    """Log retry using global logger"""
    error_logger.log_retry(error, attempt, max_attempts)


def log_circuit_state(name: str, state: str, failure_count: int = 0):
    """Log circuit state using global logger"""
    error_logger.log_circuit_state(name, state, failure_count)


# Context manager for error logging
class ErrorContextManager:
    """Context manager that logs errors automatically"""

    def __init__(self, component: str, operation: str, correlation_id: str = ""):
        self.component = component
        self.operation = operation
        self.correlation_id = correlation_id

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_val is not None:
            if isinstance(exc_val, AriseError):
                log_error(exc_val)
            else:
                # Wrap unexpected exception
                from core.errors.base import AriseError, ErrorCode
                arise_error = AriseError(
                    code=ErrorCode.INTERNAL_ERROR,
                    message=str(exc_val),
                    context=ErrorContext(
                        component=self.component,
                        operation=self.operation,
                        correlation_id=self.correlation_id,
                    ),
                )
                log_error(arise_error)
        return False  # Don't suppress exception


# Decorator for automatic error logging
def log_errors(component: str = "", operation: str = ""):
    """Decorator to automatically log errors from async functions"""
    def decorator(func):
        import functools
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            comp = component or func.__module__
            op = operation or func.__name__
            try:
                return await func(*args, **kwargs)
            except AriseError as e:
                e.context.component = comp
                e.context.operation = op
                log_error(e)
                raise
            except Exception as e:
                from core.errors.base import AriseError, ErrorCode
                arise_error = AriseError(
                    code=ErrorCode.INTERNAL_ERROR,
                    message=str(e),
                    context=ErrorContext(
                        component=comp,
                        operation=op,
                    ),
                )
                log_error(arise_error)
                raise
        return wrapper
    return decorator