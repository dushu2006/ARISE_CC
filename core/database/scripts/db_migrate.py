#!/usr/bin/env python
"""
Database Migration CLI Script

Provides commands for managing database migrations:
- init: Initialize migration environment
- create: Create a new migration
- upgrade: Apply migrations
- downgrade: Revert migrations
- current: Show current revision
- history: Show migration history
- heads: Show head revisions
- stamp: Stamp revision without running migrations
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Add core to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from alembic import command
from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory

from core.config import load_config
from core.database.base import init_db, close_db, check_database_health


def get_alembic_config() -> AlembicConfig:
    """Get Alembic configuration."""
    migrations_dir = Path(__file__).parent.parent / "migrations"
    config = AlembicConfig(str(migrations_dir / "alembic.ini"))

    # Override database URL from our config
    try:
        cfg = load_config()
        config.set_main_option("sqlalchemy.url", cfg.database.url)
    except Exception:
        # Use default if config not available
        pass

    return config


def cmd_init(args: argparse.Namespace) -> int:
    """Initialize migration environment."""
    migrations_dir = Path(__file__).parent.parent / "migrations"

    # Create directories
    versions_dir = migrations_dir / "versions"
    versions_dir.mkdir(parents=True, exist_ok=True)

    # Create alembic.ini if not exists
    ini_path = migrations_dir / "alembic.ini"
    if not ini_path.exists():
        ini_content = """# Alembic configuration for ARISE database migrations
[alembic]
script_location = %(here)s
version_locations = %(here)s/versions
prepend_sys_path = .
file_template = %%(year)d%%(month).2d%%(day).2d_%%(hour).2d%%(minute).2d_%%(rev)s_%%(slug)s
truncate_slug_length = 40

# Logging configuration
[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
"""
        ini_path.write_text(ini_content)
        print(f"Created {ini_path}")

    # Create initial migration if no versions exist
    if not any(versions_dir.iterdir()):
        print("No migrations found. Create initial migration with:")
        print("  python -m core.database.scripts.db_migrate create -m \"initial_schema\"")
    else:
        print(f"Migrations directory ready at {migrations_dir}")

    return 0


def cmd_create(args: argparse.Namespace) -> int:
    """Create a new migration."""
    config = get_alembic_config()

    try:
        command.revision(
            config,
            message=args.message,
            autogenerate=args.autogenerate,
            head=args.head,
            splice=args.splice,
            branch_label=args.branch_label,
            version_path=args.version_path,
        )
        print(f"Created migration: {args.message}")
        return 0
    except Exception as e:
        print(f"Error creating migration: {e}")
        return 1


def cmd_upgrade(args: argparse.Namespace) -> int:
    """Upgrade database to a specific revision."""
    config = get_alembic_config()

    try:
        command.upgrade(config, args.revision)
        print(f"Upgraded to revision: {args.revision}")
        return 0
    except Exception as e:
        print(f"Error upgrading: {e}")
        return 1


def cmd_downgrade(args: argparse.Namespace) -> int:
    """Downgrade database to a specific revision."""
    config = get_alembic_config()

    try:
        command.downgrade(config, args.revision)
        print(f"Downgraded to revision: {args.revision}")
        return 0
    except Exception as e:
        print(f"Error downgrading: {e}")
        return 1


def cmd_current(args: argparse.Namespace) -> int:
    """Show current revision."""
    config = get_alembic_config()

    try:
        command.current(config, verbose=args.verbose)
        return 0
    except Exception as e:
        print(f"Error getting current revision: {e}")
        return 1


def cmd_history(args: argparse.Namespace) -> int:
    """Show migration history."""
    config = get_alembic_config()

    try:
        command.history(config, rev_range=args.range, verbose=args.verbose)
        return 0
    except Exception as e:
        print(f"Error getting history: {e}")
        return 1


def cmd_heads(args: argparse.Namespace) -> int:
    """Show head revisions."""
    config = get_alembic_config()

    try:
        command.heads(config, verbose=args.verbose)
        return 0
    except Exception as e:
        print(f"Error getting heads: {e}")
        return 1


def cmd_stamp(args: argparse.Namespace) -> int:
    """Stamp revision without running migrations."""
    config = get_alembic_config()

    try:
        command.stamp(config, args.revision, purge=args.purge)
        print(f"Stamped revision: {args.revision}")
        return 0
    except Exception as e:
        print(f"Error stamping: {e}")
        return 1


def cmd_check(args: argparse.Namespace) -> int:
    """Check database health and migration status."""
    print("Checking database connection...")

    # Initialize database connection
    asyncio.run(init_db())

    healthy = asyncio.run(check_database_health())
    if healthy:
        print("✓ Database connection: OK")
    else:
        print("✗ Database connection: FAILED")
        return 1

    # Check migrations
    config = get_alembic_config()
    script = ScriptDirectory.from_config(config)

    heads = script.get_heads()
    print(f"\nHead revisions: {heads}")

    # Get current revision
    from alembic.runtime.migration import MigrationContext
    from core.database.base import get_async_engine

    async def get_current_rev():
        engine = get_async_engine()
        async with engine.connect() as conn:
            context = MigrationContext.configure(conn)
            return context.get_current_revision()

    current_rev = asyncio.run(get_current_rev())
    print(f"Current revision: {current_rev or 'None (not initialized)'}")

    if current_rev and current_rev not in heads:
        print("⚠ Database is not at head revision!")
        print("  Run 'db-migrate upgrade head' to apply pending migrations")
        return 1
    elif not current_rev:
        print("⚠ Database not initialized!")
        print("  Run 'db-migrate upgrade head' to initialize")
        return 1
    else:
        print("✓ Database is at head revision")

    asyncio.run(close_db())
    return 0


def cmd_create_tables(args: argparse.Namespace) -> int:
    """Create all tables directly (without migrations)."""
    print("Creating all tables...")

    async def create():
        await init_db()
        print("✓ All tables created")
        await close_db()

    asyncio.run(create())
    return 0


def cmd_drop_tables(args: argparse.Namespace) -> int:
    """Drop all tables (DANGEROUS!)."""
    if not args.force:
        confirm = input("This will DELETE ALL DATA. Type 'yes' to confirm: ")
        if confirm != "yes":
            print("Cancelled.")
            return 1

    print("Dropping all tables...")

    async def drop():
        from core.database.base import drop_all_tables
        await drop_all_tables()
        print("✓ All tables dropped")
        await close_db()

    asyncio.run(drop())
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="db-migrate",
        description="ARISE Database Migration CLI",
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # init
    subparsers.add_parser("init", help="Initialize migration environment")

    # create
    create_parser = subparsers.add_parser("create", help="Create a new migration")
    create_parser.add_argument("-m", "--message", required=True, help="Migration message")
    create_parser.add_argument("--autogenerate", action="store_true", default=True, help="Autogenerate migration")
    create_parser.add_argument("--head", default="head", help="Head revision")
    create_parser.add_argument("--splice", action="store_true", help="Splice into history")
    create_parser.add_argument("--branch-label", help="Branch label")
    create_parser.add_argument("--version-path", help="Version path")

    # upgrade
    upgrade_parser = subparsers.add_parser("upgrade", help="Upgrade to a revision")
    upgrade_parser.add_argument("revision", default="head", nargs="?", help="Target revision")

    # downgrade
    downgrade_parser = subparsers.add_parser("downgrade", help="Downgrade to a revision")
    downgrade_parser.add_argument("revision", default="-1", nargs="?", help="Target revision")

    # current
    current_parser = subparsers.add_parser("current", help="Show current revision")
    current_parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")

    # history
    history_parser = subparsers.add_parser("history", help="Show migration history")
    history_parser.add_argument("-r", "--range", help="Revision range (e.g., 'base:head')")
    history_parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")

    # heads
    heads_parser = subparsers.add_parser("heads", help="Show head revisions")
    heads_parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")

    # stamp
    stamp_parser = subparsers.add_parser("stamp", help="Stamp revision without running migrations")
    stamp_parser.add_argument("revision", help="Revision to stamp")
    stamp_parser.add_argument("--purge", action="store_true", help="Purge revision history")

    # check
    subparsers.add_parser("check", help="Check database health and migration status")

    # create-tables
    create_tables_parser = subparsers.add_parser("create-tables", help="Create all tables directly")

    # drop-tables
    drop_tables_parser = subparsers.add_parser("drop-tables", help="Drop all tables (DANGEROUS!)")
    drop_tables_parser.add_argument("--force", action="store_true", help="Skip confirmation")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Map commands to functions
    commands = {
        "init": cmd_init,
        "create": cmd_create,
        "upgrade": cmd_upgrade,
        "downgrade": cmd_downgrade,
        "current": cmd_current,
        "history": cmd_history,
        "heads": cmd_heads,
        "stamp": cmd_stamp,
        "check": cmd_check,
        "create-tables": cmd_create_tables,
        "drop-tables": cmd_drop_tables,
    }

    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())