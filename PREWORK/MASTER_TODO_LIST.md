# ARISE — Master Implementation Todo List

**Purpose**: Complete, granular implementation checklist covering all 27 design documents. Each item is a discrete, verifiable task. Claude Code should check off items as completed.

**Usage**: 
- Run `TaskUpdate` with `status: "in_progress"` when starting a task
- Run `TaskUpdate` with `status: "completed"` when finished
- Never skip tasks - every checkbox must be addressed
- If a task seems unclear, refer to the referenced design document

---

## PHASE 1: FOUNDATION & CORE INFRASTRUCTURE (Weeks 1-2)

### 1.1 Project Structure & Build System

- [x] **1.1.1** Create root directory structure per `03_Final_Technology_Stack.md` and `23_Developer_Experience_Tooling.md`:
  - [x] `core/` - Python monorepo
  - [x] `src-tauri/` - Rust Tauri 2 app
  - [x] `src/` - React TypeScript frontend
  - [x] `scripts/` - Dev scripts
  - [x] `tests/` - Test directories (unit, integration, contract, e2e)
  - [x] `docker/` - Dockerfiles and compose files
  - [x] `docs/` - Architecture docs
  - [x] `.github/workflows/` - CI/CD
  - [x] `.vscode/` - VS Code config
  - [x] `.devcontainer/` - Dev container config

- [x] **1.1.2** Create `pyproject.toml` in `core/` with all dependencies from `03_Final_Technology_Stack.md`:
  - [x] FastAPI 0.109+, Uvicorn, Pydantic 2.6+, Pydantic-Settings
  - [x] SQLAlchemy 2.0+, Alembic, asyncpg, aiosqlite
  - [x] Redis-py 5.0+, Prometheus-client, structlog
  - [x] OpenAI, Anthropic, Google-GenerativeAI, Ollama clients
  - [x] Porcupine, Sherpa-ONNX, TTS libraries
  - [x] Playwright, comtypes (UIA), OpenCV, Tesseract/PaddleOCR
  - [x] ChromaDB, Sentence-Transformers, Presidio
  - [x] PyTest, PyTest-Asyncio, PyTest-Cov, Hypothesis
  - [x] Ruff, Black, MyPy, Pre-commit
  - [x] Poetry for dependency management

- [x] **1.1.3** Create `Cargo.toml` in `src-tauri/` with Tauri 2 dependencies from `03_Final_Technology_Stack.md`:
  - [x] tauri 2.0, tauri-plugin-shell, tauri-plugin-dialog
  - [x] tauri-plugin-fs, tauri-plugin-http, tauri-plugin-updater
  - [x] serde, serde_json, tokio, tracing
  - [x] windows-rs for Windows-specific APIs
  - [x] clap for CLI args

- [x] **1.1.4** Create `package.json` in `src/` with frontend dependencies:
  - [x] React 18, TypeScript 5, Vite 5
  - [x] Tailwind CSS 3, Radix UI, Lucide React
  - [x] Zustand for state, TanStack Query for server state
  - [x] React Router 6, React Hook Form, Zod
  - [x] Vitest, Playwright, ESLint, Prettier
  - [x] OpenAPI TypeScript codegen dependencies

- [x] **1.1.5** Create `Makefile` in root with all commands from `23_Developer_Experience_Tooling.md`:
  - [x] `dev`, `dev-core`, `dev-tauri`, `dev-frontend`
  - [x] `test`, `test-unit`, `test-integration`, `test-contract`, `test-e2e`, `test-coverage`
  - [x] `lint`, `lint-python`, `lint-rust`, `lint-typescript`
  - [x] `format`, `format-python`, `format-rust`, `format-typescript`
  - [x] `type-check`, `type-check-python`, `type-check-rust`, `type-check-typescript`
  - [x] `build`, `build-core`, `build-tauri`, `build-frontend`
  - [x] `db-migrate`, `db-rollback`, `db-reset`
  - [x] `generate-api`, `benchmark`, `profile`

- [x] **1.1.6** Create `scripts/dev-setup.sh` one-command setup script from `23_Developer_Experience_Tooling.md`

- [x] **1.1.7** Create `.github/workflows/ci.yml` with full pipeline from `23_Developer_Experience_Tooling.md`:
  - [x] Python lint (ruff, mypy), test (pytest with coverage)
  - [x] Rust lint (clippy, fmt), test (cargo test)
  - [x] TypeScript lint (eslint), type-check (tsc), test (vitest)
  - [x] Integration tests with PostgreSQL + Redis services
  - [x] Security scanning (Trivy, Safety, Cargo-audit, pnpm audit)
  - [x] Build artifacts upload
  - [x] E2E tests on Windows runner (scheduled)

- [x] **1.1.8** Create `.github/workflows/release.yml` for automated releases from `23_Developer_Experience_Tooling.md`

- [x] **1.1.9** Create `.vscode/settings.json`, `launch.json`, `tasks.json`, `extensions.json` from `23_Developer_Experience_Tooling.md`

- [x] **1.1.10** Create `.devcontainer/devcontainer.json` and `Dockerfile` from `23_Developer_Experience_Tooling.md`

- [x] **1.1.11** Create `docker/Dockerfile.core`, `docker/Dockerfile.tauri`, `docker/docker-compose.yml`, `docker/docker-compose.prod.yml` from `26_System_Integration_Deployment.md`

- [x] **1.1.12** Create Kubernetes manifests in `k8s/` from `26_System_Integration_Deployment.md`:
  - [x] `namespace.yaml`, `configmap.yaml`, `secrets.yaml`
  - [x] `postgres.yaml` (StatefulSet), `redis.yaml` (Deployment)
  - [x] `core.yaml` (Deployment + HPA), `ingress.yaml`
  - [x] `blue-green.yaml` or `canary.yaml` for rollout strategy

### 1.2 Configuration System (Ref: `25_Configuration_Management.md`, `03_Final_Technology_Stack.md`)

- [x] **1.2.1** Create `core/config/models.py` with all Pydantic models:
  - [x] `AppConfig` - main config with all sub-configs
  - [x] `DatabaseConfig`, `RedisConfig`
  - [x] `ModelProviderConfig`, `ModelRouterConfig`
  - [x] `TaskEngineConfig`, `PolicyEngineConfig`
  - [x] `VoiceConfig`, `MemoryConfig`, `AutomationConfig`
  - [x] `SecurityConfig`, `AgentConfig`, `FrontendConfig`
  - [x] `TelemetryConfig`, `EventsConfig`
  - [x] All enums: `LogLevel`, `Environment`, `ProviderType`

- [x] **1.2.2** Create `core/config/loader.py` with `ConfigLoader` class:
  - [x] Layered loading: defaults → config.default.yaml → config.{env}.yaml → config.local.yaml → env vars
  - [x] Deep merge for nested configs
  - [x] Secret redaction in export
  - [x] Config validation for production
  - [x] Hot-reload watchers

- [x] **1.2.3** Create `core/config/secrets.py` with secret providers:
  - [x] `EnvSecretProvider` (ARISE_SECRET_ prefix)
  - [x] `WindowsCredentialManager` (PowerShell Get-StoredCredential)
  - [x] `FileSecretProvider` (Fernet-encrypted .secrets.enc)
  - [x] `VaultSecretProvider` (HashiCorp Vault HTTP API)
  - [x] `SecretManager` with priority-based provider chain

- [x] **1.2.4** Create `core/config/feature_flags.py`:
  - [x] `FeatureFlag` dataclass with type, default, rollout, targeting
  - [x] `FeatureFlagStore` with registration, evaluation, rollout
  - [x] Built-in flags: voice.enabled, voice.gemini_live, agents.multi_agent, automation.playwright, memory.consolidation, security.prompt_injection, telemetry.enabled, experimental.cv_ocr

- [x] **1.2.5** Create `core/config/migration.py` with `ConfigMigrator`:
  - [x] Migration v1.1.0: API keys → secret references
  - [x] Migration v1.2.0: Voice session settings
  - [x] Migration v1.3.0: Memory config restructure

- [x] **1.2.6** Create config files in `config/`:
  - [x] `config.default.yaml` - all defaults from `25_Configuration_Management.md`
  - [x] `config.development.yaml` - dev overrides
  - [x] `config.production.yaml` - prod overrides
  - [x] `config.local.yaml.example` - template for local

- [x] **1.2.7** Create `core/runtime/config_api.py` with FastAPI endpoints:
  - [x] `GET /api/v1/config` - full config (redacted)
  - [x] `GET /api/v1/config/{path}` - specific value
  - [x] `PATCH /api/v1/config` - runtime updates with restart detection
  - [x] `POST /api/v1/config/secrets` - store secret
  - [x] `GET /api/v1/config/secrets/{key}` - retrieve secret
  - [x] `DELETE /api/v1/config/secrets/{key}` - delete secret
  - [x] `GET /api/v1/config/secrets` - list secret keys
  - [x] `POST /api/v1/config/export` - export config
  - [x] `POST /api/v1/config/reload` - force reload
  - [x] `GET /api/v1/config/schema` - JSON schema

- [x] **1.2.8** Create TypeScript config in `src/config/index.ts` from `25_Configuration_Management.md`:
  - [x] Zod schema validation
  - [x] `ConfigStore` class with localStorage persistence
  - [x] React hooks: `useConfig`, `useFeatureFlag`
  - [x] Vite env var overrides
  - [x] All config types: AppConfig, DatabaseConfig, RedisConfig, ModelRouterConfig, TaskEngineConfig, PolicyEngineConfig, VoiceConfig, MemoryConfig, AutomationConfig, SecurityConfig, AgentsConfig, FrontendConfig, TelemetryConfig, EventsConfig
  - [x] All enums: LogLevel, Environment, ProviderType, PrivacyMode, RiskLevel, MemoryKind, TaskKind, TaskStatus, TaskPriority, FlagType, FlagStatus

- [x] **1.2.9** Create Rust config in `src-tauri/src/config.rs` from `25_Configuration_Management.md`:
  - [x] `AppConfig` struct with TOML/YAML serialization
  - [x] Tauri commands: `get_config`, `update_config`, `reset_config`
  - [x] All config types matching Python/TypeScript
  - [x] Default implementations for all sub-configs
  - [x] Load/save from file utilities
  - [x] Unit tests for serialization

### 1.3 Database Layer (Ref: `20_Database_Schemas.md`, `03_Final_Technology_Stack.md`)

- [x] **1.3.1** Create `core/database.py` with async SQLAlchemy setup:
  - [x] Engine creation with pool config
  - [x] Session factory with async context manager
  - [x] Base model class with common fields
  - [x] Health check method

- [x] **1.3.2** Create all SQLAlchemy models in `core/models/` matching `20_Database_Schemas.md`:
  - [x] `Task`, `TaskStep`, `TaskCheckpoint` (tasks tables)
  - [x] `AuditEntry` (audit table)
  - [x] `Memory`, `MemoryEmbedding`, `MemoryLink` (memory tables)
  - [x] `Agent`, `AgentTask`, `AgentHealth` (agent tables)
  - [x] `VoiceSession`, `VoiceTurn` (voice tables)
  - [x] `ConfigKey`, `ConfigValue` (config tables)
  - [x] `EvidenceRecord`, `Artifact` (evidence tables)
  - [x] `ProjectionState`, `DeadLetterEvent` (event bus tables)

- [x] **1.3.3** Create Alembic environment in `core/migrations/`:
  - [x] `env.py` with async support
  - [x] `script.py.mako` template
  - [x] Initial migration with all tables
  - [x] Indexes for common queries (correlation_id, task_id, timestamps)

- [x] **1.3.4** Create `scripts/db-migrate.py` with upgrade/downgrade/create/reset commands from `23_Developer_Experience_Tooling.md`

- [x] **1.3.5** Create `scripts/db-inspect.py` for table stats, slow queries from `23_Developer_Experience_Tooling.md`

### 1.4 Error Handling (Ref: `22_Error_Handling_Patterns.md`)

- [x] **1.4.1** Create `core/errors/base.py`:
  - [x] `ErrorCode` enum with all 50+ codes
  - [x] `ErrorContext` dataclass
  - [x] `AriseError` base exception
  - [x] Domain exceptions: `TaskError`, `PolicyError`, `ModelError`, `VoiceError`, `MemoryError`, `AgentError`, `AutomationError`, `SecurityError`, `ConfigurationError`

- [x] **1.4.2** Create `core/errors/factory.py` with all factory functions:
  - [x] `capability_denied`, `approval_required`, `provider_unavailable`, `circuit_open`
  - [x] `wake_word_not_loaded`, `asr_failed`, `memory_store_full`, `pii_detected`
  - [x] `agent_unhealthy`, `verification_failed`
  - [x] `uia_element_not_found`, `credential_not_found`, `network_blocked`
  - [x] `create_error_context`

- [x] **1.4.3** Create `core/errors/result.py`:
  - [x] `Result[T, E]` generic type with `ok`, `err`, `unwrap`, `map`, `and_then`
  - [x] `try_async`, `try_sync` helpers

- [x] **1.4.4** Create `core/runtime/ws_error_handler.py` for WebSocket JSON-RPC error formatting

- [x] **1.4.5** Create `core/runtime/http_error_handler.py` for FastAPI exception handlers

- [x] **1.4.6** Create `core/errors/retry.py`:
  - [x] `RetryPolicy` dataclass
  - [x] `with_retry` async function
  - [x] `@retryable` decorator
  - [x] `CircuitBreaker` class with `CLOSED/OPEN/HALF_OPEN` states

- [x] **1.4.7** Create `core/errors/saga.py` for saga compensation pattern

- [x] **1.4.8** Create `core/errors/logging.py` with `ErrorLogger` for structured logging

- [ ] **1.4.9** Create TypeScript error handling in `src/lib/errorHandling.ts` from `22_Error_Handling_Patterns.md`

### 1.5 Event Bus (Ref: `24_Event_Bus_Messaging.md`)

- [x] **1.5.1** Create `core/events/models.py`:
  - [x] `EventPriority` enum
  - [x] `Event` dataclass with all fields, `to_dict`, `from_dict`, `to_json`, `from_json`

- [x] **1.5.2** Create `core/events/bus.py` with `LocalEventBus`:
  - [x] Priority queue with `asyncio.PriorityQueue`
  - [x] Exact topic subscriptions + wildcard patterns (`tasks.*`)
  - [x] `subscribe`, `unsubscribe`, `publish`, `publish_sync`
  - [x] Background worker with retry logic
  - [x] Dead letter queue with size limit
  - [x] Global `get_event_bus()`, `init_event_bus()`, `shutdown_event_bus()`

- [x] **1.5.3** Create `core/events/distributed_bus.py` with `DistributedEventBus`:
  - [x] Redis Streams consumer groups
  - [x] `publish`, `subscribe`, `start_consuming`, `replay`
  - [x] `HybridEventBus` combining local + distributed

- [x] **1.5.4** Create `core/events/store.py` with `EventStore`:
  - [x] SQLite with WAL mode
  - [x] `append`, `append_batch`, `get_events`, `get_by_correlation`, `get_recent`
  - [x] Snapshots table for projections
  - [x] Dead letter queue table

- [x] **1.5.5** Create `core/events/projections.py`:
  - [x] Base `Projection` class with checkpointing
  - [x] `TaskStatusProjection` handling all task events
  - [x] `AgentHealthProjection` handling agent events
  - [x] `ModelUsageProjection` handling model events
  - [x] `ProjectionRegistry` for managing projections

- [x] **1.5.6** Create `core/events/handlers.py`:
  - [x] `EventHandlerRegistry` with decorator `@event_handler`
  - [x] `TaskEventHandlers`, `MemoryEventHandlers`, `VoiceEventHandlers`, `AgentEventHandlers`, `ModelEventHandlers`, `AutomationEventHandlers` examples
  - [x] `auto_register_handlers` utility

- [x] **1.5.7** Create `core/events/metrics.py` with Prometheus metrics

- [x] **1.5.8** Create `core/events/tracing.py` with `EventTracer` for correlation

- [x] **1.5.9** Create `core/events/config.py` with `EventsConfig` Pydantic model

### 1.6 Logging & Observability (Ref: `13_Performance_and_Resource_Management.md`, `22_Error_Handling_Patterns.md`)

- [x] **1.6.1** Create `core/structured_logging.py` (renamed from `core/logging.py` to avoid stdlib conflict):
  - [x] `StructuredFormatter` with JSON output
  - [x] Context variables: `correlation_id`, `task_id`, `agent_id`, `session_id`, `request_id`, `user_id`
  - [x] `CorrelationContext`, `TaskContext`, `AgentContext`, `SessionContext`, `RequestContext` context managers
  - [x] `LoggingConfig` Pydantic model with `get_logging_config()` method
  - [x] `log_structured()` helper function
  - [x] `setup_logging()` function with level, JSON/text output

- [x] **1.6.2** Create `core/metrics.py`:
  - [x] All Prometheus metrics from `13_Performance_and_Resource_Management.md` (100+ metrics)
  - [x] Decorators: `@track_http_metrics`, `@track_task_metrics`, `@track_model_metrics`
  - [x] `@track_event_bus_metrics`, `@track_agent_metrics`, `@track_memory_metrics`, `@track_voice_metrics`, `@track_automation_metrics`, `@track_policy_metrics`, `@track_db_metrics`, `@track_cache_metrics`
  - [x] Context managers for timing
  - [x] `create_metrics_response()` for `/metrics` endpoint

- [x] **1.6.3** Create `core/runtime/health.py` with health checks from `26_System_Integration_Deployment.md`:
  - [x] `/health` - comprehensive with DB, Redis, models, disk, memory, event bus
  - [x] `/ready` - Kubernetes readiness (DB + Redis only)
  - [x] `/live` - Kubernetes liveness
  - [x] `/metrics` - Prometheus metrics endpoint

### 1.7 FastAPI Application Entry (Ref: `19_API_Specifications.md`)

- [x] **1.7.1** Create `core/runtime/main.py`:
  - [x] FastAPI app with lifespan (startup/shutdown)
  - [x] Register all exception handlers
  - [x] Include all API routers
  - [x] CORS, TrustedHost middleware
  - [x] Request correlation ID middleware

- [x] **1.7.2** Create API routers for each domain (stubs initially):
  - [x] `core/runtime/api/tasks.py` - Task endpoints
  - [x] `core/runtime/api/memory.py` - Memory endpoints
  - [x] `core/runtime/api/voice.py` - Voice endpoints
  - [x] `core/runtime/api/agents.py` - Agent endpoints
  - [x] `core/runtime/api/automation.py` - Automation endpoints
  - [x] `core/runtime/api/config.py` - Config endpoints (from 1.2.7)
  - [x] `core/runtime/api/health.py` - Health endpoints (from 1.6.3)
  - [x] `core/runtime/api/models.py` - Model router endpoints
  - [x] `core/runtime/api/policy.py` - Policy engine endpoints

- [x] **1.7.3** Create WebSocket endpoint `/ws` for real-time updates:
  - [x] JSON-RPC 2.0 over WebSocket
  - [x] Task progress streaming
  - [x] Event subscriptions
  - [x] `WSHandler` class with method registration
  - [x] `WSErrorHandler` for JSON-RPC 2.0 error formatting

---

## PHASE 2: CORE SERVICES (Weeks 3-4)

### 2.1 Task Engine (Ref: `05_Detailed_Component_Design.md`, `06_Data_Flow_and_State_Management.md`, `07_Sequence_Diagrams.md`)

- [x] **2.1.1** Create `core/task_engine/models.py`:
  - [x] `TaskKind` enum (shell.exec, filesystem.read, filesystem.write, etc.)
  - [x] `TaskStatus` enum with all 28 states (CREATED → QUEUED → UNDERSTANDING → PLANNING → READY → RUNNING → WAITING_* → VERIFYING → COMPLETED/FAILED/CANCELLED)
  - [x] `TaskPriority` enum
  - [x] `Task`, `TaskStep`, `TaskResult`, `TaskCheckpoint` dataclasses
  - [x] `ResourceLimits` dataclass (memory_mb, cpu_percent, disk_mb, timeout)
  - [x] `TaskStateMachine` with 28 states and validated transitions

- [x] **2.1.2** Create `core/task_engine/state_machine.py`:
  - [x] `TaskStateMachine` class with transition validation
  - [x] All valid transitions defined (in models.py)
  - [x] `can_transition(from_state, to_state)` method
  - [x] `get_valid_transitions(state)` method

- [x] **2.1.3** Create `core/task_engine/queue.py`:
  - [x] `TaskQueue` with priority levels (10)
  - [x] `enqueue`, `dequeue`, `requeue`, `remove`
  - [x] Fair scheduling within priority
  - [x] Persistence to SQLite

- [x] **2.1.4** Create `core/task_engine/executor.py`:
  - [x] `TaskExecutor` with sandbox support (Docker, gVisor, Firecracker)
  - [x] Resource monitoring (memory, CPU, disk)
  - [x] Timeout enforcement with graceful cancellation
  - [x] Tool execution: shell, filesystem, HTTP, browser, UIA

- [x] **2.1.5** Create `core/task_engine/checkpoint.py`:
  - [x] `CheckpointManager` with interval-based saves
  - [x] Save/restore task state + step outputs
  - [x] Resume from last checkpoint

- [x] **2.1.6** Create `core/task_engine/engine.py` with `TaskEngine` class:
  - [x] `initialize()` - start queue worker, load checkpoints
  - [x] `submit(task)` - returns task_id
  - [x] `submit_and_wait(task, timeout)` - blocking submit
  - [x] `get_task(task_id)` - current status
  - [x] `cancel_task(task_id)` - graceful cancellation
  - [x] `wait_for_task(task_id, timeout)` - WebSocket-based wait
  - [x] `get_execution_trace(task_id)` - state history
  - [x] `shutdown()` - graceful drain

- [x] **2.1.7** Create task kinds implementations in `core/task_engine/kinds/`:
  - [x] `shell.py` - ShellExecKind
  - [x] `filesystem.py` - FileReadKind, FileWriteKind, FileListKind
  - [x] `http.py` - HttpRequestKind
  - [x] `browser.py` - BrowserNavigateKind, BrowserClickKind, BrowserExtractKind
  - [x] `uia.py` - UiaFindKind, UiaClickKind, UiaInputKind
  - [x] `memory.py` - MemoryStoreKind, MemoryQueryKind
  - [x] `agent.py` - AgentDelegateKind, AgentVerifyKind

- [x] **2.1.8** Create FastAPI endpoints in `core/runtime/api/tasks.py` per `19_API_Specifications.md`:
  - [x] `POST /api/v1/tasks` - create task
  - [x] `GET /api/v1/tasks/{task_id}` - get task
  - [x] `GET /api/v1/tasks` - list with filters
  - [x] `POST /api/v1/tasks/{task_id}/cancel` - cancel
  - [x] `GET /api/v1/tasks/{task_id}/trace` - execution trace
  - [x] `WS /ws/tasks/{task_id}` - real-time progress

### 2.2 Policy Engine (Ref: `05_Detailed_Component_Design.md`, `12_Security_and_Permissions.md`)

- [x] **2.2.1** Create `core/policy_engine/models.py`:
  - [x] `RiskLevel` enum (R0-R4) with auto-approve, timeout, MFA config
  - [x] `Capability` enum (all 30+ capabilities)
  - [x] `CapabilityGrant` dataclass (scoped, TTL, conditions)
  - [x] `ApprovalRequest`, `ApprovalDecision` dataclasses
  - [x] `PolicyEvaluationResult`, `PolicyAuditEntry` dataclasses
  - [x] `DEFAULT_RISK_LEVEL_CONFIG` mapping capabilities to risk levels
  - [x] `ResourceSensitivity` enum and `RISK_ADJUSTMENT` matrix

- [x] **2.2.2** Create `core/policy_engine/evaluator.py`:
  - [x] `RiskEvaluator` with capability → risk level mapping
  - [x] Context-aware assessment (resource sensitivity, user context)
  - [x] Policy rule engine (allow/deny/require_approval)

- [x] **2.2.3** Create `core/policy_engine/approval.py`:
  - [x] `ApprovalManager` with WebSocket UI integration
  - [x] `request_approval(task_id, capability, context)` - returns approval_id
  - [x] `grant_approval(approval_id, decision, ttl)` - user decision
  - [x] Timeout handling (auto-deny after configured seconds)
  - [x] Approval persistence

- [x] **2.2.4** Create `core/policy_engine/grants.py`:
  - [x] `CapabilityGrantManager` with CRUD for grants
  - [x] Scoped grants (resource patterns, conditions)
  - [x] TTL enforcement with background cleanup
  - [x] Grant inheritance (parent → child tasks)

- [x] **2.2.5** Create `core/policy_engine/audit.py`:
  - [x] `AuditLogger` with tamper-evident logs
  - [x] Log all: capability checks, approvals, grants, denials
  - [x] Encryption at rest (AES-256-GCM)
  - [x] Query API for compliance

- [x] **2.2.6** Create FastAPI endpoints in `core/runtime/api/policy.py` per `19_API_Specifications.md`:
  - [x] `POST /api/v1/policy/evaluate` - evaluate risk
  - [x] `POST /api/v1/policy/approvals` - request approval
  - [x] `GET /api/v1/policy/approvals/{approval_id}` - get status
  - [x] `POST /api/v1/policy/approvals/{approval_id}/decide` - user decision
  - [x] `GET /api/v1/policy/grants` - list grants
  - [x] `POST /api/v1/policy/grants` - create grant
  - [x] `DELETE /api/v1/policy/grants/{grant_id}` - revoke grant
  - [x] `GET /api/v1/policy/audit` - query audit log

### 2.3 Model Router (Ref: `05_Detailed_Component_Design.md`, `02_Technology_Research_and_Comparison.md`)

- [x] **2.3.1** Create `core/models/providers/`:
  - [x] `ModelProvider` Protocol with `complete`, `stream`, `health_check`, `count_tokens`, `estimate_cost`, `list_models`
  - [x] `AnthropicProvider`, `GeminiProvider`, `OllamaProvider` (OpenAI, AzureOpenAI, VertexAI providers in registry)
  - [x] Provider factory with config injection and registry pattern

- [x] **2.3.2** Create `core/models/engine.py` with `ModelRouter`:
  - [x] Task-type routing table with configurable rules
  - [x] Fallback chain execution with automatic failover
  - [x] Privacy modes: off, standard, redact (Presidio), local_only
  - [x] Cost tracking per request with `CostTracker`
  - [x] Token counting (tiktoken for OpenAI, approx for others)
  - [x] Streaming and embedding support

- [x] **2.3.3** Circuit breaker integrated in `ModelRouter`:
  - [x] Per-provider circuit breaker with CLOSED/OPEN/HALF_OPEN states
  - [x] Half-open test requests
  - [x] Metrics export via `get_provider_status()`

- [x] **2.3.4** Create `core/models/cost_tracker.py`:
  - [x] In-memory + persistent cost aggregation
  - [x] Per-provider, per-model, per-task-type breakdowns
  - [x] Budget alerts and usage statistics

- [x] **2.3.5** Create FastAPI endpoints in `core/runtime/api/models.py` per `19_API_Specifications.md`:
  - [x] `POST /api/v1/models/complete` - non-streaming completion
  - [x] `POST /api/v1/models/stream` - streaming (SSE)
  - [x] `GET /api/v1/models/providers` - list with health
  - [x] `GET /api/v1/models/usage` - cost/token stats
  - [x] `GET /api/v1/models/status` - provider status with circuit breakers

---

## PHASE 3: MEMORY & SECURITY (Weeks 5-6)

### 3.1 Memory System (Ref: `10_Memory_and_Knowledge.md`, `05_Detailed_Component_Design.md`)

- [x] **3.1.1** Create `core/memory/models.py`:
  - [x] `MemoryKind` enum (SEMANTIC, PREFERENCE, EPISODIC, PROCEDURAL, WORKING)
  - [x] `Memory` dataclass with id, kind, content, embedding, confidence, metadata, tags, TTL, created_at, accessed_at
  - [x] `MemoryQuery`, `MemoryResult` dataclasses
  - [x] `MemorySource` enum, `ConsolidationResult` dataclass

- [x] **3.1.2** Create `core/memory/store.py`:
  - [x] `MemoryStore` abstract base
  - [x] `ChromaDBStore` implementation (vector + metadata)
  - [x] `SQLiteFTSStore` implementation (full-text search)
  - [x] `HybridMemoryStore` combining vector + FTS + metadata filters
  - [x] `create_memory_store` factory function

- [x] **3.1.3** Create `core/memory/consolidation.py`:
  - [x] `ConsolidationPipeline` scheduled job (every 6 hours)
  - [x] Working → Episodic promotion
  - [x] Episodic → Semantic abstraction (LLM-based)
  - [x] Preference extraction from patterns
  - [x] Procedural skill learning from repetitions
  - [x] Conflict resolution (timestamp + confidence)

- [x] **3.1.4** Create `core/memory/governance.py`:
  - [x] `PIIDetector` with Presidio integration + regex fallback
  - [x] Actions: flag, redact, block per config
  - [x] TTL enforcement with background sweeper
  - [x] Max memories per kind enforcement (LRU eviction)
  - [x] Memory encryption at rest (via encryption manager)

- [x] **3.1.5** Create `core/memory/system.py` with `MemorySystem` facade:
  - [x] `store(kind, content, confidence, metadata, tags)` → memory_id
  - [x] `query(query, kind, limit, filters)` → results
  - [x] `get(memory_id)` → memory
  - [x] `update(memory_id, updates)` → bool
  - [x] `delete(memory_id)` → bool
  - [x] `trigger_consolidation(kind)` → manual trigger
  - [x] `enforce_ttl()`, `enforce_lru()`, `get_governance_stats()`, `get_stats()`

- [x] **3.1.6** Create FastAPI endpoints in `core/runtime/api/memory.py` per `19_API_Specifications.md`:
  - [x] Full implementation with actual memory system
  - [x] POST /api/v1/memory - store
  - [x] GET /api/v1/memory - query with filters
  - [x] GET /api/v1/memory/{memory_id} - get
  - [x] PATCH /api/v1/memory/{memory_id} - update
  - [x] DELETE /api/v1/memory/{memory_id} - delete
  - [x] POST /api/v1/memory/consolidate - trigger consolidation
  - [x] GET /api/v1/memory/consolidate/status - consolidation status
  - [x] POST /api/v1/memory/governance/ttl - enforce TTL
  - [x] POST /api/v1/memory/governance/lru - enforce LRU
  - [x] GET /api/v1/memory/governance/stats - governance stats
  - [x] GET /api/v1/memory/stats - memory system stats
  - [x] GET /api/v1/memory/health - health check

### 3.2 Security Hardening (Ref: `12_Security_and_Permissions.md`, `25_Configuration_Management.md`)

- [x] **3.2.1** Create `core/security/credentials.py`:
  - [x] `CredentialManager` using Windows Credential Manager (primary)
  - [x] Fallback to keyring, Vault, env, encrypted file
  - [x] `get_credential(category, key)`, `set_credential`, `delete_credential`, `list_credentials`

- [x] **3.2.2** Create `core/security/network.py`:
  - [x] `EgressController` with allowlist/denylist
  - [x] Per-capability network permissions
  - [x] DNS resolution blocking for denylisted domains
  - [x] HTTP/HTTPS proxy interception for validation
  - [x] Socket patching for automatic interception

- [x] **3.2.3** Create `core/security/prompt_injection.py`:
  - [x] `PromptInjectionDetector` with PromptGuard/DeBERTa model support
  - [x] Heuristic rules (instruction override, role play, data exfiltration, jailbreak, etc.)
  - [x] Integration points: model router input, agent input, automation input
  - [x] Async detection with ML model

- [x] **3.2.4** Create `core/security/audit.py`:
  - [x] `SecurityAuditLogger` extending policy audit
  - [x] Credential access logging
  - [x] Network block events
  - [x] Prompt injection detection events
  - [x] Tamper detection (hash chains)
  - [x] Query API, acknowledgment, chain verification

- [x] **3.2.5** Create `core/security/encryption.py`:
  - [x] AES-256-GCM for data at rest
  - [x] Key derivation from master key (PBKDF2)
  - [x] Key rotation (90 days default)
  - [x] Field-level encryption for PII
  - [x] `FieldEncryption` helper for automatic PII field encryption

---

## PHASE 4: VOICE & AUTOMATION (Weeks 7-9)

### 4.1 Voice Pipeline (Ref: `08_Voice_Architecture.md`, `05_Detailed_Component_Design.md`)

- [ ] **4.1.1** Create `core/voice/wake_word.py`:
  - [ ] `WakeWordDetector` with Porcupine
  - [ ] Model loading (hey_arise.ppn)
  - [ ] Sensitivity tuning (0.5 default)
  - [ ] Audio device selection
  - [ ] Dormant mode (CPU < 1% when not detecting)

- [ ] **4.1.2** Create `core/voice/asr.py`:
  - [ ] `ASRProvider` Protocol
  - [ ] `SherpaONNXASR` - streaming Zipformer (local primary)
  - [ ] `WhisperASR` - fallback local
  - [ ] `GeminiASR` - cloud fallback
  - [ ] `AzureASR` - enterprise fallback
  - [ ] VAD integration (Silero)
  - [ ] Language detection + switching

- [ ] **4.1.3** Create `core/voice/tts.py`:
  - [ ] `TTSProvider` Protocol
  - [ ] `GeminiTTS` - primary (Neural2 voices)
  - [ ] `CoquiTTS` - local fallback
  - [ ] `ElevenLabsTTS` - premium fallback
  - [ ] `AzureTTS` - enterprise fallback
  - [ ] Streaming audio output
  - [ ] Voice cloning (optional)

- [ ] **4.1.4** Create `core/voice/session.py`:
  - [ ] `VoiceSession` state machine (IDLE → LISTENING → PROCESSING → SPEAKING → IDLE)
  - [ ] Barge-in detection (user speaks during TTS)
  - [ ] Turn management (VAD + silence timeout)
  - [ ] Session timeout (30s default, 1hr max)
  - [ ] Context preservation across turns

- [ ] **4.1.5** Create `core/voice/pipeline.py` with `VoicePipeline`:
  - [ ] `initialize()` - load all models
  - [ ] `start_session()` → session_id
  - [ ] `process_audio(audio_chunk)` - streaming
  - [ ] `end_session()` - cleanup
  - [ ] Event emission for each stage

- [ ] **4.1.6** Create FastAPI endpoints in `core/runtime/api/voice.py` per `19_API_Specifications.md`:
  - [x] API stubs created (returning 501 Not Implemented)
  - [ ] Full implementation with actual voice pipeline

- [ ] **4.1.7** Create Tauri commands in `src-tauri/src/commands/voice.rs`:
  - [ ] `voice_start_session`, `voice_stop_session`
  - [ ] `voice_get_audio_devices`
  - [ ] Audio capture from system microphone

### 4.2 Desktop Automation (Ref: `11_Desktop_Automation.md`, `05_Detailed_Component_Design.md`)

- [ ] **4.2.1** Create `core/automation/uia.py`:
  - [ ] `UIABackend` with comtypes
  - [ ] Element finder (Name, ClassName, AutomationId, ControlType)
  - [ ] Tree walking (parent, children, siblings)
  - [ ] Actions: click, double_click, right_click, input_text, scroll, hover
  - [ ] Pattern support: Invoke, Value, Scroll, ExpandCollapse, Toggle
  - [ ] Screenshot of element
  - [ ] Retry with wait (configurable)

- [ ] **4.2.2** Create `core/automation/playwright.py`:
  - [ ] `PlaywrightBackend` with Chromium/Firefox/WebKit
  - [ ] Browser context isolation per task
  - [ ] Actions: navigate, click, fill, select, wait_for_selector, screenshot
  - [ ] PDF generation, network interception
  - [ ] Stealth mode for anti-bot

- [ ] **4.2.3** Create `core/automation/cv_ocr.py`:
  - [ ] `CVOCRBackend` with Tesseract (primary) + PaddleOCR (fallback)
  - [ ] Screen capture (Windows GraphicsCapture / mss)
  - [ ] Template matching (OpenCV)
  - [ ] Text detection + bounding boxes
  - [ ] Confidence scoring
  - [ ] Click by text/image

- [ ] **4.2.4** Create `core/automation/perception.py`:
  - [ ] `PerceptionHierarchy` - tries UIA → Playwright → CV/OCR
  - [ ] Confidence scoring per backend
  - [ ] Fallback triggers (element not found, low confidence, timeout)
  - [ ] Unified element representation

- [ ] **4.2.5** Create `core/automation/coordinator.py`:
  - [ ] `AutomationCoordinator` for cross-app workflows
  - [ ] Window management (focus, resize, position)
  - [ ] Clipboard synchronization
  - [ ] Multi-step action recording/replay
  - [ ] Safety confirmations (configurable per risk level)

- [ ] **4.2.6** Create `core/automation/system.py` with `AutomationSystem` facade:
  - [ ] `find_element(selector)` → ElementHandle
  - [ ] `click(element)`, `input_text(element, text)`, etc.
  - [ ] `navigate(url)` → browser context
  - [ ] `screenshot(region)` → bytes
  - [ ] `ocr(region)` → text + boxes

- [ ] **4.2.7** Create FastAPI endpoints in `core/runtime/api/automation.py` per `19_API_Specifications.md`:
  - [x] API stubs created (returning 501 Not Implemented)
  - [ ] Full implementation with actual automation system

- [ ] **4.2.8** Create Tauri commands in `src-tauri/src/commands/automation.rs`:
  - [ ] `automation_find_element`, `automation_click`, `automation_input`
  - [ ] `automation_screenshot`, `automation_ocr`
  - [ ] Window enumeration and management

---

## PHASE 5: MULTI-AGENT SYSTEM (Weeks 10-11)

### 5.1 Agent Framework (Ref: `09_Multi_Agent_System.md`, `05_Detailed_Component_Design.md`)

- [ ] **5.1.1** Create `core/agents/base.py`:
  - [ ] `AgentRole` enum (11 roles + COORDINATOR)
  - [ ] `AgentCapability` dataclass (tools, permissions, model)
  - [ ] `BaseAgent` abstract class with:
    - `initialize()`, `shutdown()`
    - `execute(task, context)` → Result
    - `health_check()` → HealthStatus
    - `get_capabilities()` → List[AgentCapability]
  - [ ] `AgentContext` with task_id, correlation_id, permissions, memory_scope

- [ ] **5.1.2** Create `core/agents/coordinator.py` with `CentralCoordinator`:
  - [ ] Task decomposition (LLM-based planning)
  - [ ] Specialist selection algorithm
  - [ ] Delegation protocol (JSON-RPC over event bus)
  - [ ] Progress aggregation
  - [ ] Failure handling + retry with backoff
  - [ ] Result synthesis

- [ ] **5.1.3** Create `core/agents/delegation.py`:
  - [ ] `DelegationMessage` (task, context, permissions, deadline)
  - [ ] `DelegationResponse` (result, evidence, verification_notes)
  - [ ] Async request/response with correlation
  - [ ] Timeout enforcement
  - [ ] Cancellation propagation

- [ ] **5.1.4** Create `core/agents/verification.py`:
  - [ ] `VerificationEngine` with independent verifier agent
  - [ ] Criteria: completeness, correctness, safety, policy compliance
  - [ ] Severity levels: info, warning, critical
  - [ ] Auto-fix suggestions
  - [ ] Re-verification loop (max 2 retries)

- [ ] **5.1.5** Create `core/agents/registry.py`:
  - [ ] `AgentRegistry` with registration, discovery, health monitoring
  - [ ] Heartbeat (30s interval)
  - [ ] Automatic restart on crash (max 3)
  - [ ] Load balancing for multiple instances

### 5.2 Specialist Agents (Ref: `09_Multi_Agent_System.md`)

- [ ] **5.2.1** Create `core/agents/specialists/planner.py` - `PlannerAgent`:
  - [ ] Task decomposition into subtasks
  - [ ] Dependency graph construction
  - [ ] Resource estimation
  - [ ] Model: gpt-4o (configurable)

- [ ] **5.2.2** Create `core/agents/specialists/coder.py` - `CoderAgent`:
  - [ ] Code generation, editing, refactoring
  - [ ] Test writing
  - [ ] Language detection
  - [ ] Model: gpt-4o

- [ ] **5.2.3** Create `core/agents/specialists/researcher.py` - `ResearcherAgent`:
  - [ ] Web search + synthesis
  - [ ] Source credibility assessment
  - [ ] Citation management
  - [ ] Model: gemini-1.5-pro

- [ ] **5.2.4** Create `core/agents/specialists/analyst.py` - `AnalystAgent`:
  - [ ] Data analysis, visualization
  - [ ] Statistical reasoning
  - [ ] Report generation
  - [ ] Model: claude-3.5-sonnet

- [ ] **5.2.5** Create `core/agents/specialists/creative.py` - `CreativeAgent`:
  - [ ] Writing, design, ideation
  - [ ] Style adaptation
  - [ ] Model: gpt-4o

- [ ] **5.2.6** Create `core/agents/specialists/automation.py` - `AutomationAgent`:
  - [ ] UIA/Playwright/CV action execution
  - [ ] Workflow construction
  - [ ] Error recovery
  - [ ] Model: gpt-4o-mini

- [ ] **5.2.7** Create `core/agents/specialists/memory.py` - `MemoryAgent`:
  - [ ] Memory store/query/consolidate
  - [ ] Knowledge graph construction
  - [ ] Model: gpt-4o-mini

- [ ] **5.2.8** Create `core/agents/specialists/security.py` - `SecurityAgent`:
  - [ ] Policy evaluation
  - [ ] Threat assessment
  - [ ] Audit analysis
  - [ ] Model: gpt-4o-mini

- [ ] **5.2.9** Create `core/agents/specialists/reviewer.py` - `ReviewerAgent`:
  - [ ] Code review, document review
  - [ ] Quality gates
  - [ ] Model: gpt-4o

- [ ] **5.2.10** Create `core/agents/specialists/communicator.py` - `CommunicatorAgent`:
  - [ ] Email, Slack, Teams integration
  - [ ] Message drafting, sending
  - [ ] Model: gpt-4o-mini

- [ ] **5.2.11** Create `core/agents/specialists/scheduler.py` - `SchedulerAgent`:
  - [ ] Cron-like scheduling
  - [ ] Reminder management
  - [ ] Calendar integration
  - [ ] Model: gpt-4o-mini

### 5.3 Agent Integration

- [ ] **5.3.1** Create `core/agents/system.py` with `AgentSystem` facade:
  - [ ] `initialize()` - spawn all enabled specialists
  - [ ] `delegate(task, preferred_role)` → result
  - [ ] `get_agent_health(role)` → HealthStatus
  - [ ] `shutdown()` - graceful termination

- [ ] **5.3.2** Create FastAPI endpoints in `core/runtime/api/agents.py` per `19_API_Specifications.md`:
  - [x] API stubs created (returning 501 Not Implemented)
  - [ ] Full implementation with actual agent system

- [ ] **5.3.3** Create Tauri commands in `src-tauri/src/commands/agents.rs`

---

## PHASE 6: INTEGRATION & POLISH (Weeks 12-13)

### 6.1 Frontend Implementation (Ref: `23_Developer_Experience_Tooling.md`, `19_API_Specifications.md`)

- [ ] **6.1.1** Create `src/services/api/client.ts` with full API client from `19_API_Specifications.md`:
  - [ ] REST client with typed endpoints
  - [ ] WebSocket client for task progress, voice, automation
  - [ ] SSE client for event streaming
  - [ ] Error handling with `AriseAPIError`
  - [ ] Retry logic with exponential backoff

- [ ] **6.1.2** Create Zustand stores in `src/stores/`:
  - [ ] `useTaskStore` - tasks, queue, active task
  - [ ] `useMemoryStore` - memories, search results
  - [ ] `useVoiceStore` - session state, transcript, audio level
  - [ ] `useAgentStore` - agents, health, delegation status
  - [ ] `useAutomationStore` - elements, screenshots, recordings
  - [ ] `useConfigStore` - settings, feature flags
  - [ ] `useNotificationStore` - toasts, alerts

- [ ] **6.1.3** Create reusable components in `src/components/`:
  - [ ] Layout: `Sidebar`, `Header`, `MainContent`, `StatusBar`
  - [ ] Task: `TaskCard`, `TaskTimeline`, `TaskProgress`, `TaskQueue`
  - [ ] Approval: `ApprovalToast`, `ApprovalModal`, `CapabilityRequest`
  - [ ] Memory: `MemoryBrowser`, `MemoryCard`, `MemorySearch`
  - [ ] Voice: `VoiceVisualizer`, `WakeWordIndicator`, `TranscriptView`
  - [ ] Agent: `AgentMonitor`, `AgentCard`, `DelegationView`
  - [ ] Automation: `ElementInspector`, `ScreenshotViewer`, `OCRResult`
  - [ ] Common: `Button`, `Input`, `Select`, `Modal`, `Toast`, `Dropdown`, `Tabs`, `Table`, `CodeBlock`, `MarkdownRenderer`

- [ ] **6.1.4** Create pages in `src/pages/`:
  - [ ] `Dashboard` - overview, quick actions, recent tasks
  - [ ] `Tasks` - task list, detail, timeline
  - [ ] `Memory` - browser, search, graph view
  - [ ] `Voice` - session control, history, settings
  - [ ] `Agents` - monitor, delegation history, config
  - [ ] `Automation` - recorder, inspector, playback
  - [ ] `Settings` - all config sections, feature flags, secrets

- [ ] **6.1.5** Create custom hooks in `src/hooks/`:
  - [ ] `useWebSocket`, `useSSE`, `useDebounce`, `useLocalStorage`
  - [ ] `useTaskPolling`, `useVoiceSession`, `useAutomationSession`

- [ ] **6.1.6** Implement Tailwind theme (dark default) with CSS variables

- [ ] **6.1.7** Add React Router with lazy-loaded pages

- [ ] **6.1.8** Generate TypeScript API client from OpenAPI: `make generate-api`

### 6.2 Cross-Component Integration

- [ ] **6.2.1** Wire event bus connections for all components:
  - [ ] Task Engine → Policy Engine (approval requests)
  - [ ] Task Engine → Model Router (LLM calls)
  - [ ] Task Engine → Memory (store results)
  - [ ] Task Engine → Agents (delegation)
  - [ ] Task Engine → Automation (UI actions)
  - [ ] Voice → Task Engine (voice commands as tasks)
  - [ ] Agents → All (specialist operations)
  - [ ] Policy → Audit (all decisions)

- [ ] **6.2.2** Implement saga compensation for multi-step operations:
  - [ ] Task with multiple tool calls → compensating transactions
  - [ ] Agent delegation chain → rollback on failure
  - [ ] Voice session with automation → cleanup on abort

- [ ] **6.2.3** Implement checkpoint/resume across restarts:
  - [ ] Task Engine: resume from last checkpoint
  - [ ] Voice: session recovery (optional)
  - [ ] Agents: state persistence

- [ ] **6.2.4** Implement graceful degradation:
  - [ ] Model router: fallback chain
  - [ ] Automation: UIA → Playwright → CV/OCR
  - [ ] Voice: local ASR → cloud ASR
  - [ ] Memory: ChromaDB → SQLite FTS only

### 6.3 Testing Implementation (Ref: `14_Testing_Strategy.md`, `18_Acceptance_Criteria.md`)

- [ ] **6.3.1** Unit Tests (target 80%+ coverage):
  - [ ] `tests/unit/config/` - config loader, secrets, feature flags
  - [ ] `tests/unit/errors/` - error hierarchy, factory, result, retry
  - [ ] `tests/unit/events/` - event bus, store, projections
  - [ ] `tests/unit/task_engine/` - state machine, queue, executor, kinds
  - [ ] `tests/unit/policy_engine/` - evaluator, approval, grants, audit
  - [ ] `tests/unit/model_router/` - providers, router, circuit breaker, cost
  - [ ] `tests/unit/memory/` - store, consolidation, governance
  - [ ] `tests/unit/voice/` - wake word, ASR, TTS, session
  - [ ] `tests/unit/automation/` - UIA, Playwright, CV/OCR, perception
  - [ ] `tests/unit/agents/` - base, coordinator, specialists, verification
  - [ ] `tests/unit/security/` - credentials, network, prompt injection

- [ ] **6.3.2** Contract Tests:
  - [ ] `tests/contract/api/` - OpenAPI spec compliance for all endpoints
  - [ ] `tests/contract/websocket/` - JSON-RPC message formats
  - [ ] `tests/contract/events/` - event schemas

- [ ] **6.3.3** Integration Tests:
  - [ ] `tests/integration/task_flow.py` - full task lifecycle
  - [ ] `tests/integration/policy_flow.py` - approval workflow
  - [ ] `tests/integration/model_routing.py` - fallback chains
  - [ ] `tests/integration/memory_consolidation.py` - consolidation pipeline
  - [ ] `tests/integration/voice_session.py` - voice pipeline
  - [ ] `tests/integration/automation_flow.py` - cross-app workflow
  - [ ] `tests/integration/agent_delegation.py` - multi-agent task

- [ ] **6.3.4** E2E Tests (Playwright):
  - [ ] `tests/e2e/task_creation.spec.ts` - create and monitor task
  - [ ] `tests/e2e/approval_ui.spec.ts` - approval toast/modal
  - [ ] `tests/e2e/voice_conversation.spec.ts` - wake word → response
  - [ ] `tests/e2e/memory_search.spec.ts` - store and query
  - [ ] `tests/e2e/agent_delegation.spec.ts` - delegate and verify
  - [ ] `tests/e2e/automation_record.spec.ts` - record and replay
  - [ ] `tests/e2e/settings.spec.ts` - config changes

- [ ] **6.3.5** Chaos Tests:
  - [ ] `tests/chaos/model_failure.py` - provider outage
  - [ ] `tests/chaos/network_partition.py` - Redis/DB disconnect
  - [ ] `tests/chaos/resource_exhaustion.py` - memory/CPU limits
  - [ ] `tests/chaos/crash_recovery.py` - process kill + restart

- [ ] **6.3.6** Security Tests:
  - [ ] `tests/security/prompt_injection.py` - injection attempts
  - [ ] `tests/security/credential_access.py` - unauthorized access
  - [ ] `tests/security/network_egress.py` - blocked destinations
  - [ ] `tests/security/audit_tampering.py` - log integrity

- [ ] **6.3.7** Performance Tests:
  - [ ] `tests/performance/benchmarks.py` - all SLOs from `13_Performance_and_Resource_Management.md`

### 6.4 Tauri Integration

- [ ] **6.4.1** Complete `src-tauri/src/main.rs`:
  - [ ] Window configuration (transparent, decorations, always-on-top)
  - [ ] System tray with menu (show, voice toggle, quit)
  - [ ] Global shortcuts (Ctrl+Shift+A = show, Ctrl+Shift+V = voice)
  - [ ] Auto-updater configuration
  - [ ] IPC command registration

- [ ] **6.4.2** Implement all Tauri commands:
  - [ ] `src-tauri/src/commands/task.rs` - task CRUD, progress
  - [ ] `src-tauri/src/commands/voice.rs` - session, audio devices
  - [ ] `src-tauri/src/commands/automation.rs` - find, act, screenshot, OCR
  - [ ] `src-tauri/src/commands/memory.rs` - store, query
  - [ ] `src-tauri/src/commands/config.rs` - get, update, secrets
  - [ ] `src-tauri/src/commands/agents.rs` - health, delegate

- [ ] **6.4.3** Build Tauri app: `make build-tauri`
- [ ] **6.4.4** Test on Windows (UIA, audio, system tray)

---

## PHASE 7: PRODUCTION READINESS (Week 14)

### 7.1 Deployment Artifacts

- [ ] **7.1.1** Build all Docker images: `make build`
- [ ] **7.1.2** Create Helm chart in `helm/arise/`:
  - [ ] `Chart.yaml`, `values.yaml`, `values-prod.yaml`
  - [ ] Templates: deployment, service, ingress, HPA, configmap, secret
  - [ ] PostgreSQL, Redis subcharts or external refs

- [ ] **7.1.3** Create systemd service file: `/etc/systemd/system/arise-core.service` from `26_System_Integration_Deployment.md`

- [ ] **7.1.4** Create NSIS installer script: `installer/arise-installer.nsi` from `26_System_Integration_Deployment.md`

- [ ] **7.1.5** Configure Tauri auto-updater with GitHub releases

### 7.2 Observability Stack

- [ ] **7.2.1** Create Prometheus rules in `docker/prometheus.rules.yml`:
  - [ ] High task queue latency
  - [ ] Model provider failures
  - [ ] Memory/disk/CPU thresholds
  - [ ] Voice pipeline latency
  - [ ] Agent health degradation

- [ ] **7.2.2** Create Grafana dashboards in `docker/grafana/dashboards/`:
  - [ ] ARISE Overview (tasks, models, memory, voice)
  - [ ] Task Engine Deep Dive
  - [ ] Model Router Performance
  - [ ] Voice Pipeline Metrics
  - [ ] Agent System Health
  - [ ] System Resources

- [ ] **7.2.3** Configure Loki for log aggregation (optional)

- [ ] **7.2.4** Configure Jaeger for distributed tracing (optional)

### 7.3 Documentation

- [ ] **7.3.1** Create `docs/user-guide.md` - end user documentation
- [ ] **7.3.2** Create `docs/developer-guide.md` - architecture, contributing
- [ ] **7.3.3** Create `docs/api-reference.md` - generated from OpenAPI
- [ ] **7.3.4** Create runbooks in `docs/runbooks/`:
  - [ ] `deployment.md`
  - [ ] `backup-restore.md`
  - [ ] `incident-response.md`
  - [ ] `model-provider-outage.md`
  - [ ] `voice-pipeline-debugging.md`
  - [ ] `automation-failure.md`

- [ ] **7.3.5** Create ADRs in `docs/adr/` for key decisions

### 7.4 Release Preparation

- [ ] **7.4.1** Run full test suite: `make test`
- [ ] **7.4.2** Run security scan: `make security-scan` (if added to Makefile)
- [ ] **7.4.3** Run benchmarks: `make benchmark`
- [ ] **7.4.4** Create release notes / changelog
- [ ] **7.4.5** Tag release: `git tag v1.0.0`
- [ ] **7.4.6** Trigger release workflow
- [ ] **7.4.7** Verify installer on clean Windows VM
- [ ] **7.4.8** Verify Docker images on Kubernetes staging
- [ ] **7.4.9** Smoke test all E2E journeys from `18_Acceptance_Criteria.md`

---

## VERIFICATION CHECKLIST (All Features from Design Docs)

### Core Requirements (from `01_Consolidated_Requirements_Catalogue.md`)

- [ ] AR-CORE-001: Modular monolith architecture
- [ ] AR-CORE-002: Model proposes, policy decides principle
- [ ] AR-CORE-003: 28-state task lifecycle
- [ ] AR-CORE-004: Event-driven communication
- [ ] AR-CORE-005: Local-first with cloud fallback
- [ ] AR-CORE-006: Capability-based security
- [ ] AR-CORE-007: Observability built-in
- [ ] AR-TASK-001 through AR-TASK-050: All task engine requirements
- [ ] AR-POLICY-001 through AR-POLICY-030: All policy engine requirements
- [ ] AR-MODEL-001 through AR-MODEL-025: All model router requirements
- [ ] AR-MEM-001 through AR-MEM-030: All memory system requirements
- [ ] AR-VOICE-001 through AR-VOICE-025: All voice pipeline requirements
- [ ] AR-AUTO-001 through AR-AUTO-030: All automation requirements
- [ ] AR-AGENT-001 through AR-AGENT-030: All multi-agent requirements
- [ ] AR-SEC-001 through AR-SEC-025: All security requirements
- [ ] AR-PERF-001 through AR-PERF-020: All performance requirements
- [ ] AR-DEPLOY-001 through AR-DEPLOY-015: All deployment requirements

### Acceptance Criteria (from `18_Acceptance_Criteria.md`)

- [ ] All 150+ BDD scenarios pass
- [ ] 5 E2E journeys verified:
  - [ ] Journey 1: Voice Command → Task Execution
  - [ ] Journey 2: Multi-Agent Code Generation
  - [ ] Journey 3: Desktop Automation Workflow
  - [ ] Journey 4: Memory Consolidation & Retrieval
  - [ ] Journey 5: Policy Approval & Audit Trail

### Risk Mitigations (from `17_Risk_Register.md`)

- [ ] R1: Model provider API changes - fallback chain tested
- [ ] R2: Windows UIA instability - Playwright/CV fallback tested
- [ ] R3: Voice pipeline latency - local models optimized
- [ ] R4: Memory growth - consolidation + TTL enforced
- [ ] R5: Prompt injection - detector + sandbox tested
- [ ] R6: Agent coordination failures - verification + timeout tested
- [ ] R7: Deployment complexity - Docker/K8s validated

---

## COMPLETION CRITERIA

**Phase 1 Complete When:**
- [ ] `make dev` starts all services without errors
- [ ] `make test` passes (even if empty)
- [ ] `make lint` passes
- [ ] `make type-check` passes
- [ ] Health endpoint returns healthy
- [ ] Config hot-reload works

**Phase 2 Complete When:**
- [ ] Task can be submitted, executed, completed via API
- [ ] Policy approval workflow works end-to-end
- [ ] Model router completes requests with fallback
- [ ] All unit tests for core services pass

**Phase 3 Complete When:**
- [ ] Memory store/query works with all 5 kinds
- [ ] Consolidation runs and produces semantic memories
- [ ] PII detection blocks/flags appropriately
- [ ] Credentials stored/retrieved from Windows Credential Manager
- [ ] Network egress blocked for non-allowlisted domains

**Phase 4 Complete When:**
- [ ] Wake word detects "Hey ARISE" on Windows
- [ ] Voice conversation works (ASR → LLM → TTS)
- [ ] UIA finds and clicks elements in Notepad
- [ ] Playwright navigates and extracts from web
- [ ] CV/OCR finds text on screen

**Phase 5 Complete When:**
- [ ] Coordinator decomposes task and delegates to 2+ specialists
- [ ] Verification catches introduced errors
- [ ] All 11 specialists respond to health checks
- [ ] Agent delegation visible in UI

**Phase 6 Complete When:**
- [ ] All frontend pages functional
- [ ] All integration tests pass
- [ ] All E2E tests pass
- [ ] Chaos tests pass (graceful degradation verified)

**Phase 7 Complete When:**
- [ ] Docker images build and run
- [ ] Helm chart deploys to Kubernetes
- [ ] Windows installer works on clean VM
- [ ] All monitoring dashboards show data
- [ ] All runbooks validated
- [ ] Release artifacts published

---

## NOTES FOR CLAUDE CODE

1. **Always reference the design documents** - each task maps to specific sections
2. **Run tests after each component** - don't batch
3. **Update TODO status in real-time** - use TaskUpdate tool
4. **If blocked, check dependencies** - some tasks require others first
5. **Don't skip "small" items** - config files, types, enums matter
6. **Generate API client after schema changes** - `make generate-api`
7. **Run migrations after model changes** - `make db-migrate`
8. **Keep correlation IDs flowing** - critical for debugging
9. **Use Result[T, E] everywhere** - no raw exceptions in business logic
10. **Emit events for all state changes** - enables projections, UI, audit