# ARISE — Interface Definitions (Protocol Contracts)

## Overview

Formal interface definitions (Protocols/ABCs) for all system components. These define the exact contracts that implementations must satisfy, enabling dependency injection, testing, and independent development.

---

## 1. Core Protocols (Python `typing.Protocol`)

### 1.1 Event Bus

```python
# core/events/protocols.py
from typing import Protocol, Callable, Any, Awaitable, Dict, List
from dataclasses import dataclass

@dataclass
class Event:
    topic: str
    payload: Dict[str, Any]
    timestamp: float
    correlation_id: str = ""
    causation_id: str = ""

class EventBusProtocol(Protocol):
    """Pub/sub event bus with async handlers"""
    
    async def emit(self, topic: str, payload: Dict[str, Any], 
                   correlation_id: str = "", causation_id: str = "") -> None:
        """Emit event to all subscribers"""
        ...
    
    async def subscribe(self, topic: str, handler: Callable[[Event], Awaitable[None]]) -> str:
        """Subscribe to topic, returns subscription_id for unsubscribe"""
        ...
    
    async def unsubscribe(self, subscription_id: str) -> None:
        """Remove subscription"""
        ...
    
    async def publish(self, topic: str, payload: Dict[str, Any]) -> int:
        """Publish and wait for all handlers to complete, returns handler count"""
        ...

# Standard topics
class EventTopics:
    TASK_CREATED = "task.created"
    TASK_STATUS_CHANGED = "task.status_changed"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_GRANTED = "approval.granted"
    APPROVAL_DENIED = "approval.denied"
    VOICE_STATE_CHANGED = "voice.state_changed"
    VOICE_TRANSCRIPT = "voice.transcript"
    VOICE_INTENT = "voice.intent"
    AGENT_DELEGATED = "agent.delegated"
    AGENT_COMPLETED = "agent.completed"
    AGENT_FAILED = "agent.failed"
    MEMORY_STORED = "memory.stored"
    MEMORY_CONSOLIDATED = "memory.consolidated"
    SECURITY_ALERT = "security.alert"
    RESOURCE_WARNING = "resource.warning"
    SCHEDULER_TRIGGERED = "scheduler.triggered"
    CONFIG_CHANGED = "config.changed"
```

### 1.2 Adapter Ports

```python
# core/adapters/ports.py
from typing import Protocol, Dict, Any, List, Optional, runtime_checkable
from dataclasses import dataclass
from enum import Enum

@runtime_checkable
class AdapterPort(Protocol):
    """Base protocol for all adapters"""
    
    @property
    def name(self) -> str:
        """Unique adapter identifier"""
        ...
    
    @property
    def version(self) -> str:
        """Adapter version"""
        ...
    
    def capabilities(self) -> List["AdapterCapability"]:
        """Declared capabilities"""
        ...
    
    def operations(self) -> Dict[str, "AdapterOperation"]:
        """Available operations with schemas"""
        ...
    
    async def call(self, operation: str, params: Dict[str, Any], 
                   granted_capabilities: List[str]) -> "AdapterResult":
        """Execute operation with capability check"""
        ...
    
    async def health_check(self) -> "HealthStatus":
        """Health check"""
        ...

@dataclass
class AdapterCapability:
    name: str                          # e.g., "filesystem.read"
    description: str
    risk_level: str                    # R0-R4
    resource_pattern: str = ""         # For scoped capabilities

@dataclass
class AdapterOperation:
    name: str
    description: str
    schema: Dict[str, Any]             # JSON Schema for params
    required_capabilities: List[str]
    returns_schema: Dict[str, Any]     # JSON Schema for result

@dataclass
class AdapterResult:
    success: bool
    data: Any = None
    error: Optional[str] = None
    evidence: Optional[List["EvidenceRecord"]] = None
    metadata: Optional[Dict[str, Any]] = None

@dataclass
class HealthStatus:
    healthy: bool
    details: Dict[str, Any]
    latency_ms: float = 0.0

# Specific adapter protocols

class FilesystemAdapterPort(AdapterPort, Protocol):
    """Filesystem operations"""
    
    async def read(self, path: str, encoding: str = "utf-8") -> AdapterResult:
        ...
    
    async def write(self, path: str, content: str, encoding: str = "utf-8",
                    create_dirs: bool = True) -> AdapterResult:
        ...
    
    async def list(self, path: str, recursive: bool = False, 
                   pattern: str = "*") -> AdapterResult:
        ...
    
    async def delete(self, path: str, recursive: bool = False) -> AdapterResult:
        ...
    
    async def search(self, path: str, query: str, 
                     file_pattern: str = "*", max_results: int = 100) -> AdapterResult:
        ...
    
    async def exists(self, path: str) -> AdapterResult:
        ...
    
    async def stat(self, path: str) -> AdapterResult:
        ...

class UIAAdapterPort(AdapterPort, Protocol):
    """Windows UI Automation"""
    
    async def find_element(self, app_name: str, selector: Dict[str, Any],
                           timeout: float = 10.0) -> AdapterResult:
        """Find UI element by selector"""
        ...
    
    async def click(self, element_id: str, button: str = "left",
                    count: int = 1) -> AdapterResult:
        ...
    
    async def type_text(self, element_id: str, text: str,
                        clear_first: bool = False, delay_ms: int = 0) -> AdapterResult:
        ...
    
    async def get_text(self, element_id: str) -> AdapterResult:
        ...
    
    async def get_attribute(self, element_id: str, attribute: str) -> AdapterResult:
        ...
    
    async def set_focus(self, element_id: str) -> AdapterResult:
        ...
    
    async def get_window_list(self) -> AdapterResult:
        ...
    
    async def wait_for_element(self, app_name: str, selector: Dict[str, Any],
                               timeout: float = 30.0) -> AdapterResult:
        ...
    
    async def capture_screenshot(self, region: Optional[Dict[str, int]] = None) -> AdapterResult:
        ...

class PlaywrightAdapterPort(AdapterPort, Protocol):
    """Browser automation via Playwright"""
    
    async def navigate(self, url: str, wait_until: str = "networkidle",
                       timeout: float = 30.0) -> AdapterResult:
        ...
    
    async def click(self, selector: str, button: str = "left",
                    count: int = 1, timeout: float = 10.0) -> AdapterResult:
        ...
    
    async def type(self, selector: str, text: str, delay: int = 0) -> AdapterResult:
        ...
    
    async def get_text(self, selector: str) -> AdapterResult:
        ...
    
    async def get_attribute(self, selector: str, attribute: str) -> AdapterResult:
        ...
    
    async def evaluate(self, script: str, arg: Any = None) -> AdapterResult:
        ...
    
    async def wait_for_selector(self, selector: str, state: str = "visible",
                                timeout: float = 30.0) -> AdapterResult:
        ...
    
    async def screenshot(self, full_page: bool = False,
                         path: Optional[str] = None) -> AdapterResult:
        ...
    
    async def trace_start(self, name: str) -> AdapterResult:
        ...
    
    async def trace_stop(self) -> AdapterResult:
        ...
    
    async def download(self, url: str, path: str) -> AdapterResult:
        ...
    
    async def upload(self, selector: str, file_path: str) -> AdapterResult:
        ...

class ShellAdapterPort(AdapterPort, Protocol):
    """Shell command execution"""
    
    async def execute(self, command: str, args: List[str] = None,
                      cwd: str = None, env: Dict[str, str] = None,
                      timeout: float = 60.0, capture_output: bool = True) -> AdapterResult:
        ...
    
    async def execute_streaming(self, command: str, args: List[str] = None,
                                cwd: str = None, env: Dict[str, str] = None,
                                on_stdout: Callable[[str], None] = None,
                                on_stderr: Callable[[str], None] = None) -> AdapterResult:
        ...
    
    async def which(self, command: str) -> AdapterResult:
        ...
    
    async def get_env(self, name: str) -> AdapterResult:
        ...

class NetworkAdapterPort(AdapterPort, Protocol):
    """HTTP/Network requests"""
    
    async def get(self, url: str, headers: Dict[str, str] = None,
                  params: Dict[str, str] = None, timeout: float = 30.0) -> AdapterResult:
        ...
    
    async def post(self, url: str, data: Any = None, json: Dict = None,
                   headers: Dict[str, str] = None, timeout: float = 30.0) -> AdapterResult:
        ...
    
    async def put(self, url: str, data: Any = None, json: Dict = None,
                  headers: Dict[str, str] = None, timeout: float = 30.0) -> AdapterResult:
        ...
    
    async def delete(self, url: str, headers: Dict[str, str] = None,
                     timeout: float = 30.0) -> AdapterResult:
        ...
    
    async def download_file(self, url: str, path: str,
                            progress: Callable[[int, int], None] = None) -> AdapterResult:
        ...
```

### 1.3 Model Router

```python
# core/model_router/protocols.py
from typing import Protocol, List, Dict, Any, Optional, AsyncIterator
from dataclasses import dataclass
from enum import Enum

class TaskType(str, Enum):
    FAST = "fast"                    # Quick responses, low cost
    GENERAL = "general"              # Balanced
    CODING = "coding"                # Code generation/analysis
    RESEARCH = "research"            # Complex reasoning, citations
    CREATIVE = "creative"            # Image/video/audio prompts
    VISION = "vision"                # Image understanding
    EMBEDDING = "embedding"          # Vector embeddings
    LOCAL = "local"                  # Local-only models

@dataclass
class ModelProvider:
    name: str
    type: str                        # gemini, openai, anthropic, ollama, local
    models: List["ModelInfo"]
    priority: int                    # Lower = higher priority
    enabled: bool = True
    health: "ProviderHealth" = None

@dataclass
class ModelInfo:
    name: str
    task_types: List[TaskType]
    max_tokens: int
    supports_streaming: bool = False
    supports_vision: bool = False
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0
    context_window: int = 4096

@dataclass
class ProviderHealth:
    healthy: bool
    last_check: float
    error_rate: float
    avg_latency_ms: float
    consecutive_failures: int

@dataclass
class CompletionRequest:
    messages: List[Dict[str, Any]]
    task_type: TaskType = TaskType.GENERAL
    max_tokens: Optional[int] = None
    temperature: float = 0.7
    top_p: float = 1.0
    stop_sequences: List[str] = None
    stream: bool = False
    metadata: Dict[str, Any] = None

@dataclass
class CompletionResponse:
    content: str
    usage: "TokenUsage"
    model: str
    provider: str
    finish_reason: str
    success: bool = True
    error: Optional[str] = None
    latency_ms: float = 0.0

@dataclass
class TokenUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

@dataclass
class StreamChunk:
    delta: str
    finish_reason: Optional[str] = None
    usage: Optional[TokenUsage] = None

class ModelRouterProtocol(Protocol):
    """Provider-neutral model routing"""
    
    async def complete(self, task_type: TaskType, 
                       request: CompletionRequest,
                       context: Dict[str, Any] = None) -> CompletionResponse:
        """Single completion"""
        ...
    
    async def stream(self, task_type: TaskType,
                     request: CompletionRequest,
                     context: Dict[str, Any] = None) -> AsyncIterator[StreamChunk]:
        """Streaming completion"""
        ...
    
    async def embed(self, texts: List[str], 
                    task_type: TaskType = TaskType.EMBEDDING) -> List[List[float]]:
        """Generate embeddings"""
        ...
    
    def get_available_providers(self) -> List[ModelProvider]:
        """List all configured providers"""
        ...
    
    def get_provider(self, name: str) -> Optional[ModelProvider]:
        """Get provider by name"""
        ...
    
    async def health_check(self) -> Dict[str, ProviderHealth]:
        """Check all providers"""
        ...
```

### 1.4 Memory System

```python
# core/memory/protocols.py
from typing import Protocol, List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum

class MemoryKind(str, Enum):
    SEMANTIC = "semantic"        # Permanent facts
    EPISODIC = "episodic"        # Time-bound experiences
    PROCEDURAL = "procedural"    # Skills/workflows
    PREFERENCE = "preference"    # User settings
    WORKING = "working"          # Transient context

@dataclass
class MemoryEntry:
    memory_id: str
    kind: MemoryKind
    content: str
    embedding: Optional[List[float]] = None
    metadata: Dict[str, Any] = None
    created_at: str = ""
    updated_at: str = ""
    version: int = 1
    source: str = ""             # user, agent, system, consolidation
    confidence: float = 1.0
    pii_detected: bool = False
    pii_types: List[str] = None

@dataclass
class MemoryQuery:
    query: str
    kinds: List[MemoryKind] = None
    k: int = 10
    filters: Dict[str, Any] = None
    rerank: bool = True
    include_embeddings: bool = False

@dataclass
class MemoryResult:
    memory_id: str
    kind: MemoryKind
    content: str
    score: float
    metadata: Dict[str, Any]
    created_at: str
    embedding: Optional[List[float]] = None

@dataclass
class ConsolidationConfig:
    working_to_episodic_hours: int = 1
    episodic_summarization_daily: bool = True
    procedural_reinforcement_weekly: bool = True
    preference_conflict_resolution: str = "user_confirm"  # last_write_wins, user_confirm, merge
    cleanup_enabled: bool = True
    max_memories_per_kind: Dict[MemoryKind, int] = None

class MemorySystemProtocol(Protocol):
    """Memory storage and retrieval"""
    
    async def store(self, kind: MemoryKind, content: str,
                    metadata: Dict[str, Any] = None,
                    embedding: List[float] = None) -> str:
        """Store memory, returns memory_id"""
        ...
    
    async def get(self, memory_id: str) -> Optional[MemoryEntry]:
        """Get memory by ID"""
        ...
    
    async def query(self, query: MemoryQuery) -> List[MemoryResult]:
        """Semantic search across kinds"""
        ...
    
    async def update(self, memory_id: str, content: str = None,
                     metadata: Dict[str, Any] = None) -> bool:
        """Update memory (creates new version)"""
        ...
    
    async def delete(self, memory_id: str) -> bool:
        """Delete single memory"""
        ...
    
    async def delete_by_kind(self, kind: MemoryKind) -> int:
        """Delete all memories of a kind, returns count"""
        ...
    
    async def export(self, kinds: List[MemoryKind] = None,
                     format: str = "jsonl") -> str:
        """Export memories as string"""
        ...
    
    async def import_memories(self, data: str, format: str = "jsonl",
                              merge_strategy: str = "merge") -> Dict[str, int]:
        """Import memories, returns {imported, skipped, errors}"""
        ...
    
    async def consolidate(self, config: ConsolidationConfig = None) -> Dict[str, int]:
        """Run consolidation pipeline, returns {promoted, summarized, reinforced, cleaned}"""
        ...
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get memory statistics"""
        ...

class MemoryGovernanceProtocol(Protocol):
    """Memory governance and compliance"""
    
    async def detect_pii(self, content: str) -> List["PIIFinding"]:
        """Detect PII in content"""
        ...
    
    async def apply_retention(self) -> int:
        """Apply retention policies, returns deleted count"""
        ...
    
    async def audit_access(self, memory_id: str, action: str, 
                           user_id: str = "local_user") -> None:
        """Log memory access"""
        ...
    
    async def get_user_control_data(self) -> Dict[str, Any]:
        """Get data for user control UI"""
        ...

@dataclass
class PIIFinding:
    type: str                          # email, phone, ssn, credit_card, api_key, address, name
    value: str
    start: int
    end: int
    confidence: float
```

### 1.5 Agent Protocol

```python
# core/agents/protocols.py
from typing import Protocol, List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum

class AgentStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    STARTING = "starting"
    STOPPING = "stopping"

@dataclass
class AgentCapability:
    name: str
    description: str
    required_system_capabilities: List[str]  # e.g., ["filesystem.read", "browser.navigate"]
    input_schema: Dict[str, Any]             # JSON Schema
    output_schema: Dict[str, Any]            # JSON Schema
    estimated_duration_seconds: float = 30.0
    supports_streaming: bool = False

@dataclass
class AgentTask:
    id: str
    objective: str
    context: Dict[str, Any]
    granted_capabilities: List[str]          # Subset of agent's declared capabilities
    parent_task_id: Optional[str] = None
    timeout_seconds: float = 300.0
    metadata: Dict[str, Any] = None

@dataclass
class AgentResult:
    task_id: str
    status: str                              # completed, failed, cancelled
    result: Dict[str, Any]
    evidence: List["EvidenceRecord"]
    error: Optional[str] = None
    execution_time_ms: float = 0.0
    tokens_used: Optional["TokenUsage"] = None

@dataclass
class EvidenceRecord:
    evidence_id: str
    type: str                                # screenshot, log, trace, file_diff, etc.
    description: str
    file_path: str
    metadata: Dict[str, Any]

@dataclass
class AgentHealth:
    status: AgentStatus
    details: Dict[str, Any]
    last_heartbeat: float
    consecutive_failures: int = 0

class AgentProtocol(Protocol):
    """Base protocol for all agents"""
    
    @property
    def agent_id(self) -> str:
        ...
    
    @property
    def name(self) -> str:
        ...
    
    @property
    def description(self) -> str:
        ...
    
    def capabilities(self) -> List[AgentCapability]:
        """Declared capabilities"""
        ...
    
    async def execute(self, task: AgentTask) -> AgentResult:
        """Execute task with granted capabilities"""
        ...
    
    async def cancel(self, task_id: str) -> bool:
        """Cancel running task"""
        ...
    
    async def health_check(self) -> AgentHealth:
        """Health check"""
        ...
    
    async def initialize(self, config: Dict[str, Any]) -> None:
        """Initialize with config"""
        ...
    
    async def shutdown(self) -> None:
        """Graceful shutdown"""
        ...

class CoordinatorProtocol(Protocol):
    """Central coordinator for multi-agent orchestration"""
    
    async def orchestrate(self, task: AgentTask) -> AgentResult:
        """Full orchestration: understand → decompose → plan → execute → integrate → verify"""
        ...
    
    async def decompose(self, objective: str, context: Dict) -> List[AgentTask]:
        """Decompose objective into subtasks"""
        ...
    
    async def plan(self, subtasks: List[AgentTask]) -> List[AgentTask]:
        """Order and assign subtasks to agents"""
        ...
    
    async def delegate(self, task: AgentTask, agent_id: str) -> AgentResult:
        """Delegate to specific agent"""
        ...
    
    async def verify(self, original_objective: str, results: List[AgentResult]) -> "VerificationResult":
        """Independent verification of results"""
        ...
    
    async def compensate(self, failed_task: AgentTask, completed_tasks: List[AgentTask]) -> None:
        """Execute compensation for failed task"""
        ...

@dataclass
class VerificationResult:
    verified: bool
    issues: List["VerificationIssue"]
    suggested_fix: Optional[Dict[str, Any]] = None

@dataclass
class VerificationIssue:
    type: str                                # logic_error, security_violation, incomplete, hallucination
    severity: str                            # critical, major, minor
    description: str
    location: Optional[str] = None
    agent_id: Optional[str] = None
```

---

## 2. Rust Traits (Tauri Commands)

```rust
// src-tauri/src/protocols.rs
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use async_trait::async_trait;

#[derive(Debug, Serialize, Deserialize)]
pub struct TaskCreateRequest {
    pub objective: String,
    pub context: Option<serde_json::Value>,
    pub priority: Option<String>,
    pub capabilities_requested: Option<Vec<String>>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct TaskResponse {
    pub task_id: String,
    pub objective: String,
    pub status: String,
    pub context: serde_json::Value,
    pub result: Option<serde_json::Value>,
    pub error: Option<String>,
    pub risk_level: String,
    pub required_capabilities: Vec<String>,
    pub granted_capabilities: Vec<String>,
    pub created_at: String,
    pub updated_at: String,
    pub started_at: Option<String>,
    pub completed_at: Option<String>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct VoiceSessionRequest {
    pub language: Option<String>,
    pub privacy_mode: Option<String>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct VoiceSessionResponse {
    pub session_id: String,
    pub expires_at: String,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct MemoryQueryRequest {
    pub query: String,
    pub kinds: Option<Vec<String>>,
    pub k: Option<u32>,
    pub filters: Option<serde_json::Value>,
    pub rerank: Option<bool>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct MemoryResult {
    pub memory_id: String,
    pub kind: String,
    pub content: String,
    pub score: f32,
    pub metadata: serde_json::Value,
    pub created_at: String,
}

#[async_trait]
pub trait TaskEngine: Send + Sync {
    async fn create_task(&self, req: TaskCreateRequest) -> Result<TaskResponse, String>;
    async fn get_task(&self, task_id: &str) -> Result<TaskResponse, String>;
    async fn list_tasks(&self, status: Option<String>, limit: u32, offset: u32) -> Result<Vec<TaskResponse>, String>;
    async fn cancel_task(&self, task_id: &str, reason: Option<String>) -> Result<bool, String>;
    async fn approve_task(&self, task_id: &str, approved: bool, grant_scope: Option<String>) -> Result<bool, String>;
    async fn recover_task(&self, task_id: &str) -> Result<TaskResponse, String>;
}

#[async_trait]
pub trait VoicePipeline: Send + Sync {
    async fn start_session(&self, req: VoiceSessionRequest) -> Result<VoiceSessionResponse, String>;
    async fn stop_session(&self, session_id: &str) -> Result<bool, String>;
    async fn barge_in(&self, session_id: &str) -> Result<bool, String>;
    async fn feed_audio(&self, session_id: &str, audio_base64: &str) -> Result<(), String>;
}

#[async_trait]
pub trait MemorySystem: Send + Sync {
    async fn query(&self, req: MemoryQueryRequest) -> Result<Vec<MemoryResult>, String>;
    async fn store(&self, kind: &str, content: &str, metadata: Option<serde_json::Value>) -> Result<String, String>;
    async fn get(&self, memory_id: &str) -> Result<Option<serde_json::Value>, String>;
    async fn delete(&self, memory_id: &str) -> Result<bool, String>;
    async fn export(&self, kinds: Option<Vec<String>>, format: Option<String>) -> Result<String, String>;
    async fn consolidate(&self) -> Result<serde_json::Value, String>;
}

#[async_trait]
pub trait AgentCoordinator: Send + Sync {
    async fn execute(&self, objective: &str, context: Option<serde_json::Value>) -> Result<serde_json::Value, String>;
    async fn list_agents(&self) -> Result<Vec<serde_json::Value>, String>;
    async fn get_agent_health(&self, agent_id: &str) -> Result<serde_json::Value, String>;
}

#[async_trait]
pub trait ConfigManager: Send + Sync {
    async fn get(&self, key: Option<String>) -> Result<serde_json::Value, String>;
    async fn set(&self, key: String, value: serde_json::Value) -> Result<bool, String>;
    async fn validate(&self) -> Result<Vec<String>, String>;
}
```

---

## 3. TypeScript Interfaces (Frontend)

```typescript
// src-tauri/frontend/src/types/api.ts

// Core Types
export interface Task {
  task_id: string;
  objective: string;
  status: TaskStatus;
  context: Record<string, any>;
  result?: Record<string, any>;
  error?: string;
  risk_level: RiskLevel;
  required_capabilities: string[];
  granted_capabilities: string[];
  created_at: string;
  updated_at: string;
  started_at?: string;
  completed_at?: string;
  checkpoint?: Checkpoint;
}

export type TaskStatus = 
  | 'CREATED' | 'QUEUED' | 'UNDERSTANDING' | 'PLANNING' | 'READY' | 'RUNNING'
  | 'WAITING_APPROVAL' | 'WAITING_CAPABILITY' | 'WAITING_RESOURCE' | 'WAITING_EXTERNAL'
  | 'VERIFYING' | 'COMPLETED' | 'FAILED' | 'CANCELLED';

export type RiskLevel = 'R0' | 'R1' | 'R2' | 'R3' | 'R4';

export interface Checkpoint {
  checkpoint_id: string;
  task_id: string;
  step: number;
  state: string;
  context: Record<string, any>;
  created_at: string;
}

export interface CreateTaskRequest {
  objective: string;
  context?: Record<string, any>;
  priority?: 'low' | 'normal' | 'high';
  capabilities_requested?: string[];
}

export interface ApprovalRequest {
  approved: boolean;
  grant_scope?: 'task' | 'session' | 'permanent';
  grant_duration_hours?: number;
}

// Voice Types
export type VoiceState = 'DORMANT' | 'DETECTING' | 'LISTENING' | 'PROCESSING' | 'SPEAKING';

export interface VoiceSession {
  session_id: string;
  state: VoiceState;
  language: 'en' | 'te' | 'auto';
  privacy_mode: 'standard' | 'private' | 'local_only' | 'offline';
  expires_at: string;
}

export interface VoiceEvent {
  type: 'state_changed' | 'wake_word' | 'partial_transcript' | 'final_transcript' 
      | 'intent' | 'speaking_started' | 'audio_chunk' | 'speaking_finished' | 'error';
  payload: Record<string, any>;
  timestamp: number;
}

export interface IntentClassification {
  type: string;
  confidence: number;
  entities: Record<string, any>;
  suggested_capabilities: string[];
  risk_level: RiskLevel;
}

// Memory Types
export type MemoryKind = 'semantic' | 'episodic' | 'procedural' | 'preference' | 'working';

export interface MemoryEntry {
  memory_id: string;
  kind: MemoryKind;
  content: string;
  metadata: Record<string, any>;
  created_at: string;
  updated_at: string;
  version: number;
  source: string;
  confidence: number;
  pii_detected: boolean;
  pii_types?: string[];
}

export interface MemoryQuery {
  query: string;
  kinds?: MemoryKind[];
  k?: number;
  filters?: Record<string, any>;
  rerank?: boolean;
}

export interface MemoryResult {
  memory_id: string;
  kind: MemoryKind;
  content: string;
  score: number;
  metadata: Record<string, any>;
  created_at: string;
}

// Agent Types
export interface AgentInfo {
  agent_id: string;
  name: string;
  description: string;
  type: string;
  capabilities: AgentCapability[];
  version: string;
  health: AgentHealth;
}

export interface AgentCapability {
  name: string;
  description: string;
  required_system_capabilities: string[];
  input_schema: Record<string, any>;
  output_schema: Record<string, any>;
  estimated_duration_seconds: number;
  supports_streaming: boolean;
}

export type AgentStatus = 'healthy' | 'degraded' | 'unhealthy' | 'starting' | 'stopping';

export interface AgentHealth {
  status: AgentStatus;
  details: Record<string, any>;
  last_heartbeat: number;
  consecutive_failures: number;
}

export interface AgentTask {
  id: string;
  objective: string;
  context: Record<string, any>;
  granted_capabilities: string[];
  parent_task_id?: string;
  timeout_seconds: number;
}

export interface AgentResult {
  task_id: string;
  status: 'completed' | 'failed' | 'cancelled';
  result: Record<string, any>;
  evidence: EvidenceRecord[];
  error?: string;
  execution_time_ms: number;
}

export interface EvidenceRecord {
  evidence_id: string;
  type: string;
  description: string;
  file_path: string;
  metadata: Record<string, any>;
}

// Event Types
export interface AppEvent {
  topic: string;
  payload: Record<string, any>;
  timestamp: number;
  correlation_id?: string;
  causation_id?: string;
}

// WebSocket Message Types
export type WSClientMessage = 
  | { type: 'task.create'; payload: CreateTaskRequest; request_id: string }
  | { type: 'task.get'; payload: { task_id: string }; request_id: string }
  | { type: 'task.list'; payload: { status?: string; limit?: number; offset?: number }; request_id: string }
  | { type: 'task.cancel'; payload: { task_id: string; reason?: string }; request_id: string }
  | { type: 'task.approve'; payload: { task_id: string } & ApprovalRequest; request_id: string }
  | { type: 'voice.start'; payload: VoiceSessionRequest; request_id: string }
  | { type: 'voice.stop'; payload: { session_id: string }; request_id: string }
  | { type: 'voice.barge_in'; payload: { session_id: string }; request_id: string }
  | { type: 'voice.feed_audio'; payload: { session_id: string; audio_data: string; is_final?: boolean }; request_id: string }
  | { type: 'memory.query'; payload: MemoryQuery; request_id: string }
  | { type: 'memory.store'; payload: { kind: MemoryKind; content: string; metadata?: Record<string, any> }; request_id: string }
  | { type: 'config.get'; payload: { key?: string }; request_id: string }
  | { type: 'config.set'; payload: { key: string; value: any }; request_id: string };

export type WSServerMessage = 
  | { type: 'response'; request_id: string; success: boolean; data?: any; error?: string }
  | { type: 'event'; payload: AppEvent }
  | { type: 'error'; code: string; message: string };

// Health & Metrics
export interface HealthStatus {
  healthy: boolean;
  details: Record<string, any>;
  latency_ms: number;
}

export interface MetricsSnapshot {
  cpu_percent: number;
  memory_mb: number;
  task_count: { active: number; queued: number; completed: number; failed: number };
  model_queue_depth: number;
  browser_count: number;
  agent_count: { healthy: number; degraded: number; unhealthy: number };
  memory_stats: Record<string, number>;
  uptime_seconds: number;
}
```

---

## 4. Contract Testing Helpers

```python
# tests/contract/helpers.py
from typing import Protocol, TypeVar, Any
import pytest

T = TypeVar('T', bound=Protocol)

def assert_protocol_compliance(obj: Any, protocol: type[T]) -> None:
    """Verify object implements protocol at runtime"""
    for attr in dir(protocol):
        if attr.startswith('_'):
            continue
        if not hasattr(obj, attr):
            raise AssertionError(f"Missing attribute: {attr}")
        proto_attr = getattr(protocol, attr)
        obj_attr = getattr(obj, attr)
        if callable(proto_attr) and not callable(obj_attr):
            raise AssertionError(f"Attribute {attr} should be callable")

# Usage in tests
def test_adapter_implements_protocol(uia_adapter):
    from core.adapters.ports import UIAAdapterPort
    assert_protocol_compliance(uia_adapter, UIAAdapterPort)
```

---

## 5. Implementation Checklist

For each protocol, implementations must:

- [ ] Define all required methods with exact signatures
- [ ] Handle all error cases with domain-specific error codes
- [ ] Implement health_check() with <100ms response
- [ ] Support graceful shutdown (drain in-flight requests)
- [ ] Emit standard events for observability
- [ ] Validate inputs against declared schemas
- [ ] Check capabilities before execution
- [ ] Return structured results with evidence
- [ ] Support timeout/cancellation
- [ ] Log structured logs with correlation IDs

---

*These interfaces are the source of truth for all component interactions. Any changes require version bump and migration.*