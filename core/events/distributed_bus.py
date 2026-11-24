# core/events/distributed_bus.py
"""
DistributedEventBus - Redis Streams based event bus for multi-process/multi-node deployments.

Provides:
- Redis Streams consumer groups for horizontal scaling
- Publish/subscribe with persistence
- Event replay from stream history
- HybridEventBus combining local + distributed buses
"""

from __future__ import annotations
import asyncio
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional

import redis.asyncio as redis
from core.events.models import Event, EventPriority, EventTypes
from core.events.bus import LocalEventBus, EventHandler

logger = logging.getLogger(__name__)


@dataclass
class StreamConfig:
    """Configuration for Redis Streams."""
    stream_name: str = "arise:events"
    consumer_group: str = "arise-consumers"
    consumer_name: str = ""  # Auto-generated if empty
    block_ms: int = 5000  # Block time for XREADGROUP
    count: int = 100  # Max events per read
    max_stream_length: int = 100000  # MAXLEN for stream trimming


class DistributedEventBus:
    """
    Redis Streams based distributed event bus.

    Uses consumer groups for:
    - Horizontal scaling (multiple consumers)
    - At-least-once delivery guarantee
    - Automatic load balancing
    - Message acknowledgment tracking
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        config: Optional[StreamConfig] = None,
    ):
        self.redis_url = redis_url
        self.config = config or StreamConfig()
        self._redis: Optional[redis.Redis] = None
        self._consumer_name = self.config.consumer_name or f"consumer-{uuid.uuid4().hex[:8]}"
        self._running = False
        self._consumer_task: Optional[asyncio.Task] = None
        self._handlers: dict[str, list[EventHandler]] = {}
        self._wildcard_handlers: list[tuple[str, EventHandler]] = []  # (pattern, handler)

        # Metrics
        self._events_published = 0
        self._events_received = 0
        self._events_processed = 0
        self._events_failed = 0

    async def connect(self) -> None:
        """Connect to Redis and initialize consumer group."""
        self._redis = redis.from_url(
            self.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )

        # Create consumer group (idempotent)
        try:
            await self._redis.xgroup_create(
                self.config.stream_name,
                self.config.consumer_group,
                id="0",  # Start from beginning
                mkstream=True,
            )
        except redis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

        logger.info(f"DistributedEventBus connected to {self.redis_url}")

    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        if self._running:
            await self.stop()

        if self._redis:
            await self._redis.aclose()
            self._redis = None

        logger.info("DistributedEventBus disconnected")

    async def start(self) -> None:
        """Start consuming events from Redis Streams."""
        if self._running:
            return

        if not self._redis:
            await self.connect()

        self._running = True
        self._consumer_task = asyncio.create_task(self._consume_loop())
        logger.info(f"DistributedEventBus started consuming as {self._consumer_name}")

    async def stop(self) -> None:
        """Stop consuming events."""
        if not self._running:
            return

        self._running = False

        if self._consumer_task:
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass

        logger.info("DistributedEventBus stopped consuming")

    def subscribe(
        self,
        pattern: str,
        handler: EventHandler,
    ) -> None:
        """
        Subscribe to events matching a pattern.

        Note: Pattern matching is done locally after receiving from Redis.
        """
        import re

        is_wildcard = "*" in pattern or "?" in pattern

        if is_wildcard:
            # Convert to regex
            regex_pattern = pattern.replace(".", r"\.")
            regex_pattern = regex_pattern.replace("**", ".*")
            regex_pattern = regex_pattern.replace("*", "[^.]*")
            regex_pattern = regex_pattern.replace("?", ".")
            compiled = re.compile(f"^{regex_pattern}$")
            self._wildcard_handlers.append((compiled, handler))
        else:
            if pattern not in self._handlers:
                self._handlers[pattern] = []
            self._handlers[pattern].append(handler)

        logger.debug(f"Subscribed to pattern: {pattern}")

    def unsubscribe(self, pattern: str, handler: EventHandler) -> bool:
        """Unsubscribe a handler from a pattern."""
        if pattern in self._handlers:
            try:
                self._handlers[pattern].remove(handler)
                if not self._handlers[pattern]:
                    del self._handlers[pattern]
                return True
            except ValueError:
                pass

        # Check wildcard handlers
        for i, (compiled, h) in enumerate(self._wildcard_handlers):
            if h == handler:
                self._wildcard_handlers.pop(i)
                return True

        return False

    async def publish(self, event: Event) -> str:
        """
        Publish an event to Redis Stream.

        Returns:
            The stream entry ID
        """
        if not self._redis:
            await self.connect()

        # Serialize event
        event_data = event.to_dict()
        # Convert to strings for Redis
        stream_data = {k: json.dumps(v) if not isinstance(v, str) else v
                      for k, v in event_data.items()}

        # Add to stream with MAXLEN for automatic trimming
        entry_id = await self._redis.xadd(
            self.config.stream_name,
            stream_data,
            maxlen=self.config.max_stream_length,
            approximate=True,
        )

        self._events_published += 1
        logger.debug(f"Published event {event.type} to stream: {entry_id}")
        return entry_id

    async def _consume_loop(self) -> None:
        """Main consumer loop reading from Redis Stream."""
        while self._running:
            try:
                # Read new messages from stream
                results = await self._redis.xreadgroup(
                    groupname=self.config.consumer_group,
                    consumername=self._consumer_name,
                    streams={self.config.stream_name: ">"},
                    count=self.config.count,
                    block=self.config.block_ms,
                )

                if not results:
                    continue

                for stream_name, messages in results:
                    for entry_id, data in messages:
                        await self._process_stream_entry(entry_id, data)

            except asyncio.CancelledError:
                break
            except redis.ConnectionError as e:
                logger.warning(f"Redis connection error: {e}, reconnecting...")
                await asyncio.sleep(5)
                try:
                    await self.connect()
                except Exception as conn_e:
                    logger.error(f"Failed to reconnect: {conn_e}")
            except Exception as e:
                logger.exception(f"Error in consume loop: {e}")
                await asyncio.sleep(1)

    async def _process_stream_entry(self, entry_id: str, data: dict[str, str]) -> None:
        """Process a single stream entry."""
        try:
            # Deserialize event
            event_data = {}
            for k, v in data.items():
                try:
                    event_data[k] = json.loads(v)
                except json.JSONDecodeError:
                    event_data[k] = v

            event = Event.from_dict(event_data)
            self._events_received += 1

            # Find matching handlers
            handlers = self._find_handlers(event.type)

            if not handlers:
                logger.debug(f"No handlers for event type: {event.type}")
                await self._redis.xack(
                    self.config.stream_name,
                    self.config.consumer_group,
                    entry_id,
                )
                return

            # Run handlers
            for handler in handlers:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(event)
                    else:
                        await asyncio.get_event_loop().run_in_executor(None, handler, event)
                except Exception as e:
                    logger.error(f"Handler failed for event {event.type}: {e}")
                    self._events_failed += 1
                    # Don't ack - let it be redelivered
                    return

            # Acknowledge successful processing
            await self._redis.xack(
                self.config.stream_name,
                self.config.consumer_group,
                entry_id,
            )

            self._events_processed += 1

        except Exception as e:
            logger.exception(f"Error processing stream entry {entry_id}: {e}")
            # Don't ack on error - will be redelivered

    def _find_handlers(self, event_type: str) -> list[EventHandler]:
        """Find all handlers matching an event type."""
        handlers = []

        # Exact matches
        if event_type in self._handlers:
            handlers.extend(self._handlers[event_type])

        # Wildcard matches
        for compiled, handler in self._wildcard_handlers:
            if compiled.match(event_type):
                handlers.append(handler)

        return handlers

    async def replay(
        self,
        start_id: str = "0",
        count: int = 1000,
    ) -> int:
        """
        Replay events from stream history.

        Args:
            start_id: Stream entry ID to start from ("0" for beginning)
            count: Max events to replay

        Returns:
            Number of events replayed
        """
        if not self._redis:
            await self.connect()

        results = await self._redis.xrange(
            self.config.stream_name,
            min=start_id,
            max="+",
            count=count,
        )

        replayed = 0
        for entry_id, data in results:
            await self._process_stream_entry(entry_id, data)
            replayed += 1

        logger.info(f"Replayed {replayed} events from stream")
        return replayed

    async def get_stream_info(self) -> dict[str, Any]:
        """Get stream information."""
        if not self._redis:
            await self.connect()

        info = await self._redis.xinfo_stream(self.config.stream_name)
        groups = await self._redis.xinfo_groups(self.config.stream_name)

        return {
            "stream_name": self.config.stream_name,
            "length": info.get("length", 0),
            "groups": groups,
            "consumer_group": self.config.consumer_group,
            "consumer_name": self._consumer_name,
        }

    def get_stats(self) -> dict[str, Any]:
        """Get event bus statistics."""
        return {
            "running": self._running,
            "connected": self._redis is not None,
            "consumer_name": self._consumer_name,
            "stream_name": self.config.stream_name,
            "consumer_group": self.config.consumer_group,
            "exact_subscriptions": sum(len(h) for h in self._handlers.values()),
            "wildcard_subscriptions": len(self._wildcard_handlers),
            "events_published": self._events_published,
            "events_received": self._events_received,
            "events_processed": self._events_processed,
            "events_failed": self._events_failed,
        }


class HybridEventBus:
    """
    Combines LocalEventBus and DistributedEventBus for optimal performance.

    - Local events stay in-process (fast)
    - Distributed events go through Redis (scalable)
    - Automatic routing based on event type or configuration
    """

    def __init__(
        self,
        local_bus: Optional[LocalEventBus] = None,
        distributed_bus: Optional[DistributedEventBus] = None,
        distributed_patterns: Optional[list[str]] = None,
    ):
        self.local_bus = local_bus
        self.distributed_bus = distributed_bus
        self.distributed_patterns = distributed_patterns or [
            "task.*",
            "agent.*",
            "policy.*",
            "model.*",
            "memory.*",
            "voice.*",
            "automation.*",
            "security.*",
        ]

        # Compile patterns
        import re
        self._distributed_regex = []
        for pattern in self.distributed_patterns:
            regex = pattern.replace(".", r"\.")
            regex = regex.replace("**", ".*")
            regex = regex.replace("*", "[^.]*")
            regex = regex.replace("?", ".")
            self._distributed_regex.append(re.compile(f"^{regex}$"))

    def _should_distribute(self, event_type: str) -> bool:
        """Check if event should go to distributed bus."""
        if not self.distributed_bus:
            return False
        return any(r.match(event_type) for r in self._distributed_regex)

    async def start(self) -> None:
        """Start both buses."""
        if self.local_bus:
            await self.local_bus.start()
        if self.distributed_bus:
            await self.distributed_bus.start()

    async def stop(self) -> None:
        """Stop both buses."""
        if self.local_bus:
            await self.local_bus.stop()
        if self.distributed_bus:
            await self.distributed_bus.stop()

    async def subscribe(
        self,
        pattern: str,
        handler: EventHandler,
        priority: int = 0,
    ) -> str:
        """Subscribe to events on appropriate bus(es)."""
        # Subscribe on local bus
        local_id = None
        if self.local_bus:
            local_id = await self.local_bus.subscribe(pattern, handler, priority)

        # Subscribe on distributed bus if pattern matches
        if self.distributed_bus and self._should_distribute(pattern):
            self.distributed_bus.subscribe(pattern, handler)

        return local_id or ""

    async def unsubscribe(self, subscription_id: str) -> bool:
        """Unsubscribe from both buses."""
        result = False
        if self.local_bus:
            result = await self.local_bus.unsubscribe(subscription_id)
        # Note: distributed bus unsubscription needs pattern+handler
        return result

    async def publish(self, event: Event) -> None:
        """Publish to appropriate bus based on event type."""
        if self._should_distribute(event.type):
            if self.distributed_bus:
                await self.distributed_bus.publish(event)
            # Also publish locally for local subscribers
            if self.local_bus:
                await self.local_bus.publish(event)
        else:
            if self.local_bus:
                await self.local_bus.publish(event)

    async def publish_sync(self, event: Event) -> None:
        """Publish synchronously to local bus only."""
        if self.local_bus:
            await self.local_bus.publish_sync(event)

    def get_stats(self) -> dict[str, Any]:
        """Get combined statistics."""
        stats = {"hybrid": True}

        if self.local_bus:
            stats["local"] = self.local_bus.get_stats()

        if self.distributed_bus:
            stats["distributed"] = self.distributed_bus.get_stats()

        return stats