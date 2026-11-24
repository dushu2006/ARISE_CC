# ARISE — Multi-Agent System Design

## Overview

This document specifies the multi-agent architecture for ARISE, featuring a Central Coordinator that decomposes complex objectives, delegates to 11 specialist agents, and performs independent verification. The system follows the principle: **Model proposes what. Policy and verified capabilities decide how.**

---

## 1. Agent Architecture Principles

| Principle | Implementation |
|-----------|----------------|
| **Centralized Coordination** | Single Coordinator understands, plans, delegates, verifies |
| **Specialist Isolation** | Each agent has scoped permissions, isolated context, independent lifecycle |
| **Explicit Delegation** | Coordinator creates sub-tasks with explicit objectives and capability grants |
| **Independent Verification** | Coordinator verifies results separately from agent self-validation |
| **Audit Trail** | Every delegation produces evidence bundle linked to parent task |
| **Failure Containment** | Agent failures don't cascade; Coordinator handles compensation |
| **Capability Scoping** | Agents receive only capabilities needed for their sub-task |

---

## 2. Agent Ecosystem

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           AGENT ECOSYSTEM MAP                                │
└─────────────────────────────────────────────────────────────────────────────┘

                              ┌─────────────────────┐
                              │  CENTRAL COORDINATOR │
                              │  (Orchestrator)      │
                              └──────────┬──────────┘
                                         │
         ┌───────────────┬───────────────┼───────────────┬───────────────┐
         ▼               ▼               ▼               ▼               ▼
┌─────────────────┐ ┌──────────────┐ ┌────────────┐ ┌─────────────┐ ┌──────────────┐
│    RESEARCH     │ │    CODING    │ │  BROWSER   │ │  FILESYSTEM │ │   SYSTEM     │
│    AGENT        │ │    AGENT     │ │   AGENT    │ │   AGENT     │ │   AGENT      │
│  - Deep search  │ │  - Read code │ │ - Navigate │ │ - Read/Write│ │ - Processes  │
│  - Verify srcs  │ │  - Write code│ │ - Extract  │ │ - Search    │ │ - Services   │
│  - Synthesize   │ │  - Run tests │ │ - Screenshot│ │ - Watch     │ │ - Registry   │
└─────────────────┘ └──────────────┘ └────────────┘ └─────────────┘ └──────────────┘

         ▲               ▲               ▲               ▲               ▲
         │               │               │               │               │
         │  ┌────────────┴───────────────┴───────────────┴─────────────┐ │
         │  │                    COORDINATOR DELEGATES TO               │ │
         │  └─────────────────────────────────────────────────────────┘ │
         │                                                                │
         ▼                                                                ▼
┌─────────────────┐ ┌──────────────┐ ┌────────────┐ ┌─────────────┐ ┌──────────────┐
│  COMMUNICATIONS │ │   CREATIVE   │ │  MEMORY    │ │  PROJECTS   │ │ DESKTOP UI   │
│    AGENT        │ │    AGENT     │ │   AGENT    │ │   AGENT     │ │    AGENT     │
│ - Email/SMS     │ │ - Image gen  │ │ - Store    │ │ - Plan      │ │ - Click/Type │
│ - Calendar      │ │ - Video gen  │ │ - Retrieve │ │ - Track     │ │ - Window mgmt│
│ - Notifications │ │ - Audio gen  │ │ - Consolidate│ │ - Milestones│ │ - App launch │
└─────────────────┘ └──────────────┘ └────────────┘ └─────────────┘ └──────────────┘
```

---

## 3. Central Coordinator

### 3.1 Responsibilities

```python
class CentralCoordinator:
    """
    Central Coordinator - The "brain" of multi-agent operations.
    
    Responsibilities:
    1. UNDERSTAND: Parse objective, classify intent, identify complexity
    2. DECOMPOSE: Break into sub-tasks with dependencies
    3. DELEGATE: Assign to specialist agents with scoped permissions
    4. MONITOR: Track progress, handle timeouts, manage retries
    5. INTEGRATE: Combine agent outputs into coherent result
    6. VERIFY: Independent verification of completion criteria
    7. COMPENSATE: Handle failures with rollback/alternative strategies
    """
    
    def __init__(self, runtime: "AppRuntime"):
        self.runtime = runtime
        self.agent_registry = runtime.agent_registry
        self.active_orchestrations: Dict[str, Orchestration] = {}
        self.delegation_history: List[DelegationRecord] = []
```

### 3.2 Orchestration Flow

```
ORCHESTRATION LIFECYCLE
───────────────────────

1. RECEIVE OBJECTIVE
   ├─ Input: Natural language objective + context
   ├─ Output: Structured understanding (intent, entities, constraints)

2. DECOMPOSE
   ├─ Use Model Router (complex_reasoning)
   ├─ Output: DAG of sub-tasks with:
   │    - Role assignment
   │    - Explicit prompt/instructions
   │    - Required capabilities
   │    - Dependencies (DAG edges)
   │    - Success criteria
   │    - Timeout estimates
   └─ Validation: All roles exist, capabilities available

3. PLAN EXECUTION
   ├─ Topological sort of DAG
   ├─ Identify parallelizable groups
   ├─ Resource allocation (concurrency limits)
   └─ Create Orchestration object

4. EXECUTE (with dependency resolution)
   ├─ For each ready node:
   │    ├─ Create AgentContext (scoped permissions)
   │    ├─ Delegate to agent
   │    ├─ Monitor with timeout
   │    ├─ Collect result + evidence
   │    └─ Handle failures (retry/compensate)
   └─ Wait for all nodes

5. INTEGRATE
   ├─ Collect all agent outputs
   ├─ Resolve conflicts/overlaps
   ├─ Synthesize final deliverable
   └─ Generate summary

6. VERIFY (INDEPENDENT)
   ├─ For each success criterion:
   │    ├─ Check evidence exists
   │    ├─ Validate against criteria
   │    └─ Cross-reference agent outputs
   ├─ Overall: PASS / PARTIAL / FAIL
   └─ If FAIL → Compensation or escalate

7. COMPLETE
   ├─ Create EvidenceBundle for parent task
   ├─ Store in Memory (EPISODIC + SEMANTIC)
   ├─ Emit task.completed event
   └─ Cleanup orchestration state
```

### 3.3 Decomposition Algorithm

```python
async def decompose_objective(
    self,
    objective: str,
    available_roles: List[str],
    context: Dict[str, Any] = None,
) -> Decomposition:
    """Decompose objective into agent-assignable sub-tasks"""
    
    # Build decomposition prompt
    prompt = f"""
    Objective: {objective}
    
    Available specialist roles:
    {self._format_roles(available_roles)}
    
    Context: {json.dumps(context or {}, default=str)}
    
    Decompose into a DAG of sub-tasks. Each node must have:
    - id: unique identifier
    - role: one of the available roles
    - prompt: explicit instructions for the agent
    - required_capabilities: list of capability strings
    - depends_on: list of node IDs (empty for root nodes)
    - success_criteria: verifiable completion conditions
    - estimated_duration_seconds: rough estimate
    - priority: 0-10 (higher = more critical)
    
    Principles:
    - Minimize cross-agent dependencies
    - Group related work to same agent
    - Explicit success criteria for verification
    - Capability scoping: least privilege
    - Parallelizable where possible
    
    Return JSON: {{"nodes": [...], "rationale": "..."}}
    """
    
    response = await self.runtime.model_router.complete(
        "complex_reasoning",
        CompletionRequest(messages=[{"role": "user", "content": prompt}]),
        context={"temperature": 0.3}  # Lower temp for structured output
    )
    
    decomposition = self._parse_decomposition(response.content)
    
    # Validate decomposition
    self._validate_decomposition(decomposition, available_roles)
    
    return decomposition
```

### 3.4 Agent Context & Scoping

```python
@dataclass
class AgentContext:
    """Isolated execution context for a delegated agent"""
    task_id: str                           # Unique sub-task ID
    parent_task_id: str                    # Parent orchestration task
    objective: str                         # Specific objective for this agent
    instructions: str                      # Detailed instructions
    allowed_capabilities: List[str]        # Scoped capability grants
    resource_limits: ResourceLimits        # CPU, memory, API calls, time
    working_directory: Optional[str] = None
    environment_vars: Dict[str, str] = field(default_factory=dict)
    parent_evidence_refs: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ResourceLimits:
    max_duration_seconds: int = 300
    max_memory_mb: int = 512
    max_api_calls: int = 50
    max_file_operations: int = 100
    max_network_requests: int = 20
    allowed_domains: List[str] = field(default_factory=list)  # For network caps
    allowed_paths: List[str] = field(default_factory=list)    # For filesystem caps
```

### 3.5 Delegation Protocol

```python
async def delegate(
    self,
    role: str,
    prompt: str,
    parent_task_id: str,
    capabilities: List[str],
    context: Dict[str, Any] = None,
    timeout: int = 300,
) -> AgentResult:
    """Delegate a sub-task to a specialist agent"""
    
    # 1. Get agent from registry
    agent = await self.agent_registry.get_agent(role)
    if not agent:
        raise AgentNotFoundError(f"No agent registered for role: {role}")
    
    # 2. Verify agent health and capacity
    if not await agent.is_healthy():
        raise AgentUnavailableError(f"Agent {role} unhealthy")
    
    # 3. Create scoped context
    agent_context = AgentContext(
        task_id=f"sub_{parent_task_id}_{role}_{uuid4().hex[:8]}",
        parent_task_id=parent_task_id,
        objective=prompt,
        instructions=self._build_instructions(role, prompt, context),
        allowed_capabilities=capabilities,
        resource_limits=ResourceLimits(max_duration_seconds=timeout),
        working_directory=context.get("working_directory") if context else None,
        metadata=context or {},
    )
    
    # 4. Record delegation
    delegation = DelegationRecord(
        id=agent_context.task_id,
        parent_task_id=parent_task_id,
        agent_id=agent.agent_id,
        role=role,
        started_at=datetime.utcnow(),
        status="running",
        context=agent_context,
    )
    self.delegation_history.append(delegation)
    
    # 5. Execute with monitoring
    try:
        # Set up timeout monitoring
        monitor_task = asyncio.create_task(self._monitor_delegation(delegation))
        
        # Execute agent
        result = await agent.start(agent_context)
        
        # Cancel monitor
        monitor_task.cancel()
        
        delegation.status = "completed" if result.success else "failed"
        delegation.result = result
        delegation.completed_at = datetime.utcnow()
        
        # Emit completion event
        await self.runtime.events.emit("agent.delegation_completed", {
            "delegation_id": delegation.id,
            "parent_task_id": parent_task_id,
            "role": role,
            "success": result.success,
            "evidence_count": len(result.evidence),
        })
        
        return result
        
    except asyncio.TimeoutError:
        delegation.status = "timeout"
        await agent.cancel()
        raise DelegationTimeoutError(f"Agent {role} timed out after {timeout}s")
    except Exception as e:
        delegation.status = "error"
        delegation.error = str(e)
        raise
```

### 3.6 Independent Verification

```python
class IndependentVerifier:
    """Verifies agent results without trusting agent self-assessment"""
    
    def __init__(self, runtime: "AppRuntime"):
        self.runtime = runtime
    
    async def verify_orchestration(
        self,
        orchestration: Orchestration,
        results: Dict[str, AgentResult],
    ) -> VerificationResult:
        """Verify all success criteria across all delegations"""
        
        all_checks = []
        
        for node_id, node in orchestration.decomposition.nodes.items():
            result = results.get(node_id)
            if not result:
                all_checks.append(VerificationCheck(
                    criterion=f"Node {node_id} completed",
                    passed=False,
                    evidence="No result returned",
                ))
                continue
            
            # Check each success criterion
            for criterion in node.success_criteria:
                check = await self._verify_criterion(criterion, result, orchestration)
                all_checks.append(check)
        
        # Cross-agent consistency checks
        cross_checks = await self._verify_cross_consistency(results, orchestration)
        all_checks.extend(cross_checks)
        
        # Overall verdict
        passed = all(c.passed for c in all_checks)
        partial = any(c.passed for c in all_checks) and not passed
        
        return VerificationResult(
            passed=passed,
            partial=partial,
            checks=all_checks,
            summary=self._generate_verification_summary(all_checks),
        )
    
    async def _verify_criterion(
        self,
        criterion: SuccessCriterion,
        result: AgentResult,
        orchestration: Orchestration,
    ) -> VerificationCheck:
        """Verify a single success criterion"""
        
        criterion_type = criterion.type
        
        if criterion_type == "file_exists":
            # Verify file exists and has expected content
            path = criterion.params["path"]
            expected = criterion.params.get("contains")
            exists = await self.runtime.adapters.call("filesystem", "exists", {"path": path})
            content_match = True
            if exists and expected:
                content = await self.runtime.adapters.call("filesystem", "read", {"path": path})
                content_match = expected in content
            return VerificationCheck(
                criterion=criterion.description,
                passed=exists and content_match,
                evidence=f"File check: {path}",
            )
        
        elif criterion_type == "test_passes":
            # Verify test results
            test_output = result.metadata.get("test_output", "")
            passed = "PASSED" in test_output or "passed" in test_output.lower()
            return VerificationCheck(
                criterion=criterion.description,
                passed=passed,
                evidence=test_output[:500],
            )
        
        elif criterion_type == "evidence_produced":
            # Verify expected evidence was created
            expected = set(criterion.params.get("evidence_types", []))
            produced = set(result.evidence)
            missing = expected - produced
            return VerificationCheck(
                criterion=criterion.description,
                passed=len(missing) == 0,
                evidence=f"Missing: {missing}" if missing else "All evidence present",
            )
        
        elif criterion_type == "model_verification":
            # Use LLM to verify complex criteria
            prompt = f"""
            Verify this criterion: {criterion.description}
            
            Agent result: {json.dumps(result.output, default=str)}
            Evidence: {result.evidence}
            
            Return JSON: {{"passed": true/false, "reasoning": "..."}}
            """
            response = await self.runtime.model_router.complete(
                "complex_reasoning",
                CompletionRequest(messages=[{"role": "user", "content": prompt}]),
            )
            verification = json.loads(response.content)
            return VerificationCheck(
                criterion=criterion.description,
                passed=verification["passed"],
                evidence=verification["reasoning"],
            )
        
        else:
            return VerificationCheck(
                criterion=criterion.description,
                passed=False,
                evidence=f"Unknown criterion type: {criterion_type}",
            )
```

---

## 4. Specialist Agent Specifications

### 4.1 Research Agent

```python
class ResearchAgent(BaseAgent):
    """
    Deep research with cross-source verification.
    
    Capabilities:
    - web_search: Brave Search API
    - browser_navigate: Playwright for deep extraction
    - source_verification: Cross-reference multiple sources
    - report_generation: Cited research reports
    - fact_extraction: Structured fact retrieval
    """
    
    role = "research"
    capabilities = [
        AgentCapability("web_search", "Search web via Brave API", ["network.search"]),
        AgentCapability("browser_navigate", "Navigate/extract via Playwright", ["browser.navigate"]),
        AgentCapability("source_verification", "Cross-reference sources", ["network.search"]),
        AgentCapability("report_generation", "Generate cited reports", []),
        AgentCapability("fact_extraction", "Extract structured facts", []),
    ]
    
    async def execute(self, context: AgentContext) -> AgentResult:
        objective = context.objective
        depth = context.metadata.get("depth", "standard")
        
        # 1. Decompose into research questions
        questions = await self._decompose_questions(objective)
        
        # 2. Research each question
        findings = []
        for question in questions:
            finding = await self._research_question(question, depth)
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
            metadata={"questions": len(questions), "sources": verified.source_count},
        )
    
    async def _research_question(self, question: str, depth: str) -> ResearchFinding:
        # Search
        count = 10 if depth == "deep" else 5
        results = await self.runtime.adapters.call("brave_research", "search", {
            "query": question, "count": count
        })
        
        # Extract content from top results
        sources = []
        for result in results[:count]:
            content = await self._extract_content(result.url)
            sources.append(Source(url=result.url, title=result.title, content=content))
        
        # Synthesize
        synthesis = await self._synthesize(question, sources)
        
        return ResearchFinding(question=question, sources=sources, synthesis=synthesis)
    
    async def _cross_verify(self, findings: List[ResearchFinding]) -> VerifiedResearch:
        """Verify findings across independent sources"""
        verified_findings = []
        all_evidence = []
        
        for finding in findings:
            # Group by domain/organization for independence
            groups = self._group_by_independence(finding.sources)
            
            if len(groups) >= 2:
                # Multiple independent sources - check consensus
                consensus = self._check_consensus(groups)
                verified_findings.append(VerifiedFinding(
                    question=finding.question,
                    answer=consensus.answer,
                    confidence=consensus.confidence,
                    supporting_sources=consensus.sources,
                    disagreements=consensus.disagreements,
                ))
                all_evidence.extend(consensus.evidence_refs)
            else:
                # Single source - mark as low confidence
                verified_findings.append(VerifiedFinding(
                    question=finding.question,
                    answer=finding.synthesis,
                    confidence="low",
                    supporting_sources=finding.sources,
                    disagreements=["Insufficient independent sources"],
                ))
        
        return VerifiedResearch(findings=verified_findings, evidence_refs=all_evidence)
```

### 4.2 Coding Agent

```python
class CodingAgent(BaseAgent):
    """
    Software development agent with repository understanding.
    
    Capabilities:
    - read_code: Read/understand codebase
    - write_code: Create/modify source files
    - run_tests: Execute test suites
    - lint_typecheck: Run linters/type checkers
    - git_operations: Commit, branch, diff
    - refactor: Automated refactoring
    """
    
    role = "coding"
    capabilities = [
        AgentCapability("read_code", "Read and understand codebase", ["filesystem.read"]),
        AgentCapability("write_code", "Create/modify source files", ["filesystem.write"]),
        AgentCapability("run_tests", "Execute test suites", ["shell.execute"]),
        AgentCapability("lint_typecheck", "Run linters and type checkers", ["shell.execute"]),
        AgentCapability("git_operations", "Git commit, branch, diff", ["shell.execute"]),
        AgentCapability("refactor", "Automated refactoring", ["filesystem.write", "shell.execute"]),
    ]
    
    async def execute(self, context: AgentContext) -> AgentResult:
        repo_path = context.metadata.get("repo_path", context.working_directory)
        task_desc = context.objective
        
        # 1. Understand repository
        understanding = await self._understand_repo(repo_path)
        
        # 2. Identify relevant files
        relevant_files = await self._identify_files(task_desc, understanding)
        file_contents = await self._read_files(relevant_files)
        
        # 3. Create implementation plan
        plan = await self._create_plan(task_desc, understanding, file_contents)
        
        # 4. Implement changes
        changes = await self._implement(plan, context)
        
        # 5. Run tests
        test_results = await self._run_tests(repo_path, changes)
        
        # 6. Lint and typecheck
        lint_results = await self._lint_and_typecheck(repo_path)
        
        # 7. Generate summary
        summary = self._generate_summary(changes, test_results, lint_results)
        
        success = test_results.passed and lint_results.passed
        
        return AgentResult(
            success=success,
            output=summary,
            evidence=test_results.evidence_refs + lint_results.evidence_refs,
            artifacts=changes.modified_files,
            metadata={
                "files_changed": len(changes.modified_files),
                "tests_passed": test_results.passed,
                "lint_passed": lint_results.passed,
            },
        )
    
    async def _create_plan(self, task: str, understanding: RepoUnderstanding, files: Dict[str, str]) -> ImplementationPlan:
        prompt = f"""
        Task: {task}
        
        Repository: {understanding.summary}
        Architecture: {understanding.architecture}
        Conventions: {understanding.conventions}
        Testing: {understanding.test_patterns}
        
        Relevant files:
        {self._format_files(files)}
        
        Create implementation plan with:
        1. Files to create/modify (with exact changes)
        2. Test strategy (what to test, how)
        3. Potential risks and mitigations
        4. Rollback plan
        
        Return JSON: {{"steps": [...], "files": [...], "tests": [...], "risks": [...]}}
        """
        response = await self.runtime.model_router.complete(
            "software_engineering",
            CompletionRequest(messages=[{"role": "user", "content": prompt}]),
        )
        return self._parse_plan(response.content)
```

### 4.3 Browser Agent

```python
class BrowserAgent(BaseAgent):
    """
    Browser automation specialist using Playwright.
    
    Capabilities:
    - navigate: Go to URLs, wait for load states
    - interact: Click, type, select, hover, drag-drop
    - extract: Text, HTML, attributes, tables, screenshots
    - evaluate: Execute JavaScript in page context
    - network: Monitor requests/responses
    - trace: Record Playwright traces for evidence
    - auth: Handle login flows, cookies, sessions
    """
    
    role = "browser"
    capabilities = [
        AgentCapability("navigate", "Navigate to URLs", ["browser.navigate"]),
        AgentCapability("interact", "Click, type, select elements", ["browser.click", "browser.type"]),
        AgentCapability("extract", "Extract content from pages", ["browser.read"]),
        AgentCapability("evaluate", "Execute JavaScript", ["browser.script"]),
        AgentCapability("network_monitor", "Monitor network traffic", ["browser.read"]),
        AgentCapability("trace_record", "Record Playwright traces", ["browser.trace"]),
        AgentCapability("authenticate", "Handle login flows", ["browser.navigate", "browser.click", "browser.type"]),
    ]
    
    async def execute(self, context: AgentContext) -> AgentResult:
        # Browser agent typically receives a sequence of operations
        operations = context.metadata.get("operations", [])
        context_id = context.metadata.get("context_id", "default")
        
        results = []
        evidence = []
        
        for i, op in enumerate(operations):
            self.check_cancelled()
            
            result = await self._execute_operation(op, context_id)
            results.append(result)
            
            if op.get("capture_evidence", True):
                # Screenshot after each operation
                screenshot = await self.runtime.adapters.call(
                    "playwright", "screenshot", 
                    {"context_id": context_id, "full_page": op.get("full_page", False)}
                )
                evidence.append(screenshot)
        
        return AgentResult(
            success=all(r.get("success", False) for r in results),
            output={"operations": results},
            evidence=evidence,
            metadata={"operations_completed": len(results)},
        )
    
    async def _execute_operation(self, op: Dict, context_id: str) -> Dict:
        op_type = op["type"]
        params = op.get("params", {})
        params["context_id"] = context_id
        
        adapter = self.runtime.adapters.get("playwright")
        
        if op_type == "navigate":
            return await adapter.navigate(**params)
        elif op_type == "click":
            return await adapter.click(**params)
        elif op_type == "type":
            return await adapter.type(**params)
        elif op_type == "extract":
            return await adapter.extract(**params)
        elif op_type == "evaluate":
            return await adapter.evaluate(**params)
        elif op_type == "wait_for":
            return await adapter.wait_for_selector(**params)
        elif op_type == "trace_start":
            return await adapter.trace_start(**params)
        elif op_type == "trace_stop":
            return await adapter.trace_stop(**params)
        else:
            return {"success": False, "error": f"Unknown operation: {op_type}"}
```

### 4.4 Filesystem Agent

```python
class FilesystemAgent(BaseAgent):
    """
    Filesystem operations specialist.
    
    Capabilities:
    - read: Read files (text, binary, structured)
    - write: Create/modify files
    - list: Directory listings with filters
    - search: Content search (grep, ripgrep)
    - watch: File system events
    - metadata: Stats, permissions, hashes
    - archive: Create/extract archives
    """
    
    role = "filesystem"
    capabilities = [
        AgentCapability("read", "Read files", ["filesystem.read"]),
        AgentCapability("write", "Write files", ["filesystem.write"]),
        AgentCapability("list", "List directories", ["filesystem.read"]),
        AgentCapability("search", "Search file contents", ["filesystem.read"]),
        AgentCapability("watch", "Watch for changes", ["filesystem.read"]),
        AgentCapability("metadata", "File metadata", ["filesystem.read"]),
        AgentCapability("archive", "Archive operations", ["filesystem.write", "shell.execute"]),
    ]
    
    async def execute(self, context: AgentContext) -> AgentResult:
        operations = context.metadata.get("operations", [])
        allowed_paths = context.resource_limits.allowed_paths
        
        results = []
        for op in operations:
            self.check_cancelled()
            
            # Validate path access
            path = op.get("path") or op.get("params", {}).get("path")
            if path and not self._is_path_allowed(path, allowed_paths):
                results.append({"success": False, "error": f"Path not allowed: {path}"})
                continue
            
            result = await self._execute_operation(op)
            results.append(result)
        
        return AgentResult(
            success=all(r.get("success", False) for r in results),
            output={"operations": results},
            metadata={"operations_completed": len(results)},
        )
```

### 4.5 System Agent

```python
class SystemAgent(BaseAgent):
    """
    System administration and monitoring specialist.
    
    Capabilities:
    - process: List, start, stop, monitor processes
    - service: Windows service management
    - registry: Read/write Windows registry
    - scheduled_tasks: Task Scheduler operations
    - event_log: Windows Event Log queries
    - performance: CPU, memory, disk, network metrics
    - power: Sleep, hibernate, battery status
    """
    
    role = "system"
    capabilities = [
        AgentCapability("process_list", "List processes", ["system.process_list"]),
        AgentCapability("process_control", "Start/stop processes", ["system.process_control"]),
        AgentCapability("service_control", "Manage services", ["system.service_control"]),
        AgentCapability("registry_read", "Read registry", ["registry.read"]),
        AgentCapability("registry_write", "Write registry", ["registry.write"]),
        AgentCapability("performance_monitor", "System metrics", ["system.performance"]),
        AgentCapability("power_management", "Power operations", ["system.power"]),
    ]
```

### 4.6 Communications Agent

```python
class CommunicationsAgent(BaseAgent):
    """
    Email, messaging, calendar, and notifications specialist.
    
    Capabilities:
    - email_send: Send emails (with approval)
    - email_read: Read/search emails
    - calendar_read: Read calendar events
    - calendar_write: Create/update events (with approval)
    - message_send: Send messages (Teams, Slack, SMS)
    - notification: System notifications
    """
    
    role = "communications"
    capabilities = [
        AgentCapability("email_send", "Send emails", ["network.send", "email.send"]),
        AgentCapability("email_read", "Read emails", ["network.read", "email.read"]),
        AgentCapability("calendar_read", "Read calendar", ["network.read", "calendar.read"]),
        AgentCapability("calendar_write", "Write calendar", ["network.send", "calendar.write"]),
        AgentCapability("message_send", "Send messages", ["network.send", "message.send"]),
        AgentCapability("notify", "System notifications", ["system.notify"]),
    ]
    
    # All send operations require explicit approval (R3/R4)
    # Read operations typically pre-approved (R1)
```

### 4.7 Creative Agent

```python
class CreativeAgent(BaseAgent):
    """
    Image, video, and audio generation specialist.
    
    Capabilities:
    - image_generate: Generate images (DALL-E, Midjourney, SDXL)
    - image_edit: Inpaint, outpaint, variations
    - video_generate: Generate video (Sora, Runway, Pika)
    - audio_generate: Generate audio/music (Suno, ElevenLabs)
    - design: Layout, typography, color palette generation
    """
    
    role = "creative"
    capabilities = [
        AgentCapability("image_generate", "Generate images", ["creative.image"]),
        AgentCapability("image_edit", "Edit images", ["creative.image"]),
        AgentCapability("video_generate", "Generate video", ["creative.video"]),
        AgentCapability("audio_generate", "Generate audio", ["creative.audio"]),
        AgentCapability("design", "Design assistance", []),
    ]
    
    async def execute(self, context: AgentContext) -> AgentResult:
        task_type = context.metadata.get("creative_task", "image_generate")
        prompt = context.objective
        
        if task_type == "image_generate":
            return await self._generate_image(prompt, context)
        elif task_type == "video_generate":
            return await self._generate_video(prompt, context)
        elif task_type == "audio_generate":
            return await self._generate_audio(prompt, context)
        else:
            return AgentResult(success=False, error=f"Unknown creative task: {task_type}")
    
    async def _generate_image(self, prompt: str, context: AgentContext) -> AgentResult:
        # Use model router to select best image model
        provider, spec = await self.runtime.model_router.select_model(
            "creative",
            required_capabilities=[ModelCapability.IMAGE_GENERATION],
        )
        
        # Generate
        result = await self.runtime.adapters.call("creative", "generate_image", {
            "prompt": prompt,
            "model": spec.id,
            "size": context.metadata.get("size", "1024x1024"),
            "style": context.metadata.get("style"),
        })
        
        # Save artifacts
        artifacts = []
        for img_data in result.get("images", []):
            path = await self._save_image(img_data, context)
            artifacts.append(path)
        
        return AgentResult(
            success=True,
            output=result,
            artifacts=artifacts,
            evidence=[f"Generated {len(artifacts)} images"],
        )
```

### 4.8 Memory Agent

```python
class MemoryAgent(BaseAgent):
    """
    Memory storage, retrieval, and consolidation specialist.
    
    Capabilities:
    - store: Store memories across 5 kinds
    - retrieve: Query memories with filters
    - consolidate: Trigger consolidation cycle
    - forget: Delete specific memories
    - export: Export memory for backup
    - import: Import memory from backup
    """
    
    role = "memory"
    capabilities = [
        AgentCapability("store", "Store memories", ["memory.write"]),
        AgentCapability("retrieve", "Retrieve memories", ["memory.read"]),
        AgentCapability("consolidate", "Trigger consolidation", ["memory.consolidate"]),
        AgentCapability("forget", "Delete memories", ["memory.delete"]),
        AgentCapability("export", "Export memories", ["memory.read", "filesystem.write"]),
        AgentCapability("import", "Import memories", ["memory.write", "filesystem.read"]),
    ]
```

### 4.9 Projects Agent

```python
class ProjectsAgent(BaseAgent):
    """
    Project planning, tracking, and milestone management specialist.
    
    Capabilities:
    - plan: Create project plans with milestones
    - track: Update task progress, dependencies
    - schedule: Manage timelines, resource allocation
    - report: Generate status reports
    - risk: Identify and track risks
    """
    
    role = "projects"
    capabilities = [
        AgentCapability("plan", "Create project plans", ["projects.write"]),
        AgentCapability("track", "Track progress", ["projects.read", "projects.write"]),
        AgentCapability("schedule", "Manage schedules", ["projects.write"]),
        AgentCapability("report", "Generate reports", ["projects.read"]),
        AgentCapability("risk_management", "Track risks", ["projects.write"]),
    ]
```

### 4.10 Desktop UI Agent

```python
class DesktopUIAgent(BaseAgent):
    """
    Desktop automation specialist (Windows UIA + Playwright hybrid).
    
    Capabilities:
    - launch: Launch applications
    - window: Find, focus, resize, close windows
    - click: Click UI elements
    - type: Type text into elements
    - read: Read UI element properties
    - shortcut: Send keyboard shortcuts
    - menu: Navigate menus
    - drag_drop: Drag and drop operations
    """
    
    role = "desktop_ui"
    capabilities = [
        AgentCapability("launch", "Launch applications", ["system.launch"]),
        AgentCapability("window_manage", "Manage windows", ["ui.read", "ui.write"]),
        AgentCapability("click", "Click elements", ["ui.click"]),
        AgentCapability("type", "Type text", ["ui.type"]),
        AgentCapability("read_ui", "Read UI state", ["ui.read"]),
        AgentCapability("shortcut", "Keyboard shortcuts", ["ui.type"]),
        AgentCapability("menu_navigate", "Navigate menus", ["ui.click", "ui.read"]),
        AgentCapability("drag_drop", "Drag and drop", ["ui.click", "ui.type"]),
    ]
    
    # Uses Windows UIA adapter for native apps
    # Uses Playwright for web views in apps (Electron, etc.)
```

---

## 5. Agent Registry & Lifecycle

### 5.1 Agent Registry

```python
class AgentRegistry:
    """Manages agent registration, health, and retrieval"""
    
    def __init__(self, runtime: "AppRuntime"):
        self.runtime = runtime
        self.agents: Dict[str, BaseAgent] = {}
        self.role_mapping: Dict[str, str] = {}  # role -> agent_id
    
    def register(self, agent: BaseAgent):
        self.agents[agent.agent_id] = agent
        self.role_mapping[agent.role] = agent.agent_id
    
    async def get_agent(self, role: str) -> Optional[BaseAgent]:
        agent_id = self.role_mapping.get(role)
        if agent_id:
            return self.agents.get(agent_id)
        return None
    
    async def get_all_healthy(self) -> List[BaseAgent]:
        healthy = []
        for agent in self.agents.values():
            if await agent.is_healthy():
                healthy.append(agent)
        return healthy
    
    def list_roles(self) -> List[str]:
        return list(self.role_mapping.keys())
```

### 5.2 Agent Health Monitoring

```python
class AgentHealthMonitor:
    """Monitors agent health and capacity"""
    
    def __init__(self, registry: AgentRegistry):
        self.registry = registry
        self.health_cache: Dict[str, AgentHealth] = {}
        self.check_interval = 30  # seconds
    
    async def check_all(self):
        for agent in self.registry.agents.values():
            health = await self._check_agent(agent)
            self.health_cache[agent.agent_id] = health
    
    async def _check_agent(self, agent: BaseAgent) -> AgentHealth:
        checks = {}
        
        # Basic responsiveness
        try:
            start = time.time()
            await agent.health_check()
            checks["responsiveness"] = HealthCheck(
                passed=True,
                latency_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            checks["responsiveness"] = HealthCheck(passed=False, error=str(e))
        
        # Resource usage
        try:
            usage = await agent.get_resource_usage()
            checks["resources"] = HealthCheck(
                passed=usage.memory_mb < 1024 and usage.cpu_percent < 80,
                details=usage,
            )
        except Exception:
            checks["resources"] = HealthCheck(passed=True)  # Optional
        
        # Capability availability
        try:
            caps = await agent.verify_capabilities()
            checks["capabilities"] = HealthCheck(passed=all(caps.values()))
        except Exception:
            checks["capabilities"] = HealthCheck(passed=True)
        
        overall = all(c.passed for c in checks.values())
        return AgentHealth(
            agent_id=agent.agent_id,
            role=agent.role,
            overall=overall,
            checks=checks,
            timestamp=datetime.utcnow(),
        )
```

---

## 6. Multi-Agent Communication Patterns

### 6.1 Delegation Patterns

| Pattern | Use Case | Description |
|---------|----------|-------------|
| **Sequential** | Dependent steps | Agent B waits for Agent A completion |
| **Parallel** | Independent sub-tasks | Multiple agents run simultaneously |
| **Fan-out/Fan-in** | Map-reduce | Coordinator splits, agents process, coordinator combines |
| **Pipeline** | Streaming data | Agent A output → Agent B input → Agent C output |
| **Supervisory** | Quality control | Supervisor agent reviews worker outputs |

### 6.2 Communication Protocol

```python
# All inter-agent communication goes through Coordinator
# Agents NEVER communicate directly with each other

# Delegation message (Coordinator → Agent)
@dataclass
class DelegationMessage:
    delegation_id: str
    parent_task_id: str
    role: str
    objective: str
    instructions: str
    allowed_capabilities: List[str]
    resource_limits: ResourceLimits
    context: Dict[str, Any]
    deadline: datetime

# Result message (Agent → Coordinator)
@dataclass
class DelegationResult:
    delegation_id: str
    success: bool
    output: Any
    error: Optional[str]
    evidence: List[str]
    artifacts: List[str]
    metadata: Dict[str, Any]
    duration_ms: int
```

### 6.3 Shared State via Memory System

```python
# Agents share state through Memory System (not direct communication)
# Coordinator writes to memory, agents read from memory

# Example: Research agent stores findings
await memory.store(SEMANTIC, "Competitor X pricing: $29/mo", 
    importance=0.8, tags=["competitor", "pricing"], source="research_agent")

# Coding agent retrieves for implementation
findings = await memory.retrieve(SEMANTIC, "competitor pricing", limit=10)
```

---

## 7. Failure Handling & Compensation

### 7.1 Failure Types

| Type | Detection | Response |
|------|-----------|----------|
| **Agent Crash** | Exception/timeout | Retry with same/different agent |
| **Capability Denied** | Policy rejection | Request approval or alternative approach |
| **Partial Success** | Some criteria met | Mark PARTIAL, continue if non-critical |
| **Verification Failed** | Independent check fails | Compensation: re-delegate with feedback |
| **Resource Exhausted** | Limits exceeded | Queue, scale down, or fail gracefully |

### 7.2 Compensation Strategies

```python
class CompensationManager:
    """Handles failure compensation for multi-agent tasks"""
    
    async def compensate(
        self,
        orchestration: Orchestration,
        failed_node: str,
        error: Exception,
        completed_results: Dict[str, AgentResult],
    ) -> CompensationAction:
        """Determine and execute compensation"""
        
        node = orchestration.decomposition.nodes[failed_node]
        
        # Strategy 1: Retry with same agent (transient failure)
        if self._is_transient(error):
            return CompensationAction(
                type="retry",
                node_id=failed_node,
                reason="Transient failure detected",
            )
        
        # Strategy 2: Retry with different agent (capability issue)
        if self._is_capability_error(error):
            alternative = await self._find_alternative_agent(node.role)
            if alternative:
                return CompensationAction(
                    type="retry_alternative",
                    node_id=failed_node,
                    agent_role=alternative.role,
                    reason="Capability mismatch",
                )
        
        # Strategy 3: Decompose further (too complex)
        if self._is_complexity_error(error):
            sub_nodes = await self._decompose_node(node, error)
            return CompensationAction(
                type="decompose",
                node_id=failed_node,
                sub_nodes=sub_nodes,
                reason="Task too complex, decomposed",
            )
        
        # Strategy 4: Skip if non-critical
        if not node.metadata.get("critical", True):
            return CompensationAction(
                type="skip",
                node_id=failed_node,
                reason="Non-critical node failed",
            )
        
        # Strategy 5: Escalate to human
        return CompensationAction(
            type="escalate",
            node_id=failed_node,
            reason="Automatic compensation exhausted",
        )
```

---

## 8. Agent Development Framework

### 8.1 Creating New Specialist Agents

```python
# Template for new specialist agents

class NewSpecialistAgent(BaseAgent):
    role = "new_specialist"
    capabilities = [
        AgentCapability("capability_name", "Description", ["required_permission"]),
    ]
    
    async def execute(self, context: AgentContext) -> AgentResult:
        # 1. Validate inputs
        self._validate_context(context)
        
        # 2. Execute core logic
        result = await self._core_logic(context)
        
        # 3. Self-validate
        if not await self.validate_result(result):
            return AgentResult(success=False, error="Self-validation failed")
        
        return result
    
    async def validate_result(self, result: AgentResult) -> bool:
        """Self-validation before returning to coordinator"""
        # Check required outputs present
        # Check evidence generated
        # Check no obvious errors
        return True
    
    async def health_check(self) -> bool:
        """Quick health check for registry"""
        return True
    
    async def get_resource_usage(self) -> ResourceUsage:
        """Current resource usage"""
        return ResourceUsage(memory_mb=100, cpu_percent=10)
    
    async def verify_capabilities(self) -> Dict[str, bool]:
        """Verify all declared capabilities work"""
        return {"capability_name": True}
```

### 8.2 Agent Testing Standards

```python
# tests/agents/test_research_agent.py

@pytest.fixture
async def research_agent(runtime):
    agent = ResearchAgent(runtime)
    yield agent
    await agent.cleanup()

async def test_research_agent_basic(research_agent):
    context = AgentContext(
        task_id="test_1",
        parent_task_id="parent_1",
        objective="Find current price of Bitcoin",
        instructions="Search and verify from 3+ sources",
        allowed_capabilities=["network.search"],
        resource_limits=ResourceLimits(max_duration_seconds=60),
    )
    
    result = await research_agent.start(context)
    
    assert result.success
    assert "bitcoin" in result.output.lower()
    assert len(result.evidence) >= 3
    assert result.metadata["sources_checked"] >= 3

async def test_research_agent_cross_verification(research_agent):
    # Test that conflicting sources are detected
    context = AgentContext(...)
    result = await research_agent.start(context)
    
    # Should flag disagreements in verified findings
    for finding in result.output.findings:
        if finding.confidence == "low":
            assert "Insufficient independent sources" in finding.disagreements
```

---

## 9. Performance & Scaling

### 9.1 Concurrency Model

```python
class AgentConcurrencyManager:
    """Manages concurrent agent execution"""
    
    def __init__(self, max_total_agents: int = 8, max_per_role: int = 2):
        self.max_total = max_total_agents
        self.max_per_role = max_per_role
        self.active: Dict[str, int] = defaultdict(int)  # role -> count
        self.total_active = 0
        self._lock = asyncio.Lock()
    
    async def acquire(self, role: str) -> bool:
        async with self._lock:
            if self.total_active >= self.max_total:
                return False
            if self.active[role] >= self.max_per_role:
                return False
            self.active[role] += 1
            self.total_active += 1
            return True
    
    def release(self, role: str):
        with self._lock:
            self.active[role] = max(0, self.active[role] - 1)
            self.total_active = max(0, self.total_active - 1)
```

### 9.2 Resource Limits per Agent

| Agent Role | Max Duration | Max Memory | Max API Calls | Max File Ops |
|------------|--------------|------------|---------------|--------------|
| Research | 300s | 512MB | 50 | 20 |
| Coding | 600s | 1GB | 30 | 100 |
| Browser | 300s | 1GB | 100 | 10 |
| Filesystem | 120s | 256MB | 10 | 500 |
| System | 60s | 256MB | 20 | 50 |
| Communications | 60s | 256MB | 20 | 10 |
| Creative | 120s | 1GB | 10 | 20 |
| Memory | 60s | 512MB | 10 | 100 |
| Projects | 60s | 256MB | 10 | 50 |
| Desktop UI | 120s | 512MB | 20 | 50 |

---

## 10. Security & Isolation

### 10.1 Capability-Based Security

```python
# Each agent receives ONLY capabilities needed for its sub-task
# Capabilities are scoped (path, app, time-limited)

@dataclass
class ScopedCapabilityGrant:
    capability: str
    scope: CapabilityScope
    resource_pattern: Optional[str] = None  # For PATH_SCOPED
    expires_at: Optional[datetime] = None
    conditions: List[Condition] = field(default_factory=list)

# Example: Coding agent gets filesystem.write ONLY for project directory
grant = ScopedCapabilityGrant(
    capability="filesystem.write",
    scope=CapabilityScope.PATH_SCOPED,
    resource_pattern="/home/user/project/*",
    expires_at=datetime.utcnow() + timedelta(hours=1),
)
```

### 10.2 Agent Sandboxing (Future)

| Isolation Level | Implementation | Use Case |
|-----------------|----------------|----------|
| **In-Process** | Current: async tasks | Trusted agents, low overhead |
| **Subprocess** | Separate Python process | Untrusted code, resource limits |
| **WASM** | wasmtime sandbox | Plugins, third-party agents |
| **Container** | Docker/gVisor | Maximum isolation |

---

## 11. Observability & Debugging

### 11.1 Agent Tracing

```python
# Every delegation creates a trace span
@dataclass
class AgentTraceSpan:
    trace_id: str
    span_id: str
    parent_span_id: Optional[str]
    delegation_id: str
    role: str
    started_at: datetime
    ended_at: Optional[datetime]
    status: str  # running, completed, failed
    input_summary: str
    output_summary: str
    error: Optional[str]
    resource_usage: ResourceUsage
    events: List[TraceEvent]

# Exported to OpenTelemetry for visualization
```

### 11.2 Debugging Commands

```bash
# CLI debugging (via Tauri shell)
arise agent list                    # List all agents and health
arise agent trace <delegation_id>   # Show trace for delegation
arise agent logs <agent_role>       # Show agent logs
arise agent replay <delegation_id>  # Replay delegation with debug
```

---

## 12. Open Multi-Agent Decisions

| Decision | Options | Considerations |
|----------|---------|----------------|
| Agent communication | In-process channels / gRPC / NATS | Debugging vs distribution |
| Agent sandboxing | None / Subprocess / WASM / Container | Security vs performance |
| Dynamic agent loading | Plugin system / Fixed registry | Extensibility vs stability |
| Agent marketplace | None / Internal / External | Ecosystem vs control |
| Cross-agent learning | Shared memory / Federated learning / None | Privacy vs improvement |
| Human-in-the-loop | Approval gates / Real-time collab / Async review | Latency vs quality |