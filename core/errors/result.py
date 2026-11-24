# core/errors/result.py
from typing import TypeVar, Generic, Optional, Union, Callable, Awaitable
from dataclasses import dataclass
from core.errors.base import AriseError, ErrorContext

T = TypeVar('T')
E = TypeVar('E', bound=AriseError)


@dataclass
class Result(Generic[T, E]):
    """Result type for operations that can fail"""
    success: bool
    value: Optional[T] = None
    error: Optional[E] = None

    @classmethod
    def ok(cls, value: T) -> 'Result[T, E]':
        return cls(success=True, value=value)

    @classmethod
    def err(cls, error: E) -> 'Result[T, E]':
        return cls(success=False, error=error)

    def unwrap(self) -> T:
        if not self.success:
            raise self.error
        return self.value

    def unwrap_or(self, default: T) -> T:
        return self.value if self.success else default

    def unwrap_or_else(self, default_factory: Callable[[], T]) -> T:
        return self.value if self.success else default_factory()

    def map(self, func: Callable[[T], Any]) -> 'Result':
        if self.success:
            return Result.ok(func(self.value))
        return Result.err(self.error)

    def map_err(self, func: Callable[[E], Any]) -> 'Result':
        if not self.success:
            return Result.err(func(self.error))
        return self

    def and_then(self, func: Callable[[T], 'Result']) -> 'Result':
        if self.success:
            return func(self.value)
        return Result.err(self.error)

    def or_else(self, func: Callable[[E], 'Result[T, E]']) -> 'Result[T, E]':
        if not self.success:
            return func(self.error)
        return self

    def is_ok(self) -> bool:
        return self.success

    def is_err(self) -> bool:
        return not self.success

    def expect(self, message: str) -> T:
        """Unwrap or panic with message (for testing)"""
        if not self.success:
            raise AssertionError(f"{message}: {self.error}")
        return self.value

    def expect_err(self, message: str) -> E:
        """Unwrap error or panic with message (for testing)"""
        if self.success:
            raise AssertionError(f"{message}: expected error but got success")
        return self.error


# Async variant
AsyncResult = Awaitable[Result[T, E]]


# Helper for converting exceptions to Results
async def try_async(
    coro: Awaitable[T],
    error_mapper: Callable[[Exception], E] = None,
    context: ErrorContext = None,
) -> Result[T, E]:
    """Execute async function and convert to Result"""
    try:
        value = await coro
        return Result.ok(value)
    except AriseError as e:
        if context:
            e.context = context
        return Result.err(e)
    except Exception as e:
        if error_mapper:
            return Result.err(error_mapper(e))
        from core.errors.base import AriseError, ErrorCode
        return Result.err(AriseError(
            code=ErrorCode.INTERNAL_ERROR,
            message=str(e),
            context=context or ErrorContext(),
        ))


def try_sync(
    func: Callable[[], T],
    error_mapper: Callable[[Exception], E] = None,
    context: ErrorContext = None,
) -> Result[T, E]:
    """Execute sync function and convert to Result"""
    try:
        return Result.ok(func())
    except AriseError as e:
        if context:
            e.context = context
        return Result.err(e)
    except Exception as e:
        if error_mapper:
            return Result.err(error_mapper(e))
        from core.errors.base import AriseError, ErrorCode
        return Result.err(AriseError(
            code=ErrorCode.INTERNAL_ERROR,
            message=str(e),
            context=context or ErrorContext(),
        ))


# Utility functions for working with Results

def collect_results(results: list[Result[T, E]]) -> Result[list[T], E]:
    """Collect multiple Results into a single Result with all values or first error"""
    values = []
    for r in results:
        if r.is_err():
            return Result.err(r.error)
        values.append(r.value)
    return Result.ok(values)


async def collect_async_results(results: list[AsyncResult[T, E]]) -> Result[list[T], E]:
    """Collect multiple async Results into a single Result"""
    values = []
    for coro in results:
        r = await coro
        if r.is_err():
            return Result.err(r.error)
        values.append(r.value)
    return Result.ok(values)


def first_ok(results: list[Result[T, E]]) -> Result[T, E]:
    """Return first successful Result, or last error if all fail"""
    last_error = None
    for r in results:
        if r.is_ok():
            return r
        last_error = r.error
    return Result.err(last_error) if last_error else Result.err(AriseError(
        code=ErrorCode.INTERNAL_ERROR,
        message="No results provided",
        context=ErrorContext(),
    ))


async def first_ok_async(results: list[AsyncResult[T, E]]) -> Result[T, E]:
    """Return first successful async Result, or last error if all fail"""
    last_error = None
    for coro in results:
        r = await coro
        if r.is_ok():
            return r
        last_error = r.error
    return Result.err(last_error) if last_error else Result.err(AriseError(
        code=ErrorCode.INTERNAL_ERROR,
        message="No results provided",
        context=ErrorContext(),
    ))