# ARISE — Configuration Management System

## Overview

Comprehensive configuration management for ARISE with layered configuration sources, secrets management, runtime updates, validation, and migration support. Designed for the modular monolith architecture with Python, Rust, and TypeScript components.

---

## 1. Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     CONFIGURATION LAYERS                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ 1. DEFAULTS (Built-in)                                          │   │
│  │    • Sensible defaults for all settings                         │   │
│  │    • Versioned with code                                        │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│                              ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ 2. CONFIG FILES (Layered)                                       │   │
│  │    • config.default.yaml    - Committed defaults                │   │
│  │    │   config.local.yaml     - Local overrides (gitignored)     │   │
│  │    │   config.{env}.yaml     - Environment-specific             │   │
│  │    ▼                                                          │   │
│  │ 3. ENVIRONMENT VARIABLES                                        │   │
│  │    • ARISE_* prefix                                             │   │
│  │    • Override any setting                                       │   │
│  │    • Docker/K8s friendly                                        │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│                              ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ 4. SECRETS (External)                                           │   │
│  │    • Windows Credential Manager                                 │   │
│  │    • HashiCorp Vault / AWS Secrets Manager                      │   │
│  │    • 1Password / Bitwarden CLI                                  │   │
│  │    • .env.secrets (gitignored)                                  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│                              ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ 5. RUNTIME OVERRIDES (Admin API)                                │   │
│  │    • Hot-reload without restart                                 │   │
│  │    • Audit trail for changes                                    │   │
│  │    • Feature flags                                              │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Configuration Schema

### 2.1 Core Configuration Models

```python
# core/config/models.py
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Dict, List, Optional, Any, Literal
from enum import Enum
from pathlib import Path
import json


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"


class ProviderType(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    OLLAMA = "ollama"
    AZURE_OPENAI = "azure_openai"
    VERTEX_AI = "vertex_ai"


class DatabaseConfig(BaseModel):
    """Database connection configuration"""
    url: str = "sqlite+aiosqlite:///data/arise.db"
    pool_size: int = 10
    max_overflow: int = 20
    pool_timeout: float = 30.0
    pool_recycle: int = 3600
    echo: bool = False
    echo_pool: bool = False


class RedisConfig(BaseModel):
    """Redis configuration"""
    url: str = "redis://localhost:6379/0"
    max_connections: int = 50
    socket_timeout: float = 5.0
    socket_connect_timeout: float = 5.0
    decode_responses: bool = True


class ModelProviderConfig(BaseModel):
    """Single model provider configuration"""
    type: ProviderType
    api_key: Optional[str] = None  # Loaded from secrets
    base_url: Optional[str] = None
    organization: Optional[str] = None
    
    # Model defaults
    default_model: str = ""
    models: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    
    # Limits
    max_tokens: int = 4096
    timeout: float = 60.0
    max_retries: int = 3
    
    # Features
    supports_streaming: bool = True
    supports_functions: bool = True
    supports_vision: bool = False
    supports_audio: bool = False
    
    # Cost tracking
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0
    
    # Rate limiting
    rpm_limit: int = 60
    tpm_limit: int = 100000


class ModelRouterConfig(BaseModel):
    """Model router configuration"""
    providers: Dict[str, ModelProviderConfig] = Field(default_factory=dict)
    
    # Routing rules
    default_provider: str = "openai"
    fallback_chain: List[str] = Field(default_factory=list)
    
    # Task-type routing
    task_routing: Dict[str, str] = Field(default_factory=lambda: {
        "coding": "openai:gpt-4o",
        "analysis": "anthropic:claude-3.5-sonnet",
        "creative": "gemini:gemini-1.5-pro",
        "reasoning": "openai:o1-preview",
        "fast": "openai:gpt-4o-mini",
        "local": "ollama:llama3.1",
    })
    
    # Circuit breaker
    circuit_breaker:
        enabled: bool = True
        failure_threshold: int = 5
        success_threshold: int = 3
        timeout: float = 30.0
    
    # Privacy
    privacy_mode: Literal["off", "redact", "local_only"] = "off"
    pii_detection_enabled: bool = True


class TaskEngineConfig(BaseModel):
    """Task engine configuration"""
    max_concurrent_tasks: int = 10
    default_timeout: float = 300.0
    max_retries: int = 3
    retry_backoff: float = 2.0
    
    # Queue settings
    queue_size: int = 1000
    priority_levels: int = 10
    
    # Checkpointing
    checkpoint_interval: int = 5  # steps
    checkpoint_dir: str = "data/checkpoints"
    
    # Resource limits per task
    max_memory_mb: int = 512
    max_cpu_percent: float = 80.0
    max_disk_mb: int = 1024
    
    # Sandbox
    sandbox_enabled: bool = True
    sandbox_type: Literal["none", "docker", "gvisor", "firecracker"] = "docker"


class PolicyEngineConfig(BaseModel):
    """Policy engine configuration"""
    # Risk levels
    risk_levels: Dict[str, Dict[str, Any]] = Field(default_factory=lambda: {
        "R0": {"auto_approve": True, "description": "Read-only, safe"},
        "R1": {"auto_approve": True, "description": "Local write, no network"},
        "R2": {"approval_timeout": 30, "description": "Network access, file modify"},
        "R3": {"approval_timeout": 300, "description": "System modification, credentials"},
        "R4": {"approval_timeout": 3600, "require_mfa": True, "description": "Destructive, admin"},
    })
    
    # Capability grants
    grant_ttl_default: int = 3600  # 1 hour
    grant_max_ttl: int = 86400  # 24 hours
    
    # Approval UI
    approval_ui_port: int = 8080
    approval_ui_auto_open: bool = True
    
    # Audit
    audit_enabled: bool = True
    audit_retention_days: int = 90
    audit_encrypt: bool = True


class VoiceConfig(BaseModel):
    """Voice pipeline configuration"""
    # Wake word
    wake_word_enabled: bool = True
    wake_word_model: str = "hey_arise"
    wake_word_sensitivity: float = 0.5
    wake_word_audio_device: Optional[int] = None
    
    # ASR
    asr_provider: Literal["local", "gemini", "whisper", "azure"] = "local"
    asr_model: str = "sherpa-onnx-streaming-zipformer"
    asr_language: str = "en"
    asr_vad_enabled: bool = True
    asr_vad_threshold: float = 0.3
    
    # TTS
    tts_provider: Literal["local", "gemini", "elevenlabs", "azure", "coqui"] = "gemini"
    tts_voice: str = "en-US-Neural2-F"
    tts_speed: float = 1.0
    tts_sample_rate: int = 24000
    
    # Session
    session_timeout: float = 30.0
    max_session_duration: float = 3600.0
    
    # Audio
    audio_input_device: Optional[int] = None
    audio_output_device: Optional[int] = None
    audio_buffer_size: int = 4096


class MemoryConfig(BaseModel):
    """Memory system configuration"""
    # Storage
    backend: Literal["sqlite", "chromadb", "qdrant", "weaviate"] = "sqlite"
    chromadb_path: str = "data/chromadb"
    chromadb_collection_prefix: str = "arise_"
    
    # Limits per kind
    max_memories_per_kind: Dict[str, int] = Field(default_factory=lambda: {
        "semantic": 10000,
        "preference": 1000,
        "episodic": 5000,
        "procedural": 1000,
        "working": 100,
    })
    
    # Consolidation
    consolidation_enabled: bool = True
    consolidation_interval_hours: int = 6
    consolidation_min_memories: int = 50
    consolidation_model: str = "gpt-4o-mini"
    
    # Embeddings
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    embedding_batch_size: int = 100
    
    # PII
    pii_action: Literal["flag", "redact", "block"] = "flag"
    pii_detection_model: str = "presidio"
    
    # TTL
    default_ttl_days: Dict[str, int] = Field(default_factory=lambda: {
        "semantic": 365,
        "preference": 730,
        "episodic": 30,
        "procedural": 365,
        "working": 1,
    })


class AutomationConfig(BaseModel):
    """Desktop automation configuration"""
    # Perception hierarchy
    perception_order: List[str] = ["uia", "playwright", "cv_ocr"]
    
    # UIA
    uia_enabled: bool = True
    uia_timeout: float = 10.0
    uia_retry_attempts: int = 3
    
    # Playwright
    playwright_enabled: bool = True
    playwright_browser: Literal["chromium", "firefox", "webkit"] = "chromium"
    playwright_headless: bool = False
    playwright_timeout: float = 30.0
    
    # CV/OCR
    cv_enabled: bool = True
    ocr_engine: Literal["tesseract", "paddleocr", "easyocr"] = "tesseract"
    ocr_language: str = "eng"
    ocr_confidence_threshold: float = 0.7
    screenshot_dir: str = "data/screenshots"
    
    # Safety
    action_confirmation_required: bool = True
    max_actions_per_minute: int = 60
    blocked_applications: List[str] = Field(default_factory=list)
    allowed_domains: List[str] = Field(default_factory=list)


class SecurityConfig(BaseModel):
    """Security configuration"""
    # Credentials
    credential_store: Literal["windows", "keyring", "vault", "env"] = "windows"
    vault_url: Optional[str] = None
    vault_token: Optional[str] = None
    
    # Network
    network_allowlist: List[str] = Field(default_factory=lambda: [
        "api.openai.com",
        "api.anthropic.com",
        "generativelanguage.googleapis.com",
    ])
    network_denylist: List[str] = []
    egress_control_enabled: bool = True
    
    # Prompt injection
    prompt_injection_detection: bool = True
    injection_model: str = "prompguard"
    injection_threshold: float = 0.8
    
    # Audit
    audit_log_path: str = "data/audit.log"
    audit_max_size_mb: int = 100
    audit_rotation: int = 10
    
    # Encryption
    encryption_enabled: bool = True
    encryption_algorithm: str = "AES-256-GCM"
    key_rotation_days: int = 90


class AgentConfig(BaseModel):
    """Multi-agent system configuration"""
    # Coordinator
    coordinator_enabled: bool = True
    max_concurrent_agents: int = 5
    
    # Specialist agents
    specialists: Dict[str, Dict[str, Any]] = Field(default_factory=lambda: {
        "planner": {"enabled": True, "model": "gpt-4o"},
        "coder": {"enabled": True, "model": "gpt-4o"},
        "researcher": {"enabled": True, "model": "gemini-1.5-pro"},
        "analyst": {"enabled": True, "model": "claude-3.5-sonnet"},
        "creative": {"enabled": True, "model": "gpt-4o"},
        "automation": {"enabled": True, "model": "gpt-4o-mini"},
        "memory": {"enabled": True, "model": "gpt-4o-mini"},
        "security": {"enabled": True, "model": "gpt-4o-mini"},
        "reviewer": {"enabled": True, "model": "gpt-4o"},
        "communicator": {"enabled": True, "model": "gpt-4o-mini"},
        "scheduler": {"enabled": True, "model": "gpt-4o-mini"},
    })
    
    # Verification
    verification_enabled: bool = True
    verification_model: str = "gpt-4o-mini"
    max_verification_retries: int = 2
    
    # Delegation
    delegation_timeout: float = 120.0
    max_delegation_depth: int = 3


class FrontendConfig(BaseModel):
    """Frontend/UI configuration"""
    host: str = "localhost"
    port: int = 5173
    api_url: str = "http://localhost:8000"
    ws_url: str = "ws://localhost:8000/ws"
    
    # Features
    dark_mode_default: bool = True
    animations_enabled: bool = True
    compact_mode: bool = False
    
    # Notifications
    notification_duration: int = 5000
    notification_position: str = "top-right"
    
    # Voice
    voice_ui_enabled: bool = True
    wake_word_visualizer: bool = True


class TelemetryConfig(BaseModel):
    """Telemetry configuration"""
    enabled: bool = False  # Opt-in only
    endpoint: str = "https://telemetry.arise.ai"
    sample_rate: float = 0.1
    include_system_info: bool = False
    include_usage_stats: bool = False


class AppConfig(BaseSettings):
    """Main application configuration"""
    
    # Core
    app_name: str = "ARISE"
    version: str = "0.1.0"
    environment: Environment = Environment.DEVELOPMENT
    debug: bool = False
    
    # Paths
    data_dir: Path = Path("data")
    config_dir: Path = Path("config")
    log_dir: Path = Path("logs")
    temp_dir: Path = Path("tmp")
    
    # Logging
    log_level: LogLevel = LogLevel.INFO
    log_format: Literal["json", "text"] = "json"
    log_file: Optional[str] = None
    
    # Sub-configurations
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    model_router: ModelRouterConfig = Field(default_factory=ModelRouterConfig)
    task_engine: TaskEngineConfig = Field(default_factory=TaskEngineConfig)
    policy_engine: PolicyEngineConfig = Field(default_factory=PolicyEngineConfig)
    voice: VoiceConfig = Field(default_factory=VoiceConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    automation: AutomationConfig = Field(default_factory=AutomationConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    agents: AgentConfig = Field(default_factory=AgentConfig)
    frontend: FrontendConfig = Field(default_factory=FrontendConfig)
    telemetry: TelemetryConfig = Field(default_factory=TelemetryConfig)
    
    # Events
    events: "EventsConfig" = Field(default_factory=lambda: EventsConfig())
    
    model_config = SettingsConfigDict(
        env_prefix="ARISE_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    
    @model_validator(mode="after")
    def validate_paths(self):
        """Ensure directories exist"""
        for path in [self.data_dir, self.config_dir, self.log_dir, self.temp_dir]:
            path.mkdir(parents=True, exist_ok=True)
        return self
    
    def get_provider_config(self, provider_name: str) -> Optional[ModelProviderConfig]:
        """Get provider config with secrets loaded"""
        provider = self.model_router.providers.get(provider_name)
        if provider and not provider.api_key:
            # Load from secret manager
            provider.api_key = self._load_secret(f"model_provider.{provider_name}.api_key")
        return provider
    
    def _load_secret(self, key: str) -> Optional[str]:
        """Load secret from credential store"""
        # Implementation depends on security.credential_store
        return None


# Events config (separate to avoid circular import)
class EventsConfig(BaseModel):
    mode: Literal["local", "distributed", "hybrid"] = "local"
    redis_url: str = "redis://localhost:6379"
    event_store_path: str = "data/events.db"
    retention_days: int = 30
```

### 2.2 Configuration Files

```yaml
# config/config.default.yaml
# Committed to git - base configuration

app_name: "ARISE"
version: "0.1.0"
environment: "development"
debug: false

log_level: "INFO"
log_format: "json"

database:
  url: "sqlite+aiosqlite:///data/arise.db"
  pool_size: 10

redis:
  url: "redis://localhost:6379/0"

model_router:
  default_provider: "openai"
  fallback_chain: ["anthropic", "gemini", "ollama"]
  task_routing:
    coding: "openai:gpt-4o"
    analysis: "anthropic:claude-3.5-sonnet"
    creative: "gemini:gemini-1.5-pro"
    reasoning: "openai:o1-preview"
    fast: "openai:gpt-4o-mini"
    local: "ollama:llama3.1"
  
  providers:
    openai:
      type: "openai"
      default_model: "gpt-4o"
      models:
        gpt-4o:
          max_tokens: 4096
          cost_per_1k_input: 0.005
          cost_per_1k_output: 0.015
        gpt-4o-mini:
          max_tokens: 4096
          cost_per_1k_input: 0.00015
          cost_per_1k_output: 0.0006
    anthropic:
      type: "anthropic"
      default_model: "claude-3.5-sonnet"
    gemini:
      type: "gemini"
      default_model: "gemini-1.5-pro"
    ollama:
      type: "ollama"
      base_url: "http://localhost:11434"
      default_model: "llama3.1"

task_engine:
  max_concurrent_tasks: 10
  default_timeout: 300
  sandbox_enabled: true
  sandbox_type: "docker"

policy_engine:
  risk_levels:
    R0:
      auto_approve: true
    R1:
      auto_approve: true
    R2:
      approval_timeout: 30
    R3:
      approval_timeout: 300
    R4:
      approval_timeout: 3600
      require_mfa: true

voice:
  wake_word_enabled: true
  wake_word_model: "hey_arise"
  asr_provider: "local"
  tts_provider: "gemini"

memory:
  backend: "sqlite"
  consolidation_enabled: true
  pii_action: "flag"

automation:
  perception_order: ["uia", "playwright", "cv_ocr"]
  uia_enabled: true
  playwright_enabled: true
  cv_enabled: true

security:
  credential_store: "windows"
  egress_control_enabled: true
  network_allowlist:
    - "api.openai.com"
    - "api.anthropic.com"
    - "generativelanguage.googleapis.com"

agents:
  coordinator_enabled: true
  max_concurrent_agents: 5

frontend:
  host: "localhost"
  port: 5173
  api_url: "http://localhost:8000"
  dark_mode_default: true

telemetry:
  enabled: false
```

```yaml
# config/config.local.yaml
# Gitignored - local developer overrides

debug: true
log_level: "DEBUG"

database:
  url: "postgresql+asyncpg://postgres:postgres@localhost:5432/arise"

model_router:
  providers:
    openai:
      api_key: "${OPENAI_API_KEY}"  # Resolved from env/secrets
    anthropic:
      api_key: "${ANTHROPIC_API_KEY}"

voice:
  wake_word_audio_device: 1
  audio_input_device: 1
  audio_output_device: 0

automation:
  playwright_headless: false
```

```yaml
# config/config.production.yaml
# Production overrides

environment: "production"
debug: false
log_level: "WARNING"

database:
  url: "postgresql+asyncpg://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:5432/arise"
  pool_size: 20

redis:
  url: "redis://:${REDIS_PASSWORD}@${REDIS_HOST}:6379/0"
  max_connections: 100

model_router:
  privacy_mode: "redact"
  circuit_breaker:
    enabled: true

task_engine:
  sandbox_enabled: true
  sandbox_type: "gvisor"

policy_engine:
  audit_enabled: true
  audit_encrypt: true

security:
  credential_store: "vault"
  vault_url: "https://vault.company.com"
  egress_control_enabled: true
  prompt_injection_detection: true

telemetry:
  enabled: true
  sample_rate: 0.01
```

---

## 3. Configuration Loader

```python
# core/config/loader.py
import os
import yaml
import json
from pathlib import Path
from typing import Dict, Any, Optional, List, Type, TypeVar
from copy import deepcopy
import logging

from core.config.models import AppConfig, Environment

logger = logging.getLogger(__name__)

T = TypeVar('T', bound=AppConfig)

class ConfigLoader:
    """Layered configuration loader with validation"""
    
    def __init__(
        self,
        config_class: Type[T] = AppConfig,
        config_dir: Path = Path("config"),
        env_prefix: str = "ARISE_",
    ):
        self.config_class = config_class
        self.config_dir = Path(config_dir)
        self.env_prefix = env_prefix
        self._config: Optional[T] = None
        self._watchers: List[callable] = []
    
    def load(self, environment: Environment = None) -> T:
        """Load configuration from all sources"""
        # Determine environment
        if environment is None:
            environment = Environment(os.getenv(f"{self.env_prefix}ENVIRONMENT", "development"))
        
        # Layer 1: Built-in defaults (from Pydantic model)
        base_config = self.config_class()
        config_dict = base_config.model_dump()
        
        # Layer 2: Config files (layered)
        config_files = [
            self.config_dir / "config.default.yaml",
            self.config_dir / f"config.{environment.value}.yaml",
            self.config_dir / "config.local.yaml",
        ]
        
        for config_file in config_files:
            if config_file.exists():
                with open(config_file) as f:
                    file_config = yaml.safe_load(f) or {}
                config_dict = self._deep_merge(config_dict, file_config)
                logger.info(f"Loaded config from {config_file}")
        
        # Layer 3: Environment variables (handled by Pydantic Settings)
        # But we need to pre-process for nested structures
        env_overrides = self._load_env_overrides()
        config_dict = self._deep_merge(config_dict, env_overrides)
        
        # Layer 4: Secrets (loaded at runtime when accessed)
        # Secrets are not merged into config dict but loaded lazily
        
        # Create final config object
        self._config = self.config_class(**config_dict)
        
        # Validate
        self._validate(self._config)
        
        logger.info(f"Configuration loaded for environment: {environment.value}")
        return self._config
    
    def _load_env_overrides(self) -> Dict[str, Any]:
        """Load environment variable overrides"""
        overrides = {}
        prefix = self.env_prefix
        
        for key, value in os.environ.items():
            if key.startswith(prefix):
                # Convert ARISE_DATABASE__URL -> database.url
                config_key = key[len(prefix):].lower().replace("__", ".")
                
                # Parse value
                parsed_value = self._parse_env_value(value)
                
                # Set nested value
                self._set_nested(overrides, config_key, parsed_value)
        
        return overrides
    
    def _parse_env_value(self, value: str) -> Any:
        """Parse environment variable value"""
        # Try JSON first
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            pass
        
        # Boolean
        if value.lower() in ("true", "false"):
            return value.lower() == "true"
        
        # Number
        try:
            if "." in value:
                return float(value)
            return int(value)
        except ValueError:
            pass
        
        # List (comma-separated)
        if "," in value:
            return [v.strip() for v in value.split(",")]
        
        return value
    
    def _set_nested(self, d: Dict, key: str, value: Any):
        """Set nested dictionary value"""
        parts = key.split(".")
        for part in parts[:-1]:
            d = d.setdefault(part, {})
        d[parts[-1]] = value
    
    def _deep_merge(self, base: Dict, override: Dict) -> Dict:
        """Deep merge two dictionaries"""
        result = deepcopy(base)
        
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = deepcopy(value)
        
        return result
    
    def _validate(self, config: T):
        """Validate configuration"""
        # Check required secrets
        if config.environment == Environment.PRODUCTION:
            for provider_name, provider in config.model_router.providers.items():
                if provider.api_key is None:
                    logger.warning(f"Production: Provider {provider_name} has no API key")
        
        # Validate paths
        for path_name in ["data_dir", "config_dir", "log_dir", "temp_dir"]:
            path = getattr(config, path_name)
            if not path.exists():
                path.mkdir(parents=True, exist_ok=True)
    
    def get_config(self) -> T:
        """Get loaded configuration"""
        if self._config is None:
            return self.load()
        return self._config
    
    def reload(self) -> T:
        """Reload configuration"""
        old_config = self._config
        self._config = self.load()
        
        # Notify watchers
        for watcher in self._watchers:
            try:
                watcher(old_config, self._config)
            except Exception as e:
                logger.error(f"Config watcher error: {e}")
        
        return self._config
    
    def watch(self, callback: callable):
        """Register config change watcher"""
        self._watchers.append(callback)
    
    def unwatch(self, callback: callable):
        """Unregister config change watcher"""
        if callback in self._watchers:
            self._watchers.remove(callback)
    
    def export(self, format: str = "yaml", include_secrets: bool = False) -> str:
        """Export current configuration"""
        config_dict = self._config.model_dump()
        
        if not include_secrets:
            # Redact secrets
            config_dict = self._redact_secrets(config_dict)
        
        if format == "yaml":
            return yaml.dump(config_dict, default_flow_style=False, sort_keys=False)
        elif format == "json":
            return json.dumps(config_dict, indent=2, default=str)
        else:
            raise ValueError(f"Unknown format: {format}")
    
    def _redact_secrets(self, d: Dict) -> Dict:
        """Redact sensitive values"""
        result = deepcopy(d)
        secret_keys = ["api_key", "password", "secret", "token", "key"]
        
        def redact(obj, path=""):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    full_path = f"{path}.{k}" if path else k
                    if any(sk in k.lower() for sk in secret_keys):
                        obj[k] = "***REDACTED***"
                    elif isinstance(v, (dict, list)):
                        redact(v, full_path)
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    redact(v, f"{path}[{i}]")
        
        redact(result)
        return result


# Global loader instance
_loader: Optional[ConfigLoader] = None

def get_config_loader() -> ConfigLoader:
    global _loader
    if _loader is None:
        _loader = ConfigLoader()
    return _loader

def get_config() -> AppConfig:
    return get_config_loader().get_config()

async def init_config(environment: Environment = None) -> AppConfig:
    """Initialize configuration at startup"""
    loader = get_config_loader()
    config = loader.load(environment)
    
    # Ensure directories
    for path in [config.data_dir, config.config_dir, config.log_dir, config.temp_dir]:
        path.mkdir(parents=True, exist_ok=True)
    
    return config
```

---

## 4. Secrets Management

```python
# core/config/secrets.py
import os
import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from dataclasses import dataclass
from pathlib import Path
import subprocess
import json

logger = logging.getLogger(__name__)

@dataclass
class Secret:
    """Secret value with metadata"""
    key: str
    value: str
    source: str
    metadata: Dict[str, Any] = None


class SecretProvider(ABC):
    """Abstract secret provider"""
    
    @abstractmethod
    def get_secret(self, key: str) -> Optional[str]:
        pass
    
    @abstractmethod
    def set_secret(self, key: str, value: str) -> bool:
        pass
    
    @abstractmethod
    def delete_secret(self, key: str) -> bool:
        pass
    
    @abstractmethod
    def list_secrets(self, prefix: str = "") -> Dict[str, str]:
        pass


class EnvSecretProvider(SecretProvider):
    """Environment variable secret provider"""
    
    def __init__(self, prefix: str = "ARISE_SECRET_"):
        self.prefix = prefix
    
    def get_secret(self, key: str) -> Optional[str]:
        env_key = f"{self.prefix}{key.upper().replace('.', '_')}"
        return os.getenv(env_key)
    
    def set_secret(self, key: str, value: str) -> bool:
        env_key = f"{self.prefix}{key.upper().replace('.', '_')}"
        os.environ[env_key] = value
        return True
    
    def delete_secret(self, key: str) -> bool:
        env_key = f"{self.prefix}{key.upper().replace('.', '_')}"
        if env_key in os.environ:
            del os.environ[env_key]
            return True
        return False
    
    def list_secrets(self, prefix: str = "") -> Dict[str, str]:
        result = {}
        search_prefix = f"{self.prefix}{prefix.upper().replace('.', '_')}"
        for key, value in os.environ.items():
            if key.startswith(search_prefix):
                config_key = key[len(self.prefix):].lower().replace('_', '.')
                result[config_key] = value
        return result


class WindowsCredentialManager(SecretProvider):
    """Windows Credential Manager provider"""
    
    def __init__(self, target_name: str = "ARISE"):
        self.target_name = target_name
    
    def _run_cmd(self, args: list) -> tuple:
        """Run Windows cmdkey or PowerShell"""
        try:
            result = subprocess.run(args, capture_output=True, text=True, timeout=10)
            return result.returncode, result.stdout, result.stderr
        except Exception as e:
            logger.error(f"Credential manager error: {e}")
            return -1, "", str(e)
    
    def get_secret(self, key: str) -> Optional[str]:
        # Use PowerShell to get credential
        ps_script = f"""
        $cred = Get-StoredCredential -Target '{self.target_name}/{key}' -ErrorAction SilentlyContinue
        if ($cred) {{ $cred.GetNetworkCredential().Password }}
        """
        code, stdout, stderr = self._run_cmd(["powershell", "-Command", ps_script])
        if code == 0 and stdout.strip():
            return stdout.strip()
        return None
    
    def set_secret(self, key: str, value: str) -> bool:
        ps_script = f"""
        $sec = ConvertTo-SecureString '{value}' -AsPlainText -Force
        New-StoredCredential -Target '{self.target_name}/{key}' -UserName 'arise' -Password $sec -Persist LocalMachine
        """
        code, stdout, stderr = self._run_cmd(["powershell", "-Command", ps_script])
        return code == 0
    
    def delete_secret(self, key: str) -> bool:
        ps_script = f"Remove-StoredCredential -Target '{self.target_name}/{key}' -ErrorAction SilentlyContinue"
        code, stdout, stderr = self._run_cmd(["powershell", "-Command", ps_script])
        return code == 0
    
    def list_secrets(self, prefix: str = "") -> Dict[str, str]:
        ps_script = f"""
        Get-StoredCredential | Where-Object {{ $_.Target -like '{self.target_name}/{prefix}*' }} | 
        ForEach-Object {{ $_.Target + '|' + $_.GetNetworkCredential().Password }}
        """
        code, stdout, stderr = self._run_cmd(["powershell", "-Command", ps_script])
        result = {}
        if code == 0:
            for line in stdout.strip().split('\n'):
                if '|' in line:
                    target, value = line.split('|', 1)
                    key = target.replace(f'{self.target_name}/', '').replace('/', '.')
                    result[key] = value
        return result


class FileSecretProvider(SecretProvider):
    """Encrypted file-based secret provider"""
    
    def __init__(self, file_path: Path = Path(".secrets.enc"), key: str = None):
        self.file_path = Path(file_path)
        self.key = key or os.getenv("ARISE_SECRETS_KEY")
        self._cache: Dict[str, str] = {}
        self._load()
    
    def _load(self):
        if not self.file_path.exists():
            return
        
        try:
            # Decrypt file
            from cryptography.fernet import Fernet
            key = self.key.encode() if isinstance(self.key, str) else self.key
            fernet = Fernet(key)
            
            with open(self.file_path, 'rb') as f:
                encrypted = f.read()
            
            decrypted = fernet.decrypt(encrypted)
            self._cache = json.loads(decrypted)
        except Exception as e:
            logger.error(f"Failed to load secrets: {e}")
    
    def _save(self):
        try:
            from cryptography.fernet import Fernet
            key = self.key.encode() if isinstance(self.key, str) else self.key
            fernet = Fernet(key)
            
            encrypted = fernet.encrypt(json.dumps(self._cache).encode())
            
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.file_path, 'wb') as f:
                f.write(encrypted)
        except Exception as e:
            logger.error(f"Failed to save secrets: {e}")
    
    def get_secret(self, key: str) -> Optional[str]:
        return self._cache.get(key)
    
    def set_secret(self, key: str, value: str) -> bool:
        self._cache[key] = value
        self._save()
        return True
    
    def delete_secret(self, key: str) -> bool:
        if key in self._cache:
            del self._cache[key]
            self._save()
            return True
        return False
    
    def list_secrets(self, prefix: str = "") -> Dict[str, str]:
        if prefix:
            return {k: v for k, v in self._cache.items() if k.startswith(prefix)}
        return dict(self._cache)


class VaultSecretProvider(SecretProvider):
    """HashiCorp Vault secret provider"""
    
    def __init__(self, url: str, token: str, mount_point: str = "secret"):
        self.url = url.rstrip('/')
        self.token = token
        self.mount_point = mount_point
        self._session = None
    
    async def _get_session(self):
        if self._session is None:
            import aiohttp
            self._session = aiohttp.ClientSession(
                headers={"X-Vault-Token": self.token}
            )
        return self._session
    
    async def get_secret(self, key: str) -> Optional[str]:
        session = await self._get_session()
        path = key.replace('.', '/')
        url = f"{self.url}/v1/{self.mount_point}/data/{path}"
        
        async with session.get(url) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get('data', {}).get('data', {}).get('value')
            elif resp.status == 404:
                return None
            else:
                logger.error(f"Vault error: {resp.status}")
                return None
    
    async def set_secret(self, key: str, value: str) -> bool:
        session = await self._get_session()
        path = key.replace('.', '/')
        url = f"{self.url}/v1/{self.mount_point}/data/{path}"
        
        async with session.post(url, json={"data": {"value": value}}) as resp:
            return resp.status in (200, 204)
    
    async def delete_secret(self, key: str) -> bool:
        session = await self._get_session()
        path = key.replace('.', '/')
        url = f"{self.url}/v1/{self.mount_point}/data/{path}"
        
        async with session.delete(url) as resp:
            return resp.status in (200, 204)
    
    async def list_secrets(self, prefix: str = "") -> Dict[str, str]:
        session = await self._get_session()
        path = prefix.replace('.', '/')
        url = f"{self.url}/v1/{self.mount_point}/metadata/{path}?list=true"
        
        async with session.get(url) as resp:
            if resp.status == 200:
                data = await resp.json()
                keys = data.get('data', {}).get('keys', [])
                result = {}
                for key in keys:
                    full_key = f"{prefix}.{key}" if prefix else key
                    value = await self.get_secret(full_key)
                    if value:
                        result[full_key] = value
                return result
            return {}


class SecretManager:
    """Unified secret management"""
    
    def __init__(self):
        self.providers: list[SecretProvider] = []
        self._cache: Dict[str, Secret] = {}
    
    def add_provider(self, provider: SecretProvider, priority: int = 0):
        """Add secret provider with priority (higher = checked first)"""
        self.providers.append((priority, provider))
        self.providers.sort(key=lambda x: -x[0])
    
    def get_secret(self, key: str, default: str = None) -> Optional[str]:
        """Get secret from first provider that has it"""
        # Check cache
        if key in self._cache:
            return self._cache[key].value
        
        # Check providers
        for _, provider in self.providers:
            try:
                value = provider.get_secret(key)
                if value is not None:
                    secret = Secret(key=key, value=value, source=provider.__class__.__name__)
                    self._cache[key] = secret
                    return value
            except Exception as e:
                logger.debug(f"Provider {provider.__class__.__name__} failed for {key}: {e}")
        
        return default
    
    def set_secret(self, key: str, value: str) -> bool:
        """Set secret in all providers"""
        success = False
        for _, provider in self.providers:
            try:
                if provider.set_secret(key, value):
                    success = True
                    # Update cache
                    self._cache[key] = Secret(key=key, value=value, source=provider.__class__.__name__)
            except Exception as e:
                logger.error(f"Failed to set secret in {provider.__class__.__name__}: {e}")
        return success
    
    def delete_secret(self, key: str) -> bool:
        """Delete secret from all providers"""
        success = False
        for _, provider in self.providers:
            try:
                if provider.delete_secret(key):
                    success = True
            except Exception as e:
                logger.error(f"Failed to delete secret in {provider.__class__.__name__}: {e}")
        
        if key in self._cache:
            del self._cache[key]
        return success
    
    def list_secrets(self, prefix: str = "") -> Dict[str, str]:
        """List all secrets"""
        result = {}
        for _, provider in self.providers:
            try:
                secrets = provider.list_secrets(prefix)
                for k, v in secrets.items():
                    if k not in result:  # First provider wins
                        result[k] = v
            except Exception as e:
                logger.error(f"Failed to list secrets in {provider.__class__.__name__}: {e}")
        return result
    
    def clear_cache(self):
        self._cache.clear()


# Global secret manager
_secret_manager: Optional[SecretManager] = None

def get_secret_manager() -> SecretManager:
    global _secret_manager
    if _secret_manager is None:
        _secret_manager = SecretManager()
        # Add default providers
        _secret_manager.add_provider(EnvSecretProvider(), priority=100)
        _secret_manager.add_provider(WindowsCredentialManager(), priority=50)
        # File provider if key exists
        if os.getenv("ARISE_SECRETS_KEY"):
            _secret_manager.add_provider(FileSecretProvider(), priority=10)
    return _secret_manager
```

---

## 5. Runtime Configuration API

```python
# core/runtime/config_api.py
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
import logging

from core.config.loader import get_config_loader, ConfigLoader
from core.config.models import AppConfig, Environment
from core.config.secrets import get_secret_manager
from core.security import require_capability

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/config", tags=["configuration"])

# Request/Response models

class ConfigValue(BaseModel):
    path: str
    value: Any
    source: str

class ConfigUpdateRequest(BaseModel):
    updates: Dict[str, Any] = Field(..., description="Dot-notation path to value")
    reason: str = Field("", description="Reason for change")
    persist: bool = Field(False, description="Persist to config.local.yaml")

class ConfigUpdateResponse(BaseModel):
    success: bool
    updated: List[str]
    failed: List[Dict[str, str]]
    requires_restart: List[str]

class SecretRequest(BaseModel):
    key: str
    value: str

class SecretResponse(BaseModel):
    key: str
    value: str
    source: str

class ConfigExportRequest(BaseModel):
    format: str = "yaml"
    include_secrets: bool = False

# Endpoints

@router.get("", response_model=Dict[str, Any])
async def get_config(
    include_secrets: bool = False,
    loader: ConfigLoader = Depends(get_config_loader),
):
    """Get current configuration"""
    config = loader.get_config()
    config_dict = config.model_dump()
    
    if not include_secrets:
        config_dict = loader._redact_secrets(config_dict)
    
    return config_dict

@router.get("/{path:path}", response_model=ConfigValue)
async def get_config_value(
    path: str,
    loader: ConfigLoader = Depends(get_config_loader),
):
    """Get specific configuration value by dot-notation path"""
    config = loader.get_config()
    
    try:
        value = _get_nested(config.model_dump(), path)
        return ConfigValue(path=path, value=value, source="config")
    except KeyError:
        raise HTTPException(404, f"Config path not found: {path}")

@router.patch("", response_model=ConfigUpdateResponse)
async def update_config(
    request: ConfigUpdateRequest,
    background_tasks: BackgroundTasks,
    loader: ConfigLoader = Depends(get_config_loader),
    _: None = Depends(require_capability("config.write")),
):
    """Update configuration at runtime"""
    config = loader.get_config()
    updated = []
    failed = []
    requires_restart = []
    
    # Paths that require restart
    restart_paths = {
        "database.url",
        "redis.url",
        "model_router.default_provider",
        "task_engine.sandbox_type",
        "security.credential_store",
        "voice.asr_provider",
        "voice.tts_provider",
    }
    
    for path, value in request.updates.items():
        try:
            # Validate path exists
            _get_nested(config.model_dump(), path)
            
            # Apply update
            _set_nested(config.__dict__, path, value)
            updated.append(path)
            
            if path in restart_paths:
                requires_restart.append(path)
                
        except KeyError:
            failed.append({"path": path, "error": "Path not found"})
        except Exception as e:
            failed.append({"path": path, "error": str(e)})
    
    # Persist if requested
    if request.persist and updated:
        background_tasks.add_task(_persist_config, loader, request.updates)
    
    # Notify watchers
    loader.reload()
    
    return ConfigUpdateResponse(
        success=len(failed) == 0,
        updated=updated,
        failed=failed,
        requires_restart=requires_restart,
    )

@router.post("/secrets", response_model=SecretResponse)
async def set_secret(
    request: SecretRequest,
    _: None = Depends(require_capability("secrets.write")),
):
    """Store a secret"""
    manager = get_secret_manager()
    success = manager.set_secret(request.key, request.value)
    
    if not success:
        raise HTTPException(500, "Failed to store secret")
    
    return SecretResponse(
        key=request.key,
        value="***SET***",
        source=manager.providers[0][1].__class__.__name__,
    )

@router.get("/secrets/{key}", response_model=SecretResponse)
async def get_secret(
    key: str,
    _: None = Depends(require_capability("secrets.read")),
):
    """Retrieve a secret"""
    manager = get_secret_manager()
    value = manager.get_secret(key)
    
    if value is None:
        raise HTTPException(404, f"Secret not found: {key}")
    
    # Find source
    for _, provider in manager.providers:
        if provider.get_secret(key) is not None:
            source = provider.__class__.__name__
            break
    else:
        source = "unknown"
    
    return SecretResponse(key=key, value=value, source=source)

@router.delete("/secrets/{key}")
async def delete_secret(
    key: str,
    _: None = Depends(require_capability("secrets.write")),
):
    """Delete a secret"""
    manager = get_secret_manager()
    success = manager.delete_secret(key)
    
    if not success:
        raise HTTPException(404, f"Secret not found: {key}")
    
    return {"success": True, "key": key}

@router.get("/secrets", response_model=Dict[str, str])
async def list_secrets(
    prefix: str = "",
    _: None = Depends(require_capability("secrets.list")),
):
    """List secret keys (values redacted)"""
    manager = get_secret_manager()
    secrets = manager.list_secrets(prefix)
    return {k: "***" for k in secrets.keys()}

@router.post("/export")
async def export_config(
    request: ConfigExportRequest,
    loader: ConfigLoader = Depends(get_config_loader),
    _: None = Depends(require_capability("config.read")),
):
    """Export configuration"""
    content = loader.export(request.format, request.include_secrets)
    
    from fastapi.responses import Response
    media_type = "application/x-yaml" if request.format == "yaml" else "application/json"
    return Response(content=content, media_type=media_type)

@router.post("/reload")
async def reload_config(
    loader: ConfigLoader = Depends(get_config_loader),
    _: None = Depends(require_capability("config.write")),
):
    """Force configuration reload"""
    config = loader.reload()
    return {"success": True, "environment": config.environment.value}

@router.get("/schema")
async def get_config_schema():
    """Get configuration JSON schema"""
    from core.config.models import AppConfig
    return AppConfig.model_json_schema()

# Helper functions

def _get_nested(obj: Dict, path: str) -> Any:
    """Get nested value by dot-notation path"""
    parts = path.split(".")
    for part in parts:
        if isinstance(obj, dict):
            obj = obj[part]
        elif hasattr(obj, part):
            obj = getattr(obj, part)
        else:
            raise KeyError(path)
    return obj

def _set_nested(obj: Any, path: str, value: Any):
    """Set nested value by dot-notation path"""
    parts = path.split(".")
    for part in parts[:-1]:
        if isinstance(obj, dict):
            obj = obj[part]
        else:
            obj = getattr(obj, part)
    
    last = parts[-1]
    if isinstance(obj, dict):
        obj[last] = value
    else:
        setattr(obj, last, value)

async def _persist_config(loader: ConfigLoader, updates: Dict[str, Any]):
    """Persist config updates to config.local.yaml"""
    local_path = loader.config_dir / "config.local.yaml"
    
    # Load existing
    existing = {}
    if local_path.exists():
        import yaml
        with open(local_path) as f:
            existing = yaml.safe_load(f) or {}
    
    # Merge updates
    for path, value in updates.items():
        _set_nested(existing, path, value)
    
    # Write back
    import yaml
    with open(local_path, 'w') as f:
        yaml.dump(existing, f, default_flow_style=False, sort_keys=False)
    
    logger.info(f"Persisted config updates to {local_path}")
```

---

## 6. Feature Flags

```python
# core/config/feature_flags.py
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Callable, Awaitable
from enum import Enum
import logging

logger = logging.getLogger(__name__)

class FlagType(Enum):
    BOOLEAN = "boolean"
    STRING = "string"
    NUMBER = "number"
    JSON = "json"

@dataclass
class FeatureFlag:
    """Feature flag definition"""
    key: str
    name: str
    description: str
    flag_type: FlagType = FlagType.BOOLEAN
    default_value: Any = False
    value: Any = None
    enabled: bool = True
    rollout_percentage: float = 100.0  # 0-100
    targeting_rules: list = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def evaluate(self, context: Dict[str, Any] = None) -> Any:
        """Evaluate flag for context"""
        if not self.enabled:
            return self.default_value
        
        # Check targeting rules
        if context and self.targeting_rules:
            for rule in self.targeting_rules:
                if self._match_rule(rule, context):
                    return rule.get("value", self.value)
        
        # Check rollout
        if self.rollout_percentage < 100:
            user_id = context.get("user_id", "") if context else ""
            if not self._in_rollout(user_id):
                return self.default_value
        
        return self.value if self.value is not None else self.default_value
    
    def _match_rule(self, rule: Dict, context: Dict) -> bool:
        """Check if targeting rule matches"""
        # Simple implementation - extend as needed
        for key, expected in rule.get("conditions", {}).items():
            if context.get(key) != expected:
                return False
        return True
    
    def _in_rollout(self, user_id: str) -> bool:
        """Deterministic rollout check"""
        import hashlib
        hash_val = int(hashlib.md5(f"{self.key}:{user_id}".encode()).hexdigest(), 16)
        return (hash_val % 100) < self.rollout_percentage


class FeatureFlagStore:
    """Feature flag management"""
    
    def __init__(self):
        self.flags: Dict[str, FeatureFlag] = {}
        self._evaluators: Dict[str, Callable] = {}
    
    def register(self, flag: FeatureFlag):
        """Register a feature flag"""
        self.flags[flag.key] = flag
        logger.info(f"Registered feature flag: {flag.key}")
    
    def unregister(self, key: str):
        """Unregister a feature flag"""
        self.flags.pop(key, None)
    
    def get(self, key: str) -> Optional[FeatureFlag]:
        return self.flags.get(key)
    
    def is_enabled(self, key: str, context: Dict = None) -> bool:
        """Check if boolean flag is enabled"""
        flag = self.flags.get(key)
        if not flag:
            return False
        return bool(flag.evaluate(context))
    
    def get_value(self, key: str, context: Dict = None, default: Any = None) -> Any:
        """Get flag value"""
        flag = self.flags.get(key)
        if not flag:
            return default
        return flag.evaluate(context)
    
    def set_value(self, key: str, value: Any):
        """Override flag value at runtime"""
        flag = self.flags.get(key)
        if flag:
            flag.value = value
            logger.info(f"Feature flag {key} set to {value}")
    
    def set_rollout(self, key: str, percentage: float):
        """Set rollout percentage"""
        flag = self.flags.get(key)
        if flag:
            flag.rollout_percentage = max(0, min(100, percentage))
    
    def list_flags(self) -> Dict[str, Dict]:
        """List all flags with current values"""
        return {
            key: {
                "name": flag.name,
                "description": flag.description,
                "type": flag.flag_type.value,
                "enabled": flag.enabled,
                "value": flag.value,
                "default": flag.default_value,
                "rollout": flag.rollout_percentage,
            }
            for key, flag in self.flags.items()
        }
    
    def register_evaluator(self, key: str, evaluator: Callable[[Dict], Any]):
        """Register custom evaluator for flag"""
        self._evaluators[key] = evaluator


# Built-in ARISE feature flags
DEFAULT_FLAGS = {
    "voice.enabled": FeatureFlag(
        key="voice.enabled",
        name="Voice Pipeline",
        description="Enable voice wake word and conversation",
        flag_type=FlagType.BOOLEAN,
        default_value=True,
    ),
    "voice.gemini_live": FeatureFlag(
        key="voice.gemini_live",
        name="Gemini Live API",
        description="Use Gemini Live for voice conversations",
        flag_type=FlagType.BOOLEAN,
        default_value=False,
        rollout_percentage=50,
    ),
    "agents.multi_agent": FeatureFlag(
        key="agents.multi_agent",
        name="Multi-Agent System",
        description="Enable specialist agent delegation",
        flag_type=FlagType.BOOLEAN,
        default_value=True,
    ),
    "automation.playwright": FeatureFlag(
        key="automation.playwright",
        name="Playwright Automation",
        description="Enable Playwright-based web automation",
        flag_type=FlagType.BOOLEAN,
        default_value=True,
    ),
    "memory.consolidation": FeatureFlag(
        key="memory.consolidation",
        name="Memory Consolidation",
        description="Enable automatic memory consolidation",
        flag_type=FlagType.BOOLEAN,
        default_value=True,
    ),
    "security.prompt_injection": FeatureFlag(
        key="security.prompt_injection",
        name="Prompt Injection Detection",
        description="Enable prompt injection detection",
        flag_type=FlagType.BOOLEAN,
        default_value=True,
    ),
    "telemetry.enabled": FeatureFlag(
        key="telemetry.enabled",
        name="Telemetry Collection",
        description="Enable anonymous usage telemetry",
        flag_type=FlagType.BOOLEAN,
        default_value=False,
    ),
    "experimental.cv_ocr": FeatureFlag(
        key="experimental.cv_ocr",
        name="CV/OCR Automation",
        description="Enable computer vision fallback (experimental)",
        flag_type=FlagType.BOOLEAN,
        default_value=False,
    ),
}


# Global feature flag store
_feature_flags: Optional[FeatureFlagStore] = None

def get_feature_flags() -> FeatureFlagStore:
    global _feature_flags
    if _feature_flags is None:
        _feature_flags = FeatureFlagStore()
        for flag in DEFAULT_FLAGS.values():
            _feature_flags.register(flag)
    return _feature_flags

def is_feature_enabled(key: str, context: Dict = None) -> bool:
    return get_feature_flags().is_enabled(key, context)

def get_feature_value(key: str, context: Dict = None, default: Any = None) -> Any:
    return get_feature_flags().get_value(key, context, default)
```

---

## 7. Configuration Migration

```python
# core/config/migration.py
from typing import Dict, Any, List, Callable
from dataclasses import dataclass
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

@dataclass
class Migration:
    """Configuration migration"""
    version: str
    description: str
    up: Callable[[Dict], Dict]
    down: Callable[[Dict], Dict] = None


class ConfigMigrator:
    """Handle configuration version migrations"""
    
    def __init__(self):
        self.migrations: List[Migration] = []
        self.current_version = "1.0.0"
    
    def add_migration(self, migration: Migration):
        self.migrations.append(migration)
        self.migrations.sort(key=lambda m: m.version)
    
    def migrate(self, config: Dict, target_version: str = None) -> Dict:
        """Migrate config to target version"""
        target = target_version or self.current_version
        current = config.get("_meta", {}).get("version", "0.0.0")
        
        if current == target:
            return config
        
        # Find migrations to apply
        to_apply = [m for m in self.migrations if m.version > current and m.version <= target]
        
        for migration in to_apply:
            logger.info(f"Applying migration {migration.version}: {migration.description}")
            config = migration.up(config)
            config.setdefault("_meta", {})["version"] = migration.version
        
        return config
    
    def rollback(self, config: Dict, target_version: str) -> Dict:
        """Rollback config to target version"""
        current = config.get("_meta", {}).get("version", "0.0.0")
        
        if current == target_version:
            return config
        
        # Find migrations to reverse
        to_reverse = [m for m in self.migrations if m.version <= current and m.version > target_version]
        to_reverse.reverse()
        
        for migration in to_reverse:
            if migration.down is None:
                logger.warning(f"Migration {migration.version} cannot be rolled back")
                continue
            
            logger.info(f"Rolling back migration {migration.version}: {migration.description}")
            config = migration.down(config)
            config.setdefault("_meta", {})["version"] = migration.version
        
        return config


# Migration definitions
MIGRATIONS = ConfigMigrator()

# v1.1.0: Rename model_router.providers.openai.api_key to use secret reference
MIGRATIONS.add_migration(Migration(
    version="1.1.0",
    description="Move API keys to secret references",
    up=lambda c: _migrate_api_keys_to_secrets(c),
    down=lambda c: _migrate_secrets_to_api_keys(c),
))

def _migrate_api_keys_to_secrets(config: Dict) -> Dict:
    """Move plaintext API keys to secret manager"""
    providers = config.get("model_router", {}).get("providers", {})
    for name, provider in providers.items():
        if "api_key" in provider and provider["api_key"] and not provider["api_key"].startswith("${"):
            # Store in secret manager
            from core.config.secrets import get_secret_manager
            manager = get_secret_manager()
            manager.set_secret(f"model_provider.{name}.api_key", provider["api_key"])
            # Replace with reference
            provider["api_key"] = f"${{model_provider.{name}.api_key}}"
    return config

def _migrate_secrets_to_api_keys(config: Dict) -> Dict:
    """Restore API keys from secret manager (for rollback)"""
    providers = config.get("model_router", {}).get("providers", {})
    for name, provider in providers.items():
        if "api_key" in provider and provider["api_key"].startswith("${"):
            key = provider["api_key"][2:-1]  # Remove ${}
            from core.config.secrets import get_secret_manager
            manager = get_secret_manager()
            value = manager.get_secret(key)
            if value:
                provider["api_key"] = value
    return config

# v1.2.0: Add new voice settings
MIGRATIONS.add_migration(Migration(
    version="1.2.0",
    description="Add voice session settings",
    up=lambda c: _add_voice_session_settings(c),
    down=lambda c: _remove_voice_session_settings(c),
))

def _add_voice_session_settings(config: Dict) -> Dict:
    voice = config.setdefault("voice", {})
    voice.setdefault("session_timeout", 30.0)
    voice.setdefault("max_session_duration", 3600.0)
    return config

def _remove_voice_session_settings(config: Dict) -> Dict:
    voice = config.get("voice", {})
    voice.pop("session_timeout", None)
    voice.pop("max_session_duration", None)
    return config

# v1.3.0: Restructure memory config
MIGRATIONS.add_migration(Migration(
    version="1.3.0",
    description="Restructure memory configuration",
    up=lambda c: _restructure_memory_config(c),
    down=lambda c: _restore_memory_config(c),
))

def _restructure_memory_config(config: Dict) -> Dict:
    memory = config.get("memory", {})
    # Move max_memories to per-kind dict
    if "max_memories" in memory:
        old_max = memory.pop("max_memories")
        memory.setdefault("max_memories_per_kind", {})["semantic"] = old_max
    return config

def _restore_memory_config(config: Dict) -> Dict:
    memory = config.get("memory", {})
    per_kind = memory.get("max_memories_per_kind", {})
    if "semantic" in per_kind:
        memory["max_memories"] = per_kind["semantic"]
    return config
```

---

## 8. TypeScript Configuration (Frontend)

```typescript
// src/config/index.ts
import { z } from 'zod';

// Environment detection
const isDev = import.meta.env.DEV;
const isProd = import.meta.env.PROD;

// Configuration schema
const ConfigSchema = z.object({
  app: z.object({
    name: z.string().default('ARISE'),
    version: z.string().default('0.1.0'),
    environment: z.enum(['development', 'staging', 'production', 'test']),
    debug: z.boolean().default(false),
  }),
  
  api: z.object({
    baseUrl: z.string().url().default('http://localhost:8000'),
    wsUrl: z.string().url().default('ws://localhost:8000/ws'),
    timeout: z.number().default(30000),
  }),
  
  ui: z.object({
    theme: z.enum(['light', 'dark', 'system']).default('dark'),
    animations: z.boolean().default(true),
    compactMode: z.boolean().default(false),
    language: z.string().default('en'),
  }),
  
  voice: z.object({
    enabled: z.boolean().default(true),
    wakeWordVisualizer: z.boolean().default(true),
    autoStart: z.boolean().default(false),
  }),
  
  features: z.object({
    multiAgent: z.boolean().default(true),
    voice: z.boolean().default(true),
    automation: z.boolean().default(true),
    memory: z.boolean().default(true),
    telemetry: z.boolean().default(false),
  }),
  
  notifications: z.object({
    duration: z.number().default(5000),
    position: z.enum(['top-left', 'top-right', 'bottom-left', 'bottom-right']).default('top-right'),
    sound: z.boolean().default(false),
  }),
});

export type AppConfig = z.infer<typeof ConfigSchema>;

// Default configuration
const defaultConfig: AppConfig = {
  app: {
    name: 'ARISE',
    version: '0.1.0',
    environment: isDev ? 'development' : 'production',
    debug: isDev,
  },
  api: {
    baseUrl: import.meta.env.VITE_API_URL || 'http://localhost:8000',
    wsUrl: import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws',
    timeout: 30000,
  },
  ui: {
    theme: 'dark',
    animations: true,
    compactMode: false,
    language: 'en',
  },
  voice: {
    enabled: true,
    wakeWordVisualizer: true,
    autoStart: false,
  },
  features: {
    multiAgent: true,
    voice: true,
    automation: true,
    memory: true,
    telemetry: false,
  },
  notifications: {
    duration: 5000,
    position: 'top-right',
    sound: false,
  },
};

// Configuration store
class ConfigStore {
  private config: AppConfig = defaultConfig;
  private listeners: Set<(config: AppConfig) => void> = new Set();
  
  constructor() {
    this.loadFromStorage();
    this.loadFromEnv();
  }
  
  private loadFromStorage() {
    try {
      const stored = localStorage.getItem('arise_config');
      if (stored) {
        const parsed = JSON.parse(stored);
        this.config = ConfigSchema.parse({ ...defaultConfig, ...parsed });
      }
    } catch (e) {
      console.warn('Failed to load config from storage:', e);
    }
  }
  
  private loadFromEnv() {
    // Override from Vite env vars
    if (import.meta.env.VITE_API_URL) {
      this.config.api.baseUrl = import.meta.env.VITE_API_URL;
    }
    if (import.meta.env.VITE_WS_URL) {
      this.config.api.wsUrl = import.meta.env.VITE_WS_URL;
    }
  }
  
  get(): AppConfig {
    return this.config;
  }
  
  getK<K extends keyof AppConfig>(key: K): AppConfig[K] {
    return this.config[key];
  }
  
  set<K extends keyof AppConfig>(key: K, value: AppConfig[K]) {
    this.config = { ...this.config, [key]: value };
    this.persist();
    this.notify();
  }
  
  update(partial: Partial<AppConfig>) {
    this.config = ConfigSchema.parse({ ...this.config, ...partial });
    this.persist();
    this.notify();
  }
  
  private persist() {
    try {
      localStorage.setItem('arise_config', JSON.stringify(this.config));
    } catch (e) {
      console.warn('Failed to persist config:', e);
    }
  }
  
  private notify() {
    this.listeners.forEach(fn => fn(this.config));
  }
  
  subscribe(listener: (config: AppConfig) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }
  
  // Feature flags
  isFeatureEnabled(flag: keyof AppConfig['features']): boolean {
    return this.config.features[flag];
  }
  
  setFeatureFlag(flag: keyof AppConfig['features'], enabled: boolean) {
    this.config.features[flag] = enabled;
    this.persist();
    this.notify();
  }
}

// Singleton instance
export const config = new ConfigStore();

// React hook
import { useSyncExternalStore } from 'react';

export function useConfig<K extends keyof AppConfig>(key?: K) {
  const snapshot = useSyncExternalStore(
    config.subscribe.bind(config),
    () => key ? config.getK(key) : config.get(),
    () => key ? defaultConfig[key as K] : defaultConfig
  );
  return snapshot;
}

export function useFeatureFlag(flag: keyof AppConfig['features']) {
  return useSyncExternalStore(
    config.subscribe.bind(config),
    () => config.isFeatureEnabled(flag),
    () => defaultConfig.features[flag]
  );
}
```

---

## 9. Rust Configuration (Tauri)

```rust
// src-tauri/src/config.rs
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::PathBuf;
use directories::ProjectDirs;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AppConfig {
    pub app: AppInfo,
    pub paths: PathsConfig,
    pub window: WindowConfig,
    pub tray: TrayConfig,
    pub updater: UpdaterConfig,
    pub security: SecurityConfig,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AppInfo {
    pub name: String,
    pub version: String,
    pub author: String,
    pub homepage: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PathsConfig {
    pub data_dir: PathBuf,
    pub config_dir: PathBuf,
    pub cache_dir: PathBuf,
    pub log_dir: PathBuf,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WindowConfig {
    pub width: f64,
    pub height: f64,
    pub min_width: f64,
    pub min_height: f64,
    pub title: String,
    pub decorations: bool,
    pub transparent: bool,
    pub always_on_top: bool,
    pub visible_on_all_workspaces: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TrayConfig {
    pub enabled: bool,
    pub icon: String,
    pub menu_items: Vec<TrayMenuItem>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TrayMenuItem {
    pub id: String,
    pub label: String,
    pub action: String,
    pub accelerator: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UpdaterConfig {
    pub enabled: bool,
    pub endpoint: String,
    pub check_interval_hours: u32,
    pub auto_download: bool,
    pub auto_install: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SecurityConfig {
    pub capability_allowlist: Vec<String>,
    pub protocol_allowlist: Vec<String>,
    pub csp: String,
}

impl Default for AppConfig {
    fn default() -> Self {
        let dirs = ProjectDirs::from("com", "arise", "ARISE").unwrap();
        
        Self {
            app: AppInfo {
                name: "ARISE".to_string(),
                version: env!("CARGO_PKG_VERSION").to_string(),
                author: "ARISE Team".to_string(),
                homepage: "https://arise.ai".to_string(),
            },
            paths: PathsConfig {
                data_dir: dirs.data_dir().to_path_buf(),
                config_dir: dirs.config_dir().to_path_buf(),
                cache_dir: dirs.cache_dir().to_path_buf(),
                log_dir: dirs.data_dir().join("logs"),
            },
            window: WindowConfig {
                width: 1200.0,
                height: 800.0,
                min_width: 800.0,
                min_height: 600.0,
                title: "ARISE".to_string(),
                decorations: false,
                transparent: true,
                always_on_top: false,
                visible_on_all_workspaces: false,
            },
            tray: TrayConfig {
                enabled: true,
                icon: "tray-icon.png".to_string(),
                menu_items: vec![
                    TrayMenuItem {
                        id: "show".to_string(),
                        label: "Show ARISE".to_string(),
                        action: "show".to_string(),
                        accelerator: Some("CommandOrControl+Shift+A".to_string()),
                    },
                    TrayMenuItem {
                        id: "voice".to_string(),
                        label: "Toggle Voice".to_string(),
                        action: "toggle_voice".to_string(),
                        accelerator: Some("CommandOrControl+Shift+V".to_string()),
                    },
                    TrayMenuItem {
                        id: "quit".to_string(),
                        label: "Quit".to_string(),
                        action: "quit".to_string(),
                        accelerator: None,
                    },
                ],
            },
            updater: UpdaterConfig {
                enabled: true,
                endpoint: "https://updates.arise.ai".to_string(),
                check_interval_hours: 4,
                auto_download: true,
                auto_install: false,
            },
            security: SecurityConfig {
                capability_allowlist: vec![
                    "shell.exec".to_string(),
                    "filesystem.read".to_string(),
                    "filesystem.write".to_string(),
                    "window.manage".to_string(),
                ],
                protocol_allowlist: vec![
                    "https:".to_string(),
                    "wss:".to_string(),
                ],
                csp: "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; connect-src 'self' https: wss:;".to_string(),
            },
        }
    }
}

impl AppConfig {
    pub fn load() -> Result<Self, ConfigError> {
        let dirs = ProjectDirs::from("com", "arise", "ARISE").unwrap();
        let config_path = dirs.config_dir().join("config.toml");
        
        if config_path.exists() {
            let content = std::fs::read_to_string(&config_path)?;
            let mut config: AppConfig = toml::from_str(&content)?;
            
            // Merge with defaults for any missing fields
            config.merge_with_defaults();
            Ok(config)
        } else {
            Ok(Self::default())
        }
    }
    
    pub fn save(&self) -> Result<(), ConfigError> {
        let dirs = ProjectDirs::from("com", "arise", "ARISE").unwrap();
        let config_path = dirs.config_dir().join("config.toml");
        
        std::fs::create_dir_all(dirs.config_dir())?;
        let content = toml::to_string_pretty(self)?;
        std::fs::write(&config_path, content)?;
        Ok(())
    }
    
    fn merge_with_defaults(&mut self) {
        let defaults = Self::default();
        // Merge logic - keep existing, add missing
        // Simplified - in practice use serde merge
    }
    
    pub fn get_data_dir(&self) -> PathBuf {
        self.paths.data_dir.clone()
    }
    
    pub fn get_config_dir(&self) -> PathBuf {
        self.paths.config_dir.clone()
    }
}

#[derive(Debug, thiserror::Error)]
pub enum ConfigError {
    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),
    #[error("TOML parse error: {0}")]
    Toml(#[from] toml::de::Error),
    #[error("TOML serialize error: {0}")]
    TomlSer(#[from] toml::ser::Error),
}

// Tauri commands for config management
#[tauri::command]
pub fn get_config() -> Result<AppConfig, String> {
    AppConfig::load().map_err(|e| e.to_string())
}

#[tauri::command]
pub fn update_config(config: AppConfig) -> Result<(), String> {
    config.save().map_err(|e| e.to_string())
}

#[tauri::command]
pub fn reset_config() -> Result<AppConfig, String> {
    let config = AppConfig::default();
    config.save().map_err(|e| e.to_string())?;
    Ok(config)
}
```

---

## 10. Validation & Testing

```python
# tests/config/test_config.py
import pytest
import tempfile
import os
from pathlib import Path

from core.config.loader import ConfigLoader
from core.config.models import AppConfig, Environment, LogLevel
from core.config.secrets import EnvSecretProvider, SecretManager
from core.config.migration import MIGRATIONS

class TestConfigLoader:
    def test_load_defaults(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            loader = ConfigLoader(config_dir=Path(tmpdir))
            config = loader.load(Environment.TEST)
            
            assert config.app_name == "ARISE"
            assert config.environment == Environment.TEST
            assert config.database.url == "sqlite+aiosqlite:///data/arise.db"
    
    def test_load_from_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            config_dir.joinpath("config.default.yaml").write_text("""
app_name: "TEST_APP"
debug: true
database:
  url: "postgresql://test"
""")
            
            loader = ConfigLoader(config_dir=config_dir)
            config = loader.load(Environment.TEST)
            
            assert config.app_name == "TEST_APP"
            assert config.debug is True
            assert config.database.url == "postgresql://test"
    
    def test_env_override(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["ARISE_DEBUG"] = "true"
            os.environ["ARISE_DATABASE__URL"] = "sqlite:///env.db"
            
            try:
                loader = ConfigLoader(config_dir=Path(tmpdir))
                config = loader.load(Environment.TEST)
                
                assert config.debug is True
                assert config.database.url == "sqlite:///env.db"
            finally:
                del os.environ["ARISE_DEBUG"]
                del os.environ["ARISE_DATABASE__URL"]
    
    def test_layered_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            config_dir.joinpath("config.default.yaml").write_text("debug: false")
            config_dir.joinpath("config.test.yaml").write_text("debug: true")
            config_dir.joinpath("config.local.yaml").write_text("debug: false")
            
            loader = ConfigLoader(config_dir=config_dir)
            config = loader.load(Environment.TEST)
            
            # local.yaml should win
            assert config.debug is False
    
    def test_export_redacts_secrets(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            loader = ConfigLoader(config_dir=Path(tmpdir))
            config = loader.load(Environment.TEST)
            config.model_router.providers["openai"].api_key = "sk-secret123"
            
            exported = loader.export(include_secrets=False)
            assert "sk-secret123" not in exported
            assert "***REDACTED***" in exported

class TestSecretManager:
    def test_env_provider(self):
        os.environ["ARISE_SECRET_TEST_KEY"] = "test_value"
        
        try:
            provider = EnvSecretProvider()
            value = provider.get_secret("test.key")
            assert value == "test_value"
        finally:
            del os.environ["ARISE_SECRET_TEST_KEY"]
    
    def test_secret_manager_priority(self):
        manager = SecretManager()
        provider1 = EnvSecretProvider("PREFIX1_")
        provider2 = EnvSecretProvider("PREFIX2_")
        
        os.environ["PREFIX1_SHARED"] = "from_provider1"
        os.environ["PREFIX2_SHARED"] = "from_provider2"
        os.environ["PREFIX2_UNIQUE"] = "unique"
        
        try:
            manager.add_provider(provider1, priority=100)
            manager.add_provider(provider2, priority=50)
            
            # provider1 has higher priority
            assert manager.get_secret("shared") == "from_provider1"
            assert manager.get_secret("unique") == "unique"
        finally:
            for key in ["PREFIX1_SHARED", "PREFIX2_SHARED", "PREFIX2_UNIQUE"]:
                if key in os.environ:
                    del os.environ[key]

class TestMigration:
    def test_migrate_api_keys(self):
        config = {
            "model_router": {
                "providers": {
                    "openai": {"type": "openai", "api_key": "sk-real-key"}
                }
            }
        }
        
        migrated = MIGRATIONS.migrate(config, "1.1.0")
        
        assert migrated["model_router"]["providers"]["openai"]["api_key"] == "${model_provider.openai.api_key}"

class TestFeatureFlags:
    def test_boolean_flag(self):
        from core.config.feature_flags import FeatureFlag, FlagType, FeatureFlagStore
        
        store = FeatureFlagStore()
        flag = FeatureFlag(
            key="test.flag",
            name="Test Flag",
            description="Test",
            flag_type=FlagType.BOOLEAN,
            default_value=False,
        )
        store.register(flag)
        
        assert store.is_enabled("test.flag") is False
        store.set_value("test.flag", True)
        assert store.is_enabled("test.flag") is True
    
    def test_rollout(self):
        from core.config.feature_flags import FeatureFlag, FlagType, FeatureFlagStore
        
        store = FeatureFlagStore()
        flag = FeatureFlag(
            key="test.rollout",
            name="Rollout",
            description="Test",
            flag_type=FlagType.BOOLEAN,
            default_value=False,
            rollout_percentage=50,
        )
        store.register(flag)
        
        # Same user should get consistent result
        context = {"user_id": "user123"}
        results = [store.is_enabled("test.rollout", context) for _ in range(100)]
        assert all(r == results[0] for r in results)
```

---

*This configuration management system provides type-safe, layered configuration with secrets management, runtime updates, feature flags, and migration support across all ARISE components.*