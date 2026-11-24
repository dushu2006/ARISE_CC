# core/errors/retry.py
import asyncio
import random
import time
import logging
from typing import Callable, TypeVar, Awaitable, Optional, Set, Any
from dataclasses import dataclass, field
from functools import wraps
from enum import Enum
from core.errors.base import AriseError, ErrorCode, ErrorContext

logger = logging.getLogger(__name__)

T = TypeVar('T')


@dataclass
class RetryPolicy:
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    retryable_codes: Set[ErrorCode] = frozenset({
        ErrorCode.SERVICE_UNAVAILABLE,
        ErrorCode.TIMEOUT,
        ErrorCode.RATE_LIMITED,
        ErrorCode.PROVIDER_UNAVAILABLE,
        ErrorCode.PROVIDER_RATE_LIMITED,
        ErrorCode.MODEL_TIMEOUT,
        ErrorCode.DATABASE_CONNECTION_FAILED,
        ErrorCode.EVENT_STORE_ERROR,
    })

    def calculate_delay(self, attempt: int) -> float:
        delay = min(
            self.base_delay * (self.exponential_base ** attempt),
            self.max_delay
        )
        if self.jitter:
            delay *= (0.5 + random.random())  # 0.5-1.5x
        return delay


async def with_retry(
    func: Callable[..., Awaitable[T]],
    policy: RetryPolicy = None,
    context: ErrorContext = None,
    on_retry: Callable[[Exception, int], Awaitable[None]] = None,
) -> T:
    """Execute async function with retry policy"""
    policy = policy or RetryPolicy()
    last_exception = None

    for attempt in range(policy.max_attempts):
        try:
            return await func()
        except AriseError as e:
            last_exception = e
            if e.code not in policy.retryable_codes or attempt == policy.max_attempts - 1:
                raise

            delay = policy.calculate_delay(attempt)

            if on_retry:
                await on_retry(e, attempt + 1)

            logger.warning(
                f"Retry {attempt + 1}/{policy.max_attempts} for {e.code}: "
                f"{e.message} (waiting {delay:.1f}s)"
            )

            await asyncio.sleep(delay)
        except Exception as e:
            last_exception = e
            if attempt == policy.max_attempts - 1:
                raise
            delay = policy.calculate_delay(attempt)
            await asyncio.sleep(delay)

    raise last_exception


def retryable(
    policy: RetryPolicy = None,
    context: ErrorContext = None,
):
    """Decorator for retryable async functions"""
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            return await with_retry(
                lambda: func(*args, **kwargs),
                policy=policy,
                context=context,
            )
        return wrapper
    return decorator


# Circuit Breaker

class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5
    success_threshold: int = 3
    timeout: float = 30.0
    half_open_max_calls: int = 3
    excluded_exceptions: Set[type] = field(default_factory=lambda: {KeyboardInterrupt, SystemExit})


class CircuitBreaker:
    """Circuit breaker for external dependencies"""

    def __init__(self, name: str, config: CircuitBreakerConfig = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[float] = None
        self.half_open_calls = 0
        self._lock = asyncio.Lock()

    async def call(self, func: Callable[..., Awaitable[T]]) -> T:
        async with self._lock:
            if self.state == CircuitState.OPEN:
                if time.time() - self.last_failure_time >= self.config.timeout:
                    self.state = CircuitState.HALF_OPEN
                    self.half_open_calls = 0
                    logger.info(f"Circuit {self.name} entering HALF_OPEN state")
                else:
                    raise AriseError(
                        code=ErrorCode.CIRCUIT_OPEN,
                        message=f"Circuit {self.name} is open",
                        context=ErrorContext(component="circuit_breaker", operation=self.name),
                        recoverable=True,
                        retry_after=self.config.timeout,
                    )

            if self.state == CircuitState.HALF_OPEN:
                if self.half_open_calls >= self.config.half_open_max_calls:
                    raise AriseError(
                        code=ErrorCode.CIRCUIT_OPEN,
                        message=f"Circuit {self.name} half-open limit reached",
                        recoverable=True,
                    )
                self.half_open_calls += 1

        try:
            result = await func()
            await self._on_success()
            return result
        except Exception as e:
            # Don't count excluded exceptions as failures
            if type(e) in self.config.excluded_exceptions:
                raise
            await self._on_failure()
            raise

    async def _on_success(self):
        async with self._lock:
            self.failure_count = 0
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.config.success_threshold:
                    self.state = CircuitState.CLOSED
                    self.success_count = 0
                    logger.info(f"Circuit {self.name} CLOSED after successful recovery")

    async def _on_failure(self):
        async with self._lock:
            self.failure_count += 1
            self.success_count = 0
            self.last_failure_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.OPEN
                logger.warning(f"Circuit {self.name} OPEN after half-open failure")
            elif self.failure_count >= self.config.failure_threshold:
                self.state = CircuitState.OPEN
                logger.warning(f"Circuit {self.name} OPEN after {self.failure_count} failures")

    def get_state(self) -> dict:
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
        }

    async def reset(self):
        """Manually reset circuit breaker"""
        async with self._lock:
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.success_count = 0
            self.last_failure_time = None
            self.half_open_calls = 0
            logger.info(f"Circuit {self.name} manually reset")


# Global circuit breaker registry
_circuit_breakers: dict[str, CircuitBreaker] = {}


def get_circuit_breaker(name: str, config: CircuitBreakerConfig = None) -> CircuitBreaker:
    """Get or create a circuit breaker by name"""
    if name not in _circuit_breakers:
        _circuit_breakers[name] = CircuitBreaker(name, config)
    return _circuit_breakers[name]


async def call_with_circuit_breaker(
    name: str,
    func: Callable[..., Awaitable[T]],
    config: CircuitBreakerConfig = None,
) -> T:
    """Execute function with circuit breaker protection"""
    breaker = get_circuit_breaker(name, config)
    return await breaker.call(func)


# Decorator for circuit breaker
def circuit_breaker(name: str, config: CircuitBreakerConfig = None):
    """Decorator to apply circuit breaker to async function"""
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            breaker = get_circuit_breaker(name, config)
            return await breaker.call(lambda: func(*args, **kwargs))
        return wrapper
    return decorator