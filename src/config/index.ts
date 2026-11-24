/**
 * ARISE Frontend Configuration
 * TypeScript configuration types matching the Python backend config
 */

// =============================================================================
// Enums
// =============================================================================

export enum LogLevel {
  DEBUG = 'DEBUG',
  INFO = 'INFO',
  WARNING = 'WARNING',
  ERROR = 'ERROR',
  CRITICAL = 'CRITICAL',
}

export enum Environment {
  DEVELOPMENT = 'development',
  STAGING = 'staging',
  PRODUCTION = 'production',
  TEST = 'test',
}

export enum ProviderType {
  OPENAI = 'openai',
  ANTHROPIC = 'anthropic',
  GEMINI = 'gemini',
  OLLAMA = 'ollama',
  AZURE_OPENAI = 'azure_openai',
  VERTEX_AI = 'vertex_ai',
}

export enum PrivacyMode {
  OFF = 'off',
  STANDARD = 'standard',
  REDACT = 'redact',
  LOCAL_ONLY = 'local_only',
}

export enum RiskLevel {
  R0 = 'R0',
  R1 = 'R1',
  R2 = 'R2',
  R3 = 'R3',
  R4 = 'R4',
}

export enum MemoryKind {
  SEMANTIC = 'SEMANTIC',
  EPISODIC = 'EPISODIC',
  PROCEDURAL = 'PROCEDURAL',
  PREFERENCE = 'PREFERENCE',
  WORKING = 'WORKING',
}

export enum TaskKind {
  SHELL_EXEC = 'shell.exec',
  FILE_READ = 'filesystem.read',
  FILE_WRITE = 'filesystem.write',
  FILE_LIST = 'filesystem.list',
  HTTP_REQUEST = 'http.request',
  BROWSER_NAVIGATE = 'browser.navigate',
  BROWSER_CLICK = 'browser.click',
  BROWSER_EXTRACT = 'browser.extract',
  UIA_FIND = 'uia.find',
  UIA_CLICK = 'uia.click',
  UIA_INPUT = 'uia.input',
  MEMORY_STORE = 'memory.store',
  MEMORY_QUERY = 'memory.query',
  AGENT_DELEGATE = 'agent.delegate',
  AGENT_VERIFY = 'agent.verify',
}

export enum TaskStatus {
  CREATED = 'CREATED',
  QUEUED = 'QUEUED',
  UNDERSTANDING = 'UNDERSTANDING',
  PLANNING = 'PLANNING',
  READY = 'READY',
  RUNNING = 'RUNNING',
  WAITING_APPROVAL = 'WAITING_APPROVAL',
  WAITING_TOOL = 'WAITING_TOOL',
  WAITING_MODEL = 'WAITING_MODEL',
  WAITING_RESOURCE = 'WAITING_RESOURCE',
  WAITING_HUMAN = 'WAITING_HUMAN',
  WAITING_AGENT = 'WAITING_AGENT',
  VERIFYING = 'VERIFYING',
  COMPLETED = 'COMPLETED',
  FAILED = 'FAILED',
  CANCELLED = 'CANCELLED',
  PAUSED = 'PAUSED',
  RETRYING = 'RETRYING',
  CHECKPOINTING = 'CHECKPOINTING',
  RESTORING = 'RESTORING',
  DELEGATING = 'DELEGATING',
  AGGREGATING = 'AGGREGATING',
  SYNTHESIZING = 'SYNTHESIZING',
  VALIDATING = 'VALIDATING',
  ARCHIVING = 'ARCHIVING',
  EXPIRED = 'EXPIRED',
  TIMEOUT = 'TIMEOUT',
  UNKNOWN = 'UNKNOWN',
}

export enum TaskPriority {
  LOWEST = 1,
  LOW = 2,
  BELOW_NORMAL = 3,
  NORMAL = 5,
  ABOVE_NORMAL = 6,
  HIGH = 7,
  VERY_HIGH = 8,
  CRITICAL = 9,
  EMERGENCY = 10,
}

export enum FlagType {
  BOOLEAN = 'boolean',
  STRING = 'string',
  INTEGER = 'integer',
  FLOAT = 'float',
  JSON = 'json',
}

export enum FlagStatus {
  ACTIVE = 'active',
  INACTIVE = 'inactive',
  ARCHIVED = 'archived',
}

// =============================================================================
// Database Configuration
// =============================================================================

export interface DatabaseConfig {
  url: string;
  pool_size: number;
  max_overflow: number;
  pool_timeout: number;
  pool_recycle: number;
  echo: boolean;
  echo_pool: boolean;
}

export interface RedisConfig {
  url: string;
  max_connections: number;
  socket_timeout: number;
  socket_connect_timeout: number;
  retry_on_timeout: boolean;
  decode_responses: boolean;
}

// =============================================================================
// Model Router Configuration
// =============================================================================

export interface ModelProviderConfig {
  enabled: boolean;
  api_key?: string;
  base_url?: string;
  models: string[];
  default_model?: string;
  timeout: number;
  max_retries: number;
  api_version?: string;
  endpoint?: string;
  project_id?: string;
  location?: string;
}

export interface ModelRouterConfig {
  default_provider: ProviderType;
  privacy_mode: PrivacyMode;
  fallback_chain: ProviderType[];
  providers: Record<ProviderType, ModelProviderConfig>;
  cost_tracking_enabled: boolean;
  circuit_breaker_enabled: boolean;
  circuit_breaker_threshold: number;
  circuit_breaker_timeout: number;
}

// =============================================================================
// Task Engine Configuration
// =============================================================================

export interface SandboxConfig {
  enabled: boolean;
  type: string;
  docker_image: string;
  memory_limit_mb: number;
  cpu_limit_percent: number;
  disk_limit_mb: number;
  network_enabled: boolean;
  timeout_seconds: number;
}

export interface TaskEngineConfig {
  max_concurrent_tasks: number;
  default_priority: TaskPriority;
  checkpoint_interval_seconds: number;
  max_checkpoints_per_task: number;
  task_timeout_seconds: number;
  sandbox: SandboxConfig;
  queue_priority_levels: number;
  fair_scheduling: boolean;
  persistence_enabled: boolean;
}

// =============================================================================
// Policy Engine Configuration
// =============================================================================

export interface RiskLevelConfig {
  name: string;
  auto_approve: boolean;
  requires_mfa: boolean;
  timeout_seconds: number;
}

export interface PolicyEngineConfig {
  risk_levels: Record<RiskLevel, RiskLevelConfig>;
  capabilities: string[];
  default_risk_level: RiskLevel;
  approval_ui_enabled: boolean;
  audit_enabled: boolean;
}

// =============================================================================
// Voice Configuration
// =============================================================================

export interface WakeWordConfig {
  enabled: boolean;
  model: string;
  sensitivity: number;
  audio_device: string;
  dormant_cpu_percent: number;
}

export interface ASRConfig {
  primary: string;
  fallback_chain: string[];
  language: string;
  vad_enabled: boolean;
  vad_threshold: number;
}

export interface TTSConfig {
  primary: string;
  fallback_chain: string[];
  voice: string;
  streaming: boolean;
}

export interface VoiceSessionConfig {
  timeout_seconds: number;
  max_duration_seconds: number;
  barge_in_enabled: boolean;
  context_preservation: boolean;
}

export interface VoiceConfig {
  enabled: boolean;
  wake_word: WakeWordConfig;
  asr: ASRConfig;
  tts: TTSConfig;
  session: VoiceSessionConfig;
}

// =============================================================================
// Memory Configuration
// =============================================================================

export interface MemoryKindConfig {
  enabled: boolean;
  max_items: number;
  ttl_days: number;
}

export interface ChromaDBConfig {
  enabled: boolean;
  persist_directory: string;
  collection_name: string;
}

export interface SQLiteFTSConfig {
  enabled: boolean;
  database_path: string;
}

export interface ConsolidationConfig {
  enabled: boolean;
  interval_hours: number;
  working_to_episodic_threshold: number;
  episodic_to_semantic_threshold: number;
  preference_extraction_enabled: boolean;
  procedural_learning_enabled: boolean;
}

export interface MemoryGovernanceConfig {
  pii_detection_enabled: boolean;
  pii_action: string;
  encryption_enabled: boolean;
  max_memories_per_kind: number;
  lru_eviction_enabled: boolean;
}

export interface MemoryConfig {
  enabled: boolean;
  kinds: Record<MemoryKind, MemoryKindConfig>;
  stores: {
    chromadb: ChromaDBConfig;
    sqlite_fts: SQLiteFTSConfig;
  };
  consolidation: ConsolidationConfig;
  governance: MemoryGovernanceConfig;
}

// =============================================================================
// Automation Configuration
// =============================================================================

export interface UIAConfig {
  enabled: boolean;
  backend: string;
  retry_attempts: number;
  retry_delay_ms: number;
  screenshot_on_failure: boolean;
}

export interface PlaywrightConfig {
  enabled: boolean;
  browser: string;
  headless: boolean;
  stealth_mode: boolean;
  context_isolation: boolean;
}

export interface CVOCRConfig {
  enabled: boolean;
  ocr_engine: string;
  tesseract_path: string;
  paddleocr_lang: string;
  confidence_threshold: number;
  template_matching_enabled: boolean;
}

export interface AutomationCoordinatorConfig {
  cross_app_enabled: boolean;
  clipboard_sync: boolean;
  window_management: boolean;
  safety_confirmations: boolean;
  max_workflow_steps: number;
}

export interface AutomationConfig {
  enabled: boolean;
  perception_hierarchy: string[];
  uia: UIAConfig;
  playwright: PlaywrightConfig;
  cv_ocr: CVOCRConfig;
  coordinator: AutomationCoordinatorConfig;
}

// =============================================================================
// Security Configuration
// =============================================================================

export interface CredentialsConfig {
  primary_provider: string;
  fallback_providers: string[];
}

export interface NetworkConfig {
  egress_control_enabled: boolean;
  default_policy: string;
  allowlist: string[];
  denylist: string[];
  dns_blocking_enabled: boolean;
  proxy_interception_enabled: boolean;
}

export interface PromptInjectionConfig {
  enabled: boolean;
  model: string;
  heuristic_rules_enabled: boolean;
  integration_points: string[];
}

export interface SecurityAuditConfig {
  enabled: boolean;
  tamper_evident: boolean;
  encryption_enabled: boolean;
  log_credential_access: boolean;
  log_network_blocks: boolean;
  log_prompt_injections: boolean;
}

export interface EncryptionConfig {
  algorithm: string;
  key_derivation: string;
  key_rotation_days: number;
  field_level_encryption: boolean;
}

export interface SecurityConfig {
  credentials: CredentialsConfig;
  network: NetworkConfig;
  prompt_injection: PromptInjectionConfig;
  audit: SecurityAuditConfig;
  encryption: EncryptionConfig;
}

// =============================================================================
// Agent Configuration
// =============================================================================

export interface AgentSpecialistConfig {
  enabled: boolean;
  model: string;
}

export interface AgentCoordinatorConfig {
  enabled: boolean;
  model: string;
  max_delegation_depth: number;
  timeout_seconds: number;
}

export interface AgentRegistryConfig {
  heartbeat_interval_seconds: number;
  max_restarts: number;
  health_check_timeout: number;
}

export interface AgentsConfig {
  enabled: boolean;
  coordinator: AgentCoordinatorConfig;
  specialists: Record<string, AgentSpecialistConfig>;
  registry: AgentRegistryConfig;
}

// =============================================================================
// Frontend Configuration
// =============================================================================

export interface FrontendConfig {
  api_base_url: string;
  ws_base_url: string;
  theme: string;
  language: string;
  auto_refresh_interval: number;
}

// =============================================================================
// Telemetry Configuration
// =============================================================================

export interface LoggingConfig {
  level: LogLevel;
  format: string;
  output: string;
  correlation_id_header: string;
}

export interface MetricsConfig {
  enabled: boolean;
  port: number;
  path: string;
}

export interface TracingConfig {
  enabled: boolean;
  jaeger_endpoint: string;
  sample_rate: number;
}

export interface HealthChecksConfig {
  enabled: boolean;
  interval_seconds: number;
}

export interface TelemetryConfig {
  enabled: boolean;
  logging: LoggingConfig;
  metrics: MetricsConfig;
  tracing: TracingConfig;
  health_checks: HealthChecksConfig;
}

// =============================================================================
// Events Configuration
// =============================================================================

export interface LocalEventBusConfig {
  enabled: boolean;
  worker_count: number;
  queue_size: number;
  dead_letter_queue_size: number;
}

export interface DistributedEventBusConfig {
  enabled: boolean;
  redis_streams_enabled: boolean;
  consumer_group: string;
}

export interface EventStoreConfig {
  enabled: boolean;
  type: string;
  path: string;
  wal_mode: boolean;
}

export interface ProjectionsConfig {
  enabled: boolean;
  checkpoint_interval: number;
}

export interface EventTracingConfig {
  enabled: boolean;
  correlation_header: string;
}

export interface EventsConfig {
  local: LocalEventBusConfig;
  distributed: DistributedEventBusConfig;
  store: EventStoreConfig;
  projections: ProjectionsConfig;
  tracing: EventTracingConfig;
}

// =============================================================================
// Main Application Configuration
// =============================================================================

export interface AppConfig {
  // Core app settings
  name: string;
  version: string;
  environment: Environment;
  debug: boolean;

  // Sub-configurations
  database: DatabaseConfig;
  redis: RedisConfig;
  model_router: ModelRouterConfig;
  task_engine: TaskEngineConfig;
  policy_engine: PolicyEngineConfig;
  voice: VoiceConfig;
  memory: MemoryConfig;
  automation: AutomationConfig;
  security: SecurityConfig;
  agents: AgentsConfig;
  frontend: FrontendConfig;
  telemetry: TelemetryConfig;
  events: EventsConfig;
}

// =============================================================================
// Feature Flags
// =============================================================================

export interface FeatureFlag {
  key: string;
  name: string;
  description: string;
  flag_type: FlagType;
  default_value: any;
  status: FlagStatus;
  tags: string[];
  rollout_percentage: number;
  targeting_rules: TargetingRule[];
  created_at: string;
  updated_at: string;
  created_by: string;
}

export interface TargetingRule {
  conditions: Record<string, any>;
  value: any;
}

// =============================================================================
// Config API Types
// =============================================================================

export interface ConfigResponse {
  config: AppConfig;
  version: string;
  environment: Environment;
}

export interface FeatureFlagsResponse {
  flags: Record<string, FeatureFlag>;
}

export interface FeatureFlagEvaluationRequest {
  key: string;
  context?: Record<string, any>;
}

export interface FeatureFlagEvaluationResponse {
  key: string;
  value: any;
  source: 'default' | 'targeting' | 'rollout';
}

// =============================================================================
// Default Configuration
// =============================================================================

export const defaultConfig: AppConfig = {
  name: 'ARISE',
  version: '1.0.0',
  environment: Environment.DEVELOPMENT,
  debug: true,
  database: {
    url: 'sqlite+aiosqlite:///./arise.db',
    pool_size: 5,
    max_overflow: 10,
    pool_timeout: 30,
    pool_recycle: 3600,
    echo: false,
    echo_pool: false,
  },
  redis: {
    url: 'redis://localhost:6379/0',
    max_connections: 50,
    socket_timeout: 5,
    socket_connect_timeout: 5,
    retry_on_timeout: true,
    decode_responses: true,
  },
  model_router: {
    default_provider: ProviderType.OPENAI,
    privacy_mode: PrivacyMode.STANDARD,
    fallback_chain: [
      ProviderType.OPENAI,
      ProviderType.ANTHROPIC,
      ProviderType.GEMINI,
      ProviderType.OLLAMA,
    ],
    providers: {
      [ProviderType.OPENAI]: {
        enabled: true,
        models: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo'],
        default_model: 'gpt-4o-mini',
        timeout: 60,
        max_retries: 3,
      },
      [ProviderType.ANTHROPIC]: {
        enabled: true,
        models: ['claude-3-5-sonnet-20241022', 'claude-3-5-haiku-20241022'],
        default_model: 'claude-3-5-sonnet-20241022',
        timeout: 60,
        max_retries: 3,
      },
      [ProviderType.GEMINI]: {
        enabled: true,
        models: ['gemini-1.5-pro', 'gemini-1.5-flash'],
        default_model: 'gemini-1.5-flash',
        timeout: 60,
        max_retries: 3,
      },
      [ProviderType.OLLAMA]: {
        enabled: true,
        base_url: 'http://localhost:11434',
        models: ['llama3.1:8b', 'llama3.1:70b', 'codellama:13b'],
        default_model: 'llama3.1:8b',
        timeout: 120,
        max_retries: 2,
      },
      [ProviderType.AZURE_OPENAI]: {
        enabled: false,
        models: [],
        default_model: undefined,
        timeout: 60,
        max_retries: 3,
      },
      [ProviderType.VERTEX_AI]: {
        enabled: false,
        models: [],
        default_model: undefined,
        timeout: 60,
        max_retries: 3,
      },
    },
    cost_tracking_enabled: true,
    circuit_breaker_enabled: true,
    circuit_breaker_threshold: 5,
    circuit_breaker_timeout: 60,
  },
  task_engine: {
    max_concurrent_tasks: 10,
    default_priority: TaskPriority.NORMAL,
    checkpoint_interval_seconds: 30,
    max_checkpoints_per_task: 100,
    task_timeout_seconds: 3600,
    sandbox: {
      enabled: true,
      type: 'docker',
      docker_image: 'arise/sandbox:latest',
      memory_limit_mb: 512,
      cpu_limit_percent: 50,
      disk_limit_mb: 1024,
      network_enabled: false,
      timeout_seconds: 300,
    },
    queue_priority_levels: 10,
    fair_scheduling: true,
    persistence_enabled: true,
  },
  policy_engine: {
    risk_levels: {
      [RiskLevel.R0]: { name: 'Read Only', auto_approve: true, requires_mfa: false, timeout_seconds: 0 },
      [RiskLevel.R1]: { name: 'Local Write', auto_approve: true, requires_mfa: false, timeout_seconds: 300 },
      [RiskLevel.R2]: { name: 'System Change', auto_approve: false, requires_mfa: false, timeout_seconds: 600 },
      [RiskLevel.R3]: { name: 'External Communication', auto_approve: false, requires_mfa: true, timeout_seconds: 300 },
      [RiskLevel.R4]: { name: 'Irreversible', auto_approve: false, requires_mfa: true, timeout_seconds: 60 },
    },
    capabilities: [
      'task.execute', 'task.cancel', 'filesystem.read', 'filesystem.write', 'filesystem.delete',
      'shell.exec', 'network.http', 'network.websocket', 'browser.navigate', 'browser.click',
      'browser.extract', 'uia.find', 'uia.click', 'uia.input', 'memory.store', 'memory.query',
      'memory.delete', 'voice.listen', 'voice.speak', 'agent.delegate', 'agent.verify',
      'config.read', 'config.write', 'secrets.read', 'secrets.write', 'system.shutdown',
      'system.reboot', 'credentials.read', 'credentials.write',
    ],
    default_risk_level: RiskLevel.R1,
    approval_ui_enabled: true,
    audit_enabled: true,
  },
  voice: {
    enabled: true,
    wake_word: {
      enabled: true,
      model: 'hey_arise',
      sensitivity: 0.5,
      audio_device: 'default',
      dormant_cpu_percent: 1.0,
    },
    asr: {
      primary: 'sherpa_onnx',
      fallback_chain: ['sherpa_onnx', 'whisper', 'gemini', 'azure'],
      language: 'auto',
      vad_enabled: true,
      vad_threshold: 0.5,
    },
    tts: {
      primary: 'gemini',
      fallback_chain: ['gemini', 'coqui', 'elevenlabs', 'azure'],
      voice: 'en-US-Neural2-F',
      streaming: true,
    },
    session: {
      timeout_seconds: 30,
      max_duration_seconds: 3600,
      barge_in_enabled: true,
      context_preservation: true,
    },
  },
  memory: {
    enabled: true,
    kinds: {
      [MemoryKind.SEMANTIC]: { enabled: true, max_items: 100000, ttl_days: 3650 },
      [MemoryKind.EPISODIC]: { enabled: true, max_items: 50000, ttl_days: 365 },
      [MemoryKind.PROCEDURAL]: { enabled: true, max_items: 10000, ttl_days: 3650 },
      [MemoryKind.PREFERENCE]: { enabled: true, max_items: 1000, ttl_days: 3650 },
      [MemoryKind.WORKING]: { enabled: true, max_items: 1000, ttl_days: 7 },
    },
    stores: {
      chromadb: {
        enabled: true,
        persist_directory: './data/chromadb',
        collection_name: 'arise_memories',
      },
      sqlite_fts: {
        enabled: true,
        database_path: './data/memory_fts.db',
      },
    },
    consolidation: {
      enabled: true,
      interval_hours: 6,
      working_to_episodic_threshold: 0.7,
      episodic_to_semantic_threshold: 0.8,
      preference_extraction_enabled: true,
      procedural_learning_enabled: true,
    },
    governance: {
      pii_detection_enabled: true,
      pii_action: 'redact',
      encryption_enabled: true,
      max_memories_per_kind: 100000,
      lru_eviction_enabled: true,
    },
  },
  automation: {
    enabled: true,
    perception_hierarchy: ['uia', 'playwright', 'cv_ocr'],
    uia: {
      enabled: true,
      backend: 'comtypes',
      retry_attempts: 3,
      retry_delay_ms: 100,
      screenshot_on_failure: true,
    },
    playwright: {
      enabled: true,
      browser: 'chromium',
      headless: false,
      stealth_mode: false,
      context_isolation: true,
    },
    cv_ocr: {
      enabled: true,
      ocr_engine: 'tesseract',
      tesseract_path: 'tesseract',
      paddleocr_lang: 'en',
      confidence_threshold: 0.7,
      template_matching_enabled: true,
    },
    coordinator: {
      cross_app_enabled: true,
      clipboard_sync: true,
      window_management: true,
      safety_confirmations: true,
      max_workflow_steps: 50,
    },
  },
  security: {
    credentials: {
      primary_provider: 'windows_credential_manager',
      fallback_providers: ['keyring', 'vault', 'env'],
    },
    network: {
      egress_control_enabled: true,
      default_policy: 'deny',
      allowlist: [
        'api.openai.com',
        'api.anthropic.com',
        'generativelanguage.googleapis.com',
        'localhost',
        '127.0.0.1',
      ],
      denylist: [],
      dns_blocking_enabled: true,
      proxy_interception_enabled: true,
    },
    prompt_injection: {
      enabled: true,
      model: 'promptguard',
      heuristic_rules_enabled: true,
      integration_points: ['model_router_input', 'agent_input', 'automation_input'],
    },
    audit: {
      enabled: true,
      tamper_evident: true,
      encryption_enabled: true,
      log_credential_access: true,
      log_network_blocks: true,
      log_prompt_injections: true,
    },
    encryption: {
      algorithm: 'AES-256-GCM',
      key_derivation: 'PBKDF2',
      key_rotation_days: 90,
      field_level_encryption: true,
    },
  },
  agents: {
    enabled: true,
    coordinator: {
      enabled: true,
      model: 'gpt-4o',
      max_delegation_depth: 5,
      timeout_seconds: 300,
    },
    specialists: {
      planner: { enabled: true, model: 'gpt-4o' },
      coder: { enabled: true, model: 'gpt-4o' },
      researcher: { enabled: true, model: 'gemini-1.5-pro' },
      analyst: { enabled: true, model: 'claude-3-5-sonnet-20241022' },
      creative: { enabled: true, model: 'gpt-4o' },
      automation: { enabled: true, model: 'gpt-4o-mini' },
      memory: { enabled: true, model: 'gpt-4o-mini' },
      security: { enabled: true, model: 'gpt-4o-mini' },
      reviewer: { enabled: true, model: 'gpt-4o' },
      communicator: { enabled: true, model: 'gpt-4o-mini' },
      scheduler: { enabled: true, model: 'gpt-4o-mini' },
    },
    registry: {
      heartbeat_interval_seconds: 30,
      max_restarts: 3,
      health_check_timeout: 10,
    },
  },
  frontend: {
    api_base_url: 'http://localhost:8000',
    ws_base_url: 'ws://localhost:8000',
    theme: 'dark',
    language: 'en',
    auto_refresh_interval: 30000,
  },
  telemetry: {
    enabled: true,
    logging: {
      level: LogLevel.INFO,
      format: 'json',
      output: 'stdout',
      correlation_id_header: 'X-Correlation-ID',
    },
    metrics: {
      enabled: true,
      port: 9090,
      path: '/metrics',
    },
    tracing: {
      enabled: true,
      jaeger_endpoint: 'http://localhost:4317',
      sample_rate: 0.1,
    },
    health_checks: {
      enabled: true,
      interval_seconds: 30,
    },
  },
  events: {
    local: {
      enabled: true,
      worker_count: 4,
      queue_size: 10000,
      dead_letter_queue_size: 1000,
    },
    distributed: {
      enabled: false,
      redis_streams_enabled: true,
      consumer_group: 'arise-events',
    },
    store: {
      enabled: true,
      type: 'sqlite',
      path: './data/events.db',
      wal_mode: true,
    },
    projections: {
      enabled: true,
      checkpoint_interval: 100,
    },
    tracing: {
      enabled: true,
      correlation_header: 'X-Correlation-ID',
    },
  },
};

// =============================================================================
// Config Loader
// =============================================================================

let configCache: AppConfig | null = null;

export async function loadConfig(): Promise<AppConfig> {
  if (configCache) {
    return configCache;
  }

  try {
    const response = await fetch('/api/config');
    if (response.ok) {
      const data = await response.json();
      configCache = data.config;
      return configCache;
    }
  } catch (error) {
    console.warn('Failed to load config from API, using defaults:', error);
  }

  configCache = defaultConfig;
  return defaultConfig;
}

export function getConfig(): AppConfig | null {
  return configCache;
}

export function setConfig(config: AppConfig): void {
  configCache = config;
}

export function resetConfig(): void {
  configCache = null;
}

// =============================================================================
// Feature Flag Helpers
// =============================================================================

export async function isFeatureEnabled(key: string, context?: Record<string, any>): Promise<boolean> {
  try {
    const response = await fetch('/api/feature-flags/evaluate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key, context }),
    });
    if (response.ok) {
      const data = await response.json();
      return Boolean(data.value);
    }
  } catch (error) {
    console.warn(`Failed to evaluate feature flag ${key}:`, error);
  }
  return false;
}

export async function getFeatureValue<T>(key: string, context?: Record<string, any>, defaultValue?: T): Promise<T> {
  try {
    const response = await fetch('/api/feature-flags/evaluate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key, context }),
    });
    if (response.ok) {
      const data = await response.json();
      return data.value as T;
    }
  } catch (error) {
    console.warn(`Failed to get feature flag ${key}:`, error);
  }
  return defaultValue as T;
}