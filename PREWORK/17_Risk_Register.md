# ARISE — Risk Register

## Overview

This document captures all identified risks for the ARISE project, their assessment, mitigation strategies, and ownership. Risks are tracked throughout the project lifecycle and reviewed at each phase gate.

---

## 1. Risk Classification

### 1.1 Impact Scale

| Level | Score | Description |
|-------|-------|-------------|
| **Critical** | 5 | Project failure, data loss, security breach, legal liability |
| **High** | 4 | Major feature delayed, significant rework, user trust loss |
| **Medium** | 3 | Feature degradation, schedule slip, technical debt increase |
| **Low** | 2 | Minor inconvenience, workaround exists |
| **Negligible** | 1 | Cosmetic issue, no functional impact |

### 1.2 Probability Scale

| Level | Score | Description |
|-------|-------|-------------|
| **Almost Certain** | 5 | >90% chance, has occurred in similar projects |
| **Likely** | 4 | 60-90% chance, strong indicators |
| **Possible** | 3 | 30-60% chance, could occur |
| **Unlikely** | 2 | 10-30% chance, low indicators |
| **Rare** | 1 | <10% chance, theoretical |

### 1.3 Risk Score = Impact × Probability

| Score | Rating | Action |
|-------|--------|--------|
| 20-25 | **Extreme** | Immediate mitigation required, executive visibility |
| 15-19 | **High** | Active mitigation, weekly review |
| 10-14 | **Medium** | Planned mitigation, bi-weekly review |
| 5-9 | **Low** | Monitor, monthly review |
| 1-4 | **Minimal** | Accept, quarterly review |

---

## 2. Risk Register

### 2.1 Technical Risks

| ID | Risk | Impact | Probability | Score | Rating | Owner | Status |
|----|------|--------|-------------|-------|--------|-------|--------|
| **T-001** | Windows UIA automation unreliable on target apps (Office, browsers, Electron) | 5 | 4 | 20 | Extreme | Eng-C | Active |
| **T-002** | Voice pipeline fails to meet latency targets on consumer hardware | 4 | 4 | 16 | High | Eng-B | Active |
| **T-003** | Sherpa-ONNX / Porcupine model compatibility issues with Python 3.12+ | 4 | 3 | 12 | Medium | Eng-B | Monitoring |
| **T-004** | Playwright browser version drift breaks automation | 3 | 4 | 12 | Medium | Eng-C | Active |
| **T-005** | Multi-agent coordination deadlocks or livelocks | 4 | 3 | 12 | Medium | Eng-B | Planned |
| **T-006** | Memory system unbounded growth causes OOM | 5 | 3 | 15 | High | Eng-B | Active |
| **T-007** | Model router circuit breakers misconfigured → cascade failures | 4 | 3 | 12 | Medium | Eng-A | Planned |
| **T-008** | ChromaDB vector store corruption or performance degradation | 4 | 2 | 8 | Low | Eng-B | Monitoring |
| **T-009** | Tauri 2 / Rust / Node version incompatibility | 3 | 2 | 6 | Low | Eng-C | Monitoring |
| **T-010** | CV/OCR fallback insufficient for critical automation paths | 3 | 3 | 9 | Low | Eng-C | Planned |
| **T-011** | Cross-app coordination (clipboard, drag-drop) flaky | 3 | 3 | 9 | Low | Eng-C | Planned |
| **T-012** | Local LLM inference too slow for interactive use | 3 | 3 | 9 | Low | Eng-B | Monitoring |

### 2.2 Security Risks

| ID | Risk | Impact | Probability | Score | Rating | Owner | Status |
|----|------|--------|-------------|-------|--------|-------|--------|
| **S-001** | Prompt injection bypasses defenses → unauthorized actions | 5 | 3 | 15 | High | Eng-A | Active |
| **S-002** | Credential Manager access fails on some Windows configurations | 4 | 3 | 12 | Medium | Eng-A | Planned |
| **S-003** | Audit log tampering not detected | 5 | 2 | 10 | Medium | Eng-A | Planned |
| **S-004** | Network egress control bypassed via DNS tunneling | 4 | 2 | 8 | Low | Eng-A | Planned |
| **S-005** | Capability grant escalation via confused deputy | 4 | 2 | 8 | Low | Eng-A | Planned |
| **S-006** | Memory PII detection misses sensitive data | 4 | 3 | 12 | Medium | Eng-B | Planned |
| **S-007** | Supply chain attack via compromised dependency | 5 | 2 | 10 | Medium | Eng-A | Active |
| **S-008** | Local privilege escalation via shell adapter | 5 | 2 | 10 | Medium | Eng-A | Planned |

### 2.3 Schedule & Resource Risks

| ID | Risk | Impact | Probability | Score | Rating | Owner | Status |
|----|------|--------|-------------|-------|--------|-------|--------|
| **R-001** | Key engineer unavailable (bus factor = 1 per area) | 4 | 3 | 12 | Medium | PM | Active |
| **R-002** | Voice hardware validation takes longer than planned | 3 | 4 | 12 | Medium | Eng-B | Active |
| **R-003** | API provider deprecates/ changes API (Gemini, OpenAI, ElevenLabs) | 3 | 3 | 9 | Low | Eng-B | Monitoring |
| **R-004** | Windows 11 24H2 breaks UIA/Credential Manager | 4 | 2 | 8 | Low | Eng-C | Monitoring |
| **R-005** | CI/CD Windows runner capacity constraints | 2 | 3 | 6 | Low | Eng-A | Planned |
| **R-006** | Third-party dependency (Sherpa, Porcupine) abandons maintenance | 3 | 2 | 6 | Low | Eng-B | Monitoring |

### 2.4 Product & UX Risks

| ID | Risk | Impact | Probability | Score | Rating | Owner | Status |
|----|------|--------|-------------|-------|--------|-------|--------|
| **P-001** | Voice wake word false positives annoy users | 3 | 4 | 12 | Medium | Eng-B | Active |
| **P-002** | Agent delegation produces incorrect results silently | 4 | 3 | 12 | Medium | Eng-B | Planned |
| **P-003** | Approval fatigue — users click through R2+ prompts | 3 | 4 | 12 | Medium | Eng-A | Active |
| **P-004** | Memory system learns wrong preferences | 3 | 3 | 9 | Low | Eng-B | Planned |
| **P-005** | Offline/local-only mode too limited for core workflows | 3 | 3 | 9 | Low | Eng-B | Planned |
| **P-006** | Accessibility gaps exclude users with disabilities | 3 | 2 | 6 | Low | Eng-C | Planned |

### 2.5 Operational Risks

| ID | Risk | Impact | Probability | Score | Rating | Owner | Status |
|----|------|--------|-------------|-------|--------|-------|--------|
| **O-001** | Backup/restore fails during disaster recovery | 5 | 2 | 10 | Medium | Eng-A | Planned |
| **O-002** | Auto-update mechanism bricks installation | 4 | 2 | 8 | Low | Eng-C | Planned |
| **O-003** | Telemetry opt-in rate too low for product insights | 2 | 3 | 6 | Low | PM | Accepted |
| **O-004** | Log volume fills disk on long-running systems | 3 | 3 | 9 | Low | Eng-A | Planned |

---

## 3. Mitigation Plans (Top Risks)

### T-001: Windows UIA Automation Unreliable

**Risk**: UIA fails on Office apps, browsers, Electron apps, causing automation failures.

**Mitigation**:
1. **Perception Hierarchy** (P6.4): UIA → Playwright → CV/OCR automatic fallback
2. **Element Caching** (P6.1): Cache element properties, invalidate on UI change detection
3. **Evidence Capture** (P6.5): Screenshot + metadata per action for debugging
4. **Real App Testing** (P6.8): Test matrix on Notepad, Chrome, VS Code, Explorer, Teams, Outlook
5. **Selector Strategies**: Multiple selector types (automation-id, name, class, regex)
6. **Wait Strategies**: Explicit waits with polling, not fixed sleeps

**Contingency**: If UIA <80% reliable on target apps, invest in CV/OCR as primary for those apps.

**Review**: Weekly during P6, then bi-weekly.

---

### T-002: Voice Pipeline Latency

**Risk**: End-to-end voice latency exceeds 500ms P99 on target hardware.

**Mitigation**:
1. **Local-First Processing**: Porcupine + Sherpa-ONNX run locally, no cloud round-trip for wake/ASR
2. **Streaming Architecture**: Partial ASR results, early intent classification
3. **Model Optimization**: Quantized models (INT8), ONNX Runtime optimization
4. **Hardware Profiling**: Test on minimum spec (i5-8250U, 8GB RAM) and recommended (i7-12700, 16GB)
5. **Fallback Chain**: Cloud ASR/TTS only when local fails
6. **Performance Budgets**: Per-component latency budgets enforced in CI

**Contingency**: If local ASR insufficient, use hybrid: local VAD + cloud ASR for difficult audio.

**Review**: Weekly during P3, benchmark at each integration.

---

### T-006: Memory Unbounded Growth

**Risk**: Working/episodic memory grows without bound, causing OOM.

**Mitigation**:
1. **Consolidation Pipeline** (P5.3): Working→Episodic (hourly), Episodic summarization (daily)
2. **Retention Policies** (P5.5): TTL per kind (Working: 24h, Episodic: 90d, Procedural: 1y)
3. **Size Limits**: Hard cap per collection (Semantic: 100k, Episodic: 50k, etc.)
4. **PII Auto-Detection** (P5.7): Presidio integration, flag before storage
5. **Monitoring**: Memory growth rate metric, alert at 80% capacity
6. **User Controls** (P5.8): Inspect, export, delete all

**Contingency**: Emergency consolidation job, user notification at 90% capacity.

**Review**: Continuous monitoring, weekly review of growth trends.

---

### S-001: Prompt Injection Bypass

**Risk**: Malicious input bypasses defenses, causes unauthorized actions.

**Mitigation**:
1. **Instruction Hierarchy** (12.5.3): Immutable system instructions (Priority 1-3) cannot be overridden
2. **Pattern-Based Detection** (12.5.2): 12 injection pattern categories, balanced mode default
3. **Capability Scoping** (12.4.2): Agents receive only task-scoped capabilities
4. **Independent Verification** (P4.12): Verifier agent checks all outputs
5. **Audit Logging** (12.6): All injection attempts logged with context
6. **Red Team Testing**: Quarterly prompt injection penetration testing

**Contingency**: Strict mode (reject on detection), human-in-the-loop for R3+.

**Review**: Per-release, after any security incident.

---

### S-007: Supply Chain Attack

**Risk**: Compromised dependency introduces backdoor.

**Mitigation**:
1. **Dependency Pinning**: Exact versions in pyproject.toml, Cargo.lock, package-lock.json
2. **Automated Auditing**: pip-audit, cargo-audit, npm audit in CI (P0.4)
3. **Allowed List**: Only approved dependencies, new deps require security review
4. **Vendoring**: Critical deps (Porcupine, Sherpa) vendored with hash verification
5. **SBOM Generation**: CycloneDX SBOM for each release
6. **Monitoring**: GitHub Dependabot + OSV scanner

**Contingency**: Rapid patch release process (<24h for critical).

**Review**: Per-release, weekly Dependabot review.

---

### P-001: Wake Word False Positives

**Risk**: "Arise" detected accidentally, interrupting user.

**Mitigation**:
1. **Sensitivity Tuning** (P3.1): Per-environment calibration, user-adjustable
2. **Confirmation Required**: Visual indicator + optional confirmation sound
3. **Context Awareness**: Don't trigger during media playback, calls
4. **Multi-Keyword**: Support "Hey Arise", "OK Arise" with different sensitivities
5. **False Positive Logging**: Track and analyze for model improvement

**Contingency**: Push-to-talk mode as fallback.

**Review**: User testing in P3, telemetry in P11.

---

### P-003: Approval Fatigue

**Risk**: Users blindly approve R2+ prompts.

**Mitigation**:
1. **Scoped Approvals**: "Allow for this session", "Allow for this project", "Always allow"
2. **Risk Context**: Show what capability, what resource, what action
3. **Batch Approvals**: Group related approvals
4. **Smart Defaults**: Learn user patterns, pre-approve low-risk repeated actions
5. **Audit Trail**: Show approval history in UI

**Contingency**: Mandatory re-authentication for R4 after N approvals.

**Review**: UX testing in P2, telemetry in P11.

---

## 4. Risk Monitoring Dashboard

### 4.1 Key Risk Indicators (KRIs)

| KRI | Target | Current | Trend | Action Threshold |
|-----|--------|---------|-------|------------------|
| UIA success rate (top 5 apps) | >90% | - | - | <80% |
| Voice P99 latency | <500ms | - | - | >800ms |
| Memory growth rate | <50MB/day | - | - | >100MB/day |
| Prompt injection attempts | 0 critical | - | - | >0 critical |
| Dependency vulnerabilities | 0 high/critical | - | - | >0 |
| Test coverage | >90% | - | - | <85% |
| CI build success rate | >95% | - | - | <90% |

### 4.2 Review Cadence

| Risk Level | Review Frequency | Participants |
|------------|------------------|--------------|
| Extreme | Weekly | Tech Lead + PM + Security |
| High | Bi-weekly | Tech Lead + Area Owner |
| Medium | Monthly | Area Owner |
| Low | Quarterly | Area Owner |
| Minimal | Per-release | - |

---

## 5. Risk Response Strategies

| Strategy | When to Use | Example |
|----------|-------------|---------|
| **Avoid** | Risk unacceptable, alternative exists | Don't use unmaintained dependency |
| **Mitigate** | Risk can be reduced | Add fallback, monitoring, testing |
| **Transfer** | Risk owned by third party | Cloud provider SLA for API availability |
| **Accept** | Risk low, cost of mitigation > impact | Minor cosmetic issue |

---

## 6. Escalation Path

```
Level 1: Area Owner (Engineer)
    ↓ (unresolved 1 week / High risk)
Level 2: Tech Lead
    ↓ (unresolved 1 week / Extreme risk)
Level 3: PM + Security Lead
    ↓ (project-level impact)
Level 4: Executive Sponsor
```

---

## 7. Risk Register Maintenance

| Activity | Frequency | Owner |
|----------|-----------|-------|
| Review all risks | Bi-weekly | PM |
| Update scores | Per phase gate | Tech Lead |
| Add new risks | Continuous | All |
| Retire resolved risks | Per phase gate | PM |
| Report to stakeholders | Monthly | PM |

---

## 8. Appendix: Risk Heat Map

```
PROBABILITY
5 ████████████████████████████████████████████████████ T-001
4 ████████████████████████████████████████████████████ T-002, T-004, P-001, P-003
3 ████████████████████████████████████████████████████ T-003, T-005, T-006, T-007,
    ████████████████████████████████████████████████████ S-001, S-002, S-006, R-001,
    ████████████████████████████████████████████████████ R-002, R-003, P-002, P-004,
    ████████████████████████████████████████████████████ P-005, O-004
2 ████████████████████████████████████████████████████ T-008, T-009, S-003, S-004,
    ████████████████████████████████████████████████████ S-005, S-007, S-008, R-004,
    ████████████████████████████████████████████████████ R-005, R-006, P-006, O-001,
    ████████████████████████████████████████████████████ O-002, O-003
1 ████████████████████████████████████████████████████ (none)
  +---+---+---+---+---+---+---+---+---+---+
  1   2   3   4   5   IMPACT
```

---

*Risk Register is a living document. Update at each phase gate and when new information emerges.*