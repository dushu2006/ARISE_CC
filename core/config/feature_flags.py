"""
ARISE Feature Flags
Feature flag system for gradual rollouts and configuration toggles.
"""

import json
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set
import logging

logger = logging.getLogger(__name__)


class FlagType(str, Enum):
    """Feature flag types."""
    BOOLEAN = "boolean"
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    JSON = "json"


class FlagStatus(str, Enum):
    """Feature flag status."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


@dataclass
class FeatureFlag:
    """Feature flag definition."""
    key: str
    name: str
    description: str
    flag_type: FlagType = FlagType.BOOLEAN
    default_value: Any = False
    status: FlagStatus = FlagStatus.ACTIVE
    tags: Set[str] = field(default_factory=set)
    rollout_percentage: int = 100  # 0-100
    targeting_rules: List[Dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    created_by: str = "system"

    def evaluate(self, context: Optional[Dict[str, Any]] = None) -> Any:
        """Evaluate the flag for a given context."""
        if self.status != FlagStatus.ACTIVE:
            return self.default_value

        # Check targeting rules
        if context and self.targeting_rules:
            for rule in self.targeting_rules:
                if self._matches_rule(context, rule):
                    return rule.get("value", self.default_value)

        # Check rollout percentage
        if self.rollout_percentage < 100:
            if context and "user_id" in context:
                user_hash = hash(context["user_id"]) % 100
                if user_hash >= self.rollout_percentage:
                    return self.default_value
            else:
                import random
                if random.randint(0, 99) >= self.rollout_percentage:
                    return self.default_value

        return self.get_typed_default()

    def get_typed_default(self) -> Any:
        """Get default value cast to the correct type."""
        if self.flag_type == FlagType.BOOLEAN:
            return bool(self.default_value)
        elif self.flag_type == FlagType.INTEGER:
            return int(self.default_value)
        elif self.flag_type == FlagType.FLOAT:
            return float(self.default_value)
        elif self.flag_type == FlagType.JSON:
            if isinstance(self.default_value, str):
                return json.loads(self.default_value)
            return self.default_value
        return self.default_value

    def _matches_rule(self, context: Dict[str, Any], rule: Dict[str, Any]) -> bool:
        """Check if context matches a targeting rule."""
        for key, expected in rule.get("conditions", {}).items():
            if key not in context:
                return False
            actual = context[key]
            if isinstance(expected, dict):
                # Operator-based matching
                for op, value in expected.items():
                    if op == "eq" and actual != value:
                        return False
                    elif op == "ne" and actual == value:
                        return False
                    elif op == "in" and actual not in value:
                        return False
                    elif op == "nin" and actual in value:
                        return False
                    elif op == "gt" and not (actual > value):
                        return False
                    elif op == "lt" and not (actual < value):
                        return False
                    elif op == "gte" and not (actual >= value):
                        return False
                    elif op == "lte" and not (actual <= value):
                        return False
                    elif op == "contains" and value not in str(actual):
                        return False
            else:
                # Exact match
                if actual != expected:
                    return False
        return True


class FlagStoreBackend(ABC):
    """Abstract backend for flag storage."""

    @abstractmethod
    def load_flags(self) -> Dict[str, FeatureFlag]:
        """Load all flags from storage."""
        pass

    @abstractmethod
    def save_flags(self, flags: Dict[str, FeatureFlag]) -> None:
        """Save all flags to storage."""
        pass

    @abstractmethod
    def get_flag(self, key: str) -> Optional[FeatureFlag]:
        """Get a single flag."""
        pass

    @abstractmethod
    def set_flag(self, flag: FeatureFlag) -> None:
        """Set a flag."""
        pass

    @abstractmethod
    def delete_flag(self, key: str) -> bool:
        """Delete a flag."""
        pass


class InMemoryFlagStore(FlagStoreBackend):
    """In-memory flag store (for testing/development)."""

    def __init__(self):
        self._flags: Dict[str, FeatureFlag] = {}
        self._lock = threading.RLock()

    def load_flags(self) -> Dict[str, FeatureFlag]:
        with self._lock:
            return self._flags.copy()

    def save_flags(self, flags: Dict[str, FeatureFlag]) -> None:
        with self._lock:
            self._flags = flags.copy()

    def get_flag(self, key: str) -> Optional[FeatureFlag]:
        with self._lock:
            return self._flags.get(key)

    def set_flag(self, flag: FeatureFlag) -> None:
        with self._lock:
            flag.updated_at = datetime.utcnow()
            self._flags[flag.key] = flag

    def delete_flag(self, key: str) -> bool:
        with self._lock:
            if key in self._flags:
                del self._flags[key]
                return True
            return False


class FileFlagStore(FlagStoreBackend):
    """File-based flag store (JSON)."""

    def __init__(self, file_path: Path):
        self.file_path = file_path
        self._lock = threading.RLock()
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.file_path.exists():
            self.file_path.write_text("{}")

    def _read_file(self) -> Dict[str, Any]:
        try:
            content = self.file_path.read_text()
            return json.loads(content) if content else {}
        except Exception:
            return {}

    def _write_file(self, data: Dict[str, Any]) -> None:
        self.file_path.write_text(json.dumps(data, indent=2, default=str))

    def load_flags(self) -> Dict[str, FeatureFlag]:
        with self._lock:
            data = self._read_file()
            flags = {}
            for key, value in data.items():
                try:
                    flags[key] = self._deserialize_flag(value)
                except Exception as e:
                    logger.warning(f"Failed to deserialize flag {key}: {e}")
            return flags

    def save_flags(self, flags: Dict[str, FeatureFlag]) -> None:
        with self._lock:
            data = {key: self._serialize_flag(flag) for key, flag in flags.items()}
            self._write_file(data)

    def get_flag(self, key: str) -> Optional[FeatureFlag]:
        with self._lock:
            data = self._read_file()
            if key in data:
                return self._deserialize_flag(data[key])
            return None

    def set_flag(self, flag: FeatureFlag) -> None:
        with self._lock:
            data = self._read_file()
            flag.updated_at = datetime.utcnow()
            data[flag.key] = self._serialize_flag(flag)
            self._write_file(data)

    def delete_flag(self, key: str) -> bool:
        with self._lock:
            data = self._read_file()
            if key in data:
                del data[key]
                self._write_file(data)
                return True
            return False

    def _serialize_flag(self, flag: FeatureFlag) -> Dict[str, Any]:
        return {
            "key": flag.key,
            "name": flag.name,
            "description": flag.description,
            "flag_type": flag.flag_type.value,
            "default_value": flag.default_value,
            "status": flag.status.value,
            "tags": list(flag.tags),
            "rollout_percentage": flag.rollout_percentage,
            "targeting_rules": flag.targeting_rules,
            "created_at": flag.created_at.isoformat(),
            "updated_at": flag.updated_at.isoformat(),
            "created_by": flag.created_by,
        }

    def _deserialize_flag(self, data: Dict[str, Any]) -> FeatureFlag:
        return FeatureFlag(
            key=data["key"],
            name=data["name"],
            description=data["description"],
            flag_type=FlagType(data["flag_type"]),
            default_value=data["default_value"],
            status=FlagStatus(data["status"]),
            tags=set(data.get("tags", [])),
            rollout_percentage=data.get("rollout_percentage", 100),
            targeting_rules=data.get("targeting_rules", []),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            created_by=data.get("created_by", "system"),
        )


class FeatureFlagStore:
    """
    Feature flag store with multiple backend support and real-time updates.
    """

    def __init__(
        self,
        backend: Optional[FlagStoreBackend] = None,
        config_file: Optional[Path] = None,
    ):
        if backend:
            self._backend = backend
        elif config_file:
            self._backend = FileFlagStore(config_file)
        else:
            self._backend = InMemoryFlagStore()

        self._flags: Dict[str, FeatureFlag] = {}
        self._listeners: Dict[str, List[Callable[[FeatureFlag, Any], None]]] = {}
        self._global_listeners: List[Callable[[str, FeatureFlag, Any], None]] = []
        self._lock = threading.RLock()
        self._load_flags()

    def _load_flags(self) -> None:
        """Load flags from backend."""
        with self._lock:
            self._flags = self._backend.load_flags()

    def reload(self) -> None:
        """Reload flags from backend."""
        self._load_flags()

    def get_flag(self, key: str) -> Optional[FeatureFlag]:
        """Get a flag by key."""
        with self._lock:
            return self._flags.get(key)

    def get_all_flags(self) -> Dict[str, FeatureFlag]:
        """Get all flags."""
        with self._lock:
            return self._flags.copy()

    def is_enabled(self, key: str, context: Optional[Dict[str, Any]] = None) -> bool:
        """Check if a boolean flag is enabled."""
        flag = self.get_flag(key)
        if not flag:
            return False
        return bool(flag.evaluate(context))

    def get_value(self, key: str, context: Optional[Dict[str, Any]] = None, default: Any = None) -> Any:
        """Get a flag value with type."""
        flag = self.get_flag(key)
        if not flag:
            return default
        return flag.evaluate(context)

    def set_flag(self, flag: FeatureFlag) -> None:
        """Create or update a flag."""
        with self._lock:
            old_flag = self._flags.get(flag.key)
            old_value = old_flag.evaluate({}) if old_flag else None

            self._backend.set_flag(flag)
            self._flags[flag.key] = flag

            new_value = flag.evaluate({})
            self._notify_listeners(flag.key, flag, old_value, new_value)

    def create_flag(
        self,
        key: str,
        name: str,
        description: str,
        flag_type: FlagType = FlagType.BOOLEAN,
        default_value: Any = False,
        tags: Optional[Set[str]] = None,
        rollout_percentage: int = 100,
        targeting_rules: Optional[List[Dict[str, Any]]] = None,
        created_by: str = "system",
    ) -> FeatureFlag:
        """Create a new feature flag."""
        flag = FeatureFlag(
            key=key,
            name=name,
            description=description,
            flag_type=flag_type,
            default_value=default_value,
            tags=tags or set(),
            rollout_percentage=rollout_percentage,
            targeting_rules=targeting_rules or [],
            created_by=created_by,
        )
        self.set_flag(flag)
        return flag

    def delete_flag(self, key: str) -> bool:
        """Delete a flag."""
        with self._lock:
            flag = self._flags.get(key)
            if not flag:
                return False

            old_value = flag.evaluate({})
            result = self._backend.delete_flag(key)
            if result:
                del self._flags[key]
                self._notify_listeners(key, flag, old_value, None)
            return result

    def update_flag(self, key: str, **kwargs) -> Optional[FeatureFlag]:
        """Update flag properties."""
        with self._lock:
            flag = self._flags.get(key)
            if not flag:
                return None

            for attr, value in kwargs.items():
                if hasattr(flag, attr):
                    setattr(flag, attr, value)

            flag.updated_at = datetime.utcnow()
            self.set_flag(flag)
            return flag

    def add_listener(self, key: str, callback: Callable[[FeatureFlag, Any], None]) -> None:
        """Add a listener for flag changes."""
        with self._lock:
            if key not in self._listeners:
                self._listeners[key] = []
            self._listeners[key].append(callback)

    def remove_listener(self, key: str, callback: Callable[[FeatureFlag, Any], None]) -> bool:
        """Remove a listener."""
        with self._lock:
            if key in self._listeners:
                try:
                    self._listeners[key].remove(callback)
                    return True
                except ValueError:
                    pass
            return False

    def add_global_listener(self, callback: Callable[[str, FeatureFlag, Any], None]) -> None:
        """Add a global listener for all flag changes."""
        with self._lock:
            self._global_listeners.append(callback)

    def remove_global_listener(self, callback: Callable[[str, FeatureFlag, Any], None]) -> bool:
        """Remove a global listener."""
        with self._lock:
            try:
                self._global_listeners.remove(callback)
                return True
            except ValueError:
                return False

    def _notify_listeners(
        self,
        key: str,
        flag: FeatureFlag,
        old_value: Any,
        new_value: Any,
    ) -> None:
        """Notify listeners of flag changes."""
        # Key-specific listeners
        for callback in self._listeners.get(key, []):
            try:
                callback(flag, new_value)
            except Exception as e:
                logger.error(f"Flag listener error for {key}: {e}")

        # Global listeners
        for callback in self._global_listeners:
            try:
                callback(key, flag, new_value)
            except Exception as e:
                logger.error(f"Global flag listener error: {e}")


# Predefined feature flags for ARISE
DEFAULT_FLAGS = [
    FeatureFlag(
        key="voice.enabled",
        name="Voice Pipeline",
        description="Enable voice wake word, ASR, and TTS",
        flag_type=FlagType.BOOLEAN,
        default_value=True,
        tags={"voice", "core"},
    ),
    FeatureFlag(
        key="voice.wake_word",
        name="Wake Word Detection",
        description="Enable Porcupine wake word detection",
        flag_type=FlagType.BOOLEAN,
        default_value=True,
        tags={"voice"},
    ),
    FeatureFlag(
        key="voice.barge_in",
        name="Barge-in Support",
        description="Allow user to interrupt TTS playback",
        flag_type=FlagType.BOOLEAN,
        default_value=True,
        tags={"voice"},
    ),
    FeatureFlag(
        key="automation.uia_enabled",
        name="UIA Automation",
        description="Enable Windows UIA backend",
        flag_type=FlagType.BOOLEAN,
        default_value=True,
        tags={"automation"},
    ),
    FeatureFlag(
        key="automation.playwright_enabled",
        name="Playwright Automation",
        description="Enable Playwright CDP backend",
        flag_type=FlagType.BOOLEAN,
        default_value=True,
        tags={"automation"},
    ),
    FeatureFlag(
        key="automation.cv_ocr_enabled",
        name="CV/OCR Automation",
        description="Enable computer vision fallback",
        flag_type=FlagType.BOOLEAN,
        default_value=True,
        tags={"automation"},
    ),
    FeatureFlag(
        key="memory.consolidation_enabled",
        name="Memory Consolidation",
        description="Enable background memory consolidation",
        flag_type=FlagType.BOOLEAN,
        default_value=True,
        tags={"memory"},
    ),
    FeatureFlag(
        key="memory.pii_detection",
        name="PII Detection",
        description="Enable PII detection in memories",
        flag_type=FlagType.BOOLEAN,
        default_value=True,
        tags={"memory", "security"},
    ),
    FeatureFlag(
        key="agents.multi_agent_enabled",
        name="Multi-Agent System",
        description="Enable multi-agent coordination",
        flag_type=FlagType.BOOLEAN,
        default_value=True,
        tags={"agents"},
    ),
    FeatureFlag(
        key="agents.verification_enabled",
        name="Agent Verification",
        description="Enable independent agent verification",
        flag_type=FlagType.BOOLEAN,
        default_value=True,
        tags={"agents"},
    ),
    FeatureFlag(
        key="security.prompt_injection_detection",
        name="Prompt Injection Detection",
        description="Enable prompt injection scanning",
        flag_type=FlagType.BOOLEAN,
        default_value=True,
        tags={"security"},
    ),
    FeatureFlag(
        key="security.network_egress_control",
        name="Network Egress Control",
        description="Enable network egress filtering",
        flag_type=FlagType.BOOLEAN,
        default_value=True,
        tags={"security"},
    ),
    FeatureFlag(
        key="model_router.privacy_mode",
        name="Model Router Privacy",
        description="Privacy mode for model routing",
        flag_type=FlagType.STRING,
        default_value="standard",
        tags={"model_router", "privacy"},
    ),
    FeatureFlag(
        key="model_router.cost_tracking",
        name="Cost Tracking",
        description="Track model usage costs",
        flag_type=FlagType.BOOLEAN,
        default_value=True,
        tags={"model_router"},
    ),
    FeatureFlag(
        key="task_engine.sandbox_enabled",
        name="Task Sandbox",
        description="Run tasks in sandboxed environment",
        flag_type=FlagType.BOOLEAN,
        default_value=True,
        tags={"task_engine"},
    ),
    FeatureFlag(
        key="policy_engine.audit_enabled",
        name="Policy Audit Logging",
        description="Enable tamper-evident audit logging",
        flag_type=FlagType.BOOLEAN,
        default_value=True,
        tags={"policy_engine", "security"},
    ),
    FeatureFlag(
        key="telemetry.enabled",
        name="Telemetry",
        description="Enable metrics and tracing",
        flag_type=FlagType.BOOLEAN,
        default_value=True,
        tags={"telemetry"},
    ),
    FeatureFlag(
        key="events.distributed_enabled",
        name="Distributed Event Bus",
        description="Enable Redis Streams event bus",
        flag_type=FlagType.BOOLEAN,
        default_value=False,
        tags={"events"},
    ),
    FeatureFlag(
        key="frontend.dark_mode",
        name="Dark Mode",
        description="Default dark mode for frontend",
        flag_type=FlagType.BOOLEAN,
        default_value=True,
        tags={"frontend"},
    ),
]


# Global feature flag store
_flag_store: Optional[FeatureFlagStore] = None


def get_flag_store(
    backend: Optional[FlagStoreBackend] = None,
    config_file: Optional[Path] = None,
) -> FeatureFlagStore:
    """Get or create the global feature flag store."""
    global _flag_store
    if _flag_store is None:
        _flag_store = FeatureFlagStore(backend, config_file)
        # Initialize default flags if store is empty
        if not _flag_store.get_all_flags():
            for flag in DEFAULT_FLAGS:
                _flag_store.set_flag(flag)
    return _flag_store


def is_enabled(key: str, context: Optional[Dict[str, Any]] = None) -> bool:
    """Check if a feature flag is enabled."""
    return get_flag_store().is_enabled(key, context)


def get_flag_value(key: str, context: Optional[Dict[str, Any]] = None, default: Any = None) -> Any:
    """Get a feature flag value."""
    return get_flag_store().get_value(key, context, default)


def create_flag(
    key: str,
    name: str,
    description: str,
    flag_type: FlagType = FlagType.BOOLEAN,
    default_value: Any = False,
    **kwargs,
) -> FeatureFlag:
    """Create a new feature flag."""
    return get_flag_store().create_flag(
        key, name, description, flag_type, default_value, **kwargs
    )