# core/events/store.py
"""
EventStore - Persistent event storage using SQLite with WAL mode.

Provides:
- Append-only event storage with batch support
- Query by correlation ID, time range, event type
- Snapshots table for projection checkpointing
- Dead letter queue table for failed events
- WAL mode for concurrent read/write performance
"""

from __future__ import annotations
import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from core.events.models import Event, EventPriority

# SQLite pragmas for performance
PRAGMAS = [
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL",
    "PRAGMA cache_size=-32768",  # 32MB cache
    "PRAGMA temp_store=MEMORY",
    "PRAGMA mmap_size=268435456",  # 256MB mmap
    "PRAGMA page_size=4096",
    "PRAGMA busy_timeout=5000",
]


@dataclass
class EventStoreConfig:
    """Configuration for EventStore."""
    db_path: str = "./data/events.db"
    wal_mode: bool = True
    max_batch_size: int = 1000
    snapshot_interval: int = 100  # Events between snapshots


class EventStore:
    """
    SQLite-based event store with WAL mode.

    Features:
    - Append-only event log
    - Batch append for performance
    - Queries by correlation_id, event type, time range
    - Snapshots for projection checkpointing
    - Dead letter queue for failed events
    - Automatic schema migration
    """

    def __init__(self, config: Optional[EventStoreConfig] = None):
        self.config = config or EventStoreConfig()
        self._db_path = Path(self.config.db_path)
        self._conn: Optional[sqlite3.Connection] = None
        self._initialized = False

    def _get_connection(self) -> sqlite3.Connection:
        """Get or create database connection."""
        if self._conn is None:
            # Ensure directory exists
            self._db_path.parent.mkdir(parents=True, exist_ok=True)

            self._conn = sqlite3.connect(
                str(self._db_path),
                check_same_thread=False,
                isolation_level=None,  # Autocommit mode
            )
            self._conn.row_factory = sqlite3.Row

            # Apply pragmas
            for pragma in PRAGMAS:
                self._conn.execute(pragma)

            # Enable foreign keys
            self._conn.execute("PRAGMA foreign_keys=ON")

        return self._conn

    def initialize(self) -> None:
        """Initialize database schema."""
        if self._initialized:
            return

        conn = self._get_connection()

        # Events table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                payload TEXT NOT NULL,  -- JSON
                priority INTEGER NOT NULL DEFAULT 50,
                correlation_id TEXT NOT NULL,
                causation_id TEXT,
                source TEXT NOT NULL,
                task_id TEXT,
                agent_id TEXT,
                session_id TEXT,
                timestamp TEXT NOT NULL,  -- ISO format
                expires_at TEXT,
                metadata TEXT NOT NULL,  -- JSON
                retry_count INTEGER NOT NULL DEFAULT 0,
                max_retries INTEGER NOT NULL DEFAULT 3,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

        # Indexes for common queries
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_correlation_id ON events(correlation_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON events(type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_task_id ON events(task_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_agent_id ON events(agent_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_source ON events(source)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_correlation_timestamp ON events(correlation_id, timestamp)")

        # Snapshots table for projection checkpointing
        conn.execute("""
            CREATE TABLE IF NOT EXISTS snapshots (
                projection_name TEXT PRIMARY KEY,
                checkpoint_id TEXT NOT NULL,
                state TEXT NOT NULL,  -- JSON
                event_count INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

        # Dead letter queue table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS dead_letter (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                event_data TEXT NOT NULL,  -- Full event JSON
                error TEXT NOT NULL,
                failed_at TEXT NOT NULL DEFAULT (datetime('now')),
                retry_count INTEGER NOT NULL DEFAULT 0,
                last_retry_at TEXT
            )
        """)

        conn.execute("CREATE INDEX IF NOT EXISTS idx_dead_letter_event_type ON dead_letter(event_type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_dead_letter_failed_at ON dead_letter(failed_at)")

        # Projection state table (for event sourcing)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS projection_state (
                projection_name TEXT PRIMARY KEY,
                last_event_id TEXT,
                last_event_timestamp TEXT,
                state_hash TEXT,
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

        conn.commit()
        self._initialized = True

    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> EventStore:
        self.initialize()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    @contextmanager
    def transaction(self):
        """Context manager for database transactions."""
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def _event_to_row(self, event: Event) -> tuple:
        """Convert Event to database row tuple."""
        return (
            event.id,
            event.type,
            json.dumps(event.payload),
            int(event.priority),
            event.correlation_id,
            event.causation_id,
            event.source,
            event.task_id,
            event.agent_id,
            event.session_id,
            event.timestamp.isoformat(),
            event.expires_at.isoformat() if event.expires_at else None,
            json.dumps(event.metadata),
            event.retry_count,
            event.max_retries,
        )

    def _row_to_event(self, row: sqlite3.Row) -> Event:
        """Convert database row to Event."""
        return Event(
            id=row["id"],
            type=row["type"],
            payload=json.loads(row["payload"]),
            priority=EventPriority(row["priority"]),
            correlation_id=row["correlation_id"],
            causation_id=row["causation_id"],
            source=row["source"],
            task_id=row["task_id"],
            agent_id=row["agent_id"],
            session_id=row["session_id"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            expires_at=datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None,
            metadata=json.loads(row["metadata"]),
            retry_count=row["retry_count"],
            max_retries=row["max_retries"],
        )

    def append(self, event: Event) -> str:
        """
        Append a single event to the store.

        Returns:
            Event ID
        """
        self.initialize()

        conn = self._get_connection()
        row = self._event_to_row(event)

        conn.execute("""
            INSERT INTO events (
                id, type, payload, priority, correlation_id, causation_id,
                source, task_id, agent_id, session_id, timestamp, expires_at,
                metadata, retry_count, max_retries
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, row)

        conn.commit()
        return event.id

    def append_batch(self, events: list[Event]) -> list[str]:
        """
        Append multiple events in a single transaction.

        Returns:
            List of event IDs
        """
        if not events:
            return []

        if len(events) > self.config.max_batch_size:
            raise ValueError(f"Batch size {len(events)} exceeds max {self.config.max_batch_size}")

        self.initialize()

        conn = self._get_connection()
        rows = [self._event_to_row(e) for e in events]

        conn.executemany("""
            INSERT INTO events (
                id, type, payload, priority, correlation_id, causation_id,
                source, task_id, agent_id, session_id, timestamp, expires_at,
                metadata, retry_count, max_retries
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, rows)

        conn.commit()
        return [e.id for e in events]

    def get_event(self, event_id: str) -> Optional[Event]:
        """Get a single event by ID."""
        self.initialize()

        conn = self._get_connection()
        row = conn.execute(
            "SELECT * FROM events WHERE id = ?", (event_id,)
        ).fetchone()

        if row:
            return self._row_to_event(row)
        return None

    def get_events(
        self,
        correlation_id: Optional[str] = None,
        event_type: Optional[str] = None,
        source: Optional[str] = None,
        task_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
        order_by: str = "timestamp",
        order_dir: str = "ASC",
    ) -> list[Event]:
        """
        Query events with filters.

        Args:
            correlation_id: Filter by correlation ID
            event_type: Filter by event type (exact match)
            source: Filter by source component
            task_id: Filter by task ID
            agent_id: Filter by agent ID
            start_time: Filter events after this time
            end_time: Filter events before this time
            limit: Max results
            offset: Pagination offset
            order_by: Column to order by (timestamp, correlation_id, type)
            order_dir: ASC or DESC

        Returns:
            List of matching events
        """
        self.initialize()

        conn = self._get_connection()

        conditions = []
        params = []

        if correlation_id:
            conditions.append("correlation_id = ?")
            params.append(correlation_id)

        if event_type:
            conditions.append("type = ?")
            params.append(event_type)

        if source:
            conditions.append("source = ?")
            params.append(source)

        if task_id:
            conditions.append("task_id = ?")
            params.append(task_id)

        if agent_id:
            conditions.append("agent_id = ?")
            params.append(agent_id)

        if start_time:
            conditions.append("timestamp >= ?")
            params.append(start_time.isoformat())

        if end_time:
            conditions.append("timestamp <= ?")
            params.append(end_time.isoformat())

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

        # Validate order_by to prevent injection
        valid_order_columns = {"timestamp", "correlation_id", "type", "priority", "created_at"}
        if order_by not in valid_order_columns:
            order_by = "timestamp"

        order_dir = order_dir.upper()
        if order_dir not in {"ASC", "DESC"}:
            order_dir = "ASC"

        query = f"""
            SELECT * FROM events
            {where_clause}
            ORDER BY {order_by} {order_dir}
            LIMIT ? OFFSET ?
        """

        params.extend([limit, offset])

        rows = conn.execute(query, params).fetchall()
        return [self._row_to_event(row) for row in rows]

    def get_by_correlation(self, correlation_id: str, limit: int = 1000) -> list[Event]:
        """Get all events for a correlation ID (convenience method)."""
        return self.get_events(
            correlation_id=correlation_id,
            limit=limit,
            order_by="timestamp",
            order_dir="ASC",
        )

    def get_recent(self, limit: int = 100, event_type: Optional[str] = None) -> list[Event]:
        """Get most recent events."""
        return self.get_events(
            event_type=event_type,
            limit=limit,
            order_by="timestamp",
            order_dir="DESC",
        )

    def count_events(
        self,
        correlation_id: Optional[str] = None,
        event_type: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> int:
        """Count events matching filters."""
        self.initialize()

        conn = self._get_connection()

        conditions = []
        params = []

        if correlation_id:
            conditions.append("correlation_id = ?")
            params.append(correlation_id)

        if event_type:
            conditions.append("type = ?")
            params.append(event_type)

        if start_time:
            conditions.append("timestamp >= ?")
            params.append(start_time.isoformat())

        if end_time:
            conditions.append("timestamp <= ?")
            params.append(end_time.isoformat())

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

        query = f"SELECT COUNT(*) as count FROM events {where_clause}"
        row = conn.execute(query, params).fetchone()
        return row["count"] if row else 0

    # Snapshot management for projections

    def save_snapshot(self, projection_name: str, checkpoint_id: str, state: dict[str, Any], event_count: int) -> None:
        """Save projection snapshot."""
        self.initialize()

        conn = self._get_connection()
        conn.execute("""
            INSERT OR REPLACE INTO snapshots (projection_name, checkpoint_id, state, event_count, updated_at)
            VALUES (?, ?, ?, ?, datetime('now'))
        """, (projection_name, checkpoint_id, json.dumps(state), event_count))
        conn.commit()

    def load_snapshot(self, projection_name: str) -> Optional[dict[str, Any]]:
        """Load projection snapshot."""
        self.initialize()

        conn = self._get_connection()
        row = conn.execute(
            "SELECT checkpoint_id, state, event_count FROM snapshots WHERE projection_name = ?",
            (projection_name,)
        ).fetchone()

        if row:
            return {
                "checkpoint_id": row["checkpoint_id"],
                "state": json.loads(row["state"]),
                "event_count": row["event_count"],
            }
        return None

    def delete_snapshot(self, projection_name: str) -> bool:
        """Delete projection snapshot."""
        self.initialize()

        conn = self._get_connection()
        cursor = conn.execute(
            "DELETE FROM snapshots WHERE projection_name = ?",
            (projection_name,)
        )
        conn.commit()
        return cursor.rowcount > 0

    # Dead letter queue

    def add_to_dead_letter(self, event: Event, error: str) -> int:
        """Add event to dead letter queue."""
        self.initialize()

        conn = self._get_connection()
        cursor = conn.execute("""
            INSERT INTO dead_letter (event_id, event_type, event_data, error, failed_at, retry_count)
            VALUES (?, ?, ?, ?, datetime('now'), ?)
        """, (
            event.id,
            event.type,
            event.to_json(),
            error,
            event.retry_count,
        ))
        conn.commit()
        return cursor.lastrowid

    def get_dead_letter(
        self,
        event_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Get dead letter entries."""
        self.initialize()

        conn = self._get_connection()

        conditions = []
        params = []

        if event_type:
            conditions.append("event_type = ?")
            params.append(event_type)

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

        query = f"""
            SELECT * FROM dead_letter
            {where_clause}
            ORDER BY failed_at DESC
            LIMIT ? OFFSET ?
        """

        params.extend([limit, offset])
        rows = conn.execute(query, params).fetchall()

        return [dict(row) for row in rows]

    def retry_dead_letter(self, entry_id: int) -> Optional[Event]:
        """Get dead letter entry for retry and increment retry count."""
        self.initialize()

        conn = self._get_connection()
        row = conn.execute(
            "SELECT * FROM dead_letter WHERE id = ?", (entry_id,)
        ).fetchone()

        if not row:
            return None

        # Increment retry count
        conn.execute("""
            UPDATE dead_letter
            SET retry_count = retry_count + 1, last_retry_at = datetime('now')
            WHERE id = ?
        """, (entry_id,))
        conn.commit()

        # Deserialize event
        event_data = json.loads(row["event_data"])
        return Event.from_dict(event_data)

    def remove_dead_letter(self, entry_id: int) -> bool:
        """Remove entry from dead letter queue."""
        self.initialize()

        conn = self._get_connection()
        cursor = conn.execute("DELETE FROM dead_letter WHERE id = ?", (entry_id,))
        conn.commit()
        return cursor.rowcount > 0

    def clear_dead_letter(self, older_than: Optional[datetime] = None) -> int:
        """Clear dead letter queue, optionally only older than a date."""
        self.initialize()

        conn = self._get_connection()

        if older_than:
            cursor = conn.execute(
                "DELETE FROM dead_letter WHERE failed_at < ?",
                (older_than.isoformat(),)
            )
        else:
            cursor = conn.execute("DELETE FROM dead_letter")

        conn.commit()
        return cursor.rowcount

    # Projection state management

    def update_projection_state(
        self,
        projection_name: str,
        last_event_id: str,
        last_event_timestamp: datetime,
        state_hash: str,
    ) -> None:
        """Update projection checkpoint state."""
        self.initialize()

        conn = self._get_connection()
        conn.execute("""
            INSERT OR REPLACE INTO projection_state
            (projection_name, last_event_id, last_event_timestamp, state_hash, updated_at)
            VALUES (?, ?, ?, ?, datetime('now'))
        """, (projection_name, last_event_id, last_event_timestamp.isoformat(), state_hash))
        conn.commit()

    def get_projection_state(self, projection_name: str) -> Optional[dict[str, Any]]:
        """Get projection checkpoint state."""
        self.initialize()

        conn = self._get_connection()
        row = conn.execute(
            "SELECT * FROM projection_state WHERE projection_name = ?",
            (projection_name,)
        ).fetchone()

        if row:
            return {
                "projection_name": row["projection_name"],
                "last_event_id": row["last_event_id"],
                "last_event_timestamp": datetime.fromisoformat(row["last_event_timestamp"]) if row["last_event_timestamp"] else None,
                "state_hash": row["state_hash"],
                "updated_at": datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None,
            }
        return None

    # Maintenance

    def vacuum(self) -> None:
        """Vacuum database to reclaim space."""
        self.initialize()
        conn = self._get_connection()
        conn.execute("VACUUM")

    def get_stats(self) -> dict[str, Any]:
        """Get store statistics."""
        self.initialize()

        conn = self._get_connection()

        stats = {}

        # Event counts
        row = conn.execute("SELECT COUNT(*) as count FROM events").fetchone()
        stats["total_events"] = row["count"] if row else 0

        # Events by type
        rows = conn.execute("""
            SELECT type, COUNT(*) as count FROM events GROUP BY type ORDER BY count DESC LIMIT 20
        """).fetchall()
        stats["events_by_type"] = {row["type"]: row["count"] for row in rows}

        # Dead letter count
        row = conn.execute("SELECT COUNT(*) as count FROM dead_letter").fetchone()
        stats["dead_letter_count"] = row["count"] if row else 0

        # Snapshot count
        row = conn.execute("SELECT COUNT(*) as count FROM snapshots").fetchone()
        stats["snapshot_count"] = row["count"] if row else 0

        # Database size
        row = conn.execute("PRAGMA page_count").fetchone()
        page_count = row[0] if row else 0
        row = conn.execute("PRAGMA page_size").fetchone()
        page_size = row[0] if row else 4096
        stats["db_size_bytes"] = page_count * page_size

        # WAL mode status
        row = conn.execute("PRAGMA journal_mode").fetchone()
        stats["journal_mode"] = row[0] if row else "unknown"

        return stats


# Global event store instance
_event_store: Optional[EventStore] = None


def get_event_store(config: Optional[EventStoreConfig] = None) -> EventStore:
    """Get global event store instance."""
    global _event_store
    if _event_store is None:
        _event_store = EventStore(config)
    return _event_store


def init_event_store(config: EventStoreConfig) -> EventStore:
    """Initialize global event store with config."""
    global _event_store
    _event_store = EventStore(config)
    _event_store.initialize()
    return _event_store


def close_event_store() -> None:
    """Close global event store."""
    global _event_store
    if _event_store:
        _event_store.close()
        _event_store = None