# Alembic environment configuration for ARISE database migrations
# Supports both sync and async operations

import asyncio
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Add the core package to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.database.base import Base
from core.database import models  # noqa: F401 - Import all models
from core.config import load_config


def get_alembic_config():
    """Get the Alembic configuration object."""
    from alembic.config import Config
    from pathlib import Path

    migrations_dir = Path(__file__).parent
    cfg = Config(str(migrations_dir / "alembic.ini"))
    return cfg


# Get config for module-level use (when run by alembic)
config = get_alembic_config()

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set target metadata
target_metadata = Base.metadata


def get_database_url() -> str:
    """Get database URL from configuration."""
    try:
        cfg = load_config()
        url = cfg.database.url
        # Convert relative paths to absolute paths based on project root
        if url.startswith("sqlite") and "///" in url:
            # Extract the path part
            path_part = url.split("///", 1)[1]
            if not os.path.isabs(path_part):
                # Resolve relative to project root (3 levels up from migrations)
                project_root = Path(__file__).parent.parent.parent.parent
                abs_path = (project_root / path_part).resolve()
                return f"sqlite+aiosqlite:///{abs_path.as_posix()}"
        return url
    except Exception:
        # Fallback for migration generation without full config
        return os.getenv("DATABASE_URL", "sqlite+aiosqlite:///data/arise.db")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations with the given connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in async mode."""
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = get_database_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    try:
        # Try to run async migrations
        asyncio.run(run_async_migrations())
    except RuntimeError:
        # Fallback for environments with existing event loop
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Create a task and wait for it
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, run_async_migrations())
                future.result()
        else:
            asyncio.run(run_async_migrations())


# Only run migrations when this file is executed by alembic directly
# (not when imported by db_inspect or other scripts)
def run_alembic_migrations():
    """Run migrations - only called by alembic command."""
    if context.is_offline_mode():
        run_migrations_offline()
    else:
        run_migrations_online()


if __name__ == "__main__":
    run_alembic_migrations()