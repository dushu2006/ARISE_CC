"""
ARISE Configuration Migration System
Handles versioned configuration migrations with rollback support.
"""

import json
import shutil
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Type
from enum import Enum

logger = logging.getLogger(__name__)


class MigrationStatus(str, Enum):
    """Migration status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


@dataclass
class MigrationRecord:
    """Record of a migration execution."""
    version: str
    name: str
    status: MigrationStatus = MigrationStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    backup_path: Optional[str] = None


class ConfigMigration(ABC):
    """Abstract base class for configuration migrations."""

    def __init__(self, version: str, name: str, description: str = ""):
        self.version = version
        self.name = name
        self.description = description

    @abstractmethod
    def up(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply the migration.
        Returns the updated config dict.
        """
        pass

    @abstractmethod
    def down(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Rollback the migration.
        Returns the restored config dict.
        """
        pass

    def validate(self, config: Dict[str, Any]) -> bool:
        """Validate config after migration. Override for custom validation."""
        return True


class ConfigMigrator:
    """
    Manages configuration migrations with versioning and rollback support.
    """

    def __init__(
        self,
        config_dir: Path,
        migrations_dir: Optional[Path] = None,
        backup_dir: Optional[Path] = None,
    ):
        self.config_dir = config_dir
        self.migrations_dir = migrations_dir or config_dir / "migrations"
        self.backup_dir = backup_dir or config_dir / "backups"
        self.migrations: Dict[str, ConfigMigration] = {}
        self.history: List[MigrationRecord] = []

        self.migrations_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        self._load_history()

    def register(self, migration: ConfigMigration) -> None:
        """Register a migration."""
        if migration.version in self.migrations:
            raise ValueError(f"Migration version {migration.version} already registered")
        self.migrations[migration.version] = migration

    def register_module(self, module: Type) -> None:
        """Register all migrations from a module."""
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if isinstance(attr, type) and issubclass(attr, ConfigMigration) and attr != ConfigMigration:
                migration = attr()
                self.register(migration)

    def get_current_version(self) -> str:
        """Get current config version from the config file."""
        config_file = self.config_dir / "config.default.yaml"
        if config_file.exists():
            import yaml
            with open(config_file) as f:
                config = yaml.safe_load(f) or {}
                return config.get("version", "0.0.0")
        return "0.0.0"

    def get_target_version(self) -> str:
        """Get target version (latest migration)."""
        if not self.migrations:
            return self.get_current_version()
        return max(self.migrations.keys(), key=self._version_key)

    def _version_key(self, version: str) -> tuple:
        """Convert version string to tuple for sorting."""
        parts = version.split(".")
        return tuple(int(p) for p in parts)

    def get_pending_migrations(self) -> List[ConfigMigration]:
        """Get migrations that need to be applied."""
        current = self.get_current_version()
        target = self.get_target_version()

        if self._version_key(current) >= self._version_key(target):
            return []

        pending = []
        for version in sorted(self.migrations.keys(), key=self._version_key):
            if self._version_key(version) > self._version_key(current):
                pending.append(self.migrations[version])
        return pending

    def migrate(self, target_version: Optional[str] = None, dry_run: bool = False) -> bool:
        """
        Run pending migrations up to target version.
        Returns True if all migrations succeeded.
        """
        pending = self.get_pending_migrations()

        if target_version:
            pending = [m for m in pending if self._version_key(m.version) <= self._version_key(target_version)]

        if not pending:
            logger.info("No pending migrations")
            return True

        logger.info(f"Running {len(pending)} migration(s)")

        # Load current config
        config_file = self.config_dir / "config.default.yaml"
        import yaml
        with open(config_file) as f:
            config = yaml.safe_load(f) or {}

        # Create backup
        backup_path = self._create_backup(config)
        logger.info(f"Created backup: {backup_path}")

        try:
            for migration in pending:
                record = MigrationRecord(
                    version=migration.version,
                    name=migration.name,
                    status=MigrationStatus.RUNNING,
                    started_at=datetime.utcnow(),
                    backup_path=str(backup_path),
                )
                self.history.append(record)

                logger.info(f"Applying migration {migration.version}: {migration.name}")

                if not dry_run:
                    config = migration.up(config)

                    # Validate
                    if not migration.validate(config):
                        raise ValueError(f"Migration {migration.version} validation failed")

                    # Update config version
                    config["version"] = migration.version

                    # Save config
                    with open(config_file, "w") as f:
                        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

                record.status = MigrationStatus.COMPLETED
                record.completed_at = datetime.utcnow()
                self._save_history()

                logger.info(f"Migration {migration.version} completed")

            return True

        except Exception as e:
            logger.error(f"Migration failed: {e}")
            record.status = MigrationStatus.FAILED
            record.error = str(e)
            record.completed_at = datetime.utcnow()
            self._save_history()

            # Rollback on failure
            if not dry_run:
                self._restore_backup(backup_path)
                logger.info("Rolled back to backup")

            return False

    def rollback(self, target_version: str, dry_run: bool = False) -> bool:
        """
        Rollback migrations to target version.
        Returns True if rollback succeeded.
        """
        current = self.get_current_version()

        if self._version_key(target_version) >= self._version_key(current):
            logger.info("Target version is not older than current version")
            return True

        # Find migrations to rollback (in reverse order)
        to_rollback = []
        for version in sorted(self.migrations.keys(), key=self._version_key, reverse=True):
            if self._version_key(version) > self._version_key(target_version):
                to_rollback.append(self.migrations[version])

        if not to_rollback:
            logger.info("No migrations to rollback")
            return True

        logger.info(f"Rolling back {len(to_rollback)} migration(s)")

        # Load current config
        config_file = self.config_dir / "config.default.yaml"
        import yaml
        with open(config_file) as f:
            config = yaml.safe_load(f) or {}

        # Create backup
        backup_path = self._create_backup(config)
        logger.info(f"Created backup: {backup_path}")

        try:
            for migration in to_rollback:
                record = MigrationRecord(
                    version=migration.version,
                    name=migration.name,
                    status=MigrationStatus.RUNNING,
                    started_at=datetime.utcnow(),
                    backup_path=str(backup_path),
                )
                self.history.append(record)

                logger.info(f"Rolling back migration {migration.version}: {migration.name}")

                if not dry_run:
                    config = migration.down(config)

                    # Update config version
                    config["version"] = target_version

                    # Save config
                    with open(config_file, "w") as f:
                        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

                record.status = MigrationStatus.ROLLED_BACK
                record.completed_at = datetime.utcnow()
                self._save_history()

                logger.info(f"Rollback {migration.version} completed")

            return True

        except Exception as e:
            logger.error(f"Rollback failed: {e}")
            record.status = MigrationStatus.FAILED
            record.error = str(e)
            record.completed_at = datetime.utcnow()
            self._save_history()

            # Restore backup on failure
            if not dry_run:
                self._restore_backup(backup_path)
                logger.info("Restored backup after rollback failure")

            return False

    def _create_backup(self, config: Dict[str, Any]) -> Path:
        """Create a backup of the current config."""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_file = self.backup_dir / f"config_backup_{timestamp}.yaml"

        import yaml
        with open(backup_file, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

        return backup_file

    def _restore_backup(self, backup_path: Path) -> None:
        """Restore config from backup."""
        config_file = self.config_dir / "config.default.yaml"
        shutil.copy2(backup_path, config_file)

    def _load_history(self) -> None:
        """Load migration history."""
        history_file = self.migrations_dir / "history.json"
        if history_file.exists():
            try:
                with open(history_file) as f:
                    data = json.load(f)
                    self.history = [
                        MigrationRecord(
                            version=r["version"],
                            name=r["name"],
                            status=MigrationStatus(r["status"]),
                            started_at=datetime.fromisoformat(r["started_at"]) if r["started_at"] else None,
                            completed_at=datetime.fromisoformat(r["completed_at"]) if r["completed_at"] else None,
                            error=r["error"],
                            backup_path=r["backup_path"],
                        )
                        for r in data
                    ]
            except Exception as e:
                logger.warning(f"Failed to load migration history: {e}")

    def _save_history(self) -> None:
        """Save migration history."""
        history_file = self.migrations_dir / "history.json"
        data = [
            {
                "version": r.version,
                "name": r.name,
                "status": r.status.value,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                "error": r.error,
                "backup_path": r.backup_path,
            }
            for r in self.history
        ]
        with open(history_file, "w") as f:
            json.dump(data, f, indent=2)

    def get_history(self) -> List[MigrationRecord]:
        """Get migration history."""
        return self.history.copy()

    def get_status(self) -> Dict[str, Any]:
        """Get migration status summary."""
        current = self.get_current_version()
        target = self.get_target_version()
        pending = self.get_pending_migrations()

        return {
            "current_version": current,
            "target_version": target,
            "pending_count": len(pending),
            "pending_versions": [m.version for m in pending],
            "history_count": len(self.history),
            "last_migration": self.history[-1].version if self.history else None,
        }


# =============================================================================
# Built-in Migrations
# =============================================================================

class Migration_v1_0_0(ConfigMigration):
    """Initial configuration structure v1.0.0"""

    def __init__(self):
        super().__init__("1.0.0", "Initial configuration structure")

    def up(self, config: Dict[str, Any]) -> Dict[str, Any]:
        # Ensure all required sections exist
        required_sections = [
            "database", "redis", "model_router", "task_engine",
            "policy_engine", "voice", "memory", "automation",
            "security", "agents", "frontend", "telemetry", "events",
        ]
        for section in required_sections:
            if section not in config:
                config[section] = {}

        config["version"] = "1.0.0"
        return config

    def down(self, config: Dict[str, Any]) -> Dict[str, Any]:
        # Remove version, keep structure
        config.pop("version", None)
        return config


class Migration_v1_1_0(ConfigMigration):
    """Add feature flags and secret provider configuration v1.1.0"""

    def __init__(self):
        super().__init__("1.1.0", "Add feature flags and secret providers")

    def up(self, config: Dict[str, Any]) -> Dict[str, Any]:
        config.setdefault("feature_flags", {})
        config.setdefault("secrets", {
            "primary_provider": "windows_credential_manager",
            "fallback_providers": ["keyring", "file", "env"],
        })
        config["version"] = "1.1.0"
        return config

    def down(self, config: Dict[str, Any]) -> Dict[str, Any]:
        config.pop("feature_flags", None)
        config.pop("secrets", None)
        config["version"] = "1.0.0"
        return config


class Migration_v1_2_0(ConfigMigration):
    """Add sandbox configuration and network egress control v1.2.0"""

    def __init__(self):
        super().__init__("1.2.0", "Add sandbox and network egress config")

    def up(self, config: Dict[str, Any]) -> Dict[str, Any]:
        # Task engine sandbox config
        config.setdefault("task_engine", {}).setdefault("sandbox", {
            "enabled": True,
            "type": "docker",
            "docker_image": "arise/sandbox:latest",
            "memory_limit_mb": 512,
            "cpu_limit_percent": 50,
            "disk_limit_mb": 1024,
            "network_enabled": False,
            "timeout_seconds": 300,
        })

        # Security network egress
        config.setdefault("security", {}).setdefault("network", {
            "egress_control_enabled": True,
            "default_policy": "deny",
            "allowlist": [
                "api.openai.com",
                "api.anthropic.com",
                "generativelanguage.googleapis.com",
                "localhost",
                "127.0.0.1",
            ],
            "denylist": [],
            "dns_blocking_enabled": True,
            "proxy_interception_enabled": True,
        })

        config["version"] = "1.2.0"
        return config

    def down(self, config: Dict[str, Any]) -> Dict[str, Any]:
        config.get("task_engine", {}).pop("sandbox", None)
        config.get("security", {}).pop("network", None)
        config["version"] = "1.1.0"
        return config


# =============================================================================
# Migration Factory
# =============================================================================

def create_migrator(
    config_dir: Path,
    migrations_dir: Optional[Path] = None,
    backup_dir: Optional[Path] = None,
) -> ConfigMigrator:
    """Create a migrator with all built-in migrations registered."""
    migrator = ConfigMigrator(config_dir, migrations_dir, backup_dir)

    # Register built-in migrations in order
    migrator.register(Migration_v1_0_0())
    migrator.register(Migration_v1_1_0())
    migrator.register(Migration_v1_2_0())

    return migrator