# core/events/bus.py
"""
LocalEventBus - In-process event bus with priority queue and wildcard subscriptions.

Provides async event publishing with:
- Priority queue ordering (asyncio.PriorityQueue)
- Exact topic subscriptions
- Wildcard pattern subscriptions (e.g., "task.*", "agent.health_check")
- Background worker with retry logic
- Dead letter queue with size limit
- Global lifecycle management
"""

from __future__ import annotations
import asyncio
import logging
import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional
from core.events.models import Event, EventPriority, EventTypes

logger = logging.getLogger(__name__)


# Type alias for event handlers
EventHandler = Callable[[Event], Any]


@dataclass
class Subscription:
    """Represents a subscription to an event topic/pattern."""
    id: str
    pattern: str  # Exact topic or wildcard pattern
    handler: EventHandler
    priority: int = 0  # Handler priority (higher = runs first)
    is_wildcard: bool = field(init=False)
    compiled_pattern: re.Pattern = field(init=False)

    def __post_init__(self):
        self.is_wildcard = "*" in self.pattern or "?" in self.pattern
        # Convert wildcard pattern to regex
        # * matches any characters except dot, ** matches any including dot
        # ? matches single character
        regex_pattern = self.pattern.replace(".", r"\.")
        regex_pattern = regex_pattern.replace("**", ".*")
        regex_pattern = regex_pattern.replace("*", "[^.]*")
        regex_pattern = regex_pattern.replace("?", ".")
        self.compiled_pattern = re.compile(f"^{regex_pattern}$")

    def matches(self, topic: str) -> bool:
        """Check if this subscription matches the given topic."""
        if self.is_wildcard:
            return bool(self.compiled_pattern.match(topic))
        return self.pattern == topic


@dataclass
class DeadLetterEntry:
    """Entry in the dead letter queue."""
    event: Event
    error: str
    failed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    retry_count: int = 0


class LocalEventBus:
    """
    In-process event bus with priority queue and wildcard subscriptions.

    Features:
    - asyncio.PriorityQueue for ordered event processing
    - Exact and wildcard topic subscriptions
    - Background worker with configurable concurrency
    - Retry logic with exponential backoff
    - Dead letter queue with size limit
    - Graceful shutdown
    """

    def __init__(
        self,
        worker_count: int = 4,
        queue_maxsize: int = 10000,
        dead_letter_maxsize: int = 1000,
        default_retry_delay: float = 1.0,
        max_retry_delay: float = 60.0,
    ):
        self.worker_count = worker_count
        self.queue_maxsize = queue_maxsize
        self.dead_letter_maxsize = dead_letter_maxsize
        self.default_retry_delay = default_retry_delay
        self.max_retry_delay = max_retry_delay

        # Event queue (priority queue - higher priority first)
        self._queue: asyncio.PriorityQueue[tuple[int, Event]] = asyncio.PriorityQueue(maxsize=queue_maxsize)

        # Subscriptions: topic -> list of subscriptions
        self._subscriptions: dict[str, list[Subscription]] = defaultdict(list)
        self._wildcard_subscriptions: list[Subscription] = []

        # Dead letter queue
        self._dead_letter: list[DeadLetterEntry] = []

        # Worker management
        self._workers: list[asyncio.Task] = []
        self._running = False
        self._shutdown_event = asyncio.Event()

        # Metrics
        self._events_published = 0
        self._events_processed = 0
        self._events_failed = 0
        self._dead_letter_count = 0

        # Lock for subscription modifications
        self._sub_lock = asyncio.Lock()

    async def start(self) -> None:
        """Start the background workers."""
        if self._running:
            return

        self._running = True
        self._shutdown_event.clear()

        for i in range(self.worker_count):
            worker = asyncio.create_task(self._worker(f"worker-{i}"))
            self._workers.append(worker)

        logger.info(f"LocalEventBus started with {self.worker_count} workers")

    async def stop(self, timeout: float = 30.0) -> None:
        """Stop the event bus gracefully."""
        if not self._running:
            return

        self._running = False
        self._shutdown_event.set()

        # Wait for workers to finish current work
        try:
            await asyncio.wait_for(
                asyncio.gather(*self._workers, return_exceptions=True),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.warning("Event bus shutdown timed out, cancelling workers")
            for worker in self._workers:
                worker.cancel()
            await asyncio.gather(*self._workers, return_exceptions=True)

        self._workers.clear()
        logger.info("LocalEventBus stopped")

    async def subscribe(
        self,
        pattern: str,
        handler: EventHandler,
        priority: int = 0,
    ) -> str:
        """
        Subscribe to events matching a pattern.

        Args:
            pattern: Event topic pattern (exact or wildcard like "task.*")
            handler: Async function to handle events
            priority: Handler priority (higher runs first)

        Returns:
            Subscription ID for unsubscribing
        """
        subscription = Subscription(
            id=str(uuid.uuid4()),
            pattern=pattern,
            handler=handler,
            priority=priority,
        )

        async with self._sub_lock:
            if subscription.is_wildcard:
                self._wildcard_subscriptions.append(subscription)
                # Sort by priority (highest first)
                self._wildcard_subscriptions.sort(key=lambda s: -s.priority)
            else:
                self._subscriptions[pattern].append(subscription)
                self._subscriptions[pattern].sort(key=lambda s: -s.priority)

        logger.debug(f"Subscribed {subscription.id} to pattern '{pattern}'")
        return subscription.id

    async def unsubscribe(self, subscription_id: str) -> bool:
        """
        Unsubscribe by subscription ID.

        Returns:
            True if subscription was found and removed
        """
        async with self._sub_lock:
            # Check exact subscriptions
            for topic, subs in self._subscriptions.items():
                for i, sub in enumerate(subs):
                    if sub.id == subscription_id:
                        subs.pop(i)
                        logger.debug(f"Unsubscribed {subscription_id} from '{topic}'")
                        return True

            # Check wildcard subscriptions
            for i, sub in enumerate(self._wildcard_subscriptions):
                if sub.id == subscription_id:
                    self._wildcard_subscriptions.pop(i)
                    logger.debug(f"Unsubscribed {subscription_id} from wildcard")
                    return True

        return False

    def _find_matching_subscriptions(self, topic: str) -> list[Subscription]:
        """Find all subscriptions matching a topic."""
        matches = []

        # Exact matches
        if topic in self._subscriptions:
            matches.extend(self._subscriptions[topic])

        # Wildcard matches
        for sub in self._wildcard_subscriptions:
            if sub.matches(topic):
                matches.append(sub)

        # Sort by priority (highest first)
        matches.sort(key=lambda s: -s.priority)
        return matches

    async def publish(self, event: Event) -> None:
        """
        Publish an event to the bus.

        Events are queued for async processing by background workers.
        """
        if not self._running:
            raise RuntimeError("Event bus is not running")

        # Priority queue uses (priority, event) - negate priority for max-heap behavior
        queue_item = (-int(event.priority), event)

        try:
            await self._queue.put(queue_item)
            self._events_published += 1
        except asyncio.QueueFull:
            logger.error(f"Event queue full, dropping event: {event.type}")
            self._events_failed += 1
            raise

    async def publish_sync(self, event: Event) -> None:
        """
        Publish an event and wait for all handlers to complete.

        Use sparingly - bypasses the queue for immediate processing.
        """
        subscriptions = self._find_matching_subscriptions(event.type)

        if not subscriptions:
            logger.debug(f"No subscribers for event type: {event.type}")
            return

        # Run all handlers concurrently
        tasks = [self._run_handler(sub, event) for sub in subscriptions]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _worker(self, name: str) -> None:
        """Background worker that processes events from the queue."""
        logger.debug(f"Event bus worker {name} started")

        while self._running:
            try:
                # Wait for event with timeout to check shutdown
                try:
                    _, event = await asyncio.wait_for(
                        self._queue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue

                await self._process_event(event)
                self._queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Worker {name} error: {e}")

        logger.debug(f"Event bus worker {name} stopped")

    async def _process_event(self, event: Event) -> None:
        """Process a single event through all matching subscriptions."""
        subscriptions = self._find_matching_subscriptions(event.type)

        if not subscriptions:
            logger.debug(f"No subscribers for event type: {event.type}")
            return

        # Run all handlers
        for subscription in subscriptions:
            try:
                await self._run_handler(subscription, event)
            except Exception as e:
                logger.error(f"Handler {subscription.id} failed for event {event.type}: {e}")
                await self._handle_handler_failure(event, subscription, e)

        self._events_processed += 1

    async def _run_handler(self, subscription: Subscription, event: Event) -> None:
        """Run a single handler with error handling."""
        handler = subscription.handler

        if asyncio.iscoroutinefunction(handler):
            await handler(event)
        else:
            # Run sync handler in executor
            await asyncio.get_event_loop().run_in_executor(None, handler, event)

    async def _handle_handler_failure(
        self,
        event: Event,
        subscription: Subscription,
        error: Exception,
    ) -> None:
        """Handle handler failure with retry logic."""
        event.retry_count += 1

        if event.retry_count <= event.max_retries:
            # Schedule retry with exponential backoff
            delay = min(
                self.default_retry_delay * (2 ** (event.retry_count - 1)),
                self.max_retry_delay
            )

            logger.warning(
                f"Retrying event {event.type} (attempt {event.retry_count}/{event.max_retries}) "
                f"after {delay}s due to: {error}"
            )

            await asyncio.sleep(delay)

            # Re-queue for retry
            await self.publish(event)
        else:
            # Max retries exceeded - move to dead letter queue
            await self._add_to_dead_letter(event, str(error))
            self._events_failed += 1

    async def _add_to_dead_letter(self, event: Event, error: str) -> None:
        """Add event to dead letter queue."""
        entry = DeadLetterEntry(event=event, error=error)

        if len(self._dead_letter) >= self.dead_letter_maxsize:
            # Remove oldest entry
            self._dead_letter.pop(0)

        self._dead_letter.append(entry)
        self._dead_letter_count += 1

        logger.error(f"Event moved to dead letter queue: {event.type} - {error}")

    def get_dead_letter(self, limit: int = 100) -> list[DeadLetterEntry]:
        """Get dead letter entries (newest first)."""
        return list(reversed(self._dead_letter))[:limit]

    def clear_dead_letter(self) -> int:
        """Clear dead letter queue, return count of cleared entries."""
        count = len(self._dead_letter)
        self._dead_letter.clear()
        return count

    def get_stats(self) -> dict[str, Any]:
        """Get event bus statistics."""
        return {
            "running": self._running,
            "worker_count": self.worker_count,
            "queue_size": self._queue.qsize(),
            "queue_maxsize": self.queue_maxsize,
            "subscriptions_exact": sum(len(s) for s in self._subscriptions.values()),
            "subscriptions_wildcard": len(self._wildcard_subscriptions),
            "events_published": self._events_published,
            "events_processed": self._events_processed,
            "events_failed": self._events_failed,
            "dead_letter_size": len(self._dead_letter),
            "dead_letter_maxsize": self.dead_letter_maxsize,
        }

    async def replay_dead_letter(self, limit: int = 100) -> int:
        """Replay events from dead letter queue."""
        replayed = 0
        entries = self.get_dead_letter(limit)

        for entry in entries:
            entry.event.retry_count = 0  # Reset retry count
            await self.publish(entry.event)
            replayed += 1

        # Clear replayed entries
        self._dead_letter = self._dead_letter[:-replayed] if replayed else self._dead_letter

        logger.info(f"Replayed {replayed} events from dead letter queue")
        return replayed


# Global event bus instance
_event_bus: Optional[LocalEventBus] = None


async def get_event_bus() -> LocalEventBus:
    """Get the global event bus instance."""
    global _event_bus
    if _event_bus is None:
        _event_bus = LocalEventBus()
        await _event_bus.start()
    return _event_bus


async def init_event_bus(
    worker_count: int = 4,
    queue_maxsize: int = 10000,
    dead_letter_maxsize: int = 1000,
) -> LocalEventBus:
    """Initialize the global event bus with custom configuration."""
    global _event_bus
    if _event_bus is not None:
        await _event_bus.stop()

    _event_bus = LocalEventBus(
        worker_count=worker_count,
        queue_maxsize=queue_maxsize,
        dead_letter_maxsize=dead_letter_maxsize,
    )
    await _event_bus.start()
    return _event_bus


async def shutdown_event_bus() -> None:
    """Shutdown the global event bus."""
    global _event_bus
    if _event_bus is not None:
        await _event_bus.stop()
        _event_bus = None