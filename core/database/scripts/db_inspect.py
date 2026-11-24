#!/usr/bin/env python
"""
Database Inspection CLI Script

Provides commands for inspecting database state:
- tables: List all tables
- schema: Show table schema
- count: Count rows in tables
- sample: Sample data from tables
- indexes: Show indexes
- foreign-keys: Show foreign key relationships
- health: Check database health
- stats: Show database statistics
- audit: Show audit log summary
- tasks: Show task summary
- agents: Show agent summary
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add core to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import inspect, text, func, select, create_engine
from sqlalchemy.engine import Inspector
from sqlalchemy.pool import NullPool

from core.database.base import (
    get_async_engine,
    get_async_session,
    init_db,
    close_db,
    check_database_health,
    Base,
)
from core.database import models
from core.config import load_config


def get_sync_engine():
    """Get a synchronous engine for inspection."""
    cfg = load_config()
    url = cfg.database.url
    if url.startswith("sqlite"):
        url = url.replace("sqlite+aiosqlite", "sqlite")
    return create_engine(url, poolclass=NullPool)


def format_table(rows: List[Dict], headers: Optional[List[str]] = None) -> str:
    """Format rows as a table."""
    if not rows:
        return "(empty)"

    if headers is None:
        headers = list(rows[0].keys())

    # Calculate column widths
    widths = {h: len(h) for h in headers}
    for row in rows:
        for h in headers:
            val = str(row.get(h, ""))
            widths[h] = max(widths[h], len(val))

    # Format header
    header_line = " | ".join(h.ljust(widths[h]) for h in headers)
    separator = "-+-".join("-" * widths[h] for h in headers)

    # Format rows
    lines = [header_line, separator]
    for row in rows:
        line = " | ".join(str(row.get(h, "")).ljust(widths[h]) for h in headers)
        lines.append(line)

    return "\n".join(lines)


async def cmd_tables(args: argparse.Namespace) -> int:
    """List all tables."""
    engine = get_sync_engine()  # Use sync engine for inspection

    inspector = inspect(engine)
    tables = inspector.get_table_names()

    if args.json:
        print(json.dumps(tables, indent=2))
    else:
        print(f"Tables ({len(tables)}):")
        for table in sorted(tables):
            print(f"  {table}")

    return 0


async def cmd_schema(args: argparse.Namespace) -> int:
    """Show table schema."""
    engine = get_sync_engine()  # Use sync engine for inspection

    inspector = inspect(engine)

    if args.table:
        tables = [args.table]
    else:
        tables = inspector.get_table_names()

    for table in tables:
        print(f"\n=== {table} ===")
        columns = inspector.get_columns(table)
        for col in columns:
            nullable = "NULL" if col["nullable"] else "NOT NULL"
            default = f" DEFAULT {col['default']}" if col["default"] is not None else ""
            print(f"  {col['name']}: {col['type']} {nullable}{default}")

        # Show indexes
        indexes = inspector.get_indexes(table)
        if indexes:
            print("  Indexes:")
            for idx in indexes:
                unique = "UNIQUE " if idx["unique"] else ""
                cols = ", ".join(idx["column_names"])
                print(f"    {unique}({cols})")

        # Show foreign keys
        fks = inspector.get_foreign_keys(table)
        if fks:
            print("  Foreign Keys:")
            for fk in fks:
                cols = ", ".join(fk["constrained_columns"])
                ref_cols = ", ".join(fk["referred_columns"])
                print(f"    {cols} -> {fk['referred_table']}({ref_cols})")

    return 0


async def cmd_count(args: argparse.Namespace) -> int:
    """Count rows in tables."""
    engine = get_sync_engine()

    with engine.connect() as conn:
        inspector = inspect(conn)
        tables = inspector.get_table_names()

        results = []
        for table in sorted(tables):
            if args.table and table != args.table:
                continue
            result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
            count = result.scalar()
            results.append({"table": table, "count": count})

        if args.json:
            print(json.dumps(results, indent=2))
        else:
            print(format_table(results, ["table", "count"]))

    return 0


async def cmd_sample(args: argparse.Namespace) -> int:
    """Sample data from tables."""
    engine = get_sync_engine()

    with engine.connect() as conn:
        inspector = inspect(conn)

        tables = [args.table] if args.table else inspector.get_table_names()

        for table in tables:
            if args.table and table != args.table:
                continue

            columns = [c["name"] for c in inspector.get_columns(table)]
            col_str = ", ".join(columns[:args.columns]) if args.columns else ", ".join(columns)

            query = f"SELECT {col_str} FROM {table} LIMIT {args.limit}"
            if args.order_by:
                query += f" ORDER BY {args.order_by} DESC"

            result = conn.execute(text(query))
            rows = [dict(row._mapping) for row in result]

            print(f"\n=== {table} (showing {len(rows)} rows) ===")
            if rows:
                if args.json:
                    print(json.dumps(rows, indent=2, default=str))
                else:
                    # Filter columns if specified
                    if args.columns:
                        headers = columns[:args.columns]
                    else:
                        headers = columns
                    print(format_table(rows, headers))
            else:
                print("(empty)")

    return 0


async def cmd_indexes(args: argparse.Namespace) -> int:
    """Show all indexes."""
    engine = get_sync_engine()  # Use sync engine for inspection

    inspector = inspect(engine)
    tables = inspector.get_table_names()

    all_indexes = []
    for table in tables:
        indexes = inspector.get_indexes(table)
        for idx in indexes:
            all_indexes.append({
                "table": table,
                "name": idx["name"],
                "unique": idx["unique"],
                "columns": ", ".join(idx["column_names"]),
            })

    if args.json:
        print(json.dumps(all_indexes, indent=2))
    else:
        print(format_table(all_indexes, ["table", "name", "unique", "columns"]))

    return 0


async def cmd_foreign_keys(args: argparse.Namespace) -> int:
    """Show foreign key relationships."""
    engine = get_sync_engine()  # Use sync engine for inspection

    inspector = inspect(engine)
    tables = inspector.get_table_names()

    all_fks = []
    for table in tables:
        fks = inspector.get_foreign_keys(table)
        for fk in fks:
            all_fks.append({
                "table": table,
                "columns": ", ".join(fk["constrained_columns"]),
                "ref_table": fk["referred_table"],
                "ref_columns": ", ".join(fk["referred_columns"]),
                "on_delete": fk.get("options", {}).get("ondelete", ""),
            })

    if args.json:
        print(json.dumps(all_fks, indent=2))
    else:
        print(format_table(all_fks, ["table", "columns", "ref_table", "ref_columns", "on_delete"]))

    return 0


async def cmd_health(args: argparse.Namespace) -> int:
    """Check database health."""
    print("Checking database health...")

    healthy = await check_database_health()
    if healthy:
        print("Database connection: OK")
    else:
        print("Database connection: FAILED")
        return 1

    # Additional checks
    engine = get_async_engine()

    async with engine.connect() as conn:
        # Check WAL mode (SQLite)
        result = await conn.execute(text("PRAGMA journal_mode"))
        journal_mode = result.scalar()
        print(f"Journal mode: {journal_mode}")

        # Check page size
        result = await conn.execute(text("PRAGMA page_size"))
        page_size = result.scalar()
        print(f"Page size: {page_size}")

        # Check cache size
        result = await conn.execute(text("PRAGMA cache_size"))
        cache_size = result.scalar()
        print(f"Cache size: {cache_size} pages ({abs(cache_size) * page_size / 1024 / 1024:.1f} MB)")

        # Check foreign keys
        result = await conn.execute(text("PRAGMA foreign_keys"))
        fk = result.scalar()
        print(f"Foreign keys: {'ON' if fk else 'OFF'}")

        # Check integrity
        result = await conn.execute(text("PRAGMA integrity_check"))
        integrity = result.scalar()
        print(f"Integrity: {integrity}")

    await close_db()
    return 0


async def cmd_stats(args: argparse.Namespace) -> int:
    """Show database statistics."""
    engine = get_sync_engine()  # Use sync engine for inspection

    inspector = inspect(engine)
    tables = inspector.get_table_names()

    stats = []
    for table in tables:
        # Get row count using sync engine
        with engine.connect() as conn:
            result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
            count = result.scalar()

        # Estimate size (SQLite)
        if count > 0:
            # Get column info for size estimation
            columns = inspector.get_columns(table)
            # Rough estimate
            avg_row_size = sum(50 for _ in columns)  # rough estimate
            est_size_kb = (count * avg_row_size) / 1024
        else:
            est_size_kb = 0

        stats.append({
            "table": table,
            "rows": count,
            "est_size_kb": round(est_size_kb, 1),
        })

    # Sort by size
    stats.sort(key=lambda x: x["est_size_kb"], reverse=True)

    if args.json:
        print(json.dumps(stats, indent=2))
    else:
        print(format_table(stats, ["table", "rows", "est_size_kb"]))

        # Total
        total_rows = sum(s["rows"] for s in stats)
        total_size = sum(s["est_size_kb"] for s in stats)
        print(f"\nTotal: {total_rows} rows, ~{total_size:.1f} KB")

    return 0


async def cmd_audit(args: argparse.Namespace) -> int:
    """Show audit log summary."""

    cfg = load_config()
    async with get_async_session(cfg.database.url) as session:
        # Recent audit events
        from core.database.models import AuditLog, SecurityEvent

        query = select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(args.limit)
        result = await session.execute(query)
        events = result.scalars().all()

        if args.json:
            data = [{
                "event_id": e.id,
                "event_type": e.event_type.value,
                "timestamp": e.timestamp.isoformat(),
                "user_id": e.user_id,
                "action": e.action,
                "resource": e.resource,
                "success": e.success,
            } for e in events]
            print(json.dumps(data, indent=2))
        else:
            rows = [{
                "event_id": e.id[:8] + "...",
                "type": e.event_type.value,
                "time": e.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                "user": e.user_id,
                "action": e.action,
                "resource": e.resource or "-",
                "success": "OK" if e.success else "FAIL",
            } for e in events]
            print(format_table(rows, ["event_id", "type", "time", "user", "action", "resource", "success"]))

        # Security events count
        sec_query = select(func.count(SecurityEvent.event_id))
        sec_result = await session.execute(sec_query)
        sec_count = sec_result.scalar()

        # Unacknowledged security events
        unack_query = select(func.count(SecurityEvent.event_id)).where(SecurityEvent.acknowledged == False)
        unack_result = await session.execute(unack_query)
        unack_count = unack_result.scalar()

        print(f"\nSecurity events: {sec_count} total, {unack_count} unacknowledged")

    await close_db()
    return 0


async def cmd_tasks(args: argparse.Namespace) -> int:
    """Show task summary."""

    cfg = load_config()
    async with get_async_session(cfg.database.url) as session:
        from core.database.models import Task, TaskStatus

        # Count by status
        query = select(Task.status, func.count(Task.id)).group_by(Task.status)
        result = await session.execute(query)
        status_counts = {row[0].value: row[1] for row in result}

        print("Tasks by status:")
        for status in TaskStatus:
            count = status_counts.get(status.value, 0)
            print(f"  {status.value}: {count}")

        # Recent tasks
        query = select(Task).order_by(Task.created_at.desc()).limit(args.limit)
        result = await session.execute(query)
        tasks = result.scalars().all()

        print(f"\nRecent tasks ({len(tasks)}):")
        rows = [{
            "task_id": t.id[:8] + "...",
            "objective": t.objective[:50] + "..." if len(t.objective) > 50 else t.objective,
            "status": t.status.value,
            "risk": t.risk_level.value,
            "priority": t.priority.name,
            "created": t.created_at.strftime("%Y-%m-%d %H:%M"),
        } for t in tasks]
        print(format_table(rows, ["task_id", "objective", "status", "risk", "priority", "created"]))

    await close_db()
    return 0


async def cmd_agents(args: argparse.Namespace) -> int:
    """Show agent summary."""

    cfg = load_config()
    async with get_async_session(cfg.database.url) as session:
        from core.database.models import Agent, AgentHealth, AgentExecution, AgentStatus, AgentType

        # Agents by type
        query = select(Agent.type, func.count(Agent.id)).group_by(Agent.type)
        result = await session.execute(query)
        type_counts = {row[0].value: row[1] for row in result}

        print("Agents by type:")
        for atype in AgentType:
            count = type_counts.get(atype.value, 0)
            print(f"  {atype.value}: {count}")

        # Health summary
        query = select(AgentHealth.status, func.count(AgentHealth.agent_id)).group_by(AgentHealth.status)
        result = await session.execute(query)
        health_counts = {row[0].value: row[1] for row in result}

        print("\nAgent health:")
        for status in AgentStatus:
            count = health_counts.get(status.value, 0)
            print(f"  {status.value}: {count}")

        # Recent executions
        query = select(AgentExecution).order_by(AgentExecution.started_at.desc()).limit(args.limit)
        result = await session.execute(query)
        executions = result.scalars().all()

        print(f"\nRecent executions ({len(executions)}):")
        rows = [{
            "execution_id": e.id[:8] + "...",
            "agent_id": e.agent_id[:8] + "...",
            "objective": e.objective[:50] + "..." if len(e.objective) > 50 else e.objective,
            "status": e.status,
            "time_ms": e.execution_time_ms or 0,
            "started": e.started_at.strftime("%Y-%m-%d %H:%M"),
        } for e in executions]
        print(format_table(rows, ["execution_id", "agent_id", "objective", "status", "time_ms", "started"]))

    await close_db()
    return 0


async def cmd_memories(args: argparse.Namespace) -> int:
    """Show memory summary."""

    cfg = load_config()
    async with get_async_session(cfg.database.url) as session:
        from core.database.models import MemoryMetadata, MemoryKind, ConsolidationRun

        # Memories by kind
        query = select(MemoryMetadata.kind, func.count(MemoryMetadata.id)).group_by(MemoryMetadata.kind)
        result = await session.execute(query)
        kind_counts = {row[0].value: row[1] for row in result}

        print("Memories by kind:")
        for kind in MemoryKind:
            count = kind_counts.get(kind.value, 0)
            print(f"  {kind.value}: {count}")

        # PII flagged
        query = select(func.count(MemoryMetadata.id)).where(MemoryMetadata.pii_detected == True)
        result = await session.execute(query)
        pii_count = result.scalar()
        print(f"\nPII flagged: {pii_count}")

        # Archived
        query = select(func.count(MemoryMetadata.id)).where(MemoryMetadata.is_archived == True)
        result = await session.execute(query)
        archived_count = result.scalar()
        print(f"Archived: {archived_count}")

        # Recent consolidations
        query = select(ConsolidationRun).order_by(ConsolidationRun.started_at.desc()).limit(args.limit)
        result = await session.execute(query)
        consolidations = result.scalars().all()

        print(f"\nRecent consolidations ({len(consolidations)}):")
        rows = [{
            "run_id": c.id[:8] + "...",
            "kind": c.kind,
            "status": c.status,
            "input": c.input_count,
            "output": c.output_count,
            "started": c.started_at.strftime("%Y-%m-%d %H:%M"),
        } for c in consolidations]
        print(format_table(rows, ["run_id", "kind", "status", "input", "output", "started"]))

    await close_db()
    return 0


async def cmd_voice(args: argparse.Namespace) -> int:
    """Show voice session summary."""

    cfg = load_config()
    async with get_async_session(cfg.database.url) as session:
        from core.database.models import VoiceSession, VoiceInteraction, VoiceSessionStatus

        # Sessions by status
        query = select(VoiceSession.status, func.count(VoiceSession.id)).group_by(VoiceSession.status)
        result = await session.execute(query)
        status_counts = {row[0].value: row[1] for row in result}

        print("Voice sessions by status:")
        for status in VoiceSessionStatus:
            count = status_counts.get(status.value, 0)
            print(f"  {status.value}: {count}")

        # Total interactions
        query = select(func.sum(VoiceSession.total_interactions))
        result = await session.execute(query)
        total_interactions = result.scalar() or 0
        print(f"\nTotal interactions: {total_interactions}")

        # Recent sessions
        query = select(VoiceSession).order_by(VoiceSession.started_at.desc()).limit(args.limit)
        result = await session.execute(query)
        sessions = result.scalars().all()

        print(f"\nRecent sessions ({len(sessions)}):")
        rows = [{
            "session_id": s.id[:8] + "...",
            "user": s.user_id,
            "privacy": s.privacy_mode.value,
            "status": s.status.value,
            "interactions": s.total_interactions,
            "audio_ms": s.total_audio_duration_ms,
            "started": s.started_at.strftime("%Y-%m-%d %H:%M"),
        } for s in sessions]
        print(format_table(rows, ["session_id", "user", "privacy", "status", "interactions", "audio_ms", "started"]))

    await close_db()
    return 0


async def cmd_config(args: argparse.Namespace) -> int:
    """Show configuration settings."""

    cfg = load_config()
    async with get_async_session(cfg.database.url) as session:
        from core.database.models import Setting

        query = select(Setting).order_by(Setting.category, Setting.key)
        if args.category:
            query = query.where(Setting.category == args.category)
        result = await session.execute(query)
        settings = result.scalars().all()

        print(f"Settings ({len(settings)}):")
        rows = [{
            "key": s.key,
            "type": s.value_type,
            "category": s.category,
            "sensitive": "SECRET" if s.is_sensitive else "",
            "mutable": "YES" if s.is_runtime_mutable else "NO",
            "value": str(s.value_json)[:50] + "..." if len(str(s.value_json)) > 50 else str(s.value_json),
        } for s in settings]
        print(format_table(rows, ["key", "type", "category", "sensitive", "mutable", "value"]))

    await close_db()
    return 0


async def cmd_evidence(args: argparse.Namespace) -> int:
    """Show evidence summary."""

    cfg = load_config()
    async with get_async_session(cfg.database.url) as session:
        from core.database.models import Evidence, EvidenceChain

        # Evidence by type
        query = select(Evidence.type, func.count(Evidence.id)).group_by(Evidence.type)
        result = await session.execute(query)
        type_counts = dict(result.all())

        print("Evidence by type:")
        for etype, count in sorted(type_counts.items()):
            print(f"  {etype}: {count}")

        # Total size
        query = select(func.sum(Evidence.file_size_bytes))
        result = await session.execute(query)
        total_size = result.scalar() or 0
        print(f"\nTotal size: {total_size / 1024 / 1024:.2f} MB")

        # Recent evidence
        query = select(Evidence).order_by(Evidence.created_at.desc()).limit(args.limit)
        result = await session.execute(query)
        evidence = result.scalars().all()

        print(f"\nRecent evidence ({len(evidence)}):")
        rows = [{
            "evidence_id": e.id[:8] + "...",
            "type": e.type,
            "task_id": e.task_id[:8] + "..." if e.task_id else "-",
            "size_kb": round(e.file_size_bytes / 1024, 1),
            "mime": e.mime_type or "-",
            "created": e.created_at.strftime("%Y-%m-%d %H:%M"),
        } for e in evidence]
        print(format_table(rows, ["evidence_id", "type", "task_id", "size_kb", "mime", "created"]))

        # Chains
        query = select(func.count(EvidenceChain.id))
        result = await session.execute(query)
        chain_count = result.scalar()
        print(f"\nEvidence chains: {chain_count}")

    await close_db()
    return 0


async def cmd_migrations(args: argparse.Namespace) -> int:
    """Show migration status."""
    engine = get_sync_engine()  # Use sync engine for Alembic

    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory

    # Get current revision
    with engine.connect() as conn:
        context = MigrationContext.configure(conn)
        current_rev = context.get_current_revision()

    # Get head revisions
    from core.database.migrations.env import get_alembic_config
    config = get_alembic_config()
    script = ScriptDirectory.from_config(config)
    heads = script.get_heads()

    print(f"Current revision: {current_rev or 'None'}")
    print(f"Head revisions: {heads}")

    if current_rev and current_rev not in heads:
        print("Not at head revision!")

    # Show history
    print("\nMigration history:")
    for rev in script.walk_revisions():
        marker = " -> " if rev.revision == current_rev else "    "
        print(f"{marker}{rev.revision}: {rev.doc}")

    return 0


async def cmd_export(args: argparse.Namespace) -> int:
    """Export table data as JSON/CSV."""
    engine = get_sync_engine()

    with engine.connect() as conn:
        inspector = inspect(conn)

        tables = [args.table] if args.table else inspector.get_table_names()

        for table in tables:
            columns = [c["name"] for c in inspector.get_columns(table)]
            col_str = ", ".join(columns[:args.columns]) if args.columns else ", ".join(columns)

            query = f"SELECT {col_str} FROM {table}"
            if args.where:
                query += f" WHERE {args.where}"
            if args.order_by:
                query += f" ORDER BY {args.order_by}"
            if args.limit:
                query += f" LIMIT {args.limit}"

            result = conn.execute(text(query))
            rows = [dict(row._mapping) for row in result]

            if args.format == "json":
                output = {table: rows}
                if args.output:
                    with open(args.output, "w") as f:
                        json.dump(output, f, indent=2, default=str)
                else:
                    print(json.dumps(output, indent=2, default=str))
            elif args.format == "csv":
                import csv
                import io
                output = io.StringIO()
                if rows:
                    writer = csv.DictWriter(output, fieldnames=rows[0].keys())
                    writer.writeheader()
                    writer.writerows(rows)
                if args.output:
                    with open(args.output, "w") as f:
                        f.write(output.getvalue())
                else:
                    print(output.getvalue())

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="db-inspect",
        description="ARISE Database Inspection CLI",
    )
    parser.add_argument("-j", "--json", action="store_true", help="Output as JSON")
    parser.add_argument("-l", "--limit", type=int, default=20, help="Limit rows (default: 20)")

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # tables
    subparsers.add_parser("tables", help="List all tables")

    # schema
    schema_parser = subparsers.add_parser("schema", help="Show table schema")
    schema_parser.add_argument("table", nargs="?", help="Table name (default: all)")

    # count
    count_parser = subparsers.add_parser("count", help="Count rows in tables")
    count_parser.add_argument("table", nargs="?", help="Table name (default: all)")

    # sample
    sample_parser = subparsers.add_parser("sample", help="Sample data from tables")
    sample_parser.add_argument("table", nargs="?", help="Table name (default: all)")
    sample_parser.add_argument("-c", "--columns", type=int, help="Number of columns to show")
    sample_parser.add_argument("-o", "--order-by", help="Order by column")

    # indexes
    subparsers.add_parser("indexes", help="Show all indexes")

    # foreign-keys
    subparsers.add_parser("foreign-keys", help="Show foreign key relationships")

    # health
    subparsers.add_parser("health", help="Check database health")

    # stats
    subparsers.add_parser("stats", help="Show database statistics")

    # audit
    audit_parser = subparsers.add_parser("audit", help="Show audit log summary")
    audit_parser.add_argument("-l", "--limit", type=int, default=20, help="Limit events")

    # tasks
    tasks_parser = subparsers.add_parser("tasks", help="Show task summary")
    tasks_parser.add_argument("-l", "--limit", type=int, default=20, help="Limit tasks")

    # agents
    agents_parser = subparsers.add_parser("agents", help="Show agent summary")
    agents_parser.add_argument("-l", "--limit", type=int, default=20, help="Limit executions")

    # memories
    memories_parser = subparsers.add_parser("memories", help="Show memory summary")
    memories_parser.add_argument("-l", "--limit", type=int, default=20, help="Limit consolidations")

    # voice
    voice_parser = subparsers.add_parser("voice", help="Show voice session summary")
    voice_parser.add_argument("-l", "--limit", type=int, default=20, help="Limit sessions")

    # config
    config_parser = subparsers.add_parser("config", help="Show configuration settings")
    config_parser.add_argument("-c", "--category", help="Filter by category")

    # evidence
    evidence_parser = subparsers.add_parser("evidence", help="Show evidence summary")
    evidence_parser.add_argument("-l", "--limit", type=int, default=20, help="Limit evidence")

    # migrations
    subparsers.add_parser("migrations", help="Show migration status")

    # export
    export_parser = subparsers.add_parser("export", help="Export table data")
    export_parser.add_argument("table", nargs="?", help="Table name (default: all)")
    export_parser.add_argument("-f", "--format", choices=["json", "csv"], default="json", help="Output format")
    export_parser.add_argument("-o", "--output", help="Output file")
    export_parser.add_argument("-c", "--columns", type=int, help="Number of columns")
    export_parser.add_argument("-w", "--where", help="WHERE clause")
    export_parser.add_argument("--order-by", help="ORDER BY clause")
    export_parser.add_argument("-l", "--limit", type=int, help="Limit rows")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    commands = {
        "tables": cmd_tables,
        "schema": cmd_schema,
        "count": cmd_count,
        "sample": cmd_sample,
        "indexes": cmd_indexes,
        "foreign-keys": cmd_foreign_keys,
        "health": cmd_health,
        "stats": cmd_stats,
        "audit": cmd_audit,
        "tasks": cmd_tasks,
        "agents": cmd_agents,
        "memories": cmd_memories,
        "voice": cmd_voice,
        "config": cmd_config,
        "evidence": cmd_evidence,
        "migrations": cmd_migrations,
        "export": cmd_export,
    }

    return asyncio.run(commands[args.command](args))


if __name__ == "__main__":
    sys.exit(main())