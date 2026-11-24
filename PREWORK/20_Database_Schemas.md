# ARISE — Database Schemas

## Overview

Complete SQL schemas for all persistent data stores. Uses SQLite with WAL mode for durability and performance.

---

## 1. Task Engine Database (`data/tasks/tasks.db`)

### 1.1 Tables

```sql
-- Main task table
CREATE TABLE tasks (
    task_id TEXT PRIMARY KEY,                    -- UUID v4
    objective TEXT NOT NULL,                     -- User's objective
    context_json TEXT NOT NULL DEFAULT '{}',     -- Full context as JSON
    status TEXT NOT NULL,                        -- 28-state enum
    risk_level TEXT NOT NULL DEFAULT 'R1',       -- R0-R4
    required_capabilities_json TEXT NOT NULL DEFAULT '[]', -- JSON array
    granted_capabilities_json TEXT NOT NULL DEFAULT '[]',  -- JSON array
    result_json TEXT,                            -- Task result as JSON
    error TEXT,                                  -- Error message if failed
    parent_task_id TEXT,                         -- For subtasks
    root_task_id TEXT,                           -- Top-level task
    priority INTEGER NOT NULL DEFAULT 0,         -- -1=low, 0=normal, 1=high
    created_at TEXT NOT NULL,                    -- ISO 8601 UTC
    updated_at TEXT NOT NULL,                    -- ISO 8601 UTC
    started_at TEXT,                             -- ISO 8601 UTC
    completed_at TEXT,                           -- ISO 8601 UTC
    timeout_at TEXT,                             -- ISO 8601 UTC
    retry_count INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER NOT NULL DEFAULT 3,
    saga_compensation_json TEXT,                 -- Compensation steps as JSON
    metadata_json TEXT NOT NULL DEFAULT '{}'     -- Extensible metadata
);

-- Checkpoints for crash recovery
CREATE TABLE task_checkpoints (
    checkpoint_id TEXT PRIMARY KEY,              -- UUID v4
    task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    step INTEGER NOT NULL,                       -- Step number
    state TEXT NOT NULL,                         -- State at checkpoint
    context_json TEXT NOT NULL,                  -- Full context snapshot
    executed_actions_json TEXT NOT NULL,         -- Actions executed so far
    created_at TEXT NOT NULL,                    -- ISO 8601 UTC
    is_latest INTEGER NOT NULL DEFAULT 0         -- Flag for latest checkpoint
);

-- Task dependencies (for DAG execution)
CREATE TABLE task_dependencies (
    task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    depends_on_task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    dependency_type TEXT NOT NULL DEFAULT 'sequential', -- sequential, parallel, conditional
    condition_json TEXT,                         -- Condition for conditional deps
    PRIMARY KEY (task_id, depends_on_task_id)
);

-- Task approvals
CREATE TABLE task_approvals (
    approval_id TEXT PRIMARY KEY,                -- UUID v4
    task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    capability TEXT NOT NULL,                    -- Capability requested
    risk_level TEXT NOT NULL,                    -- R2-R4
    resource TEXT,                               -- Target resource
    description TEXT,                            -- Human-readable description
    requested_at TEXT NOT NULL,                  -- ISO 8601 UTC
    responded_at TEXT,                           -- ISO 8601 UTC
    approved INTEGER,                            -- 1=approved, 0=denied, NULL=pending
    granted_by TEXT,                             -- user, system, policy
    grant_scope TEXT,                            -- task, session, permanent
    grant_duration_hours INTEGER,                -- For temporary grants
    expires_at TEXT,                             -- ISO 8601 UTC
    grant_id TEXT                                -- Reference to capability grant
);

-- Scheduled tasks
CREATE TABLE scheduled_tasks (
    schedule_id TEXT PRIMARY KEY,                -- UUID v4
    name TEXT NOT NULL UNIQUE,
    cron_expression TEXT NOT NULL,               -- 5-field cron
    objective TEXT NOT NULL,
    context_json TEXT NOT NULL DEFAULT '{}',
    enabled INTEGER NOT NULL DEFAULT 1,          -- 1=enabled, 0=disabled
    next_run_at TEXT,                            -- ISO 8601 UTC
    last_run_at TEXT,                            -- ISO 8601 UTC
    last_task_id TEXT,                           -- Reference to last created task
    created_at TEXT NOT NULL,                    -- ISO 8601 UTC
    updated_at TEXT NOT NULL,                    -- ISO 8601 UTC
    timezone TEXT NOT NULL DEFAULT 'local',      -- IANA timezone
    max_catchup_runs INTEGER NOT NULL DEFAULT 1, -- For missed runs
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

-- Task events (for debugging/replay)
CREATE TABLE task_events (
    event_id TEXT PRIMARY KEY,                   -- UUID v4
    task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,                    -- status_change, step_complete, error, etc.
    from_state TEXT,                             -- Previous state
    to_state TEXT,                               -- New state
    step INTEGER,                                -- Current step
    message TEXT,                                -- Human-readable message
    details_json TEXT,                           -- Additional details
    created_at TEXT NOT NULL                     -- ISO 8601 UTC
);

-- Indexes
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_root ON tasks(root_task_id);
CREATE INDEX idx_tasks_parent ON tasks(parent_task_id);
CREATE INDEX idx_tasks_created ON tasks(created_at DESC);
CREATE INDEX idx_checkpoints_task ON task_checkpoints(task_id);
CREATE INDEX idx_checkpoints_latest ON task_checkpoints(task_id, is_latest);
CREATE INDEX idx_approvals_task ON task_approvals(task_id);
CREATE INDEX idx_approvals_pending ON task_approvals(approved) WHERE approved IS NULL;
CREATE INDEX idx_scheduled_next_run ON scheduled_tasks(next_run_at) WHERE enabled = 1;
CREATE INDEX idx_events_task ON task_events(task_id, created_at);
```

### 1.2 Views

```sql
-- Active tasks view
CREATE VIEW active_tasks AS
SELECT * FROM tasks 
WHERE status IN ('CREATED', 'QUEUED', 'UNDERSTANDING', 'PLANNING', 'READY', 'RUNNING', 
                 'WAITING_APPROVAL', 'WAITING_CAPABILITY', 'WAITING_RESOURCE', 'WAITING_EXTERNAL', 'VERIFYING');

-- Task summary with duration
CREATE VIEW task_summary AS
SELECT 
    t.task_id,
    t.objective,
    t.status,
    t.risk_level,
    t.created_at,
    t.started_at,
    t.completed_at,
    CASE 
        WHEN t.started_at AND t.completed_at THEN 
            (julianday(t.completed_at) - julianday(t.started_at)) * 86400
        WHEN t.started_at THEN 
            (julianday('now') - julianday(t.started_at)) * 86400
        ELSE NULL
    END as duration_seconds
FROM tasks t;

-- Pending approvals
CREATE VIEW pending_approvals AS
SELECT a.*, t.objective, t.context_json
FROM task_approvals a
JOIN tasks t ON a.task_id = t.task_id
WHERE a.approved IS NULL
AND (a.expires_at IS NULL OR a.expires_at > datetime('now'));
```

---

## 2. Audit Log Database (`data/security/audit.sqlite`)

### 2.1 Tables

```sql
-- Immutable audit log with hash chain
CREATE TABLE audit_log (
    event_id TEXT PRIMARY KEY,                   -- audit_{uuid}
    event_type TEXT NOT NULL,                    -- Enum: AuditEventType
    timestamp TEXT NOT NULL,                     -- ISO 8601 UTC
    user_id TEXT NOT NULL DEFAULT 'local_user',
    session_id TEXT,                             -- Voice/task session
    task_id TEXT,                                -- Related task
    agent_id TEXT,                               -- Related agent
    action TEXT NOT NULL,                        -- Action performed
    resource TEXT,                               -- Target resource
    capability TEXT,                             -- Capability involved
    risk_level TEXT,                             -- R0-R4
    success INTEGER NOT NULL,                    -- 1=success, 0=failure
    error TEXT,                                  -- Error message
    context_json TEXT NOT NULL DEFAULT '{}',     -- Sanitized context (no secrets)
    previous_hash TEXT,                          -- Hash of previous event
    event_hash TEXT NOT NULL,                    -- SHA256 of this event
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Audit log verification checkpoints
CREATE TABLE audit_checkpoints (
    checkpoint_id TEXT PRIMARY KEY,
    last_event_id TEXT NOT NULL,
    last_hash TEXT NOT NULL,
    events_count INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    verified_by TEXT                             -- 'startup' | 'manual' | 'scheduled'
);

-- Security events (high-priority subset)
CREATE TABLE security_events (
    event_id TEXT PRIMARY KEY REFERENCES audit_log(event_id),
    severity TEXT NOT NULL,                      -- critical, high, medium, low
    category TEXT NOT NULL,                      -- injection, auth, network, data, config
    source_ip TEXT,                              -- If network event
    user_agent TEXT,                             -- If applicable
    mitre_technique TEXT,                        -- MITRE ATT&CK technique ID
    response_action TEXT,                        -- blocked, logged, alerted, lockdown
    acknowledged INTEGER NOT NULL DEFAULT 0,
    acknowledged_at TEXT,
    acknowledged_by TEXT
);

-- Indexes
CREATE INDEX idx_audit_timestamp ON audit_log(timestamp DESC);
CREATE INDEX idx_audit_task ON audit_log(task_id);
CREATE INDEX idx_audit_type ON audit_log(event_type);
CREATE INDEX idx_audit_user ON audit_log(user_id);
CREATE INDEX idx_security_severity ON security_events(severity);
CREATE INDEX idx_security_category ON security_events(category);
CREATE INDEX idx_security_ack ON security_events(acknowledged) WHERE acknowledged = 0;
```

### 2.2 Triggers for Hash Chain

```sql
-- Auto-compute hash on insert
CREATE TRIGGER audit_hash_chain
AFTER INSERT ON audit_log
BEGIN
    UPDATE audit_log 
    SET event_hash = (
        SELECT hex(sha256(
            NEW.event_id || '|' || 
            NEW.timestamp || '|' || 
            NEW.event_type || '|' || 
            NEW.action || '|' || 
            COALESCE(NEW.resource, '') || '|' || 
            CAST(NEW.success AS TEXT) || '|' || 
            COALESCE(previous_hash, '')
        ))
    )
    WHERE event_id = NEW.event_id;
    
    -- Update previous_hash for next insert
    UPDATE audit_log 
    SET previous_hash = (
        SELECT event_hash FROM audit_log 
        WHERE event_id = NEW.event_id
    )
    WHERE rowid = (SELECT MAX(rowid) FROM audit_log WHERE rowid > (SELECT rowid FROM audit_log WHERE event_id = NEW.event_id));
END;
```

---

## 3. Memory System Databases

### 3.1 Vector Store (ChromaDB - `data/memory/vectors/`)

ChromaDB manages its own schema. Collections per memory kind:

```python
# Collection configurations
COLLECTIONS = {
    "semantic_memories": {
        "metadata": {"hnsw:space": "cosine", "hnsw:construction_ef": 200, "hnsw:M": 16},
        "embedding_dim": 384,  # all-MiniLM-L6-v2
    },
    "episodic_memories": {
        "metadata": {"hnsw:space": "cosine", "hnsw:construction_ef": 200, "hnsw:M": 16},
        "embedding_dim": 384,
    },
    "procedural_memories": {
        "metadata": {"hnsw:space": "cosine", "hnsw:construction_ef": 200, "hnsw:M": 16},
        "embedding_dim": 384,
    },
    "preference_memories": {
        "metadata": {"hnsw:space": "cosine", "hnsw:construction_ef": 200, "hnsw:M": 16},
        "embedding_dim": 384,
    },
    "working_memories": {
        "metadata": {"hnsw:space": "cosine", "hnsw:construction_ef": 100, "hnsw:M": 8},
        "embedding_dim": 384,
    }
}
```

### 3.2 FTS5 Store (`data/memory/fts.sqlite`)

```sql
-- Full-text search for keyword-based retrieval
CREATE VIRTUAL TABLE memory_fts USING fts5(
    memory_id UNINDEXED,
    kind UNINDEXED,
    content,
    tags,
    source,
    metadata_json UNINDEXED,
    created_at UNINDEXED,
    tokenize = 'porter unicode61'
);

-- Sync trigger from vector store (application-level)
-- Application writes to both stores simultaneously

-- Memory metadata for governance
CREATE TABLE memory_metadata (
    memory_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    source TEXT,                                 -- user, agent, system, consolidation
    confidence REAL NOT NULL DEFAULT 1.0,        -- 0.0-1.0
    pii_detected INTEGER NOT NULL DEFAULT 0,     -- 1=PII flagged
    pii_types_json TEXT,                         -- JSON array of PII types
    retention_expires_at TEXT,                   -- ISO 8601 UTC
    access_count INTEGER NOT NULL DEFAULT 0,
    last_accessed_at TEXT,                       -- ISO 8601 UTC
    created_at TEXT NOT NULL,                    -- ISO 8601 UTC
    updated_at TEXT NOT NULL,                    -- ISO 8601 UTC
    version INTEGER NOT NULL DEFAULT 1,
    previous_version_id TEXT,                    -- For corrections
    is_archived INTEGER NOT NULL DEFAULT 0
);

-- Consolidation tracking
CREATE TABLE consolidation_runs (
    run_id TEXT PRIMARY KEY,                     -- UUID v4
    kind TEXT NOT NULL,                          -- working_to_episodic, episodic_summarization, etc.
    started_at TEXT NOT NULL,                    -- ISO 8601 UTC
    completed_at TEXT,                           -- ISO 8601 UTC
    input_count INTEGER NOT NULL DEFAULT 0,
    output_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,                        -- running, completed, failed
    error TEXT,
    config_json TEXT                             -- Consolidation config used
);

-- Indexes
CREATE INDEX idx_memory_metadata_kind ON memory_metadata(kind);
CREATE INDEX idx_memory_metadata_pii ON memory_metadata(pii_detected) WHERE pii_detected = 1;
CREATE INDEX idx_memory_metadata_expires ON memory_metadata(retention_expires_at) WHERE retention_expires_at IS NOT NULL;
CREATE INDEX idx_memory_metadata_accessed ON memory_metadata(last_accessed_at DESC);
CREATE INDEX idx_consolidation_kind ON consolidation_runs(kind, started_at DESC);
```

---

## 4. Credential Manager Database (Windows Credential Manager)

Not a local database - uses Windows Credential Manager (DPAPI). But we track metadata locally:

```sql
-- Local metadata for credential management
CREATE TABLE credential_metadata (
    category TEXT NOT NULL,                      -- api_keys, grants, oauth_tokens, etc.
    key TEXT NOT NULL,                           -- Key within category
    target_name TEXT NOT NULL UNIQUE,            -- Full CM target name
    description TEXT,
    created_at TEXT NOT NULL,                    -- ISO 8601 UTC
    updated_at TEXT NOT NULL,                    -- ISO 8601 UTC
    expires_at TEXT,                             -- ISO 8601 UTC
    rotation_required INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (category, key)
);

CREATE INDEX idx_cred_meta_category ON credential_metadata(category);
CREATE INDEX idx_cred_meta_expires ON credential_metadata(expires_at) WHERE expires_at IS NOT NULL;
```

---

## 5. Agent Registry Database (`data/agents/registry.db`)

```sql
-- Registered agents
CREATE TABLE agents (
    agent_id TEXT PRIMARY KEY,                   -- UUID v4
    name TEXT NOT NULL UNIQUE,
    type TEXT NOT NULL,                          -- research, coding, browser, etc.
    description TEXT,
    version TEXT NOT NULL,
    module_path TEXT NOT NULL,                   -- Python import path
    class_name TEXT NOT NULL,
    capabilities_json TEXT NOT NULL,             -- JSON array of AgentCapability
    config_json TEXT NOT NULL DEFAULT '{}',      -- Agent-specific config
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Agent health tracking
CREATE TABLE agent_health (
    agent_id TEXT PRIMARY KEY REFERENCES agents(agent_id) ON DELETE CASCADE,
    status TEXT NOT NULL,                        -- healthy, degraded, unhealthy, unknown
    last_heartbeat TEXT,                         -- ISO 8601 UTC
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    total_executions INTEGER NOT NULL DEFAULT 0,
    successful_executions INTEGER NOT NULL DEFAULT 0,
    avg_execution_time_ms REAL,
    last_error TEXT,
    last_error_at TEXT,
    cpu_percent REAL,
    memory_mb REAL,
    updated_at TEXT NOT NULL
);

-- Agent execution history
CREATE TABLE agent_executions (
    execution_id TEXT PRIMARY KEY,               -- UUID v4
    agent_id TEXT NOT NULL REFERENCES agents(agent_id),
    task_id TEXT,                                -- Parent task
    delegation_id TEXT,                          -- From coordinator
    objective TEXT NOT NULL,
    status TEXT NOT NULL,                        -- completed, failed, cancelled
    started_at TEXT NOT NULL,
    completed_at TEXT,
    execution_time_ms INTEGER,
    result_json TEXT,
    error TEXT,
    evidence_count INTEGER NOT NULL DEFAULT 0,
    verification_status TEXT,                    -- verified, failed, pending
    verification_issues_json TEXT
);

-- Indexes
CREATE INDEX idx_agents_type ON agents(type);
CREATE INDEX idx_agents_enabled ON agents(enabled) WHERE enabled = 1;
CREATE INDEX idx_health_status ON agent_health(status);
CREATE INDEX idx_executions_agent ON agent_executions(agent_id, started_at DESC);
CREATE INDEX idx_executions_task ON agent_executions(task_id);
```

---

## 6. Voice Pipeline Database (`data/voice/sessions.db`)

```sql
-- Voice sessions
CREATE TABLE voice_sessions (
    session_id TEXT PRIMARY KEY,                 -- UUID v4
    user_id TEXT NOT NULL DEFAULT 'local_user',
    privacy_mode TEXT NOT NULL,                  -- standard, private, local_only, offline
    language TEXT NOT NULL DEFAULT 'en',         -- en, te, auto
    wake_word_used TEXT,                         -- Which keyword triggered
    started_at TEXT NOT NULL,                    -- ISO 8601 UTC
    ended_at TEXT,                               -- ISO 8601 UTC
    expires_at TEXT,                             -- ISO 8601 UTC (30 min token)
    total_interactions INTEGER NOT NULL DEFAULT 0,
    total_audio_duration_ms INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,                        -- active, expired, ended, error
    error TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

-- Voice interactions (per command)
CREATE TABLE voice_interactions (
    interaction_id TEXT PRIMARY KEY,             -- UUID v4
    session_id TEXT NOT NULL REFERENCES voice_sessions(session_id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,                   -- Order in session
    wake_word_confidence REAL,
    asr_transcript TEXT,
    asr_confidence REAL,
    asr_language TEXT,
    asr_duration_ms INTEGER,
    intent_type TEXT,
    intent_confidence REAL,
    intent_entities_json TEXT,
    intent_duration_ms INTEGER,
    risk_level TEXT,
    task_id TEXT,                                -- Created task
    tts_provider TEXT,
    tts_duration_ms INTEGER,
    tts_audio_size_bytes INTEGER,
    barge_in INTEGER NOT NULL DEFAULT 0,         -- 1 if interrupted
    total_duration_ms INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Indexes
CREATE INDEX idx_voice_sessions_user ON voice_sessions(user_id, started_at DESC);
CREATE INDEX idx_voice_interactions_session ON voice_interactions(session_id, sequence);
CREATE INDEX idx_voice_interactions_task ON voice_interactions(task_id);
```

---

## 7. Configuration Database (`data/config/settings.db`)

```sql
-- Application settings with versioning
CREATE TABLE settings (
    key TEXT PRIMARY KEY,                        -- Dot notation: "voice.wake_word.sensitivity"
    value_json TEXT NOT NULL,                    -- JSON value
    value_type TEXT NOT NULL,                    -- string, number, boolean, object, array
    description TEXT,
    category TEXT NOT NULL,                      -- app, security, policy, model_router, voice, memory, performance
    is_sensitive INTEGER NOT NULL DEFAULT 0,     -- 1=contains secrets, redacted in exports
    is_runtime_mutable INTEGER NOT NULL DEFAULT 1, -- 1=can change without restart
    validation_json TEXT,                        -- JSON Schema for validation
    default_value_json TEXT,                     -- Default value
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    updated_by TEXT                              -- user, system, migration
);

-- Settings history for rollback
CREATE TABLE settings_history (
    history_id TEXT PRIMARY KEY,                 -- UUID v4
    key TEXT NOT NULL,
    old_value_json TEXT,
    new_value_json TEXT,
    changed_at TEXT NOT NULL,
    changed_by TEXT,
    reason TEXT
);

-- Indexes
CREATE INDEX idx_settings_category ON settings(category);
CREATE INDEX idx_settings_sensitive ON settings(is_sensitive) WHERE is_sensitive = 1;
```

---

## 8. Evidence Store (`data/evidence/evidence.db`)

```sql
-- Evidence records for audit and debugging
CREATE TABLE evidence (
    evidence_id TEXT PRIMARY KEY,                -- UUID v4
    task_id TEXT,                                -- Related task
    agent_id TEXT,                               -- Related agent
    interaction_id TEXT,                         -- Related voice interaction
    type TEXT NOT NULL,                          -- screenshot, log, network_trace, file_diff, clipboard, ui_tree
    description TEXT,
    file_path TEXT NOT NULL,                     -- Relative to evidence root
    file_size_bytes INTEGER NOT NULL,
    mime_type TEXT,                              -- image/png, text/plain, application/json
    checksum_sha256 TEXT NOT NULL,               -- For integrity
    metadata_json TEXT NOT NULL DEFAULT '{}',    -- Coordinates, selectors, URLs, etc.
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Evidence chains (for multi-step operations)
CREATE TABLE evidence_chains (
    chain_id TEXT PRIMARY KEY,                   -- UUID v4
    task_id TEXT NOT NULL,
    name TEXT,                                   -- Human-readable name
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE evidence_chain_links (
    chain_id TEXT NOT NULL REFERENCES evidence_chains(chain_id) ON DELETE CASCADE,
    evidence_id TEXT NOT NULL REFERENCES evidence(evidence_id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    PRIMARY KEY (chain_id, sequence)
);

-- Indexes
CREATE INDEX idx_evidence_task ON evidence(task_id);
CREATE INDEX idx_evidence_agent ON evidence(agent_id);
CREATE INDEX idx_evidence_type ON evidence(type);
CREATE INDEX idx_evidence_created ON evidence(created_at DESC);
CREATE INDEX idx_evidence_chain_task ON evidence_chains(task_id);
```

---

## 9. Migration System

```sql
-- Schema version tracking
CREATE TABLE schema_migrations (
    migration_id TEXT PRIMARY KEY,               -- e.g., "001_initial_schema"
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL DEFAULT (datetime('now')),
    checksum TEXT NOT NULL,                      -- SHA256 of migration SQL
    execution_time_ms INTEGER,
    success INTEGER NOT NULL DEFAULT 1,
    error TEXT
);

-- Example migration
-- 001_initial_schema.sql
-- 002_add_task_checkpoints.sql
-- 003_add_audit_hash_chain.sql
-- 004_add_memory_fts.sql
-- 005_add_agent_registry.sql
-- 006_add_voice_sessions.sql
-- 007_add_evidence_store.sql
-- 008_add_settings_history.sql
```

---

## 10. Connection Configuration

```python
# SQLite connection settings for all databases
SQLITE_PRAGMAS = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA cache_size = -32768;           -- 32MB cache
PRAGMA temp_store = MEMORY;
PRAGMA mmap_size = 268435456;         -- 256MB mmap
PRAGMA page_size = 4096;
PRAGMA busy_timeout = 5000;           -- 5 second busy timeout
PRAGMA foreign_keys = ON;
PRAGMA recursive_triggers = ON;
"""

# Connection pool per database
CONNECTION_POOLS = {
    "tasks": {"min": 3, "max": 10},
    "audit": {"min": 2, "max": 5},
    "memory_fts": {"min": 3, "max": 8},
    "agents": {"min": 2, "max": 5},
    "voice": {"min": 1, "max": 3},
    "config": {"min": 1, "max": 3},
    "evidence": {"min": 2, "max": 5},
}
```

---

## 11. Backup & Recovery

```sql
-- Backup procedure (run via SQLite .backup command)
-- .backup 'backups/tasks_20260115.db'

-- Point-in-time recovery via WAL
-- 1. Copy tasks.db and tasks.db-wal
-- 2. Open copy, verify integrity
-- 3. Restore from checkpoint

-- Automated backup schedule (via scheduler)
-- Daily: Full backup at 03:00
-- Hourly: WAL checkpoint
-- Weekly: Verify integrity + test restore
```

---

## 12. Performance Tuning

### 12.1 Analyze & Vacuum Schedule

```sql
-- Run weekly via scheduler
ANALYZE;                    -- Update query planner stats
VACUUM;                     -- Reclaim space (run during low usage)

-- For WAL databases, use:
PRAGMA wal_checkpoint(TRUNCATE);  -- Checkpoint and truncate WAL
```

### 12.2 Query Plans

```sql
-- Example: Task lookup with checkpoint
EXPLAIN QUERY PLAN
SELECT t.*, c.context_json as checkpoint_context
FROM tasks t
LEFT JOIN task_checkpoints c ON t.task_id = c.task_id AND c.is_latest = 1
WHERE t.task_id = ?;

-- Should use: SEARCH tasks USING PRIMARY KEY (task_id=?)
--            SEARCH task_checkpoints USING INDEX idx_checkpoints_latest (task_id=? AND is_latest=?)
```

---

*All schemas use SQLite with WAL mode for durability. Migrations are versioned and idempotent.*