"""
ARISE Configuration Models
All Pydantic models for the layered configuration system.
"""

from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# =============================================================================
# Enums
# =============================================================================

class LogLevel(str, Enum):
    """Logging levels."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class Environment(str, Enum):
    """Deployment environments."""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"


class ProviderType(str, Enum):
    """LLM provider types."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    OLLAMA = "ollama"
    AZURE_OPENAI = "azure_openai"
    VERTEX_AI = "vertex_ai"


class PrivacyMode(str, Enum):
    """Model router privacy modes."""
    OFF = "off"
    STANDARD = "standard"
    REDACT = "redact"
    LOCAL_ONLY = "local_only"


class RiskLevel(str, Enum):
    """Policy engine risk levels."""
    R0 = "R0"  # Read Only
    R1 = "R1"  # Local Write
    R2 = "R2"  # System Change
    R3 = "R3"  # External Communication
    R4 = "R4"  # Irreversible


class MemoryKind(str, Enum):
    """Memory kinds."""
    SEMANTIC = "SEMANTIC"
    EPISODIC = "EPISODIC"
    PROCEDURAL = "PROCEDURAL"
    PREFERENCE = "PREFERENCE"
    WORKING = "WORKING"


class TaskKind(str, Enum):
    """Task kinds."""
    SHELL_EXEC = "shell.exec"
    FILE_READ = "filesystem.read"
    FILE_WRITE = "filesystem.write"
    FILE_LIST = "filesystem.list"
    HTTP_REQUEST = "http.request"
    BROWSER_NAVIGATE = "browser.navigate"
    BROWSER_CLICK = "browser.click"
    BROWSER_EXTRACT = "browser.extract"
    UIA_FIND = "uia.find"
    UIA_CLICK = "uia.click"
    UIA_INPUT = "uia.input"
    MEMORY_STORE = "memory.store"
    MEMORY_QUERY = "memory.query"
    AGENT_DELEGATE = "agent.delegate"
    AGENT_VERIFY = "agent.verify"


class TaskStatus(str, Enum):
    """Task status (28 states)."""
    CREATED = "CREATED"
    QUEUED = "QUEUED"
    UNDERSTANDING = "UNDERSTANDING"
    PLANNING = "PLANNING"
    READY = "READY"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    WAITING_TOOL = "WAITING_TOOL"
    WAITING_MODEL = "WAITING_MODEL"
    WAITING_RESOURCE = "WAITING_RESOURCE"
    WAITING_HUMAN = "WAITING_HUMAN"
    WAITING_AGENT = "WAITING_AGENT"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    PAUSED = "PAUSED"
    RETRYING = "RETRYING"
    CHECKPOINTING = "CHECKPOINTING"
    RESTORING = "RESTORING"
    DELEGATING = "DELEGATING"
    AGGREGATING = "AGGREGATING"
    SYNTHESIZING = "SYNTHESIZING"
    VALIDATING = "VALIDATING"
    ARCHIVING = "ARCHIVING"
    EXPIRED = "EXPIRED"
    TIMEOUT = "TIMEOUT"
    UNKNOWN = "UNKNOWN"


class TaskPriority(int, Enum):
    """Task priority levels (1-10, higher = more urgent)."""
    LOWEST = 1
    LOW = 2
    BELOW_NORMAL = 3
    NORMAL = 5
    ABOVE_NORMAL = 6
    HIGH = 7
    VERY_HIGH = 8
    CRITICAL = 9
    EMERGENCY = 10


# =============================================================================
# Database Configuration
# =============================================================================

class DatabaseConfig(BaseModel):
    """Database connection configuration."""
    url: str = "sqlite+aiosqlite:///./arise.db"
    pool_size: int = Field(default=5, ge=1, le=100)
    max_overflow: int = Field(default=10, ge=0, le=100)
    pool_timeout: int = Field(default=30, ge=1, le=300)
    pool_recycle: int = Field(default=3600, ge=60, le=86400)
    echo: bool = False
    echo_pool: bool = False


class RedisConfig(BaseModel):
    """Redis connection configuration."""
    url: str = "redis://localhost:6379/0"
    max_connections: int = Field(default=50, ge=1, le=500)
    socket_timeout: int = Field(default=5, ge=1, le=60)
    socket_connect_timeout: int = Field(default=5, ge=1, le=60)
    retry_on_timeout: bool = True
    decode_responses: bool = True


# =============================================================================
# Model Router Configuration
# =============================================================================

class ModelProviderConfig(BaseModel):
    """Individual model provider configuration."""
    enabled: bool = True
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    models: List[str] = Field(default_factory=list)
    default_model: Optional[str] = None
    timeout: int = Field(default=60, ge=5, le=300)
    max_retries: int = Field(default=3, ge=0, le=10)
    # Provider-specific fields
    api_version: Optional[str] = None
    endpoint: Optional[str] = None
    project_id: Optional[str] = None
    location: Optional[str] = None


class ModelRouterConfig(BaseModel):
    """Model router configuration."""
    default_provider: ProviderType = ProviderType.OPENAI
    privacy_mode: PrivacyMode = PrivacyMode.STANDARD
    fallback_chain: List[ProviderType] = Field(default_factory=lambda: [
        ProviderType.OPENAI,
        ProviderType.ANTHROPIC,
        ProviderType.GEMINI,
        ProviderType.OLLAMA,
    ])
    providers: Dict[ProviderType, ModelProviderConfig] = Field(default_factory=dict)
    cost_tracking_enabled: bool = True
    circuit_breaker_enabled: bool = True
    circuit_breaker_threshold: int = Field(default=5, ge=1, le=100)
    circuit_breaker_timeout: int = Field(default=60, ge=10, le=300)


# =============================================================================
# Task Engine Configuration
# =============================================================================

class SandboxConfig(BaseModel):
    """Sandbox configuration for task execution."""
    enabled: bool = True
    type: str = "docker"  # docker, gvisor, firecracker
    docker_image: str = "arise/sandbox:latest"
    memory_limit_mb: int = Field(default=512, ge=64, le=8192)
    cpu_limit_percent: int = Field(default=50, ge=10, le=100)
    disk_limit_mb: int = Field(default=1024, ge=100, le=51200)
    network_enabled: bool = False
    timeout_seconds: int = Field(default=300, ge=30, le=3600)


class TaskEngineConfig(BaseModel):
    """Task engine configuration."""
    max_concurrent_tasks: int = Field(default=10, ge=1, le=100)
    default_priority: TaskPriority = TaskPriority.NORMAL
    checkpoint_interval_seconds: int = Field(default=30, ge=10, le=300)
    max_checkpoints_per_task: int = Field(default=100, ge=10, le=1000)
    task_timeout_seconds: int = Field(default=3600, ge=60, le=86400)
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    queue_priority_levels: int = Field(default=10, ge=1, le=20)
    fair_scheduling: bool = True
    persistence_enabled: bool = True


# =============================================================================
# Policy Engine Configuration
# =============================================================================

class RiskLevelConfig(BaseModel):
    """Risk level configuration."""
    name: str
    auto_approve: bool = False
    requires_mfa: bool = False
    timeout_seconds: int = Field(default=300, ge=0, le=3600)


class PolicyEngineConfig(BaseModel):
    """Policy engine configuration."""
    risk_levels: Dict[RiskLevel, RiskLevelConfig] = Field(default_factory=lambda: {
        RiskLevel.R0: RiskLevelConfig(name="Read Only", auto_approve=True, requires_mfa=False, timeout_seconds=0),
        RiskLevel.R1: RiskLevelConfig(name="Local Write", auto_approve=True, requires_mfa=False, timeout_seconds=300),
        RiskLevel.R2: RiskLevelConfig(name="System Change", auto_approve=False, requires_mfa=False, timeout_seconds=600),
        RiskLevel.R3: RiskLevelConfig(name="External Communication", auto_approve=False, requires_mfa=True, timeout_seconds=300),
        RiskLevel.R4: RiskLevelConfig(name="Irreversible", auto_approve=False, requires_mfa=True, timeout_seconds=60),
    })
    capabilities: List[str] = Field(default_factory=lambda: [
        "task.execute", "task.cancel", "filesystem.read", "filesystem.write", "filesystem.delete",
        "shell.exec", "network.http", "network.websocket", "browser.navigate", "browser.click",
        "browser.extract", "uia.find", "uia.click", "uia.input", "memory.store", "memory.query",
        "memory.delete", "voice.listen", "voice.speak", "agent.delegate", "agent.verify",
        "config.read", "config.write", "secrets.read", "secrets.write", "system.shutdown",
        "system.reboot", "credentials.read", "credentials.write",
    ])
    default_risk_level: RiskLevel = RiskLevel.R1
    approval_ui_enabled: bool = True
    audit_enabled: bool = True


# =============================================================================
# Voice Configuration
# =============================================================================

class WakeWordConfig(BaseModel):
    """Wake word detection configuration."""
    enabled: bool = True
    model: str = "hey_arise"
    sensitivity: float = Field(default=0.5, ge=0.0, le=1.0)
    audio_device: str = "default"
    dormant_cpu_percent: float = Field(default=1.0, ge=0.1, le=10.0)


class ASRConfig(BaseModel):
    """ASR configuration."""
    primary: str = "sherpa_onnx"
    fallback_chain: List[str] = Field(default_factory=lambda: ["sherpa_onnx", "whisper", "gemini", "azure"])
    language: str = "auto"
    vad_enabled: bool = True
    vad_threshold: float = Field(default=0.5, ge=0.0, le=1.0)


class TTSConfig(BaseModel):
    """TTS configuration."""
    primary: str = "gemini"
    fallback_chain: List[str] = Field(default_factory=lambda: ["gemini", "coqui", "elevenlabs", "azure"])
    voice: str = "en-US-Neural2-F"
    streaming: bool = True


class VoiceSessionConfig(BaseModel):
    """Voice session configuration."""
    timeout_seconds: int = Field(default=30, ge=5, le=300)
    max_duration_seconds: int = Field(default=3600, ge=60, le=86400)
    barge_in_enabled: bool = True
    context_preservation: bool = True


class VoiceConfig(BaseModel):
    """Voice pipeline configuration."""
    enabled: bool = True
    wake_word: WakeWordConfig = Field(default_factory=WakeWordConfig)
    asr: ASRConfig = Field(default_factory=ASRConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)
    session: VoiceSessionConfig = Field(default_factory=VoiceSessionConfig)


# =============================================================================
# Memory Configuration
# =============================================================================

class MemoryKindConfig(BaseModel):
    """Per-kind memory configuration."""
    enabled: bool = True
    max_items: int = Field(default=100000, ge=1000, le=1000000)
    ttl_days: int = Field(default=3650, ge=1, le=36500)


class ChromaDBConfig(BaseModel):
    """ChromaDB vector store configuration."""
    enabled: bool = True
    persist_directory: str = "./data/chromadb"
    collection_name: str = "arise_memories"


class SQLiteFTSConfig(BaseModel):
    """SQLite FTS store configuration."""
    enabled: bool = True
    database_path: str = "./data/memory_fts.db"


class ConsolidationConfig(BaseModel):
    """Memory consolidation configuration."""
    enabled: bool = True
    interval_hours: int = Field(default=6, ge=1, le=168)
    working_to_episodic_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    episodic_to_semantic_threshold: float = Field(default=0.8, ge=0.0, le=1.0)
    preference_extraction_enabled: bool = True
    procedural_learning_enabled: bool = True


class MemoryGovernanceConfig(BaseModel):
    """Memory governance configuration."""
    pii_detection_enabled: bool = True
    pii_action: str = "redact"  # flag, redact, block
    encryption_enabled: bool = True
    max_memories_per_kind: int = Field(default=100000, ge=1000, le=1000000)
    lru_eviction_enabled: bool = True


class MemoryConfig(BaseModel):
    """Memory system configuration."""
    enabled: bool = True
    kinds: Dict[MemoryKind, MemoryKindConfig] = Field(default_factory=lambda: {
        MemoryKind.SEMANTIC: MemoryKindConfig(enabled=True, max_items=100000, ttl_days=3650),
        MemoryKind.EPISODIC: MemoryKindConfig(enabled=True, max_items=50000, ttl_days=365),
        MemoryKind.PROCEDURAL: MemoryKindConfig(enabled=True, max_items=10000, ttl_days=3650),
        MemoryKind.PREFERENCE: MemoryKindConfig(enabled=True, max_items=1000, ttl_days=3650),
        MemoryKind.WORKING: MemoryKindConfig(enabled=True, max_items=1000, ttl_days=7),
    })
    stores: Dict[str, Any] = Field(default_factory=lambda: {
        "chromadb": ChromaDBConfig(),
        "sqlite_fts": SQLiteFTSConfig(),
    })
    consolidation: ConsolidationConfig = Field(default_factory=ConsolidationConfig)
    governance: MemoryGovernanceConfig = Field(default_factory=MemoryGovernanceConfig)


# =============================================================================
# Automation Configuration
# =============================================================================

class UIAConfig(BaseModel):
    """UIA backend configuration."""
    enabled: bool = True
    backend: str = "comtypes"
    retry_attempts: int = Field(default=3, ge=1, le=10)
    retry_delay_ms: int = Field(default=100, ge=10, le=1000)
    screenshot_on_failure: bool = True


class PlaywrightConfig(BaseModel):
    """Playwright backend configuration."""
    enabled: bool = True
    browser: str = "chromium"
    headless: bool = False
    stealth_mode: bool = False
    context_isolation: bool = True


class CVOCRConfig(BaseModel):
    """CV/OCR backend configuration."""
    enabled: bool = True
    ocr_engine: str = "tesseract"  # tesseract, paddleocr
    tesseract_path: str = "tesseract"
    paddleocr_lang: str = "en"
    confidence_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    template_matching_enabled: bool = True


class AutomationCoordinatorConfig(BaseModel):
    """Automation coordinator configuration."""
    cross_app_enabled: bool = True
    clipboard_sync: bool = True
    window_management: bool = True
    safety_confirmations: bool = True
    max_workflow_steps: int = Field(default=50, ge=5, le=200)


class AutomationConfig(BaseModel):
    """Desktop automation configuration."""
    enabled: bool = True
    perception_hierarchy: List[str] = Field(default_factory=lambda: ["uia", "playwright", "cv_ocr"])
    uia: UIAConfig = Field(default_factory=UIAConfig)
    playwright: PlaywrightConfig = Field(default_factory=PlaywrightConfig)
    cv_ocr: CVOCRConfig = Field(default_factory=CVOCRConfig)
    coordinator: AutomationCoordinatorConfig = Field(default_factory=AutomationCoordinatorConfig)


# =============================================================================
# Security Configuration
# =============================================================================

class CredentialsConfig(BaseModel):
    """Credentials configuration."""
    primary_provider: str = "windows_credential_manager"
    fallback_providers: List[str] = Field(default_factory=lambda: ["keyring", "vault", "env"])


class NetworkConfig(BaseModel):
    """Network egress control configuration."""
    egress_control_enabled: bool = True
    default_policy: str = "deny"  # allow, deny
    allowlist: List[str] = Field(default_factory=lambda: [
        "api.openai.com",
        "api.anthropic.com",
        "generativelanguage.googleapis.com",
        "localhost",
        "127.0.0.1",
    ])
    denylist: List[str] = Field(default_factory=list)
    dns_blocking_enabled: bool = True
    proxy_interception_enabled: bool = True


class PromptInjectionConfig(BaseModel):
    """Prompt injection detection configuration."""
    enabled: bool = True
    model: str = "promptguard"
    heuristic_rules_enabled: bool = True
    integration_points: List[str] = Field(default_factory=lambda: [
        "model_router_input", "agent_input", "automation_input"
    ])


class SecurityAuditConfig(BaseModel):
    """Security audit configuration."""
    enabled: bool = True
    tamper_evident: bool = True
    encryption_enabled: bool = True
    log_credential_access: bool = True
    log_network_blocks: bool = True
    log_prompt_injections: bool = True


class EncryptionConfig(BaseModel):
    """Encryption configuration."""
    algorithm: str = "AES-256-GCM"
    key_derivation: str = "PBKDF2"
    key_rotation_days: int = Field(default=90, ge=1, le=365)
    field_level_encryption: bool = True


class SecurityConfig(BaseModel):
    """Security hardening configuration."""
    credentials: CredentialsConfig = Field(default_factory=CredentialsConfig)
    network: NetworkConfig = Field(default_factory=NetworkConfig)
    prompt_injection: PromptInjectionConfig = Field(default_factory=PromptInjectionConfig)
    audit: SecurityAuditConfig = Field(default_factory=SecurityAuditConfig)
    encryption: EncryptionConfig = Field(default_factory=EncryptionConfig)
    # CORS and trusted hosts
    cors_origins: List[str] = Field(default_factory=lambda: ["*"])
    trusted_hosts: List[str] = Field(default_factory=list)


# =============================================================================
# Agent Configuration
# =============================================================================

class AgentSpecialistConfig(BaseModel):
    """Agent specialist configuration."""
    enabled: bool = True
    model: str = "gpt-4o-mini"


class AgentCoordinatorConfig(BaseModel):
    """Central coordinator configuration."""
    enabled: bool = True
    model: str = "gpt-4o"
    max_delegation_depth: int = Field(default=5, ge=1, le=10)
    timeout_seconds: int = Field(default=300, ge=30, le=3600)


class AgentRegistryConfig(BaseModel):
    """Agent registry configuration."""
    heartbeat_interval_seconds: int = Field(default=30, ge=10, le=300)
    max_restarts: int = Field(default=3, ge=0, le=10)
    health_check_timeout: int = Field(default=10, ge=5, le=60)


class AgentsConfig(BaseModel):
    """Multi-agent system configuration."""
    enabled: bool = True
    coordinator: AgentCoordinatorConfig = Field(default_factory=AgentCoordinatorConfig)
    specialists: Dict[str, AgentSpecialistConfig] = Field(default_factory=lambda: {
        "planner": AgentSpecialistConfig(enabled=True, model="gpt-4o"),
        "coder": AgentSpecialistConfig(enabled=True, model="gpt-4o"),
        "researcher": AgentSpecialistConfig(enabled=True, model="gemini-1.5-pro"),
        "analyst": AgentSpecialistConfig(enabled=True, model="claude-3-5-sonnet-20241022"),
        "creative": AgentSpecialistConfig(enabled=True, model="gpt-4o"),
        "automation": AgentSpecialistConfig(enabled=True, model="gpt-4o-mini"),
        "memory": AgentSpecialistConfig(enabled=True, model="gpt-4o-mini"),
        "security": AgentSpecialistConfig(enabled=True, model="gpt-4o-mini"),
        "reviewer": AgentSpecialistConfig(enabled=True, model="gpt-4o"),
        "communicator": AgentSpecialistConfig(enabled=True, model="gpt-4o-mini"),
        "scheduler": AgentSpecialistConfig(enabled=True, model="gpt-4o-mini"),
    })
    registry: AgentRegistryConfig = Field(default_factory=AgentRegistryConfig)


# =============================================================================
# Frontend Configuration
# =============================================================================

class FrontendConfig(BaseModel):
    """Frontend configuration."""
    api_base_url: str = "http://localhost:8000"
    ws_base_url: str = "ws://localhost:8000"
    theme: str = "dark"
    language: str = "en"
    auto_refresh_interval: int = Field(default=30000, ge=5000, le=300000)


# =============================================================================
# Telemetry Configuration
# =============================================================================

class LoggingConfig(BaseModel):
    """Logging configuration."""
    level: LogLevel = LogLevel.INFO
    format: str = "json"  # json, text
    output: str = "stdout"  # stdout, file
    correlation_id_header: str = "X-Correlation-ID"


class MetricsConfig(BaseModel):
    """Metrics configuration."""
    enabled: bool = True
    port: int = Field(default=9090, ge=1024, le=65535)
    path: str = "/metrics"


class TracingConfig(BaseModel):
    """Distributed tracing configuration."""
    enabled: bool = True
    jaeger_endpoint: str = "http://localhost:4317"
    sample_rate: float = Field(default=0.1, ge=0.0, le=1.0)


class HealthChecksConfig(BaseModel):
    """Health checks configuration."""
    enabled: bool = True
    interval_seconds: int = Field(default=30, ge=10, le=300)


class TelemetryConfig(BaseModel):
    """Telemetry configuration."""
    enabled: bool = True
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    metrics: MetricsConfig = Field(default_factory=MetricsConfig)
    tracing: TracingConfig = Field(default_factory=TracingConfig)
    health_checks: HealthChecksConfig = Field(default_factory=HealthChecksConfig)


# =============================================================================
# Events Configuration
# =============================================================================

class LocalEventBusConfig(BaseModel):
    """Local event bus configuration."""
    enabled: bool = True
    worker_count: int = Field(default=4, ge=1, le=32)
    queue_size: int = Field(default=10000, ge=1000, le=100000)
    dead_letter_queue_size: int = Field(default=1000, ge=100, le=10000)


class DistributedEventBusConfig(BaseModel):
    """Distributed event bus configuration."""
    enabled: bool = False
    redis_streams_enabled: bool = True
    consumer_group: str = "arise-events"


class EventStoreConfig(BaseModel):
    """Event store configuration."""
    enabled: bool = True
    type: str = "sqlite"  # sqlite, postgres
    path: str = "./data/events.db"
    wal_mode: bool = True


class ProjectionsConfig(BaseModel):
    """Projections configuration."""
    enabled: bool = True
    checkpoint_interval: int = Field(default=100, ge=10, le=1000)


class EventTracingConfig(BaseModel):
    """Event tracing configuration."""
    enabled: bool = True
    correlation_header: str = "X-Correlation-ID"
    service_name: str = "arise"


class EventsConfig(BaseModel):
    """Event bus configuration."""
    local: LocalEventBusConfig = Field(default_factory=LocalEventBusConfig)
    distributed: DistributedEventBusConfig = Field(default_factory=DistributedEventBusConfig)
    store: EventStoreConfig = Field(default_factory=EventStoreConfig)
    projections: ProjectionsConfig = Field(default_factory=ProjectionsConfig)
    tracing: EventTracingConfig = Field(default_factory=EventTracingConfig)


# =============================================================================
# Main Application Configuration
# =============================================================================

class AppConfig(BaseModel):
    """Main application configuration containing all sub-configurations."""
    # Core app settings
    name: str = "ARISE"
    version: str = "1.0.0"
    environment: Environment = Environment.DEVELOPMENT
    debug: bool = True

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
    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    frontend: FrontendConfig = Field(default_factory=FrontendConfig)
    telemetry: TelemetryConfig = Field(default_factory=TelemetryConfig)
    events: EventsConfig = Field(default_factory=EventsConfig)


# =============================================================================
# Settings Management (for Pydantic Settings)
# =============================================================================

class Settings(BaseSettings):
    """Settings loaded from environment variables."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_nested_delimiter="__",
    )

    # Environment
    environment: Environment = Environment.DEVELOPMENT
    debug: bool = True
    log_level: LogLevel = LogLevel.INFO

    # Database
    database_url: str = "sqlite+aiosqlite:///./arise.db"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Model Providers
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    google_api_key: Optional[str] = None
    azure_openai_api_key: Optional[str] = None
    azure_openai_endpoint: Optional[str] = None
    vertex_ai_project_id: Optional[str] = None
    vertex_ai_location: Optional[str] = None

    # Voice
    porcupine_access_key: Optional[str] = None
    elevenlabs_api_key: Optional[str] = None

    # Security
    master_encryption_key: Optional[str] = None
    vault_addr: Optional[str] = None
    vault_token: Optional[str] = None

    # Telemetry
    otel_exporter_otlp_endpoint: Optional[str] = None
    otel_exporter_otlp_headers: Optional[str] = None


# Global settings instance
settings = Settings()