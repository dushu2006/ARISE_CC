# core/events/projections.py
"""
Event Projections - Materialized views built from event streams.

Provides:
- Base Projection class with checkpointing
- TaskStatusProjection for tracking task state
- AgentHealthProjection for agent monitoring
- Automatic snapshot persistence
"""

from __future__ import annotations
import hashlib
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from core.events.models import Event, EventTypes
from core.events.store import EventStore, get_event_store

logger = logging.getLogger(__name__)


@dataclass
class ProjectionCheckpoint:
    """Checkpoint for projection state."""
    projection_name: str
    last_event_id: str
    last_event_timestamp: datetime
    state_hash: str
    event_count: int


class Projection(ABC):
    """
    Base class for event projections.

    Projections build materialized views from event streams.
    They support:
    - Incremental processing from last checkpoint
    - Automatic snapshot persistence
    - State hash for change detection
    - Replay capability
    """

    def __init__(
        self,
        name: str,
        event_store: Optional[EventStore] = None,
        snapshot_interval: int = 100,
    ):
        self.name = name
        self.event_store = event_store or get_event_store()
        self.snapshot_interval = snapshot_interval
        self._state: dict[str, Any] = {}
        self._event_count = 0
        self._last_event_id: Optional[str] = None
        self._last_event_timestamp: Optional[datetime] = None
        self._initialized = False

    @abstractmethod
    def handle_event(self, event: Event) -> None:
        """Process a single event and update projection state."""
        pass

    @abstractmethod
    def get_state(self) -> dict[str, Any]:
        """Get current projection state."""
        pass

    def _compute_state_hash(self) -> str:
        """Compute hash of current state for change detection."""
        state_json = json.dumps(self._state, sort_keys=True, default=str)
        return hashlib.sha256(state_json.encode()).hexdigest()[:16]

    async def initialize(self) -> None:
        """Load latest snapshot if available."""
        if self._initialized:
            return

        snapshot = self.event_store.load_snapshot(self.name)
        if snapshot:
            self._state = snapshot["state"]
            self._event_count = snapshot["event_count"]
            self._last_event_id = snapshot["checkpoint_id"]
            logger.info(f"Projection {self.name} loaded snapshot: {self._event_count} events")
        else:
            logger.info(f"Projection {self.name} starting fresh")

        self._initialized = True

    async def process_events(self, events: list[Event]) -> int:
        """Process a batch of events."""
        if not self._initialized:
            await self.initialize()

        processed = 0
        for event in events:
            try:
                self.handle_event(event)
                processed += 1
                self._event_count += 1
                self._last_event_id = event.id
                self._last_event_timestamp = event.timestamp
            except Exception as e:
                logger.error(f"Projection {self.name} failed to process event {event.id}: {e}")
                raise

        # Save snapshot periodically
        if self._event_count % self.snapshot_interval == 0:
            await self.save_snapshot()

        return processed

    async def save_snapshot(self) -> None:
        """Persist current state as snapshot."""
        if not self._last_event_id or not self._last_event_timestamp:
            return

        state_hash = self._compute_state_hash()

        self.event_store.save_snapshot(
            projection_name=self.name,
            checkpoint_id=self._last_event_id,
            state=self._state,
            event_count=self._event_count,
        )

        self.event_store.update_projection_state(
            projection_name=self.name,
            last_event_id=self._last_event_id,
            last_event_timestamp=self._last_event_timestamp,
            state_hash=state_hash,
        )

        logger.debug(f"Projection {self.name} saved snapshot at event {self._last_event_id}")

    async def rebuild(self, batch_size: int = 1000) -> int:
        """
        Rebuild projection from scratch by replaying all events.

        Returns:
            Total events processed
        """
        logger.info(f"Rebuilding projection {self.name} from scratch")

        # Reset state
        self._state = {}
        self._event_count = 0
        self._last_event_id = None
        self._last_event_timestamp = None

        # Delete existing snapshot
        self.event_store.delete_snapshot(self.name)

        # Process all events
        total_processed = 0
        offset = 0

        while True:
            events = self.event_store.get_events(
                limit=batch_size,
                offset=offset,
                order_by="timestamp",
                order_dir="ASC",
            )

            if not events:
                break

            await self.process_events(events)
            total_processed += len(events)
            offset += batch_size

            logger.info(f"Projection {self.name} rebuilt {total_processed} events...")

        # Save final snapshot
        await self.save_snapshot()

        logger.info(f"Projection {self.name} rebuild complete: {total_processed} events")
        return total_processed

    def get_checkpoint(self) -> Optional[ProjectionCheckpoint]:
        """Get current checkpoint info."""
        if not self._last_event_id:
            return None

        return ProjectionCheckpoint(
            projection_name=self.name,
            last_event_id=self._last_event_id,
            last_event_timestamp=self._last_event_timestamp,
            state_hash=self._compute_state_hash(),
            event_count=self._event_count,
        )


class TaskStatusProjection(Projection):
    """
    Projection for tracking task status from task events.

    Maintains:
    - Task status by task_id
    - Task progress and current step
    - Task timing (started, completed, duration)
    - Task counts by status
    - Recent task history
    """

    def __init__(
        self,
        event_store: Optional[EventStore] = None,
        max_history: int = 1000,
    ):
        super().__init__("task_status", event_store, snapshot_interval=50)
        self.max_history = max_history

        # State structure
        self._state = {
            "tasks": {},  # task_id -> task info
            "counts_by_status": {},  # status -> count
            "recent_tasks": [],  # List of recent task IDs (newest first)
            "active_tasks": set(),  # Set of currently running task IDs
        }

    def handle_event(self, event: Event) -> None:
        """Process task-related events."""
        task_id = event.task_id
        if not task_id:
            return

        task_info = self._state["tasks"].get(task_id, {
            "task_id": task_id,
            "status": "unknown",
            "created_at": None,
            "started_at": None,
            "completed_at": None,
            "current_step": None,
            "progress": 0.0,
            "error": None,
            "correlation_id": event.correlation_id,
        })

        # Update based on event type
        if event.type == EventTypes.TASK_CREATED:
            task_info["status"] = "created"
            task_info["created_at"] = event.timestamp.isoformat()
            task_info["payload"] = event.payload

        elif event.type == EventTypes.TASK_QUEUED:
            task_info["status"] = "queued"

        elif event.type == EventTypes.TASK_STARTED:
            task_info["status"] = "running"
            task_info["started_at"] = event.timestamp.isoformat()
            self._state["active_tasks"].add(task_id)

        elif event.type == EventTypes.TASK_PROGRESS:
            task_info["progress"] = event.payload.get("progress", task_info["progress"])
            task_info["current_step"] = event.payload.get("step", task_info["current_step"])

        elif event.type == EventTypes.TASK_STEP_STARTED:
            task_info["current_step"] = event.payload.get("step")
            task_info["progress"] = event.payload.get("progress", 0)

        elif event.type == EventTypes.TASK_STEP_COMPLETED:
            task_info["progress"] = event.payload.get("progress", task_info["progress"])

        elif event.type == EventTypes.TASK_COMPLETED:
            task_info["status"] = "completed"
            task_info["completed_at"] = event.timestamp.isoformat()
            task_info["progress"] = 1.0
            task_info["result"] = event.payload.get("result")
            self._state["active_tasks"].discard(task_id)

        elif event.type == EventTypes.TASK_FAILED:
            task_info["status"] = "failed"
            task_info["completed_at"] = event.timestamp.isoformat()
            task_info["error"] = event.payload.get("error")
            self._state["active_tasks"].discard(task_id)

        elif event.type == EventTypes.TASK_CANCELLED:
            task_info["status"] = "cancelled"
            task_info["completed_at"] = event.timestamp.isoformat()
            self._state["active_tasks"].discard(task_id)

        elif event.type == EventTypes.TASK_CHECKPOINT:
            task_info["checkpoint"] = event.payload

        elif event.type == EventTypes.TASK_RETRY:
            task_info["status"] = "retrying"
            task_info["retry_count"] = event.payload.get("retry_count", 0)

        # Update task info
        self._state["tasks"][task_id] = task_info

        # Update counts
        status = task_info["status"]
        self._state["counts_by_status"][status] = self._state["counts_by_status"].get(status, 0) + 1

        # Update recent tasks (keep newest first)
        if task_id in self._state["recent_tasks"]:
            self._state["recent_tasks"].remove(task_id)
        self._state["recent_tasks"].insert(0, task_id)

        # Trim history
        if len(self._state["recent_tasks"]) > self.max_history:
            removed = self._state["recent_tasks"].pop()
            # Clean up old task data if no longer in recent
            if removed not in self._state["recent_tasks"] and removed not in self._state["active_tasks"]:
                self._state["tasks"].pop(removed, None)

    def get_state(self) -> dict[str, Any]:
        """Get current projection state."""
        return {
            "tasks": self._state["tasks"],
            "counts_by_status": self._state["counts_by_status"],
            "recent_tasks": self._state["recent_tasks"][:100],  # Limit returned history
            "active_tasks": list(self._state["active_tasks"]),
            "total_tasks": len(self._state["tasks"]),
            "last_updated": self._last_event_timestamp.isoformat() if self._last_event_timestamp else None,
        }

    def get_task(self, task_id: str) -> Optional[dict[str, Any]]:
        """Get status for a specific task."""
        return self._state["tasks"].get(task_id)

    def get_tasks_by_status(self, status: str) -> list[dict[str, Any]]:
        """Get all tasks with a specific status."""
        return [
            task for task in self._state["tasks"].values()
            if task["status"] == status
        ]

    def get_active_tasks(self) -> list[dict[str, Any]]:
        """Get all currently running tasks."""
        return [
            self._state["tasks"][tid] for tid in self._state["active_tasks"]
            if tid in self._state["tasks"]
        ]


class AgentHealthProjection(Projection):
    """
    Projection for tracking agent health from agent events.

    Maintains:
    - Agent health status by role
    - Last heartbeat timestamp
    - Capabilities and current load
    - Health history for trend analysis
    """

    def __init__(
        self,
        event_store: Optional[EventStore] = None,
        stale_threshold_seconds: int = 60,
    ):
        super().__init__("agent_health", event_store, snapshot_interval=20)
        self.stale_threshold_seconds = stale_threshold_seconds

        self._state = {
            "agents": {},  # agent_id -> agent info
            "by_role": {},  # role -> list of agent_ids
        }

    def handle_event(self, event: Event) -> None:
        """Process agent-related events."""
        agent_id = event.agent_id
        if not agent_id:
            return

        agent_info = self._state["agents"].get(agent_id, {
            "agent_id": agent_id,
            "role": event.payload.get("role", "unknown"),
            "status": "unknown",
            "last_heartbeat": None,
            "capabilities": [],
            "current_load": 0,
            "max_load": 10,
            "health_score": 1.0,
            "metadata": {},
        })

        if event.type == EventTypes.AGENT_REGISTERED:
            agent_info["status"] = "healthy"
            agent_info["capabilities"] = event.payload.get("capabilities", [])
            agent_info["max_load"] = event.payload.get("max_load", 10)
            agent_info["metadata"] = event.payload.get("metadata", {})

            # Register by role
            role = agent_info["role"]
            if role not in self._state["by_role"]:
                self._state["by_role"][role] = []
            if agent_id not in self._state["by_role"][role]:
                self._state["by_role"][role].append(agent_id)

        elif event.type == EventTypes.AGENT_HEARTBEAT:
            agent_info["last_heartbeat"] = event.timestamp.isoformat()
            agent_info["current_load"] = event.payload.get("current_load", agent_info["current_load"])
            agent_info["health_score"] = event.payload.get("health_score", 1.0)
            agent_info["status"] = "healthy" if agent_info["health_score"] > 0.5 else "degraded"

        elif event.type == EventTypes.AGENT_HEALTH_CHANGED:
            agent_info["status"] = event.payload.get("status", agent_info["status"])
            agent_info["health_score"] = event.payload.get("health_score", agent_info["health_score"])
            if "capabilities" in event.payload:
                agent_info["capabilities"] = event.payload["capabilities"]

        elif event.type == EventTypes.AGENT_DELEGATION_STARTED:
            agent_info["current_load"] = agent_info.get("current_load", 0) + 1

        elif event.type == EventTypes.AGENT_DELEGATION_COMPLETED:
            agent_info["current_load"] = max(0, agent_info.get("current_load", 1) - 1)

        elif event.type == EventTypes.AGENT_DELEGATION_FAILED:
            agent_info["current_load"] = max(0, agent_info.get("current_load", 1) - 1)
            agent_info["health_score"] = max(0, agent_info.get("health_score", 1.0) - 0.1)

        elif event.type == EventTypes.AGENT_SHUTDOWN:
            agent_info["status"] = "shutdown"
            agent_info["current_load"] = 0

        self._state["agents"][agent_id] = agent_info

    def get_state(self) -> dict[str, Any]:
        """Get current projection state."""
        # Compute derived statuses
        now = datetime.now(timezone.utc)
        stale_agents = []
        healthy_agents = []

        for agent_id, info in self._state["agents"].items():
            if info["last_heartbeat"]:
                last_hb = datetime.fromisoformat(info["last_heartbeat"])
                if (now - last_hb).total_seconds() > self.stale_threshold_seconds:
                    info["status"] = "stale"
                    stale_agents.append(agent_id)
                elif info["status"] == "healthy":
                    healthy_agents.append(agent_id)

        return {
            "agents": self._state["agents"],
            "by_role": self._state["by_role"],
            "summary": {
                "total": len(self._state["agents"]),
                "healthy": len(healthy_agents),
                "stale": len(stale_agents),
                "shutdown": sum(1 for a in self._state["agents"].values() if a["status"] == "shutdown"),
            },
            "last_updated": self._last_event_timestamp.isoformat() if self._last_event_timestamp else None,
        }

    def get_agent(self, agent_id: str) -> Optional[dict[str, Any]]:
        """Get health info for a specific agent."""
        return self._state["agents"].get(agent_id)

    def get_agents_by_role(self, role: str) -> list[dict[str, Any]]:
        """Get all agents for a specific role."""
        agent_ids = self._state["by_role"].get(role, [])
        return [self._state["agents"][aid] for aid in agent_ids if aid in self._state["agents"]]

    def get_healthy_agents(self, role: Optional[str] = None) -> list[dict[str, Any]]:
        """Get agents with healthy status, optionally filtered by role."""
        agents = []
        for agent_id, info in self._state["agents"].items():
            if info["status"] == "healthy":
                if role is None or info["role"] == role:
                    agents.append(info)
        return agents


class ModelUsageProjection(Projection):
    """
    Projection for tracking model usage and costs.

    Maintains:
    - Request counts by provider/model
    - Token usage and costs
    - Error rates
    - Latency percentiles
    """

    def __init__(self, event_store: Optional[EventStore] = None):
        super().__init__("model_usage", event_store, snapshot_interval=100)

        self._state = {
            "by_provider": {},  # provider -> stats
            "by_model": {},  # model -> stats
            "total_requests": 0,
            "total_tokens": 0,
            "total_cost": 0.0,
            "errors": 0,
        }

    def handle_event(self, event: Event) -> None:
        """Process model-related events."""
        if event.type not in (EventTypes.MODEL_REQUEST, EventTypes.MODEL_RESPONSE, EventTypes.MODEL_ERROR):
            return

        provider = event.payload.get("provider", "unknown")
        model = event.payload.get("model", "unknown")
        key = f"{provider}:{model}"

        # Initialize provider stats
        if provider not in self._state["by_provider"]:
            self._state["by_provider"][provider] = {
                "requests": 0,
                "tokens": 0,
                "cost": 0.0,
                "errors": 0,
                "latencies": [],
            }

        # Initialize model stats
        if key not in self._state["by_model"]:
            self._state["by_model"][key] = {
                "provider": provider,
                "model": model,
                "requests": 0,
                "tokens": 0,
                "cost": 0.0,
                "errors": 0,
                "latencies": [],
            }

        provider_stats = self._state["by_provider"][provider]
        model_stats = self._state["by_model"][key]

        if event.type == EventTypes.MODEL_REQUEST:
            provider_stats["requests"] += 1
            model_stats["requests"] += 1
            self._state["total_requests"] += 1

        elif event.type == EventTypes.MODEL_RESPONSE:
            tokens = event.payload.get("tokens", 0)
            cost = event.payload.get("cost", 0.0)
            latency = event.payload.get("latency_ms", 0)

            provider_stats["tokens"] += tokens
            provider_stats["cost"] += cost
            if latency:
                provider_stats["latencies"].append(latency)
                # Keep only last 1000 latencies
                if len(provider_stats["latencies"]) > 1000:
                    provider_stats["latencies"] = provider_stats["latencies"][-1000:]

            model_stats["tokens"] += tokens
            model_stats["cost"] += cost
            if latency:
                model_stats["latencies"].append(latency)
                if len(model_stats["latencies"]) > 1000:
                    model_stats["latencies"] = model_stats["latencies"][-1000:]

            self._state["total_tokens"] += tokens
            self._state["total_cost"] += cost

        elif event.type == EventTypes.MODEL_ERROR:
            provider_stats["errors"] += 1
            model_stats["errors"] += 1
            self._state["errors"] += 1

    def _compute_percentiles(self, latencies: list[float]) -> dict[str, float]:
        """Compute latency percentiles."""
        if not latencies:
            return {"p50": 0, "p95": 0, "p99": 0}

        sorted_latencies = sorted(latencies)
        n = len(sorted_latencies)

        return {
            "p50": sorted_latencies[n // 2],
            "p95": sorted_latencies[int(n * 0.95)],
            "p99": sorted_latencies[int(n * 0.99)],
        }

    def get_state(self) -> dict[str, Any]:
        """Get current projection state with computed metrics."""
        result = {
            "by_provider": {},
            "by_model": {},
            "totals": {
                "requests": self._state["total_requests"],
                "tokens": self._state["total_tokens"],
                "cost": self._state["total_cost"],
                "errors": self._state["errors"],
                "error_rate": self._state["errors"] / max(1, self._state["total_requests"]),
            },
        }

        # Add computed percentiles
        for provider, stats in self._state["by_provider"].items():
            result["by_provider"][provider] = {
                "requests": stats["requests"],
                "tokens": stats["tokens"],
                "cost": stats["cost"],
                "errors": stats["errors"],
                "error_rate": stats["errors"] / max(1, stats["requests"]),
                "latency": self._compute_percentiles(stats["latencies"]),
            }

        for key, stats in self._state["by_model"].items():
            result["by_model"][key] = {
                "provider": stats["provider"],
                "model": stats["model"],
                "requests": stats["requests"],
                "tokens": stats["tokens"],
                "cost": stats["cost"],
                "errors": stats["errors"],
                "error_rate": stats["errors"] / max(1, stats["requests"]),
                "latency": self._compute_percentiles(stats["latencies"]),
            }

        return result


# Projection registry for easy access
class ProjectionRegistry:
    """Registry for managing multiple projections."""

    def __init__(self, event_store: Optional[EventStore] = None):
        self.event_store = event_store or get_event_store()
        self._projections: dict[str, Projection] = {}

    def register(self, projection: Projection) -> None:
        """Register a projection."""
        self._projections[projection.name] = projection

    def get(self, name: str) -> Optional[Projection]:
        """Get a projection by name."""
        return self._projections.get(name)

    async def initialize_all(self) -> None:
        """Initialize all registered projections."""
        for projection in self._projections.values():
            await projection.initialize()

    async def process_event(self, event: Event) -> None:
        """Process event through all projections."""
        for projection in self._projections.values():
            try:
                projection.handle_event(event)
                projection._event_count += 1
                projection._last_event_id = event.id
                projection._last_event_timestamp = event.timestamp

                # Save snapshot periodically
                if projection._event_count % projection.snapshot_interval == 0:
                    await projection.save_snapshot()
            except Exception as e:
                logger.error(f"Projection {projection.name} error processing event: {e}")

    async def save_all_snapshots(self) -> None:
        """Save snapshots for all projections."""
        for projection in self._projections.values():
            await projection.save_snapshot()


# Global projection registry
_projection_registry: Optional[ProjectionRegistry] = None


def get_projection_registry(event_store: Optional[EventStore] = None) -> ProjectionRegistry:
    """Get global projection registry."""
    global _projection_registry
    if _projection_registry is None:
        _projection_registry = ProjectionRegistry(event_store)
        # Register default projections
        _projection_registry.register(TaskStatusProjection(_projection_registry.event_store))
        _projection_registry.register(AgentHealthProjection(_projection_registry.event_store))
        _projection_registry.register(ModelUsageProjection(_projection_registry.event_store))
    return _projection_registry


async def init_projections(event_store: Optional[EventStore] = None) -> ProjectionRegistry:
    """Initialize all projections."""
    registry = get_projection_registry(event_store)
    await registry.initialize_all()
    return registry