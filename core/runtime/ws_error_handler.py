# core/runtime/ws_error_handler.py
import json
import logging
from typing import Callable, Any, Optional
from core.errors.base import AriseError, ErrorCode
from core.errors.result import Result

logger = logging.getLogger(__name__)


class WSErrorHandler:
    """Handle errors in WebSocket JSON-RPC communication"""

    @staticmethod
    def format_jsonrpc_error(
        request_id: Any,
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
    def format_success(request_id: Any, result: Any) -> str:
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
        request_id: Any,
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


class WSHandler:
    """WebSocket message handler with JSON-RPC 2.0 support"""

    def __init__(self):
        self.methods: dict[str, Callable] = {}

    def register(self, method_name: str) -> Callable:
        """Decorator to register a method handler"""
        def decorator(func: Callable) -> Callable:
            self.methods[method_name] = func
            return func
        return decorator

    async def handle_message(self, message: str, correlation_id: str = "") -> Optional[str]:
        """Handle incoming WebSocket message"""
        try:
            request = json.loads(message)
        except json.JSONDecodeError:
            return WSErrorHandler.format_jsonrpc_error(
                None,
                AriseError(
                    code=ErrorCode.INVALID_REQUEST,
                    message="Invalid JSON",
                    context=ErrorContext(component="ws_handler", operation="parse"),
                )
            )

        # Validate JSON-RPC 2.0
        if request.get("jsonrpc") != "2.0":
            return WSErrorHandler.format_jsonrpc_error(
                request.get("id"),
                AriseError(
                    code=ErrorCode.INVALID_REQUEST,
                    message="Invalid JSON-RPC version",
                    context=ErrorContext(component="ws_handler", operation="validate"),
                )
            )

        method_name = request.get("method")
        if not method_name:
            return WSErrorHandler.format_jsonrpc_error(
                request.get("id"),
                AriseError(
                    code=ErrorCode.INVALID_REQUEST,
                    message="Missing method",
                    context=ErrorContext(component="ws_handler", operation="validate"),
                )
            )

        handler = self.methods.get(method_name)
        if not handler:
            return WSErrorHandler.format_jsonrpc_error(
                request.get("id"),
                AriseError(
                    code=ErrorCode.NOT_FOUND,
                    message=f"Method not found: {method_name}",
                    context=ErrorContext(component="ws_handler", operation="dispatch"),
                )
            )

        params = request.get("params", {})
        if isinstance(params, list):
            params = dict(enumerate(params))

        request_id = request.get("id")

        return await WSErrorHandler.handle_method(
            method_name=method_name,
            handler=handler,
            params=params,
            request_id=request_id,
            correlation_id=correlation_id,
        )


# Global WebSocket handler instance
_ws_handler: Optional[WSHandler] = None


def get_ws_handler() -> WSHandler:
    """Get global WebSocket handler"""
    global _ws_handler
    if _ws_handler is None:
        _ws_handler = WSHandler()
    return _ws_handler


def register_websocket_exception_handlers(app) -> None:
    """Register WebSocket exception handlers with FastAPI app"""
    # WebSocket errors are handled via the WSHandler class
    # This function is a placeholder for future WebSocket-specific error handlers
    pass