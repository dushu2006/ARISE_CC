# ARISE — API Specifications (OpenAPI 3.1)

## Overview

Complete OpenAPI 3.1 specifications for all internal and external APIs. These specs enable type-safe client generation, contract testing, and clear frontend-backend contracts.

---

## 1. Core Runtime API (WebSocket + JSON-RPC 2.0)

### 1.1 Connection

```yaml
# WebSocket endpoint: ws://localhost:8765/arise/v1
# Protocol: JSON-RPC 2.0 over WebSocket
# Authentication: None (local-only), capability-based auth per request
```

### 1.2 JSON-RPC Methods

```json
{
  "jsonrpc": "2.0",
  "method": "task.create",
  "params": {
    "objective": "string",
    "context": {},
    "priority": "normal|high|low",
    "capabilities_requested": ["filesystem.read", "ui.click"]
  },
  "id": "req-123"
}
```

### 1.3 Method Catalog

| Method | Params | Returns | Description |
|--------|--------|---------|-------------|
| `task.create` | `{objective, context?, priority?, capabilities_requested?}` | `{task_id, status}` | Create new task |
| `task.get` | `{task_id}` | `Task` | Get task status/result |
| `task.list` | `{status?, limit?, offset?}` | `{tasks[], total}` | List tasks |
| `task.cancel` | `{task_id, reason?}` | `{success}` | Cancel task |
| `task.approve` | `{task_id, approved, grant_scope?}` | `{success}` | Approve/deny R2+ task |
| `voice.start` | `{language?, privacy_mode?}` | `{session_id}` | Start voice session |
| `voice.stop` | `{session_id}` | `{success}` | Stop voice session |
| `voice.barge_in` | `{session_id}` | `{success}` | Interrupt current TTS |
| `memory.query` | `{query, kinds?, k?, filters?}` | `{results[]}` | Semantic search |
| `memory.store` | `{kind, content, metadata?}` | `{memory_id}` | Store memory |
| `memory.export` | `{kinds?, format?}` | `{data}` | Export memories |
| `memory.delete` | `{memory_id? kind? all?}` | `{deleted_count}` | Delete memories |
| `agent.execute` | `{agent_id, task, context, capabilities}` | `{result, evidence[]}` | Execute agent task |
| `agent.list` | `{}` | `{agents[]}` | List available agents |
| `system.health` | `{}` | `HealthStatus` | System health check |
| `system.metrics` | `{}` | `MetricsSnapshot` | Prometheus metrics |
| `config.get` | `{key?}` | `{config}` | Get configuration |
| `config.set` | `{key, value}` | `{success}` | Set configuration |
| `scheduler.create` | `{name, cron, objective, context}` | `{schedule_id}` | Create scheduled task |
| `scheduler.list` | `{}` | `{schedules[]}` | List scheduled tasks |
| `scheduler.trigger` | `{schedule_id}` | `{task_id}` | Trigger scheduled task now |
| `scheduler.delete` | `{schedule_id}` | `{success}` | Delete scheduled task |

### 1.4 Event Notifications (Server → Client)

```json
{
  "jsonrpc": "2.0",
  "method": "event.task_status",
  "params": {
    "task_id": "task-123",
    "status": "RUNNING",
    "progress": 0.5,
    "current_step": "executing_action"
  }
}
```

| Event | Payload | Description |
|-------|---------|-------------|
| `event.task_status` | `{task_id, status, progress?, current_step?, result?, error?}` | Task state changes |
| `event.approval_requested` | `{task_id, capability, risk_level, resource, description, expires_at}` | R2+ approval needed |
| `event.voice_state` | `{session_id, state, transcript?, intent?}` | Voice pipeline state |
| `event.agent_delegated` | `{parent_task_id, agent_id, subtask_objective}` | Agent delegation |
| `event.memory_consolidated` | `{kind, count, timestamp}` | Consolidation cycle complete |
| `event.security_alert` | `{type, severity, details}` | Security events |
| `event.resource_warning` | `{pool, current, limit, unit}` | Resource soft limit |
| `event.scheduler_triggered` | `{schedule_id, task_id}` | Scheduled task fired |

---

## 2. Task Engine REST API (HTTP)

### 2.1 Base URL

```
http://localhost:8766/api/v1
```

### 2.2 OpenAPI Spec

```yaml
openapi: 3.1.0
info:
  title: ARISE Task Engine API
  version: 1.0.0
  description: REST API for task management
servers:
  - url: http://localhost:8766/api/v1
paths:
  /tasks:
    post:
      operationId: createTask
      summary: Create a new task
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateTaskRequest'
      responses:
        '201':
          description: Task created
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/TaskResponse'
        '400':
          $ref: '#/components/responses/BadRequest'
        '401':
          $ref: '#/components/responses/Unauthorized'
    get:
      operationId: listTasks
      summary: List tasks with filters
      parameters:
        - name: status
          in: query
          schema:
            type: string
            enum: [CREATED, QUEUED, UNDERSTANDING, PLANNING, READY, RUNNING, WAITING_APPROVAL, WAITING_CAPABILITY, WAITING_RESOURCE, WAITING_EXTERNAL, VERIFYING, COMPLETED, FAILED, CANCELLED]
        - name: limit
          in: query
          schema:
            type: integer
            default: 50
            maximum: 200
        - name: offset
          in: query
          schema:
            type: integer
            default: 0
      responses:
        '200':
          description: Task list
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/TaskListResponse'
  /tasks/{task_id}:
    get:
      operationId: getTask
      summary: Get task by ID
      parameters:
        - name: task_id
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Task details
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/TaskResponse'
        '404':
          $ref: '#/components/responses/NotFound'
    delete:
      operationId: cancelTask
      summary: Cancel a task
      parameters:
        - name: task_id
          in: path
          required: true
          schema:
            type: string
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                reason:
                  type: string
      responses:
        '200':
          description: Task cancelled
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/CancelResponse'
        '404':
          $ref: '#/components/responses/NotFound'
        '409':
          $ref: '#/components/responses/Conflict'
  /tasks/{task_id}/approve:
    post:
      operationId: approveTask
      summary: Approve or deny a task requiring approval
      parameters:
        - name: task_id
          in: path
          required: true
          schema:
            type: string
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ApprovalRequest'
      responses:
        '200':
          description: Approval processed
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ApprovalResponse'
        '400':
          $ref: '#/components/responses/BadRequest'
        '404':
          $ref: '#/components/responses/NotFound'
        '409':
          $ref: '#/components/responses/Conflict'
  /tasks/{task_id}/checkpoints:
    get:
      operationId: listCheckpoints
      summary: List checkpoints for a task
      parameters:
        - name: task_id
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Checkpoint list
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/Checkpoint'
  /tasks/{task_id}/recover:
    post:
      operationId: recoverTask
      summary: Recover task from latest checkpoint
      parameters:
        - name: task_id
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Task recovered
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/TaskResponse'
        '404':
          $ref: '#/components/responses/NotFound'
        '409':
          $ref: '#/components/responses/Conflict'

components:
  schemas:
    CreateTaskRequest:
      type: object
      required:
        - objective
      properties:
        objective:
          type: string
          minLength: 1
          maxLength: 10000
        context:
          type: object
          additionalProperties: true
          default: {}
        priority:
          type: string
          enum: [low, normal, high]
          default: normal
        capabilities_requested:
          type: array
          items:
            type: string
          default: []
        scheduled_for:
          type: string
          format: date-time
    TaskResponse:
      type: object
      properties:
        task_id:
          type: string
        objective:
          type: string
        status:
          type: string
          enum: [CREATED, QUEUED, UNDERSTANDING, PLANNING, READY, RUNNING, WAITING_APPROVAL, WAITING_CAPABILITY, WAITING_RESOURCE, WAITING_EXTERNAL, VERIFYING, COMPLETED, FAILED, CANCELLED]
        context:
          type: object
        result:
          type: object
        error:
          type: string
        risk_level:
          type: string
          enum: [R0, R1, R2, R3, R4]
        required_capabilities:
          type: array
          items:
            type: string
        granted_capabilities:
          type: array
          items:
            type: string
        created_at:
          type: string
          format: date-time
        updated_at:
          type: string
          format: date-time
        started_at:
          type: string
          format: date-time
        completed_at:
          type: string
          format: date-time
        checkpoint:
          $ref: '#/components/schemas/Checkpoint'
    TaskListResponse:
      type: object
      properties:
        tasks:
          type: array
          items:
            $ref: '#/components/schemas/TaskResponse'
        total:
          type: integer
        limit:
          type: integer
        offset:
          type: integer
    Checkpoint:
      type: object
      properties:
        checkpoint_id:
          type: string
        task_id:
          type: string
        step:
          type: integer
        state:
          type: string
        context:
          type: object
        created_at:
          type: string
          format: date-time
    ApprovalRequest:
      type: object
      required:
        - approved
      properties:
        approved:
          type: boolean
        grant_scope:
          type: string
          enum: [task, session, permanent]
          default: task
        grant_duration_hours:
          type: integer
          minimum: 1
          maximum: 168
    ApprovalResponse:
      type: object
      properties:
        success:
          type: boolean
        grant_id:
          type: string
        message:
          type: string
    CancelResponse:
      type: object
      properties:
        success:
          type: boolean
        message:
          type: string
  responses:
    BadRequest:
      description: Invalid request
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/ErrorResponse'
    Unauthorized:
      description: Authentication required
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/ErrorResponse'
    NotFound:
      description: Resource not found
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/ErrorResponse'
    Conflict:
      description: Resource conflict
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/ErrorResponse'
    ErrorResponse:
      type: object
      properties:
        error:
          type: object
          properties:
            code:
              type: string
            message:
              type: string
            details:
              type: object
```

---

## 3. Voice Pipeline API

### 3.1 WebSocket Sub-protocol

```
ws://localhost:8765/arise/v1/voice
```

### 3.2 Messages (Client → Server)

```typescript
interface VoiceClientMessage {
  type: 'start_session' | 'audio_chunk' | 'barge_in' | 'stop_session' | 'set_privacy_mode';
  payload: {
    // start_session
    language?: 'en' | 'te';
    privacy_mode?: 'standard' | 'private' | 'local_only' | 'offline';
    wake_word_sensitivity?: number; // 0.0-1.0
    
    // audio_chunk
    audio_data?: string; // base64 encoded PCM16 16kHz mono
    timestamp?: number;
    is_final?: boolean;
    
    // barge_in
    // (no payload)
    
    // stop_session
    // (no payload)
    
    // set_privacy_mode
    privacy_mode?: 'standard' | 'private' | 'local_only' | 'offline';
  };
  request_id: string;
}
```

### 3.3 Messages (Server → Client)

```typescript
interface VoiceServerMessage {
  type: 'session_started' | 'wake_word_detected' | 'listening_started' | 
        'partial_transcript' | 'final_transcript' | 'intent_classified' | 
        'processing_started' | 'speaking_started' | 'audio_chunk' | 
        'speaking_finished' | 'session_ended' | 'error' | 'privacy_mode_changed';
  payload: {
    // session_started
    session_id?: string;
    expires_at?: string;
    
    // wake_word_detected
    confidence?: number;
    keyword?: string;
    
    // partial_transcript / final_transcript
    transcript?: string;
    is_final?: boolean;
    language?: 'en' | 'te';
    
    // intent_classified
    intent?: IntentClassification;
    
    // audio_chunk (TTS)
    audio_data?: string; // base64 encoded Opus/PCM
    format?: 'opus' | 'pcm16';
    sample_rate?: number;
    is_final?: boolean;
    
    // error
    code?: string;
    message?: string;
    recoverable?: boolean;
  };
  request_id?: string; // for request-response correlation
}
```

---

## 4. Memory System API

### 4.1 REST Endpoints

```yaml
paths:
  /memory/query:
    post:
      operationId: queryMemory
      summary: Semantic search across memory kinds
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - query
              properties:
                query:
                  type: string
                  minLength: 1
                kinds:
                  type: array
                  items:
                    type: string
                    enum: [semantic, episodic, procedural, preference, working]
                  default: [semantic, episodic, procedural, preference]
                k:
                  type: integer
                  default: 10
                  minimum: 1
                  maximum: 100
                filters:
                  type: object
                  properties:
                    date_from:
                      type: string
                      format: date-time
                    date_to:
                      type: string
                      format: date-time
                    tags:
                      type: array
                      items:
                        type: string
                    source:
                      type: string
                rerank:
                  type: boolean
                  default: true
      responses:
        '200':
          description: Search results
          content:
            application/json:
              schema:
                type: object
                properties:
                  results:
                    type: array
                    items:
                      $ref: '#/components/schemas/MemoryResult'
                  query_time_ms:
                    type: number
  /memory/store:
    post:
      operationId: storeMemory
      summary: Store a new memory
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - kind
                - content
              properties:
                kind:
                  type: string
                  enum: [semantic, episodic, procedural, preference, working]
                content:
                  type: string
                  minLength: 1
                metadata:
                  type: object
                  properties:
                    source:
                      type: string
                    tags:
                      type: array
                      items:
                        type: string
                    confidence:
                      type: number
                      minimum: 0
                      maximum: 1
                      default: 1.0
                    entities:
                      type: array
                      items:
                        type: object
      responses:
        '201':
          description: Memory stored
          content:
            application/json:
              schema:
                type: object
                properties:
                  memory_id:
                    type: string
  /memory/{memory_id}:
    get:
      operationId: getMemory
      summary: Get memory by ID
      parameters:
        - name: memory_id
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Memory details
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/MemoryEntry'
        '404':
          $ref: '#/components/responses/NotFound'
    patch:
      operationId: updateMemory
      summary: Update memory (correction)
      parameters:
        - name: memory_id
          in: path
          required: true
          schema:
            type: string
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                content:
                  type: string
                metadata:
                  type: object
      responses:
        '200':
          description: Memory updated
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/MemoryEntry'
        '404':
          $ref: '#/components/responses/NotFound'
    delete:
      operationId: deleteMemory
      summary: Delete memory
      parameters:
        - name: memory_id
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Memory deleted
          content:
            application/json:
              schema:
                type: object
                properties:
                  success:
                    type: boolean
        '404':
          $ref: '#/components/responses/NotFound'
  /memory/export:
    post:
      operationId: exportMemory
      summary: Export all memories
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                kinds:
                  type: array
                  items:
                    type: string
                    enum: [semantic, episodic, procedural, preference, working]
                format:
                  type: string
                  enum: [jsonl, json, csv]
                  default: jsonl
                include_metadata:
                  type: boolean
                  default: true
      responses:
        '200':
          description: Exported data
          content:
            application/json:
              schema:
                type: object
                properties:
                  data:
                    type: string
                  format:
                    type: string
                  count:
                    type: integer
  /memory/import:
    post:
      operationId: importMemory
      summary: Import memories
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - data
                - format
              properties:
                data:
                  type: string
                format:
                  type: string
                  enum: [jsonl, json, csv]
                merge_strategy:
                  type: string
                  enum: [skip, overwrite, merge]
                  default: merge
      responses:
        '200':
          description: Import result
          content:
            application/json:
              schema:
                type: object
                properties:
                  imported:
                    type: integer
                  skipped:
                    type: integer
                  errors:
                    type: array
                    items:
                      type: string
  /memory/delete_all:
    post:
      operationId: deleteAllMemories
      summary: Delete all memories (requires confirmation)
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - confirmation
              properties:
                confirmation:
                  type: string
                  enum: ['DELETE_ALL_MEMORIES']
                kinds:
                  type: array
                  items:
                    type: string
                    enum: [semantic, episodic, procedural, preference, working]
      responses:
        '200':
          description: Deletion result
          content:
            application/json:
              schema:
                type: object
                properties:
                  deleted_count:
                    type: integer

components:
  schemas:
    MemoryResult:
      type: object
      properties:
        memory_id:
          type: string
        kind:
          type: string
        content:
          type: string
        score:
          type: number
        metadata:
          type: object
        created_at:
          type: string
          format: date-time
    MemoryEntry:
      type: object
      properties:
        memory_id:
          type: string
        kind:
          type: string
        content:
          type: string
        metadata:
          type: object
        created_at:
          type: string
          format: date-time
        updated_at:
          type: string
          format: date-time
        version:
          type: integer
```

---

## 5. Agent Coordination API

### 5.1 JSON-RPC Methods

```typescript
// Agent Registry
interface AgentInfo {
  agent_id: string;
  name: string;
  description: string;
  capabilities: AgentCapability[];
  version: string;
  health: 'healthy' | 'degraded' | 'unhealthy';
  last_heartbeat: string;
}

interface AgentCapability {
  name: string;
  description: string;
  required_capabilities: string[]; // System capabilities
  input_schema: JSONSchema;
  output_schema: JSONSchema;
}

// Delegation Protocol
interface DelegateRequest {
  parent_task_id: string;
  agent_id: string;
  objective: string;
  context: Record<string, any>;
  granted_capabilities: string[]; // Subset of agent's declared capabilities
  timeout_seconds: number;
  verification_required: boolean;
}

interface DelegateResponse {
  delegation_id: string;
  status: 'accepted' | 'rejected' | 'queued';
  estimated_duration_seconds?: number;
}

// Agent Execution
interface ExecuteRequest {
  delegation_id: string;
  task: AgentTask;
}

interface AgentTask {
  id: string;
  objective: string;
  context: Record<string, any>;
  granted_capabilities: string[];
  parent_task_id?: string;
}

interface ExecuteResponse {
  status: 'completed' | 'failed' | 'cancelled';
  result: Record<string, any>;
  evidence: EvidenceRecord[];
  error?: string;
  execution_time_ms: number;
}

// Verification
interface VerifyRequest {
  delegation_id: string;
  original_objective: string;
  agent_result: Record<string, any>;
  evidence: EvidenceRecord[];
}

interface VerifyResponse {
  verified: boolean;
  issues: VerificationIssue[];
  suggested_fix?: Record<string, any>;
}

interface VerificationIssue {
  type: 'logic_error' | 'security_violation' | 'incomplete' | 'hallucination' | 'policy_violation';
  severity: 'critical' | 'major' | 'minor';
  description: string;
  location?: string;
}
```

---

## 6. Configuration API

### 6.1 Schema (JSON Schema)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "app": {
      "type": "object",
      "properties": {
        "name": { "type": "string", "default": "ARISE" },
        "version": { "type": "string" },
        "data_dir": { "type": "string", "default": "data" },
        "log_level": { "type": "string", "enum": ["DEBUG", "INFO", "WARNING", "ERROR"], "default": "INFO" },
        "privacy_mode": { "type": "string", "enum": ["standard", "private", "local_only", "offline"], "default": "standard" }
      },
      "required": ["data_dir"]
    },
    "security": {
      "type": "object",
      "properties": {
        "credential_backend": { "type": "string", "enum": ["windows_credential_manager"], "default": "windows_credential_manager" },
        "prompt_defense_strictness": { "type": "string", "enum": ["permissive", "balanced", "strict"], "default": "balanced" },
        "audit_log_path": { "type": "string", "default": "data/security/audit.sqlite" },
        "audit_retention_days": { "type": "integer", "default": 365 },
        "network_policy": { "type": "string", "enum": ["allow_list", "deny_list", "local_only"], "default": "allow_list" },
        "certificate_pinning": { "type": "boolean", "default": true }
      }
    },
    "policy": {
      "type": "object",
      "properties": {
        "default_risk_level": { "type": "string", "enum": ["R0", "R1", "R2", "R3", "R4"], "default": "R1" },
        "approval_timeout_seconds": { "type": "integer", "default": 300 },
        "max_grant_duration_hours": { "type": "integer", "default": 24 },
        "strict_mode": { "type": "boolean", "default": false }
      }
    },
    "model_router": {
      "type": "object",
      "properties": {
        "providers": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "name": { "type": "string" },
              "type": { "type": "string", "enum": ["gemini", "openai", "anthropic", "ollama", "local"] },
              "api_key_env": { "type": "string" },
              "base_url": { "type": "string" },
              "models": {
                "type": "array",
                "items": {
                  "type": "object",
                  "properties": {
                    "name": { "type": "string" },
                    "task_types": { "type": "array", "items": { "type": "string" } },
                    "max_tokens": { "type": "integer" },
                    "supports_streaming": { "type": "boolean" },
                    "supports_vision": { "type": "boolean" },
                    "cost_per_1k_input": { "type": "number" },
                    "cost_per_1k_output": { "type": "number" }
                  },
                  "required": ["name", "task_types"]
                }
              },
              "priority": { "type": "integer" },
              "enabled": { "type": "boolean", "default": true }
            },
            "required": ["name", "type", "models"]
          }
        },
        "default_task_type": { "type": "string", "default": "general" },
        "circuit_breaker": {
          "type": "object",
          "properties": {
            "failure_threshold": { "type": "integer", "default": 5 },
            "timeout_seconds": { "type": "integer", "default": 30 },
            "half_open_requests": { "type": "integer", "default": 3 }
          }
        }
      }
    },
    "voice": {
      "type": "object",
      "properties": {
        "wake_word": {
          "type": "object",
          "properties": {
            "keywords": { "type": "array", "items": { "type": "string" }, "default": ["arise"] },
            "sensitivity": { "type": "number", "minimum": 0, "maximum": 1, "default": 0.5 },
            "model_path": { "type": "string" }
          }
        },
        "asr": {
          "type": "object",
          "properties": {
            "engine": { "type": "string", "enum": ["sherpa_onnx", "whisper_cpp", "gemini_live"], "default": "sherpa_onnx" },
            "model_path": { "type": "string" },
            "language": { "type": "string", "enum": ["en", "te", "auto"], "default": "auto" },
            "streaming": { "type": "boolean", "default": true }
          }
        },
        "tts": {
          "type": "object",
          "properties": {
            "fallback_chain": {
              "type": "array",
              "items": {
                "type": "object",
                "properties": {
                  "provider": { "type": "string", "enum": ["elevenlabs", "openai", "piper", "system"] },
                  "voice_id": { "type": "string" },
                  "model": { "type": "string" },
                  "api_key_env": { "type": "string" }
                },
                "required": ["provider"]
              }
            },
            "streaming": { "type": "boolean", "default": true }
          }
        },
        "audio": {
          "type": "object",
          "properties": {
            "input_device": { "type": "string" },
            "output_device": { "type": "string" },
            "sample_rate": { "type": "integer", "default": 16000 },
            "echo_cancellation": { "type": "boolean", "default": true }
          }
        },
        "session": {
          "type": "object",
          "properties": {
            "token_duration_minutes": { "type": "integer", "default": 30 },
            "max_session_minutes": { "type": "integer", "default": 480 }
          }
        }
      }
    },
    "memory": {
      "type": "object",
      "properties": {
        "vector_store": {
          "type": "object",
          "properties": {
            "type": { "type": "string", "enum": ["chromadb", "qdrant", "lancedb"], "default": "chromadb" },
            "path": { "type": "string", "default": "data/memory/vectors" },
            "collections": {
              "type": "object",
              "properties": {
                "semantic": { "type": "string", "default": "semantic_memories" },
                "episodic": { "type": "string", "default": "episodic_memories" },
                "procedural": { "type": "string", "default": "procedural_memories" },
                "preference": { "type": "string", "default": "preference_memories" },
                "working": { "type": "string", "default": "working_memories" }
              }
            }
          }
        },
        "fts_store": {
          "type": "object",
          "properties": {
            "path": { "type": "string", "default": "data/memory/fts.sqlite" }
          }
        },
        "consolidation": {
          "type": "object",
          "properties": {
            "working_to_episodic_hours": { "type": "integer", "default": 1 },
            "episodic_summarization_daily": { "type": "boolean", "default": true },
            "procedural_reinforcement_weekly": { "type": "boolean", "default": true },
            "preference_conflict_resolution": { "type": "string", "enum": ["last_write_wins", "user_confirm", "merge"], "default": "user_confirm" },
            "cleanup_enabled": { "type": "boolean", "default": true },
            "max_memories_per_kind": {
              "type": "object",
              "properties": {
                "semantic": { "type": "integer", "default": 100000 },
                "episodic": { "type": "integer", "default": 50000 },
                "procedural": { "type": "integer", "default": 10000 },
                "preference": { "type": "integer", "default": 1000 },
                "working": { "type": "integer", "default": 1000 }
              }
            }
          }
        },
        "pii_detection": {
          "type": "object",
          "properties": {
            "enabled": { "type": "boolean", "default": true },
            "engine": { "type": "string", "enum": ["presidio", "regex"], "default": "presidio" },
            "action": { "type": "string", "enum": ["flag", "redact", "block"], "default": "flag" }
          }
        }
      }
    },
    "performance": {
      "type": "object",
      "properties": {
        "resource_limits": {
          "type": "object",
          "properties": {
            "cpu_percent_soft": { "type": "number", "default": 70 },
            "cpu_percent_hard": { "type": "number", "default": 85 },
            "memory_mb_soft": { "type": "integer", "default": 4096 },
            "memory_mb_hard": { "type": "integer", "default": 6144 },
            "model_concurrency_soft": { "type": "integer", "default": 3 },
            "model_concurrency_hard": { "type": "integer", "default": 5 },
            "browser_concurrency_soft": { "type": "integer", "default": 2 },
            "browser_concurrency_hard": { "type": "integer", "default": 3 },
            "agent_concurrency_soft": { "type": "integer", "default": 5 },
            "agent_concurrency_hard": { "type": "integer", "default": 8 }
          }
        },
        "caching": {
          "type": "object",
          "properties": {
            "model_responses_l1_size": { "type": "integer", "default": 100 },
            "model_responses_l1_ttl": { "type": "integer", "default": 300 },
            "web_search_l1_size": { "type": "integer", "default": 50 },
            "web_search_l1_ttl": { "type": "integer", "default": 600 },
            "file_index_l1_size": { "type": "integer", "default": 200 },
            "file_index_l1_ttl": { "type": "integer", "default": 300 }
          }
        }
      }
    }
  },
  "required": ["app", "security", "policy", "model_router", "voice", "memory", "performance"]
}
```

---

## 7. Error Code Reference

### 7.1 System Error Codes

| Code | HTTP | Description | Retryable |
|------|------|-------------|-----------|
| `INVALID_REQUEST` | 400 | Request validation failed | No |
| `UNAUTHORIZED` | 401 | Missing/invalid authentication | No |
| `FORBIDDEN` | 403 | Capability denied | No |
| `NOT_FOUND` | 404 | Resource not found | No |
| `CONFLICT` | 409 | State conflict (e.g., task not cancellable) | No |
| `RATE_LIMITED` | 429 | Too many requests | Yes |
| `INTERNAL_ERROR` | 500 | Unexpected server error | Yes |
| `SERVICE_UNAVAILABLE` | 503 | Dependency unavailable | Yes |
| `TIMEOUT` | 504 | Operation timed out | Yes |

### 7.2 Domain Error Codes

| Code | Domain | Description |
|------|--------|-------------|
| `TASK_NOT_FOUND` | Task | Task ID doesn't exist |
| `TASK_NOT_CANCELLABLE` | Task | Task in non-cancellable state |
| `APPROVAL_EXPIRED` | Policy | Approval request timed out |
| `APPROVAL_DENIED` | Policy | User denied approval |
| `CAPABILITY_DENIED` | Policy | Required capability not granted |
| `RISK_TOO_HIGH` | Policy | Action exceeds max allowed risk |
| `PROVIDER_UNAVAILABLE` | Model | All providers failed |
| `CIRCUIT_OPEN` | Model | Circuit breaker open |
| `WAKE_WORD_NOT_LOADED` | Voice | Wake word model not loaded |
| `ASR_FAILED` | Voice | Speech recognition failed |
| `TTS_FAILED` | Voice | Text-to-speech failed |
| `SESSION_EXPIRED` | Voice | Voice session token expired |
| `MEMORY_STORE_FULL` | Memory | Vector store at capacity |
| `PII_DETECTED` | Memory | PII found in content |
| `AGENT_UNHEALTHY` | Agent | Agent failed health check |
| `AGENT_TIMEOUT` | Agent | Agent execution timed out |
| `VERIFICATION_FAILED` | Agent | Independent verification failed |
| `UIA_ELEMENT_NOT_FOUND` | Automation | UIA element not found |
| `PLAYWRIGHT_NAVIGATION_FAILED` | Automation | Page navigation failed |
| `CV_OCR_LOW_CONFIDENCE` | Automation | Computer vision confidence too low |
| `CREDENTIAL_NOT_FOUND` | Security | Credential not in Credential Manager |
| `NETWORK_BLOCKED` | Security | Egress blocked by policy |
| `AUDIT_TAMPERED` | Security | Audit log integrity check failed |

---

## 8. Client SDK Generation

### 8.1 Commands

```bash
# Generate Python client
openapi-generator-cli generate \
  -i api_spec.yaml \
  -g python \
  -o ./generated/python \
  --additional-properties=packageName=arise_client,projectName=ARISE

# Generate TypeScript client
openapi-generator-cli generate \
  -i api_spec.yaml \
  -g typescript-axios \
  -o ./generated/typescript \
  --additional-properties=npmName=@arise/client,npmVersion=1.0.0

# Generate Rust client
openapi-generator-cli generate \
  -i api_spec.yaml \
  -g rust \
  -o ./generated/rust \
  --additional-properties=packageName=arise_client
```

### 8.2 Usage Example (Python)

```python
from arise_client import AriseClient, CreateTaskRequest

client = AriseClient(base_url="http://localhost:8766/api/v1")

# Create task
task = client.create_task(CreateTaskRequest(
    objective="Open Chrome and navigate to GitHub",
    priority="normal"
))

# Wait for completion
result = client.wait_for_task(task.task_id, timeout=60)
print(result.result)

# Voice session via WebSocket
async with client.voice_session() as session:
    await session.start(language="en")
    async for event in session.events():
        print(event)
```

---

## 9. Versioning & Compatibility

| Version | Status | Supported Until | Breaking Changes |
|---------|--------|-----------------|------------------|
| v1.0 | Current | - | - |
| v0.9 | Deprecated | 2026-12-31 | Task state enum changed |
| v0.8 | Deprecated | 2026-09-30 | Memory API restructured |

### Compatibility Rules

1. **Minor versions**: Backward compatible (additive only)
2. **Major versions**: Breaking changes allowed
3. **Deprecation**: 6-month notice before removal
4. **Client SDK**: Pinned to major version, auto-update for minors

---

## 10. Testing Contract Compliance

### 10.1 Schemathesis Test

```python
import schemathesis
from hypothesis import given

schema = schemathesis.from_path("api_spec.yaml")

@schema.parametrize()
@given(case=schema["/tasks"]["POST"].as_strategy())
def test_task_creation(case):
    response = case.call()
    case.validate_response(response)
```

### 10.2 Pact Consumer-Driven Contracts

```yaml
# pact/arise_frontend-arise_backend.json
{
  "provider": { "name": "ARISE Backend" },
  "consumer": { "name": "ARISE Frontend" },
  "interactions": [
    {
      "description": "Create task via REST",
      "request": {
        "method": "POST",
        "path": "/api/v1/tasks",
        "body": { "objective": "Test task" }
      },
      "response": {
        "status": 201,
        "body": { "task_id": "task-123", "status": "CREATED" }
      }
    }
  ]
}
```