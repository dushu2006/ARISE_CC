"""
SQLAlchemy 2.0 Async Database Base and Session Management

Provides:
- Declarative base with common mixins
- Async engine and session factory
- Database manager for lifecycle
- Connection pooling with SQLite WAL mode
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any, AsyncGenerator, Optional, TypeVar
from uuid import uuid4

from sqlalchemy import DateTime, MetaData, String, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column
from sqlalchemy.pool import NullPool
from sqlalchemy import event

from core.config import load_config


# =============================================================================
# Naming Convention for Constraints
# =============================================================================

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


# =============================================================================
# Declarative Base
# =============================================================================

class Base(DeclarativeBase):
    """Base class for all ORM models with common configuration."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    # Default table name from class name (snake_case plural)
    @declared_attr.directive
    def __tablename__(cls) -> str:
        import re
        name = re.sub(r"(?<!^)(?=[A-Z])", "_", cls.__name__).lower()
        if name.endswith("y"):
            return name[:-1] + "ies"
        elif name.endswith("s"):
            return name + "es"
        else:
            return name + "s"


# =============================================================================
# Mixins
# =============================================================================

class TimestampMixin:
    """Mixin for created_at and updated_at timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        doc="Record creation timestamp (UTC)",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
        doc="Record last update timestamp (UTC)",
    )


class UUIDMixin:
    """Mixin for UUID primary key."""

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
        nullable=False,
        doc="Unique identifier (UUID v4)",
    )


class SoftDeleteMixin:
    """Mixin for soft delete support."""

    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Soft delete timestamp (UTC)",
    )
    is_deleted: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        doc="Soft delete flag",
    )


# =============================================================================
# Database Manager
# =============================================================================

class DatabaseManager:
    """
    Manages database connections and sessions.

    Supports multiple database backends (SQLite, PostgreSQL) with
    proper connection pooling and async patterns.
    """

    def __init__(self, database_url: Optional[str] = None):
        self._engine: Optional[AsyncEngine] = None
        self._session_factory: Optional[async_sessionmaker[AsyncSession]] = None
        self._database_url = database_url
        self._initialized = False

    @property
    def database_url(self) -> str:
        """Get database URL from config or override."""
        if self._database_url:
            return self._database_url
        cfg = load_config()
        url = cfg.database.url
        # Convert relative SQLite paths to absolute paths based on project root
        if url.startswith("sqlite") and "///" in url:
            path_part = url.split("///", 1)[1]
            if not os.path.isabs(path_part):
                # Resolve relative to project root (where config is loaded from)
                project_root = Path(__file__).parent.parent.parent
                abs_path = (project_root / path_part).resolve()
                return f"sqlite+aiosqlite:///{abs_path.as_posix()}"
        return url

    @property
    def engine(self) -> AsyncEngine:
        """Get or create async engine."""
        if self._engine is None:
            self._engine = self._create_engine()
        return self._engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        """Get or create session factory."""
        if self._session_factory is None:
            self._session_factory = async_sessionmaker(
                bind=self.engine,
                class_=AsyncSession,
                expire_on_commit=False,
                autoflush=False,
            )
        return self._session_factory

    def _create_engine(self) -> AsyncEngine:
        """Create async engine with appropriate settings."""
        url = self.database_url

        # SQLite-specific configuration
        if url.startswith("sqlite"):
            # For SQLite, use NullPool to avoid connection issues
            # and enable WAL mode
            engine = create_async_engine(
                url,
                echo=False,
                poolclass=NullPool,
                connect_args={
                    "check_same_thread": False,
                    "timeout": 30,
                },
            )

            # Configure SQLite pragmas on connect
            @event.listens_for(engine.sync_engine, "connect")
            def set_sqlite_pragma(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.execute("PRAGMA cache_size=-32768")  # 32MB
                cursor.execute("PRAGMA temp_store=MEMORY")
                cursor.execute("PRAGMA mmap_size=268435456")  # 256MB
                cursor.execute("PRAGMA page_size=4096")
                cursor.execute("PRAGMA busy_timeout=5000")
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA recursive_triggers=ON")
                cursor.close()

        # PostgreSQL-specific configuration
        elif url.startswith("postgresql"):
            engine = create_async_engine(
                url,
                echo=False,
                pool_size=10,
                max_overflow=20,
                pool_timeout=30.0,
                pool_recycle=3600,
                pool_pre_ping=True,
            )

        else:
            # Default configuration
            engine = create_async_engine(url, echo=False)

        return engine

    async def init(self) -> None:
        """Initialize database - create tables if they don't exist."""
        if self._initialized:
            return

        # Import all models to register them
        from core.database import models  # noqa: F401

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        self._initialized = True

    async def close(self) -> None:
        """Close database connections."""
        if self._engine:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None
            self._initialized = False

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get a database session with automatic commit/rollback."""
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[AsyncSession, None]:
        """Get a session with explicit transaction control."""
        async with self.session_factory() as session:
            async with session.begin():
                try:
                    yield session
                except Exception:
                    await session.rollback()
                    raise

    async def health_check(self) -> bool:
        """Check database connectivity."""
        try:
            async with self.session_factory() as session:
                await session.execute(select(1))
            return True
        except Exception:
            return False


# =============================================================================
# Global Database Manager Instance
# =============================================================================

_db_manager: Optional[DatabaseManager] = None


def get_database_manager(database_url: Optional[str] = None) -> DatabaseManager:
    """Get global database manager instance."""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager(database_url)
    elif database_url and _db_manager._database_url != database_url:
        # Recreate manager if URL changed
        _db_manager = DatabaseManager(database_url)
    return _db_manager


def get_engine(database_url: Optional[str] = None) -> AsyncEngine:
    """Get async engine."""
    return get_database_manager(database_url).engine


def get_session_factory(database_url: Optional[str] = None) -> async_sessionmaker[AsyncSession]:
    """Get session factory."""
    return get_database_manager(database_url).session_factory


@asynccontextmanager
async def get_session(database_url: Optional[str] = None) -> AsyncGenerator[AsyncSession, None]:
    """Get a database session."""
    async with get_database_manager(database_url).session() as session:
        yield session


async def init_db(database_url: Optional[str] = None) -> None:
    """Initialize database."""
    await get_database_manager(database_url).init()


async def close_db() -> None:
    """Close database connections."""
    global _db_manager
    if _db_manager:
        await _db_manager.close()
        _db_manager = None


# =============================================================================
# Utility Functions
# =============================================================================

async def run_migrations(database_url: Optional[str] = None) -> None:
    """Run database migrations (placeholder for Alembic integration)."""
    # This will be implemented with Alembic
    await init_db(database_url)


async def check_database_health(database_url: Optional[str] = None) -> bool:
    """Check database connectivity."""
    try:
        async with get_session(database_url) as session:
            await session.execute(select(1))
        return True
    except Exception:
        return False


async def drop_all_tables(database_url: Optional[str] = None) -> None:
    """Drop all tables (use with caution!)."""
    engine = get_engine(database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# Convenience alias for backwards compatibility
AsyncSessionLocal = get_session_factory()
get_async_engine = get_engine
get_async_session_factory = get_session_factory
get_async_session = get_session


def get_table_names(database_url: Optional[str] = None) -> list[str]:
    """Get all table names in the database."""
    from sqlalchemy import inspect

    engine = get_engine(database_url)
    inspector = inspect(engine.sync_engine)
    return inspector.get_table_names()


T = TypeVar("T", bound=Base)


async def get_or_create(
    session: AsyncSession,
    model: type[T],
    defaults: Optional[dict[str, Any]] = None,
    **kwargs: Any,
) -> tuple[T, bool]:
    """
    Get an instance or create it if it doesn't exist.

    Returns:
        Tuple of (instance, created)
    """
    stmt = select(model).filter_by(**kwargs)
    result = await session.execute(stmt)
    instance = result.scalar_one_or_none()

    if instance:
        return instance, False

    params = {**kwargs, **(defaults or {})}
    instance = model(**params)
    session.add(instance)
    await session.flush()
    return instance, True


async def bulk_insert(
    session: AsyncSession,
    model: type[T],
    objects: list[dict[str, Any]],
    batch_size: int = 1000,
) -> int:
    """
    Bulk insert objects efficiently.

    Returns:
        Number of inserted rows
    """
    total = 0
    for i in range(0, len(objects), batch_size):
        batch = objects[i:i + batch_size]
        session.add_all([model(**obj) for obj in batch])
        await session.flush()
        total += len(batch)
    return total