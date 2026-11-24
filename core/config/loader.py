"""
ARISE Configuration Loader
Layered configuration loading with YAML files, environment variables, and secrets.
"""

import os
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional, Type, TypeVar
from pydantic import BaseModel

from .models import (
    AppConfig,
    Settings,
    Environment,
    DatabaseConfig,
    RedisConfig,
    ModelRouterConfig,
    TaskEngineConfig,
    PolicyEngineConfig,
    VoiceConfig,
    MemoryConfig,
    AutomationConfig,
    SecurityConfig,
    AgentsConfig,
    FrontendConfig,
    TelemetryConfig,
    EventsConfig,
    settings,
)

T = TypeVar("T", bound=BaseModel)


class ConfigLoader:
    """
    Layered configuration loader supporting:
    1. Default values (lowest priority)
    2. config.default.yaml
    3. config.{environment}.yaml
    4. config.local.yaml (gitignored, highest priority)
    5. Environment variables (via Pydantic Settings)
    6. Secret providers (for sensitive values)
    """

    def __init__(
        self,
        config_dir: Optional[Path] = None,
        environment: Optional[Environment] = None,
        secrets_manager: Optional["SecretManager"] = None,
    ):
        self.config_dir = config_dir or Path(__file__).parent.parent.parent / "config"
        self.environment = environment or settings.environment
        self.secrets_manager = secrets_manager
        self._config_cache: Optional[AppConfig] = None

    def load(self, force_reload: bool = False) -> AppConfig:
        """Load the complete application configuration."""
        if self._config_cache is not None and not force_reload:
            return self._config_cache

        # Layer 1: Default configuration (from model defaults)
        config_data = self._get_default_config()

        # Layer 2: config.default.yaml
        default_file = self.config_dir / "config.default.yaml"
        if default_file.exists():
            config_data = self._merge_config(config_data, self._load_yaml(default_file))

        # Layer 3: config.{environment}.yaml
        env_file = self.config_dir / f"config.{self.environment.value}.yaml"
        if env_file.exists():
            config_data = self._merge_config(config_data, self._load_yaml(env_file))

        # Layer 4: config.local.yaml (gitignored)
        local_file = self.config_dir / "config.local.yaml"
        if local_file.exists():
            config_data = self._merge_config(config_data, self._load_yaml(local_file))

        # Layer 5: Environment variables (via Pydantic Settings)
        config_data = self._apply_env_overrides(config_data)

        # Layer 6: Secret providers (for sensitive values)
        if self.secrets_manager:
            config_data = self._apply_secrets(config_data)

        # Create final config object
        self._config_cache = AppConfig(**config_data)
        return self._config_cache

    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration from model defaults."""
        return AppConfig().model_dump()

    def _load_yaml(self, path: Path) -> Dict[str, Any]:
        """Load YAML configuration file."""
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _merge_config(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """Deep merge two configuration dictionaries."""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_config(result[key], value)
            else:
                result[key] = value
        return result

    def _apply_env_overrides(self, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """Apply environment variable overrides via Pydantic Settings."""
        # The Settings class automatically loads from environment variables
        # We just need to apply them to the config data
        env_overrides = self._extract_env_overrides()
        return self._merge_config(config_data, env_overrides)

    def _extract_env_overrides(self) -> Dict[str, Any]:
        """Extract environment variable overrides using the Settings model."""
        # Settings automatically reads from environment variables with __ delimiter
        # We convert the settings to a dict and flatten nested structures
        settings_dict = settings.model_dump()
        return self._flatten_dict(settings_dict)

    def _flatten_dict(self, d: Dict[str, Any], parent_key: str = "", sep: str = "__") -> Dict[str, Any]:
        """Flatten nested dictionary with double underscore separator."""
        items = []
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.extend(self._flatten_dict(v, new_key, sep=sep).items())
            elif v is not None:
                items.append((new_key, v))
        return dict(items)

    def _apply_secrets(self, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """Apply secrets from secret providers."""
        if not self.secrets_manager:
            return config_data

        # Get all secrets from the secret manager
        secrets = self.secrets_manager.get_all_secrets()

        # Apply secrets to config (secrets override everything)
        for key, value in secrets.items():
            self._set_nested_key(config_data, key.split("__"), value)

        return config_data

    def _set_nested_key(self, d: Dict[str, Any], keys: List[str], value: Any) -> None:
        """Set a nested key in a dictionary."""
        current = d
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        current[keys[-1]] = value

    def reload(self) -> AppConfig:
        """Force reload configuration."""
        return self.load(force_reload=True)

    def get_config_dir(self) -> Path:
        """Get the configuration directory path."""
        return self.config_dir

    def get_environment(self) -> Environment:
        """Get the current environment."""
        return self.environment


# Global config loader instance
_config_loader: Optional[ConfigLoader] = None


def get_config_loader(
    config_dir: Optional[Path] = None,
    environment: Optional[Environment] = None,
    secrets_manager: Optional["SecretManager"] = None,
) -> ConfigLoader:
    """Get or create the global config loader."""
    global _config_loader
    if _config_loader is None:
        _config_loader = ConfigLoader(config_dir, environment, secrets_manager)
    return _config_loader


def load_config(
    config_dir: Optional[Path] = None,
    environment: Optional[Environment] = None,
    secrets_manager: Optional["SecretManager"] = None,
) -> AppConfig:
    """Load the application configuration."""
    loader = get_config_loader(config_dir, environment, secrets_manager)
    return loader.load()


def reload_config() -> AppConfig:
    """Reload the application configuration."""
    global _config_loader
    if _config_loader is not None:
        return _config_loader.reload()
    return load_config()