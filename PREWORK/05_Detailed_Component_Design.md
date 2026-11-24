# ARISE — Detailed Component Design

## Overview

This document specifies the detailed design of each major component in the ARISE architecture. Each component is defined by its:
- **Interface Contract** (Ports/Protocols)
- **Internal Structure** (Classes, State Machines, Algorithms)
- **Dependencies** (Upstream/Downstream)
- **Configuration** (Settings, Tunables)
- **Error Handling** (Retry, Fallback, Degradation)
- **Testing Strategy** (Unit, Integration, Contract)

---

## 1. Task Engine (`src/arise/engine/`)

### 1.1 Task Status Machine (28 States)

```python
# src/arise/engine/tasks.py
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import uuid4

class TaskStatus(Enum):
    # Initial
    CREATED = "created"                    # Task object instantiated
    QUEUED = "queued"                      # Waiting for scheduler/executor slot
    
    # Understanding & Planning
    UNDERSTANDING = "understanding"        # Intent classification, entity extraction
    PLANNING = "planning"                  # Decomposition, agent selection, resource estimation
    PLAN_REVIEW = "plan_review"            # Human review of plan (optional, for complex tasks)
    PLAN_APPROVED = "plan_approved"        # Plan accepted, ready to execute
    PLAN_REJECTED = "plan_rejected"        # Plan rejected, back to planning
    
    # Pre-execution
    READY = "ready"                        # All resources allocated, permissions granted
    WAITING_APPROVAL = "waiting_approval"  # Explicit user approval needed (R2+)
    WAITING_RESOURCE = "waiting_resource"  # Resource contention (GPU, API quota, lock)
    WAITING_DEPENDENCY = "waiting_dependency" # Upstream task not complete
    
    # Execution
    RUNNING = "running"                    # Active execution
    PAUSED = "paused"                      # User/system paused, state preserved
    WAITING_INPUT = "waiting_input"        # Need user clarification mid-task
    WAITING_AGENT = "waiting_agent"        # Delegated to specialist agent
    WAITING_TOOL = "waiting_tool"          # Waiting for external tool/API response
    WAITING_VERIFICATION = "waiting_verification" # Execution done, awaiting verification
    
    # Verification & Completion
    VERIFYING = "verifying"                # Independent postcondition checks running
    VERIFICATION_PASSED = "verification_passed"
    VERIFICATION_FAILED = "verification_failed"
    COMPLETED = "completed"                # Success, evidence recorded
    PARTIAL = "partial"                    # Some steps succeeded, others failed
    
    # Failure & Termination
    FAILED = "failed"                      # Terminal failure, evidence recorded
    CANCELLED = "cancelled"                # User/system cancelled, cleanup done
    TIMED_OUT = "timed_out"                # Exceeded deadline, cleanup done
    RECOVERING = "recovering"              # Attempting recovery from failure
    
    # Special
    ARCHIVED = "archived"                  # Moved to cold storage

# Valid transitions (enforced by TaskEngine)
VALID_TRANSITIONS: Dict[TaskStatus, List[TaskStatus]] = {
    TaskStatus.CREATED: [TaskStatus.QUEUED, TaskStatus.CANCELLED],
    TaskStatus.QUEUED: [TaskStatus.UNDERSTANDING, TaskStatus.CANCELLED],
    TaskStatus.UNDERSTANDING: [TaskStatus.PLANNING, TaskStatus.FAILED, TaskStatus.CANCELLED],
    TaskStatus.PLANNING: [TaskStatus.PLAN_REVIEW, TaskStatus.PLAN_APPROVED, TaskStatus.PLAN_REJECTED, TaskStatus.FAILED, TaskStatus.CANCELLED],
    TaskStatus.PLAN_REVIEW: [TaskStatus.PLAN_APPROVED, TaskStatus.PLAN_REJECTED, TaskStatus.CANCELLED],
    TaskStatus.PLAN_APPROVED: [TaskStatus.READY, TaskStatus.WAITING_APPROVAL, TaskStatus.CANCELLED],
    TaskStatus.PLAN_REJECTED: [TaskStatus.PLANNING, TaskStatus.CANCELLED],
    TaskStatus.READY: [TaskStatus.RUNNING, TaskStatus.WAITING_RESOURCE, TaskStatus.WAITING_DEPENDENCY, TaskStatus.CANCELLED],
    TaskStatus.WAITING_APPROVAL: [TaskStatus.READY, TaskStatus.CANCELLED, TaskStatus.TIMED_OUT],
    TaskStatus.WAITING_RESOURCE: [TaskStatus.READY, TaskStatus.CANCELLED, TaskStatus.TIMED_OUT],
    TaskStatus.WAITING_DEPENDENCY: [TaskStatus.READY, TaskStatus.CANCELLED],
    TaskStatus.RUNNING: [TaskStatus.PAUSED, TaskStatus.WAITING_INPUT, TaskStatus.WAITING_AGENT, TaskStatus.WAITING_TOOL, TaskStatus.WAITING_VERIFICATION, TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.TIMED_OUT],
    TaskStatus.PAUSED: [TaskStatus.RUNNING, TaskStatus.CANCELLED],
    TaskStatus.WAITING_INPUT: [TaskStatus.RUNNING, TaskStatus.CANCELLED, TaskStatus.TIMED_OUT],
    TaskStatus.WAITING_AGENT: [TaskStatus.RUNNING, TaskStatus.FAILED, TaskStatus.CANCELLED],
    TaskStatus.WAITING_TOOL: [TaskStatus.RUNNING, TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.TIMED_OUT],
    TaskStatus.WAITING_VERIFICATION: [TaskStatus.VERIFYING, TaskStatus.CANCELLED],
    TaskStatus.VERIFYING: [TaskStatus.VERIFICATION_PASSED, TaskStatus.VERIFICATION_FAILED, TaskStatus.CANCELLED],
    TaskStatus.VERIFICATION_PASSED: [TaskStatus.COMPLETED],
    TaskStatus.VERIFICATION_FAILED: [TaskStatus.RECOVERING, TaskStatus.PARTIAL, TaskStatus.FAILED],
    TaskStatus.COMPLETED: [TaskStatus.ARCHIVED],
    TaskStatus.PARTIAL: [TaskStatus.ARCHIVED, TaskStatus.RECOVERING],
    TaskStatus.FAILED: [TaskStatus.RECOVERING, TaskStatus.ARCHIVED],
    TaskStatus.CANCELLED: [TaskStatus.ARCHIVED],
    TaskStatus.TIMED_OUT: [TaskStatus.RECOVERING, TaskStatus.ARCHIVED],
    TaskStatus.RECOVERING: [TaskStatus.READY, TaskStatus.PLANNING, TaskStatus.FAILED, TaskStatus.CANCELLED],
    TaskStatus.ARCHIVED: [],
}

@dataclass
class TaskContext:
    """Serializable execution context - checkpointed at every state transition"""
    variables: Dict[str, Any] = field(default_factory=dict)
    references: Dict[str, str] = field(default_factory=dict)  # name -> object_id
    step_results: List[Dict[str, Any]] = field(default_factory=list)
    agent_outputs: Dict[str, Any] = field(default_factory=dict)
    evidence_refs: List[str] = field(default_factory=list)
    checkpoints: List[str] = field(default_factory=list)  # checkpoint IDs
    
    def to_json(self) -> str: ...
    @classmethod
    def from_json(cls, data: str) -> "TaskContext": ...

@dataclass
class Task:
    id: str = field(default_factory=lambda: f"task_{uuid4().hex[:12]}")
    type: str                                           # e.g., "desktop_control", "research", "coding"
    objective: str                                      # User's natural language request
    status: TaskStatus = TaskStatus.CREATED
    priority: int = 0                                   # Higher = more urgent
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    deadline: Optional[datetime] = None
    parent_task_id: Optional[str] = None                # For sub-tasks
    child_task_ids: List[str] = field(default_factory=list)
    assigned_agent_id: Optional[str] = None
    required_capabilities: List[str] = field(default_factory=list)
    granted_capabilities: List[str] = field(default_factory=list)
    context: TaskContext = field(default_factory=TaskContext)
    plan: Optional["ExecutionPlan"] = None
    evidence_bundle: Optional["EvidenceBundle"] = None
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    
    def can_transition(self, new_status: TaskStatus) -> bool:
        return new_status in VALID_TRANSITIONS.get(self.status, [])
    
    def transition(self, new_status: TaskStatus) -> bool:
        if not self.can_transition(new_status):
            raise InvalidTransitionError(f"{self.status} -> {new_status}")
        self.status = new_status
        self.updated_at = datetime.utcnow()
        if new_status == TaskStatus.RUNNING and not self.started_at:
            self.started_at = datetime.utcnow()
        if new_status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.PARTIAL):
            self.completed_at = datetime.utcnow()
        return True
```

### 1.2 Execution Plan

```python
# src/arise/engine/planning.py
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum

class StepType(Enum):
    ADAPTER_CALL = "adapter_call"        # Direct adapter invocation
    AGENT_DELEGATE = "agent_delegate"    # Delegate to specialist agent
    SUB_TASK = "sub_task"                # Create child task
    USER_INPUT = "user_input"            # Request clarification
    VERIFICATION = "verification"        # Independent check
    CHECKPOINT = "checkpoint"            # Persist state
    CONDITIONAL = "conditional"          # Branch based on condition

@dataclass
class PlanStep:
    id: str
    type: StepType
    description: str
    # For ADAPTER_CALL
    adapter: Optional[str] = None
    operation: Optional[str] = None
    params: Dict[str, Any] = field(default_factory=dict)
    # For AGENT_DELEGATE
    agent_role: Optional[str] = None
    agent_prompt: Optional[str] = None
    # For SUB_TASK
    sub_task_type: Optional[str] = None
    sub_task_objective: Optional[str] = None
    # For CONDITIONAL
    condition: Optional[str] = None       # Expression evaluable in context
    then_step: Optional[str] = None
    else_step: Optional[str] = None
    # Common
    depends_on: List[str] = field(default_factory=list)  # Step IDs
    timeout_seconds: int = 300
    retry_policy: Dict[str, Any] = field(default_factory=dict)
    idempotency_key: Optional[str] = None
    expected_evidence: List[str] = field(default_factory=list)

@dataclass
class ExecutionPlan:
    task_id: str
    steps: List[PlanStep] = field(default_factory=list)
    estimated_duration_seconds: int = 0
    required_capabilities: List[str] = field(default_factory=list)
    required_resources: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    planner_version: str = "1.0"
    
    def get_executable_steps(self, completed_step_ids: set) -> List[PlanStep]:
        """Return steps whose dependencies are satisfied"""
        return [
            s for s in self.steps
            if s.id not in completed_step_ids
            and all(d in completed_step_ids for d in s.depends_on)
        ]
    
    def topological_order(self) -> List[PlanStep]:
        """Return steps in dependency order"""
        # Kahn's algorithm
        ...
```

### 1.3 Task Engine Core

```python
# src/arise/engine/engine.py
from abc import ABC, abstractmethod
from typing import AsyncGenerator, Optional, List
import asyncio
from contextlib import asynccontextmanager

class TaskEngine:
    """
    Central task orchestration engine.
    Manages lifecycle, scheduling, checkpointing, recovery.
    """
    
    def __init__(
        self,
        runtime: "AppRuntime",
        planner: "GatewayTaskPlanner",
        policy_engine: "PolicyEngine",
        agent_coordinator: "CentralCoordinator",
        checkpoint_store: "CheckpointStore",
        event_bus: "EventBus",
        max_concurrent: int = 4,
    ):
        self.runtime = runtime
        self.planner = planner
        self.policy = policy_engine
        self.coordinator = agent_coordinator
        self.checkpoints = checkpoint_store
        self.events = event_bus
        self.max_concurrent = max_concurrent
        
        self._running_tasks: Dict[str, Task] = {}
        self._task_queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._worker_semaphore = asyncio.Semaphore(max_concurrent)
        self._shutdown = False
    
    async def submit(self, task: Task) -> str:
        """Submit task for execution, return task_id"""
        # 1. Validate objective, classify intent
        intent = await self.runtime.intent_classifier.classify(task.objective)
        task.context.variables["intent"] = intent
        
        # 2. Policy check - can this task even be created?
        risk = await self.policy.assess_risk(task.objective, intent)
        task.required_capabilities = risk.required_capabilities
        
        # 3. Create initial checkpoint
        await self.checkpoints.save(TaskCheckpoint.from_task(task))
        
        # 4. Queue for processing
        await self._task_queue.put((-task.priority, task.created_at, task))
        
        # 5. Emit event
        await self.events.emit("task.created", task)
        
        return task.id
    
    async def start_workers(self, count: int = None):
        """Start background worker tasks"""
        count = count or self.max_concurrent
        for i in range(count):
            asyncio.create_task(self._worker(f"worker-{i}"))
    
    async def _worker(self, name: str):
        while not self._shutdown:
            try:
                _, _, task = await asyncio.wait_for(
                    self._task_queue.get(), timeout=1.0
                )
                async with self._worker_semaphore:
                    await self._execute_task(task)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Worker {name} error: {e}")
    
    async def _execute_task(self, task: Task):
        """Main execution loop for a single task"""
        self._running_tasks[task.id] = task
        
        try:
            # UNDERSTANDING -> PLANNING
            await self._transition(task, TaskStatus.UNDERSTANDING)
            await self._transition(task, TaskStatus.PLANNING)
            
            # Generate plan
            plan = await self.planner.create_plan(task, self.runtime)
            task.plan = plan
            
            # PLAN_REVIEW (optional for complex tasks)
            if plan.estimated_duration_seconds > 300 or plan.required_capabilities:
                await self._transition(task, TaskStatus.PLAN_REVIEW)
                # Wait for approval via event...
            
            await self._transition(task, TaskStatus.PLAN_APPROVED)
            
            # Policy: check capabilities, request approvals
            grants = await self.policy.request_approvals(task)
            task.granted_capabilities = grants
            
            await self._transition(task, TaskStatus.READY)
            
            # Execute steps
            await self._transition(task, TaskStatus.RUNNING)
            await self._execute_plan(task)
            
            # Verification
            await self._transition(task, TaskStatus.WAITING_VERIFICATION)
            await self._transition(task, TaskStatus.VERIFYING)
            
            verified = await self._verify_completion(task)
            if verified:
                await self._transition(task, TaskStatus.VERIFICATION_PASSED)
                await self._transition(task, TaskStatus.COMPLETED)
            else:
                await self._transition(task, TaskStatus.VERIFICATION_FAILED)
                # Recovery logic...
                await self._transition(task, TaskStatus.FAILED)
                
        except TaskCancelled:
            await self._transition(task, TaskStatus.CANCELLED)
        except Exception as e:
            task.error = str(e)
            await self._transition(task, TaskStatus.FAILED)
            logger.exception(f"Task {task.id} failed")
        finally:
            # Final checkpoint, cleanup
            await self.checkpoints.save(TaskCheckpoint.from_task(task))
            await self.events.emit(f"task.{task.status.value}", task)
            self._running_tasks.pop(task.id, None)
    
    async def _execute_plan(self, task: Task):
        """Execute plan steps with dependency resolution"""
        completed_steps = set()
        step_futures: Dict[str, asyncio.Task] = {}
        
        while len(completed_steps) < len(task.plan.steps):
            # Get executable steps
            executable = task.plan.get_executable_steps(completed_steps)
            
            if not executable:
                # Wait for running steps to complete
                done, _ = await asyncio.wait(
                    step_futures.values(),
                    return_when=asyncio.FIRST_COMPLETED
                )
                for fut in done:
                    step_id = next(k for k, v in step_futures.items() if v == fut)
                    step_futures.pop(step_id)
                    completed_steps.add(step_id)
                continue
            
            # Launch executable steps (respecting concurrency)
            for step in executable:
                if len(step_futures) >= self.max_concurrent:
                    break
                fut = asyncio.create_task(self._execute_step(task, step))
                step_futures[step.id] = fut
            
            # Wait for at least one to complete
            if step_futures:
                done, _ = await asyncio.wait(
                    step_futures.values(),
                    return_when=asyncio.FIRST_COMPLETED
                )
                for fut in done:
                    step_id = next(k for k, v in step_futures.items() if v == fut)
                    step_futures.pop(step_id)
                    completed_steps.add(step_id)
    
    async def _execute_step(self, task: Task, step: PlanStep):
        """Execute a single plan step"""
        checkpoint_id = await self.checkpoints.save(TaskCheckpoint.from_task(task))
        task.context.checkpoints.append(checkpoint_id)
        
        try:
            if step.type == StepType.ADAPTER_CALL:
                result = await self.runtime.adapters.call(
                    step.adapter, step.operation, step.params,
                    capabilities=task.granted_capabilities
                )
            elif step.type == StepType.AGENT_DELEGATE:
                result = await self.coordinator.delegate(
                    step.agent_role, step.agent_prompt,
                    parent_task_id=task.id,
                    capabilities=task.granted_capabilities
                )
            elif step.type == StepType.SUB_TASK:
                sub_task = Task(
                    type=step.sub_task_type,
                    objective=step.sub_task_objective,
                    parent_task_id=task.id,
                    priority=task.priority,
                )
                sub_task_id = await self.submit(sub_task)
                task.child_task_ids.append(sub_task_id)
                # Wait for sub-task completion
                result = await self._wait_for_subtask(sub_task_id)
            elif step.type == StepType.USER_INPUT:
                result = await self._request_user_input(step.params.get("prompt"))
            elif step.type == StepType.VERIFICATION:
                result = await self._verify_step(task, step)
            elif step.type == StepType.CHECKPOINT:
                await self.checkpoints.save(TaskCheckpoint.from_task(task))
                result = {"checkpoint": "saved"}
            elif step.type == StepType.CONDITIONAL:
                condition_met = self._eval_condition(step.condition, task.context)
                next_step = step.then_step if condition_met else step.else_step
                result = {"branch": next_step}
            else:
                raise ValueError(f"Unknown step type: {step.type}")
            
            # Record step result
            task.context.step_results.append({
                "step_id": step.id,
                "result": result,
                "timestamp": datetime.utcnow().isoformat(),
            })
            
            # Verify expected evidence
            for ev in step.expected_evidence:
                if ev not in task.context.evidence_refs:
                    logger.warning(f"Expected evidence {ev} not produced by step {step.id}")
                    
        except Exception as e:
            # Retry logic
            if step.retry_policy.get("max_retries", 0) > task.retry_count:
                task.retry_count += 1
                await asyncio.sleep(step.retry_policy.get("backoff", 1) ** task.retry_count)
                return await self._execute_step(task, step)
            raise
    
    async def cancel_task(self, task_id: str, reason: str = "User cancelled"):
        """Cancel a running or queued task"""
        if task_id in self._running_tasks:
            task = self._running_tasks[task_id]
            # Signal cancellation to executing step
            task.context.variables["_cancel_requested"] = True
            task.context.variables["_cancel_reason"] = reason
            # Wait for graceful stop (with timeout)
            await asyncio.wait_for(self._wait_for_task_stop(task_id), timeout=30)
        else:
            # Remove from queue (would need queue inspection)
            pass
    
    async def pause_task(self, task_id: str):
        """Pause a running task, preserving state"""
        if task_id in self._running_tasks:
            task = self._running_tasks[task_id]
            await self._transition(task, TaskStatus.PAUSED)
            await self.checkpoints.save(TaskCheckpoint.from_task(task))
    
    async def resume_task(self, task_id: str):
        """Resume a paused task"""
        # Reload from checkpoint
        checkpoint = await self.checkpoints.load_latest(task_id)
        task = checkpoint.to_task()
        await self.submit(task)  # Re-queue
    
    async def _verify_completion(self, task: Task) -> bool:
        """Independent verification of task completion"""
        if not task.plan:
            return False
        
        verifier = self.runtime.verifier
        for step in task.plan.steps:
            if step.expected_evidence:
                for ev_ref in step.expected_evidence:
                    if not await verifier.verify_evidence(ev_ref, step):
                        return False
        return True
    
    async def _transition(self, task: Task, new_status: TaskStatus):
        """Atomic state transition with checkpoint and event"""
        old_status = task.status
        task.transition(new_status)
        await self.checkpoints.save(TaskCheckpoint.from_task(task))
        await self.events.emit("task.state_changed", {
            "task_id": task.id,
            "previous_state": old_status.value,
            "new_state": new_status.value,
            "timestamp": datetime.utcnow().isoformat(),
        })
```

### 1.4 Checkpoint Store (SQLite WAL)

```python
# src/arise/engine/checkpoints.py
import sqlite3
import json
from pathlib import Path
from contextlib import contextmanager
from typing import Optional, List

class CheckpointStore:
    """SQLite-backed checkpoint persistence with WAL mode"""
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        with self._conn() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS checkpoints (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    step_index INTEGER NOT NULL,
                    context_json TEXT NOT NULL,
                    evidence_refs TEXT NOT NULL,  -- JSON array
                    timestamp TEXT NOT NULL,      -- ISO 8601
                    agent_id TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_checkpoints_task 
                ON checkpoints(task_id, timestamp DESC)
            """)
    
    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()
    
    async def save(self, checkpoint: TaskCheckpoint) -> str:
        checkpoint_id = f"cp_{uuid4().hex[:12]}"
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO checkpoints (id, task_id, status, step_index, context_json, evidence_refs, timestamp, agent_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                checkpoint_id,
                checkpoint.task_id,
                checkpoint.state.value,
                checkpoint.step_index,
                checkpoint.context.to_json(),
                json.dumps(checkpoint.evidence_refs),
                checkpoint.timestamp.isoformat(),
                checkpoint.agent_id,
            ))
        return checkpoint_id
    
    async def load_latest(self, task_id: str) -> Optional[TaskCheckpoint]:
        with self._conn() as conn:
            row = conn.execute("""
                SELECT * FROM checkpoints 
                WHERE task_id = ? 
                ORDER BY timestamp DESC 
                LIMIT 1
            """, (task_id,)).fetchone()
            if row:
                return TaskCheckpoint(
                    task_id=row["task_id"],
                    state=TaskStatus(row["status"]),
                    step_index=row["step_index"],
                    context=TaskContext.from_json(row["context_json"]),
                    evidence_refs=json.loads(row["evidence_refs"]),
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    agent_id=row["agent_id"],
                )
        return None
    
    async def load_all(self, task_id: str) -> List[TaskCheckpoint]:
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT * FROM checkpoints WHERE task_id = ? ORDER BY timestamp
            """, (task_id,)).fetchall()
            return [TaskCheckpoint(...) for row in rows]
```

---

## 2. Policy Engine (`src/arise/policy/`)

### 2.1 Risk Assessment Model

```python
# src/arise/policy/models.py
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Callable
from datetime import datetime, time
import re

class RiskLevel(Enum):
    R0 = 0  # Read-only, no side effects
    R1 = 1  # Local write, reversible
    R2 = 2  # System state change
    R3 = 3  # External communication
    R4 = 4  # Irreversible / financial / security-critical

class CapabilityScope(Enum):
    GLOBAL = "global"                    # Applies everywhere
    APP_SPECIFIC = "app_specific"        # Specific application only
    PATH_SCOPED = "path_scoped"          # Specific filesystem paths
    TEMPORARY = "temporary"              # Time-limited grant

class GrantSource(Enum):
    POLICY_DEFAULT = "policy_default"    # Built-in policy
    USER_EXPLICIT = "user_explicit"      # User granted via UI
    TEMPORARY_APPROVAL = "temporary_approval"  # One-time approval
    INHERITED = "inherited"              # From parent task/agent

@dataclass
class Condition:
    """Runtime condition for capability grant"""
    type: str  # "time_of_day", "network_type", "battery_level", "custom"
    params: Dict[str, Any] = field(default_factory=dict)
    
    def evaluate(self, context: Dict[str, Any]) -> bool:
        if self.type == "time_of_day":
            now = datetime.now().time()
            start = time.fromisoformat(self.params["start"])
            end = time.fromisoformat(self.params["end"])
            return start <= now <= end
        elif self.type == "network_type":
            return context.get("network_type") in self.params.get("allowed", [])
        elif self.type == "battery_level":
            return context.get("battery_percent", 100) >= self.params.get("min_percent", 20)
        elif self.type == "custom":
            func = self.params.get("function")
            if callable(func):
                return func(context)
        return True

@dataclass
class CapabilityGrant:
    capability: str                      # e.g., "filesystem.write", "browser.navigate"
    scope: CapabilityScope = CapabilityScope.GLOBAL
    resource_pattern: Optional[str] = None  # Glob/regex for PATH_SCOPED
    expires_at: Optional[datetime] = None
    granted_by: GrantSource = GrantSource.POLICY_DEFAULT
    conditions: List[Condition] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def matches(self, capability: str, resource: str, context: Dict[str, Any]) -> bool:
        if not self._capability_matches(capability):
            return False
        if not self._resource_matches(resource):
            return False
        if self.expires_at and datetime.utcnow() > self.expires_at:
            return False
        return all(c.evaluate(context) for c in self.conditions)
    
    def _capability_matches(self, cap: str) -> bool:
        # Support wildcards: "filesystem.*" matches "filesystem.write"
        pattern = self.capability.replace(".", r"\.").replace("*", ".*")
        return bool(re.match(f"^{pattern}$", cap))
    
    def _resource_matches(self, resource: str) -> bool:
        if self.scope == CapabilityScope.GLOBAL:
            return True
        elif self.scope == CapabilityScope.APP_SPECIFIC:
            return self.resource_pattern == resource
        elif self.scope == CapabilityScope.PATH_SCOPED:
            import fnmatch
            return fnmatch.fnmatch(resource, self.resource_pattern or "*")
        elif self.scope == CapabilityScope.TEMPORARY:
            return True
        return False

@dataclass
class RiskAssessment:
    level: RiskLevel
    required_capabilities: List[str]
    reasoning: str
    requires_approval: bool
    approval_reason: Optional[str] = None
    suggested_grants: List[CapabilityGrant] = field(default_factory=list)
    conditions: List[Condition] = field(default_factory=list)
```

### 2.2 Policy Engine Core

```python
# src/arise/policy/engine.py
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import re

class PolicyEngine:
    """
    Central policy evaluation and approval system.
    Evaluates risk, checks capabilities, manages approvals.
    """
    
    def __init__(self, runtime: "AppRuntime"):
        self.runtime = runtime
        self.grants: Dict[str, List[CapabilityGrant]] = {}  # subject -> grants
        self.rules: List[PolicyRule] = []
        self._load_default_rules()
        self._load_user_rules()
    
    def _load_default_rules(self):
        """Built-in policy rules (cannot be removed, only overridden)"""
        self.rules = [
            # R0 - Read operations
            PolicyRule(
                pattern=r"^(list|read|get|search|find|view|inspect|describe)\b",
                risk_level=RiskLevel.R0,
                capabilities=["filesystem.read", "registry.read", "process.list"],
                description="Read-only operations",
            ),
            # R1 - Local reversible writes
            PolicyRule(
                pattern=r"^(create|write|edit|update|modify|click|type|select)\b",
                risk_level=RiskLevel.R1,
                capabilities=["filesystem.write", "ui.click", "ui.type", "browser.dom_write"],
                description="Local reversible actions",
            ),
            # R2 - System state changes
            PolicyRule(
                pattern=r"^(install|uninstall|configure|enable|disable|start|stop|restart|kill)\b",
                risk_level=RiskLevel.R2,
                capabilities=["system.install", "system.configure", "process.control", "service.control"],
                description="System configuration changes",
            ),
            # R3 - External communication
            PolicyRule(
                pattern=r"^(send|post|publish|email|message|notify|webhook|api_call)\b",
                risk_level=RiskLevel.R3,
                capabilities=["network.send", "email.send", "message.send", "webhook.call"],
                description="External communication",
            ),
            # R4 - Irreversible/financial
            PolicyRule(
                pattern=r"^(delete|remove|purchase|buy|transfer|shutdown|format|encrypt|sign)\b",
                risk_level=RiskLevel.R4,
                capabilities=["filesystem.delete", "financial.transact", "system.shutdown", "crypto.sign"],
                description="Irreversible or financial actions",
            ),
        ]
    
    def _load_user_rules(self):
        """Load user-defined rules from settings (override defaults)"""
        user_rules = self.runtime.settings.policy_rules
        for rule_data in user_rules:
            rule = PolicyRule(**rule_data)
            # Replace default rule with same pattern or append
            existing_idx = next((i for i, r in enumerate(self.rules) if r.pattern == rule.pattern), None)
            if existing_idx is not None:
                self.rules[existing_idx] = rule
            else:
                self.rules.append(rule)
        # Sort by specificity (longer pattern first)
        self.rules.sort(key=lambda r: -len(r.pattern))
    
    async def assess_risk(self, objective: str, intent: "IntentClassification") -> RiskAssessment:
        """Assess risk level and required capabilities for an objective"""
        # 1. Match against rules
        matched_rules = [r for r in self.rules if r.matches(objective, intent)]
        
        if not matched_rules:
            # Default to R1 for unknown
            return RiskAssessment(
                level=RiskLevel.R1,
                required_capabilities=["ui.interact"],
                reasoning="No matching policy rule, defaulting to R1",
                requires_approval=False,
            )
        
        # 2. Highest risk level wins
        max_risk = max(matched_rules, key=lambda r: r.risk_level.value)
        
        # 3. Aggregate capabilities
        all_caps = set()
        for rule in matched_rules:
            all_caps.update(rule.capabilities)
        
        # 4. Check existing grants
        granted = await self._check_grants("user", list(all_caps), {"objective": objective})
        missing = [c for c in all_caps if c not in granted]
        
        return RiskAssessment(
            level=max_risk.risk_level,
            required_capabilities=list(all_caps),
            reasoning=f"Matched {len(matched_rules)} rules, highest risk: {max_risk.risk_level.name}",
            requires_approval=max_risk.risk_level >= RiskLevel.R2 or bool(missing),
            approval_reason=f"Requires {max_risk.risk_level.name} capabilities: {missing}" if missing else None,
            suggested_grants=self._suggest_grants(missing, max_risk.risk_level),
        )
    
    async def check_capability(
        self,
        subject: str,          # "user", "agent:{id}", "task:{id}"
        capability: str,
        resource: str = "",
        context: Dict[str, Any] = None,
    ) -> bool:
        """Check if subject has capability for resource"""
        grants = self.grants.get(subject, [])
        context = context or {}
        return any(g.matches(capability, resource, context) for g in grants)
    
    async def request_approvals(self, task: Task) -> List[str]:
        """Request and record approvals for missing capabilities"""
        granted = []
        for cap in task.required_capabilities:
            if await self.check_capability("user", cap, "", {"task_id": task.id}):
                granted.append(cap)
            elif task.status == TaskStatus.WAITING_APPROVAL:
                # Wait for user approval via UI event
                approval = await self._wait_for_approval(task.id, cap)
                if approval:
                    self.grant_capability("user", CapabilityGrant(
                        capability=cap,
                        granted_by=GrantSource.TEMPORARY_APPROVAL,
                        expires_at=datetime.utcnow() + timedelta(hours=1),
                    ))
                    granted.append(cap)
                else:
                    raise ApprovalDeniedError(f"Approval denied for {cap}")
            else:
                # Request approval
                await self.runtime.events.emit("approval.requested", {
                    "task_id": task.id,
                    "capability": cap,
                    "risk_level": task.plan.required_risk_level if task.plan else RiskLevel.R1,
                })
                # Transition to WAITING_APPROVAL handled by caller
        return granted
    
    def grant_capability(self, subject: str, grant: CapabilityGrant):
        """Grant a capability to a subject"""
        if subject not in self.grants:
            self.grants[subject] = []
        self.grants[subject].append(grant)
        self._persist_grants()
    
    def revoke_capability(self, subject: str, capability: str):
        """Revoke a capability"""
        if subject in self.grants:
            self.grants[subject] = [
                g for g in self.grants[subject]
                if not g._capability_matches(capability)
            ]
            self._persist_grants()
    
    async def _wait_for_approval(self, task_id: str, capability: str) -> bool:
        """Wait for user approval via event (with timeout)"""
        future = asyncio.get_event_loop().create_future()
        
        def handler(event):
            if event.data.get("task_id") == task_id and event.data.get("capability") == capability:
                future.set_result(event.data.get("approved", False))
        
        self.runtime.events.on("approval.granted", handler)
        self.runtime.events.on("approval.denied", handler)
        
        try:
            return await asyncio.wait_for(future, timeout=300)  # 5 min
        except asyncio.TimeoutError:
            return False
        finally:
            self.runtime.events.off("approval.granted", handler)
            self.runtime.events.off("approval.denied", handler)
```

### 2.3 Approval UI Integration

```typescript
// Frontend: Approval Modal Component
interface ApprovalRequest {
  task_id: string;
  capability: string;
  risk_level: "R0" | "R1" | "R2" | "R3" | "R4";
  description: string;
  resource?: string;
  expires_in_seconds?: number;
}

// Risk level styling
const RISK_STYLES = {
  R0: { color: "green", label: "Read-only", icon: "eye" },
  R1: { color: "blue", label: "Local write", icon: "edit" },
  R2: { color: "amber", label: "System change", icon: "settings" },
  R3: { color: "orange", label: "External comms", icon: "send" },
  R4: { color: "red", label: "Irreversible", icon: "alert-triangle" },
};

// Approval flow:
// 1. Backend emits approval.requested event
// 2. Frontend shows modal with risk explanation
// 3. User grants/denies (with optional "remember for this app/folder")
// 4. Frontend invokes Tauri command: policy.grant_capability / policy.deny_capability
// 5. Backend receives, updates grants, continues task
```

---

## 3. Model Router (`src/arise/models/router.py`)

### 3.1 Provider Abstraction

```python
# src/arise/models/providers/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncGenerator, List, Dict, Any, Optional
from enum import Enum

class ModelCapability(Enum):
    TEXT_GENERATION = "text_generation"
    CHAT = "chat"
    EMBEDDINGS = "embeddings"
    VISION = "vision"
    AUDIO_INPUT = "audio_input"
    AUDIO_OUTPUT = "audio_output"
    TOOL_CALLING = "tool_calling"
    REASONING = "reasoning"
    REALTIME_AUDIO = "realtime_audio"  # Speech-to-speech
    STREAMING = "streaming"

@dataclass
class ModelSpec:
    id: str                              # Provider-specific model ID
    name: str                            # Human-readable name
    provider: str                        # "gemini", "openai", "anthropic", etc.
    capabilities: List[ModelCapability]
    context_window: int                  # Max tokens
    max_output_tokens: int
    pricing: Dict[str, float]            # per 1M tokens: input, output, cached_input
    latency_tier: str                    # "fast", "balanced", "quality"
    supports_streaming: bool = True
    supports_json_mode: bool = False
    supports_parallel_tool_calls: bool = False
    deprecated: bool = False

@dataclass
class CompletionRequest:
    messages: List[Dict[str, Any]]
    model: Optional[str] = None
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    tools: Optional[List[Dict]] = None
    tool_choice: Optional[str] = None
    response_format: Optional[Dict] = None
    stream: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class CompletionResponse:
    content: str
    model: str
    usage: Dict[str, int]                # prompt_tokens, completion_tokens, total_tokens
    finish_reason: str
    tool_calls: Optional[List[Dict]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

class ModelProvider(ABC):
    """Abstract base for model providers"""
    
    @property
    @abstractmethod
    def name(self) -> str: ...
    
    @abstractmethod
    async def list_models(self) -> List[ModelSpec]: ...
    
    @abstractmethod
    async def complete(self, request: CompletionRequest) -> CompletionResponse: ...
    
    @abstractmethod
    async def stream_complete(self, request: CompletionRequest) -> AsyncGenerator[str, None]: ...
    
    @abstractmethod
    async def embeddings(self, texts: List[str], model: str) -> List[List[float]]: ...
    
    @abstractmethod
    async def health_check(self) -> bool: ...
    
    @abstractmethod
    async def close(self): ...
```

### 3.2 Provider Implementations

```python
# src/arise/models/providers/gemini.py
import google.generativeai as genai
from google.generativeai.types import GenerateContentConfig
from .base import ModelProvider, ModelSpec, ModelCapability, CompletionRequest, CompletionResponse

class GeminiProvider(ModelProvider):
    name = "gemini"
    
    def __init__(self, api_key: str, config: Dict[str, Any]):
        genai.configure(api_key=api_key)
        self.config = config
        self._models_cache: List[ModelSpec] = []
    
    async def list_models(self) -> List[ModelSpec]:
        if not self._models_cache:
            # Static model specs for known models (API doesn't list all)
            self._models_cache = [
                ModelSpec(
                    id="gemini-3.8-live",
                    name="Gemini 3.8 Live",
                    provider="gemini",
                    capabilities=[ModelCapability.REALTIME_AUDIO, ModelCapability.TOOL_CALLING, ModelCapability.REASONING],
                    context_window=131072,
                    max_output_tokens=65536,
                    pricing={"input_audio": 0.005, "output_audio": 0.018},  # per minute
                    latency_tier="fast",
                ),
                ModelSpec(
                    id="gemini-3.8-live-extended-thinking",
                    name="Gemini 3.8 Live Extended Thinking",
                    provider="gemini",
                    capabilities=[ModelCapability.REALTIME_AUDIO, ModelCapability.TOOL_CALLING, ModelCapability.REASONING],
                    context_window=131072,
                    max_output_tokens=65536,
                    pricing={"input_audio": 0.005, "output_audio": 0.018},
                    latency_tier="balanced",
                ),
                ModelSpec(
                    id="gemini-2.5-pro",
                    name="Gemini 2.5 Pro",
                    provider="gemini",
                    capabilities=[ModelCapability.CHAT, ModelCapability.VISION, ModelCapability.TOOL_CALLING, ModelCapability.REASONING],
                    context_window=2000000,
                    max_output_tokens=8192,
                    pricing={"input": 1.25, "output": 5.00},  # per 1M tokens
                    latency_tier="quality",
                ),
                ModelSpec(
                    id="gemini-2.5-flash",
                    name="Gemini 2.5 Flash",
                    provider="gemini",
                    capabilities=[ModelCapability.CHAT, ModelCapability.VISION, ModelCapability.TOOL_CALLING],
                    context_window=1000000,
                    max_output_tokens=8192,
                    pricing={"input": 0.075, "output": 0.30},
                    latency_tier="fast",
                ),
            ]
        return self._models_cache
    
    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        model = genai.GenerativeModel(request.model or "gemini-2.5-flash")
        # Convert messages to Gemini format
        contents = self._convert_messages(request.messages)
        response = await model.generate_content_async(
            contents,
            generation_config=GenerateContentConfig(
                temperature=request.temperature,
                max_output_tokens=request.max_tokens,
            ),
            tools=request.tools,
        )
        return CompletionResponse(
            content=response.text,
            model=request.model,
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},  # TODO
            finish_reason="stop",
        )
    
    async def stream_complete(self, request: CompletionRequest):
        model = genai.GenerativeModel(request.model or "gemini-2.5-flash")
        contents = self._convert_messages(request.messages)
        response = await model.generate_content_async(
            contents,
            generation_config=GenerateContentConfig(temperature=request.temperature),
            stream=True,
        )
        async for chunk in response:
            if chunk.text:
                yield chunk.text
    
    async def embeddings(self, texts: List[str], model: str) -> List[List[float]]:
        result = await genai.embed_content_async(
            model=model or "text-embedding-004",
            content=texts,
        )
        return result["embedding"]
    
    async def health_check(self) -> bool:
        try:
            await self.embeddings(["health check"], "text-embedding-004")
            return True
        except Exception:
            return False
```

```python
# src/arise/models/providers/openai.py
from openai import AsyncOpenAI
from .base import ModelProvider, ModelSpec, ModelCapability, CompletionRequest, CompletionResponse

class OpenAIProvider(ModelProvider):
    name = "openai"
    
    def __init__(self, api_key: str, config: Dict[str, Any]):
        self.client = AsyncOpenAI(api_key=api_key, base_url=config.get("base_url"))
        self.config = config
    
    async def list_models(self) -> List[ModelSpec]:
        return [
            ModelSpec(
                id="gpt-realtime-2.1",
                name="GPT Realtime 2.1",
                provider="openai",
                capabilities=[ModelCapability.REALTIME_AUDIO, ModelCapability.TOOL_CALLING],
                context_window=128000,
                max_output_tokens=32000,
                pricing={"input_audio": 0.096, "output_audio": 0.24},  # per minute
                latency_tier="fast",
            ),
            ModelSpec(
                id="gpt-realtime-2.1-mini",
                name="GPT Realtime 2.1 Mini",
                provider="openai",
                capabilities=[ModelCapability.REALTIME_AUDIO, ModelCapability.TOOL_CALLING],
                context_window=128000,
                max_output_tokens=32000,
                pricing={"input_audio": 0.032, "output_audio": 0.08},
                latency_tier="fast",
            ),
            ModelSpec(
                id="gpt-5",
                name="GPT-5",
                provider="openai",
                capabilities=[ModelCapability.CHAT, ModelCapability.VISION, ModelCapability.TOOL_CALLING, ModelCapability.REASONING],
                context_window=200000,
                max_output_tokens=16384,
                pricing={"input": 5.00, "output": 15.00},
                latency_tier="quality",
            ),
            ModelSpec(
                id="gpt-4o",
                name="GPT-4o",
                provider="openai",
                capabilities=[ModelCapability.CHAT, ModelCapability.VISION, ModelCapability.TOOL_CALLING],
                context_window=128000,
                max_output_tokens=16384,
                pricing={"input": 2.50, "output": 10.00},
                latency_tier="balanced",
            ),
            ModelSpec(
                id="gpt-4o-mini",
                name="GPT-4o Mini",
                provider="openai",
                capabilities=[ModelCapability.CHAT, ModelCapability.VISION, ModelCapability.TOOL_CALLING],
                context_window=128000,
                max_output_tokens=16384,
                pricing={"input": 0.15, "output": 0.60},
                latency_tier="fast",
            ),
        ]
    
    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        response = await self.client.chat.completions.create(
            model=request.model or "gpt-4o-mini",
            messages=request.messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            tools=request.tools,
            tool_choice=request.tool_choice,
            response_format=request.response_format,
            stream=False,
        )
        choice = response.choices[0]
        return CompletionResponse(
            content=choice.message.content or "",
            model=response.model,
            usage={
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            },
            finish_reason=choice.finish_reason,
            tool_calls=[tc.model_dump() for tc in choice.message.tool_calls] if choice.message.tool_calls else None,
        )
    
    async def stream_complete(self, request: CompletionRequest):
        stream = await self.client.chat.completions.create(
            model=request.model or "gpt-4o-mini",
            messages=request.messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            stream=True,
        )
        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
    
    async def embeddings(self, texts: List[str], model: str) -> List[List[float]]:
        response = await self.client.embeddings.create(
            model=model or "text-embedding-3-small",
            input=texts,
        )
        return [d.embedding for d in response.data]
    
    async def health_check(self) -> bool:
        try:
            await self.client.models.list()
            return True
        except Exception:
            return False
```

### 3.3 Model Router with Circuit Breaker

```python
# src/arise/models/router.py
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum
import asyncio
import time
from collections import defaultdict

class CircuitState(Enum):
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Failing, reject requests
    HALF_OPEN = "half_open" # Testing recovery

@dataclass
class CircuitBreaker:
    provider: str
    failure_threshold: int = 5
    recovery_timeout: float = 30.0  # seconds
    half_open_max_calls: int = 3
    
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: float = 0
    half_open_calls: int = 0
    
    def record_success(self):
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.half_open_max_calls:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.success_count = 0
        elif self.state == CircuitState.CLOSED:
            self.failure_count = 0  # Reset on success
    
    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            self.half_open_calls = 0
        elif self.state == CircuitState.CLOSED and self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
    
    def can_execute(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
                return True
            return False
        if self.state == CircuitState.HALF_OPEN:
            return self.half_open_calls < self.half_open_max_calls
        return False
    
    def execute_start(self):
        if self.state == CircuitState.HALF_OPEN:
            self.half_open_calls += 1

@dataclass
class RoutingRule:
    task_type: str
    required_capabilities: List[ModelCapability]
    preferred_providers: List[str]  # In priority order
    fallback_providers: List[str]
    max_latency_ms: Optional[int] = None
    max_cost_per_request: Optional[float] = None
    privacy_mode: str = "standard"  # "standard", "private", "local_only"

class ModelRouter:
    """
    Intelligent model routing with circuit breakers, fallback chains,
    and capability-based selection.
    """
    
    def __init__(self, runtime: "AppRuntime"):
        self.runtime = runtime
        self.providers: Dict[str, ModelProvider] = {}
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.routing_rules: List[RoutingRule] = []
        self._load_default_rules()
        self._model_specs_cache: Dict[str, ModelSpec] = {}
    
    def register_provider(self, provider: ModelProvider):
        self.providers[provider.name] = provider
        self.circuit_breakers[provider.name] = CircuitBreaker(provider.name)
        # Invalidate cache
        self._model_specs_cache.clear()
    
    def _load_default_rules(self):
        self.routing_rules = [
            RoutingRule(
                task_type="voice_conversation",
                required_capabilities=[ModelCapability.REALTIME_AUDIO],
                preferred_providers=["gemini", "openai"],
                fallback_providers=[],
                privacy_mode="standard",
            ),
            RoutingRule(
                task_type="intent_classification",
                required_capabilities=[ModelCapability.CHAT],
                preferred_providers=["gemini", "openai"],
                fallback_providers=["anthropic", "local"],
                max_latency_ms=500,
                max_cost_per_request=0.001,
            ),
            RoutingRule(
                task_type="entity_extraction",
                required_capabilities=[ModelCapability.CHAT],
                preferred_providers=["gemini", "openai"],
                fallback_providers=["anthropic", "local"],
                max_latency_ms=500,
            ),
            RoutingRule(
                task_type="complex_reasoning",
                required_capabilities=[ModelCapability.REASONING, ModelCapability.CHAT],
                preferred_providers=["anthropic", "openai", "gemini"],
                fallback_providers=["local"],
                max_cost_per_request=0.10,
            ),
            RoutingRule(
                task_type="software_engineering",
                required_capabilities=[ModelCapability.CHAT, ModelCapability.TOOL_CALLING, ModelCapability.REASONING],
                preferred_providers=["anthropic", "openai", "gemini"],
                fallback_providers=["local"],
            ),
            RoutingRule(
                task_type="deep_research",
                required_capabilities=[ModelCapability.CHAT, ModelCapability.TOOL_CALLING],
                preferred_providers=["gemini", "anthropic", "openai"],
                fallback_providers=["local"],
            ),
            RoutingRule(
                task_type="code_generation",
                required_capabilities=[ModelCapability.CHAT, ModelCapability.TOOL_CALLING],
                preferred_providers=["anthropic", "openai", "gemini"],
                fallback_providers=["local"],
            ),
            RoutingRule(
                task_type="offline",
                required_capabilities=[ModelCapability.CHAT],
                preferred_providers=["local"],
                fallback_providers=[],
                privacy_mode="local_only",
            ),
        ]
    
    async def select_model(
        self,
        task_type: str,
        required_capabilities: List[ModelCapability] = None,
        context: Dict[str, Any] = None,
    ) -> tuple[str, ModelSpec]:  # (provider_name, model_spec)
        """Select best model for task type"""
        context = context or {}
        privacy_mode = context.get("privacy_mode", "standard")
        
        # Find matching rule
        rule = next((r for r in self.routing_rules if r.task_type == task_type), None)
        if not rule:
            rule = self.routing_rules[0]  # Default
        
        # Merge capabilities
        all_caps = set(rule.required_capabilities)
        if required_capabilities:
            all_caps.update(required_capabilities)
        
        # Get candidate providers in priority order
        candidates = rule.preferred_providers + rule.fallback_providers
        
        # Filter by privacy mode
        if privacy_mode == "local_only":
            candidates = [p for p in candidates if p == "local"]
        elif privacy_mode == "private":
            # Prefer providers with data processing agreements
            pass
        
        # Ensure models loaded
        await self._refresh_model_specs()
        
        # Score and select
        for provider_name in candidates:
            if provider_name not in self.providers:
                continue
            
            # Check circuit breaker
            cb = self.circuit_breakers[provider_name]
            if not cb.can_execute():
                continue
            
            # Find matching model
            provider = self.providers[provider_name]
            specs = await provider.list_models()
            
            for spec in specs:
                if spec.deprecated:
                    continue
                if not all(c in spec.capabilities for c in all_caps):
                    continue
                if rule.max_latency_ms and spec.latency_tier == "quality":
                    # Rough heuristic: quality tier > 1000ms
                    continue
                if rule.max_cost_per_request:
                    est_cost = self._estimate_cost(spec, context.get("estimated_tokens", 1000))
                    if est_cost > rule.max_cost_per_request:
                        continue
                
                return provider_name, spec
        
        raise NoSuitableModelError(f"No model found for task_type={task_type}, capabilities={all_caps}")
    
    async def complete(
        self,
        task_type: str,
        request: CompletionRequest,
        context: Dict[str, Any] = None,
    ) -> CompletionResponse:
        """Execute completion with automatic fallback"""
        context = context or {}
        last_error = None
        
        rule = next((r for r in self.routing_rules if r.task_type == task_type), None)
        candidates = (rule.preferred_providers + rule.fallback_providers) if rule else list(self.providers.keys())
        
        for provider_name in candidates:
            if provider_name not in self.providers:
                continue
            
            cb = self.circuit_breakers[provider_name]
            if not cb.can_execute():
                continue
            
            cb.execute_start()
            provider = self.providers[provider_name]
            
            try:
                # Use provider-specific model if not specified
                if not request.model:
                    _, spec = await self.select_model(task_type, context=context)
                    request.model = spec.id
                
                response = await provider.complete(request)
                cb.record_success()
                
                # Record usage for cost tracking
                await self.runtime.usage_tracker.record(provider_name, request.model, response.usage)
                
                return response
                
            except Exception as e:
                cb.record_failure()
                last_error = e
                logger.warning(f"Provider {provider_name} failed for {task_type}: {e}")
                continue
        
        raise AllProvidersFailedError(f"All providers failed for {task_type}: {last_error}")
    
    async def stream_complete(
        self,
        task_type: str,
        request: CompletionRequest,
        context: Dict[str, Any] = None,
    ):
        """Stream with fallback (falls back on first chunk failure)"""
        # Similar to complete but with streaming
        ...
    
    async def embeddings(
        self,
        texts: List[str],
        task_type: str = "embeddings",
        context: Dict[str, Any] = None,
    ) -> List[List[float]]:
        """Get embeddings with provider fallback"""
        provider_name, spec = await self.select_model(
            task_type,
            required_capabilities=[ModelCapability.EMBEDDINGS],
            context=context,
        )
        provider = self.providers[provider_name]
        cb = self.circuit_breakers[provider_name]
        
        cb.execute_start()
        try:
            result = await provider.embeddings(texts, spec.id)
            cb.record_success()
            return result
        except Exception as e:
            cb.record_failure()
            raise
    
    def _estimate_cost(self, spec: ModelSpec, estimated_tokens: int) -> float:
        """Estimate cost in USD for a request"""
        input_price = spec.pricing.get("input", spec.pricing.get("input_audio", 0))
        output_price = spec.pricing.get("output", spec.pricing.get("output_audio", 0))
        # Rough estimate: 75% input, 25% output
        return (input_price * 0.75 + output_price * 0.25) * estimated_tokens / 1_000_000
    
    async def _refresh_model_specs(self):
        """Refresh model specs from all providers"""
        for name, provider in self.providers.items():
            try:
                specs = await provider.list_models()
                for spec in specs:
                    self._model_specs_cache[f"{name}/{spec.id}"] = spec
            except Exception as e:
                logger.warning(f"Failed to refresh models for {name}: {e}")
    
    async def health_check_all(self) -> Dict[str, bool]:
        """Check health of all providers"""
        results = {}
        for name, provider in self.providers.items():
            cb = self.circuit_breakers[name]
            if cb.state == CircuitState.OPEN:
                results[name] = False
                continue
            try:
                results[name] = await provider.health_check()
            except Exception:
                results[name] = False
        return results
```

---

## 4. Multi-Agent Coordinator (`src/arise/agents/`)

### 4.1 Agent Base Class

```python
# src/arise/agents/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, AsyncGenerator
from enum import Enum
import asyncio

class AgentStatus(Enum):
    IDLE = "idle"
    INITIALIZING = "initializing"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    TERMINATED = "terminated"

@dataclass
class AgentCapability:
    name: str
    description: str
    required_permissions: List[str] = field(default_factory=list)
    max_concurrent: int = 1

@dataclass
class AgentContext:
    """Isolated context for each agent instance"""
    task_id: str
    parent_task_id: Optional[str]
    objective: str
    instructions: str
    allowed_capabilities: List[str]
    resource_limits: Dict[str, Any]
    working_directory: Optional[str] = None
    artifacts: List[str] = field(default_factory=list)
    evidence_refs: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

class BaseAgent(ABC):
    """Base class for all specialist agents"""
    
    def __init__(
        self,
        agent_id: str,
        role: str,
        runtime: "AppRuntime",
        capabilities: List[AgentCapability],
    ):
        self.agent_id = agent_id
        self.role = role
        self.runtime = runtime
        self.capabilities = capabilities
        self.status = AgentStatus.IDLE
        self.current_context: Optional[AgentContext] = None
        self._task: Optional[asyncio.Task] = None
        self._cancel_event = asyncio.Event()
    
    @abstractmethod
    async def execute(self, context: AgentContext) -> "AgentResult":
        """Execute the agent's work"""
        pass
    
    @abstractmethod
    async def validate_result(self, result: "AgentResult") -> bool:
        """Self-validation of result (coordinator does independent verification)"""
        pass
    
    async def start(self, context: AgentContext) -> "AgentResult":
        """Start agent execution"""
        self.current_context = context
        self.status = AgentStatus.INITIALIZING
        self._cancel_event.clear()
        
        try:
            # Initialize resources
            await self._initialize(context)
            self.status = AgentStatus.RUNNING
            
            # Execute with timeout
            result = await asyncio.wait_for(
                self.execute(context),
                timeout=context.resource_limits.get("max_duration_seconds", 300)
            )
            
            # Self-validate
            if await self.validate_result(result):
                self.status = AgentStatus.COMPLETED
            else:
                self.status = AgentStatus.FAILED
                result.error = "Self-validation failed"
            
            return result
            
        except asyncio.TimeoutError:
            self.status = AgentStatus.FAILED
            return AgentResult(success=False, error="Execution timeout", evidence=[])
        except asyncio.CancelledError:
            self.status = AgentStatus.TERMINATED
            return AgentResult(success=False, error="Cancelled", evidence=[])
        except Exception as e:
            self.status = AgentStatus.FAILED
            return AgentResult(success=False, error=str(e), evidence=[])
        finally:
            await self._cleanup()
    
    async def cancel(self):
        """Request cancellation"""
        self._cancel_event.set()
        if self._task:
            self._task.cancel()
    
    async def _initialize(self, context: AgentContext):
        """Override for agent-specific initialization"""
        pass
    
    async def _cleanup(self):
        """Override for agent-specific cleanup"""
        pass
    
    def check_cancelled(self):
        """Call periodically during long operations"""
        if self._cancel_event.is_set():
            raise asyncio.CancelledError()

@dataclass
class AgentResult:
    success: bool
    output: Any = None
    error: Optional[str] = None
    evidence: List[str] = field(default_factory=list)  # Evidence refs
    artifacts: List[str] = field(default_factory=list)  # File paths
    metadata: Dict[str, Any] = field(default_factory=dict)
```

### 4.2 Specialist Agents

```python
# src/arise/agents/specialists/research.py
class ResearchAgent(BaseAgent):
    """Deep research with cross-source verification"""
    
    def __init__(self, runtime: "AppRuntime"):
        capabilities = [
            AgentCapability("web_search", "Search the web via Brave API", ["network.search"]),
            AgentCapability("browser_navigate", "Navigate and extract via Playwright", ["browser.navigate"]),
            AgentCapability("source_verification", "Cross-reference multiple sources", ["network.search"]),
            AgentCapability("report_generation", "Generate cited research reports", []),
        ]
        super().__init__("research_agent", "research", runtime, capabilities)
    
    async def execute(self, context: AgentContext) -> AgentResult:
        # Parse research objective from instructions
        objective = context.objective
        depth = context.metadata.get("depth", "standard")  # quick, standard, deep
        
        # 1. Decompose into sub-questions
        sub_questions = await self._decompose_objective(objective)
        
        # 2. Research each sub-question
        findings = []
        for q in sub_questions:
            finding = await self._research_question(q, depth)
            findings.append(finding)
            self.check_cancelled()
        
        # 3. Cross-source verification
        verified = await self._cross_verify(findings)
        
        # 4. Generate report
        report = await self._generate_report(objective, verified)
        
        # 5. Save artifacts
        report_path = await self._save_report(report, context)
        
        return AgentResult(
            success=True,
            output=report,
            evidence=verified.evidence_refs,
            artifacts=[report_path],
            metadata={"sub_questions": len(sub_questions), "sources_checked": verified.source_count},
        )
    
    async def _decompose_objective(self, objective: str) -> List[str]:
        # Use model router for decomposition
        prompt = f"Decompose this research objective into 3-7 specific sub-questions:\n{objective}"
        response = await self.runtime.model_router.complete(
            "complex_reasoning",
            CompletionRequest(messages=[{"role": "user", "content": prompt}])
        )
        # Parse response into list
        return self._parse_questions(response.content)
    
    async def _research_question(self, question: str, depth: str) -> "ResearchFinding":
        # Search web
        search_results = await self.runtime.adapters.call("brave_research", "search", {
            "query": question,
            "count": 10 if depth == "deep" else 5,
        })
        
        # Extract content from top results
        sources = []
        for result in search_results[:5]:
            content = await self._extract_content(result.url)
            sources.append({"url": result.url, "title": result.title, "content": content})
        
        # Synthesize finding
        synthesis = await self._synthesize(question, sources)
        
        return ResearchFinding(question=question, sources=sources, synthesis=synthesis)
    
    async def _cross_verify(self, findings: List["ResearchFinding"]) -> "VerifiedResearch":
        # For each finding, check if multiple independent sources agree
        verified_findings = []
        all_evidence = []
        
        for finding in findings:
            # Group sources by domain/organization
            source_groups = self._group_by_independence(finding.sources)
            
            # Require at least 2 independent groups for verification
            if len(source_groups) >= 2:
                consensus = self._check_consensus(source_groups)
                verified_findings.append({
                    "question": finding.question,
                    "answer": consensus.answer,
                    "confidence": consensus.confidence,
                    "supporting_sources": consensus.sources,
                    "disagreements": consensus.disagreements,
                })
                all_evidence.extend(consensus.evidence_refs)
            else:
                verified_findings.append({
                    "question": finding.question,
                    "answer": finding.synthesis,
                    "confidence": "low",
                    "supporting_sources": finding.sources,
                    "disagreements": ["Insufficient independent sources"],
                })
        
        return VerifiedResearch(findings=verified_findings, evidence_refs=all_evidence)
```

```python
# src/arise/agents/specialists/coding.py
class CodingAgent(BaseAgent):
    """Software development agent with repository understanding"""
    
    def __init__(self, runtime: "AppRuntime"):
        capabilities = [
            AgentCapability("read_code", "Read and understand codebase", ["filesystem.read"]),
            AgentCapability("write_code", "Create/modify source files", ["filesystem.write"]),
            AgentCapability("run_tests", "Execute test suites", ["shell.execute"]),
            AgentCapability("lint_typecheck", "Run linters and type checkers", ["shell.execute"]),
            AgentCapability("git_operations", "Commit, branch, diff", ["shell.execute"]),
        ]
        super().__init__("coding_agent", "coding", runtime, capabilities)
    
    async def execute(self, context: AgentContext) -> AgentResult:
        # Context includes: repo_path, task_description, conventions, test_requirements
        repo_path = context.metadata.get("repo_path")
        task_desc = context.objective
        
        # 1. Understand repository
        repo_understanding = await self._understand_repo(repo_path)
        
        # 2. Read relevant files
        relevant_files = await self._identify_relevant_files(task_desc, repo_understanding)
        file_contents = await self._read_files(relevant_files)
        
        # 3. Generate implementation plan
        plan = await self._create_plan(task_desc, repo_understanding, file_contents)
        
        # 4. Implement changes
        changes = await self._implement(plan, context)
        
        # 5. Run tests
        test_results = await self._run_tests(repo_path, changes)
        
        # 6. Lint and typecheck
        lint_results = await self._lint_and_typecheck(repo_path)
        
        # 7. Generate summary
        summary = self._generate_summary(changes, test_results, lint_results)
        
        return AgentResult(
            success=test_results.passed and lint_results.passed,
            output=summary,
            evidence=test_results.evidence_refs + lint_results.evidence_refs,
            artifacts=changes.modified_files,
            metadata={"files_changed": len(changes.modified_files), "tests_passed": test_results.passed},
        )
    
    async def _create_plan(self, task: str, understanding: "RepoUnderstanding", files: Dict[str, str]) -> "ImplementationPlan":
        prompt = f"""
        Task: {task}
        
        Repository: {understanding.summary}
        Architecture: {understanding.architecture}
        Conventions: {understanding.conventions}
        
        Relevant files:
        {self._format_files(files)}
        
        Create a detailed implementation plan with:
        1. Files to create/modify
        2. Exact changes needed
        3. Test strategy
        4. Potential risks
        """
        response = await self.runtime.model_router.complete(
            "software_engineering",
            CompletionRequest(messages=[{"role": "user", "content": prompt}])
        )
        return self._parse_plan(response.content)
```

### 4.3 Central Coordinator

```python
# src/arise/agents/coordinator.py
class CentralCoordinator:
    """
    Central coordinator for multi-agent tasks.
    Understands objectives, decomposes, delegates, verifies, integrates.
    """
    
    def __init__(self, runtime: "AppRuntime"):
        self.runtime = runtime
        self.agent_registry = runtime.agent_registry
        self.active_delegations: Dict[str, "Delegation"] = {}
    
    async def delegate(
        self,
        role: str,
        prompt: str,
        parent_task_id: str,
        capabilities: List[str],
        context: Dict[str, Any] = None,
    ) -> AgentResult:
        """Delegate a sub-task to a specialist agent"""
        
        # 1. Get agent from registry
        agent = await self.agent_registry.get_agent(role)
        if not agent:
            raise AgentNotFoundError(f"No agent registered for role: {role}")
        
        # 2. Check agent health and capacity
        if not await agent.is_healthy():
            raise AgentUnavailableError(f"Agent {role} not healthy")
        
        # 3. Create agent context with scoped permissions
        agent_context = AgentContext(
            task_id=f"sub_{parent_task_id}_{role}_{uuid4().hex[:8]}",
            parent_task_id=parent_task_id,
            objective=prompt,
            instructions=self._build_instructions(role, prompt, context),
            allowed_capabilities=capabilities,
            resource_limits={
                "max_duration_seconds": 300,
                "max_memory_mb": 512,
                "max_api_calls": 50,
            },
            working_directory=context.get("working_directory") if context else None,
        )
        
        # 4. Record delegation
        delegation = Delegation(
            id=agent_context.task_id,
            parent_task_id=parent_task_id,
            agent_id=agent.agent_id,
            role=role,
            started_at=datetime.utcnow(),
            status="running",
        )
        self.active_delegations[delegation.id] = delegation
        
        # 5. Execute agent
        try:
            result = await agent.start(agent_context)
            delegation.status = "completed" if result.success else "failed"
            delegation.result = result
            delegation.completed_at = datetime.utcnow()
            
            # 6. Notify coordinator of completion (for integration)
            await self.runtime.events.emit("agent.delegation_completed", {
                "delegation_id": delegation.id,
                "parent_task_id": parent_task_id,
                "role": role,
                "success": result.success,
            })
            
            return result
            
        except Exception as e:
            delegation.status = "failed"
            delegation.error = str(e)
            raise
        finally:
            self.active_delegations.pop(delegation.id, None)
    
    async def orchestrate_complex_task(
        self,
        objective: str,
        parent_task_id: str,
        available_roles: List[str],
    ) -> "OrchestrationResult":
        """Full orchestration: decompose -> delegate -> integrate -> verify"""
        
        # 1. Understand and decompose
        decomposition = await self._decompose_objective(objective, available_roles)
        
        # 2. Create execution graph with dependencies
        execution_graph = self._build_execution_graph(decomposition)
        
        # 3. Execute with dependency resolution
        results = {}
        for node in execution_graph.topological_order():
            # Wait for dependencies
            for dep in node.depends_on:
                if dep in results and not results[dep].success:
                    raise DependencyFailedError(f"Dependency {dep} failed")
            
            # Delegate
            result = await self.delegate(
                role=node.role,
                prompt=node.prompt,
                parent_task_id=parent_task_id,
                capabilities=node.required_capabilities,
                context=node.context,
            )
            results[node.id] = result
        
        # 4. Integrate results
        integrated = await self._integrate_results(objective, results)
        
        # 5. Independent verification
        verification = await self._independent_verification(objective, integrated)
        
        return OrchestrationResult(
            success=verification.passed,
            integrated_output=integrated,
            agent_results=results,
            verification=verification,
        )
    
    def _build_instructions(self, role: str, prompt: str, context: Dict) -> str:
        """Build role-specific instructions for the agent"""
        base_instructions = {
            "research": "You are a research specialist. Provide thorough, cited findings.",
            "coding": "You are a software engineer. Follow conventions, write tests.",
            "computer_use": "You are a desktop automation specialist. Use UIA/Playwright.",
            "browser": "You are a browser automation specialist. Use Playwright CDP.",
            "filesystem": "You are a filesystem specialist. Read/write/search files.",
            "system": "You are a system administration specialist. Monitor/configure OS.",
            "communications": "You are a communications specialist. Send messages with approval.",
            "creative": "You are a creative specialist. Generate images/video/audio.",
            "memory": "You are a memory specialist. Store/retrieve/consolidate knowledge.",
            "projects": "You are a project management specialist. Plan/track milestones.",
        }
        return f"{base_instructions.get(role, '')}\n\nTask: {prompt}\n\nContext: {json.dumps(context, default=str)}"
```

---

## 5. Memory System (`src/arise/memory/`)

### 5.1 Five Kinds of Memory

```python
# src/arise/memory/system.py
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

class MemoryKind(Enum):
    SEMANTIC = "semantic"       # Facts, concepts, knowledge (permanent)
    EPISODIC = "episodic"       # Experiences, events, interactions (time-decay)
    PROCEDURAL = "procedural"   # Skills, workflows, how-to (reinforced by use)
    PREFERENCE = "preference"   # User preferences, corrections (explicit + inferred)
    WORKING = "working"         # Current task context, transient (TTL)

@dataclass
class MemoryRecord:
    id: str
    kind: MemoryKind
    content: str                    # Text content
    embedding: Optional[List[float]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    access_count: int = 0
    last_accessed: Optional[datetime] = None
    importance: float = 1.0         # 0-1, affects retention
    source: str = "auto"            # "auto", "explicit", "correction"
    expires_at: Optional[datetime] = None  # For WORKING memory
    tags: List[str] = field(default_factory=list)
    
    # Kind-specific fields
    episode_timestamp: Optional[datetime] = None  # EPISODIC
    procedure_steps: Optional[List[str]] = None   # PROCEDURAL
    preference_key: Optional[str] = None          # PREFERENCE

class MemorySystem:
    """Unified memory system with 5 kinds, governance, and consolidation"""
    
    def __init__(self, runtime: "AppRuntime"):
        self.runtime = runtime
        self.stores: Dict[MemoryKind, "MemoryStore"] = {}
        self.consolidation_scheduler = runtime.scheduler
        self._init_stores()
        self._schedule_consolidation()
    
    def _init_stores(self):
        # ChromaDB for vector-based kinds
        chroma_client = self.runtime.chroma_client
        self.stores[MemoryKind.SEMANTIC] = ChromaMemoryStore(
            chroma_client.get_collection("semantic"),
            MemoryKind.SEMANTIC,
        )
        self.stores[MemoryKind.EPISODIC] = ChromaMemoryStore(
            chroma_client.get_collection("episodic"),
            MemoryKind.EPISODIC,
        )
        self.stores[MemoryKind.PROCEDURAL] = ChromaMemoryStore(
            chroma_client.get_collection("procedural"),
            MemoryKind.PROCEDURAL,
        )
        self.stores[MemoryKind.PREFERENCE] = ChromaMemoryStore(
            chroma_client.get_collection("preference"),
            MemoryKind.PREFERENCE,
        )
        # SQLite FTS5 for working memory (fast, exact match)
        self.stores[MemoryKind.WORKING] = SQLiteWorkingStore(
            self.runtime.sqlite_pool,
        )
    
    async def store(
        self,
        kind: MemoryKind,
        content: str,
        metadata: Dict[str, Any] = None,
        embedding: List[float] = None,
        importance: float = 1.0,
        source: str = "auto",
        tags: List[str] = None,
        **kind_specific,
    ) -> MemoryRecord:
        """Store a memory record"""
        store = self.stores[kind]
        record = MemoryRecord(
            id=f"mem_{uuid4().hex[:12]}",
            kind=kind,
            content=content,
            embedding=embedding or await self._embed(content),
            metadata=metadata or {},
            importance=importance,
            source=source,
            tags=tags or [],
            **kind_specific,
        )
        
        # Kind-specific defaults
        if kind == MemoryKind.WORKING:
            record.expires_at = datetime.utcnow() + timedelta(hours=24)
        elif kind == MemoryKind.EPISODIC:
            record.episode_timestamp = kind_specific.get("episode_timestamp", datetime.utcnow())
        elif kind == MemoryKind.PROCEDURAL:
            record.procedure_steps = kind_specific.get("procedure_steps")
        elif kind == MemoryKind.PREFERENCE:
            record.preference_key = kind_specific.get("preference_key")
        
        await store.add(record)
        
        # Auto-link to current task if any
        current_task = self.runtime.task_engine.get_current_task()
        if current_task:
            current_task.context.evidence_refs.append(record.id)
        
        return record
    
    async def retrieve(
        self,
        kind: MemoryKind,
        query: str,
        limit: int = 10,
        filters: Dict[str, Any] = None,
        min_similarity: float = 0.7,
    ) -> List[MemoryRecord]:
        """Retrieve relevant memories"""
        store = self.stores[kind]
        query_embedding = await self._embed(query)
        results = await store.search(query_embedding, limit, filters, min_similarity)
        
        # Update access stats
        for record in results:
            record.access_count += 1
            record.last_accessed = datetime.utcnow()
            await store.update(record)
        
        return results
    
    async def retrieve_for_context(
        self,
        context: str,
        kinds: List[MemoryKind] = None,
        limit_per_kind: int = 5,
    ) -> Dict[MemoryKind, List[MemoryRecord]]:
        """Retrieve relevant memories across kinds for a context"""
        kinds = kinds or list(MemoryKind)
        results = {}
        for kind in kinds:
            results[kind] = await self.retrieve(kind, context, limit_per_kind)
        return results
    
    async def consolidate(self):
        """Scheduled consolidation: summarize, deduplicate, resolve conflicts"""
        # 1. Working -> Episodic (important working memories become episodic)
        await self._promote_working_to_episodic()
        
        # 2. Episodic summarization (old episodes -> semantic facts)
        await self._summarize_episodic()
        
        # 3. Procedural reinforcement (successful procedures -> stronger)
        await self._reinforce_procedural()
        
        # 4. Preference conflict resolution
        await self._resolve_preference_conflicts()
        
        # 5. Cleanup expired working memory
        await self._cleanup_expired()
    
    async def _promote_working_to_episodic(self):
        working_store = self.stores[MemoryKind.WORKING]
        episodic_store = self.stores[MemoryKind.EPISODIC]
        
        # Find important working memories (high access, explicit source)
        candidates = await working_store.search_by_criteria(
            importance_min=0.7,
            source_in=["explicit", "correction"],
            older_than=timedelta(hours=1),
        )
        
        for record in candidates:
            # Create episodic version
            episodic_record = MemoryRecord(
                id=f"mem_{uuid4().hex[:12]}",
                kind=MemoryKind.EPISODIC,
                content=record.content,
                embedding=record.embedding,
                metadata={**record.metadata, "promoted_from": record.id},
                importance=record.importance,
                source=record.source,
                episode_timestamp=record.created_at,
            )
            await episodic_store.add(episodic_record)
            # Keep working copy but mark promoted
            record.metadata["promoted"] = True
            await working_store.update(record)
    
    async def _summarize_episodic(self):
        """Convert old episodic memories into semantic facts"""
        episodic_store = self.stores[MemoryKind.EPISODIC]
        semantic_store = self.stores[MemoryKind.SEMANTIC]
        
        # Find episodes older than 30 days with high importance
        old_episodes = await episodic_store.search_by_criteria(
            importance_min=0.8,
            older_than=timedelta(days=30),
            not_summarized=True,
        )
        
        for episode in old_episodes:
            # Use LLM to extract semantic facts
            facts = await self._extract_facts(episode.content)
            
            for fact in facts:
                semantic_record = MemoryRecord(
                    id=f"mem_{uuid4().hex[:12]}",
                    kind=MemoryKind.SEMANTIC,
                    content=fact,
                    embedding=await self._embed(fact),
                    metadata={"source_episode": episode.id},
                    importance=0.9,
                    source="consolidation",
                )
                await semantic_store.add(semantic_record)
            
            episode.metadata["summarized"] = True
            await episodic_store.update(episode)
    
    async def delete_all(self, confirmation: str):
        """Complete deletion across all stores (requires explicit confirmation)"""
        if confirmation != "DELETE ALL MEMORIES":
            raise ValueError("Confirmation phrase mismatch")
        
        for kind, store in self.stores.items():
            await store.delete_all()
        
        # Also clear ChromaDB collections, SQLite tables, file artifacts
        await self.runtime.chroma_client.reset()
        await self.runtime.sqlite_pool.execute("DELETE FROM memories")
        
        # Note: Credential Manager and backups are NOT cleared by this
```

### 5.2 Memory Stores

```python
# src/arise/memory/stores/chroma.py
import chromadb
from chromadb.api.models.Collection import Collection
from typing import List, Optional, Dict, Any
from ..system import MemoryRecord, MemoryKind

class ChromaMemoryStore:
    """ChromaDB-backed store for vector-based memory kinds"""
    
    def __init__(self, collection: Collection, kind: MemoryKind):
        self.collection = collection
        self.kind = kind
    
    async def add(self, record: MemoryRecord):
        self.collection.add(
            ids=[record.id],
            documents=[record.content],
            embeddings=[record.embedding] if record.embedding else None,
            metadatas=[{
                "kind": record.kind.value,
                "metadata": json.dumps(record.metadata),
                "created_at": record.created_at.isoformat(),
                "updated_at": record.updated_at.isoformat(),
                "access_count": record.access_count,
                "last_accessed": record.last_accessed.isoformat() if record.last_accessed else None,
                "importance": record.importance,
                "source": record.source,
                "tags": json.dumps(record.tags),
                "episode_timestamp": record.episode_timestamp.isoformat() if record.episode_timestamp else None,
                "procedure_steps": json.dumps(record.procedure_steps) if record.procedure_steps else None,
                "preference_key": record.preference_key,
                "expires_at": record.expires_at.isoformat() if record.expires_at else None,
            }],
        )
    
    async def update(self, record: MemoryRecord):
        self.collection.update(
            ids=[record.id],
            documents=[record.content],
            embeddings=[record.embedding] if record.embedding else None,
            metadatas=[{
                "metadata": json.dumps(record.metadata),
                "updated_at": record.updated_at.isoformat(),
                "access_count": record.access_count,
                "last_accessed": record.last_accessed.isoformat() if record.last_accessed else None,
                "importance": record.importance,
            }],
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
            similarity = 1 - distance  # Cosine distance -> similarity
            if similarity >= min_similarity:
                meta = results["metadatas"][0][i]
                records.append(self._deserialize(doc_id, results["documents"][0][i], meta, results["embeddings"][0][i] if results["embeddings"] else None))
        return records
    
    async def search_by_criteria(self, **criteria) -> List[MemoryRecord]:
        where = self._build_where(criteria)
        results = self.collection.get(where=where, include=["documents", "embeddings", "metadatas"])
        return [self._deserialize(...) for ...]
    
    def _build_where(self, filters: Dict) -> Dict:
        # Convert criteria to Chroma where clause
        ...
    
    def _deserialize(self, id: str, content: str, meta: Dict, embedding: List[float]) -> MemoryRecord:
        return MemoryRecord(
            id=id,
            kind=self.kind,
            content=content,
            embedding=embedding,
            metadata=json.loads(meta.get("metadata", "{}")),
            created_at=datetime.fromisoformat(meta["created_at"]),
            updated_at=datetime.fromisoformat(meta["updated_at"]),
            access_count=meta.get("access_count", 0),
            last_accessed=datetime.fromisoformat(meta["last_accessed"]) if meta.get("last_accessed") else None,
            importance=meta.get("importance", 1.0),
            source=meta.get("source", "auto"),
            tags=json.loads(meta.get("tags", "[]")),
            episode_timestamp=datetime.fromisoformat(meta["episode_timestamp"]) if meta.get("episode_timestamp") else None,
            procedure_steps=json.loads(meta["procedure_steps"]) if meta.get("procedure_steps") else None,
            preference_key=meta.get("preference_key"),
            expires_at=datetime.fromisoformat(meta["expires_at"]) if meta.get("expires_at") else None,
        )
    
    async def delete_all(self):
        self.collection.delete(where={"kind": self.kind.value})
```

---

## 6. Voice Pipeline (`src/arise/voice/`)

### 6.1 Pipeline Orchestrator

```python
# src/arise/voice/pipeline.py
from dataclasses import dataclass
from typing import AsyncGenerator, Optional, Callable
from enum import Enum
import asyncio

class VoiceState(Enum):
    DORMANT = "dormant"           # Wake word listener only
    DETECTING = "detecting"       # Wake word detected, activating VAD
    LISTENING = "listening"       # VAD active, capturing speech
    PROCESSING = "processing"     # ASR complete, sending to model
    SPEAKING = "speaking"         # TTS playing response
    MUTED = "muted"               # Explicitly muted

@dataclass
class VoiceConfig:
    wake_words: List[str] = field(default_factory=lambda: ["Hey ARISE", "Computer"])
    wake_word_sensitivity: float = 0.5
    vad_sensitivity: str = "medium"  # low, medium, high
    vad_silence_ms: int = 500
    asr_language: str = "auto"       # auto, en, te, code-switch
    tts_voice: str = "default"
    tts_speed: float = 1.0
    gemini_live_model: str = "gemini-3.8-live"
    enable_barge_in: bool = True
    session_resumption: bool = True

class VoicePipeline:
    """
    Complete voice pipeline: Wake Word -> VAD/ASR -> Gemini Live -> TTS
    Manages state, audio routing, barge-in, session persistence.
    """
    
    def __init__(self, runtime: "AppRuntime", config: VoiceConfig):
        self.runtime = runtime
        self.config = config
        self.state = VoiceState.DORMANT
        
        # Components
        self.wake_detector = WakeWordDetector(config.wake_words, config.wake_word_sensitivity)
        self.vad_asr = SherpaVADASR(config.vad_sensitivity, config.vad_silence_ms, config.asr_language)
        self.gemini_live = GeminiLiveClient(config.gemini_live_model)
        self.tts = TTSFallback()  # ElevenLabs + OpenAI fallback
        
        # Audio routing
        self.audio_input: Optional[asyncio.Queue] = None  # Raw audio chunks
        self.audio_output: Optional[asyncio.Queue] = None  # TTS audio chunks
        self.playback_task: Optional[asyncio.Task] = None
        
        # Session management
        self.session_id: Optional[str] = None
        self.resumption_token: Optional[str] = None
        self.conversation_history: List[Dict] = []
        
        # Callbacks
        self.on_state_change: Optional[Callable[[VoiceState], None]] = None
        self.on_transcript: Optional[Callable[[str, bool], None]] = None  # text, is_final
        self.on_response: Optional[Callable[[str], None]] = None
    
    async def start(self):
        """Start the pipeline (enters DORMANT -> wake word detection)"""
        await self.wake_detector.start(self._on_wake_detected)
        self._set_state(VoiceState.DORMANT)
    
    async def stop(self):
        """Stop everything"""
        await self.wake_detector.stop()
        await self.vad_asr.stop()
        await self.gemini_live.disconnect()
        if self.playback_task:
            self.playback_task.cancel()
        self._set_state(VoiceState.DORMANT)
    
    async def mute(self):
        """Immediate mute"""
        await self.vad_asr.stop()
        await self.gemini_live.disconnect()
        if self.playback_task:
            self.playback_task.cancel()
        self._set_state(VoiceState.MUTED)
    
    async def unmute(self):
        """Unmute -> back to dormant"""
        await self.start()
    
    def _set_state(self, new_state: VoiceState):
        old = self.state
        self.state = new_state
        if self.on_state_change:
            self.on_state_change(new_state)
        self.runtime.events.emit("voice.state_changed", {"from": old.value, "to": new_state.value})
    
    async def _on_wake_detected(self, wake_word: str):
        """Callback when wake word detected"""
        self._set_state(VoiceState.DETECTING)
        
        # Start VAD/ASR
        await self.vad_asr.start(self._on_speech_start, self._on_speech_end, self._on_transcript)
        self._set_state(VoiceState.LISTENING)
    
    async def _on_speech_start(self):
        """User started speaking"""
        pass  # Visual feedback
    
    async def _on_speech_end(self):
        """User stopped speaking - ASR final result ready"""
        self._set_state(VoiceState.PROCESSING)
    
    async def _on_transcript(self, text: str, is_final: bool):
        """Incremental or final transcript"""
        if self.on_transcript:
            self.on_transcript(text, is_final)
        
        if is_final and text.strip():
            # Send to Gemini Live
            await self._send_to_gemini(text)
    
    async def _send_to_gemini(self, text: str):
        """Send user transcript to Gemini Live, handle response"""
        try:
            # Ensure connection
            if not self.gemini_live.connected:
                await self.gemini_live.connect(
                    session_id=self.session_id,
                    resumption_token=self.resumption_token,
                    on_audio=self._on_gemini_audio,
                    on_interrupted=self._on_gemini_interrupted,
                    on_tool_call=self._on_gemini_tool_call,
                )
                self.session_id = self.gemini_live.session_id
                self.resumption_token = self.gemini_live.resumption_token
            
            # Send text (Gemini Live accepts text input too)
            await self.gemini_live.send_text(text)
            
            # Add to history
            self.conversation_history.append({"role": "user", "content": text})
            
        except Exception as e:
            logger.error(f"Gemini Live error: {e}")
            # Fallback to TTS-only response
            await self._fallback_response(text)
    
    async def _on_gemini_audio(self, audio_chunk: bytes):
        """Receive audio from Gemini Live, queue for playback"""
        if self.state == VoiceState.PROCESSING:
            self._set_state(VoiceState.SPEAKING)
        await self.audio_output.put(audio_chunk)
        
        # Start playback if not running
        if not self.playback_task or self.playback_task.done():
            self.playback_task = asyncio.create_task(self._playback_loop())
    
    async def _on_gemini_interrupted(self):
        """Gemini detected user interruption (barge-in)"""
        if self.config.enable_barge_in:
            # Clear playback queue immediately
            while not self.audio_output.empty():
                try:
                    self.audio_output.get_nowait()
                except asyncio.QueueEmpty:
                    break
            # Stop current playback
            if self.playback_task:
                self.playback_task.cancel()
            # Restart VAD/ASR for new input
            await self.vad_asr.restart()
            self._set_state(VoiceState.LISTENING)
    
    async def _on_gemini_tool_call(self, tool_call: Dict):
        """Gemini requested tool execution"""
        # Execute via ARISE task engine
        result = await self.runtime.task_engine.execute_tool(
            tool_call["name"],
            tool_call["arguments"],
        )
        # Return result to Gemini
        await self.gemini_live.send_tool_result(tool_call["id"], result)
    
    async def _playback_loop(self):
        """Play queued audio chunks via Tauri audio commands"""
        try:
            # Start playback stream on Tauri side
            await self.runtime.tauri_commands.audio_start_playback()
            
            while True:
                chunk = await self.audio_output.get()
                if chunk is None:  # Sentinel
                    break
                await self.runtime.tauri_commands.audio_write_chunk(chunk)
            
            await self.runtime.tauri_commands.audio_stop_playback()
            self._set_state(VoiceState.DORMANT)  # Back to wake word
            
        except asyncio.CancelledError:
            await self.runtime.tauri_commands.audio_stop_playback()
            raise
        except Exception as e:
            logger.error(f"Playback error: {e}")
            await self.runtime.tauri_commands.audio_stop_playback()
    
    async def _fallback_response(self, user_text: str):
        """Fallback when Gemini Live unavailable"""
        # Use regular model + TTS
        response = await self.runtime.model_router.complete(
            "voice_conversation",
            CompletionRequest(messages=[
                {"role": "system", "content": "You are ARISE, a helpful voice assistant. Keep responses concise."},
                {"role": "user", "content": user_text},
            ])
        )
        await self._speak(response.content)
    
    async def _speak(self, text: str):
        """Speak text via TTS fallback"""
        audio_stream = await self.tts.synthesize_stream(text, self.config.tts_voice)
        self._set_state(VoiceState.SPEAKING)
        async for chunk in audio_stream:
            await self.audio_output.put(chunk)
        if not self.playback_task or self.playback_task.done():
            self.playback_task = asyncio.create_task(self._playback_loop())
```

### 6.2 Wake Word Detector (Porcupine)

```python
# src/arise/voice/wake_word.py
import pvporcupine
from pvrecorder import PvRecorder
from typing import Callable, List
import asyncio

class WakeWordDetector:
    """Always-on wake word detection using Porcupine"""
    
    def __init__(
        self,
        wake_words: List[str],
        sensitivity: float = 0.5,
        access_key: str = None,  # From Picovoice console
    ):
        self.wake_words = wake_words
        self.sensitivity = sensitivity
        self.access_key = access_key
        self.porcupine = None
        self.recorder = None
        self.callback: Callable[[str], None] = None
        self._running = False
        self._task: asyncio.Task = None
    
    async def start(self, callback: Callable[[str], None]):
        self.callback = callback
        
        # Initialize Porcupine with built-in keywords or custom
        keyword_paths = []
        for word in self.wake_words:
            if word.lower() in ["hey arise", "computer", "jarvis", "alexa"]:
                # Use built-in
                keyword_paths.append(word.lower().replace(" ", "_"))
            else:
                # Custom .ppn file needed
                keyword_paths.append(f"models/{word}.ppn")
        
        self.porcupine = pvporcupine.create(
            access_key=self.access_key,
            keyword_paths=keyword_paths,
            sensitivities=[self.sensitivity] * len(keyword_paths),
        )
        
        # Audio recorder (matches Porcupine frame length)
        self.recorder = PvRecorder(
            device_index=-1,  # Default
            frame_length=self.porcupine.frame_length,
        )
        
        self._running = True
        self._task = asyncio.create_task(self._detection_loop())
    
    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self.recorder:
            self.recorder.delete()
        if self.porcupine:
            self.porcupine.delete()
    
    async def _detection_loop(self):
        self.recorder.start()
        while self._running:
            try:
                pcm = self.recorder.read()
                keyword_index = self.porcupine.process(pcm)
                if keyword_index >= 0:
                    wake_word = self.wake_words[keyword_index]
                    if self.callback:
                        await self.callback(wake_word)
            except Exception as e:
                logger.error(f"Wake word detection error: {e}")
                await asyncio.sleep(0.1)
        self.recorder.stop()
```

### 6.3 Sherpa-ONNX VAD + ASR

```python
# src/arise/voice/vad_asr.py
import sherpa_onnx
from typing import Callable, Optional
import asyncio
import numpy as np

class SherpaVADASR:
    """Unified VAD + Streaming ASR using Sherpa-ONNX"""
    
    def __init__(
        self,
        vad_sensitivity: str = "medium",  # low, medium, high
        silence_ms: int = 500,
        language: str = "auto",
    ):
        self.vad_sensitivity = vad_sensitivity
        self.silence_ms = silence_ms
        self.language = language
        
        self.recognizer = None
        self.callback_speech_start: Callable = None
        self.callback_speech_end: Callable = None
        self.callback_transcript: Callable[[str, bool], None] = None
        
        self._running = False
        self._task: asyncio.Task = None
        self._audio_queue: asyncio.Queue = asyncio.Queue()
    
    async def start(
        self,
        on_speech_start: Callable,
        on_speech_end: Callable,
        on_transcript: Callable[[str, bool], None],
    ):
        self.callback_speech_start = on_speech_start
        self.callback_speech_end = on_speech_end
        self.callback_transcript = on_transcript
        
        # Configure Sherpa-ONNX
        vad_config = sherpa_onnx.VadConfig(
            threshold=0.5 if vad_sensitivity == "medium" else (0.3 if vad_sensitivity == "low" else 0.7),
            min_speech_duration=0.1,
            min_silence_duration=self.silence_ms / 1000,
            window_size=512,
        )
        
        # Use streaming transducer model (supports English + Telugu)
        self.recognizer = sherpa_onnx.OnlineRecognizer(
            tokens="models/sherpa/tokens.txt",
            encoder="models/sherpa/encoder-ep20.onnx",
            decoder="models/sherpa/decoder-ep20.onnx",
            joiner="models/sherpa/joiner-ep20.onnx",
            num_threads=2,
            sample_rate=16000,
            feature_dim=80,
            decoding_method="greedy_search",
            vad_config=vad_config,
            enable_endpoint_detection=True,
            rule1_min_trailing_silence=2.4,
            rule2_min_trailing_silence=1.2,
            rule3_min_utterance_length=300,
        )
        
        self._running = True
        self._task = asyncio.create_task(self._recognition_loop())
    
    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
    
    async def push_audio(self, pcm_bytes: bytes):
        """Push raw PCM audio from capture"""
        await self._audio_queue.put(pcm_bytes)
    
    async def _recognition_loop(self):
        stream = self.recognizer.create_stream()
        last_speech_start = False
        
        while self._running:
            try:
                pcm_bytes = await asyncio.wait_for(self._audio_queue.get(), timeout=0.1)
                # Convert to float32 samples
                samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
                
                # Process chunk
                stream.accept_waveform(16000, samples)
                
                # Check for endpoint detection
                while self.recognizer.is_ready(stream):
                    self.recognizer.decode_stream(stream)
                
                # Get transcript
                result = stream.result
                if result.text:
                    is_final = stream.is_endpoint
                    if self.callback_transcript:
                        await self.callback_transcript(result.text, is_final)
                    
                    # Detect speech start/end
                    if result.text and not last_speech_start:
                        last_speech_start = True
                        if self.callback_speech_start:
                            await self.callback_speech_start()
                    
                    if is_final:
                        last_speech_start = False
                        if self.callback_speech_end:
                            await self.callback_speech_end()
                        # Reset stream for next utterance
                        stream = self.recognizer.create_stream()
                        
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"ASR error: {e}")
                await asyncio.sleep(0.1)
    
    async def restart(self):
        """Restart for barge-in"""
        await self.stop()
        await self.start(
            self.callback_speech_start,
            self.callback_speech_end,
            self.callback_transcript,
        )
```

---

## 7. Adapters (`src/arise/adapters/`)

### 7.1 Adapter Protocol

```python
# src/arise/core/ports.py
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

@dataclass
class AdapterCapability:
    name: str
    description: str
    risk_level: str  # R0-R4
    required_permissions: List[str]
    supports_async: bool = True
    estimated_latency_ms: int = 1000

class AdapterPort(ABC):
    """Base protocol for all adapters"""
    
    @property
    @abstractmethod
    def name(self) -> str: ...
    
    @property
    @abstractmethod
    def capabilities(self) -> List[AdapterCapability]: ...
    
    @abstractmethod
    async def health_check(self) -> bool: ...
    
    @abstractmethod
    async def close(self): ...

class DesktopAdapterPort(AdapterPort):
    """Windows desktop automation"""
    
    @abstractmethod
    async def launch_app(self, app_name: str, args: List[str] = None) -> Dict: ...
    
    @abstractmethod
    async def find_window(self, title: str, class_name: str = None) -> Dict: ...
    
    @abstractmethod
    async def click_element(self, selector: Dict) -> Dict: ...
    
    @abstractmethod
    async def type_text(self, selector: Dict, text: str) -> Dict: ...
    
    @abstractmethod
    async def get_window_state(self, window_id: str) -> Dict: ...
    
    @abstractmethod
    async def list_windows(self) -> List[Dict]: ...

class BrowserAdapterPort(AdapterPort):
    """Browser automation via Playwright"""
    
    @abstractmethod
    async def attach_to_profile(self, browser: str, profile_path: str) -> Dict: ...
    
    @abstractmethod
    async def navigate(self, url: str, wait_until: str = "networkidle") -> Dict: ...
    
    @abstractmethod
    async def click(self, selector: str) -> Dict: ...
    
    @abstractmethod
    async def type(self, selector: str, text: str) -> Dict: ...
    
    @abstractmethod
    async def extract(self, selector: str, attribute: str = "text") -> Dict: ...
    
    @abstractmethod
    async def screenshot(self, full_page: bool = False) -> bytes: ...
    
    @abstractmethod
    async def evaluate(self, script: str) -> Any: ...
    
    @abstractmethod
    async def get_console_logs(self) -> List[Dict]: ...
    
    @abstractmethod
    async def get_network_logs(self) -> List[Dict]: ...
```

### 7.2 Windows UIA Adapter (Hybrid)

```python
# src/arise/adapters/windows_uia.py
import uiautomation as auto
import pywinauto
from pywinauto import Desktop, Application
from .ports import DesktopAdapterPort, AdapterCapability
from typing import Dict, List, Any
import asyncio
import threading

class WindowsUIAAdapter(DesktopAdapterPort):
    """Hybrid UIA adapter: uiautomation-new (low-level) + pywinauto (high-level)"""
    
    name = "windows_uia"
    
    def __init__(self):
        self._uia_initialized = False
        self._lock = threading.Lock()
    
    @property
    def capabilities(self) -> List[AdapterCapability]:
        return [
            AdapterCapability("launch_app", "Launch Windows application", "R1", ["system.launch"]),
            AdapterCapability("find_window", "Find window by title/class", "R0", ["ui.read"]),
            AdapterCapability("click_element", "Click UI element", "R1", ["ui.click"]),
            AdapterCapability("type_text", "Type text into element", "R1", ["ui.type"]),
            AdapterCapability("get_window_state", "Get window state/position", "R0", ["ui.read"]),
            AdapterCapability("list_windows", "List all top-level windows", "R0", ["ui.read"]),
            AdapterCapability("get_element_tree", "Get full UIA tree", "R0", ["ui.read"]),
            AdapterCapability("wait_for_element", "Wait for element to appear", "R0", ["ui.read"]),
        ]
    
    def _ensure_uia_init(self):
        """Initialize UIA for current thread (thread-safe)"""
        with self._lock:
            if not self._uia_initialized:
                auto.InitializeUIAutomationInCurrentThread()
                self._uia_initialized = True
    
    async def health_check(self) -> bool:
        try:
            self._ensure_uia_init()
            # Try to get desktop root
            root = auto.GetRootControl()
            return root is not None
        except Exception:
            return False
    
    async def close(self):
        if self._uia_initialized:
            auto.UninitializeUIAutomationInCurrentThread()
            self._uia_initialized = False
    
    async def launch_app(self, app_name: str, args: List[str] = None) -> Dict:
        """Launch app using pywinauto (handles process management)"""
        self._ensure_uia_init()
        
        # Map common names to executables
        exe_map = {
            "chrome": "chrome.exe",
            "edge": "msedge.exe",
            "firefox": "firefox.exe",
            "notepad": "notepad.exe",
            "explorer": "explorer.exe",
            "cmd": "cmd.exe",
            "powershell": "powershell.exe",
            "vscode": "code.exe",
        }
        
        exe = exe_map.get(app_name.lower(), app_name)
        cmd = [exe] + (args or [])
        
        app = Application(backend="uia").start(" ".join(cmd))
        
        # Wait for main window
        try:
            main_window = app.window()
            main_window.wait("visible", timeout=10)
            return {
                "success": True,
                "process_id": app.process,
                "window_handle": main_window.handle,
                "title": main_window.window_text(),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def find_window(self, title: str, class_name: str = None) -> Dict:
        """Find window using uiautomation (more precise)"""
        self._ensure_uia_init()
        
        # Search by name
        window = auto.WindowControl(Name=title, searchDepth=1)
        if not window.Exists(0):
            # Try partial match
            desktop = auto.GetRootControl()
            for win in desktop.GetChildren():
                if win.ControlType == auto.ControlType.WindowControl:
                    if title.lower() in win.Name.lower():
                        window = win
                        break
        
        if window.Exists(0):
            return {
                "found": True,
                "handle": window.NativeWindowHandle,
                "title": window.Name,
                "class_name": window.ClassName,
                "rect": {"left": window.BoundingRectangle.left, "top": window.BoundingRectangle.top,
                         "right": window.BoundingRectangle.right, "bottom": window.BoundingRectangle.bottom},
                "process_id": window.ProcessId,
            }
        return {"found": False}
    
    async def click_element(self, selector: Dict) -> Dict:
        """Click element using uiautomation patterns"""
        self._ensure_uia_init()
        
        # Resolve element from selector
        element = await self._resolve_element(selector)
        if not element:
            return {"success": False, "error": "Element not found"}
        
        # Try InvokePattern (click)
        try:
            invoke = element.GetInvokePattern()
            invoke.Invoke()
            return {"success": True}
        except Exception:
            # Fallback: LegacyIAccessiblePattern or click via mouse
            try:
                rect = element.BoundingRectangle
                import pyautogui
                pyautogui.click(rect.left + rect.width() // 2, rect.top + rect.height() // 2)
                return {"success": True}
            except Exception as e:
                return {"success": False, "error": str(e)}
    
    async def type_text(self, selector: Dict, text: str) -> Dict:
        """Type text into element"""
        self._ensure_uia_init()
        
        element = await self._resolve_element(selector)
        if not element:
            return {"success": False, "error": "Element not found"}
        
        try:
            # Focus first
            element.SetFocus()
            
            # Try ValuePattern (set text directly)
            try:
                value_pattern = element.GetValuePattern()
                value_pattern.SetValue(text)
                return {"success": True}
            except Exception:
                # Fallback: SendKeys via pyautogui
                import pyautogui
                pyautogui.write(text, interval=0.01)
                return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def get_window_state(self, window_id: str) -> Dict:
        """Get window state (position, size, visibility)"""
        self._ensure_uia_init()
        
        window = auto.ControlFromHandle(int(window_id))
        if not window or not window.Exists(0):
            return {"found": False}
        
        rect = window.BoundingRectangle
        return {
            "found": True,
            "title": window.Name,
            "visible": window.IsVisible,
            "enabled": window.IsEnabled,
            "focused": window.HasFocus,
            "rect": {"left": rect.left, "top": rect.top, "right": rect.right, "bottom": rect.bottom},
            "state": "maximized" if window.IsMaximized else "minimized" if window.IsMinimized else "normal",
        }
    
    async def list_windows(self) -> List[Dict]:
        """List all top-level windows"""
        self._ensure_uia_init()
        
        desktop = auto.GetRootControl()
        windows = []
        for win in desktop.GetChildren():
            if win.ControlType == auto.ControlType.WindowControl:
                rect = win.BoundingRectangle
                windows.append({
                    "handle": win.NativeWindowHandle,
                    "title": win.Name,
                    "class_name": win.ClassName,
                    "process_id": win.ProcessId,
                    "visible": win.IsVisible,
                    "rect": {"left": rect.left, "top": rect.top, "right": rect.right, "bottom": rect.bottom},
                })
        return windows
    
    async def _resolve_element(self, selector: Dict) -> Any:
        """Resolve UIA element from selector dict"""
        # Selector can contain: name, automation_id, class_name, control_type, depth, parent
        search_props = {}
        if "name" in selector:
            search_props["Name"] = selector["name"]
        if "automation_id" in selector:
            search_props["AutomationId"] = selector["automation_id"]
        if "class_name" in selector:
            search_props["ClassName"] = selector["class_name"]
        if "control_type" in selector:
            search_props["ControlType"] = getattr(auto.ControlType, selector["control_type"])
        
        # Start from root or parent
        if "parent" in selector:
            parent = auto.ControlFromHandle(int(selector["parent"]))
        else:
            parent = auto.GetRootControl()
        
        # Search
        element = parent.FindFirst(**search_props)
        if element and element.Exists(0):
            return element
        return None
```

### 7.3 Playwright Browser Adapter

```python
# src/arise/adapters/browser_playwright.py
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from .ports import BrowserAdapterPort, AdapterCapability
from typing import Dict, List, Any, Optional
import asyncio

class PlaywrightBrowserAdapter(BrowserAdapterPort):
    """Browser automation via Playwright with CDP attach to existing profiles"""
    
    name = "playwright"
    
    def __init__(self):
        self.playwright = None
        self.browsers: Dict[str, Browser] = {}
        self.contexts: Dict[str, BrowserContext] = {}
        self.pages: Dict[str, Page] = {}
    
    @property
    def capabilities(self) -> List[AdapterCapability]:
        return [
            AdapterCapability("attach_to_profile", "Attach to existing browser profile", "R1", ["browser.attach"]),
            AdapterCapability("navigate", "Navigate to URL", "R1", ["browser.navigate"]),
            AdapterCapability("click", "Click element", "R1", ["browser.click"]),
            AdapterCapability("type", "Type text", "R1", ["browser.type"]),
            AdapterCapability("extract", "Extract content", "R0", ["browser.read"]),
            AdapterCapability("screenshot", "Take screenshot", "R0", ["browser.read"]),
            AdapterCapability("evaluate", "Execute JavaScript", "R1", ["browser.script"]),
            AdapterCapability("get_console_logs", "Get console logs", "R0", ["browser.read"]),
            AdapterCapability("get_network_logs", "Get network logs", "R0", ["browser.read"]),
            AdapterCapability("wait_for_selector", "Wait for element", "R0", ["browser.read"]),
            AdapterCapability("trace_start", "Start trace recording", "R0", ["browser.trace"]),
            AdapterCapability("trace_stop", "Stop trace recording", "R0", ["browser.trace"]),
        ]
    
    async def health_check(self) -> bool:
        try:
            if not self.playwright:
                self.playwright = await async_playwright().start()
            # Quick test
            browser = await self.playwright.chromium.launch(headless=True)
            await browser.close()
            return True
        except Exception:
            return False
    
    async def close(self):
        for context in self.contexts.values():
            await context.close()
        for browser in self.browsers.values():
            await browser.close()
        if self.playwright:
            await self.playwright.stop()
    
    async def attach_to_profile(
        self,
        browser: str = "chromium",  # chromium, firefox, webkit
        profile_path: str = None,
        channel: str = None,  # "msedge", "chrome"
        headless: bool = False,
        context_id: str = "default",
    ) -> Dict:
        """Attach to existing browser profile via CDP"""
        
        if context_id in self.contexts:
            return {"success": True, "context_id": context_id, "reused": True}
        
        # Launch browser with persistent context
        pw = self.playwright or await async_playwright().start()
        self.playwright = pw
        
        launch_args = {
            "headless": headless,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--force-renderer-accessibility",
            ],
        }
        
        if channel:
            launch_args["channel"] = channel
        
        if profile_path:
            # Use persistent context for profile
            context = await pw[browser].launch_persistent_context(
                user_data_dir=profile_path,
                **launch_args,
            )
        else:
            # Temporary context
            browser_instance = await pw[browser].launch(**launch_args)
            context = await browser_instance.new_context()
            self.browsers[context_id] = browser_instance
        
        self.contexts[context_id] = context
        
        # Enable tracing for evidence
        await context.tracing.start(screenshots=True, snapshots=True, sources=True)
        
        return {
            "success": True,
            "context_id": context_id,
            "browser": browser,
            "pages": len(context.pages),
        }
    
    async def navigate(
        self,
        url: str,
        wait_until: str = "networkidle",
        timeout: int = 30000,
        context_id: str = "default",
    ) -> Dict:
        context = self.contexts.get(context_id)
        if not context:
            return {"success": False, "error": "Context not found"}
        
        page = context.pages[0] if context.pages else await context.new_page()
        self.pages[context_id] = page
        
        try:
            response = await page.goto(url, wait_until=wait_until, timeout=timeout)
            return {
                "success": True,
                "url": page.url,
                "title": await page.title(),
                "status": response.status if response else None,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def click(self, selector: str, context_id: str = "default") -> Dict:
        page = self.pages.get(context_id)
        if not page:
            return {"success": False, "error": "No active page"}
        
        try:
            await page.click(selector, timeout=10000)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def type(self, selector: str, text: str, context_id: str = "default") -> Dict:
        page = self.pages.get(context_id)
        if not page:
            return {"success": False, "error": "No active page"}
        
        try:
            await page.fill(selector, text, timeout=10000)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def extract(self, selector: str, attribute: str = "text", context_id: str = "default") -> Dict:
        page = self.pages.get(context_id)
        if not page:
            return {"success": False, "error": "No active page"}
        
        try:
            element = await page.wait_for_selector(selector, timeout=5000)
            if attribute == "text":
                value = await element.text_content()
            elif attribute == "html":
                value = await element.inner_html()
            else:
                value = await element.get_attribute(attribute)
            return {"success": True, "value": value}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def screenshot(self, full_page: bool = False, context_id: str = "default") -> bytes:
        page = self.pages.get(context_id)
        if not page:
            raise ValueError("No active page")
        
        return await page.screenshot(full_page=full_page, type="png")
    
    async def evaluate(self, script: str, context_id: str = "default") -> Any:
        page = self.pages.get(context_id)
        if not page:
            raise ValueError("No active page")
        
        return await page.evaluate(script)
    
    async def get_console_logs(self, context_id: str = "default") -> List[Dict]:
        page = self.pages.get(context_id)
        if not page:
            return []
        # Console messages captured via page.on("console")
        return page._console_messages  # Internal, would need proper collection
    
    async def get_network_logs(self, context_id: str = "default") -> List[Dict]:
        page = self.pages.get(context_id)
        if not page:
            return []
        # Network events captured via page.on("request"/"response")
        return page._network_logs  # Internal
    
    async def trace_start(self, context_id: str = "default"):
        context = self.contexts.get(context_id)
        if context:
            await context.tracing.start(screenshots=True, snapshots=True, sources=True)
    
    async def trace_stop(self, path: str, context_id: str = "default") -> Dict:
        context = self.contexts.get(context_id)
        if not context:
            return {"success": False, "error": "Context not found"}
        
        await context.tracing.stop(path=path)
        return {"success": True, "trace_path": path}
```

---

## 8. Configuration & Settings

```python
# src/arise/config/settings.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, SecretStr
from pathlib import Path
from typing import Optional, List, Dict, Any
import json

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )
    
    # Core
    app_name: str = "ARISE"
    environment: str = "development"  # development, staging, production
    data_dir: Path = Field(
        default_factory=lambda: Path.home() / "AppData" / "Local" / "ARISE"
    )
    log_level: str = "INFO"
    
    # Network
    api_host: str = "127.0.0.1"
    api_port: int = 8765
    websocket_path: str = "/ws"
    
    # Model Providers (API keys stored in Credential Manager, not here)
    gemini_api_key: Optional[SecretStr] = None
    openai_api_key: Optional[SecretStr] = None
    anthropic_api_key: Optional[SecretStr] = None
    elevenlabs_api_key: Optional[SecretStr] = None
    nvidia_nim_api_key: Optional[SecretStr] = None
    
    # Voice
    porcupine_access_key: Optional[SecretStr] = None
    wake_words: List[str] = Field(default_factory=lambda: ["Hey ARISE", "Computer"])
    vad_sensitivity: str = "medium"
    asr_language: str = "auto"
    tts_provider: str = "elevenlabs"  # elevenlabs, openai, local
    tts_voice: str = "default"
    
    # Memory
    chroma_persist_dir: Optional[Path] = None
    memory_consolidation_interval_hours: int = 6
    working_memory_ttl_hours: int = 24
    
    # Task Engine
    max_concurrent_tasks: int = 4
    default_task_timeout_seconds: int = 300
    checkpoint_interval_steps: int = 1
    
    # Policy
    policy_rules: List[Dict[str, Any]] = Field(default_factory=list)
    default_risk_level: str = "R1"
    
    # Scheduler
    scheduler_timezone: str = "Asia/Calcutta"
    
    # Backups
    backup_enabled: bool = True
    backup_interval_hours: int = 24
    backup_retention_days: int = 30
    backup_dir: Optional[Path] = None
    
    # Updates
    auto_update_check: bool = True
    update_channel: str = "stable"  # stable, beta, alpha
    
    # UI
    theme: str = "system"  # light, dark, system
    floating_companion_enabled: bool = True
    global_shortcut: str = "Alt+A"
    
    def get_data_dir(self) -> Path:
        """Ensure data directory exists"""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "memory").mkdir(exist_ok=True)
        (self.data_dir / "checkpoints").mkdir(exist_ok=True)
        (self.data_dir / "artifacts").mkdir(exist_ok=True)
        (self.data_dir / "logs").mkdir(exist_ok=True)
        (self.data_dir / "backups").mkdir(exist_ok=True)
        return self.data_dir
```

---

## 9. Testing Strategy per Component

| Component | Unit Tests | Integration Tests | Contract Tests | E2E Tests |
|-----------|------------|-------------------|----------------|-----------|
| **Task Engine** | State machine, transitions, checkpoint serialization | Full task lifecycle, pause/resume, recovery | Task API schema, WebSocket events | Voice → task → completion |
| **Policy Engine** | Risk assessment, grant matching, condition evaluation | Approval flow, capability checks | Approval API, grant CRUD | R0-R4 scenarios |
| **Model Router** | Circuit breaker, fallback logic, cost estimation | Multi-provider failover, streaming | Provider interfaces | Task-type routing |
| **Coordinator** | Decomposition, graph building, integration | Multi-agent delegation, verification | Agent protocols | Complex project task |
| **Memory** | Store CRUD, retrieval, consolidation logic | Cross-kind queries, promotion | Memory API | Long-term retention |
| **Voice** | State machine, barge-in, session resumption | Pipeline integration, fallback | Voice API, audio format | Wake → speak → verify |
| **UIA Adapter** | Element resolution, pattern invocation | App launch, window management | Adapter protocol | Real Windows apps |
| **Playwright** | Selector resolution, CDP attach | Navigation, extraction, trace | Adapter protocol | Real websites |
| **Persistence** | Checkpoint save/load, WAL integrity | SQLite + ChromaDB transactions | Schema migrations | Crash recovery |

---

## 10. Open Component Decisions

| Component | Decision | Options | Blocker |
|-----------|----------|---------|---------|
| Task Queue | Persistence backend | SQLite WAL vs Redis vs Custom | Concurrency + durability |
| Agent Comm | Transport protocol | In-process channels vs gRPC vs NATS | Debugging vs distribution |
| Memory Consol | Scheduler | APScheduler cron vs event-driven | Resource spikes |
| Evidence | Storage format | JSONL+SQLite vs Parquet vs Custom | Query patterns |
| Plugin Sandbox | Isolation | wasmtime vs subprocess vs in-process | WASI maturity |
| Audio Transport | Real-time path | cpal→Tauri→WebAudio vs WebRTC | Browser compatibility |
| Multi-Agent Sync | Consistency model | Event sourcing vs CRDT vs Coordinator | Audit requirements |