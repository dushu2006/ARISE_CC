# ARISE — Event Bus & Messaging Architecture

## Overview

Centralized event-driven communication backbone for ARISE's modular monolith. Provides reliable, ordered, and observable message passing between all components with support for local and distributed deployments.

---

## 1. Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        EVENT BUS LAYER                                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐             │
│  │   Producers  │───▶│  Event Bus   │───▶│  Consumers   │             │
│  │              │    │              │    │              │             │
│  │ • Task Eng   │    │ • Topics     │    │ • Policy Eng │             │
│  │ • Model Rtr  │    │ • Partitions │    │ • Memory Sys │             │
│  │ • Agents     │    │ • Retention  │    │ • Voice      │             │
│  │ • Automation │    │ • Replay     │    │ • Automation │             │
│  │ • Security   │    │ • Dead Letter│    │ • UI         │             │
│  └──────────────┘    └──────────────┘    └──────────────┘             │
│         │                   │                    │                     │
│         ▼                   ▼                    ▼                     │
│  ┌──────────────────────────────────────────────────────────────┐     │
│  │                    EVENT STORE (SQLite + WAL)                │     │
│  │  • Immutable event log  • Indexing by topic/correlation      │     │
│  │  • Snapshots            • Compaction                         │     │
│  └──────────────────────────────────────────────────────────────┘     │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Core Concepts

### 2.1 Event Structure

```python
# core/events/models.py
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from datetime import datetime
from enum import Enum
import uuid
import json

class EventPriority(Enum):
    LOW = 0
    NORMAL = 50
    HIGH = 100
    CRITICAL = 200

@dataclass
class Event:
    """Immutable event record"""
    # Identity
    event_id: str = field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:16]}")
    event_type: str = ""           # e.g., "task.created", "memory.stored"
    topic: str = ""                # Routing key: "tasks", "memory", "agents"
    
    # Payload
    payload: Dict[str, Any] = field(default_factory=dict)
    schema_version: int = 1
    
    # Context
    correlation_id: str = ""       # Groups related events
    causation_id: str = ""         # Event that caused this event
    source_component: str = ""     # "task_engine", "model_router", etc.
    source_instance: str = ""      # Instance ID for distributed deployments
    
    # Timing
    timestamp: datetime = field(default_factory=datetime.utcnow)
    processed_at: Optional[datetime] = None
    
    # Delivery
    priority: EventPriority = EventPriority.NORMAL
    ttl: Optional[int] = None      # Time-to-live in seconds
    retry_count: int = 0
    max_retries: int = 3
    
    # Metadata
    headers: Dict[str, str] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "topic": self.topic,
            "payload": self.payload,
            "schema_version": self.schema_version,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "source_component": self.source_component,
            "source_instance": self.source_instance,
            "timestamp": self.timestamp.isoformat() + "Z",
            "processed_at": self.processed_at.isoformat() + "Z" if self.processed_at else None,
            "priority": self.priority.value,
            "ttl": self.ttl,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "headers": self.headers,
            "tags": self.tags,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Event':
        evt = cls(
            event_id=data["event_id"],
            event_type=data["event_type"],
            topic=data["topic"],
            payload=data["payload"],
            schema_version=data.get("schema_version", 1),
            correlation_id=data.get("correlation_id", ""),
            causation_id=data.get("causation_id", ""),
            source_component=data.get("source_component", ""),
            source_instance=data.get("source_instance", ""),
            timestamp=datetime.fromisoformat(data["timestamp"].rstrip("Z")),
            processed_at=datetime.fromisoformat(data["processed_at"].rstrip("Z")) if data.get("processed_at") else None,
            priority=EventPriority(data.get("priority", 50)),
            ttl=data.get("ttl"),
            retry_count=data.get("retry_count", 0),
            max_retries=data.get("max_retries", 3),
            headers=data.get("headers", {}),
            tags=data.get("tags", []),
        )
        return evt
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_json(cls, json_str: str) -> 'Event':
        return cls.from_dict(json.loads(json_str))
```

### 2.2 Topic Design

```
Topic Hierarchy:
├── tasks
│   ├── tasks.created
│   ├── tasks.queued
│   ├── tasks.started
│   ├── tasks.progress
│   ├── tasks.completed
│   ├── tasks.failed
│   ├── tasks.cancelled
│   └── tasks.retry
├── policy
│   ├── policy.approval_requested
│   ├── policy.approval_granted
│   ├── policy.approval_denied
│   ├── policy.capability_granted
│   └── policy.capability_revoked
├── memory
│   ├── memory.stored
│   ├── memory.retrieved
│   ├── memory.consolidated
│   ├── memory.pii_detected
│   └── memory.expired
├── agents
│   ├── agents.spawned
│   ├── agents.delegated
│   ├── agents.verified
│   ├── agents.health_changed
│   └── agents.terminated
├── voice
│   ├── voice.wake_detected
│   ├── voice.session_started
│   ├── voice.transcription
│   ├── voice.synthesis
│   └── voice.session_ended
├── automation
│   ├── automation.action_executed
│   ├── automation.element_found
│   ├── automation.navigation
│   └── automation.error
├── security
│   ├── security.credential_accessed
│   ├── security.network_blocked
│   ├── security.prompt_injection
│   └── security.audit
└── system
    ├── system.startup
    ├── system.shutdown
    ├── system.health_check
    ├── system.metrics
    └── system.config_changed
```

---

## 3. Event Bus Implementation

### 3.1 Local Event Bus (In-Process)

```python
# core/events/bus.py
import asyncio
from typing import Dict, List, Callable, Awaitable, Optional, Set
from dataclasses import dataclass, field
from collections import defaultdict
import logging
from contextvars import ContextVar

from core.events.models import Event, EventPriority

logger = logging.getLogger(__name__)

# Type aliases
EventHandler = Callable[[Event], Awaitable[None]]
SubscriptionId = str

@dataclass
class Subscription:
    """Event subscription"""
    subscription_id: SubscriptionId
    topic_pattern: str           # e.g., "tasks.*", "memory.stored"
    handler: EventHandler
    priority: int = 0            # Higher = earlier execution
    filter_fn: Optional[Callable[[Event], bool]] = None
    once: bool = False           # Auto-unsubscribe after first event

class LocalEventBus:
    """High-performance in-process event bus"""
    
    def __init__(self):
        self._subscriptions: Dict[str, List[Subscription]] = defaultdict(list)
        self._wildcard_subscriptions: List[Subscription] = []
        self._running = False
        self._event_queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._worker_task: Optional[asyncio.Task] = None
        self._subscription_counter = 0
        self._dead_letter_queue: List[Event] = []
        self._max_dlq_size = 1000
    
    async def start(self):
        """Start event processing worker"""
        if self._running:
            return
        self._running = True
        self._worker_task = asyncio.create_task(self._process_events())
        logger.info("Event bus started")
    
    async def stop(self):
        """Stop event processing"""
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        logger.info("Event bus stopped")
    
    def subscribe(
        self,
        topic_pattern: str,
        handler: EventHandler,
        priority: int = 0,
        filter_fn: Optional[Callable[[Event], bool]] = None,
        once: bool = False,
    ) -> SubscriptionId:
        """Subscribe to events matching topic pattern"""
        self._subscription_counter += 1
        sub_id = f"sub_{self._subscription_counter}"
        
        subscription = Subscription(
            subscription_id=sub_id,
            topic_pattern=topic_pattern,
            handler=handler,
            priority=priority,
            filter_fn=filter_fn,
            once=once,
        )
        
        if "*" in topic_pattern or topic_pattern.endswith("."):
            # Wildcard subscription
            self._wildcard_subscriptions.append(subscription)
            self._wildcard_subscriptions.sort(key=lambda s: -s.priority)
        else:
            # Exact topic subscription
            self._subscriptions[topic_pattern].append(subscription)
            self._subscriptions[topic_pattern].sort(key=lambda s: -s.priority)
        
        logger.debug(f"Subscribed {sub_id} to {topic_pattern}")
        return sub_id
    
    def unsubscribe(self, subscription_id: SubscriptionId) -> bool:
        """Unsubscribe by ID"""
        # Check exact subscriptions
        for topic, subs in self._subscriptions.items():
            for i, sub in enumerate(subs):
                if sub.subscription_id == subscription_id:
                    subs.pop(i)
                    logger.debug(f"Unsubscribed {subscription_id} from {topic}")
                    return True
        
        # Check wildcard subscriptions
        for i, sub in enumerate(self._wildcard_subscriptions):
            if sub.subscription_id == subscription_id:
                self._wildcard_subscriptions.pop(i)
                logger.debug(f"Unsubscribed {subscription_id} from wildcard")
                return True
        
        return False
    
    async def publish(self, event: Event) -> None:
        """Publish event to bus (async, non-blocking)"""
        # Priority queue: negative priority for max-heap behavior
        await self._event_queue.put((-event.priority.value, event))
    
    async def publish_sync(self, event: Event, timeout: float = 5.0) -> List[Any]:
        """Publish and wait for all handlers to complete"""
        results = []
        handlers = self._get_handlers(event)
        
        for handler in handlers:
            try:
                result = await asyncio.wait_for(handler(event), timeout=timeout)
                results.append(result)
            except asyncio.TimeoutError:
                logger.error(f"Handler timeout for {event.event_type}")
                results.append(None)
            except Exception as e:
                logger.exception(f"Handler error for {event.event_type}")
                results.append(e)
        
        return results
    
    def _get_handlers(self, event: Event) -> List[EventHandler]:
        """Get all handlers matching event topic"""
        handlers = []
        
        # Exact matches
        for sub in self._subscriptions.get(event.topic, []):
            if sub.filter_fn is None or sub.filter_fn(event):
                handlers.append(sub.handler)
        
        # Wildcard matches
        for sub in self._wildcard_subscriptions:
            if self._match_pattern(event.topic, sub.topic_pattern):
                if sub.filter_fn is None or sub.filter_fn(event):
                    handlers.append(sub.handler)
        
        return handlers
    
    def _match_pattern(self, topic: str, pattern: str) -> bool:
        """Match topic against pattern with wildcards"""
        if pattern == "*":
            return True
        if pattern.endswith("*"):
            prefix = pattern[:-1]
            return topic.startswith(prefix)
        if pattern.endswith("."):
            prefix = pattern
            return topic.startswith(prefix)
        return topic == pattern
    
    async def _process_events(self):
        """Background event processing loop"""
        while self._running:
            try:
                # Wait for event with timeout to check running flag
                try:
                    _, event = await asyncio.wait_for(
                        self._event_queue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue
                
                await self._deliver_event(event)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("Error in event processing loop")
    
    async def _deliver_event(self, event: Event):
        """Deliver event to all matching handlers"""
        handlers = self._get_handlers(event)
        
        if not handlers:
            logger.debug(f"No handlers for {event.topic}")
            return
        
        # Execute handlers concurrently
        tasks = []
        for handler in handlers:
            tasks.append(self._safe_handler(handler, event))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _safe_handler(self, handler: EventHandler, event: Event):
        """Execute handler with error handling and retry logic"""
        try:
            await handler(event)
        except Exception as e:
            logger.error(f"Handler failed for {event.event_type}: {e}")
            
            # Retry logic
            if event.retry_count < event.max_retries:
                event.retry_count += 1
                # Re-queue with delay
                await asyncio.sleep(2 ** event.retry_count)
                await self.publish(event)
            else:
                # Move to dead letter queue
                await self._dead_letter(event)
    
    async def _dead_letter(self, event: Event):
        """Move event to dead letter queue"""
        self._dead_letter_queue.append(event)
        if len(self._dead_letter_queue) > self._max_dlq_size:
            self._dead_letter_queue.pop(0)
        
        # Emit dead letter event
        dlq_event = Event(
            event_type="system.dead_letter",
            topic="system",
            payload={"original_event": event.to_dict(), "error": "Max retries exceeded"},
            source_component="event_bus",
        )
        await self.publish(dlq_event)
    
    def get_stats(self) -> dict:
        """Get bus statistics"""
        return {
            "running": self._running,
            "queue_size": self._event_queue.qsize(),
            "subscriptions": {
                "exact": sum(len(s) for s in self._subscriptions.values()),
                "wildcard": len(self._wildcard_subscriptions),
            },
            "dead_letter_queue_size": len(self._dead_letter_queue),
        }

# Global instance
_event_bus: Optional[LocalEventBus] = None

def get_event_bus() -> LocalEventBus:
    global _event_bus
    if _event_bus is None:
        _event_bus = LocalEventBus()
    return _event_bus

async def init_event_bus() -> LocalEventBus:
    bus = get_event_bus()
    await bus.start()
    return bus

async def shutdown_event_bus():
    global _event_bus
    if _event_bus:
        await _event_bus.stop()
        _event_bus = None
```

### 3.2 Distributed Event Bus (Redis Streams)

```python
# core/events/distributed_bus.py
import asyncio
import json
import logging
from typing import Dict, List, Callable, Awaitable, Optional
from dataclasses import dataclass

import redis.asyncio as redis
from core.events.models import Event

logger = logging.getLogger(__name__)

@dataclass
class StreamConfig:
    max_len: int = 10000
    max_len_approx: bool = True

class DistributedEventBus:
    """Redis Streams based distributed event bus"""
    
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_url = redis_url
        self._redis: Optional[redis.Redis] = None
        self._consumer_groups: Dict[str, str] = {}  # topic -> group_name
        self._handlers: Dict[str, List[Callable]] = {}
        self._running = False
        self._consumer_tasks: List[asyncio.Task] = []
    
    async def connect(self):
        """Connect to Redis"""
        self._redis = redis.from_url(self.redis_url, decode_responses=True)
        await self._redis.ping()
        logger.info("Connected to Redis for distributed event bus")
    
    async def disconnect(self):
        """Disconnect from Redis"""
        self._running = False
        for task in self._consumer_tasks:
            task.cancel()
        await asyncio.gather(*self._consumer_tasks, return_exceptions=True)
        
        if self._redis:
            await self._redis.close()
        logger.info("Disconnected from Redis")
    
    async def publish(self, event: Event) -> str:
        """Publish event to Redis Stream"""
        stream_name = f"events:{event.topic}"
        
        # Add to stream
        event_id = await self._redis.xadd(
            stream_name,
            {"data": event.to_json()},
            maxlen=10000,
            approximate=True
        )
        
        logger.debug(f"Published {event.event_type} to {stream_name} as {event_id}")
        return event_id
    
    def subscribe(
        self,
        topic: str,
        handler: Callable[[Event], Awaitable[None]],
        group_name: str = None,
        consumer_name: str = None,
    ):
        """Subscribe to topic with consumer group"""
        if topic not in self._handlers:
            self._handlers[topic] = []
        self._handlers[topic].append(handler)
        
        if group_name:
            self._consumer_groups[topic] = group_name
    
    async def start_consuming(self, consumer_name: str = None):
        """Start consuming from all subscribed topics"""
        self._running = True
        consumer_name = consumer_name or f"consumer_{id(self)}"
        
        for topic, handlers in self._handlers.items():
            group_name = self._consumer_groups.get(topic, f"group_{topic}")
            task = asyncio.create_task(
                self._consume_stream(topic, group_name, consumer_name, handlers)
            )
            self._consumer_tasks.append(task)
        
        logger.info(f"Started consuming from {len(self._handlers)} topics")
    
    async def _consume_stream(
        self,
        topic: str,
        group_name: str,
        consumer_name: str,
        handlers: List[Callable],
    ):
        """Consume events from a stream"""
        stream_name = f"events:{topic}"
        
        # Create consumer group if not exists
        try:
            await self._redis.xgroup_create(stream_name, group_name, id="0", mkstream=True)
        except redis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise
        
        while self._running:
            try:
                # Read new messages
                messages = await self._redis.xreadgroup(
                    group_name,
                    consumer_name,
                    {stream_name: ">"},
                    count=10,
                    block=5000,
                )
                
                if not messages:
                    continue
                
                for stream, entries in messages:
                    for entry_id, entry_data in entries:
                        try:
                            event = Event.from_json(entry_data["data"])
                            
                            # Process with all handlers
                            for handler in handlers:
                                await handler(event)
                            
                            # Acknowledge
                            await self._redis.xack(stream_name, group_name, entry_id)
                            
                        except Exception as e:
                            logger.exception(f"Error processing event {entry_id}")
                            # Don't ack - will be redelivered
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Error in consumer for {topic}")
                await asyncio.sleep(1)
    
    async def replay(
        self,
        topic: str,
        from_timestamp: float,
        handler: Callable[[Event], Awaitable[None]],
    ):
        """Replay events from timestamp"""
        stream_name = f"events:{topic}"
        
        messages = await self._redis.xrange(
            stream_name,
            min=f"({int(from_timestamp * 1000)}",
            max="+",
            count=1000,
        )
        
        for entry_id, entry_data in messages:
            event = Event.from_json(entry_data["data"])
            await handler(event)

# Hybrid bus combining local and distributed
class HybridEventBus:
    """Combines local and distributed event buses"""
    
    def __init__(
        self,
        local_bus: LocalEventBus,
        distributed_bus: DistributedEventBus = None,
    ):
        self.local = local_bus
        self.distributed = distributed_bus
        self._bridged_topics: Set[str] = set()
    
    async def start(self):
        await self.local.start()
        if self.distributed:
            await self.distributed.connect()
            await self.distributed.start_consuming()
    
    async def stop(self):
        await self.local.stop()
        if self.distributed:
            await self.distributed.disconnect()
    
    def bridge_topic(self, topic: str, direction: str = "both"):
        """Bridge topic between local and distributed bus"""
        self._bridged_topics.add(topic)
        
        if direction in ("both", "local_to_distributed"):
            # Local -> Distributed
            self.local.subscribe(
                topic,
                self._forward_to_distributed,
                priority=100,
            )
        
        if direction in ("both", "distributed_to_local"):
            # Distributed -> Local
            if self.distributed:
                self.distributed.subscribe(
                    topic,
                    self._forward_to_local,
                )
    
    async def _forward_to_distributed(self, event: Event):
        if self.distributed and event.topic in self._bridged_topics:
            await self.distributed.publish(event)
    
    async def _forward_to_local(self, event: Event):
        if event.topic in self._bridged_topics:
            await self.local.publish(event)
    
    async def publish(self, event: Event, distribute: bool = True):
        """Publish to local and optionally distributed bus"""
        await self.local.publish(event)
        
        if distribute and self.distributed and event.topic in self._bridged_topics:
            await self.distributed.publish(event)
```

---

## 4. Event Sourcing & Projections

### 4.1 Event Store

```python
# core/events/store.py
import sqlite3
import asyncio
import json
import logging
from typing import List, Optional, AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from core.events.models import Event

logger = logging.getLogger(__name__)

@dataclass
class EventRecord:
    """Persisted event record"""
    id: int
    event_id: str
    event_type: str
    topic: str
    payload: str  # JSON
    schema_version: int
    correlation_id: str
    causation_id: str
    source_component: str
    source_instance: str
    timestamp: str
    priority: int
    headers: str  # JSON
    tags: str     # JSON

class EventStore:
    """SQLite-based event store with WAL mode"""
    
    def __init__(self, db_path: str = "data/events.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()
    
    def _init_db(self):
        """Initialize database schema"""
        self._conn = sqlite3.connect(
            self.db_path,
            check_same_thread=False,
            isolation_level=None,  # Autocommit
        )
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA cache_size=-32768")  # 32MB
        
        # Events table
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT UNIQUE NOT NULL,
                event_type TEXT NOT NULL,
                topic TEXT NOT NULL,
                payload TEXT NOT NULL,
                schema_version INTEGER NOT NULL DEFAULT 1,
                correlation_id TEXT,
                causation_id TEXT,
                source_component TEXT NOT NULL,
                source_instance TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                priority INTEGER NOT NULL DEFAULT 50,
                headers TEXT,
                tags TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        
        # Indexes for common queries
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_events_topic ON events(topic)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_events_correlation ON events(correlation_id)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_events_source ON events(source_component)")
        
        # Snapshots table for projections
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS snapshots (
                aggregate_id TEXT PRIMARY KEY,
                aggregate_type TEXT NOT NULL,
                state TEXT NOT NULL,
                version INTEGER NOT NULL,
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        
        # Dead letter queue
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS dead_letters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL,
                event_data TEXT NOT NULL,
                error TEXT NOT NULL,
                retry_count INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        
        logger.info(f"Event store initialized at {self.db_path}")
    
    async def append(self, event: Event) -> int:
        """Append event to store"""
        loop = asyncio.get_event_loop()
        
        def _insert():
            cursor = self._conn.execute("""
                INSERT INTO events (
                    event_id, event_type, topic, payload, schema_version,
                    correlation_id, causation_id, source_component,
                    source_instance, timestamp, priority, headers, tags
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event.event_id,
                event.event_type,
                event.topic,
                json.dumps(event.payload),
                event.schema_version,
                event.correlation_id,
                event.causation_id,
                event.source_component,
                event.source_instance,
                event.timestamp.isoformat() + "Z",
                event.priority.value,
                json.dumps(event.headers),
                json.dumps(event.tags),
            ))
            return cursor.lastrowid
        
        return await loop.run_in_executor(None, _insert)
    
    async def append_batch(self, events: List[Event]) -> List[int]:
        """Batch append events"""
        loop = asyncio.get_event_loop()
        
        def _batch_insert():
            cursor = self._conn.cursor()
            ids = []
            for event in events:
                cursor.execute("""
                    INSERT INTO events (
                        event_id, event_type, topic, payload, schema_version,
                        correlation_id, causation_id, source_component,
                        source_instance, timestamp, priority, headers, tags
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    event.event_id,
                    event.event_type,
                    event.topic,
                    json.dumps(event.payload),
                    event.schema_version,
                    event.correlation_id,
                    event.causation_id,
                    event.source_component,
                    event.source_instance,
                    event.timestamp.isoformat() + "Z",
                    event.priority.value,
                    json.dumps(event.headers),
                    json.dumps(event.tags),
                ))
                ids.append(cursor.lastrowid)
            self._conn.commit()
            return ids
        
        return await loop.run_in_executor(None, _batch_insert)
    
    async def get_events(
        self,
        topic: str = None,
        event_type: str = None,
        correlation_id: str = None,
        from_timestamp: datetime = None,
        to_timestamp: datetime = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> List[Event]:
        """Query events with filters"""
        loop = asyncio.get_event_loop()
        
        def _query():
            conditions = []
            params = []
            
            if topic:
                conditions.append("topic = ?")
                params.append(topic)
            if event_type:
                conditions.append("event_type = ?")
                params.append(event_type)
            if correlation_id:
                conditions.append("correlation_id = ?")
                params.append(correlation_id)
            if from_timestamp:
                conditions.append("timestamp >= ?")
                params.append(from_timestamp.isoformat() + "Z")
            if to_timestamp:
                conditions.append("timestamp <= ?")
                params.append(to_timestamp.isoformat() + "Z")
            
            where = " WHERE " + " AND ".join(conditions) if conditions else ""
            
            cursor = self._conn.execute(f"""
                SELECT * FROM events
                {where}
                ORDER BY timestamp ASC, id ASC
                LIMIT ? OFFSET ?
            """, params + [limit, offset])
            
            return [self._row_to_event(row) for row in cursor.fetchall()]
        
        return await loop.run_in_executor(None, _query)
    
    async def get_by_correlation(self, correlation_id: str) -> List[Event]:
        """Get all events for a correlation ID"""
        return await self.get_events(correlation_id=correlation_id, limit=10000)
    
    async def get_recent(self, topic: str, limit: int = 100) -> List[Event]:
        """Get most recent events for topic"""
        loop = asyncio.get_event_loop()
        
        def _query():
            cursor = self._conn.execute("""
                SELECT * FROM events
                WHERE topic = ?
                ORDER BY timestamp DESC, id DESC
                LIMIT ?
            """, (topic, limit))
            return [self._row_to_event(row) for row in cursor.fetchall()]
        
        return await loop.run_in_executor(None, _query)
    
    def _row_to_event(self, row) -> Event:
        """Convert database row to Event"""
        return Event(
            event_id=row[1],
            event_type=row[2],
            topic=row[3],
            payload=json.loads(row[4]),
            schema_version=row[5],
            correlation_id=row[6] or "",
            causation_id=row[7] or "",
            source_component=row[8],
            source_instance=row[9],
            timestamp=datetime.fromisoformat(row[10].rstrip("Z")),
            priority=EventPriority(row[11]),
            headers=json.loads(row[12]) if row[12] else {},
            tags=json.loads(row[13]) if row[13] else [],
        )
    
    async def save_snapshot(self, aggregate_id: str, aggregate_type: str, state: dict, version: int):
        """Save projection snapshot"""
        loop = asyncio.get_event_loop()
        
        def _save():
            self._conn.execute("""
                INSERT OR REPLACE INTO snapshots (aggregate_id, aggregate_type, state, version)
                VALUES (?, ?, ?, ?)
            """, (aggregate_id, aggregate_type, json.dumps(state), version))
            self._conn.commit()
        
        await loop.run_in_executor(None, _save)
    
    async def load_snapshot(self, aggregate_id: str) -> Optional[dict]:
        """Load projection snapshot"""
        loop = asyncio.get_event_loop()
        
        def _load():
            cursor = self._conn.execute("""
                SELECT state, version FROM snapshots WHERE aggregate_id = ?
            """, (aggregate_id,))
            row = cursor.fetchone()
            if row:
                return {"state": json.loads(row[0]), "version": row[1]}
            return None
        
        return await loop.run_in_executor(None, _load)
    
    async def add_to_dlq(self, event: Event, error: str, retry_count: int):
        """Add event to dead letter queue"""
        loop = asyncio.get_event_loop()
        
        def _insert():
            self._conn.execute("""
                INSERT INTO dead_letters (event_id, event_data, error, retry_count)
                VALUES (?, ?, ?, ?)
            """, (event.event_id, event.to_json(), error, retry_count))
            self._conn.commit()
        
        await loop.run_in_executor(None, _insert)
    
    async def get_dlq(self, limit: int = 100) -> List[dict]:
        """Get dead letter queue entries"""
        loop = asyncio.get_event_loop()
        
        def _query():
            cursor = self._conn.execute("""
                SELECT * FROM dead_letters ORDER BY created_at DESC LIMIT ?
            """, (limit,))
            return [
                {
                    "id": row[0],
                    "event_id": row[1],
                    "event_data": json.loads(row[2]),
                    "error": row[3],
                    "retry_count": row[4],
                    "created_at": row[5],
                }
                for row in cursor.fetchall()
            ]
        
        return await loop.run_in_executor(None, _query)
    
    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
```

### 4.2 Projections

```python
# core/events/projections.py
from typing import Dict, Any, Callable, Awaitable, List, Optional
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
import asyncio
import logging

from core.events.models import Event
from core.events.store import EventStore

logger = logging.getLogger(__name__)

@dataclass
class ProjectionState:
    """State of a projection"""
    aggregate_id: str
    aggregate_type: str
    state: Dict[str, Any] = field(default_factory=dict)
    version: int = 0
    last_event_id: str = ""
    last_event_timestamp: str = ""

class Projection(ABC):
    """Base class for event projections"""
    
    def __init__(self, name: str, event_store: EventStore):
        self.name = name
        self.event_store = event_store
        self._handlers: Dict[str, Callable[[Event], Awaitable[None]]] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._last_processed_id = 0
    
    def handles(self, event_type: str):
        """Decorator to register event handler"""
        def decorator(handler: Callable[[Event], Awaitable[None]]):
            self._handlers[event_type] = handler
            return handler
        return decorator
    
    @abstractmethod
    async def project(self, event: Event) -> None:
        """Process single event"""
        pass
    
    async def start(self, from_timestamp: str = None):
        """Start projection processing"""
        self._running = True
        self._task = asyncio.create_task(self._run(from_timestamp))
        logger.info(f"Projection {self.name} started")
    
    async def stop(self):
        """Stop projection"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info(f"Projection {self.name} stopped")
    
    async def _run(self, from_timestamp: str = None):
        """Main projection loop"""
        # Load checkpoint
        checkpoint = await self._load_checkpoint()
        if checkpoint:
            self._last_processed_id = checkpoint
        
        while self._running:
            try:
                # Fetch new events
                events = await self.event_store.get_events(
                    from_timestamp=from_timestamp,
                    limit=100,
                )
                
                # Filter to events after checkpoint
                new_events = [e for e in events if self._event_id_to_int(e.event_id) > self._last_processed_id]
                
                for event in new_events:
                    await self.project(event)
                    self._last_processed_id = self._event_id_to_int(event.event_id)
                
                # Save checkpoint periodically
                if new_events:
                    await self._save_checkpoint()
                
                await asyncio.sleep(1)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Error in projection {self.name}")
                await asyncio.sleep(5)
    
    def _event_id_to_int(self, event_id: str) -> int:
        """Convert event_id to integer for ordering"""
        # evt_<hex> -> extract numeric part
        try:
            return int(event_id.split("_")[1], 16)
        except (IndexError, ValueError):
            return 0
    
    async def _load_checkpoint(self) -> int:
        """Load last processed event ID"""
        # Implementation depends on storage
        return 0
    
    async def _save_checkpoint(self):
        """Save checkpoint"""
        pass

# Example: Task Status Projection
class TaskStatusProjection(Projection):
    """Projects task events into current task status view"""
    
    def __init__(self, event_store: EventStore):
        super().__init__("task_status", event_store)
        self._task_states: Dict[str, Dict] = {}
    
    @handles("task.created")
    @handles("task.queued")
    @handles("task.started")
    @handles("task.progress")
    @handles("task.completed")
    @handles("task.failed")
    @handles("task.cancelled")
    async def handle_task_event(self, event: Event):
        task_id = event.payload.get("task_id")
        if not task_id:
            return
        
        if task_id not in self._task_states:
            self._task_states[task_id] = {
                "task_id": task_id,
                "status": "unknown",
                "created_at": event.timestamp.isoformat(),
                "updated_at": event.timestamp.isoformat(),
            }
        
        state = self._task_states[task_id]
        state["updated_at"] = event.timestamp.isoformat()
        
        # Update status based on event type
        status_map = {
            "task.created": "created",
            "task.queued": "queued",
            "task.started": "running",
            "task.progress": "running",
            "task.completed": "completed",
            "task.failed": "failed",
            "task.cancelled": "cancelled",
        }
        
        state["status"] = status_map.get(event.event_type, state["status"])
        state["last_event"] = event.event_type
        
        # Store progress if available
        if "progress" in event.payload:
            state["progress"] = event.payload["progress"]
        
        # Store result if completed
        if event.event_type in ("task.completed", "task.failed"):
            state["result"] = event.payload.get("result")
            state["error"] = event.payload.get("error")
    
    async def project(self, event: Event):
        handler = self._handlers.get(event.event_type)
        if handler:
            await handler(event)
    
    def get_task_status(self, task_id: str) -> Optional[Dict]:
        return self._task_states.get(task_id)
    
    def get_all_tasks(self) -> List[Dict]:
        return list(self._task_states.values())

# Example: Agent Health Projection
class AgentHealthProjection(Projection):
    """Projects agent events into health dashboard"""
    
    def __init__(self, event_store: EventStore):
        super().__init__("agent_health", event_store)
        self._agent_states: Dict[str, Dict] = {}
    
    @handles("agents.spawned")
    @handles("agents.health_changed")
    @handles("agents.terminated")
    async def handle_agent_event(self, event: Event):
        agent_id = event.payload.get("agent_id")
        if not agent_id:
            return
        
        if event.event_type == "agents.terminated":
            self._agent_states.pop(agent_id, None)
            return
        
        if agent_id not in self._agent_states:
            self._agent_states[agent_id] = {
                "agent_id": agent_id,
                "role": event.payload.get("role", "unknown"),
                "status": "unknown",
                "last_heartbeat": None,
            }
        
        state = self._agent_states[agent_id]
        state["status"] = event.payload.get("status", state["status"])
        state["last_heartbeat"] = event.timestamp.isoformat()
        
        if "metrics" in event.payload:
            state["metrics"] = event.payload["metrics"]
    
    async def project(self, event: Event):
        handler = self._handlers.get(event.event_type)
        if handler:
            await handler(event)
    
    def get_agent_health(self, agent_id: str) -> Optional[Dict]:
        return self._agent_states.get(agent_id)
    
    def get_all_agents(self) -> List[Dict]:
        return list(self._agent_states.values())
```

---

## 5. Consumer Patterns

### 5.1 Event Handlers

```python
# core/events/handlers.py
from typing import Callable, Awaitable, List, Optional
from dataclasses import dataclass
import asyncio
import logging

from core.events.models import Event
from core.events.bus import LocalEventBus

logger = logging.getLogger(__name__)

@dataclass
class HandlerConfig:
    """Configuration for event handler"""
    topic_pattern: str
    priority: int = 0
    filter_fn: Optional[Callable[[Event], bool]] = None
    retry_policy: Optional[dict] = None
    timeout: float = 30.0

class EventHandlerRegistry:
    """Registry for event handlers with lifecycle management"""
    
    def __init__(self, event_bus: LocalEventBus):
        self.bus = event_bus
        self._handlers: List[tuple] = []  # (config, handler_func)
        self._subscription_ids: List[str] = []
    
    def register(self, config: HandlerConfig, handler: Callable[[Event], Awaitable[None]]):
        """Register event handler"""
        sub_id = self.bus.subscribe(
            topic_pattern=config.topic_pattern,
            handler=handler,
            priority=config.priority,
            filter_fn=config.filter_fn,
        )
        self._handlers.append((config, handler))
        self._subscription_ids.append(sub_id)
        logger.debug(f"Registered handler for {config.topic_pattern}")
    
    def register_method(self, obj, method_name: str, config: HandlerConfig):
        """Register bound method as handler"""
        handler = getattr(obj, method_name)
        self.register(config, handler)
    
    async def unregister_all(self):
        """Unregister all handlers"""
        for sub_id in self._subscription_ids:
            self.bus.unsubscribe(sub_id)
        self._handlers.clear()
        self._subscription_ids.clear()

# Decorator for easy handler registration
def event_handler(topic_pattern: str, priority: int = 0, filter_fn=None):
    """Decorator to register event handler"""
    def decorator(func):
        func._event_handler_config = HandlerConfig(
            topic_pattern=topic_pattern,
            priority=priority,
            filter_fn=filter_fn,
        )
        return func
    return decorator

# Example handlers

class TaskEventHandlers:
    """Handlers for task lifecycle events"""
    
    def __init__(self, policy_engine, model_router, memory_system):
        self.policy_engine = policy_engine
        self.model_router = model_router
        self.memory_system = memory_system
    
    @event_handler("tasks.created", priority=100)
    async def on_task_created(self, event: Event):
        """Initialize task tracking"""
        task_id = event.payload.get("task_id")
        logger.info(f"Task created: {task_id}")
        
        # Check if task requires policy approval
        capability = event.payload.get("required_capability")
        if capability:
            await self.policy_engine.request_approval(
                task_id=task_id,
                capability=capability,
                context=event.payload,
            )
    
    @event_handler("tasks.queued", priority=50)
    async def on_task_queued(self, event: Event):
        """Task queued for execution"""
        task_id = event.payload.get("task_id")
        logger.debug(f"Task queued: {task_id}")
    
    @event_handler("tasks.started", priority=50)
    async def on_task_started(self, event: Event):
        """Task execution started"""
        task_id = event.payload.get("task_id")
        logger.info(f"Task started: {task_id}")
    
    @event_handler("tasks.completed", priority=50)
    async def on_task_completed(self, event: Event):
        """Task completed successfully"""
        task_id = event.payload.get("task_id")
        result = event.payload.get("result")
        logger.info(f"Task completed: {task_id}")
        
        # Store result in memory if significant
        if result and isinstance(result, dict) and result.get("store_in_memory"):
            await self.memory_system.store(
                kind="episodic",
                content=f"Task {task_id} completed: {result.get('summary', '')}",
                confidence=0.9,
                metadata={"task_id": task_id, "result": result},
            )
    
    @event_handler("tasks.failed", priority=100)
    async def on_task_failed(self, event: Event):
        """Task failed - trigger recovery"""
        task_id = event.payload.get("task_id")
        error = event.payload.get("error")
        logger.error(f"Task failed: {task_id} - {error}")
        
        # Store failure for learning
        await self.memory_system.store(
            kind="episodic",
            content=f"Task {task_id} failed: {error}",
            confidence=0.8,
            metadata={"task_id": task_id, "error": error},
            tags=["failure", "learning"],
        )
        
        # Trigger retry if applicable
        retry_count = event.payload.get("retry_count", 0)
        max_retries = event.payload.get("max_retries", 3)
        if retry_count < max_retries:
            # Emit retry event
            from core.events.bus import get_event_bus
            bus = get_event_bus()
            await bus.publish(Event(
                event_type="tasks.retry",
                topic="tasks",
                payload={"task_id": task_id, "retry_count": retry_count + 1},
                correlation_id=event.correlation_id,
                causation_id=event.event_id,
                source_component="task_event_handlers",
            ))

class MemoryEventHandlers:
    """Handlers for memory events"""
    
    def __init__(self, memory_system):
        self.memory_system = memory_system
    
    @event_handler("memory.stored", priority=50)
    async def on_memory_stored(self, event: Event):
        """Trigger consolidation check"""
        kind = event.payload.get("kind")
        if kind in ("semantic", "episodic"):
            # Check if consolidation needed
            count = await self.memory_system.count_kind(kind)
            if count % 100 == 0:  # Every 100 memories
                await self.memory_system.trigger_consolidation(kind)
    
    @event_handler("memory.pii_detected", priority=200)
    async def on_pii_detected(self, event: Event):
        """Handle PII detection"""
        pii_types = event.payload.get("pii_types", [])
        memory_id = event.payload.get("memory_id")
        logger.warning(f"PII detected in memory {memory_id}: {pii_types}")
        
        # Alert security
        from core.events.bus import get_event_bus
        bus = get_event_bus()
        await bus.publish(Event(
            event_type="security.pii_detected",
            topic="security",
            payload={
                "memory_id": memory_id,
                "pii_types": pii_types,
                "action": event.payload.get("action", "flagged"),
            },
            source_component="memory_handlers",
            priority=EventPriority.HIGH,
        ))

# Auto-registration
def auto_register_handlers(registry: EventHandlerRegistry, obj):
    """Auto-register all @event_handler methods on object"""
    for attr_name in dir(obj):
        attr = getattr(obj, attr_name)
        if callable(attr) and hasattr(attr, '_event_handler_config'):
            config = attr._event_handler_config
            registry.register(config, attr)
```

---

## 6. Observability

### 6.1 Event Metrics

```python
# core/events/metrics.py
from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry
from core.events.models import Event
import time

registry = CollectorRegistry()

events_published = Counter(
    "arise_events_published_total",
    "Total events published",
    ["topic", "event_type"],
    registry=registry
)

events_delivered = Counter(
    "arise_events_delivered_total",
    "Total events delivered to handlers",
    ["topic", "event_type", "status"],
    registry=registry
)

event_processing_duration = Histogram(
    "arise_event_processing_seconds",
    "Event processing duration",
    ["topic", "event_type"],
    registry=registry
)

event_queue_size = Gauge(
    "arise_event_queue_size",
    "Current event queue size",
    registry=registry
)

active_subscriptions = Gauge(
    "arise_active_subscriptions",
    "Active event subscriptions",
    ["topic_pattern"],
    registry=registry
)

dead_letter_count = Counter(
    "arise_dead_letter_total",
    "Events moved to dead letter queue",
    ["topic", "event_type"],
    registry=registry
)

class EventMetrics:
    """Collect event bus metrics"""
    
    @staticmethod
    def record_publish(event: Event):
        events_published.labels(
            topic=event.topic,
            event_type=event.event_type,
        ).inc()
    
    @staticmethod
    def record_delivery(event: Event, status: str, duration: float):
        events_delivered.labels(
            topic=event.topic,
            event_type=event.event_type,
            status=status,
        ).inc()
        event_processing_duration.labels(
            topic=event.topic,
            event_type=event.event_type,
        ).observe(duration)
    
    @staticmethod
    def record_queue_size(size: int):
        event_queue_size.set(size)
    
    @staticmethod
    def record_subscription(topic_pattern: str, count: int):
        active_subscriptions.labels(topic_pattern=topic_pattern).set(count)
    
    @staticmethod
    def record_dead_letter(event: Event):
        dead_letter_count.labels(
            topic=event.topic,
            event_type=event.event_type,
        ).inc()
```

### 6.2 Event Tracing

```python
# core/events/tracing.py
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
import asyncio
import uuid

from core.events.models import Event

@dataclass
class TraceSpan:
    """Single span in event trace"""
    span_id: str
    trace_id: str
    parent_span_id: Optional[str]
    event_type: str
    topic: str
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_ms: Optional[float] = None
    status: str = "started"  # started, completed, failed
    error: Optional[str] = None
    metadata: Dict = field(default_factory=dict)

@dataclass
class EventTrace:
    """Complete trace for a correlation ID"""
    trace_id: str
    spans: List[TraceSpan] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    
    def add_span(self, span: TraceSpan):
        self.spans.append(span)
    
    def get_root_spans(self) -> List[TraceSpan]:
        return [s for s in self.spans if s.parent_span_id is None]
    
    def get_children(self, parent_span_id: str) -> List[TraceSpan]:
        return [s for s in self.spans if s.parent_span_id == parent_span_id]
    
    def to_dict(self) -> Dict:
        return {
            "trace_id": self.trace_id,
            "spans": [
                {
                    "span_id": s.span_id,
                    "parent_span_id": s.parent_span_id,
                    "event_type": s.event_type,
                    "topic": s.topic,
                    "start_time": s.start_time.isoformat(),
                    "end_time": s.end_time.isoformat() if s.end_time else None,
                    "duration_ms": s.duration_ms,
                    "status": s.status,
                    "error": s.error,
                    "metadata": s.metadata,
                }
                for s in self.spans
            ],
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }

class EventTracer:
    """Distributed tracing for event flows"""
    
    def __init__(self):
        self._traces: Dict[str, EventTrace] = {}
        self._active_spans: Dict[str, TraceSpan] = {}
        self._max_traces = 10000
    
    def start_span(
        self,
        trace_id: str,
        event: Event,
        parent_span_id: str = None,
    ) -> TraceSpan:
        """Start a new trace span"""
        span = TraceSpan(
            span_id=f"span_{uuid.uuid4().hex[:12]}",
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            event_type=event.event_type,
            topic=event.topic,
            start_time=datetime.utcnow(),
            metadata={
                "event_id": event.event_id,
                "source_component": event.source_component,
            },
        )
        
        # Get or create trace
        if trace_id not in self._traces:
            self._traces[trace_id] = EventTrace(trace_id=trace_id)
        
        self._traces[trace_id].add_span(span)
        self._active_spans[span.span_id] = span
        
        # Limit traces
        if len(self._traces) > self._max_traces:
            oldest = min(self._traces.keys(), key=lambda k: self._traces[k].created_at)
            del self._traces[oldest]
        
        return span
    
    def end_span(self, span_id: str, status: str = "completed", error: str = None):
        """End a trace span"""
        if span_id not in self._active_spans:
            return
        
        span = self._active_spans.pop(span_id)
        span.end_time = datetime.utcnow()
        span.duration_ms = (span.end_time - span.start_time).total_seconds() * 1000
        span.status = status
        span.error = error
        
        # Check if trace complete
        trace = self._traces.get(span.trace_id)
        if trace and all(s.end_time for s in trace.spans):
            trace.completed_at = datetime.utcnow()
    
    def get_trace(self, trace_id: str) -> Optional[EventTrace]:
        return self._traces.get(trace_id)
    
    def get_traces_by_time(self, from_time: datetime, to_time: datetime) -> List[EventTrace]:
        return [
            t for t in self._traces.values()
            if from_time <= t.created_at <= to_time
        ]

# Global tracer
_tracer: Optional[EventTracer] = None

def get_tracer() -> EventTracer:
    global _tracer
    if _tracer is None:
        _tracer = EventTracer()
    return _tracer
```

---

## 7. Configuration

```python
# core/events/config.py
from pydantic_settings import BaseSettings
from typing import Optional, List
from enum import Enum

class EventBusMode(str, Enum):
    LOCAL = "local"
    DISTRIBUTED = "distributed"
    HYBRID = "hybrid"

class EventsConfig(BaseSettings):
    """Event bus configuration"""
    
    # Mode
    mode: EventBusMode = EventBusMode.LOCAL
    
    # Local bus
    local_queue_size: int = 10000
    local_worker_count: int = 4
    local_dlq_max_size: int = 1000
    
    # Distributed bus (Redis)
    redis_url: str = "redis://localhost:6379"
    redis_consumer_group: str = "arise"
    redis_stream_max_len: int = 10000
    redis_read_block_ms: int = 5000
    
    # Event store
    event_store_path: str = "data/events.db"
    event_store_wal: bool = True
    event_retention_days: int = 30
    event_compaction_interval_hours: int = 24
    
    # Projections
    projection_checkpoint_interval: int = 100
    projection_snapshot_interval: int = 1000
    
    # Tracing
    tracing_enabled: bool = True
    tracing_sample_rate: float = 1.0
    tracing_max_traces: int = 10000
    
    # Metrics
    metrics_enabled: bool = True
    metrics_port: int = 9090
    
    # Bridging
    bridged_topics: List[str] = [
        "tasks",
        "policy",
        "memory",
        "agents",
        "security",
        "system",
    ]
    
    class Config:
        env_prefix = "ARISE_EVENTS_"
        env_file = ".env"

# Default config instance
events_config = EventsConfig()
```

---

## 8. Testing

```python
# tests/events/test_event_bus.py
import pytest
import asyncio
from core.events.bus import LocalEventBus
from core.events.models import Event, EventPriority

@pytest.fixture
async def event_bus():
    bus = LocalEventBus()
    await bus.start()
    yield bus
    await bus.stop()

class TestEventBus:
    async def test_publish_subscribe(self, event_bus):
        received = []
        
        async def handler(event: Event):
            received.append(event)
        
        sub_id = event_bus.subscribe("test.topic", handler)
        
        event = Event(
            event_type="test.event",
            topic="test.topic",
            payload={"message": "hello"},
        )
        
        await event_bus.publish(event)
        await asyncio.sleep(0.1)
        
        assert len(received) == 1
        assert received[0].payload["message"] == "hello"
        
        event_bus.unsubscribe(sub_id)
    
    async def test_wildcard_subscription(self, event_bus):
        received = []
        
        async def handler(event: Event):
            received.append(event.topic)
        
        event_bus.subscribe("test.*", handler)
        
        await event_bus.publish(Event(event_type="a", topic="test.a", payload={}))
        await event_bus.publish(Event(event_type="b", topic="test.b", payload={}))
        await event_bus.publish(Event(event_type="c", topic="other.c", payload={}))
        await asyncio.sleep(0.1)
        
        assert "test.a" in received
        assert "test.b" in received
        assert "other.c" not in received
    
    async def test_priority_ordering(self, event_bus):
        order = []
        
        async def low_handler(event: Event):
            order.append("low")
        
        async def high_handler(event: Event):
            order.append("high")
        
        event_bus.subscribe("priority.test", low_handler, priority=0)
        event_bus.subscribe("priority.test", high_handler, priority=100)
        
        await event_bus.publish(Event(
            event_type="test", topic="priority.test", payload={},
            priority=EventPriority.NORMAL
        ))
        await asyncio.sleep(0.1)
        
        # High priority should execute first
        assert order == ["high", "low"]
    
    async def test_retry_on_failure(self, event_bus):
        attempt = 0
        
        async def failing_handler(event: Event):
            nonlocal attempt
            attempt += 1
            if attempt < 3:
                raise ValueError("Temporary failure")
        
        event_bus.subscribe("retry.test", failing_handler)
        
        event = Event(
            event_type="test", topic="retry.test", payload={},
            max_retries=3,
        )
        
        await event_bus.publish(event)
        await asyncio.sleep(1)  # Wait for retries
        
        assert attempt == 3
    
    async def test_dead_letter_on_max_retries(self, event_bus):
        async def always_fails(event: Event):
            raise ValueError("Permanent failure")
        
        event_bus.subscribe("dlq.test", always_fails)
        
        event = Event(
            event_type="test", topic="dlq.test", payload={},
            max_retries=2,
        )
        
        await event_bus.publish(event)
        await asyncio.sleep(1)
        
        stats = event_bus.get_stats()
        assert stats["dead_letter_queue_size"] == 1
```

---

## 9. Usage Examples

### 9.1 Publishing Events

```python
# In any component
from core.events.bus import get_event_bus
from core.events.models import Event, EventPriority

async def submit_task(task_id: str, payload: dict):
    bus = get_event_bus()
    
    event = Event(
        event_type="task.created",
        topic="tasks",
        payload={
            "task_id": task_id,
            "payload": payload,
            "required_capability": "shell.exec",
        },
        correlation_id=f"task_{task_id}",
        source_component="task_api",
        priority=EventPriority.HIGH,
    )
    
    await bus.publish(event)
```

### 9.2 Subscribing to Events

```python
# In a component that needs to react
from core.events.bus import get_event_bus
from core.events.handlers import EventHandlerRegistry, event_handler

class MyComponent:
    def __init__(self):
        self.bus = get_event_bus()
        self.registry = EventHandlerRegistry(self.bus)
        self._register_handlers()
    
    def _register_handlers(self):
        # Auto-register decorated methods
        from core.events.handlers import auto_register_handlers
        auto_register_handlers(self.registry, self)
    
    @event_handler("tasks.completed", priority=50)
    async def on_task_completed(self, event: Event):
        task_id = event.payload.get("task_id")
        result = event.payload.get("result")
        print(f"Task {task_id} completed with: {result}")
    
    @event_handler("memory.pii_detected", priority=200)
    async def on_pii(self, event: Event):
        print(f"PII alert: {event.payload}")
    
    async def shutdown(self):
        await self.registry.unregister_all()
```

---

*This event bus architecture provides reliable, observable, and scalable messaging for all ARISE components with support for both local and distributed deployments.*