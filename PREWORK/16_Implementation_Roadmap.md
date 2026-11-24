# ARISE — Implementation Roadmap

## Overview

This document provides a detailed, phased implementation roadmap for ARISE, translating the architectural design into actionable milestones with dependencies, resource requirements, and success criteria.

---

## 1. Roadmap Principles

| Principle | Application |
|-----------|-------------|
| **Security First** | No feature ships without security review |
| **Vertical Slices** | Deliver end-to-end user value each phase |
| **Test-Driven** | Tests written before/with implementation |
| **Local-First** | No external dependencies for core features |
| **Incremental Deployment** | Each phase deployable to user machine |
| **Rollback Ready** | Every change reversible |

---

## 2. Phase Overview

```
Phase 0: Foundation (Weeks 1-2)     → Dev environment, CI/CD, security baseline
Phase 1: Security Core (Weeks 3-5)  → Credentials, prompt defense, audit, network
Phase 2: Task & Policy (Weeks 4-6)  → Complete task engine, policy, approvals
Phase 3: Voice Pipeline (Weeks 5-8) → Wake word → ASR → Intent → TTS (validated)
Phase 4: Multi-Agent (Weeks 6-10)   → Coordinator + 11 specialists + verification
Phase 5: Memory System (Weeks 7-9)  → 5 kinds, consolidation, governance, retrieval
Phase 6: Desktop Automation (Weeks 8-10) → UIA + Playwright + CV/OCR + cross-app
Phase 7: Communication (Weeks 9-11) → Email, Calendar, Messaging
Phase 8: Creative (Weeks 10-12)     → Image, Video, Audio generation
Phase 9: Research (Weeks 9-11)      → Brave, Academic, Code search
Phase 10: Observability (Weeks 11-13) → Metrics, health, tracing, chaos, backup
Phase 11: Polish & Ship (Weeks 12-14) → E2E tests, perf, docs, installer
```

---

## 3. Detailed Phase Plans

### Phase 0: Foundation (Weeks 1-2)

#### Goals
- Reproducible development environment
- CI/CD pipeline with all test stages
- Baseline security configuration
- Architecture decision records started

#### Deliverables

| ID | Deliverable | Owner | Criteria |
|----|-------------|-------|----------|
| P0.1 | Dev container / setup script | Platform | `./scripts/setup_dev.sh` works on clean Windows |
| P0.2 | GitHub Actions CI/CD | Platform | Unit, contract, integration, e2e, perf, chaos, security all run |
| P0.3 | Pre-commit hooks | Platform | Ruff, mypy, bandit, unit tests on commit |
| P0.4 | Dependency management | Platform | pip-audit, cargo-audit, npm audit in CI |
| P0.5 | Configuration schema | Platform | Pydantic settings with validation, env overrides |
| P0.6 | Logging & tracing setup | Platform | Structured JSON logs, correlation IDs |
| P0.7 | ADR template & first 5 ADRs | Arch | 001-architecture, 002-security, 003-voice, 004-agents, 005-memory |

#### Dependencies
- None (starts immediately)

#### Risks
- Windows dev environment complexity → Use dev containers
- CI runner costs → Use self-hosted for Windows e2e

---

### Phase 1: Security Core (Weeks 3-5)

#### Goals
- Complete security foundation per 12_Security_and_Permissions.md
- All credentials in Windows Credential Manager
- Prompt injection defense active
- Immutable audit logging
- Network egress control

#### Deliverables

| ID | Deliverable | Owner | Criteria |
|----|-------------|-------|----------|
| P1.1 | Windows Credential Manager wrapper | Security | `credential_manager.store/retrieve/delete` works, DPAPI encrypted |
| P1.2 | Credential categories implemented | Security | api_keys, grants, oauth_tokens, ssh_keys, certificates |
| P1.3 | Capability system complete | Security | All Capability enums, CapabilityGrant, CapabilityScope |
| P1.4 | Policy engine with R0-R4 | Security | Risk assessment, approval workflows, grant management |
| P1.5 | Prompt injection defense | Security | Pattern-based + instruction hierarchy, balanced mode default |
| P1.6 | Audit log with hash chain | Security | Immutable, tamper-evident, queryable, integrity verification |
| P1.7 | Network egress control | Security | Allow-list policy, certificate pinning for critical domains |
| P1.8 | Security lockdown mode | Security | Emergency activation, revokes temp grants, blocks network |
| P1.9 | Security tests (90% coverage) | QA | Unit + contract + integration for all security components |

#### Dependencies
- P0.1, P0.2 (CI for security tests)

#### Acceptance Criteria
- [ ] No secrets in code, logs, or memory dumps
- [ ] Prompt injection attempts detected and logged
- [ ] Audit log integrity verified on startup
- [ ] Network connections blocked without capability
- [ ] Lockdown mode activates and deactivates cleanly

---

### Phase 2: Task Engine & Policy Integration (Weeks 4-6)

#### Goals
- Complete 28-state task lifecycle with checkpoint persistence
- Full policy integration at task boundaries
- Approval UI in frontend
- Scheduler foundation

#### Deliverables

| ID | Deliverable | Owner | Criteria |
|----|-------------|-------|----------|
| P2.1 | Complete 28-state machine | Backend | All states, transitions, validation, persistence |
| P2.2 | Checkpoint serialization | Backend | Save/restore at every WAITING_* state, JSON + SQLite |
| P2.3 | Task-engine ↔ policy integration | Backend | Risk assessment on create, capability checks on execute |
| P2.4 | Approval workflow | Backend + Frontend | UI prompt for R2+, timeout, grant/revoke persistence |
| P2.5 | Scheduler core | Backend | Cron expression parsing, next-run calculation, persistence |
| P2.6 | Scheduled task management UI | Frontend | Create, edit, enable/disable, run now, history |
| P2.7 | Task checkpoint recovery | Backend | Resume from last checkpoint after crash/restart |
| P2.8 | Saga compensation for multi-step | Backend | Rollback handlers, compensation execution |

#### Dependencies
- P1.3, P1.4 (Policy engine)

#### Acceptance Criteria
- [ ] Task survives process restart at any WAITING_* state
- [ ] R2+ tasks require approval before execution
- [ ] Scheduled tasks fire at correct times (±30s)
- [ ] Failed multi-step tasks execute compensations

---

### Phase 3: Voice Pipeline (Weeks 5-8)

#### Goals
- Complete dormant-first voice pipeline
- Validated on real Windows hardware
- Barge-in, multilingual, session resumption working
- <500ms P99 wake-word detection

#### Deliverables

| ID | Deliverable | Owner | Criteria |
|----|-------------|-------|----------|
| P3.1 | Porcupine wake word detector | Voice | Sensitivity tuning, multiple keywords, low CPU |
| P3.2 | Sherpa-ONNX VAD + ASR streaming | Voice | Real-time, partial results, English + Telugu |
| P3.3 | Intent classification | Voice | <50ms, integrates with policy for risk |
| P3.4 | Gemini Live API client | Voice | Session management, 30-min resumption tokens |
| P3.5 | TTS fallback chain | Voice | ElevenLabs → OpenAI → Piper, streaming |
| P3.6 | CPAL audio routing | Voice | Cross-platform, device selection, echo cancellation |
| P3.7 | Voice state machine | Voice | DORMANT→DETECTING→LISTENING→PROCESSING→SPEAKING |
| P3.8 | Barge-in implementation | Voice | Interrupt TTS, cancel model inference, new ASR |
| P3.9 | Multilingual support (EN/TE) | Voice | Language detection, per-language models |
| P3.10 | Privacy modes | Voice | STANDARD, PRIVATE, LOCAL_ONLY, OFFLINE |
| P3.11 | Voice pipeline integration tests | QA | E2E on Windows hardware, latency benchmarks |

#### Dependencies
- P1.1 (API keys in Credential Manager)
- P2.1 (Task engine for voice-initiated tasks)

#### Acceptance Criteria
- [ ] Wake word detects "Arise" in <100ms P99 on target hardware
- [ ] ASR accuracy >90% for clear speech (EN), >80% (TE)
- [ ] Barge-in stops TTS within 200ms
- [ ] Session resumes after 25-min pause
- [ ] LOCAL_ONLY mode works without internet

---

### Phase 4: Multi-Agent Platform (Weeks 6-10)

#### Goals
- Central Coordinator with full orchestration flow
- 11 specialist agents implemented
- Independent verification working
- Agent health monitoring

#### Deliverables

| ID | Deliverable | Owner | Criteria |
|----|-------------|-------|----------|
| P4.1 | Central Coordinator | Agents | Understand→Decompose→Plan→Execute→Integrate→Verify |
| P4.2 | Research Agent | Agents | Multi-source search, cross-verification, citations |
| P4.3 | Coding Agent | Agents | Read→Plan→Write→Test→Lint→Verify, repo-aware |
| P4.4 | Browser Agent | Agents | Navigate→Interact→Extract→Trace, Playwright pool |
| P4.5 | Filesystem Agent | Agents | Read/Write/Search/Index, path-scoped capabilities |
| P4.6 | System Agent | Agents | Process/Registry/Service control, scoped |
| P4.7 | Communications Agent | Agents | Email/Calendar/Message, OAuth token management |
| P4.8 | Creative Agent | Agents | Image/Video/Audio generation, prompt engineering |
| P4.9 | Memory Agent | Agents | Store/Query/Consolidate/Govern, cross-kind |
| P4.10 | Projects Agent | Agents | Project CRUD, task linking, progress tracking |
| P4.11 | Desktop UI Agent | Agents | UIA/Playwright/CV perception, cross-app coordination |
| P4.12 | Verification Agent | Agents | Independent output verification, fault detection |
| P4.13 | Agent registry & health | Agents | Registration, heartbeats, auto-restart, metrics |
| P4.14 | Delegation protocol | Agents | Context scoping, capability grants, result contracts |
| P4.15 | Multi-agent integration tests | QA | Complex tasks with 3+ agents, verification |

#### Dependencies
- P2.1 (Task engine for agent tasks)
- P3.10 (Voice can trigger agents)
- P5.1 (Memory for agent context)

#### Acceptance Criteria
- [ ] Coordinator decomposes "Research X and write code" into Research→Coding→Verification
- [ ] Each agent only uses granted capabilities
- [ ] Verification agent catches injected bugs in coding output
- [ ] Failed agent triggers compensation or retry with different agent
- [ ] Agent health monitoring detects and restarts stuck agents

---

### Phase 5: Memory System (Weeks 7-9)

#### Goals
- 5 memory kinds with distinct characteristics
- Consolidation pipeline running automatically
- Cross-kind retrieval with re-ranking
- Governance: PII, retention, user control

#### Deliverables

| ID | Deliverable | Owner | Criteria |
|----|-------------|-------|----------|
| P5.1 | ChromaDB vector stores (5 collections) | Memory | Semantic, Episodic, Procedural, Preference, Working |
| P5.2 | SQLite FTS5 for keyword search | Memory | BM25 ranking, filters, joins with vector |
| P5.3 | Consolidation pipeline | Memory | Working→Episodic (hourly), Episodic summarization (daily), Procedural reinforcement (weekly) |
| P5.4 | Preference conflict resolution | Memory | Last-write-wins + user confirmation for conflicts |
| P5.5 | Cleanup & retention | Memory | TTL per kind, PII auto-detection, size limits |
| P5.6 | Cross-kind retrieval | Memory | Vector + FTS + MMR re-ranking, citations |
| P5.7 | PII detection (Presidio) | Memory | Detect: names, emails, phones, keys, addresses |
| P5.8 | User control interface | Memory + Frontend | Inspect, correct, export, import, delete all |
| P5.9 | Memory governance policies | Memory | Configurable retention, encryption, access control |

#### Dependencies
- P1.1 (Credentials for embedding models if cloud)
- P4.9 (Memory agent uses these APIs)

#### Acceptance Criteria
- [ ] Working memory promoted to episodic after 1 hour
- [ ] Episodic memories summarized daily with <10% info loss
- [ ] Procedural skills reinforced from successful task patterns
- [ ] PII detected and flagged before storage
- [ ] User can export all memory as JSONL in <5s
- [ ] Cross-kind query returns relevant results with citations

---

### Phase 6: Desktop Automation (Weeks 8-10)

#### Goals
- Hybrid automation: UIA (native) + Playwright (web/Electron) + CV/OCR (fallback)
- Perception hierarchy resolver
- Evidence capture
- Cross-app coordination

#### Deliverables

| ID | Deliverable | Owner | Criteria |
|----|-------------|-------|----------|
| P6.1 | UIA adapter production-ready | Automation | Element caching, evidence screenshots, error recovery |
| P6.2 | Playwright adapter production-ready | Automation | Browser pooling, CDP session reuse, trace collection |
| P6.3 | CV/OCR fallback adapter | Automation | OpenCV template matching, Tesseract OCR, confidence scoring |
| P6.4 | Perception hierarchy resolver | Automation | UIA → Playwright → CV, automatic fallback |
| P6.5 | Evidence capture system | Automation | Screenshots + annotations + metadata per action |
| P6.6 | Cross-app coordination | Automation | Clipboard, drag-drop, DDE, window management |
| P6.7 | Desktop UI agent integration | Automation | Uses all three backends seamlessly |
| P6.8 | Automation integration tests | QA | Real apps: Notepad, Chrome, VS Code, Explorer, Teams |

#### Dependencies
- P2.1 (Task engine for automation tasks)
- P4.11 (Desktop UI agent consumes adapters)

#### Acceptance Criteria
- [ ] UIA finds element in Notepad in <50ms P99
- [ ] Playwright navigates and extracts in <2s P99
- [ ] CV/OCR fallback activates when UIA/Playwright fail
- [ ] Evidence captured for every automation action
- [ ] Copy from Chrome, paste into Notepad works reliably

---

### Phase 7: Communication Adapters (Weeks 9-11)

#### Goals
- Email (Microsoft Graph + IMAP/SMTP)
- Calendar (Graph + CalDAV)
- Messaging (Slack + Discord)

#### Deliverables

| ID | Deliverable | Owner | Criteria |
|----|-------------|-------|----------|
| P7.1 | Email adapter | Comm | Send/read/search, OAuth2, attachment handling |
| P7.2 | Calendar adapter | Comm | Read/write events, recurring, timezone handling |
| P7.3 | Messaging adapter | Comm | Slack Bot API, Discord Bot API, send/read/react |
| P7.4 | Communications agent integration | Comm | Uses all three, unified interface |
| P7.5 | OAuth token management | Comm | Auto-refresh, secure storage in Credential Manager |

#### Dependencies
- P1.1 (OAuth tokens in Credential Manager)
- P4.7 (Communications agent)

#### Acceptance Criteria
- [ ] Send email with attachment via Graph API
- [ ] Create calendar event with attendees
- [ ] Post message to Slack channel
- [ ] Tokens auto-refresh without user intervention

---

### Phase 8: Creative Adapters (Weeks 10-12)

#### Goals
- Image generation (DALL-E 3, Stable Diffusion)
- Video generation (Runway, Pika, local)
- Audio generation (ElevenLabs, OpenAI TTS, Piper)

#### Deliverables

| ID | Deliverable | Owner | Criteria |
|----|-------------|-------|----------|
| P8.1 | Image generation adapter | Creative | DALL-E 3 + SDXL, prompt enhancement, variations |
| P8.2 | Video generation adapter | Creative | Runway Gen-2 API, prompt→video, status polling |
| P8.3 | Audio generation adapter | Creative | ElevenLabs + OpenAI TTS + Piper, voice cloning |
| P8.4 | Creative agent integration | Creative | Unified interface, style presets, batch generation |
| P8.5 | Asset management | Creative | Local storage, metadata, versioning |

#### Dependencies
- P1.1 (API keys)
- P4.8 (Creative agent)

#### Acceptance Criteria
- [ ] Generate image from prompt in <10s (DALL-E) / <30s (SD local)
- [ ] Generate 5s video from prompt in <60s
- [ ] Clone voice and speak text in <5s

---

### Phase 9: Research Adapters (Weeks 9-11)

#### Goals
- Web search (Brave API)
- Academic search (Semantic Scholar, arXiv)
- Code search (GitHub, Sourcegraph)

#### Deliverables

| ID | Deliverable | Owner | Criteria |
|----|-------------|-------|----------|
| P9.1 | Web search adapter | Research | Brave API, pagination, result ranking |
| P9.2 | Academic search adapter | Research | Semantic Scholar + arXiv, citation graph |
| P9.3 | Code search adapter | Research | GitHub Code Search, regex, language filters |
| P9.4 | Research agent integration | Research | Multi-source, cross-verification, synthesis |
| P9.5 | Citation management | Research | Auto-cite, bibliography export |

#### Dependencies
- P1.1 (API keys)
- P4.2 (Research agent)
- P5.6 (Memory for citations)

#### Acceptance Criteria
- [ ] Web search returns 10 relevant results in <2s
- [ ] Academic search finds papers with citations
- [ ] Code search finds functions across repos
- [ ] Research agent produces cited report

---

### Phase 10: Observability & Hardening (Weeks 11-13)

#### Goals
- Production-grade observability
- Chaos engineering maturity
- Backup/restore
- Performance baselines

#### Deliverables

| ID | Deliverable | Owner | Criteria |
|----|-------------|-------|----------|
| P10.1 | Prometheus metrics | Platform | Custom metrics, /metrics endpoint, Grafana dashboards |
| P10.2 | Health checks | Platform | Liveness, readiness, dependency checks |
| P10.3 | Distributed tracing | Platform | OpenTelemetry, W3C trace context, Jaeger export |
| P10.4 | Structured logging | Platform | JSON, correlation IDs, log levels, rotation |
| P10.5 | Performance benchmarks | Platform | Automated in CI, regression detection |
| P10.6 | Chaos engineering suite | Platform | Fault injector, scenarios, automated runs |
| P10.7 | Backup/restore system | Platform | Encrypted backups, point-in-time recovery, DR test |
| P10.8 | Resource governor tuning | Platform | Limits validated under load |
| P10.9 | Security hardening review | Security | Penetration test, dependency audit, config review |

#### Dependencies
- All previous phases (observability wraps everything)

#### Acceptance Criteria
- [ ] Dashboards show real-time system health
- [ ] Alert fires within 30s of SLO breach
- [ ] Chaos scenario "model provider down" passes
- [ ] Backup restores full state in <5min
- [ ] Performance within 10% of baselines

---

### Phase 11: Polish & Ship (Weeks 12-14)

#### Goals
- Complete E2E test coverage
- Performance optimization
- Documentation
- Installer & auto-update

#### Deliverables

| ID | Deliverable | Owner | Criteria |
|----|-------------|-------|----------|
| P11.1 | E2E test suite complete | QA | All 10 critical journeys passing |
| P11.2 | Performance optimization | Platform | All SLOs met with margin |
| P11.3 | User documentation | Docs | Getting started, config, troubleshooting |
| P11.4 | Developer documentation | Docs | Architecture, APIs, contribution guide |
| P11.5 | Windows installer (MSI) | Platform | Signed, auto-update, silent install |
| P11.6 | Auto-update mechanism | Platform | Delta updates, rollback, channel selection |
| P11.7 | Telemetry opt-in | Platform | Anonymous usage stats, crash reports |
| P11.8 | Accessibility audit | Frontend | WCAG 2.1 AA, screen reader, keyboard nav |
| P11.9 | Release checklist | All | Security sign-off, perf sign-off, QA sign-off |

#### Dependencies
- All previous phases

#### Acceptance Criteria
- [ ] Installer works on clean Windows 10/11
- [ ] Auto-update applies without restart (mostly)
- [ ] All critical journeys pass in CI
- [ ] Documentation complete and accurate
- [ ] Accessibility score >90%

---

## 4. Resource Allocation

### 4.1 Team Structure (3 Engineers)

| Role | Focus Areas | Phases |
|------|-------------|--------|
| **Engineer A (Backend Lead)** | Task engine, policy, security, model router, scheduler | P0, P1, P2, P10 |
| **Engineer B (Agents & Voice)** | Multi-agent, voice pipeline, memory, research | P3, P4, P5, P9 |
| **Engineer C (Automation & Frontend)** | Desktop automation, communication, creative, Tauri/React | P6, P7, P8, P11 |

### 4.2 Shared Responsibilities

| Area | Owner | Backup |
|------|-------|--------|
| CI/CD | Engineer A | Engineer C |
| Security reviews | Engineer A | All |
| Code reviews | Rotating | - |
| Documentation | Engineer C | Engineer B |
| Release engineering | Engineer A | Engineer C |

---

## 5. Milestone Calendar

```
Week 1-2:   ████ P0 Foundation
Week 3-5:      ███████ P1 Security Core
Week 4-6:        ███████ P2 Task & Policy
Week 5-8:          ██████████ P3 Voice Pipeline
Week 6-10:            ████████████████ P4 Multi-Agent
Week 7-9:              ██████████ P5 Memory
Week 8-10:                ██████████ P6 Desktop Automation
Week 9-11:                  ██████████ P7 Communication
Week 10-12:                   ██████████ P8 Creative
Week 9-11:                    ██████████ P9 Research
Week 11-13:                       ██████████ P10 Observability
Week 12-14:                          ██████████ P11 Polish & Ship

TOTAL: 14 weeks (3.5 months) with 3 engineers
```

---

## 6. Risk Mitigation

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Voice pipeline fails on target hardware | High | High | Start P3.11 validation in Week 5, have cloud fallback |
| UIA flakiness blocks automation | High | Medium | Invest in P6.1 element caching, CV fallback early |
| Agent coordination complexity | Medium | High | Build P4.1 incrementally, test each agent in isolation |
| Memory consolidation performance | Medium | Medium | Profile early (P5.3), use incremental processing |
| Tauri 2 breaking changes | Low | High | Pin version, monitor releases, allocate buffer in P11 |
| Windows Credential Manager permissions | Low | High | Test on clean VMs, document fallback |
| API provider deprecation | Medium | Medium | Abstraction layers, multiple providers per capability |

---

## 7. Go/No-Go Gates

| Gate | Criteria | Decision |
|------|----------|----------|
| **End of P1** | Security review passes, no critical vulns | Proceed to P2/P3 |
| **End of P3** | Voice P99 <500ms on target hardware | Proceed to P4 (voice-triggered agents) |
| **End of P4** | 3 agents + coordinator + verification working | Proceed to P5/P6 |
| **End of P6** | Automation works on 5 real apps | Proceed to P7/P8/P9 |
| **End of P10** | All SLOs met, chaos passes, backup restores | Proceed to P11 |
| **End of P11** | All gates pass, installer works, docs complete | **SHIP** |

---

## 8. Budget Estimate

| Category | Cost (USD) | Notes |
|----------|------------|-------|
| **Engineering (3 × 14 weeks)** | $180,000 | $150/hr × 40hr × 14wk × 3 |
| **Cloud APIs (dev/test)** | $5,000 | Gemini, OpenAI, ElevenLabs, Brave |
| **Windows CI runners** | $2,000 | GitHub Actions Windows + self-hosted |
| **Code signing cert** | $500 | EV cert for installer |
| **Penetration test** | $10,000 | Third-party security audit |
| **Total** | **~$197,500** | |

---

## 9. Success Metrics

### 9.1 Technical Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Test coverage | >90% | CI coverage report |
| Critical journey pass rate | 100% | E2E test results |
| P99 voice latency | <500ms | Benchmark suite |
| P99 task creation | <200ms | Benchmark suite |
| Memory growth | <100MB/day | Long-running test |
| Crash rate | <0.1% | Telemetry (opt-in) |

### 9.2 User Experience Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Time to first successful task | <2 min | User study |
| Voice command success rate | >90% | Analytics |
| Task completion rate | >95% | Task engine stats |
| User-reported bugs | <5/week | Support channel |

---

## 10. Post-Launch Roadmap (Months 4-6)

| Month | Focus |
|-------|-------|
| **Month 4** | Bug fixes, performance tuning, user feedback integration |
| **Month 5** | Plugin system design, community extensions, marketplace |
| **Month 6** | Advanced agents (data analysis, ML training), team features |

---

*This roadmap is a living document. Update at each phase gate based on learnings.*