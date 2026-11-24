# ARISE — Testing Strategy

## Overview

This document defines the comprehensive testing strategy for ARISE, covering unit tests, integration tests, contract tests, end-to-end tests, chaos engineering, performance benchmarks, and specialized testing for voice, agents, and security.

---

## 1. Testing Pyramid

```
                    ┌─────────────────┐
                    │   E2E Tests     │  ← 5%  (Critical user journeys)
                    │   (10-20)       │
               ┌────┴────────────────┴────┐
               │  Integration Tests       │  ← 15% (Component interactions)
               │  (50-100)                │
        ┌──────┴──────────────────────────┴──────┐
        │       Contract Tests                   │  ← 20% (Interface contracts)
        │       (100-200)                        │
┌───────┴────────────────────────────────────────┴───────┐
│                  Unit Tests                            │  ← 60% (Logic verification)
│                  (500-1000)                            │
└────────────────────────────────────────────────────────┘
```

### 1.1 Test Distribution by Layer

| Layer | Count | Speed | Scope | Tools |
|-------|-------|-------|-------|-------|
| Unit | 500-1000 | <1s total | Single function/class | pytest, pytest-asyncio, hypothesis |
| Contract | 100-200 | <5s total | Interface compliance | pytest, schemathesis, pact |
| Integration | 50-100 | <30s total | Multi-component | pytest, testcontainers |
| E2E | 10-20 | <5min total | Full user flows | Playwright, custom harness |
| Performance | 20-30 | <10min total | SLO validation | Custom benchmarks |
| Chaos | 10-15 | <30min total | Resilience | Chaos Mesh, custom injectors |
| Security | 20-30 | <5min total | Vulnerability | bandit, semgrep, custom |

---

## 2. Unit Testing

### 2.1 Structure

```python
# tests/unit/
├── test_policy_engine.py          # Policy rules, risk assessment, grants
├── test_task_engine.py            # State machine, transitions, checkpoints
├── test_model_router.py           # Provider selection, fallback, circuit breaker
├── test_memory_system.py          # Consolidation, retrieval, governance
├── test_voice_pipeline.py         # Wake word, VAD, ASR, TTS, state machine
├── test_intent_classifier.py      # Classification accuracy, edge cases
├── test_adapters/
│   ├── test_uia_adapter.py
│   ├── test_playwright_adapter.py
│   ├── test_filesystem_adapter.py
│   └── test_shell_adapter.py
├── test_agents/
│   ├── test_research_agent.py
│   ├── test_coding_agent.py
│   └── test_coordinator.py
├── test_security/
│   ├── test_prompt_defense.py
│   ├── test_capability_system.py
│   └── test_audit_log.py
└── test_performance/
    ├── test_resource_governor.py
    ├── test_cache.py
    └── test_concurrency.py
```

### 2.2 Unit Test Patterns

```python
# tests/unit/test_policy_engine.py
import pytest
from hypothesis import given, strategies as st
from arise.security.policy_engine import PolicyEngine, RiskLevel, Capability
from arise.security.capabilities import CapabilityGrant, CapabilityScope

class TestPolicyEngine:
    """Unit tests for PolicyEngine"""
    
    @pytest.fixture
    def policy_engine(self, runtime):
        return PolicyEngine(runtime)
    
    @pytest.mark.parametrize("objective,expected_risk", [
        ("list files in Documents", RiskLevel.R0),
        ("read config file", RiskLevel.R0),
        ("create new file", RiskLevel.R1),
        ("edit existing file", RiskLevel.R1),
        ("install python package", RiskLevel.R2),
        ("send email to user", RiskLevel.R3),
        ("delete all files", RiskLevel.R4),
    ])
    def test_risk_assessment(self, policy_engine, objective, expected_risk):
        assessment = await policy_engine.assess_risk(objective, mock_intent())
        assert assessment.level == expected_risk
    
    @given(st.text(min_size=1, max_size=100))
    def test_risk_assessment_never_crashes(self, policy_engine, objective):
        # Property-based: should never raise unhandled exception
        assessment = await policy_engine.assess_risk(objective, mock_intent())
        assert assessment.level in RiskLevel
    
    async def test_capability_grant_scoping(self, policy_engine):
        # Global grant
        policy_engine.grant_capability("user", CapabilityGrant(
            capability=Capability.FILESYSTEM_WRITE,
            scope=CapabilityScope.GLOBAL
        ))
        assert await policy_engine.check_capability("user", Capability.FILESYSTEM_WRITE, "/any/path")
        
        # Path-scoped grant
        policy_engine.grant_capability("user", CapabilityGrant(
            capability=Capability.FILESYSTEM_WRITE,
            scope=CapabilityScope.PATH_SCOPED,
            resource_pattern="/home/user/project/*"
        ))
        assert await policy_engine.check_capability("user", Capability.FILESYSTEM_WRITE, "/home/user/project/file.txt")
        assert not await policy_engine.check_capability("user", Capability.FILESYSTEM_WRITE, "/etc/passwd")
    
    async def test_approval_required_for_r2_plus(self, policy_engine):
        # R2 requires approval
        assessment = await policy_engine.assess_risk("install package", mock_intent())
        assert assessment.requires_approval
        assert assessment.level == RiskLevel.R2
        
        # R0 does not
        assessment = await policy_engine.assess_risk("list files", mock_intent())
        assert not assessment.requires_approval
        assert assessment.level == RiskLevel.R0

class TestCapabilityGrant:
    """Unit tests for CapabilityGrant matching"""
    
    @pytest.mark.parametrize("grant_scope,resource,expected", [
        (CapabilityScope.GLOBAL, "/any/path", True),
        (CapabilityScope.PATH_SCOPED, "/home/user/project/file.txt", True),
        (CapabilityScope.PATH_SCOPED, "/etc/passwd", False),
        (CapabilityScope.DOMAIN_SCOPED, "api.github.com", True),
        (CapabilityScope.DOMAIN_SCOPED, "api.evil.com", False),
        (CapabilityScope.TEMPORARY, "resource", True),  # Time checked separately
    ])
    def test_scope_matching(self, grant_scope, resource, expected):
        grant = CapabilityGrant(
            capability=Capability.FILESYSTEM_WRITE,
            scope=grant_scope,
            resource_pattern="/home/user/project/*" if grant_scope == CapabilityScope.PATH_SCOPED else "api.github.com"
        )
        assert grant.matches(Capability.FILESYSTEM_WRITE, resource) == expected
    
    def test_expiry(self):
        grant = CapabilityGrant(
            capability=Capability.FILESYSTEM_WRITE,
            expires_at=datetime.utcnow() - timedelta(hours=1)  # Expired
        )
        assert not grant.matches(Capability.FILESYSTEM_WRITE, "/test")
    
    def test_conditions(self):
        grant = CapabilityGrant(
            capability=Capability.FILESYSTEM_WRITE,
            conditions=[lambda ctx: ctx.get("time_of_day") == "business_hours"]
        )
        assert grant.matches(Capability.FILESYSTEM_WRITE, "/test", {"time_of_day": "business_hours"})
        assert not grant.matches(Capability.FILESYSTEM_WRITE, "/test", {"time_of_day": "night"})
```

### 2.3 Test Fixtures

```python
# tests/conftest.py
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from arise.runtime import AppRuntime

@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
def mock_runtime():
    runtime = MagicMock(spec=AppRuntime)
    runtime.settings = MagicMock()
    runtime.events = MagicMock()
    runtime.events.emit = AsyncMock()
    runtime.credential_manager = MagicMock()
    runtime.audit_log = MagicMock()
    runtime.audit_log.log = AsyncMock()
    return runtime

@pytest.fixture
def mock_intent():
    intent = MagicMock()
    intent.type = "task"
    intent.entities = {}
    intent.confidence = 0.9
    return intent

@pytest.fixture
async def test_db(tmp_path):
    """Temporary database for tests"""
    db_path = tmp_path / "test.db"
    # Initialize schema
    yield db_path
    # Cleanup handled by tmp_path

@pytest.fixture
def temp_dir(tmp_path):
    return tmp_path
```

---

## 3. Contract Testing

### 3.1 Adapter Port Contracts

```python
# tests/contract/test_adapter_ports.py
import pytest
from arise.adapters.ports import AdapterPort, AdapterCapability, AdapterResult

class AdapterContractTests:
    """Contract tests that ALL adapters must pass"""
    
    @pytest.fixture
    def adapter(self):
        # Override in subclasses
        raise NotImplementedError
    
    @pytest.mark.contract
    async def test_capability_declaration(self, adapter):
        """Adapter must declare its capabilities"""
        caps = adapter.capabilities()
        assert isinstance(caps, list)
        assert all(isinstance(c, AdapterCapability) for c in caps)
        assert len(caps) > 0
    
    @pytest.mark.contract
    async def test_operation_schema_validation(self, adapter):
        """Each operation must have a valid schema"""
        for op_name, op in adapter.operations().items():
            assert op.name == op_name
            assert op.schema is not None
            # Schema must be valid JSON Schema
            import jsonschema
            jsonschema.Draft7Validator.check_schema(op.schema)
    
    @pytest.mark.contract
    async def test_call_requires_capabilities(self, adapter):
        """Operations must require declared capabilities"""
        for op_name, op in adapter.operations().items():
            required = op.required_capabilities
            assert isinstance(required, list)
            # Each required capability must be declared
            declared = [c.name for c in adapter.capabilities()]
            for cap in required:
                assert cap in declared, f"{op_name} requires undeclared {cap}"
    
    @pytest.mark.contract
    async def test_call_returns_result(self, adapter):
        """Call must return AdapterResult"""
        # Test with minimal valid input for each operation
        for op_name, op in adapter.operations().items():
            # Generate valid input from schema
            test_input = generate_test_data(op.schema)
            result = await adapter.call(op_name, test_input, op.required_capabilities)
            assert isinstance(result, AdapterResult)
            assert result.success or result.error is not None
    
    @pytest.mark.contract
    async def test_call_validates_input(self, adapter):
        """Call must reject invalid input"""
        for op_name, op in adapter.operations().items():
            invalid_input = {"invalid": "data"}
            result = await adapter.call(op_name, invalid_input, op.required_capabilities)
            assert not result.success
            assert result.error is not None
    
    @pytest.mark.contract
    async def test_call_checks_capabilities(self, adapter):
        """Call must deny without required capabilities"""
        for op_name, op in adapter.operations().items():
            test_input = generate_test_data(op.schema)
            # Call with empty capabilities
            result = await adapter.call(op_name, test_input, [])
            assert not result.success
            assert "capability" in result.error.lower()

# Concrete test classes for each adapter
class TestUIAAdapterContract(AdapterContractTests):
    @pytest.fixture
    def adapter(self):
        from arise.adapters.uia_adapter import UIAAdapter
        return UIAAdapter()

class TestPlaywrightAdapterContract(AdapterContractTests):
    @pytest.fixture
    def adapter(self):
        from arise.adapters.playwright_adapter import PlaywrightAdapter
        return PlaywrightAdapter()

class TestFilesystemAdapterContract(AdapterContractTests):
    @pytest.fixture
    def adapter(self):
        from arise.adapters.filesystem_adapter import FilesystemAdapter
        return FilesystemAdapter()
```

### 3.2 Model Router Contracts

```python
# tests/contract/test_model_router.py
import pytest
from arise.model_router import ModelRouter, CompletionRequest, CompletionResponse

class ModelRouterContractTests:
    """Contract tests for ModelRouter"""
    
    @pytest.fixture
    def router(self, runtime):
        return ModelRouter(runtime)
    
    @pytest.mark.contract
    async def test_complete_returns_response(self, router):
        request = CompletionRequest(
            messages=[{"role": "user", "content": "Hello"}],
            task_type="fast",
            max_tokens=100,
        )
        response = await router.complete("fast", request, {})
        assert isinstance(response, CompletionResponse)
        assert response.content is not None
        assert response.usage is not None
    
    @pytest.mark.contract
    async def test_complete_handles_empty_messages(self, router):
        request = CompletionRequest(messages=[], task_type="fast")
        response = await router.complete("fast", request, {})
        assert not response.success
        assert "empty" in response.error.lower()
    
    @pytest.mark.contract
    async def test_complete_respects_max_tokens(self, router):
        request = CompletionRequest(
            messages=[{"role": "user", "content": "Count to 1000"}],
            task_type="fast",
            max_tokens=10,
        )
        response = await router.complete("fast", request, {})
        assert response.usage.completion_tokens <= 10
    
    @pytest.mark.contract
    async def test_stream_returns_chunks(self, router):
        request = CompletionRequest(
            messages=[{"role": "user", "content": "Hello"}],
            task_type="fast",
        )
        chunks = []
        async for chunk in router.stream("fast", request, {}):
            chunks.append(chunk)
        assert len(chunks) > 0
        assert all(hasattr(c, 'delta') for c in chunks)
    
    @pytest.mark.contract
    async def test_provider_selection(self, router):
        # Should select appropriate provider for task type
        providers = await router.get_available_providers()
        assert len(providers) > 0
        assert all(hasattr(p, 'name') and hasattr(p, 'capabilities') for p in providers)
    
    @pytest.mark.contract
    async def test_fallback_on_failure(self, router, monkeypatch):
        # Mock primary provider failure
        async def failing_complete(*args, **kwargs):
            raise Exception("Provider unavailable")
        
        monkeypatch.setattr(router.providers["primary"], "complete", failing_complete)
        
        request = CompletionRequest(
            messages=[{"role": "user", "content": "Test"}],
            task_type="fast",
        )
        response = await router.complete("fast", request, {})
        # Should succeed via fallback
        assert response.success or response.provider != "primary"
```

### 3.3 Agent Protocol Contracts

```python
# tests/contract/test_agent_protocol.py
import pytest
from arise.agents.protocol import Agent, AgentTask, AgentResult, AgentCapability

class AgentProtocolTests:
    """Contract tests for all agents"""
    
    @pytest.fixture
    def agent(self):
        raise NotImplementedError
    
    @pytest.mark.contract
    async def test_agent_declares_capabilities(self, agent):
        caps = agent.capabilities()
        assert isinstance(caps, list)
        assert all(isinstance(c, AgentCapability) for c in caps)
    
    @pytest.mark.contract
    async def test_execute_returns_result(self, agent):
        task = AgentTask(
            id="test-1",
            objective="Test task",
            context={},
            granted_capabilities=agent.capabilities(),
        )
        result = await agent.execute(task)
        assert isinstance(result, AgentResult)
        assert result.task_id == "test-1"
        assert result.status in ("completed", "failed")
    
    @pytest.mark.contract
    async def test_execute_validates_capabilities(self, agent):
        task = AgentTask(
            id="test-2",
            objective="Test",
            context={},
            granted_capabilities=[],  # No capabilities granted
        )
        result = await agent.execute(task)
        assert result.status == "failed"
        assert "capability" in result.error.lower()
    
    @pytest.mark.contract
    async def test_cancel_stops_execution(self, agent):
        task = AgentTask(id="test-3", objective="Long task", context={}, granted_capabilities=agent.capabilities())
        exec_task = asyncio.create_task(agent.execute(task))
        await asyncio.sleep(0.1)
        await agent.cancel(task.id)
        result = await exec_task
        assert result.status in ("cancelled", "failed")
    
    @pytest.mark.contract
    async def test_health_check(self, agent):
        health = await agent.health_check()
        assert hasattr(health, 'healthy')
        assert hasattr(health, 'details')

# Test each agent
class TestResearchAgentProtocol(AgentProtocolTests):
    @pytest.fixture
    def agent(self, runtime):
        from arise.agents.research_agent import ResearchAgent
        return ResearchAgent(runtime)

class TestCodingAgentProtocol(AgentProtocolTests):
    @pytest.fixture
    def agent(self, runtime):
        from arise.agents.coding_agent import CodingAgent
        return CodingAgent(runtime)
```

---

## 4. Integration Testing

### 4.1 Component Integration

```python
# tests/integration/test_task_execution.py
import pytest
from arise.runtime import AppRuntime

class TestTaskExecutionIntegration:
    """Integration tests for task execution flow"""
    
    @pytest.fixture
    async def runtime(self, test_config):
        runtime = AppRuntime(test_config)
        await runtime.start()
        yield runtime
        await runtime.shutdown()
    
    @pytest.mark.integration
    async def test_simple_task_flow(self, runtime):
        """Test complete task: create -> execute -> complete"""
        # Create task
        task = await runtime.task_engine.create_task(
            objective="Create a test file",
            context={"path": "/tmp/test_output.txt"},
        )
        assert task.status == "QUEUED"
        
        # Execute
        await runtime.task_engine.execute_task(task.id)
        
        # Wait for completion
        completed_task = await runtime.task_engine.wait_for_task(task.id, timeout=30)
        assert completed_task.status == "COMPLETED"
        assert completed_task.result is not None
        
        # Verify file created
        import os
        assert os.path.exists("/tmp/test_output.txt")
    
    @pytest.mark.integration
    async def test_task_with_policy_approval(self, runtime):
        """Test task requiring R2+ approval"""
        task = await runtime.task_engine.create_task(
            objective="Install requests package",
            context={},
        )
        
        # Should be waiting for approval
        assert task.status == "WAITING_APPROVAL"
        
        # Approve
        await runtime.policy_engine.grant_approval(task.id, approved=True)
        
        # Execute
        await runtime.task_engine.execute_task(task.id)
        completed = await runtime.task_engine.wait_for_task(task.id, timeout=60)
        assert completed.status == "COMPLETED"
    
    @pytest.mark.integration
    async def test_task_checkpoint_recovery(self, runtime):
        """Test task can resume from checkpoint"""
        task = await runtime.task_engine.create_task(
            objective="Multi-step task",
            context={"steps": 5},
        )
        
        await runtime.task_engine.execute_task(task.id)
        
        # Simulate crash after step 2
        await runtime.task_engine.pause_task(task.id)
        checkpoint = await runtime.task_engine.get_checkpoint(task.id)
        assert checkpoint.step == 2
        
        # Restart runtime
        await runtime.shutdown()
        runtime2 = AppRuntime(test_config)
        await runtime2.start()
        
        # Recover
        recovered = await runtime2.task_engine.recover_task(task.id)
        assert recovered.status == "RUNNING"
        assert recovered.checkpoint.step == 2
```

### 4.2 Multi-Agent Integration

```python
# tests/integration/test_multi_agent.py
import pytest

class TestMultiAgentIntegration:
    """Integration tests for multi-agent coordination"""
    
    @pytest.mark.integration
    async def test_coordinator_delegates_to_specialists(self, runtime):
        """Test coordinator decomposes and delegates"""
        task = await runtime.task_engine.create_task(
            objective="Research Python async patterns and write example code",
            context={},
        )
        
        await runtime.task_engine.execute_task(task.id)
        completed = await runtime.task_engine.wait_for_task(task.id, timeout=120)
        
        assert completed.status == "COMPLETED"
        # Should have research + coding output
        assert "research" in completed.result
        assert "code" in completed.result
    
    @pytest.mark.integration
    async def test_agent_verification(self, runtime):
        """Test independent verification of agent output"""
        # Configure agent to produce known-bad output
        runtime.agent_registry.get("coding").inject_fault("missing_imports")
        
        task = await runtime.task_engine.create_task(
            objective="Write Python function to calculate fibonacci",
            context={},
        )
        
        await runtime.task_engine.execute_task(task.id)
        completed = await runtime.task_engine.wait_for_task(task.id, timeout=60)
        
        # Verification should catch the error
        assert completed.status == "COMPLETED"
        assert "verified" in completed.result
        assert completed.result["verified"] == True  # Fixed by verifier
    
    @pytest.mark.integration
    async def test_agent_failure_compensation(self, runtime):
        """Test compensation when agent fails"""
        runtime.agent_registry.get("browser").inject_fault("crash")
        
        task = await runtime.task_engine.create_task(
            objective="Navigate to example.com and extract title",
            context={},
        )
        
        await runtime.task_engine.execute_task(task.id)
        completed = await runtime.task_engine.wait_for_task(task.id, timeout=60)
        
        # Should either retry with different agent or fail gracefully
        assert completed.status in ("COMPLETED", "FAILED")
        if completed.status == "FAILED":
            assert "compensation" in completed.result
```

### 4.3 Voice Pipeline Integration

```python
# tests/integration/test_voice_pipeline.py
import pytest
import numpy as np

class TestVoicePipelineIntegration:
    """Integration tests for voice pipeline"""
    
    @pytest.mark.integration
    async def test_wake_word_to_response(self, runtime):
        """Test complete voice flow: wake -> ASR -> intent -> response -> TTS"""
        # Generate test audio with wake word
        wake_audio = generate_wake_word_audio("arise")
        command_audio = generate_speech_audio("What time is it?")
        
        # Feed to pipeline
        await runtime.voice_pipeline.feed_audio(wake_audio)
        await runtime.voice_pipeline.feed_audio(command_audio)
        
        # Wait for response
        response = await runtime.voice_pipeline.wait_for_response(timeout=10)
        
        assert response.transcript == "What time is it?"
        assert response.intent.type == "query"
        assert response.audio is not None
        assert len(response.audio) > 0
    
    @pytest.mark.integration
    async def test_barge_in(self, runtime):
        """Test barge-in during TTS playback"""
        # Start long response
        response_task = asyncio.create_task(
            runtime.voice_pipeline.speak("This is a very long response that should be interrupted...")
        )
        
        # Wait for speech to start
        await runtime.voice_pipeline.wait_for_speaking()
        
        # Barge in
        barge_audio = generate_speech_audio("Stop!")
        await runtime.voice_pipeline.feed_audio(barge_audio)
        
        # Original speech should be cancelled
        response = await response_task
        assert response.cancelled == True
        assert "Stop" in response.new_transcript
    
    @pytest.mark.integration
    async def test_multilingual(self, runtime):
        """Test English + Telugu support"""
        # English
        en_audio = generate_speech_audio("Hello", lang="en")
        await runtime.voice_pipeline.feed_audio(en_audio)
        en_response = await runtime.voice_pipeline.wait_for_response()
        assert en_response.lang == "en"
        
        # Telugu
        te_audio = generate_speech_audio("నమస్కారం", lang="te")
        await runtime.voice_pipeline.feed_audio(te_audio)
        te_response = await runtime.voice_pipeline.wait_for_response()
        assert te_response.lang == "te"
```

---

## 5. End-to-End Testing

### 5.1 Critical User Journeys

```python
# tests/e2e/test_critical_journeys.py
import pytest
from playwright.async_api import async_playwright

class TestCriticalJourneys:
    """End-to-end tests for critical user journeys"""
    
    @pytest.fixture
    async def app(self):
        """Launch full ARISE application"""
        async with async_playwright() as p:
            # Launch Tauri app
            app = await p.chromium.launch(
                executable_path="target/release/arise.exe",
                args=["--test-mode"],
            )
            yield app
            await app.close()
    
    @pytest.mark.e2e
    async def test_voice_command_to_desktop_action(self, app):
        """User says 'Open Chrome and go to GitHub' -> Chrome opens, navigates"""
        page = await app.new_page()
        
        # Click microphone button
        await page.click('[data-testid="mic-button"]')
        
        # Simulate voice input (inject audio)
        await page.evaluate("""
            () => window.testInjectAudio('open_chrome_github.wav')
        """)
        
        # Wait for Chrome to open and navigate
        await page.wait_for_selector('[data-testid="chrome-window"]', timeout=10000)
        await page.wait_for_url("**/github.com**", timeout=15000)
        
        # Verify
        title = await page.title()
        assert "GitHub" in title
    
    @pytest.mark.e2e
    async def test_scheduled_daily_briefing(self, app):
        """Daily briefing runs at scheduled time"""
        page = await app.new_page()
        
        # Navigate to scheduler
        await page.click('[data-testid="scheduler-tab"]')
        
        # Create daily briefing task
        await page.fill('[data-testid="task-name"]', "Daily Briefing")
        await page.fill('[data-testid="task-schedule"]', "0 8 * * *")
        await page.fill('[data-testid="task-objective"]', "Check email, calendar, and news")
        await page.click('[data-testid="save-task"]')
        
        # Trigger manually
        await page.click('[data-testid="run-now"]')
        
        # Wait for completion
        await page.wait_for_selector('[data-testid="task-completed"]', timeout=60000)
        
        # Verify output
        briefing = await page.text_content('[data-testid="briefing-output"]')
        assert "email" in briefing.lower()
        assert "calendar" in briefing.lower()
    
    @pytest.mark.e2e
    async def test_multi_agent_coding_task(self, app):
        """User requests code -> agents research, write, test, verify"""
        page = await app.new_page()
        
        # Submit coding task
        await page.fill('[data-testid="task-input"]', 
            "Create a Python CLI tool for managing TODO lists with add, list, complete commands")
        await page.click('[data-testid="submit-task"]')
        
        # Watch agent coordination
        await page.wait_for_selector('[data-testid="agent-research-working"]', timeout=5000)
        await page.wait_for_selector('[data-testid="agent-coding-working"]', timeout=30000)
        await page.wait_for_selector('[data-testid="agent-verification-working"]', timeout=45000)
        
        # Wait for completion
        await page.wait_for_selector('[data-testid="task-completed"]', timeout=120000)
        
        # Verify output
        code = await page.text_content('[data-testid="generated-code"]')
        assert "def add" in code
        assert "def list" in code
        assert "def complete" in code
        assert "argparse" in code or "click" in code
        
        # Verify tests pass
        test_results = await page.text_content('[data-testid="test-results"]')
        assert "passed" in test_results.lower()
```

### 5.2 E2E Test Harness

```python
# tests/e2e/harness.py
import asyncio
from playwright.async_api import async_playwright
from dataclasses import dataclass
from typing import Optional

@dataclass
class E2EContext:
    app: "PlaywrightApp"
    page: "Page"
    runtime_url: str = "http://localhost:8765"  # WebSocket bridge

class E2EHarness:
    """End-to-end test harness"""
    
    def __init__(self, app_path: str = "target/release/arise.exe"):
        self.app_path = app_path
        self.playwright = None
        self.browser = None
        self.context = None
    
    async def start(self) -> E2EContext:
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            executable_path=self.app_path,
            args=["--test-mode", "--remote-debugging-port=9222"],
        )
        self.context = await self.browser.new_context()
        page = await self.context.new_page()
        
        # Wait for app to be ready
        await page.wait_for_selector('[data-testid="app-ready"]', timeout=30000)
        
        return E2EContext(app=self, page=page)
    
    async def stop(self):
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
    
    async def inject_audio(self, audio_path: str):
        """Inject audio file into voice pipeline"""
        await self.context.page.evaluate(f"""
            () => window.testInjectAudio('{audio_path}')
        """)
    
    async def send_text_command(self, command: str):
        """Send text command via chat input"""
        await self.context.page.fill('[data-testid="chat-input"]', command)
        await self.context.page.press('[data-testid="chat-input"]', 'Enter')
    
    async def wait_for_task_completion(self, task_id: str, timeout: int = 60000):
        """Wait for task to complete"""
        await self.context.page.wait_for_selector(
            f'[data-testid="task-{task_id}-completed"]',
            timeout=timeout
        )
    
    async def get_task_result(self, task_id: str) -> dict:
        """Get task result from UI"""
        return await self.context.page.evaluate(f"""
            () => window.getTaskResult('{task_id}')
        """)
    
    async def simulate_scheduler_trigger(self, task_name: str):
        """Trigger scheduled task manually"""
        await self.context.page.click(f'[data-testid="task-{task_name}-run"]')
```

---

## 6. Chaos Engineering

### 6.1 Fault Injection

```python
# tests/chaos/fault_injector.py
import asyncio
import random
from enum import Enum
from dataclasses import dataclass
from typing import Callable, Any

class FaultType(Enum):
    LATENCY = "latency"
    ERROR = "error"
    TIMEOUT = "timeout"
    CRASH = "crash"
    NETWORK_PARTITION = "network_partition"
    RESOURCE_EXHAUSTION = "resource_exhaustion"

@dataclass
class FaultConfig:
    fault_type: FaultType
    probability: float = 0.1
    latency_ms: int = 1000
    error_message: str = "Injected fault"
    duration_seconds: int = 60

class FaultInjector:
    """Runtime fault injection for chaos testing"""
    
    def __init__(self):
        self.active_faults: Dict[str, FaultConfig] = {}
        self.original_functions: Dict[str, Callable] = {}
    
    def inject(self, target: str, config: FaultConfig):
        """Inject fault into target function"""
        # Store original
        module_name, func_name = target.rsplit(".", 1)
        module = __import__(module_name, fromlist=[func_name])
        self.original_functions[target] = getattr(module, func_name)
        
        # Create faulty wrapper
        async def faulty_wrapper(*args, **kwargs):
            if random.random() < config.probability:
                if config.fault_type == FaultType.LATENCY:
                    await asyncio.sleep(config.latency_ms / 1000)
                    return await self.original_functions[target](*args, **kwargs)
                elif config.fault_type == FaultType.ERROR:
                    raise Exception(config.error_message)
                elif config.fault_type == FaultType.TIMEOUT:
                    await asyncio.sleep(config.duration_seconds)
                    raise asyncio.TimeoutError()
                elif config.fault_type == FaultType.CRASH:
                    import os
                    os._exit(1)
            return await self.original_functions[target](*args, **kwargs)
        
        # Replace
        setattr(module, func_name, faulty_wrapper)
        self.active_faults[target] = config
    
    def remove(self, target: str):
        """Remove fault injection"""
        if target in self.original_functions:
            module_name, func_name = target.rsplit(".", 1)
            module = __import__(module_name, fromlist=[func_name])
            setattr(module, func_name, self.original_functions[target])
            del self.original_functions[target]
            del self.active_faults[target]
    
    def remove_all(self):
        for target in list(self.active_faults.keys()):
            self.remove(target)

# Pre-defined chaos scenarios
CHAOS_SCENARIOS = {
    "model_provider_flaky": {
        "arise.model_router.providers.openai.complete": FaultConfig(
            FaultType.ERROR, probability=0.3, error_message="Rate limited"
        ),
        "arise.model_router.providers.anthropic.complete": FaultConfig(
            FaultType.LATENCY, probability=0.2, latency_ms=5000
        ),
    },
    "voice_pipeline_degraded": {
        "arise.voice.asr.transcribe": FaultConfig(
            FaultType.ERROR, probability=0.2, error_message="Audio unclear"
        ),
        "arise.voice.tts.synthesize": FaultConfig(
            FaultType.LATENCY, probability=0.1, latency_ms=3000
        ),
    },
    "browser_unstable": {
        "arise.adapters.playwright_adapter.navigate": FaultConfig(
            FaultType.ERROR, probability=0.15, error_message="Navigation timeout"
        ),
        "arise.adapters.playwright_adapter.click": FaultConfig(
            FaultType.LATENCY, probability=0.1, latency_ms=2000
        ),
    },
    "memory_system_slow": {
        "arise.memory.query": FaultConfig(
            FaultType.LATENCY, probability=0.2, latency_ms=1000
        ),
        "arise.memory.consolidate": FaultConfig(
            FaultType.TIMEOUT, probability=0.05, duration_seconds=30
        ),
    },
}
```

### 6.2 Chaos Tests

```python
# tests/chaos/test_resilience.py
import pytest
from tests.chaos.fault_injector import FaultInjector, CHAOS_SCENARIOS

class TestChaosResilience:
    """Chaos engineering tests"""
    
    @pytest.fixture
    def fault_injector(self):
        injector = FaultInjector()
        yield injector
        injector.remove_all()
    
    @pytest.mark.chaos
    async def test_model_fallback_under_failure(self, runtime, fault_injector):
        """System should fallback when primary model provider fails"""
        # Inject failures
        for target, config in CHAOS_SCENARIOS["model_provider_flaky"].items():
            fault_injector.inject(target, config)
        
        # Execute multiple requests
        successes = 0
        for i in range(20):
            try:
                response = await runtime.model_router.complete("fast", 
                    CompletionRequest(messages=[{"role": "user", "content": f"Test {i}"}]), {})
                if response.success:
                    successes += 1
            except Exception:
                pass
        
        # Should have high success rate via fallback
        assert successes >= 15  # 75% success rate
    
    @pytest.mark.chaos
    async def test_voice_degraded_graceful(self, runtime, fault_injector):
        """Voice pipeline should degrade gracefully"""
        for target, config in CHAOS_SCENARIOS["voice_pipeline_degraded"].items():
            fault_injector.inject(target, config)
        
        # Test multiple voice interactions
        results = []
        for i in range(10):
            response = await runtime.voice_pipeline.process_voice(
                generate_speech_audio(f"Test command {i}")
            )
            results.append(response.success)
        
        # Should handle gracefully (not crash)
        assert all(r is not None for r in results)  # All returned something
        success_rate = sum(results) / len(results)
        assert success_rate >= 0.5  # At least 50% work
    
    @pytest.mark.chaos
    async def test_task_recovery_after_crash(self, runtime, fault_injector):
        """Tasks should recover after component crash"""
        # Start a long-running task
        task = await runtime.task_engine.create_task(
            objective="Multi-step research task",
            context={"steps": 10},
        )
        await runtime.task_engine.execute_task(task.id)
        
        # Wait for progress
        await asyncio.sleep(2)
        
        # Inject crash in model router
        fault_injector.inject(
            "arise.model_router.ModelRouter.complete",
            FaultInjector.FaultConfig(FaultInjector.FaultType.CRASH, probability=1.0)
        )
        
        # Wait for task to fail
        await asyncio.sleep(5)
        
        # Remove fault
        fault_injector.remove("arise.model_router.ModelRouter.complete")
        
        # Task should be recoverable
        recovered = await runtime.task_engine.recover_task(task.id)
        assert recovered.status in ("RUNNING", "QUEUED", "WAITING_APPROVAL")
    
    @pytest.mark.chaos
    async def test_resource_exhaustion_handling(self, runtime):
        """System should handle resource exhaustion"""
        # Fill memory
        memory_hogs = []
        try:
            while True:
                memory_hogs.append(bytearray(100 * 1024 * 1024))  # 100MB chunks
        except MemoryError:
            pass
        
        try:
            # Try to execute task under memory pressure
            task = await runtime.task_engine.create_task(
                objective="Simple task",
                context={},
            )
            await runtime.task_engine.execute_task(task.id)
            completed = await runtime.task_engine.wait_for_task(task.id, timeout=30)
            
            # Should either complete or fail gracefully
            assert completed.status in ("COMPLETED", "FAILED")
            if completed.status == "FAILED":
                assert "memory" in completed.error.lower() or "resource" in completed.error.lower()
        finally:
            memory_hogs.clear()
```

---

## 7. Performance Testing

### 7.1 Benchmark Tests

```python
# tests/performance/test_benchmarks.py
import pytest
import asyncio
import time
from tests.performance.benchmarks import PerformanceBenchmark, PERFORMANCE_THRESHOLDS

class TestPerformanceBenchmarks:
    """Performance regression tests"""
    
    @pytest.fixture
    def benchmark(self, runtime):
        return PerformanceBenchmark(runtime)
    
    @pytest.mark.performance
    async def test_all_benchmarks_pass_thresholds(self, benchmark):
        results = await benchmark.run_all()
        
        failures = []
        for result in results:
            threshold = PERFORMANCE_THRESHOLDS.get(result.name, {})
            
            if "p99" in threshold and result.p99 > threshold["p99"]:
                failures.append(f"{result.name}: p99 {result.p99:.3f}s > {threshold['p99']:.3f}s")
            
            if "throughput" in threshold and result.throughput < threshold["throughput"]:
                failures.append(f"{result.name}: throughput {result.throughput:.1f} < {threshold['throughput']:.1f}")
        
        if failures:
            pytest.fail("Performance regressions detected:\n" + "\n".join(failures))
    
    @pytest.mark.performance
    async def test_concurrent_task_handling(self, runtime):
        """Test handling multiple concurrent tasks"""
        # Create 20 tasks simultaneously
        tasks = []
        for i in range(20):
            task = await runtime.task_engine.create_task(
                objective=f"Simple task {i}",
                context={},
            )
            tasks.append(task)
        
        # Execute all
        start = time.time()
        for task in tasks:
            await runtime.task_engine.execute_task(task.id)
        
        # Wait for all
        completed = await asyncio.gather(*[
            runtime.task_engine.wait_for_task(t.id, timeout=60) for t in tasks
        ])
        
        elapsed = time.time() - start
        
        # All should complete
        assert all(c.status == "COMPLETED" for c in completed)
        # Should complete within reasonable time
        assert elapsed < 30  # 20 tasks in 30 seconds
    
    @pytest.mark.performance
    async def test_memory_under_load(self, runtime):
        """Test memory system under load"""
        # Insert 10000 memories
        for i in range(10000):
            await runtime.memory.store(
                kind="semantic",
                content=f"Fact {i}: Some factual information about topic {i}",
                metadata={"topic": f"topic_{i % 100}"}
            )
        
        # Query performance
        start = time.time()
        for i in range(100):
            results = await runtime.memory.query(f"topic_{i}", k=10)
            assert len(results) <= 10
        query_time = time.time() - start
        
        # 100 queries should complete quickly
        assert query_time < 5.0  # 50ms per query average
```

### 7.2 Load Testing

```python
# tests/performance/test_load.py
import pytest
import asyncio
from dataclasses import dataclass

@dataclass
class LoadTestResult:
    total_requests: int
    successful: int
    failed: int
    avg_latency: float
    p99_latency: float
    errors: dict

class LoadTester:
    def __init__(self, runtime):
        self.runtime = runtime
    
    async def run_load_test(
        self,
        duration_seconds: int = 60,
        target_rps: int = 10,
        task_generator: callable = None,
    ) -> LoadTestResult:
        """Run sustained load test"""
        latencies = []
        errors = {}
        successful = 0
        failed = 0
        
        async def worker():
            nonlocal successful, failed
            while not self._stop_event.is_set():
                start = time.time()
                try:
                    task = task_generator() if task_generator else {"objective": "test"}
                    t = await self.runtime.task_engine.create_task(**task)
                    await self.runtime.task_engine.execute_task(t.id)
                    completed = await self.runtime.task_engine.wait_for_task(t.id, timeout=30)
                    if completed.status == "COMPLETED":
                        successful += 1
                    else:
                        failed += 1
                        errors[completed.error] = errors.get(completed.error, 0) + 1
                except Exception as e:
                    failed += 1
                    errors[str(e)] = errors.get(str(e), 0) + 1
                
                latency = time.time() - start
                latencies.append(latency)
                
                # Rate limiting
                await asyncio.sleep(1.0 / target_rps)
        
        self._stop_event = asyncio.Event()
        workers = [asyncio.create_task(worker()) for _ in range(target_rps)]
        
        await asyncio.sleep(duration_seconds)
        self._stop_event.set()
        await asyncio.gather(*workers)
        
        latencies.sort()
        return LoadTestResult(
            total_requests=successful + failed,
            successful=successful,
            failed=failed,
            avg_latency=sum(latencies) / len(latencies) if latencies else 0,
            p99_latency=latencies[int(len(latencies) * 0.99)] if latencies else 0,
            errors=errors,
        )

@pytest.mark.load
async def test_sustained_load(runtime):
    """Test system under sustained load for 1 minute"""
    tester = LoadTester(runtime)
    result = await tester.run_load_test(
        duration_seconds=60,
        target_rps=5,
        task_generator=lambda: {"objective": "Create a file", "context": {"path": f"/tmp/load_test_{random.random()}.txt"}}
    )
    
    # Assert SLOs
    assert result.successful / result.total_requests >= 0.95  # 95% success rate
    assert result.p99_latency < 10.0  # P99 < 10s
    assert result.avg_latency < 3.0   # Avg < 3s
```

---

## 8. Security Testing

### 8.1 Security Test Suite

```python
# tests/security/test_security.py
import pytest
from tests.security.prompt_injection_corpus import INJECTION_ATTEMPTS

class TestPromptInjectionDefense:
    """Test prompt injection defense"""
    
    @pytest.mark.security
    @pytest.mark.parametrize("attempt", INJECTION_ATTEMPTS)
    async def test_injection_blocked(self, runtime, attempt):
        """Each injection attempt should be detected/sanitized"""
        analysis = runtime.prompt_defense.analyze(attempt.payload)
        
        if attempt.severity == "critical":
            assert analysis.detected, f"Failed to detect: {attempt.name}"
            assert analysis.confidence >= 0.7
        elif attempt.severity == "high":
            assert analysis.detected or attempt.category in ["social_eng"]
    
    @pytest.mark.security
    async def test_capability_enforcement(self, runtime):
        """Capabilities must be enforced at adapter boundary"""
        # Try to call filesystem write without capability
        adapter = runtime.filesystem_adapter
        result = await adapter.call("write", {"path": "/tmp/test.txt", "content": "test"}, [])
        assert not result.success
        assert "capability" in result.error.lower()
    
    @pytest.mark.security
    async def test_audit_log_immutability(self, runtime):
        """Audit log should be tamper-evident"""
        # Log some events
        for i in range(10):
            await runtime.audit_log.log("test_event", action=f"action_{i}")
        
        # Verify integrity
        result = await runtime.audit_log.verify_integrity()
        assert result.valid
        
        # Tamper with database
        import sqlite3
        conn = sqlite3.connect(runtime.audit_log.db_path)
        conn.execute("UPDATE audit_log SET action = 'TAMPERED' WHERE event_id = (SELECT event_id FROM audit_log LIMIT 1)")
        conn.commit()
        conn.close()
        
        # Should detect tampering
        result = await runtime.audit_log.verify_integrity()
        assert not result.valid
        assert len(result.errors) > 0
    
    @pytest.mark.security
    async def test_credential_isolation(self, runtime):
        """Credentials should not leak in logs or memory"""
        # Store credential
        await runtime.credential_manager.store_api_key("test_provider", "sk-secret123")
        
        # Check audit log doesn't contain secret
        events = await runtime.audit_log.query(limit=100)
        for event in events:
            assert "sk-secret123" not in str(event.context)
            assert "secret123" not in str(event.context)
        
        # Check memory dumps don't contain secret
        import gc
        for obj in gc.get_objects():
            try:
                if hasattr(obj, '__dict__'):
                    obj_str = str(obj.__dict__)
                    assert "sk-secret123" not in obj_str
            except Exception:
                pass
    
    @pytest.mark.security
    async def test_network_egress_control(self, runtime):
        """Network egress should be controlled by policy"""
        # Try to connect to non-allowlisted domain
        from arise.security.network_policy import NetworkPolicyEngine
        
        allowed = await runtime.network_policy.check_connection(
            capability="network.send",
            destination="evil.com",
            port=443,
        )
        assert not allowed
        
        # Allowlisted should work
        allowed = await runtime.network_policy.check_connection(
            capability="model.inference",
            destination="generativelanguage.googleapis.com",
            port=443,
        )
        assert allowed
```

### 8.2 Static Analysis

```yaml
# .github/workflows/security.yml
name: Security Analysis

on: [push, pull_request]

jobs:
  bandit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run Bandit
        run: |
          pip install bandit
          bandit -r src/ -f json -o bandit-report.json || true
      - name: Upload Bandit Report
        uses: actions/upload-artifact@v4
        with:
          name: bandit-report
          path: bandit-report.json

  semgrep:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run Semgrep
        uses: returntocorp/semgrep-action@v1
        with:
          config: >-
            p/security-audit
            p/secrets
            p/python
      - name: Upload Semgrep Results
        uses: actions/upload-artifact@v4
        with:
          name: semgrep-results
          path: semgrep-results.sarif

  pip-audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run pip-audit
        run: |
          pip install pip-audit
          pip-audit -r requirements.txt --format=json --output=pip-audit.json || true
      - name: Upload pip-audit
        uses: actions/upload-artifact@v4
        with:
          name: pip-audit
          path: pip-audit.json
```

---

## 9. Test Infrastructure

### 9.1 CI/CD Pipeline

```yaml
# .github/workflows/test.yml
name: Test Suite

on: [push, pull_request]

jobs:
  unit:
    name: Unit Tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install dependencies
        run: |
          pip install -e ".[dev]"
      - name: Run unit tests
        run: |
          pytest tests/unit -v --tb=short -x --cov=src/arise --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v3

  contract:
    name: Contract Tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install dependencies
        run: |
          pip install -e ".[dev]"
      - name: Run contract tests
        run: |
          pytest tests/contract -v --tb=short -m contract

  integration:
    name: Integration Tests
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install system deps
        run: |
          sudo apt-get update && sudo apt-get install -y python3-tk libnss3 libatk-bridge2.0-0
      - name: Install dependencies
        run: |
          pip install -e ".[dev]"
          playwright install chromium
      - name: Run integration tests
        run: |
          pytest tests/integration -v --tb=short -m integration --timeout=120

  e2e:
    name: E2E Tests
    runs-on: windows-latest  # Requires Windows for Tauri
    timeout-minutes: 60
    steps:
      - uses: actions/checkout@v4
      - name: Setup Rust
        uses: dtolnay/rust-toolchain@stable
      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: "20"
      - name: Build Tauri app
        run: |
          cd src-tauri
          cargo build --release
      - name: Run E2E tests
        run: |
          pytest tests/e2e -v --tb=short -m e2e --timeout=300

  performance:
    name: Performance Tests
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install dependencies
        run: |
          pip install -e ".[dev]"
      - name: Run performance tests
        run: |
          pytest tests/performance -v --tb=short -m performance --timeout=600
      - name: Benchmark comparison
        run: |
          python scripts/compare_benchmarks.py

  chaos:
    name: Chaos Tests
    runs-on: ubuntu-latest
    timeout-minutes: 60
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install dependencies
        run: |
          pip install -e ".[dev]"
      - name: Run chaos tests
        run: |
          pytest tests/chaos -v --tb=short -m chaos --timeout=1800

  security:
    name: Security Tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install dependencies
        run: |
          pip install -e ".[dev]"
      - name: Run security tests
        run: |
          pytest tests/security -v --tb=short -m security

  all-tests:
    name: All Tests Pass
    needs: [unit, contract, integration, e2e, performance, chaos, security]
    runs-on: ubuntu-latest
    steps:
      - run: echo "All test suites passed!"
```

### 9.2 Test Data Management

```python
# tests/fixtures/test_data.py
"""Test data generators and fixtures"""

import random
import string
from dataclasses import dataclass
from typing import List, Dict, Any

@dataclass
class TestScenario:
    name: str
    objective: str
    expected_steps: List[str]
    expected_capabilities: List[str]
    expected_risk_level: str

SCENARIOS = [
    TestScenario(
        name="simple_file_read",
        objective="Read the README.md file",
        expected_steps=["filesystem.read"],
        expected_capabilities=["filesystem.read"],
        expected_risk_level="R0",
    ),
    TestScenario(
        name="create_python_script",
        objective="Create a Python script that prints hello world",
        expected_steps=["filesystem.write", "shell.execute"],
        expected_capabilities=["filesystem.write", "shell.execute"],
        expected_risk_level="R1",
    ),
    TestScenario(
        name="web_research",
        objective="Research the latest Python 3.12 features",
        expected_steps=["browser.navigate", "browser.read", "memory.write"],
        expected_capabilities=["browser.navigate", "browser.read", "memory.write"],
        expected_risk_level="R1",
    ),
    TestScenario(
        name="install_package",
        objective="Install the requests library",
        expected_steps=["shell.execute"],
        expected_capabilities=["shell.execute"],
        expected_risk_level="R2",
    ),
    TestScenario(
        name="send_email",
        objective="Send email to team@company.com with subject 'Update'",
        expected_steps=["email.send"],
        expected_capabilities=["email.send"],
        expected_risk_level="R3",
    ),
]

def generate_random_string(length: int = 10) -> str:
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def generate_test_data(schema: dict) -> dict:
    """Generate valid test data from JSON schema"""
    # Simplified implementation
    if schema.get("type") == "object":
        result = {}
        for prop, prop_schema in schema.get("properties", {}).items():
            result[prop] = generate_test_data(prop_schema)
        return result
    elif schema.get("type") == "string":
        return "test_string"
    elif schema.get("type") == "integer":
        return 42
    elif schema.get("type") == "boolean":
        return True
    elif schema.get("type") == "array":
        return [generate_test_data(schema.get("items", {}))]
    return None
```

---

## 10. Test Metrics & Reporting

### 10.1 Coverage Targets

| Component | Line Coverage | Branch Coverage | Mutation Score |
|-----------|---------------|-----------------|----------------|
| Policy Engine | 95% | 90% | 85% |
| Task Engine | 90% | 85% | 80% |
| Model Router | 85% | 80% | 75% |
| Memory System | 90% | 85% | 80% |
| Voice Pipeline | 80% | 75% | 70% |
| Adapters | 85% | 80% | 75% |
| Agents | 85% | 80% | 75% |
| Security | 95% | 90% | 85% |
| **Overall** | **90%** | **85%** | **80%** |

### 10.2 Test Report Dashboard

```python
# scripts/test_report.py
"""Generate test report dashboard"""

import json
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List

@dataclass
class TestSuiteResult:
    name: str
    passed: int
    failed: int
    skipped: int
    duration: float
    coverage: Dict[str, float]

def generate_report():
    """Generate HTML test report"""
    results = {}
    
    for suite in ["unit", "contract", "integration", "e2e", "performance", "chaos", "security"]:
        report_path = Path(f"test-results/{suite}-report.json")
        if report_path.exists():
            with open(report_path) as f:
                data = json.load(f)
                results[suite] = TestSuiteResult(
                    name=suite,
                    passed=data.get("passed", 0),
                    failed=data.get("failed", 0),
                    skipped=data.get("skipped", 0),
                    duration=data.get("duration", 0),
                    coverage=data.get("coverage", {}),
                )
    
    # Generate HTML
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>ARISE Test Report</title>
        <style>
            table {{ border-collapse: collapse; width: 100%; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
            th {{ background-color: #f2f2f2; }}
            .pass {{ color: green; }}
            .fail {{ color: red; }}
            .skip {{ color: orange; }}
        </style>
    </head>
    <body>
        <h1>ARISE Test Report</h1>
        <table>
            <tr><th>Suite</th><th>Passed</th><th>Failed</th><th>Skipped</th><th>Duration</th><th>Coverage</th></tr>
    """
    
    for suite, result in results.items():
        total = result.passed + result.failed + result.skipped
        pass_rate = result.passed / total * 100 if total > 0 else 0
        coverage = result.coverage.get("line", 0) * 100
        
        html += f"""
            <tr>
                <td>{suite}</td>
                <td class="pass">{result.passed}</td>
                <td class="fail">{result.failed}</td>
                <td class="skip">{result.skipped}</td>
                <td>{result.duration:.1f}s</td>
                <td>{coverage:.1f}%</td>
            </tr>
        """
    
    html += """
        </table>
    </body>
    </html>
    """
    
    Path("test-report.html").write_text(html)
    print("Report generated: test-report.html")

if __name__ == "__main__":
    generate_report()
```

---

## 11. Test Execution Strategy

### 11.1 Local Development

```bash
# Quick feedback loop (< 30s)
pytest tests/unit -x --tb=short -q

# Full unit suite (< 2min)
pytest tests/unit --cov=src/arise

# Contract tests (< 30s)
pytest tests/contract -m contract

# Integration tests (< 5min)
pytest tests/integration -m integration

# Specific component
pytest tests/unit/test_policy_engine.py -v
pytest tests/integration/test_task_execution.py -v
```

### 11.2 Pre-commit Hooks

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: unit-tests
        name: Unit Tests (fast)
        entry: pytest tests/unit -x --tb=short -q --timeout=30
        language: system
        pass_filenames: false
        stages: [commit]
      - id: security-scan
        name: Security Scan
        entry: bandit -r src/ -q
        language: system
        pass_filenames: false
        stages: [commit]
```

### 11.3 Release Gates

| Gate | Criteria |
|------|----------|
| **Merge to main** | All unit + contract tests pass, coverage >= 85% |
| **Release candidate** | All integration + e2e pass, performance within 10% of baseline |
| **Production release** | All chaos + security pass, no critical vulnerabilities |

---

## 12. Open Testing Decisions

| Decision | Options | Considerations |
|----------|---------|----------------|
| E2E on Windows only | Windows runner / Cross-platform Tauri | Tauri runs on Windows; need Windows for UIA |
| Browser for E2E | Playwright / Selenium / CDP | Playwright best for modern web |
| Load testing | Locust / k6 / Custom | Custom integrates with our runtime |
| Mutation testing | mutmut / Cosmic Ray | mutmut: Python-native |
| Property-based | hypothesis / quickcheck | hypothesis: mature, good shrinking |
| Visual regression | Percy / Chromatic / Custom | Custom: screenshot + pixelmatch |