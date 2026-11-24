# core/runtime/websocket.py
"""
WebSocket Handler - JSON-RPC 2.0 over WebSocket.

Provides:
- WebSocket endpoint for real-time updates
- JSON-RPC 2.0 message protocol
- Task progress streaming
- Event subscriptions
- Voice session streaming
- Automation session streaming
"""

from __future__ import annotations
import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Set

from fastapi import WebSocket, WebSocketDisconnect, status
from fastapi.websockets import WebSocketState
from pydantic import BaseModel, Field, ValidationError

from core.events import get_event_bus, Event, EventPriority
from core.events.tracing import correlation_context, get_correlation_id
from core.structured_logging import log_structured

logger = logging.getLogger(__name__)


# Helper function for structured logging
def _log_structured(level: int, message: str, **extra: Any) -> None:
    log_structured(logger, level, message, **extra)


# ============================================================
# JSON-RPC 2.0 Models
# ============================================================

class JSONRPCVersion(str, Enum):
    V2 = "2.0"


class JSONRPCRequest(BaseModel):
    """JSON-RPC 2.0 request."""
    jsonrpc: JSONRPCVersion = JSONRPCVersion.V2
    method: str
    params: Optional[Dict[str, Any]] = None
    id: Optional[Any] = None  # Can be string, number, or null


class JSONRPCResponse(BaseModel):
    """JSON-RPC 2.0 response."""
    jsonrpc: JSONRPCVersion = JSONRPCVersion.V2
    result: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None
    id: Optional[Any] = None


class JSONRPCError(BaseModel):
    """JSON-RPC 2.0 error object."""
    code: int
    message: str
    data: Optional[Any] = None


class JSONRPCNotification(BaseModel):
    """JSON-RPC 2.0 notification (no id)."""
    jsonrpc: JSONRPCVersion = JSONRPCVersion.V2
    method: str
    params: Optional[Dict[str, Any]] = None


# ============================================================
# JSON-RPC Error Codes
# ============================================================

class JSONRPCErrorCode:
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603
    # Custom codes
    UNAUTHORIZED = -32001
    SUBSCRIPTION_FAILED = -32002
    SUBSCRIPTION_NOT_FOUND = -32003
    TASK_NOT_FOUND = -32004
    SESSION_NOT_FOUND = -32005


# ============================================================
# WebSocket Message Types
# ============================================================

class WSMessageType(str, Enum):
    # Connection management
    CONNECT = "connect"
    DISCONNECT = "disconnect"
    PING = "ping"
    PONG = "pong"

    # Subscriptions
    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"
    SUBSCRIPTION_CONFIRMED = "subscription_confirmed"

    # Task progress
    TASK_PROGRESS = "task.progress"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    TASK_CANCELLED = "task.cancelled"

    # Voice
    VOICE_TRANSCRIPT = "voice.transcript"
    VOICE_AUDIO_LEVEL = "voice.audio_level"
    VOICE_STATE_CHANGE = "voice.state_change"

    # Automation
    AUTOMATION_ELEMENT_FOUND = "automation.element_found"
    AUTOMATION_ACTION_COMPLETE = "automation.action_complete"
    AUTOMATION_SCREENSHOT = "automation.screenshot"
    AUTOMATION_OCR_RESULT = "automation.ocr_result"

    # Agents
    AGENT_DELEGATION = "agent.delegation"
    AGENT_VERIFICATION = "agent.verification"
    AGENT_HEALTH = "agent.health"

    # System
    SYSTEM_ALERT = "system.alert"
    CONFIG_CHANGED = "config.changed"


# ============================================================
# Subscription Manager
# ============================================================

@dataclass
class Subscription:
    """WebSocket subscription."""
    id: str
    client_id: str
    topic: str
    filters: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class SubscriptionManager:
    """Manages WebSocket subscriptions."""

    def __init__(self):
        self._subscriptions: Dict[str, Subscription] = {}
        self._client_subscriptions: Dict[str, Set[str]] = {}  # client_id -> set of subscription_ids
        self._topic_subscriptions: Dict[str, Set[str]] = {}   # topic -> set of subscription_ids

    def create_subscription(
        self,
        client_id: str,
        topic: str,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Subscription:
        """Create a new subscription."""
        sub_id = str(uuid.uuid4())[:12]
        subscription = Subscription(
            id=sub_id,
            client_id=client_id,
            topic=topic,
            filters=filters or {},
        )

        self._subscriptions[sub_id] = subscription

        if client_id not in self._client_subscriptions:
            self._client_subscriptions[client_id] = set()
        self._client_subscriptions[client_id].add(sub_id)

        if topic not in self._topic_subscriptions:
            self._topic_subscriptions[topic] = set()
        self._topic_subscriptions[topic].add(sub_id)

        return subscription

    def remove_subscription(self, sub_id: str) -> bool:
        """Remove a subscription."""
        if sub_id not in self._subscriptions:
            return False

        sub = self._subscriptions[sub_id]

        # Remove from client subscriptions
        if sub.client_id in self._client_subscriptions:
            self._client_subscriptions[sub.client_id].discard(sub_id)
            if not self._client_subscriptions[sub.client_id]:
                del self._client_subscriptions[sub.client_id]

        # Remove from topic subscriptions
        if sub.topic in self._topic_subscriptions:
            self._topic_subscriptions[sub.topic].discard(sub_id)
            if not self._topic_subscriptions[sub.topic]:
                del self._topic_subscriptions[sub.topic]

        del self._subscriptions[sub_id]
        return True

    def remove_client_subscriptions(self, client_id: str) -> List[str]:
        """Remove all subscriptions for a client."""
        removed = []
        if client_id in self._client_subscriptions:
            for sub_id in list(self._client_subscriptions[client_id]):
                self.remove_subscription(sub_id)
                removed.append(sub_id)
        return removed

    def get_subscriptions_for_topic(self, topic: str) -> List[Subscription]:
        """Get all subscriptions for a topic."""
        sub_ids = self._topic_subscriptions.get(topic, set())
        return [self._subscriptions[sid] for sid in sub_ids if sid in self._subscriptions]

    def get_client_subscriptions(self, client_id: str) -> List[Subscription]:
        """Get all subscriptions for a client."""
        sub_ids = self._client_subscriptions.get(client_id, set())
        return [self._subscriptions[sid] for sid in sub_ids if sid in self._subscriptions]


# ============================================================
# WebSocket Connection Manager
# ============================================================

@dataclass
class WSClient:
    """WebSocket client connection."""
    id: str
    websocket: WebSocket
    connected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_ping: Optional[datetime] = None
    subscriptions: Set[str] = field(default_factory=set)
    metadata: Dict[str, Any] = field(default_factory=dict)


class ConnectionManager:
    """Manages WebSocket connections."""

    def __init__(self):
        self._clients: Dict[str, WSClient] = {}
        self._subscription_manager = SubscriptionManager()
        self._message_handlers: Dict[str, Callable] = {}
        self._event_bus = None

    @property
    def subscription_manager(self) -> SubscriptionManager:
        return self._subscription_manager

    async def connect(self, websocket: WebSocket, client_id: Optional[str] = None) -> WSClient:
        """Accept a new WebSocket connection."""
        await websocket.accept()

        if client_id is None:
            client_id = str(uuid.uuid4())[:12]

        client = WSClient(id=client_id, websocket=websocket)
        self._clients[client_id] = client

        _log_structured(logging.INFO, "WebSocket connected", client_id=client_id, total_clients=len(self._clients))

        # Send connection confirmation
        await self.send_jsonrpc(client_id, JSONRPCResponse(
            id=None,
            result={"type": "connected", "client_id": client_id},
        ))

        return client

    async def disconnect(self, client_id: str) -> None:
        """Disconnect a client."""
        if client_id in self._clients:
            client = self._clients[client_id]

            # Remove all subscriptions
            self._subscription_manager.remove_client_subscriptions(client_id)

            # Close WebSocket if still open
            if client.websocket.client_state == WebSocketState.CONNECTED:
                await client.websocket.close()

            del self._clients[client_id]

            _log_structured(logging.INFO, "WebSocket disconnected", client_id=client_id, total_clients=len(self._clients))

    def get_client(self, client_id: str) -> Optional[WSClient]:
        """Get client by ID."""
        return self._clients.get(client_id)

    def get_all_clients(self) -> List[WSClient]:
        """Get all connected clients."""
        return list(self._clients.values())

    async def send_jsonrpc(self, client_id: str, response: JSONRPCResponse) -> bool:
        """Send JSON-RPC response to client."""
        client = self._clients.get(client_id)
        if not client or client.websocket.client_state != WebSocketState.CONNECTED:
            return False

        try:
            await client.websocket.send_text(response.model_dump_json(exclude_none=True))
            return True
        except Exception as e:
            logger.error(f"Failed to send to client {client_id}: {e}")
            await self.disconnect(client_id)
            return False

    async def send_notification(self, client_id: str, notification: JSONRPCNotification) -> bool:
        """Send JSON-RPC notification to client."""
        client = self._clients.get(client_id)
        if not client or client.websocket.client_state != WebSocketState.CONNECTED:
            return False

        try:
            await client.websocket.send_text(notification.model_dump_json(exclude_none=True))
            return True
        except Exception as e:
            logger.error(f"Failed to send notification to client {client_id}: {e}")
            await self.disconnect(client_id)
            return False

    async def broadcast(self, notification: JSONRPCNotification, topic: Optional[str] = None) -> int:
        """Broadcast notification to all clients or subscribers of a topic."""
        sent = 0

        if topic:
            # Send to subscribers of topic
            subscriptions = self._subscription_manager.get_subscriptions_for_topic(topic)
            client_ids = set(sub.client_id for sub in subscriptions)
            for client_id in client_ids:
                if await self.send_notification(client_id, notification):
                    sent += 1
        else:
            # Send to all clients
            for client_id in list(self._clients.keys()):
                if await self.send_notification(client_id, notification):
                    sent += 1

        return sent

    async def broadcast_event(self, event: Event) -> int:
        """Broadcast an event to relevant subscribers."""
        # Map event types to WebSocket topics
        topic_map = {
            "task.started": "tasks",
            "task.progress": "tasks",
            "task.completed": "tasks",
            "task.failed": "tasks",
            "task.cancelled": "tasks",
            "voice.transcript": "voice",
            "voice.audio_level": "voice",
            "voice.state_change": "voice",
            "automation.element_found": "automation",
            "automation.action_complete": "automation",
            "automation.screenshot": "automation",
            "automation.ocr_result": "automation",
            "agent.delegation": "agents",
            "agent.verification": "agents",
            "agent.health": "agents",
        }

        topic = topic_map.get(event.type, "events")

        notification = JSONRPCNotification(
            method="event",
            params={
                "topic": topic,
                "event_type": event.type,
                "payload": event.payload,
                "correlation_id": event.correlation_id,
                "timestamp": event.timestamp.isoformat(),
            },
        )

        return await self.broadcast(notification, topic)

    def register_handler(self, method: str, handler: Callable) -> None:
        """Register a JSON-RPC method handler."""
        self._message_handlers[method] = handler

    async def handle_message(self, client_id: str, message: str) -> None:
        """Handle incoming WebSocket message."""
        client = self._clients.get(client_id)
        if not client:
            return

        try:
            data = json.loads(message)
        except json.JSONDecodeError as e:
            await self.send_jsonrpc(client_id, JSONRPCResponse(
                id=None,
                error={"code": JSONRPCErrorCode.PARSE_ERROR, "message": "Parse error", "data": str(e)},
            ))
            return

        # Validate as JSON-RPC request
        try:
            request = JSONRPCRequest(**data)
        except ValidationError as e:
            await self.send_jsonrpc(client_id, JSONRPCResponse(
                id=data.get("id"),
                error={"code": JSONRPCErrorCode.INVALID_REQUEST, "message": "Invalid request", "data": str(e)},
            ))
            return

        # Handle request
        handler = self._message_handlers.get(request.method)
        if not handler:
            await self.send_jsonrpc(client_id, JSONRPCResponse(
                id=request.id,
                error={"code": JSONRPCErrorCode.METHOD_NOT_FOUND, "message": f"Method not found: {request.method}"},
            ))
            return

        try:
            # Execute handler with correlation context
            with correlation_context(request.params.get("correlation_id") if request.params else None):
                result = await handler(client_id, request.params or {})

            if request.id is not None:
                await self.send_jsonrpc(client_id, JSONRPCResponse(
                    id=request.id,
                    result=result,
                ))

        except Exception as e:
            logger.error(f"Handler error for {request.method}: {e}", exc_info=True)
            if request.id is not None:
                await self.send_jsonrpc(client_id, JSONRPCResponse(
                    id=request.id,
                    error={"code": JSONRPCErrorCode.INTERNAL_ERROR, "message": "Internal error", "data": str(e)},
                ))


# ============================================================
# Global Connection Manager
# ============================================================

_connection_manager: Optional[ConnectionManager] = None


def get_connection_manager() -> ConnectionManager:
    """Get global connection manager."""
    global _connection_manager
    if _connection_manager is None:
        _connection_manager = ConnectionManager()
        # Register default handlers
        _register_default_handlers(_connection_manager)
    return _connection_manager


def _register_default_handlers(manager: ConnectionManager) -> None:
    """Register default JSON-RPC handlers."""

    async def handle_ping(client_id: str, params: Dict) -> Dict:
        return {"pong": True, "timestamp": datetime.now(timezone.utc).isoformat()}

    async def handle_subscribe(client_id: str, params: Dict) -> Dict:
        topic = params.get("topic")
        if not topic:
            raise ValueError("Topic required")

        filters = params.get("filters", {})
        subscription = manager.subscription_manager.create_subscription(client_id, topic, filters)

        return {
            "subscription_id": subscription.id,
            "topic": topic,
            "filters": filters,
        }

    async def handle_unsubscribe(client_id: str, params: Dict) -> Dict:
        subscription_id = params.get("subscription_id")
        if not subscription_id:
            raise ValueError("Subscription ID required")

        success = manager.subscription_manager.remove_subscription(subscription_id)
        return {"success": success}

    async def handle_get_subscriptions(client_id: str, params: Dict) -> Dict:
        subs = manager.subscription_manager.get_client_subscriptions(client_id)
        return {
            "subscriptions": [
                {"id": s.id, "topic": s.topic, "filters": s.filters, "created_at": s.created_at.isoformat()}
                for s in subs
            ],
        }

    manager.register_handler("ping", handle_ping)
    manager.register_handler("subscribe", handle_subscribe)
    manager.register_handler("unsubscribe", handle_unsubscribe)
    manager.register_handler("get_subscriptions", handle_get_subscriptions)


# ============================================================
# WebSocket Endpoint Handler
# ============================================================

async def websocket_endpoint(websocket: WebSocket) -> None:
    """
    Main WebSocket endpoint handler.

    Handles JSON-RPC 2.0 messages over WebSocket.
    """
    manager = get_connection_manager()
    client_id = None

    try:
        # Accept connection
        client = await manager.connect(websocket)
        client_id = client.id

        # Message loop
        while True:
            try:
                message = await websocket.receive_text()
                await manager.handle_message(client_id, message)
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"Error processing message from {client_id}: {e}", exc_info=True)
                # Send error but continue
                await manager.send_jsonrpc(client_id, JSONRPCResponse(
                    id=None,
                    error={"code": JSONRPCErrorCode.INTERNAL_ERROR, "message": "Message processing error"},
                ))

    except Exception as e:
        logger.error(f"WebSocket error for {client_id}: {e}", exc_info=True)

    finally:
        if client_id:
            await manager.disconnect(client_id)


# ============================================================
# Event Bus Integration
# ============================================================

async def start_event_forwarding() -> None:
    """Start forwarding events from event bus to WebSocket clients."""
    manager = get_connection_manager()
    bus = get_event_bus()

    if not bus:
        logger.warning("Event bus not available for WebSocket forwarding")
        return

    async def event_handler(event: Event) -> None:
        await manager.broadcast_event(event)

    # Subscribe to all relevant event types
    event_types = [
        "task.*",
        "voice.*",
        "automation.*",
        "agent.*",
        "policy.*",
        "model.*",
        "memory.*",
        "security.*",
    ]

    for event_type in event_types:
        bus.subscribe(event_type, event_handler)

    _log_structured(logging.INFO, "Event bus forwarding started for WebSocket")


async def stop_event_forwarding() -> None:
    """Stop event forwarding."""
    bus = get_event_bus()
    if bus:
        # Note: We'd need to track subscription IDs to unsubscribe properly
        # For now, this is a placeholder
        _log_structured(logging.INFO, "Event bus forwarding stopped")


# ============================================================
# Utility Functions for Sending Updates
# ============================================================

async def send_task_progress(task_id: str, progress: float, message: str = "", metadata: Optional[Dict] = None) -> int:
    """Send task progress update to subscribers."""
    manager = get_connection_manager()
    notification = JSONRPCNotification(
        method="task.progress",
        params={
            "task_id": task_id,
            "progress": progress,
            "message": message,
            "metadata": metadata or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
    return await manager.broadcast(notification, "tasks")


async def send_task_completed(task_id: str, result: Dict) -> int:
    """Send task completion notification."""
    manager = get_connection_manager()
    notification = JSONRPCNotification(
        method="task.completed",
        params={
            "task_id": task_id,
            "result": result,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
    return await manager.broadcast(notification, "tasks")


async def send_task_failed(task_id: str, error: str) -> int:
    """Send task failure notification."""
    manager = get_connection_manager()
    notification = JSONRPCNotification(
        method="task.failed",
        params={
            "task_id": task_id,
            "error": error,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
    return await manager.broadcast(notification, "tasks")


async def send_voice_transcript(session_id: str, transcript: str, is_final: bool = False) -> int:
    """Send voice transcript update."""
    manager = get_connection_manager()
    notification = JSONRPCNotification(
        method="voice.transcript",
        params={
            "session_id": session_id,
            "transcript": transcript,
            "is_final": is_final,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
    return await manager.broadcast(notification, "voice")


async def send_automation_element_found(element_id: str, element_data: Dict) -> int:
    """Send automation element found notification."""
    manager = get_connection_manager()
    notification = JSONRPCNotification(
        method="automation.element_found",
        params={
            "element_id": element_id,
            "element": element_data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
    return await manager.broadcast(notification, "automation")


async def send_agent_delegation(delegation_id: str, from_role: str, to_role: str, task: Dict) -> int:
    """Send agent delegation notification."""
    manager = get_connection_manager()
    notification = JSONRPCNotification(
        method="agent.delegation",
        params={
            "delegation_id": delegation_id,
            "from_role": from_role,
            "to_role": to_role,
            "task": task,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
    return await manager.broadcast(notification, "agents")


# ============================================================
# Exports
# ============================================================

__all__ = [
    "websocket_endpoint",
    "get_connection_manager",
    "start_event_forwarding",
    "stop_event_forwarding",
    "send_task_progress",
    "send_task_completed",
    "send_task_failed",
    "send_voice_transcript",
    "send_automation_element_found",
    "send_agent_delegation",
    "ConnectionManager",
    "SubscriptionManager",
    "JSONRPCRequest",
    "JSONRPCResponse",
    "JSONRPCNotification",
    "JSONRPCErrorCode",
    "WSMessageType",
]