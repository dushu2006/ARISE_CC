# ARISE — Data Flow & State Management

## Overview

This document defines how data flows through the ARISE system, how state is managed across components, and the consistency guarantees provided. The architecture follows an event-driven, eventually-consistent model with strong consistency at critical boundaries (policy, checkpoints, evidence).

---

## 1. System-Wide Data Flow

### 1.1 Primary Data Flows

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ARISE DATA FLOW ARCHITECTURE                      │
└─────────────────────────────────────────────────────────────────────────────┘

┌──────────────┐     Voice/Text      ┌──────────────┐     Intent/Plan     ┌──────────────┐
│   FRONTEND   │ ◄─────────────────► │  TASK ENGINE │ ◄─────────────────► │ MODEL ROUTER │
│  (React/TS)  │   WebSocket/HTTP    │   (Python)   │    JSON-RPC         │   (Python)   │
└──────┬───────┘                     └──────┬───────┘                     └──────┬───────┘
       │                                    │                                    │
       │ UI Events                          │ Task Events                        │ Model Events
       ▼                                    ▼                                    ▼
┌──────────────┐                     ┌──────────────┐                     ┌──────────────┐
│  EVENT BUS   │ ◄─────────────────► │  POLICY      │                     │  PROVIDERS   │
│  (Redis/    │   Pub/Sub           │  ENGINE      │                     │  (Gemini/    │
│   In-proc)   │                     │  (Python)    │                     │   OpenAI/    │
└──────┬───────┘                     └──────┬───────┘                     │   Anthropic) │
       │                                    │                             └──────────────┘
       │ Policy Events                      │ Approvals
       ▼                                    ▼
┌──────────────┐                     ┌──────────────┐
│  COORDINATOR │ ◄─────────────────► │  AGENTS      │
│  (Python)    │   Delegation        │  (Specialist)│
└──────┬───────┘                     └──────┬───────┘
       │                                    │
       │ Tool Calls                         │ Evidence
       ▼                                    ▼
┌──────────────┐                     ┌──────────────┐
│  ADAPTERS    │ ◄─────────────────► │  MEMORY      │
│  (UIA/       │   Observations      │  SYSTEM      │
│   Playwright)│                     │  (ChromaDB)  │
└──────┬───────┘                     └──────┬───────┘
       │                                    │
       │ Observations                       │ Retrieval
       ▼                                    ▼
┌──────────────┐                     ┌──────────────┐
│ CHECKPOINT   │ ◄─────────────────► │  EVIDENCE    │
│  STORE       │   Snapshots         │  STORE       │
│  (SQLite)    │                     │  (SQLite)    │
└──────────────┘                     └──────────────┘
```

### 1.2 Communication Protocols

| Channel | Protocol | Use Case | Latency Target |
|---------|----------|----------|----------------|
| Frontend ↔ Backend | WebSocket (JSON-RPC 2.0) | Real-time UI updates, streaming | <50ms |
| Backend ↔ Model Router | In-process async calls | Model inference | <10ms |
| Task Engine ↔ Adapters | In-process async calls | Tool execution | <10ms |
| Coordinator ↔ Agents | In-process async + channels | Delegation | <10ms |
| Components ↔ Event Bus | In-process pub/sub | Decoupled events | <5ms |
| Checkpoint Store | SQLite WAL (sync) | Durability | <5ms write |
| Evidence Store | SQLite + file refs | Audit trail | <10ms |

---

## 2. Task State Management

### 2.1 Task Lifecycle State Machine

```
CREATED ──► QUEUED ──► UNDERSTANDING ──► PLANNING ──► PLAN_REVIEW
                                                              │
                                              ┌───────────────┴───────────────┐
                                              ▼                               ▼
                                        PLAN_APPROVED                    PLAN_REJECTED
                                              │                               │
                                              ▼                               │
                                        ┌─────┴─────┐                         │
                                        ▼           ▼                         │
                                   READY    WAITING_APPROVAL                 │
                                        │           │                         │
                                        ▼           ▼                         │
                                   ┌────┴────┐ ┌────┴────┐                   │
                                   ▼         ▼ ▼         ▼                   │
                               RUNNING  ◄──► PAUSED    WAITING_*             │
                                   │                    (INPUT/AGENT/TOOL)   │
                                   ▼                                         │
                              WAITING_VERIFICATION                           │
                                   │                                         │
                                   ▼                                         │
                              VERIFYING                                       │
                                   │                                         │
                              ┌────┴────┐                                    │
                              ▼         ▼                                    │
                         VERIF_PASS  VERIF_FAIL                              │
                              │         │                                    │
                              ▼         ▼                                    │
                          COMPLETED  PARTIAL/FAILED                          │
                              │         │                                    │
                              └────┬────┘                                    │
                                   ▼                                         │
                               ARCHIVED ◄────────────────────────────────────┘
```

### 2.2 State Persistence Strategy

**Checkpointing Policy:**
- Every state transition → immediate checkpoint (SQLite WAL)
- Every plan step completion → checkpoint with step results
- Every 30 seconds during RUNNING → periodic checkpoint
- On pause/cancel → full context checkpoint

**Checkpoint Content:**
```python
@dataclass
class TaskCheckpoint:
    task_id: str
    state: TaskStatus
    step_index: int           # Current plan step
    context: TaskContext      # Full serializable context
    evidence_refs: List[str]  # Evidence produced so far
    timestamp: datetime
    agent_id: Optional[str]   # If delegated
    parent_task_id: Optional[str]
```

**Recovery Process:**
1. On startup, scan `checkpoints` table for non-terminal states
2. For each: load latest checkpoint → reconstruct Task object
3. If state ∈ {RUNNING, PAUSED, WAITING_*} → transition to RECOVERING
4. RECOVERING tasks: re-verify preconditions → resume from last checkpoint step
5. If verification fails → PLANNING (re-plan) or FAILED

### 2.3 Concurrency Control

```python
class TaskConcurrencyManager:
    """Manages concurrent task execution with resource limits"""
    
    def __init__(self, max_concurrent: int = 4):
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.resource_locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self.running_tasks: Dict[str, Task] = {}
    
    async def acquire_slot(self, task: Task) -> bool:
        """Try to acquire execution slot"""
        return await self.semaphore.acquire()
    
    async def release_slot(self, task: Task):
        self.semaphore.release()
    
    async def acquire_resource(self, task: Task, resource: str, timeout: float = 30) -> bool:
        """Acquire exclusive access to named resource (e.g., GPU, browser profile)"""
        lock = self.resource_locks[resource]
        try:
            await asyncio.wait_for(lock.acquire(), timeout=timeout)
            task.context.variables[f"_lock_{resource}"] = True
            return True
        except asyncio.TimeoutError:
            return False
    
    def release_resource(self, task: Task, resource: str):
        if f"_lock_{resource}" in task.context.variables:
            self.resource_locks[resource].release()
            del task.context.variables[f"_lock_{resource}"]
```

---

## 3. Policy State & Capability Grants

### 3.1 Grant Lifecycle

```
┌─────────────────────────────────────────────────────────────────┐
│                    CAPABILITY GRANT LIFECYCLE                   │
└─────────────────────────────────────────────────────────────────┘

REQUESTED ──► EVALUATING ──► GRANTED ──► ACTIVE ──► EXPIRED/REVOKED
    │            │            │         │           │
    │            │            │         │           └─► Audit log
    │            │            │         └─► Enforcement check
    │            │            └─► Persist to Credential Manager
    │            └─► Risk assessment + User approval
    └─► Policy rule match / User explicit

Grant States:
- REQUESTED: User/agent asked for capability
- EVALUATING: Policy engine assessing risk, checking rules
- GRANTED: Approved (by policy default or user)
- ACTIVE: Currently usable (conditions met, not expired)
- EXPIRED: Time-based expiry reached
- REVOKED: Explicitly revoked by user or policy change
```

### 3.2 Grant Persistence

**Storage:** Windows Credential Manager (DPAPI-encrypted)
- Key format: `ARISE/grants/{subject}/{capability_hash}`
- Value: JSON-serialized `CapabilityGrant`
- Scope: Per-user, roaming profile compatible

**In-Memory Cache:**
- Loaded at startup, refreshed on changes
- TTL: 5 minutes (auto-refresh on access)
- Invalidation: On grant/revoke, broadcast `policy.grants_changed` event

---

## 4. Memory System Data Flow

### 4.1 Memory Kinds & Storage

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        MEMORY STORAGE ARCHITECTURE                       │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────┐    Embeddings     ┌─────────────────┐
│  SEMANTIC   │ ───────────────►  │   ChromaDB      │
│  (Facts,    │   Vector Search   │   Collection    │
│   Knowledge)│                   │   "semantic"    │
└─────────────┘                   └─────────────────┘
       │                                    │
       │ Consolidation                      │ Retrieval
       ▼                                    ▼
┌─────────────┐                   ┌─────────────────┐
│  EPISODIC   │ ───────────────►  │   ChromaDB      │
│  (Events,   │   Vector Search   │   Collection    │
│   History)  │                   │   "episodic"    │
└─────────────┘                   └─────────────────┘
       │                                    │
       │ Promotion                          │ Retrieval
       ▼                                    ▼
┌─────────────┐                   ┌─────────────────┐
│  WORKING    │ ───────────────►  │   SQLite FTS5   │
│  (Task ctx, │   Exact Match     │   Table         │
│   Temp)     │                   │   "working"     │
└─────────────┘                   └─────────────────┘
       │                                    │
       │                                    │ Retrieval
       ▼                                    ▼
┌─────────────┐                   ┌─────────────────┐
│ PROCEDURAL  │ ───────────────►  │   ChromaDB      │
│  (Skills,   │   Vector Search   │   Collection    │
│   Workflows)│                   │   "procedural"  │
└─────────────┘                   └─────────────────┘
       │                                    │
       │                                    │ Retrieval
       ▼                                    ▼
┌─────────────┐                   ┌─────────────────┐
│ PREFERENCE  │ ───────────────►  │   ChromaDB      │
│  (User      │   Vector Search   │   Collection    │
│   Prefs)    │                   │   "preference"  │
└─────────────┘                   └─────────────────┘
```

### 4.2 Consolidation Pipeline

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      MEMORY CONSOLIDATION PIPELINE                       │
└─────────────────────────────────────────────────────────────────────────┘

EVERY 6 HOURS (configurable):
┌──────────────────────────────────────────────────────────────────────┐
│ 1. WORKING → EPISODIC PROMOTION                                      │
│    - Scan working memories: importance ≥ 0.7, source ∈ {explicit,    │
│      correction}, age ≥ 1 hour                                       │
│    - Clone to episodic with episode_timestamp = created_at           │
│    - Mark working as promoted                                        │
└──────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│ 2. EPISODIC SUMMARIZATION                                            │
│    - Scan episodic: importance ≥ 0.8, age ≥ 30 days, not summarized  │
│    - LLM extracts semantic facts (max 5 per episode)                 │
│    - Store in semantic with source_episode reference                 │
│    - Mark episodic as summarized                                     │
└──────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│ 3. PROCEDURAL REINFORCEMENT                                          │
│    - Find procedures with success_count ≥ 3, failure_count = 0       │
│    - Increase importance by 0.1 (capped at 1.0)                      │
│    - Failed procedures: decrease importance, add to review queue     │
└──────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│ 4. PREFERENCE CONFLICT RESOLUTION                                    │
│    - Find preferences with same key, different values                │
│    - Resolve: explicit > inferred, recent > old, high importance     │
│    - Archive superseded, keep resolution rationale                   │
└──────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│ 5. CLEANUP                                                           │
│    - Delete expired working memories (TTL 24h default)               │
│    - Vacuum ChromaDB collections                                     │
│    - Update access statistics                                        │
└──────────────────────────────────────────────────────────────────────┘
```

### 4.3 Cross-Kind Retrieval

```python
async def retrieve_for_context(
    self,
    query: str,
    task_context: TaskContext,
    limit_per_kind: int = 5,
) -> Dict[MemoryKind, List[MemoryRecord]]:
    """Unified retrieval across all memory kinds"""
    
    # Parallel retrieval
    results = await asyncio.gather(*[
        self.retrieve(kind, query, limit_per_kind)
        for kind in MemoryKind
    ])
    
    # Re-rank by relevance to task context
    for kind, records in zip(MemoryKind, results):
        for record in records:
            record.relevance_score = self._score_relevance(record, task_context)
        records.sort(key=lambda r: r.relevance_score, reverse=True)
    
    return dict(zip(MemoryKind, results))
```

---

## 5. Evidence & Audit Trail

### 5.1 Evidence Bundle Structure

```python
@dataclass
class EvidenceRecord:
    id: str                              # UUID
    task_id: str
    step_id: str
    type: EvidenceType                   # OBSERVATION, ACTION, VERIFICATION, ARTIFACT
    source: str                          # adapter name, agent id, etc.
    content: str                         # Human-readable description
    data_ref: Optional[str]              # File path, screenshot path, log ref
    metadata: Dict[str, Any]
    timestamp: datetime
    hash: str                            # SHA-256 of content for integrity

@dataclass
class EvidenceBundle:
    task_id: str
    records: List[EvidenceRecord]
    created_at: datetime
    completed_at: Optional[datetime]
    integrity_hash: str                  # Merkle root of all records
    
    def verify_integrity(self) -> bool:
        """Verify no records have been tampered with"""
        computed = self._compute_merkle_root()
        return computed == self.integrity_hash
```

### 5.2 Evidence Flow

```
TASK EXECUTION                          EVIDENCE CREATION
─────────────────                       ───────────────────

Step 1: click_element("button#submit")  
    │
    ▼
UIA Adapter executes click              
    │
    ├─► Creates EvidenceRecord:
    │     type=OBSERVATION
    │     content="Clicked submit button"
    │     data_ref="screenshots/step_1_before.png"
    │     metadata={selector, rect, timestamp}
    │
    ▼
Step 2: wait_for_navigation()           
    │
    ▼
Playwright detects navigation           
    │
    ├─► Creates EvidenceRecord:
    │     type=VERIFICATION
    │     content="Navigation to /dashboard completed"
    │     data_ref="traces/step_2_trace.zip"
    │     metadata={url_before, url_after, network_logs}
    │
    ▼
... (more steps)

TASK COMPLETION                          EVIDENCE BUNDLE
──────────────────                       ─────────────────
                                           
TaskEngine.verify_completion()            
    │                                     EvidenceBundle:
    ├─► Collects all step evidence            task_id: "task_abc123"
    ├─► Computes Merkle root                  records: [ev_1, ev_2, ...]
    └─► Stores bundle                         integrity_hash: "sha256..."
                                               created_at: ...
                                               completed_at: now()
```

### 5.3 Evidence Storage

- **Metadata:** SQLite (evidence table) — fast queries by task, type, time
- **Artifacts:** Filesystem (`data/evidence/{task_id}/{record_id}.{ext}`)
- **Trace files:** Playwright traces, UIA screenshots, model responses
- **Retention:** Configurable (default 90 days), archive to cold storage after

---

## 6. Event Bus Architecture

### 6.1 Event Schema

```python
@dataclass
class SystemEvent:
    event_id: str = field(default_factory=lambda: f"evt_{uuid4().hex[:12]}")
    event_type: str                         # e.g., "task.created", "policy.grant_changed"
    source: str                             # Component that emitted
    timestamp: datetime = field(default_factory=datetime.utcnow)
    correlation_id: Optional[str] = None    # For tracing related events
    causation_id: Optional[str] = None      # Event that caused this
    payload: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
```

### 6.2 Core Event Types

| Event Type | Source | Payload | Consumers |
|------------|--------|---------|-----------|
| `task.created` | TaskEngine | task_id, objective, priority | Scheduler, UI |
| `task.state_changed` | TaskEngine | task_id, from_state, to_state | UI, Coordinator, Policy |
| `task.completed` | TaskEngine | task_id, result, evidence_bundle | Memory, UI, Scheduler |
| `task.failed` | TaskEngine | task_id, error, evidence_bundle | Memory, UI, Alerting |
| `approval.requested` | PolicyEngine | task_id, capability, risk_level | UI (modal) |
| `approval.granted` | UI | task_id, capability, grant_source | PolicyEngine |
| `approval.denied` | UI | task_id, capability, reason | PolicyEngine, TaskEngine |
| `policy.grant_changed` | PolicyEngine | subject, capability, action | All components |
| `agent.delegation_started` | Coordinator | delegation_id, parent_task, role | UI, Monitoring |
| `agent.delegation_completed` | Coordinator | delegation_id, result, evidence | TaskEngine, Memory |
| `memory.consolidated` | MemorySystem | stats {promoted, summarized, cleaned} | Monitoring |
| `voice.state_changed` | VoicePipeline | from_state, to_state | UI |
| `checkpoint.saved` | CheckpointStore | task_id, checkpoint_id, step | Recovery |
| `resource.contention` | ConcurrencyManager | task_id, resource, wait_time | Scheduler, UI |

### 6.3 Event Delivery Guarantees

| Guarantee | Implementation |
|-----------|----------------|
| **At-least-once** | In-process: direct async call; Redis: pub/sub with acknowledgment |
| **Ordering per correlation_id** | Single-threaded event processor per correlation_id |
| **Durability** | Critical events (task.*, policy.*) also written to SQLite event log |
| **Replay** | Event log supports full replay for debugging/recovery |

---

## 7. Frontend-Backend Synchronization

### 7.1 WebSocket Protocol (JSON-RPC 2.0)

```typescript
// Client → Server
interface ClientRequest {
  jsonrpc: "2.0";
  id: string | number;
  method: string;
  params?: any;
}

// Server → Client (Response)
interface ServerResponse {
  jsonrpc: "2.0";
  id: string | number;
  result?: any;
  error?: { code: number; message: string; data?: any };
}

// Server → Client (Notification/Event)
interface ServerNotification {
  jsonrpc: "2.0";
  method: string;  // e.g., "task.state_changed", "voice.transcript"
  params: any;
}
```

### 7.2 Key Methods

| Method | Direction | Description |
|--------|-----------|-------------|
| `task.submit` | C→S | Submit new task |
| `task.cancel` | C→S | Cancel running task |
| `task.pause` / `task.resume` | C→S | Pause/resume |
| `task.get_status` | C→S | Poll current status |
| `task.get_checkpoint` | C→S | Load checkpoint for resume |
| `policy.request_approval` | S→C | Request capability approval |
| `policy.grant_capability` | C→S | Grant approval |
| `voice.transcript` | S→C | Streaming transcript (partial/final) |
| `voice.state_changed` | S→C | Voice pipeline state |
| `agent.progress` | S→C | Specialist agent progress |
| `system.health` | C→S | Health check |

### 7.3 State Synchronization

```typescript
// Frontend maintains local task state
interface TaskViewModel {
  id: string;
  status: TaskStatus;
  progress: number;        // 0-100
  current_step: string;    // Human-readable
  transcript: string;      // Voice transcript
  evidence_count: number;
  error?: string;
}

// Sync strategy:
// 1. Initial load: GET /api/tasks/{id} → full state
// 2. Real-time: WebSocket notifications for state changes
// 3. Optimistic UI: Immediate feedback on user actions
// 4. Conflict resolution: Server state wins, show diff
```

---

## 8. Cross-Component Data Consistency

### 8.1 Consistency Boundaries

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    CONSISTENCY BOUNDARY MAP                              │
└─────────────────────────────────────────────────────────────────────────┘

STRONG CONSISTENCY (ACID)                    EVENTUAL CONSISTENCY
───────────────────────────                  ──────────────────────
✓ Task checkpoints (SQLite WAL)              ✓ Memory embeddings
✓ Policy grants (Cred Manager)               ✓ Agent-to-agent messages
✓ Evidence records (SQLite)                  ✓ UI notifications
✓ Model router circuit breakers              ✓ Metrics/telemetry
✓ Resource locks                             ✓ Search indexes

TRANSACTIONAL BOUNDARIES:
┌─────────────────────────────────────────────────────────────────────────┐
│ 1. TASK CREATION:                                                        │
│    - Policy assessment + Task insert + Initial checkpoint = ATOMIC     │
│    - If policy denies → no task created                                 │
└─────────────────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────────────────┐
│ 2. CAPABILITY GRANT:                                                     │
│    - Credential Manager write + In-memory cache update = ATOMIC        │
│    - Event emitted after both succeed                                   │
└─────────────────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────────────────┐
│ 3. TASK COMPLETION:                                                      │
│    - Final checkpoint + Evidence bundle + Memory stores = ATOMIC       │
│    - Compensation: if memory fails, task marked COMPLETED,             │
│      memory sync retried async                                           │
└─────────────────────────────────────────────────────────────────────────┘
```

### 8.2 Saga Pattern for Distributed Operations

```python
# Example: Multi-agent task with compensation
class MultiAgentTaskSaga:
    """Saga orchestrator for complex multi-agent tasks"""
    
    def __init__(self, runtime: "AppRuntime"):
        self.runtime = runtime
        self.steps: List[SagaStep] = []
        self.compensations: List[Callable] = []
    
    async def execute(self, task: Task) -> SagaResult:
        completed_steps = []
        
        try:
            for step in self.steps:
                result = await step.execute(task)
                completed_steps.append((step, result))
                
                # Register compensation
                if step.compensation:
                    self.compensations.append(step.compensation)
                    
        except Exception as e:
            # Execute compensations in reverse order
            for step, result in reversed(completed_steps):
                if step.compensation:
                    try:
                        await step.compensation(task, result)
                    except Exception as comp_error:
                        logger.error(f"Compensation failed: {comp_error}")
                        # Log for manual intervention
            raise
```

---

## 9. Data Migration & Schema Evolution

### 9.1 Versioning Strategy

| Store | Versioning | Migration Strategy |
|-------|------------|-------------------|
| SQLite (checkpoints, evidence, grants) | Schema version in `meta` table | ALTER TABLE + data migration scripts |
| ChromaDB (memory) | Collection metadata `schema_version` | Re-embed on major version change |
| Event log | Event schema version in payload | Upcast on read (backward compatible) |
| Config | Pydantic settings version | Automatic migration via defaults |

### 9.2 Migration Example

```sql
-- Migration: Add retry_count to checkpoints table (v2 → v3)
-- Version: 3
-- Date: 2026-11-10

BEGIN TRANSACTION;

-- Add column with default
ALTER TABLE checkpoints ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0;

-- Update version
UPDATE meta SET value = '3' WHERE key = 'schema_version';

COMMIT;
```

---

## 10. Performance Targets

| Operation | Target | Measurement |
|-----------|--------|-------------|
| Task submission → QUEUED | <100ms | p99 |
| State transition + checkpoint | <50ms | p99 |
| Policy check (cached) | <10ms | p99 |
| Policy check (uncached) | <200ms | p99 |
| Memory retrieval (vector) | <200ms | p99 |
| Memory retrieval (working) | <20ms | p99 |
| Event bus publish | <5ms | p99 |
| WebSocket message delivery | <50ms | p99 |
| Checkpoint recovery (100 steps) | <2s | p99 |
| Full system startup | <5s | p99 |

---

## 11. Open Data Flow Decisions

| Decision | Options | Considerations |
|----------|---------|----------------|
| Event bus backend | In-process / Redis / NATS | Scale vs simplicity |
| Checkpoint compression | None / zstd / lz4 | Large contexts vs CPU |
| Evidence deduplication | Content hash / semantic | Storage vs compute |
| Cross-device sync | None / SyncThing / Custom | User demand vs complexity |
| Streaming model responses | Server-Sent Events / WebSocket frames | Browser compatibility |
| Offline queue | Local SQLite / IndexedDB | Desktop vs web |