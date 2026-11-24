//! ARISE Tauri Configuration
//! Rust configuration types matching the Python/TypeScript config

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::PathBuf;

/// Application environment
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Environment {
    Development,
    Staging,
    Production,
    Test,
}

impl Default for Environment {
    fn default() -> Self {
        Environment::Development
    }
}

/// Log level
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "uppercase")]
pub enum LogLevel {
    Debug,
    Info,
    Warning,
    Error,
    Critical,
}

impl Default for LogLevel {
    fn default() -> Self {
        LogLevel::Info
    }
}

/// LLM Provider types
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ProviderType {
    OpenAI,
    Anthropic,
    Gemini,
    Ollama,
    AzureOpenAI,
    VertexAI,
}

impl Default for ProviderType {
    fn default() -> Self {
        ProviderType::OpenAI
    }
}

/// Privacy mode for model router
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum PrivacyMode {
    Off,
    Standard,
    Redact,
    LocalOnly,
}

impl Default for PrivacyMode {
    fn default() -> Self {
        PrivacyMode::Standard
    }
}

/// Risk levels for policy engine
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "uppercase")]
pub enum RiskLevel {
    R0,
    R1,
    R2,
    R3,
    R4,
}

impl Default for RiskLevel {
    fn default() -> Self {
        RiskLevel::R1
    }
}

/// Memory kinds
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "uppercase")]
pub enum MemoryKind {
    Semantic,
    Episodic,
    Procedural,
    Preference,
    Working,
}

/// Task kinds
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TaskKind {
    ShellExec,
    FilesystemRead,
    FilesystemWrite,
    FilesystemList,
    HttpRequest,
    BrowserNavigate,
    BrowserClick,
    BrowserExtract,
    UiaFind,
    UiaClick,
    UiaInput,
    MemoryStore,
    MemoryQuery,
    AgentDelegate,
    AgentVerify,
}

/// Task status (28 states)
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TaskStatus {
    Created,
    Queued,
    Understanding,
    Planning,
    Ready,
    Running,
    WaitingApproval,
    WaitingTool,
    WaitingModel,
    WaitingResource,
    WaitingHuman,
    WaitingAgent,
    Verifying,
    Completed,
    Failed,
    Cancelled,
    Paused,
    Retrying,
    Checkpointing,
    Restoring,
    Delegating,
    Aggregating,
    Synthesizing,
    Validating,
    Archiving,
    Expired,
    Timeout,
    Unknown,
}

/// Task priority (1-10)
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[repr(u8)]
pub enum TaskPriority {
    Lowest = 1,
    Low = 2,
    BelowNormal = 3,
    Normal = 5,
    AboveNormal = 6,
    High = 7,
    VeryHigh = 8,
    Critical = 9,
    Emergency = 10,
}

impl Default for TaskPriority {
    fn default() -> Self {
        TaskPriority::Normal
    }
}

/// Feature flag types
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum FlagType {
    Boolean,
    String,
    Integer,
    Float,
    Json,
}

/// Feature flag status
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum FlagStatus {
    Active,
    Inactive,
    Archived,
}

// =============================================================================
// Database Configuration
// =============================================================================

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DatabaseConfig {
    pub url: String,
    pub pool_size: u32,
    pub max_overflow: u32,
    pub pool_timeout: u32,
    pub pool_recycle: u32,
    pub echo: bool,
    pub echo_pool: bool,
}

impl Default for DatabaseConfig {
    fn default() -> Self {
        Self {
            url: "sqlite+aiosqlite:///./arise.db".to_string(),
            pool_size: 5,
            max_overflow: 10,
            pool_timeout: 30,
            pool_recycle: 3600,
            echo: false,
            echo_pool: false,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RedisConfig {
    pub url: String,
    pub max_connections: u32,
    pub socket_timeout: u32,
    pub socket_connect_timeout: u32,
    pub retry_on_timeout: bool,
    pub decode_responses: bool,
}

impl Default for RedisConfig {
    fn default() -> Self {
        Self {
            url: "redis://localhost:6379/0".to_string(),
            max_connections: 50,
            socket_timeout: 5,
            socket_connect_timeout: 5,
            retry_on_timeout: true,
            decode_responses: true,
        }
    }
}

// =============================================================================
// Model Router Configuration
// =============================================================================

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModelProviderConfig {
    pub enabled: bool,
    pub api_key: Option<String>,
    pub base_url: Option<String>,
    pub models: Vec<String>,
    pub default_model: Option<String>,
    pub timeout: u32,
    pub max_retries: u32,
    pub api_version: Option<String>,
    pub endpoint: Option<String>,
    pub project_id: Option<String>,
    pub location: Option<String>,
}

impl Default for ModelProviderConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            api_key: None,
            base_url: None,
            models: Vec::new(),
            default_model: None,
            timeout: 60,
            max_retries: 3,
            api_version: None,
            endpoint: None,
            project_id: None,
            location: None,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModelRouterConfig {
    pub default_provider: ProviderType,
    pub privacy_mode: PrivacyMode,
    pub fallback_chain: Vec<ProviderType>,
    pub providers: HashMap<ProviderType, ModelProviderConfig>,
    pub cost_tracking_enabled: bool,
    pub circuit_breaker_enabled: bool,
    pub circuit_breaker_threshold: u32,
    pub circuit_breaker_timeout: u32,
}

impl Default for ModelRouterConfig {
    fn default() -> Self {
        let mut providers = HashMap::new();
        providers.insert(ProviderType::OpenAI, ModelProviderConfig::default());
        providers.insert(ProviderType::Anthropic, ModelProviderConfig::default());
        providers.insert(ProviderType::Gemini, ModelProviderConfig::default());
        providers.insert(ProviderType::Ollama, ModelProviderConfig::default());
        providers.insert(ProviderType::AzureOpenAI, ModelProviderConfig::default());
        providers.insert(ProviderType::VertexAI, ModelProviderConfig::default());

        Self {
            default_provider: ProviderType::OpenAI,
            privacy_mode: PrivacyMode::Standard,
            fallback_chain: vec![
                ProviderType::OpenAI,
                ProviderType::Anthropic,
                ProviderType::Gemini,
                ProviderType::Ollama,
            ],
            providers,
            cost_tracking_enabled: true,
            circuit_breaker_enabled: true,
            circuit_breaker_threshold: 5,
            circuit_breaker_timeout: 60,
        }
    }
}

// =============================================================================
// Task Engine Configuration
// =============================================================================

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SandboxConfig {
    pub enabled: bool,
    pub r#type: String,
    pub docker_image: String,
    pub memory_limit_mb: u32,
    pub cpu_limit_percent: u32,
    pub disk_limit_mb: u32,
    pub network_enabled: bool,
    pub timeout_seconds: u32,
}

impl Default for SandboxConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            r#type: "docker".to_string(),
            docker_image: "arise/sandbox:latest".to_string(),
            memory_limit_mb: 512,
            cpu_limit_percent: 50,
            disk_limit_mb: 1024,
            network_enabled: false,
            timeout_seconds: 300,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TaskEngineConfig {
    pub max_concurrent_tasks: u32,
    pub default_priority: TaskPriority,
    pub checkpoint_interval_seconds: u32,
    pub max_checkpoints_per_task: u32,
    pub task_timeout_seconds: u32,
    pub sandbox: SandboxConfig,
    pub queue_priority_levels: u32,
    pub fair_scheduling: bool,
    pub persistence_enabled: bool,
}

impl Default for TaskEngineConfig {
    fn default() -> Self {
        Self {
            max_concurrent_tasks: 10,
            default_priority: TaskPriority::Normal,
            checkpoint_interval_seconds: 30,
            max_checkpoints_per_task: 100,
            task_timeout_seconds: 3600,
            sandbox: SandboxConfig::default(),
            queue_priority_levels: 10,
            fair_scheduling: true,
            persistence_enabled: true,
        }
    }
}

// =============================================================================
// Policy Engine Configuration
// =============================================================================

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RiskLevelConfig {
    pub name: String,
    pub auto_approve: bool,
    pub requires_mfa: bool,
    pub timeout_seconds: u32,
}

impl Default for RiskLevelConfig {
    fn default() -> Self {
        Self {
            name: "Default".to_string(),
            auto_approve: false,
            requires_mfa: false,
            timeout_seconds: 300,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PolicyEngineConfig {
    pub risk_levels: HashMap<RiskLevel, RiskLevelConfig>,
    pub capabilities: Vec<String>,
    pub default_risk_level: RiskLevel,
    pub approval_ui_enabled: bool,
    pub audit_enabled: bool,
}

impl Default for PolicyEngineConfig {
    fn default() -> Self {
        let mut risk_levels = HashMap::new();
        risk_levels.insert(RiskLevel::R0, RiskLevelConfig {
            name: "Read Only".to_string(),
            auto_approve: true,
            requires_mfa: false,
            timeout_seconds: 0,
        });
        risk_levels.insert(RiskLevel::R1, RiskLevelConfig {
            name: "Local Write".to_string(),
            auto_approve: true,
            requires_mfa: false,
            timeout_seconds: 300,
        });
        risk_levels.insert(RiskLevel::R2, RiskLevelConfig {
            name: "System Change".to_string(),
            auto_approve: false,
            requires_mfa: false,
            timeout_seconds: 600,
        });
        risk_levels.insert(RiskLevel::R3, RiskLevelConfig {
            name: "External Communication".to_string(),
            auto_approve: false,
            requires_mfa: true,
            timeout_seconds: 300,
        });
        risk_levels.insert(RiskLevel::R4, RiskLevelConfig {
            name: "Irreversible".to_string(),
            auto_approve: false,
            requires_mfa: true,
            timeout_seconds: 60,
        });

        Self {
            risk_levels,
            capabilities: vec![
                "task.execute".to_string(),
                "task.cancel".to_string(),
                "filesystem.read".to_string(),
                "filesystem.write".to_string(),
                "filesystem.delete".to_string(),
                "shell.exec".to_string(),
                "network.http".to_string(),
                "network.websocket".to_string(),
                "browser.navigate".to_string(),
                "browser.click".to_string(),
                "browser.extract".to_string(),
                "uia.find".to_string(),
                "uia.click".to_string(),
                "uia.input".to_string(),
                "memory.store".to_string(),
                "memory.query".to_string(),
                "memory.delete".to_string(),
                "voice.listen".to_string(),
                "voice.speak".to_string(),
                "agent.delegate".to_string(),
                "agent.verify".to_string(),
                "config.read".to_string(),
                "config.write".to_string(),
                "secrets.read".to_string(),
                "secrets.write".to_string(),
                "system.shutdown".to_string(),
                "system.reboot".to_string(),
                "credentials.read".to_string(),
                "credentials.write".to_string(),
            ],
            default_risk_level: RiskLevel::R1,
            approval_ui_enabled: true,
            audit_enabled: true,
        }
    }
}

// =============================================================================
// Voice Configuration
// =============================================================================

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WakeWordConfig {
    pub enabled: bool,
    pub model: String,
    pub sensitivity: f32,
    pub audio_device: String,
    pub dormant_cpu_percent: f32,
}

impl Default for WakeWordConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            model: "hey_arise".to_string(),
            sensitivity: 0.5,
            audio_device: "default".to_string(),
            dormant_cpu_percent: 1.0,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ASRConfig {
    pub primary: String,
    pub fallback_chain: Vec<String>,
    pub language: String,
    pub vad_enabled: bool,
    pub vad_threshold: f32,
}

impl Default for ASRConfig {
    fn default() -> Self {
        Self {
            primary: "sherpa_onnx".to_string(),
            fallback_chain: vec![
                "sherpa_onnx".to_string(),
                "whisper".to_string(),
                "gemini".to_string(),
                "azure".to_string(),
            ],
            language: "auto".to_string(),
            vad_enabled: true,
            vad_threshold: 0.5,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TTSConfig {
    pub primary: String,
    pub fallback_chain: Vec<String>,
    pub voice: String,
    pub streaming: bool,
}

impl Default for TTSConfig {
    fn default() -> Self {
        Self {
            primary: "gemini".to_string(),
            fallback_chain: vec![
                "gemini".to_string(),
                "coqui".to_string(),
                "elevenlabs".to_string(),
                "azure".to_string(),
            ],
            voice: "en-US-Neural2-F".to_string(),
            streaming: true,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VoiceSessionConfig {
    pub timeout_seconds: u32,
    pub max_duration_seconds: u32,
    pub barge_in_enabled: bool,
    pub context_preservation: bool,
}

impl Default for VoiceSessionConfig {
    fn default() -> Self {
        Self {
            timeout_seconds: 30,
            max_duration_seconds: 3600,
            barge_in_enabled: true,
            context_preservation: true,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VoiceConfig {
    pub enabled: bool,
    pub wake_word: WakeWordConfig,
    pub asr: ASRConfig,
    pub tts: TTSConfig,
    pub session: VoiceSessionConfig,
}

impl Default for VoiceConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            wake_word: WakeWordConfig::default(),
            asr: ASRConfig::default(),
            tts: TTSConfig::default(),
            session: VoiceSessionConfig::default(),
        }
    }
}

// =============================================================================
// Memory Configuration
// =============================================================================

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemoryKindConfig {
    pub enabled: bool,
    pub max_items: u32,
    pub ttl_days: u32,
}

impl Default for MemoryKindConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            max_items: 100000,
            ttl_days: 3650,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChromaDBConfig {
    pub enabled: bool,
    pub persist_directory: PathBuf,
    pub collection_name: String,
}

impl Default for ChromaDBConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            persist_directory: PathBuf::from("./data/chromadb"),
            collection_name: "arise_memories".to_string(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SQLiteFTSConfig {
    pub enabled: bool,
    pub database_path: PathBuf,
}

impl Default for SQLiteFTSConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            database_path: PathBuf::from("./data/memory_fts.db"),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConsolidationConfig {
    pub enabled: bool,
    pub interval_hours: u32,
    pub working_to_episodic_threshold: f32,
    pub episodic_to_semantic_threshold: f32,
    pub preference_extraction_enabled: bool,
    pub procedural_learning_enabled: bool,
}

impl Default for ConsolidationConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            interval_hours: 6,
            working_to_episodic_threshold: 0.7,
            episodic_to_semantic_threshold: 0.8,
            preference_extraction_enabled: true,
            procedural_learning_enabled: true,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemoryGovernanceConfig {
    pub pii_detection_enabled: bool,
    pub pii_action: String,
    pub encryption_enabled: bool,
    pub max_memories_per_kind: u32,
    pub lru_eviction_enabled: bool,
}

impl Default for MemoryGovernanceConfig {
    fn default() -> Self {
        Self {
            pii_detection_enabled: true,
            pii_action: "redact".to_string(),
            encryption_enabled: true,
            max_memories_per_kind: 100000,
            lru_eviction_enabled: true,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemoryConfig {
    pub enabled: bool,
    pub kinds: HashMap<MemoryKind, MemoryKindConfig>,
    pub chromadb: ChromaDBConfig,
    pub sqlite_fts: SQLiteFTSConfig,
    pub consolidation: ConsolidationConfig,
    pub governance: MemoryGovernanceConfig,
}

impl Default for MemoryConfig {
    fn default() -> Self {
        let mut kinds = HashMap::new();
        kinds.insert(MemoryKind::Semantic, MemoryKindConfig {
            enabled: true,
            max_items: 100000,
            ttl_days: 3650,
        });
        kinds.insert(MemoryKind::Episodic, MemoryKindConfig {
            enabled: true,
            max_items: 50000,
            ttl_days: 365,
        });
        kinds.insert(MemoryKind::Procedural, MemoryKindConfig {
            enabled: true,
            max_items: 10000,
            ttl_days: 3650,
        });
        kinds.insert(MemoryKind::Preference, MemoryKindConfig {
            enabled: true,
            max_items: 1000,
            ttl_days: 3650,
        });
        kinds.insert(MemoryKind::Working, MemoryKindConfig {
            enabled: true,
            max_items: 1000,
            ttl_days: 7,
        });

        Self {
            enabled: true,
            kinds,
            chromadb: ChromaDBConfig::default(),
            sqlite_fts: SQLiteFTSConfig::default(),
            consolidation: ConsolidationConfig::default(),
            governance: MemoryGovernanceConfig::default(),
        }
    }
}

// =============================================================================
// Automation Configuration
// =============================================================================

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UIAConfig {
    pub enabled: bool,
    pub backend: String,
    pub retry_attempts: u32,
    pub retry_delay_ms: u32,
    pub screenshot_on_failure: bool,
}

impl Default for UIAConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            backend: "comtypes".to_string(),
            retry_attempts: 3,
            retry_delay_ms: 100,
            screenshot_on_failure: true,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PlaywrightConfig {
    pub enabled: bool,
    pub browser: String,
    pub headless: bool,
    pub stealth_mode: bool,
    pub context_isolation: bool,
}

impl Default for PlaywrightConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            browser: "chromium".to_string(),
            headless: false,
            stealth_mode: false,
            context_isolation: true,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CVOCRConfig {
    pub enabled: bool,
    pub ocr_engine: String,
    pub tesseract_path: String,
    pub paddleocr_lang: String,
    pub confidence_threshold: f32,
    pub template_matching_enabled: bool,
}

impl Default for CVOCRConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            ocr_engine: "tesseract".to_string(),
            tesseract_path: "tesseract".to_string(),
            paddleocr_lang: "en".to_string(),
            confidence_threshold: 0.7,
            template_matching_enabled: true,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AutomationCoordinatorConfig {
    pub cross_app_enabled: bool,
    pub clipboard_sync: bool,
    pub window_management: bool,
    pub safety_confirmations: bool,
    pub max_workflow_steps: u32,
}

impl Default for AutomationCoordinatorConfig {
    fn default() -> Self {
        Self {
            cross_app_enabled: true,
            clipboard_sync: true,
            window_management: true,
            safety_confirmations: true,
            max_workflow_steps: 50,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AutomationConfig {
    pub enabled: bool,
    pub perception_hierarchy: Vec<String>,
    pub uia: UIAConfig,
    pub playwright: PlaywrightConfig,
    pub cv_ocr: CVOCRConfig,
    pub coordinator: AutomationCoordinatorConfig,
}

impl Default for AutomationConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            perception_hierarchy: vec!["uia".to_string(), "playwright".to_string(), "cv_ocr".to_string()],
            uia: UIAConfig::default(),
            playwright: PlaywrightConfig::default(),
            cv_ocr: CVOCRConfig::default(),
            coordinator: AutomationCoordinatorConfig::default(),
        }
    }
}

// =============================================================================
// Security Configuration
// =============================================================================

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CredentialsConfig {
    pub primary_provider: String,
    pub fallback_providers: Vec<String>,
}

impl Default for CredentialsConfig {
    fn default() -> Self {
        Self {
            primary_provider: "windows_credential_manager".to_string(),
            fallback_providers: vec!["keyring".to_string(), "vault".to_string(), "env".to_string()],
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NetworkConfig {
    pub egress_control_enabled: bool,
    pub default_policy: String,
    pub allowlist: Vec<String>,
    pub denylist: Vec<String>,
    pub dns_blocking_enabled: bool,
    pub proxy_interception_enabled: bool,
}

impl Default for NetworkConfig {
    fn default() -> Self {
        Self {
            egress_control_enabled: true,
            default_policy: "deny".to_string(),
            allowlist: vec![
                "api.openai.com".to_string(),
                "api.anthropic.com".to_string(),
                "generativelanguage.googleapis.com".to_string(),
                "localhost".to_string(),
                "127.0.0.1".to_string(),
            ],
            denylist: Vec::new(),
            dns_blocking_enabled: true,
            proxy_interception_enabled: true,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PromptInjectionConfig {
    pub enabled: bool,
    pub model: String,
    pub heuristic_rules_enabled: bool,
    pub integration_points: Vec<String>,
}

impl Default for PromptInjectionConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            model: "promptguard".to_string(),
            heuristic_rules_enabled: true,
            integration_points: vec![
                "model_router_input".to_string(),
                "agent_input".to_string(),
                "automation_input".to_string(),
            ],
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SecurityAuditConfig {
    pub enabled: bool,
    pub tamper_evident: bool,
    pub encryption_enabled: bool,
    pub log_credential_access: bool,
    pub log_network_blocks: bool,
    pub log_prompt_injections: bool,
}

impl Default for SecurityAuditConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            tamper_evident: true,
            encryption_enabled: true,
            log_credential_access: true,
            log_network_blocks: true,
            log_prompt_injections: true,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EncryptionConfig {
    pub algorithm: String,
    pub key_derivation: String,
    pub key_rotation_days: u32,
    pub field_level_encryption: bool,
}

impl Default for EncryptionConfig {
    fn default() -> Self {
        Self {
            algorithm: "AES-256-GCM".to_string(),
            key_derivation: "PBKDF2".to_string(),
            key_rotation_days: 90,
            field_level_encryption: true,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SecurityConfig {
    pub credentials: CredentialsConfig,
    pub network: NetworkConfig,
    pub prompt_injection: PromptInjectionConfig,
    pub audit: SecurityAuditConfig,
    pub encryption: EncryptionConfig,
}

impl Default for SecurityConfig {
    fn default() -> Self {
        Self {
            credentials: CredentialsConfig::default(),
            network: NetworkConfig::default(),
            prompt_injection: PromptInjectionConfig::default(),
            audit: SecurityAuditConfig::default(),
            encryption: EncryptionConfig::default(),
        }
    }
}

// =============================================================================
// Agent Configuration
// =============================================================================

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentSpecialistConfig {
    pub enabled: bool,
    pub model: String,
}

impl Default for AgentSpecialistConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            model: "gpt-4o-mini".to_string(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentCoordinatorConfig {
    pub enabled: bool,
    pub model: String,
    pub max_delegation_depth: u32,
    pub timeout_seconds: u32,
}

impl Default for AgentCoordinatorConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            model: "gpt-4o".to_string(),
            max_delegation_depth: 5,
            timeout_seconds: 300,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentRegistryConfig {
    pub heartbeat_interval_seconds: u32,
    pub max_restarts: u32,
    pub health_check_timeout: u32,
}

impl Default for AgentRegistryConfig {
    fn default() -> Self {
        Self {
            heartbeat_interval_seconds: 30,
            max_restarts: 3,
            health_check_timeout: 10,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentsConfig {
    pub enabled: bool,
    pub coordinator: AgentCoordinatorConfig,
    pub specialists: HashMap<String, AgentSpecialistConfig>,
    pub registry: AgentRegistryConfig,
}

impl Default for AgentsConfig {
    fn default() -> Self {
        let mut specialists = HashMap::new();
        specialists.insert("planner".to_string(), AgentSpecialistConfig { enabled: true, model: "gpt-4o".to_string() });
        specialists.insert("coder".to_string(), AgentSpecialistConfig { enabled: true, model: "gpt-4o".to_string() });
        specialists.insert("researcher".to_string(), AgentSpecialistConfig { enabled: true, model: "gemini-1.5-pro".to_string() });
        specialists.insert("analyst".to_string(), AgentSpecialistConfig { enabled: true, model: "claude-3-5-sonnet-20241022".to_string() });
        specialists.insert("creative".to_string(), AgentSpecialistConfig { enabled: true, model: "gpt-4o".to_string() });
        specialists.insert("automation".to_string(), AgentSpecialistConfig { enabled: true, model: "gpt-4o-mini".to_string() });
        specialists.insert("memory".to_string(), AgentSpecialistConfig { enabled: true, model: "gpt-4o-mini".to_string() });
        specialists.insert("security".to_string(), AgentSpecialistConfig { enabled: true, model: "gpt-4o-mini".to_string() });
        specialists.insert("reviewer".to_string(), AgentSpecialistConfig { enabled: true, model: "gpt-4o".to_string() });
        specialists.insert("communicator".to_string(), AgentSpecialistConfig { enabled: true, model: "gpt-4o-mini".to_string() });
        specialists.insert("scheduler".to_string(), AgentSpecialistConfig { enabled: true, model: "gpt-4o-mini".to_string() });

        Self {
            enabled: true,
            coordinator: AgentCoordinatorConfig::default(),
            specialists,
            registry: AgentRegistryConfig::default(),
        }
    }
}

// =============================================================================
// Frontend Configuration
// =============================================================================

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FrontendConfig {
    pub api_base_url: String,
    pub ws_base_url: String,
    pub theme: String,
    pub language: String,
    pub auto_refresh_interval: u32,
}

impl Default for FrontendConfig {
    fn default() -> Self {
        Self {
            api_base_url: "http://localhost:8000".to_string(),
            ws_base_url: "ws://localhost:8000".to_string(),
            theme: "dark".to_string(),
            language: "en".to_string(),
            auto_refresh_interval: 30000,
        }
    }
}

// =============================================================================
// Telemetry Configuration
// =============================================================================

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LoggingConfig {
    pub level: LogLevel,
    pub format: String,
    pub output: String,
    pub correlation_id_header: String,
}

impl Default for LoggingConfig {
    fn default() -> Self {
        Self {
            level: LogLevel::Info,
            format: "json".to_string(),
            output: "stdout".to_string(),
            correlation_id_header: "X-Correlation-ID".to_string(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MetricsConfig {
    pub enabled: bool,
    pub port: u16,
    pub path: String,
}

impl Default for MetricsConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            port: 9090,
            path: "/metrics".to_string(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TracingConfig {
    pub enabled: bool,
    pub jaeger_endpoint: String,
    pub sample_rate: f32,
}

impl Default for TracingConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            jaeger_endpoint: "http://localhost:4317".to_string(),
            sample_rate: 0.1,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HealthChecksConfig {
    pub enabled: bool,
    pub interval_seconds: u32,
}

impl Default for HealthChecksConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            interval_seconds: 30,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TelemetryConfig {
    pub enabled: bool,
    pub logging: LoggingConfig,
    pub metrics: MetricsConfig,
    pub tracing: TracingConfig,
    pub health_checks: HealthChecksConfig,
}

impl Default for TelemetryConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            logging: LoggingConfig::default(),
            metrics: MetricsConfig::default(),
            tracing: TracingConfig::default(),
            health_checks: HealthChecksConfig::default(),
        }
    }
}

// =============================================================================
// Events Configuration
// =============================================================================

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LocalEventBusConfig {
    pub enabled: bool,
    pub worker_count: u32,
    pub queue_size: u32,
    pub dead_letter_queue_size: u32,
}

impl Default for LocalEventBusConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            worker_count: 4,
            queue_size: 10000,
            dead_letter_queue_size: 1000,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DistributedEventBusConfig {
    pub enabled: bool,
    pub redis_streams_enabled: bool,
    pub consumer_group: String,
}

impl Default for DistributedEventBusConfig {
    fn default() -> Self {
        Self {
            enabled: false,
            redis_streams_enabled: true,
            consumer_group: "arise-events".to_string(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EventStoreConfig {
    pub enabled: bool,
    pub r#type: String,
    pub path: String,
    pub wal_mode: bool,
}

impl Default for EventStoreConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            r#type: "sqlite".to_string(),
            path: "./data/events.db".to_string(),
            wal_mode: true,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProjectionsConfig {
    pub enabled: bool,
    pub checkpoint_interval: u32,
}

impl Default for ProjectionsConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            checkpoint_interval: 100,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EventTracingConfig {
    pub enabled: bool,
    pub correlation_header: String,
}

impl Default for EventTracingConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            correlation_header: "X-Correlation-ID".to_string(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EventsConfig {
    pub local: LocalEventBusConfig,
    pub distributed: DistributedEventBusConfig,
    pub store: EventStoreConfig,
    pub projections: ProjectionsConfig,
    pub tracing: EventTracingConfig,
}

impl Default for EventsConfig {
    fn default() -> Self {
        Self {
            local: LocalEventBusConfig::default(),
            distributed: DistributedEventBusConfig::default(),
            store: EventStoreConfig::default(),
            projections: ProjectionsConfig::default(),
            tracing: EventTracingConfig::default(),
        }
    }
}

// =============================================================================
// Main Application Configuration
// =============================================================================

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AppConfig {
    pub name: String,
    pub version: String,
    pub environment: Environment,
    pub debug: bool,

    pub database: DatabaseConfig,
    pub redis: RedisConfig,
    pub model_router: ModelRouterConfig,
    pub task_engine: TaskEngineConfig,
    pub policy_engine: PolicyEngineConfig,
    pub voice: VoiceConfig,
    pub memory: MemoryConfig,
    pub automation: AutomationConfig,
    pub security: SecurityConfig,
    pub agents: AgentsConfig,
    pub frontend: FrontendConfig,
    pub telemetry: TelemetryConfig,
    pub events: EventsConfig,
}

impl Default for AppConfig {
    fn default() -> Self {
        Self {
            name: "ARISE".to_string(),
            version: "1.0.0".to_string(),
            environment: Environment::Development,
            debug: true,
            database: DatabaseConfig::default(),
            redis: RedisConfig::default(),
            model_router: ModelRouterConfig::default(),
            task_engine: TaskEngineConfig::default(),
            policy_engine: PolicyEngineConfig::default(),
            voice: VoiceConfig::default(),
            memory: MemoryConfig::default(),
            automation: AutomationConfig::default(),
            security: SecurityConfig::default(),
            agents: AgentsConfig::default(),
            frontend: FrontendConfig::default(),
            telemetry: TelemetryConfig::default(),
            events: EventsConfig::default(),
        }
    }
}

/// Load configuration from a YAML file
pub fn load_config_from_file(path: &PathBuf) -> Result<AppConfig, Box<dyn std::error::Error>> {
    let content = std::fs::read_to_string(path)?;
    let config: AppConfig = serde_yaml::from_str(&content)?;
    Ok(config)
}

/// Save configuration to a YAML file
pub fn save_config_to_file(config: &AppConfig, path: &PathBuf) -> Result<(), Box<dyn std::error::Error>> {
    let content = serde_yaml::to_string(config)?;
    std::fs::write(path, content)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_default_config() {
        let config = AppConfig::default();
        assert_eq!(config.name, "ARISE");
        assert_eq!(config.environment, Environment::Development);
        assert!(config.debug);
    }

    #[test]
    fn test_serialization() {
        let config = AppConfig::default();
        let yaml = serde_yaml::to_string(&config).unwrap();
        let parsed: AppConfig = serde_yaml::from_str(&yaml).unwrap();
        assert_eq!(config.name, parsed.name);
    }
}