# ARISE — Error Handling Patterns

## Overview

Standardized error handling patterns for consistent, debuggable, and recoverable error management across all components.

---

## 1. Error Hierarchy

### 1.1 Base Exception Classes

```python
# core/errors/base.py
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum
import traceback
import uuid

class ErrorCode(str, Enum):
    # System
    INVALID_REQUEST = "INVALID_REQUEST"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    TIMEOUT = "TIMEOUT"
    
    # Task
    TASK_NOT_FOUND = "TASK_NOT_FOUND"
    TASK_NOT_CANCELLABLE = "TASK_NOT_CANCELLABLE"
    TASK_ALREADY_COMPLETED = "TASK_ALREADY_COMPLETED"
    
    # Policy
    APPROVAL_EXPIRED = "APPROVAL_EXPIRED"
    APPROVAL_DENIED = "APPROVAL_DENIED"
    CAPABILITY_DENIED = "CAPABILITY_DENIED"
    RISK_TOO_HIGH = "RISK_TOO_HIGH"
    GRANT_EXPIRED = "GRANT_EXPIRED"
    
    # Model
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    CIRCUIT_OPEN = "CIRCUIT_OPEN"
    MODEL_TIMEOUT = "MODEL_TIMEOUT"
    TOKEN_LIMIT_EXCEEDED = "TOKEN_LIMIT_EXCEEDED"
    CONTENT_FILTERED = "CONTENT_FILTERED"
    
    # Voice
    WAKE_WORD_NOT_LOADED = "WAKE_WORD_NOT_LOADED"
    ASR_FAILED = "ASR_FAILED"
    TTS_FAILED = "TTS_FAILED"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    AUDIO_DEVICE_ERROR = "AUDIO_DEVICE_ERROR"
    
    # Memory
    MEMORY_STORE_FULL = "MEMORY_STORE_FULL"
    PII_DETECTED = "PII_DETECTED"
    MEMORY_NOT_FOUND = "MEMORY_NOT_FOUND"
    CONSOLIDATION_FAILED = "CONSOLIDATION_FAILED"
    
    # Agent
    AGENT_UNHEALTHY = "AGENT_UNHEALTHY"
    AGENT_TIMEOUT = "AGENT_TIMEOUT"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    DELEGATION_FAILED = "DELEGATION_FAILED"
    
    # Automation
    UIA_ELEMENT_NOT_FOUND = "UIA_ELEMENT_NOT_FOUND"
    PLAYWRIGHT_NAVIGATION_FAILED = "PLAYWRIGHT_NAVIGATION_FAILED"
    CV_OCR_LOW_CONFIDENCE = "CV_OCR_LOW_CONFIDENCE"
    AUTOMATION_TIMEOUT = "AUTOMATION_TIMEOUT"
    
    # Security
    CREDENTIAL_NOT_FOUND = "CREDENTIAL_NOT_FOUND"
    NETWORK_BLOCKED = "NETWORK_BLOCKED"
    AUDIT_TAMPERED = "AUDIT_TAMPERED"
    PROMPT_INJECTION_DETECTED = "PROMPT_INJECTION_DETECTED"

@dataclass
class ErrorContext:
    """Structured error context for debugging"""
    error_id: str = field(default_factory=lambda: f"err_{uuid.uuid4().hex[:12]}")
    timestamp: str = ""  # ISO 8601
    component: str = ""
    operation: str = ""
    correlation_id: str = ""
    causation_id: str = ""
    user_id: str = "local_user"
    session_id: str = ""
    task_id: str = ""
    agent_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    stack_trace: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_id": self.error_id,
            "timestamp": self.timestamp,
            "component": self.component,
            "operation": self.operation,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "metadata": self.metadata,
        }

class AriseError(Exception):
    """Base exception for all ARISE errors"""
    
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        context: Optional[ErrorContext] = None,
        recoverable: bool = False,
        retry_after: Optional[float] = None,
        suggested_actions: List[str] = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.context = context or ErrorContext()
        self.recoverable = recoverable
        self.retry_after = retry_after
        self.suggested_actions = suggested_actions or []
        
        # Auto-capture stack trace
        if not self.context.stack_trace:
            self.context.stack_trace = "".join(traceback.format_stack()[:-1])
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": {
                "code": self.code.value,
                "message": self.message,
                "recoverable": self.recoverable,
                "retry_after": self.retry_after,
                "suggested_actions": self.suggested_actions,
                "context": self.context.to_dict(),
            }
        }
    
    def to_json(self) -> str:
        import json
        return json.dumps(self.to_dict(), default=str)

# Domain-specific exceptions

class TaskError(AriseError):
    """Task engine errors"""
    pass

class PolicyError(AriseError):
    """Policy engine errors"""
    pass

class ModelError(AriseError):
    """Model router errors"""
    pass

class VoiceError(AriseError):
    """Voice pipeline errors"""
    pass

class MemoryError(AriseError):
    """Memory system errors"""
    pass

class AgentError(AriseError):
    """Agent system errors"""
    pass

class AutomationError(AriseError):
    """Desktop automation errors"""
    pass

class SecurityError(AriseError):
    """Security system errors"""
    pass

class ConfigurationError(AriseError):
    """Configuration errors"""
    pass
```

### 1.2 Error Factory

```python
# core/errors/factory.py
from core.errors.base import (
    AriseError, ErrorCode, ErrorContext,
    TaskError, PolicyError, ModelError, VoiceError,
    MemoryError, AgentError, AutomationError, SecurityError
)
from typing import Optional, Dict, Any
import time

def create_error_context(
    component: str,
    operation: str,
    correlation_id: str = "",
    causation_id: str = "",
    task_id: str = "",
    agent_id: str = "",
    session_id: str = "",
    **metadata
) -> ErrorContext:
    """Create standardized error context"""
    return ErrorContext(
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        component=component,
        operation=operation,
        correlation_id=correlation_id,
        causation_id=causation_id,
        task_id=task_id,
        agent_id=agent_id,
        session_id=session_id,
        metadata=metadata,
    )

# Factory functions for common errors

def capability_denied(
    capability: str,
    resource: str = "",
    context: ErrorContext = None,
) -> PolicyError:
    ctx = context or create_error_context("policy", "check_capability")
    ctx.metadata.update({"capability": capability, "resource": resource})
    return PolicyError(
        code=ErrorCode.CAPABILITY_DENIED,
        message=f"Capability denied: {capability}" + (f" for {resource}" if resource else ""),
        context=ctx,
        recoverable=True,
        suggested_actions=[
            "Request user approval for this capability",
            "Check if capability grant exists and hasn't expired",
            "Verify capability scope matches resource",
        ],
    )

def approval_required(
    risk_level: str,
    capability: str,
    resource: str,
    context: ErrorContext = None,
) -> PolicyError:
    ctx = context or create_error_context("policy", "assess_risk")
    ctx.metadata.update({"risk_level": risk_level, "capability": capability, "resource": resource})
    return PolicyError(
        code=ErrorCode.APPROVAL_DENIED,
        message=f"Action requires {risk_level} approval: {capability} on {resource}",
        context=ctx,
        recoverable=True,
        suggested_actions=[
            "Wait for user approval via UI",
            "Check approval timeout (default 5 minutes)",
        ],
    )

def provider_unavailable(
    provider: str,
    task_type: str,
    context: ErrorContext = None,
) -> ModelError:
    ctx = context or create_error_context("model_router", "complete")
    ctx.metadata.update({"provider": provider, "task_type": task_type})
    return ModelError(
        code=ErrorCode.PROVIDER_UNAVAILABLE,
        message=f"Provider {provider} unavailable for {task_type}",
        context=ctx,
        recoverable=True,
        retry_after=30.0,
        suggested_actions=[
            "Request will be routed to fallback provider",
            "Check provider API status",
            "Verify API credentials",
        ],
    )

def circuit_open(
    provider: str,
    retry_after: float,
    context: ErrorContext = None,
) -> ModelError:
    ctx = context or create_error_context("model_router", "complete")
    ctx.metadata.update({"provider": provider, "circuit_state": "open"})
    return ModelError(
        code=ErrorCode.CIRCUIT_OPEN,
        message=f"Circuit breaker open for {provider}, retry after {retry_after}s",
        context=ctx,
        recoverable=True,
        retry_after=retry_after,
        suggested_actions=[
            f"Wait {retry_after}s for half-open test",
            "Check provider health endpoint",
        ],
    )

def wake_word_not_loaded(context: ErrorContext = None) -> VoiceError:
    ctx = context or create_error_context("voice", "detect_wake_word")
    return VoiceError(
        code=ErrorCode.WAKE_WORD_NOT_LOADED,
        message="Wake word model not loaded",
        context=ctx,
        recoverable=False,
        suggested_actions=[
            "Restart voice pipeline",
            "Check Porcupine model file exists",
            "Verify model license key",
        ],
    )

def asr_failed(
    reason: str,
    audio_duration_ms: float = 0,
    context: ErrorContext = None,
) -> VoiceError:
    ctx = context or create_error_context("voice", "transcribe")
    ctx.metadata.update({"reason": reason, "audio_duration_ms": audio_duration_ms})
    return VoiceError(
        code=ErrorCode.ASR_FAILED,
        message=f"Speech recognition failed: {reason}",
        context=ctx,
        recoverable=True,
        suggested_actions=[
            "Try speaking more clearly",
            "Reduce background noise",
            "Check microphone input level",
            "Fallback to cloud ASR if available",
        ],
    )

def memory_store_full(kind: str, context: ErrorContext = None) -> MemoryError:
    ctx = context or create_error_context("memory", "store")
    ctx.metadata.update({"kind": kind})
    return MemoryError(
        code=ErrorCode.MEMORY_STORE_FULL,
        message=f"Memory store full for {kind} memories",
        context=ctx,
        recoverable=True,
        suggested_actions=[
            "Run consolidation to free space",
            "Increase max_memories_per_kind limit",
            "Delete old/low-confidence memories",
        ],
    )

def pii_detected(
    pii_types: list,
    content_preview: str,
    context: ErrorContext = None,
) -> MemoryError:
    ctx = context or create_error_context("memory", "detect_pii")
    ctx.metadata.update({"pii_types": pii_types, "content_preview": content_preview[:100]})
    return MemoryError(
        code=ErrorCode.PII_DETECTED,
        message=f"PII detected in content: {', '.join(pii_types)}",
        context=ctx,
        recoverable=True,
        suggested_actions=[
            "Review and redact PII before storing",
            "Configure PII action: flag, redact, or block",
            "Use memory.governance to handle",
        ],
    )

def agent_unhealthy(
    agent_id: str,
    reason: str,
    context: ErrorContext = None,
) -> AgentError:
    ctx = context or create_error_context("agent", "health_check", agent_id=agent_id)
    ctx.metadata.update({"reason": reason})
    return AgentError(
        code=ErrorCode.AGENT_UNHEALTHY,
        message=f"Agent {agent_id} unhealthy: {reason}",
        context=ctx,
        recoverable=True,
        suggested_actions=[
            "Agent will be restarted automatically",
            "Check agent logs for errors",
            "Verify agent dependencies",
        ],
    )

def verification_failed(
    agent_id: str,
    issues: list,
    context: ErrorContext = None,
) -> AgentError:
    ctx = context or create_error_context("agent", "verify", agent_id=agent_id)
    ctx.metadata.update({"issues": issues})
    critical = any(i.get("severity") == "critical" for i in issues)
    return AgentError(
        code=ErrorCode.VERIFICATION_FAILED,
        message=f"Verification failed for {agent_id}: {len(issues)} issues",
        context=ctx,
        recoverable=not critical,
        suggested_actions=[
            "Review verification issues",
            "Apply suggested fix if available",
            "Re-run with corrected input",
        ] if not critical else [
            "Critical issue - manual intervention required",
            "Check agent output for security violations",
        ],
    )

def uia_element_not_found(
    app_name: str,
    selector: Dict[str, Any],
    context: ErrorContext = None,
) -> AutomationError:
    ctx = context or create_error_context("automation", "find_element")
    ctx.metadata.update({"app_name": app_name, "selector": selector})
    return AutomationError(
        code=ErrorCode.UIA_ELEMENT_NOT_FOUND,
        message=f"UIA element not found in {app_name}: {selector}",
        context=ctx,
        recoverable=True,
        suggested_actions=[
            "Verify application is running and visible",
            "Try alternative selector (name, class, automation_id)",
            "Fall back to Playwright or CV/OCR",
            "Increase wait timeout",
        ],
    )

def credential_not_found(
    category: str,
    key: str,
    context: ErrorContext = None,
) -> SecurityError:
    ctx = context or create_error_context("security", "get_credential")
    ctx.metadata.update({"category": category, "key": key})
    return SecurityError(
        code=ErrorCode.CREDENTIAL_NOT_FOUND,
        message=f"Credential not found: {category}/{key}",
        context=ctx,
        recoverable=False,
        suggested_actions=[
            f"Store credential via Credential Manager: {category}/{key}",
            "Check credential spelling and case",
            "Verify credential hasn't been deleted",
        ],
    )

def network_blocked(
    destination: str,
    capability: str,
    context: ErrorContext = None,
) -> SecurityError:
    ctx = context or create_error_context("security", "check_egress")
    ctx.metadata.update({"destination": destination, "capability": capability})
    return SecurityError(
        code=ErrorCode.NETWORK_BLOCKED,
        message=f"Network egress blocked to {destination} (requires {capability})",
        context=ctx,
        recoverable=False,
        suggested_actions=[
            "Add destination to network allow-list",
            "Verify required capability is granted",
            "Check network policy configuration",
        ],
    )
```

---

## 2. Result Pattern

```python
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
    
    def is_ok(self) -> bool:
        return self.success
    
    def is_err(self) -> bool:
        return not self.success

# Async variant
AsyncResult = Awaitable[Result[T, E]]

# Helper for converting exceptions to Results
async def try_async(
    coro: Awaitable[T],
    error_mapper: Callable[[Exception], E] = None,
    context: ErrorContext = None,
) -> Result[T, E]:
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
```

---

## 3. Error Handling Middleware

### 3.1 WebSocket Error Handler

```python
# core/runtime/ws_error_handler.py
import json
import logging
from core.errors.base import AriseError, ErrorCode
from core.errors.result import Result

logger = logging.getLogger(__name__)

class WSErrorHandler:
    """Handle errors in WebSocket JSON-RPC communication"""
    
    @staticmethod
    def format_jsonrpc_error(
        request_id: str,
        error: AriseError,
    ) -> str:
        """Format error as JSON-RPC 2.0 error response"""
        response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": WSErrorHandler._map_code(error.code),
                "message": error.message,
                "data": error.to_dict()["error"],
            },
        }
        return json.dumps(response)
    
    @staticmethod
    def _map_code(code: ErrorCode) -> int:
        """Map ARISE error codes to JSON-RPC error codes"""
        mapping = {
            ErrorCode.INVALID_REQUEST: -32600,
            ErrorCode.UNAUTHORIZED: -32001,
            ErrorCode.FORBIDDEN: -32002,
            ErrorCode.NOT_FOUND: -32003,
            ErrorCode.CONFLICT: -32004,
            ErrorCode.RATE_LIMITED: -32005,
            ErrorCode.INTERNAL_ERROR: -32603,
            ErrorCode.SERVICE_UNAVAILABLE: -32006,
            ErrorCode.TIMEOUT: -32007,
        }
        return mapping.get(code, -32000)
    
    @staticmethod
    def format_success(request_id: str, result: Any) -> str:
        """Format successful JSON-RPC response"""
        response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": result,
        }
        return json.dumps(response)
    
    @staticmethod
    async def handle_method(
        method_name: str,
        handler: Callable,
        params: dict,
        request_id: str,
        correlation_id: str = "",
    ) -> str:
        """Execute method with error handling"""
        try:
            # Extract context from params
            context = params.pop("_context", None)
            
            result = await handler(**params)
            
            # Handle Result type
            if isinstance(result, Result):
                if result.is_ok():
                    return WSErrorHandler.format_success(request_id, result.value)
                else:
                    return WSErrorHandler.format_jsonrpc_error(request_id, result.error)
            
            return WSErrorHandler.format_success(request_id, result)
            
        except AriseError as e:
            if correlation_id:
                e.context.correlation_id = correlation_id
            logger.warning(f"Method {method_name} failed: {e.code} - {e.message}")
            return WSErrorHandler.format_jsonrpc_error(request_id, e)
            
        except Exception as e:
            logger.exception(f"Unexpected error in {method_name}")
            arise_error = AriseError(
                code=ErrorCode.INTERNAL_ERROR,
                message=f"Internal error: {str(e)}",
                context=ErrorContext(
                    component="ws_handler",
                    operation=method_name,
                    correlation_id=correlation_id,
                ),
            )
            return WSErrorHandler.format_jsonrpc_error(request_id, arise_error)
```

### 3.2 HTTP Error Handler (FastAPI/Starlette)

```python
# core/runtime/http_error_handler.py
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from core.errors.base import AriseError, ErrorCode, ErrorContext
import logging

logger = logging.getLogger(__name__)

async def arise_error_handler(request: Request, exc: AriseError) -> JSONResponse:
    """Convert AriseError to HTTP response"""
    status_code = _map_status_code(exc.code)
    
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
    
    arise_error = AriseError(
        code=ErrorCode.INVALID_REQUEST if exc.status_code == 400 else ErrorCode.INTERNAL_ERROR,
        message=exc.detail,
        context=ErrorContext(
            component="http",
            operation=request.url.path,
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
    
    arise_error = AriseError(
        code=ErrorCode.INTERNAL_ERROR,
        message="Internal server error",
        context=ErrorContext(
            component="http",
            operation=request.url.path,
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

# Register in FastAPI app
def register_error_handlers(app):
    app.add_exception_handler(AriseError, arise_error_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
```

---

## 4. Retry & Circuit Breaker Patterns

```python
# core/errors/retry.py
import asyncio
import random
from typing import Callable, TypeVar, Awaitable, Optional, Set
from dataclasses import dataclass
from functools import wraps
from core.errors.base import AriseError, ErrorCode, ErrorContext

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

@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5
    success_threshold: int = 3
    timeout: float = 30.0
    half_open_max_calls: int = 3

class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

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
    
    async def _on_failure(self):
        async with self._lock:
            self.failure_count += 1
            self.success_count = 0
            self.last_failure_time = time.time()
            
            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.OPEN
            elif self.failure_count >= self.config.failure_threshold:
                self.state = CircuitState.OPEN
    
    def get_state(self) -> dict:
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
        }
```

---

## 5. Error Recovery Patterns

### 5.1 Saga Compensation

```python
# core/task/saga.py
from typing import List, Callable, Awaitable, Dict, Any
from dataclasses import dataclass, field
from core.errors.base import AriseError, ErrorCode, ErrorContext

@dataclass
class SagaStep:
    name: str
    execute: Callable[[], Awaitable[Any]]
    compensate: Callable[[Any], Awaitable[None]]  # Receives execute result
    execute_context: ErrorContext
    compensate_context: ErrorContext

@dataclass
class SagaExecution:
    steps: List[SagaStep] = field(default_factory=list)
    completed_steps: List[tuple] = field(default_factory=list)  # (step_name, result)
    status: str = "running"  # running, completed, compensating, failed
    error: Optional[AriseError] = None

class Saga:
    """Saga pattern for distributed transaction compensation"""
    
    def __init__(self, name: str):
        self.name = name
        self.execution = SagaExecution()
    
    def add_step(
        self,
        name: str,
        execute: Callable[[], Awaitable[Any]],
        compensate: Callable[[Any], Awaitable[None]],
        execute_context: ErrorContext = None,
        compensate_context: ErrorContext = None,
    ) -> 'Saga':
        self.execution.steps.append(SagaStep(
            name=name,
            execute=execute,
            compensate=compensate,
            execute_context=execute_context or ErrorContext(component="saga", operation=name),
            compensate_context=compensate_context or ErrorContext(component="saga", operation=f"compensate_{name}"),
        ))
        return self
    
    async def execute(self) -> Any:
        """Execute all steps, compensate on failure"""
        try:
            for step in self.execution.steps:
                result = await step.execute()
                self.execution.completed_steps.append((step.name, result))
            
            self.execution.status = "completed"
            return self.execution.completed_steps[-1][1] if self.execution.completed_steps else None
            
        except Exception as e:
            self.execution.error = e if isinstance(e, AriseError) else AriseError(
                code=ErrorCode.INTERNAL_ERROR,
                message=str(e),
                context=ErrorContext(component="saga", operation=self.name),
            )
            self.execution.status = "compensating"
            await self._compensate()
            self.execution.status = "failed"
            raise
    
    async def _compensate(self):
        """Run compensations in reverse order"""
        for step_name, result in reversed(self.execution.completed_steps):
            step = next(s for s in self.execution.steps if s.name == step_name)
            try:
                await step.compensate(result)
                logger.info(f"Compensated step: {step_name}")
            except Exception as e:
                logger.error(f"Compensation failed for {step_name}: {e}")
                # Log but continue compensating other steps
```

---

## 6. Logging Integration

```python
# core/errors/logging.py
import logging
import json
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

# Usage
error_logger = ErrorLogger()

try:
    await risky_operation()
except AriseError as e:
    error_logger.log_error(e)
    raise
```

---

## 7. Testing Error Scenarios

```python
# tests/errors/test_patterns.py
import pytest
from core.errors.base import AriseError, ErrorCode
from core.errors.factory import (
    capability_denied, approval_required, provider_unavailable,
    circuit_open, asr_failed, memory_store_full, pii_detected,
    agent_unhealthy, verification_failed, uia_element_not_found,
    credential_not_found, network_blocked,
)
from core.errors.result import Result, try_async

class TestErrorFactory:
    def test_capability_denied(self):
        error = capability_denied("filesystem.write", "/etc/passwd")
        assert error.code == ErrorCode.CAPABILITY_DENIED
        assert error.recoverable
        assert "filesystem.write" in error.message
        assert "/etc/passwd" in error.message
    
    def test_approval_required(self):
        error = approval_required("R3", "email.send", "user@company.com")
        assert error.code == ErrorCode.APPROVAL_DENIED
        assert error.recoverable
        assert "R3" in error.message
    
    def test_provider_unavailable(self):
        error = provider_unavailable("openai", "coding")
        assert error.code == ErrorCode.PROVIDER_UNAVAILABLE
        assert error.retry_after == 30.0
    
    def test_circuit_open(self):
        error = circuit_open("gemini", 45.0)
        assert error.code == ErrorCode.CIRCUIT_OPEN
        assert error.retry_after == 45.0

class TestResultPattern:
    @pytest.mark.asyncio
    async def test_ok_result(self):
        result = Result.ok("success")
        assert result.is_ok()
        assert result.unwrap() == "success"
    
    @pytest.mark.asyncio
    async def test_err_result(self):
        error = AriseError(ErrorCode.NOT_FOUND, "Not found")
        result = Result.err(error)
        assert result.is_err()
        with pytest.raises(AriseError):
            result.unwrap()
        assert result.unwrap_or("default") == "default"
    
    @pytest.mark.asyncio
    async def test_try_async_success(self):
        async def success():
            return "value"
        
        result = await try_async(success())
        assert result.is_ok()
        assert result.value == "value"
    
    @pytest.mark.asyncio
    async def test_try_async_failure(self):
        async def fail():
            raise AriseError(ErrorCode.NOT_FOUND, "Not found")
        
        result = await try_async(fail())
        assert result.is_err()
        assert result.error.code == ErrorCode.NOT_FOUND

class TestRetryPattern:
    @pytest.mark.asyncio
    async def test_retry_succeeds(self):
        call_count = 0
        
        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise AriseError(ErrorCode.SERVICE_UNAVAILABLE, "Temporary")
            return "success"
        
        from core.errors.retry import with_retry, RetryPolicy
        result = await with_retry(flaky, RetryPolicy(max_attempts=5, base_delay=0.01))
        assert result == "success"
        assert call_count == 3
    
    @pytest.mark.asyncio
    async def test_retry_exhausted(self):
        async def always_fails():
            raise AriseError(ErrorCode.SERVICE_UNAVAILABLE, "Permanent")
        
        from core.errors.retry import with_retry, RetryPolicy
        with pytest.raises(AriseError) as exc:
            await with_retry(always_fails, RetryPolicy(max_attempts=3, base_delay=0.01))
        assert exc.value.code == ErrorCode.SERVICE_UNAVAILABLE
```

---

## 8. Client-Side Error Handling (TypeScript)

```typescript
// src-tauri/frontend/src/lib/errorHandling.ts

export interface AriseError {
  code: string;
  message: string;
  recoverable: boolean;
  retry_after?: number;
  suggested_actions?: string[];
  context: ErrorContext;
}

export interface ErrorContext {
  error_id: string;
  timestamp: string;
  component: string;
  operation: string;
  correlation_id: string;
  task_id?: string;
  agent_id?: string;
  session_id?: string;
  metadata: Record<string, any>;
}

export class AriseAPIError extends Error {
  constructor(public readonly error: AriseError) {
    super(error.message);
    this.name = 'AriseAPIError';
  }
  
  get isRecoverable(): boolean {
    return this.error.recoverable;
  }
  
  get retryAfter(): number | undefined {
    return this.error.retry_after;
  }
  
  get suggestedActions(): string[] {
    return this.error.suggested_actions || [];
  }
}

export async function handleAPIResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const errorData = await response.json();
    throw new AriseAPIError(errorData.error);
  }
  return response.json();
}

export async function withRetry<T>(
  fn: () => Promise<T>,
  options: {
    maxAttempts?: number;
    baseDelay?: number;
    onRetry?: (error: AriseAPIError, attempt: number) => Promise<void>;
  } = {}
): Promise<T> {
  const { maxAttempts = 3, baseDelay = 1000, onRetry } = options;
  let lastError: AriseAPIError;
  
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error as AriseAPIError;
      
      if (!lastError.isRecoverable || attempt === maxAttempts) {
        throw lastError;
      }
      
      const delay = baseDelay * Math.pow(2, attempt - 1) * (0.5 + Math.random());
      
      if (onRetry) {
        await onRetry(lastError, attempt);
      }
      
      await new Promise(resolve => setTimeout(resolve, delay));
    }
  }
  
  throw lastError!;
}

// React hook for error handling
export function useErrorHandler() {
  const handleError = (error: unknown) => {
    if (error instanceof AriseAPIError) {
      // Log to monitoring
      console.error(`[${error.error.context.error_id}] ${error.error.code}: ${error.message}`);
      
      // Show user-friendly message
      if (error.error.code === 'APPROVAL_DENIED') {
        // Trigger approval UI
        return;
      }
      if (error.error.code === 'CAPABILITY_DENIED') {
        // Show capability request UI
        return;
      }
    }
    
    // Generic error handling
    console.error('Unexpected error:', error);
  };
  
  return { handleError };
}
```

---

*These error handling patterns ensure consistent, recoverable, and debuggable error management across all ARISE components.*