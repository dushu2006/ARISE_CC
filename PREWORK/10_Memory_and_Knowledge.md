# ARISE — Memory & Knowledge System

## Overview

This document specifies the complete memory architecture for ARISE, implementing five distinct memory kinds with governance, consolidation, and retrieval optimized for autonomous agent operation. The system follows cognitive architecture principles adapted for AI agents.

---

## 1. Memory Architecture Principles

| Principle | Implementation |
|-----------|----------------|
| **Five Kinds** | Semantic, Episodic, Procedural, Preference, Working — each with distinct retention, retrieval, and consolidation rules |
| **Governance First** | Every memory operation checked against privacy, scope, and retention policies |
| **Automatic Consolidation** | Background processes promote, summarize, and reinforce memories without user intervention |
| **Explicit User Control** | Users can inspect, correct, delete, and export any memory at any time |
| **Cross-Kind Retrieval** | Unified query interface retrieves relevant memories from all kinds simultaneously |
| **Evidence-Linked** | Memories reference evidence records for verifiability |
| **Conflict Resolution** | Automated + user-guided resolution for contradictory memories |

---

## 2. Five Kinds of Memory

### 2.1 Semantic Memory (Facts & Knowledge)

```python
@dataclass
class SemanticMemory(MemoryRecord):
    """Permanent knowledge: facts, concepts, definitions, relationships"""
    kind: MemoryKind = MemoryKind.SEMANTIC
    
    # Semantic-specific
    subject: str = ""                    # Entity/concept this fact is about
    predicate: str = ""                  # Relationship type
    object: str = ""                     # Value/related entity
    confidence: float = 1.0              # 0-1, source reliability
    source_episode_id: Optional[str] = None  # If promoted from episodic
    contradictions: List[str] = field(default_factory=list)  # Conflicting fact IDs

# Examples:
# - "Python is a programming language" (subject=Python, predicate=is_a, object=programming language)
# - "ARISE uses Gemini 3.8 Live for voice" (subject=ARISE, predicate=uses, object=Gemini 3.8 Live)
# - "User prefers dark mode" (subject=User, predicate=prefers, object=dark_mode)
```

**Characteristics:**
- **Retention:** Permanent (until explicitly deleted or contradicted)
- **Retrieval:** Vector similarity + keyword (ChromaDB)
- **Consolidation:** Promoted from episodic, reinforced by usage
- **Conflict Handling:** Multiple values allowed, confidence-weighted retrieval

### 2.2 Episodic Memory (Experiences & Events)

```python
@dataclass
class EpisodicMemory(MemoryRecord):
    """Time-bound experiences: interactions, task executions, observations"""
    kind: MemoryKind = MemoryKind.EPISODIC
    
    # Episodic-specific
    episode_timestamp: datetime          # When the experience occurred
    duration_seconds: Optional[float] = None
    participants: List[str] = field(default_factory=list)  # Agents, users, systems
    location: Optional[str] = None       # App, window, URL, file path
    actions: List[str] = field(default_factory=list)       # What happened
    outcome: Optional[str] = None        # Success/failure/partial
    emotional_valence: float = 0.0       # -1 to 1 (for future affective computing)
    summarized: bool = False             # Whether promoted to semantic
    source_task_id: Optional[str] = None

# Examples:
# - "User asked to open Chrome at 2026-11-10 08:30:00, succeeded"
# - "Research agent found 15 sources for JWT best practices"
# - "Coding agent refactored auth module, tests passed"
```

**Characteristics:**
- **Retention:** Time-decay (configurable, default 1 year), then archival
- **Retrieval:** Temporal + vector similarity
- **Consolidation:** Summarized to semantic after 30 days (high importance)
- **Indexing:** By timestamp, task_id, participants, outcome

### 2.3 Procedural Memory (Skills & Workflows)

```python
@dataclass
class ProceduralMemory(MemoryRecord):
    """How-to knowledge: skills, workflows, procedures, patterns"""
    kind: MemoryKind = MemoryKind.PROCEDURAL
    
    # Procedural-specific
    procedure_name: str                  # Human-readable name
    procedure_steps: List[str]           # Ordered steps
    preconditions: List[str] = field(default_factory=list)
    postconditions: List[str] = field(default_factory=list)
    success_count: int = 0               # Successful executions
    failure_count: int = 0               # Failed executions
    last_executed: Optional[datetime] = None
    average_duration_seconds: float = 0.0
    tags: List[str] = field(default_factory=list)  # e.g., ["coding", "refactor", "jwt"]
    version: int = 1                     # Incremented on modification

# Examples:
# - "How to authenticate with JWT in FastAPI"
# - "Steps to create a Playwright trace for evidence"
# - "Procedure for cross-source verification in research"
```

**Characteristics:**
- **Retention:** Permanent, reinforced by successful use
- **Retrieval:** Vector similarity on procedure_name + tags + steps
- **Consolidation:** Success reinforces (importance++), failure weakens
- **Versioning:** Explicit version control for procedure evolution

### 2.4 Preference Memory (User Preferences & Corrections)

```python
@dataclass
class PreferenceMemory(MemoryRecord):
    """User preferences, corrections, and personalized settings"""
    kind: MemoryKind = MemoryKind.PREFERENCE
    
    # Preference-specific
    preference_key: str                  # e.g., "theme", "voice_speed", "default_browser"
    preference_value: Any                # The actual preference
    preference_type: str = "explicit"    # "explicit" | "inferred" | "correction"
    scope: str = "global"                # "global" | "app" | "task" | "domain"
    context_pattern: Optional[str] = None  # When this applies
    supersedes: List[str] = field(default_factory=list)  # Previous preference IDs
    user_confirmed: bool = False         # Explicitly confirmed by user

# Examples:
# - {"key": "theme", "value": "dark", "type": "explicit", "scope": "global"}
# - {"key": "voice_speed", "value": 1.2, "type": "inferred", "scope": "global"}
# - {"key": "default_browser", "value": "firefox", "type": "correction", "scope": "global"}
# - {"key": "code_style", "value": "black", "type": "explicit", "scope": "app:vscode"}
```

**Characteristics:**
- **Retention:** Permanent until superseded or explicitly deleted
- **Retrieval:** Exact key match + scope filtering (fast, SQLite FTS5)
- **Consolidation:** Conflict resolution (explicit > inferred > default)
- **Priority:** Explicit user settings always win

### 2.5 Working Memory (Transient Task Context)

```python
@dataclass
class WorkingMemory(MemoryRecord):
    """Short-term context for active task execution"""
    kind: MemoryKind = MemoryKind.WORKING
    
    # Working-specific
    task_id: str                         # Associated task
    step_index: int = 0                  # Current plan step
    variables: Dict[str, Any] = field(default_factory=dict)
    intermediate_results: List[Any] = field(default_factory=list)
    active_goals: List[str] = field(default_factory=list)
    attention_focus: Optional[str] = None  # Current focus entity
    expires_at: datetime                 # TTL (default 24 hours)

# Examples:
# - Current task variables: {"target_url": "github.com", "browser": "chrome"}
# - Intermediate research findings not yet verified
# - Code snippets being assembled during coding task
```

**Characteristics:**
- **Retention:** TTL-based (default 24 hours), auto-cleanup
- **Retrieval:** Exact task_id match (fast, SQLite)
- **Consolidation:** Important items promoted to episodic
- **Isolation:** Per-task, not shared across tasks

---

## 3. Storage Backends

### 3.1 ChromaDB (Vector Memory Kinds)

```python
class ChromaMemoryStore:
    """ChromaDB-backed store for Semantic, Episodic, Procedural, Preference"""
    
    COLLECTIONS = {
        MemoryKind.SEMANTIC: "arise_semantic",
        MemoryKind.EPISODIC: "arise_episodic",
        MemoryKind.PROCEDURAL: "arise_procedural",
        MemoryKind.PREFERENCE: "arise_preference",
    }
    
    def __init__(self, client: chromadb.Client, kind: MemoryKind):
        self.client = client
        self.kind = kind
        self.collection = client.get_or_create_collection(
            name=self.COLLECTIONS[kind],
            metadata={"hnsw:space": "cosine", "schema_version": "1"},
        )
    
    async def add(self, record: MemoryRecord):
        # Prepare metadata (ChromaDB requires flat metadata)
        metadata = self._flatten_metadata(record)
        
        self.collection.add(
            ids=[record.id],
            documents=[record.content],
            embeddings=[record.embedding] if record.embedding else None,
            metadatas=[metadata],
        )
    
    async def search(
        self,
        query_embedding: List[float],
        limit: int = 10,
        filters: Dict[str, Any] = None,
        min_similarity: float = 0.7,
    ) -> List[MemoryRecord]:
        where = self._build_where(filters)
        
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=limit,
            where=where,
            include=["documents", "embeddings", "metadatas", "distances"],
        )
        
        records = []
        for i, doc_id in enumerate(results["ids"][0]):
            distance = results["distances"][0][i]
            similarity = 1 - distance
            if similarity >= min_similarity:
                records.append(self._deserialize(
                    doc_id, results["documents"][0][i], 
                    results["metadatas"][0][i], 
                    results["embeddings"][0][i] if results["embeddings"] else None
                ))
        return records
    
    def _flatten_metadata(self, record: MemoryRecord) -> Dict[str, Any]:
        """Flatten nested metadata for ChromaDB"""
        meta = {
            "kind": record.kind.value,
            "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
            "access_count": record.access_count,
            "importance": record.importance,
            "source": record.source,
            "tags": json.dumps(record.tags),
        }
        
        # Add kind-specific fields
        if record.kind == MemoryKind.EPISODIC:
            meta["episode_timestamp"] = record.episode_timestamp.isoformat() if record.episode_timestamp else ""
            meta["duration_seconds"] = record.duration_seconds or 0
            meta["participants"] = json.dumps(record.participants)
            meta["outcome"] = record.outcome or ""
            meta["summarized"] = record.summarized
            meta["source_task_id"] = record.source_task_id or ""
        
        elif record.kind == MemoryKind.PROCEDURAL:
            meta["procedure_name"] = record.procedure_name
            meta["procedure_steps"] = json.dumps(record.procedure_steps)
            meta["preconditions"] = json.dumps(record.preconditions)
            meta["postconditions"] = json.dumps(record.postconditions)
            meta["success_count"] = record.success_count
            meta["failure_count"] = record.failure_count
            meta["version"] = record.version
        
        elif record.kind == MemoryKind.PREFERENCE:
            meta["preference_key"] = record.preference_key
            meta["preference_value"] = json.dumps(record.preference_value)
            meta["preference_type"] = record.preference_type
            meta["scope"] = record.scope
            meta["user_confirmed"] = record.user_confirmed
        
        elif record.kind == MemoryKind.SEMANTIC:
            meta["subject"] = record.subject
            meta["predicate"] = record.predicate
            meta["object"] = record.object
            meta["confidence"] = record.confidence
            meta["source_episode_id"] = record.source_episode_id or ""
        
        # Add custom metadata
        for k, v in record.metadata.items():
            meta[f"meta_{k}"] = json.dumps(v) if not isinstance(v, (str, int, float, bool)) else v
        
        return meta
```

### 3.2 SQLite FTS5 (Working Memory + Preference Index)

```python
class SQLiteWorkingStore:
    """SQLite FTS5 for working memory (fast exact match) and preference lookup"""
    
    def __init__(self, pool: sqlite3.Connection):
        self.pool = pool
        self._init_schema()
    
    def _init_schema(self):
        with self.pool:
            # Working memory table
            self.pool.execute("""
                CREATE TABLE IF NOT EXISTS working_memory (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    step_index INTEGER DEFAULT 0
                )
            """)
            self.pool.execute("""
                CREATE INDEX IF NOT EXISTS idx_working_task 
                ON working_memory(task_id, created_at DESC)
            """)
            self.pool.execute("""
                CREATE INDEX IF NOT EXISTS idx_working_expires 
                ON working_memory(expires_at)
            """)
            
            # Preference FTS5 index for fast key lookup
            self.pool.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS preference_fts 
                USING fts5(
                    preference_key, preference_value, scope, 
                    content='preferences', content_rowid='rowid'
                )
            """)
            
            # Preferences table
            self.pool.execute("""
                CREATE TABLE IF NOT EXISTS preferences (
                    id TEXT PRIMARY KEY,
                    preference_key TEXT NOT NULL,
                    preference_value TEXT NOT NULL,
                    preference_type TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    context_pattern TEXT,
                    user_confirmed INTEGER DEFAULT 0,
                    supersedes TEXT,  -- JSON array
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            self.pool.execute("""
                CREATE INDEX IF NOT EXISTS idx_pref_key_scope 
                ON preferences(preference_key, scope)
            """)
```

---

## 4. Memory Operations API

### 4.1 Core Operations

```python
class MemorySystem:
    """Unified memory interface"""
    
    def __init__(self, runtime: "AppRuntime"):
        self.runtime = runtime
        self.stores: Dict[MemoryKind, MemoryStore] = {}
        self._init_stores()
    
    # ===== STORE =====
    
    async def remember(
        self,
        kind: MemoryKind,
        content: str,
        *,
        importance: float = 1.0,
        source: str = "auto",
        tags: List[str] = None,
        embedding: List[float] = None,
        **kind_specific,
    ) -> MemoryRecord:
        """Store a new memory"""
        store = self.stores[kind]
        
        # Generate embedding if not provided
        if embedding is None:
            embedding = await self._embed(content)
        
        record = MemoryRecord(
            id=f"mem_{uuid4().hex[:12]}",
            kind=kind,
            content=content,
            embedding=embedding,
            importance=importance,
            source=source,
            tags=tags or [],
            **kind_specific,
        )
        
        await store.add(record)
        
        # Link to current task if any
        current_task = self.runtime.task_engine.get_current_task()
        if current_task:
            current_task.context.evidence_refs.append(record.id)
        
        return record
    
    # Convenience methods per kind
    async def remember_fact(self, content: str, subject: str, predicate: str, obj: str, **kwargs) -> SemanticMemory:
        return await self.remember(MemoryKind.SEMANTIC, content, subject=subject, predicate=predicate, object=obj, **kwargs)
    
    async def remember_episode(self, content: str, episode_timestamp: datetime, **kwargs) -> EpisodicMemory:
        return await self.remember(MemoryKind.EPISODIC, content, episode_timestamp=episode_timestamp, **kwargs)
    
    async def remember_procedure(self, name: str, steps: List[str], **kwargs) -> ProceduralMemory:
        content = f"{name}: " + " → ".join(steps)
        return await self.remember(MemoryKind.PROCEDURAL, content, procedure_name=name, procedure_steps=steps, **kwargs)
    
    async def remember_preference(self, key: str, value: Any, type: str = "explicit", **kwargs) -> PreferenceMemory:
        content = f"{key} = {value}"
        return await self.remember(MemoryKind.PREFERENCE, content, preference_key=key, preference_value=value, preference_type=type, **kwargs)
    
    async def remember_working(self, task_id: str, content: str, **kwargs) -> WorkingMemory:
        return await self.remember(MemoryKind.WORKING, content, task_id=task_id, expires_at=datetime.utcnow() + timedelta(hours=24), **kwargs)
    
    # ===== RETRIEVE =====
    
    async def recall(
        self,
        kind: MemoryKind,
        query: str,
        limit: int = 10,
        filters: Dict[str, Any] = None,
        min_similarity: float = 0.7,
    ) -> List[MemoryRecord]:
        """Retrieve memories by semantic similarity"""
        store = self.stores[kind]
        query_embedding = await self._embed(query)
        return await store.search(query_embedding, limit, filters, min_similarity)
    
    async def recall_for_context(
        self,
        context: str,
        kinds: List[MemoryKind] = None,
        limit_per_kind: int = 5,
    ) -> Dict[MemoryKind, List[MemoryRecord]]:
        """Unified recall across multiple kinds"""
        kinds = kinds or list(MemoryKind)
        
        # Parallel retrieval
        tasks = [self.recall(kind, context, limit_per_kind) for kind in kinds]
        results = await asyncio.gather(*tasks)
        
        # Re-rank by relevance to context
        combined = {}
        for kind, records in zip(kinds, results):
            for record in records:
                record.relevance_score = self._score_relevance(record, context)
            records.sort(key=lambda r: r.relevance_score, reverse=True)
            combined[kind] = records
        
        return combined
    
    async def get_preference(self, key: str, scope: str = "global") -> Optional[Any]:
        """Fast preference lookup (exact match)"""
        store = self.stores[MemoryKind.PREFERENCE]
        if isinstance(store, SQLiteWorkingStore):
            row = store.pool.execute("""
                SELECT preference_value, preference_type, user_confirmed
                FROM preferences
                WHERE preference_key = ? AND scope = ?
                ORDER BY 
                    CASE preference_type WHEN 'explicit' THEN 0 WHEN 'correction' THEN 1 ELSE 2 END,
                    user_confirmed DESC,
                    updated_at DESC
                LIMIT 1
            """, (key, scope)).fetchone()
            if row:
                return json.loads(row[0])
        return None
    
    async def get_working_context(self, task_id: str) -> List[WorkingMemory]:
        """Get all working memory for a task"""
        store = self.stores[MemoryKind.WORKING]
        if isinstance(store, SQLiteWorkingStore):
            rows = store.pool.execute("""
                SELECT * FROM working_memory WHERE task_id = ? ORDER BY created_at
            """, (task_id,)).fetchall()
            return [self._deserialize_working(row) for row in rows]
        return []
    
    # ===== UPDATE =====
    
    async def reinforce(self, memory_id: str, success: bool = True):
        """Reinforce or weaken a memory based on outcome"""
        # Find which store contains this memory
        for kind, store in self.stores.items():
            record = await store.get(memory_id)
            if record:
                if success:
                    record.importance = min(1.0, record.importance + 0.1)
                    if record.kind == MemoryKind.PROCEDURAL:
                        record.success_count += 1
                else:
                    record.importance = max(0.1, record.importance - 0.2)
                    if record.kind == MemoryKind.PROCEDURAL:
                        record.failure_count += 1
                
                record.updated_at = datetime.utcnow()
                await store.update(record)
                return
        
        raise ValueError(f"Memory not found: {memory_id}")
    
    async def supersede_preference(self, key: str, new_value: Any, scope: str = "global", reason: str = ""):
        """Replace a preference with new value"""
        old = await self.get_preference(key, scope)
        if old is not None:
            # Archive old preference
            await self.remember(MemoryKind.PREFERENCE, 
                f"[SUPERSEDED] {key} = {old}",
                preference_key=key,
                preference_value=old,
                preference_type="archived",
                scope=scope,
                metadata={"superseded_by": "new_value", "reason": reason},
            )
        
        # Store new preference
        return await self.remember_preference(key, new_value, type="explicit", scope=scope)
    
    # ===== DELETE =====
    
    async def forget(self, memory_id: str, confirmation: str = None):
        """Delete a specific memory (requires confirmation for safety)"""
        if confirmation and confirmation != "FORGET":
            raise ValueError("Confirmation required: pass confirmation='FORGET'")
        
        for store in self.stores.values():
            if await store.exists(memory_id):
                await store.delete(memory_id)
                return
        
        raise ValueError(f"Memory not found: {memory_id}")
    
    async def forget_all(self, confirmation: str):
        """Nuclear option: delete ALL memories"""
        if confirmation != "DELETE ALL MEMORIES":
            raise ValueError("Confirmation phrase mismatch")
        
        for kind, store in self.stores.items():
            await store.delete_all()
        
        # Also clear ChromaDB collections
        await self.runtime.chroma_client.reset()
        
        logger.warning("ALL MEMORIES DELETED by user request")
```

---

## 5. Consolidation Pipeline

### 5.1 Scheduled Consolidation (Every 6 Hours)

```python
class MemoryConsolidator:
    """Background consolidation processes"""
    
    def __init__(self, memory_system: MemorySystem, scheduler: "Scheduler"):
        self.memory = memory_system
        self.scheduler = scheduler
        self.scheduler.add_cron_job("0 */6 * * *", self.consolidate_all)
    
    async def consolidate_all(self):
        """Run all consolidation steps"""
        stats = ConsolidationStats()
        
        # 1. Working → Episodic Promotion
        stats.promoted = await self._promote_working_to_episodic()
        
        # 2. Episodic Summarization → Semantic
        stats.summarized = await self._summarize_episodic()
        
        # 3. Procedural Reinforcement
        stats.reinforced, stats.weakened = await self._reinforce_procedural()
        
        # 4. Preference Conflict Resolution
        stats.resolved = await self._resolve_preference_conflicts()
        
        # 5. Cleanup Expired
        stats.cleaned = await self._cleanup_expired()
        
        # 6. Deduplication
        stats.deduplicated = await self._deduplicate_semantic()
        
        # Emit event
        await self.memory.runtime.events.emit("memory.consolidated", stats.to_dict())
        
        return stats
    
    async def _promote_working_to_episodic(self) -> int:
        """Promote important working memories to episodic"""
        working_store = self.memory.stores[MemoryKind.WORKING]
        episodic_store = self.memory.stores[MemoryKind.EPISODIC]
        
        # Find candidates: high importance, explicit source, >1 hour old
        candidates = await working_store.search_by_criteria(
            importance_min=0.7,
            source_in=["explicit", "correction"],
            older_than=timedelta(hours=1),
            not_promoted=True,
        )
        
        promoted = 0
        for record in candidates:
            # Create episodic version
            episodic = EpisodicMemory(
                id=f"mem_{uuid4().hex[:12]}",
                content=record.content,
                embedding=record.embedding,
                metadata={**record.metadata, "promoted_from": record.id},
                importance=record.importance,
                source=record.source,
                episode_timestamp=record.created_at,
            )
            await episodic_store.add(episodic)
            
            # Mark working as promoted
            record.metadata["promoted"] = True
            record.updated_at = datetime.utcnow()
            await working_store.update(record)
            promoted += 1
        
        return promoted
    
    async def _summarize_episodic(self) -> int:
        """Convert old episodic memories to semantic facts"""
        episodic_store = self.memory.stores[MemoryKind.EPISODIC]
        semantic_store = self.memory.stores[MemoryKind.SEMANTIC]
        
        # Find episodes: high importance, >30 days old, not summarized
        old_episodes = await episodic_store.search_by_criteria(
            importance_min=0.8,
            older_than=timedelta(days=30),
            not_summarized=True,
        )
        
        summarized = 0
        for episode in old_episodes:
            # Extract semantic facts using LLM
            facts = await self._extract_facts(episode.content)
            
            for fact in facts:
                semantic = SemanticMemory(
                    id=f"mem_{uuid4().hex[:12]}",
                    content=fact,
                    embedding=await self.memory._embed(fact),
                    metadata={"source_episode": episode.id},
                    importance=0.9,
                    source="consolidation",
                    subject=self._extract_subject(fact),
                    predicate=self._extract_predicate(fact),
                    object=self._extract_object(fact),
                )
                await semantic_store.add(semantic)
            
            # Mark as summarized
            episode.summarized = True
            episode.updated_at = datetime.utcnow()
            await episodic_store.update(episode)
            summarized += 1
        
        return summarized
    
    async def _extract_facts(self, episode_content: str) -> List[str]:
        """Use LLM to extract discrete facts from episode"""
        prompt = f"""
        Extract 1-5 discrete, verifiable facts from this experience.
        Each fact should be a single sentence, self-contained.
        Focus on: decisions made, outcomes, learned information, user preferences.
        
        Experience: {episode_content}
        
        Return JSON array of strings.
        """
        response = await self.memory.runtime.model_router.complete(
            "complex_reasoning",
            CompletionRequest(messages=[{"role": "user", "content": prompt}]),
        )
        return json.loads(response.content)
    
    async def _reinforce_procedural(self) -> Tuple[int, int]:
        """Reinforce successful procedures, weaken failed ones"""
        procedural_store = self.memory.stores[MemoryKind.PROCEDURAL]
        
        # Reinforce: success_count >= 3, failure_count = 0
        successful = await procedural_store.search_by_criteria(
            success_count_min=3,
            failure_count=0,
        )
        
        reinforced = 0
        for proc in successful:
            proc.importance = min(1.0, proc.importance + 0.1)
            proc.updated_at = datetime.utcnow()
            await procedural_store.update(proc)
            reinforced += 1
        
        # Weaken: failure_count > 0
        failed = await procedural_store.search_by_criteria(
            failure_count_min=1,
        )
        
        weakened = 0
        for proc in failed:
            proc.importance = max(0.1, proc.importance - 0.2)
            proc.updated_at = datetime.utcnow()
            await procedural_store.update(proc)
            weakened += 1
            
            # If critically weak, flag for review
            if proc.importance < 0.3:
                await self.memory.runtime.events.emit("procedure.needs_review", {
                    "procedure_id": proc.id,
                    "name": proc.procedure_name,
                    "failure_count": proc.failure_count,
                })
        
        return reinforced, weakened
    
    async def _resolve_preference_conflicts(self) -> int:
        """Resolve conflicting preferences for same key"""
        pref_store = self.memory.stores[MemoryKind.PREFERENCE]
        
        # Find keys with multiple active preferences
        conflicts = await pref_store.find_conflicts()
        
        resolved = 0
        for key, prefs in conflicts.items():
            # Resolution priority: explicit > correction > inferred, recent > old, confirmed
            prefs.sort(key=lambda p: (
                0 if p.preference_type == "explicit" else (1 if p.preference_type == "correction" else 2),
                not p.user_confirmed,
                -p.updated_at.timestamp(),
            ))
            
            winner = prefs[0]
            losers = prefs[1:]
            
            for loser in losers:
                # Archive loser
                loser.preference_type = "archived"
                loser.metadata["superseded_by"] = winner.id
                loser.metadata["resolution_reason"] = self._resolution_reason(winner, loser)
                loser.updated_at = datetime.utcnow()
                await pref_store.update(loser)
                resolved += 1
        
        return resolved
    
    def _resolution_reason(self, winner: PreferenceMemory, loser: PreferenceMemory) -> str:
        if winner.preference_type != loser.preference_type:
            return f"Type priority: {winner.preference_type} > {loser.preference_type}"
        if winner.user_confirmed != loser.user_confirmed:
            return "User confirmed preference wins"
        return f"More recent: {winner.updated_at} > {loser.updated_at}"
    
    async def _cleanup_expired(self) -> int:
        """Delete expired working memories"""
        working_store = self.memory.stores[MemoryKind.WORKING]
        expired = await working_store.search_by_criteria(expired=True)
        
        for record in expired:
            await working_store.delete(record.id)
        
        return len(expired)
    
    async def _deduplicate_semantic(self) -> int:
        """Find and merge near-duplicate semantic facts"""
        semantic_store = self.memory.stores[MemoryKind.SEMANTIC]
        
        # This is expensive - sample-based approach
        all_facts = await semantic_store.search_by_criteria(limit=1000)
        
        deduplicated = 0
        # Simple approach: exact content match
        seen = {}
        for fact in all_facts:
            normalized = fact.content.lower().strip()
            if normalized in seen:
                # Merge: keep higher importance, combine metadata
                existing = seen[normalized]
                if fact.importance > existing.importance:
                    existing.importance = fact.importance
                    existing.metadata["merged_from"] = existing.metadata.get("merged_from", []) + [fact.id]
                    await semantic_store.update(existing)
                await semantic_store.delete(fact.id)
                deduplicated += 1
            else:
                seen[normalized] = fact
        
        return deduplicated
```

---

## 6. Retrieval Strategies

### 6.1 Query Planning

```python
class RetrievalPlanner:
    """Plans optimal retrieval strategy for a query"""
    
    def __init__(self, memory: MemorySystem):
        self.memory = memory
    
    async def plan_retrieval(self, query: str, context: Dict = None) -> RetrievalPlan:
        """Analyze query and plan multi-kind retrieval"""
        
        # Classify query type
        query_type = await self._classify_query(query)
        
        # Determine which kinds to search
        kinds = self._select_kinds(query_type, context)
        
        # Determine filters per kind
        filters = self._build_filters(query_type, context)
        
        # Determine limits
        limits = self._calculate_limits(query_type)
        
        return RetrievalPlan(
            query=query,
            query_type=query_type,
            kinds=kinds,
            filters=filters,
            limits=limits,
            rerank_strategy=self._select_reranker(query_type),
        )
    
    def _select_kinds(self, query_type: QueryType, context: Dict) -> List[MemoryKind]:
        """Select relevant memory kinds based on query type"""
        mapping = {
            QueryType.FACTUAL: [MemoryKind.SEMANTIC, MemoryKind.EPISODIC],
            QueryType.PROCEDURAL: [MemoryKind.PROCEDURAL, MemoryKind.SEMANTIC],
            QueryType.PREFERENCE: [MemoryKind.PREFERENCE],
            QueryType.CONTEXTUAL: [MemoryKind.WORKING, MemoryKind.EPISODIC],
            QueryType.HISTORICAL: [MemoryKind.EPISODIC, MemoryKind.SEMANTIC],
            QueryType.TROUBLESHOOTING: [MemoryKind.PROCEDURAL, MemoryKind.EPISODIC, MemoryKind.SEMANTIC],
        }
        return mapping.get(query_type, [MemoryKind.SEMANTIC, MemoryKind.EPISODIC])
```

### 6.2 Cross-Kind Re-Ranking

```python
class CrossKindReranker:
    """Re-ranks results from multiple memory kinds"""
    
    def __init__(self, runtime: "AppRuntime"):
        self.runtime = runtime
    
    async def rerank(
        self,
        results: Dict[MemoryKind, List[MemoryRecord]],
        query: str,
        context: Dict = None,
        top_k: int = 10,
    ) -> List[MemoryRecord]:
        """Combine and re-rank results from all kinds"""
        
        # Flatten with kind tags
        all_results = []
        for kind, records in results.items():
            for record in records:
                record.source_kind = kind
                all_results.append(record)
        
        if not all_results:
            return []
        
        # Score each result
        for record in all_results:
            record.final_score = self._calculate_score(record, query, context)
        
        # Sort by final score
        all_results.sort(key=lambda r: r.final_score, reverse=True)
        
        return all_results[:top_k]
    
    def _calculate_score(self, record: MemoryRecord, query: str, context: Dict) -> float:
        """Composite scoring function"""
        scores = {}
        
        # 1. Vector similarity (already computed)
        scores["similarity"] = getattr(record, "similarity", 0.5)
        
        # 2. Importance weight
        scores["importance"] = record.importance
        
        # 3. Recency (for episodic/working)
        if record.kind in [MemoryKind.EPISODIC, MemoryKind.WORKING]:
            age_hours = (datetime.utcnow() - record.created_at).total_seconds() / 3600
            scores["recency"] = max(0, 1 - age_hours / (24 * 30))  # Decay over 30 days
        else:
            scores["recency"] = 0.5
        
        # 4. Access frequency (popularity)
        scores["frequency"] = min(1.0, record.access_count / 10)
        
        # 5. Source reliability
        source_weights = {"explicit": 1.0, "correction": 0.9, "auto": 0.7, "consolidation": 0.8}
        scores["source"] = source_weights.get(record.source, 0.5)
        
        # 6. Context relevance
        if context:
            scores["context"] = self._context_match(record, context)
        else:
            scores["context"] = 0.5
        
        # Weighted combination
        weights = {
            "similarity": 0.35,
            "importance": 0.20,
            "recency": 0.15,
            "frequency": 0.10,
            "source": 0.10,
            "context": 0.10,
        }
        
        return sum(scores[k] * weights[k] for k in weights)
```

---

## 7. Memory Governance & Privacy

### 7.1 Governance Policies

```python
class MemoryGovernance:
    """Enforces memory policies"""
    
    POLICIES = {
        # Retention policies
        "retention": {
            MemoryKind.SEMANTIC: RetentionPolicy(permanent=True),
            MemoryKind.EPISODIC: RetentionPolicy(max_age=timedelta(days=365), archive_after=timedelta(days=90)),
            MemoryKind.PROCEDURAL: RetentionPolicy(permanent=True),
            MemoryKind.PREFERENCE: RetentionPolicy(permanent=True),
            MemoryKind.WORKING: RetentionPolicy(max_age=timedelta(hours=24), hard_delete=True),
        },
        
        # Scope policies
        "scope": {
            "user_data": ["preference", "episodic"],  # User-identifiable
            "system_data": ["semantic", "procedural"],  # Non-identifiable
            "task_data": ["working"],  # Transient
        },
        
        # Access control
        "access": {
            "read": ["user", "assistants"],  # Who can read
            "write": ["user", "assistants", "consolidation"],
            "delete": ["user"],  # Only user can delete
            "export": ["user"],
        },
        
        # Privacy
        "pii_handling": {
            "detect": True,  # Auto-detect PII in memories
            "encrypt": True,  # Encrypt PII-containing memories
            "require_consent": True,  # Require consent for PII storage
        },
    }
    
    async def validate_store(self, record: MemoryRecord) -> ValidationResult:
        """Validate a memory record against policies"""
        errors = []
        warnings = []
        
        # Check retention
        policy = self.POLICIES["retention"][record.kind]
        if policy.max_age and record.created_at:
            if datetime.utcnow() - record.created_at > policy.max_age:
                if policy.hard_delete:
                    errors.append(f"Memory exceeds max age ({policy.max_age})")
                else:
                    warnings.append(f"Memory should be archived (age > {policy.max_age})")
        
        # Check PII
        if self.POLICIES["pii_handling"]["detect"]:
            pii = self._detect_pii(record.content)
            if pii and not record.metadata.get("pii_consent"):
                warnings.append(f"Potential PII detected: {pii}. Consent recommended.")
        
        # Check scope
        if record.kind in self.POLICIES["scope"]["user_data"]:
            if not record.metadata.get("user_consent"):
                warnings.append("User data should have consent flag")
        
        return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)
    
    def _detect_pii(self, content: str) -> List[str]:
        """Detect potential PII in content"""
        pii_patterns = {
            "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
            "phone": r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b",
            "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
            "credit_card": r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b",
            "address": r"\b\d+\s+[A-Za-z\s]+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd)\b",
        }
        
        detected = []
        for pii_type, pattern in pii_patterns.items():
            if re.search(pattern, content):
                detected.append(pii_type)
        
        return detected
```

### 7.2 User Control Interface

```python
class MemoryUserControl:
    """User-facing memory control operations"""
    
    def __init__(self, memory: MemorySystem, governance: MemoryGovernance):
        self.memory = memory
        self.governance = governance
    
    async def inspect_memory(self, memory_id: str) -> MemoryInspection:
        """Full inspection of a memory record"""
        record = await self.memory.get_memory(memory_id)
        if not record:
            raise ValueError(f"Memory not found: {memory_id}")
        
        validation = await self.governance.validate_store(record)
        
        return MemoryInspection(
            record=record,
            validation=validation,
            linked_evidence=await self._get_linked_evidence(record),
            related_memories=await self._find_related(record),
        )
    
    async def correct_memory(self, memory_id: str, corrected_content: str, reason: str):
        """User corrects a memory (creates correction record)"""
        original = await self.memory.get_memory(memory_id)
        if not original:
            raise ValueError(f"Memory not found: {memory_id}")
        
        # Create correction as new memory with higher priority
        correction = await self.memory.remember(
            kind=original.kind,
            content=corrected_content,
            importance=original.importance + 0.1,  # Corrections are more important
            source="correction",
            metadata={
                "corrects": memory_id,
                "original_content": original.content,
                "reason": reason,
            },
        )
        
        # Link original to correction
        original.metadata["corrected_by"] = correction.id
        original.updated_at = datetime.utcnow()
        await self.memory.stores[original.kind].update(original)
        
        return correction
    
    async def export_memories(
        self,
        kinds: List[MemoryKind] = None,
        format: str = "json",
        include_working: bool = False,
    ) -> str:
        """Export memories for backup/portability"""
        kinds = kinds or [k for k in MemoryKind if k != MemoryKind.WORKING or include_working]
        
        export_data = {
            "version": "1.0",
            "exported_at": datetime.utcnow().isoformat(),
            "kinds": {},
        }
        
        for kind in kinds:
            store = self.memory.stores[kind]
            all_records = await store.get_all()
            export_data["kinds"][kind.value] = [r.to_dict() for r in all_records]
        
        if format == "json":
            return json.dumps(export_data, indent=2)
        elif format == "jsonl":
            return "\n".join(json.dumps(r) for kind_data in export_data["kinds"].values() for r in kind_data)
        else:
            raise ValueError(f"Unsupported format: {format}")
    
    async def import_memories(self, data: str, format: str = "json", merge_strategy: str = "upsert"):
        """Import memories from backup"""
        if format == "json":
            export_data = json.loads(data)
        elif format == "jsonl":
            export_data = {"kinds": {}}
            for line in data.strip().split("\n"):
                record = json.loads(line)
                kind = record.pop("kind")
                if kind not in export_data["kinds"]:
                    export_data["kinds"][kind] = []
                export_data["kinds"][kind].append(record)
        else:
            raise ValueError(f"Unsupported format: {format}")
        
        imported = 0
        for kind_str, records in export_data["kinds"].items():
            kind = MemoryKind(kind_str)
            store = self.memory.stores[kind]
            
            for record_data in records:
                record = MemoryRecord.from_dict(record_data)
                
                if merge_strategy == "upsert":
                    await store.upsert(record)
                elif merge_strategy == "skip_existing":
                    if not await store.exists(record.id):
                        await store.add(record)
                elif merge_strategy == "new_only":
                    # Generate new IDs, preserve content
                    record.id = f"mem_{uuid4().hex[:12]}"
                    record.metadata["imported_from"] = record_data["id"]
                    await store.add(record)
                
                imported += 1
        
        return {"imported": imported}
    
    async def delete_all_memories(self, confirmation: str):
        """Nuclear delete - requires explicit confirmation"""
        if confirmation != "DELETE ALL MEMORIES":
            raise ValueError("Must confirm with exact phrase: 'DELETE ALL MEMORIES'")
        
        await self.memory.forget_all(confirmation)
        
        return {"status": "all_memories_deleted"}
```

---

## 8. Integration with Task Engine

### 8.1 Automatic Memory Capture

```python
class TaskMemoryIntegration:
    """Automatically captures memories during task execution"""
    
    def __init__(self, runtime: "AppRuntime"):
        self.runtime = runtime
        self.runtime.events.on("task.step_completed", self._on_step_completed)
        self.runtime.events.on("task.completed", self._on_task_completed)
        self.runtime.events.on("task.failed", self._on_task_failed)
        self.runtime.events.on("approval.granted", self._on_approval)
        self.runtime.events.on("policy.grant_changed", self._on_grant_changed)
    
    async def _on_step_completed(self, event):
        """Capture procedural memory from successful steps"""
        task_id = event.data["task_id"]
        step = event.data["step"]
        result = event.data["result"]
        
        if result.get("success") and step.get("type") == "ADAPTER_CALL":
            # Learn procedure: "To do X, use adapter Y with params Z"
            procedure_name = f"How to {step['operation']} with {step['adapter']}"
            steps = [
                f"Use adapter: {step['adapter']}",
                f"Operation: {step['operation']}",
                f"Parameters: {json.dumps(step['params'])}",
            ]
            
            await self.runtime.memory.remember_procedure(
                name=procedure_name,
                steps=steps,
                importance=0.6,
                source="auto",
                tags=[step['adapter'], step['operation']],
            )
    
    async def _on_task_completed(self, event):
        """Create episodic memory for completed task"""
        task = event.data["task"]
        
        await self.runtime.memory.remember_episode(
            content=f"Task completed: {task.objective}",
            episode_timestamp=task.completed_at,
            importance=0.8,
            source="auto",
            participants=[task.assigned_agent_id] if task.assigned_agent_id else ["user"],
            outcome="success",
            source_task_id=task.id,
            tags=[task.type],
        )
        
        # Also store key facts as semantic
        if task.evidence_bundle:
            for evidence in task.evidence_bundle.records:
                if evidence.type == "VERIFICATION" and evidence.metadata.get("key_fact"):
                    await self.runtime.memory.remember_fact(
                        content=evidence.metadata["key_fact"],
                        subject=evidence.metadata.get("subject", "task"),
                        predicate="resulted_in",
                        object=evidence.metadata.get("outcome", "success"),
                        importance=0.7,
                        source="task_evidence",
                        source_episode_id=f"task_{task.id}",
                    )
    
    async def _on_approval(self, event):
        """Learn user preference from approval"""
        capability = event.data["capability"]
        resource = event.data.get("resource", "")
        
        # Infer preference: user allows this capability
        pref_key = f"allow_{capability.replace('.', '_')}"
        if resource:
            pref_key += f"_{resource.replace('.', '_').replace('/', '_')}"
        
        await self.runtime.memory.remember_preference(
            key=pref_key,
            value=True,
            type="inferred",
            scope="global" if not resource else "resource",
            metadata={"source_approval": event.data["task_id"]},
        )
```

---

## 9. Performance Optimization

### 9.1 Embedding Cache

```python
class EmbeddingCache:
    """Caches embeddings to avoid recomputation"""
    
    def __init__(self, max_size: int = 10000):
        self.cache: Dict[str, List[float]] = {}
        self.max_size = max_size
        self.access_order: List[str] = []
    
    async def get_or_compute(self, text: str, embedder: Callable) -> List[float]:
        # Normalize text for caching
        key = hashlib.sha256(text.encode()).hexdigest()[:32]
        
        if key in self.cache:
            # Move to front (LRU)
            self.access_order.remove(key)
            self.access_order.insert(0, key)
            return self.cache[key]
        
        # Compute embedding
        embedding = await embedder(text)
        
        # Store with LRU eviction
        if len(self.cache) >= self.max_size:
            oldest = self.access_order.pop()
            del self.cache[oldest]
        
        self.cache[key] = embedding
        self.access_order.insert(0, key)
        
        return embedding
```

### 9.2 Batch Operations

```python
class BatchMemoryOperations:
    """Batch memory operations for efficiency"""
    
    async def batch_store(self, records: List[MemoryRecord]):
        """Store multiple records in single transaction"""
        by_kind = defaultdict(list)
        for record in records:
            by_kind[record.kind].append(record)
        
        for kind, kind_records in by_kind.items():
            store = self.memory.stores[kind]
            if hasattr(store, "batch_add"):
                await store.batch_add(kind_records)
            else:
                for record in kind_records:
                    await store.add(record)
    
    async def batch_retrieve(self, queries: List[Tuple[MemoryKind, str]], limit: int = 10):
        """Retrieve for multiple queries in parallel"""
        tasks = [self.memory.recall(kind, query, limit) for kind, query in queries]
        return await asyncio.gather(*tasks)
```

---

## 10. Testing Strategy

### 10.1 Unit Tests

```python
# tests/memory/test_memory_system.py

async def test_five_kinds_storage(memory_system):
    """Test storing in all five memory kinds"""
    # Semantic
    sem = await memory_system.remember_fact(
        "Python is a programming language",
        subject="Python", predicate="is_a", object="programming language"
    )
    assert sem.kind == MemoryKind.SEMANTIC
    
    # Episodic
    ep = await memory_system.remember_episode(
        "User opened Chrome", episode_timestamp=datetime.utcnow()
    )
    assert ep.kind == MemoryKind.EPISODIC
    
    # Procedural
    proc = await memory_system.remember_procedure(
        "Open Chrome", ["Launch chrome.exe", "Wait for window"]
    )
    assert proc.kind == MemoryKind.PROCEDURAL
    
    # Preference
    pref = await memory_system.remember_preference("theme", "dark")
    assert pref.kind == MemoryKind.PREFERENCE
    
    # Working
    work = await memory_system.remember_working("task_123", "Current URL: github.com")
    assert work.kind == MemoryKind.WORKING

async def test_cross_kind_retrieval(memory_system):
    """Test unified recall across kinds"""
    # Store related memories in different kinds
    await memory_system.remember_fact("User prefers dark mode", "User", "prefers", "dark_mode")
    await memory_system.remember_preference("theme", "dark")
    await memory_system.remember_episode("User set theme to dark", datetime.utcnow())
    
    results = await memory_system.recall_for_context("dark mode preference")
    
    assert MemoryKind.SEMANTIC in results
    assert MemoryKind.PREFERENCE in results
    assert MemoryKind.EPISODIC in results
    # Preference should rank highest for exact key match
    assert results[MemoryKind.PREFERENCE][0].relevance_score > 0.9

async def test_consolidation_promotion(memory_system, consolidator):
    """Test working → episodic promotion"""
    # Create important working memory
    work = await memory_system.remember_working(
        "task_1", "Critical finding: API key in config",
        importance=0.9, source="explicit"
    )
    
    # Manually trigger promotion (simulate time passing)
    work.created_at = datetime.utcnow() - timedelta(hours=2)
    await memory_system.stores[MemoryKind.WORKING].update(work)
    
    # Run consolidation
    await consolidator._promote_working_to_episodic()
    
    # Verify promotion
    episodic_memories = await memory_system.recall(
        MemoryKind.EPISODIC, "API key in config", limit=5
    )
    assert len(episodic_memories) > 0
    assert episodic_memories[0].metadata.get("promoted_from") == work.id

async def test_preference_conflict_resolution(memory_system, consolidator):
    """Test preference conflict resolution"""
    # Create conflicting preferences
    await memory_system.remember_preference("theme", "light", type="inferred")
    await memory_system.remember_preference("theme", "dark", type="explicit")
    
    # Run consolidation
    await consolidator._resolve_preference_conflicts()
    
    # Explicit should win
    current = await memory_system.get_preference("theme")
    assert current == "dark"
```

---

## 11. Configuration

```toml
# config/memory.toml

[storage]
chroma_path = "data/memory/chroma"
sqlite_path = "data/memory/memory.sqlite"
backup_path = "data/memory/backups"

[retention]
semantic_permanent = true
episodic_max_days = 365
episodic_archive_days = 90
procedural_permanent = true
preference_permanent = true
working_ttl_hours = 24

[consolidation]
interval_hours = 6
promote_importance_threshold = 0.7
promote_source_types = ["explicit", "correction"]
promote_min_age_hours = 1
summarize_importance_threshold = 0.8
summarize_min_age_days = 30
reinforce_success_threshold = 3
weaken_on_failure = true

[retrieval]
default_limit = 10
min_similarity = 0.7
rerank_weights = {similarity=0.35, importance=0.20, recency=0.15, frequency=0.10, source=0.10, context=0.10}
max_context_results = 50

[privacy]
pii_detection = true
pii_encryption = true
require_consent_for_pii = true
encrypt_sensitive_kinds = ["preference", "episodic"]

[performance]
embedding_cache_size = 10000
batch_size = 100
parallel_retrieval = true
chroma_hnsw_ef = 128
```

---

## 12. Open Memory Decisions

| Decision | Options | Considerations |
|----------|---------|----------------|
| Embedding model | text-embedding-3-small / BGE / Local | Cost vs quality vs privacy |
| Vector DB | ChromaDB / Qdrant / Weaviate | Chroma: embedded, simple; Qdrant: production-ready |
| Episodic summarization | LLM-based / Rule-based / Hybrid | Quality vs cost |
| Cross-device sync | None / Encrypted sync / CRDT | User demand vs complexity |
| Memory compression | None / Summarization / Quantization | Storage vs retrieval quality |
| Forgetting curve | Exponential / Power-law / Custom | Cognitive plausibility |
| PII detection | Regex / NER model / LLM | Accuracy vs performance |