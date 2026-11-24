# ARISE — Consolidated Requirements Catalogue

## Traceability Matrix

Each requirement has a unique ID: **AR-[DOMAIN]-[NNN]**

Domains: `CORE` (fundamental), `VOICE`, `DESKTOP`, `BROWSER`, `AGENTS`, `MEMORY`, `PROJECTS`, `RESEARCH`, `CREATIVE`, `SYSTEM`, `SECURITY`, `UI`, `PERF`, `DEPLOY`

Categories: **E**ssential, **A**dvanced, **F**uture, **O**ptional, **S**ecurity, **P**erformance

---

## 1. Core Intelligence & Orchestration (AR-CORE)

| ID | Requirement | Category | Dependencies | Source |
|----|-------------|----------|--------------|--------|
| AR-CORE-001 | Natural-language objective understanding with context, references, constraints | E | AR-VOICE-001, AR-DESKTOP-001 | Master §1.1, §3 |
| AR-CORE-002 | Intent classification: command vs question vs conversation vs task | E | AR-CORE-001 | Master §3, existing `IntentClassifier` |
| AR-CORE-003 | Contextual reference resolution (that, this, next, previous, continue) | E | AR-CORE-001, AR-DESKTOP-002 | Master §3.1 |
| AR-CORE-004 | Stateful interaction awareness (active app, window, tab, page, selection) | E | AR-DESKTOP-002, AR-BROWSER-001 | Master §3.2 |
| AR-CORE-005 | Correction/interruption handling (no, stop, redirect) without task restart | E | AR-CORE-003, AR-CORE-019 | Master §3.3 |
| AR-CORE-006 | Complexity-based execution: lightweight for simple, planned for complex | E | AR-CORE-001, AR-AGENTS-001 | Master §8.1 |
| AR-CORE-007 | Hybrid execution method selection (API, UIA, DOM, shortcuts, vision) | E | AR-DESKTOP-001, AR-BROWSER-001 | Master §8.2 |
| AR-CORE-008 | Independent task completion within permissions | E | AR-SEC-001, AR-AGENTS-003 | Master §8.3 |
| AR-CORE-009 | Persistent task lifecycle with 18+ states (created → verified-complete) | E | AR-CORE-010, AR-AGENTS-004 | Master §8.4, existing `TaskStatus` |
| AR-CORE-010 | Multiple concurrent tasks with pause/resume/cancel/reprioritize | E | AR-CORE-009, AR-SYSTEM-001 | Master §8.5 |
| AR-CORE-011 | Checkpoint persistence for long-running tasks | E | AR-CORE-009, AR-MEMORY-001 | Master §8.6 |
| AR-CORE-012 | Adaptive task prioritization (urgency, importance, deps, resources) | A | AR-CORE-010, AR-PROJECTS-001 | Master §8.7 |
| AR-CORE-013 | Deadline management: propose schedules, ask for approval | A | AR-CORE-012, AR-PROJECTS-005 | Master §8.8 |
| AR-CORE-014 | Dynamic resource allocation (CPU, RAM, GPU, VRAM, network, API) | E | AR-SYSTEM-001, AR-AGENTS-003 | Master §8.9 |
| AR-CORE-015 | Immediate acknowledgement (<500ms) separate from execution | P | AR-VOICE-002, AR-PERF-001 | Master §5.2 |
| AR-CORE-016 | Four communication states: acknowledgement, progress, completion, failure | E | AR-VOICE-002 | Master §5.2 table |
| AR-CORE-017 | Continuous conversation while tasks execute in background | E | AR-VOICE-003, AR-CORE-010 | Master §5.3 |
| AR-CORE-018 | Task-conversation context separation | E | AR-CORE-017, AR-MEMORY-003 | Master §5.3 |
| AR-CORE-019 | Interruption/cancellation with state preservation | E | AR-CORE-009, AR-CORE-011 | Master §5.3, §9.5 |
| AR-CORE-020 | Evidence-based completion for ALL tasks | E | AR-DESKTOP-001, AR-BROWSER-001 | Master §18, §24.4 |

---

## 2. Voice & Conversation (AR-VOICE)

| ID | Requirement | Category | Dependencies | Source |
|----|-------------|----------|--------------|--------|
| AR-VOICE-001 | Configurable wake-word activation (multiple, user-defined, aliases) | E | AR-VOICE-007 | Master §5.1 |
| AR-VOICE-002 | Immediate spoken acknowledgement ("Yes, Chrome is opening") | E | AR-CORE-015, AR-PERF-001 | Master §5.2 |
| AR-VOICE-003 | Continuous conversation: interrupt, correct, change topic, follow-up | E | AR-CORE-017 | Master §5.3 |
| AR-VOICE-004 | Voice consistency across model providers (unified presentation layer) | E | AR-VOICE-006 | Master §5.4 |
| AR-VOICE-005 | Speech quality: no skipped segments, correct ordering, controlled streaming | E | AR-VOICE-006 | Master §5.5 |
| AR-VOICE-006 | Live conversational model (Gemini Live) for dialogue; ARISE owns execution | E | AR-CORE-001, AR-AGENTS-001 | Master §5.4 |
| AR-VOICE-007 | Multilingual: English, Telugu, code-switching, response-language matching | E | AR-VOICE-001 | Master §5.6 |
| AR-VOICE-008 | Adaptive personality: professional/technical vs casual/everyday | A | AR-CORE-001 | Master §5.7 |
| AR-VOICE-009 | Visible listening indicators (dormant, detecting, listening, processing, speaking, muted) | E | AR-SEC-001 | Master §5.8 |
| AR-VOICE-010 | Immediate mute control + spoken sleep command | E | AR-VOICE-009 | Master §5.8 |
| AR-VOICE-011 | Dormant mode: wake-word listener active, full components inactive | A | AR-DEPLOY-001 | Master §23.4 |
| AR-VOICE-012 | Barge-in and cancellation during speech generation | E | AR-VOICE-003, AR-VOICE-005 | Master §8, §5.3 |

---

## 3. Desktop Control & Computer Awareness (AR-DESKTOP)

| ID | Requirement | Category | Dependencies | Source |
|----|-------------|----------|--------------|--------|
| AR-DESKTOP-001 | Full desktop control: open/close/switch/focus/type/click/scroll/drag/select | E | AR-DESKTOP-002, AR-DESKTOP-003 | Master §7 |
| AR-DESKTOP-002 | Fast interaction strategy: API → DOM → UIA → shortcuts → vision (auto-select) | E | AR-DESKTOP-003, AR-DESKTOP-007 | Master §7.1 |
| AR-DESKTOP-003 | Screen understanding: accessibility + app state + DOM + vision (revalidate before act) | E | AR-DESKTOP-004 | Master §7.2 |
| AR-DESKTOP-004 | Failure handling: detect, understand state, determine cause, try alternative, preserve progress | E | AR-CORE-019, AR-CORE-020 | Master §7.3 |
| AR-DESKTOP-005 | Initial environment discovery (1-2 min): apps, hardware, FS, browser, dev env, interfaces | E | AR-DESKTOP-006 | Master §6.1 |
| AR-DESKTOP-006 | Application capability profiles: actions, methods, limitations, permissions | A | AR-DESKTOP-005 | Master §6.2 |
| AR-DESKTOP-007 | Startup discovery + live awareness (events) + on-demand rediscovery | E | AR-DESKTOP-005 | Master §6.3 |
| AR-DESKTOP-008 | Private data boundaries: read access FS, write with permission, inspect only when relevant | S | AR-SEC-001, AR-MEMORY-001 | Master §6.4 |
| AR-DESKTOP-009 | Windows system controls: brightness, keyboard backlight, sleep, shutdown (with approval) | E | AR-SEC-002 | Master §4.5 |
| AR-DESKTOP-010 | Hardware capability discovery (verify control exists before exposing) | E | AR-DESKTOP-005 | Master §4.5 |
| AR-DESKTOP-011 | Camera discovery, permission, capture, vision interpretation | A | AR-DESKTOP-005, AR-CREATIVE-001 | Master §4.10 |

---

## 4. Browser Automation (AR-BROWSER)

| ID | Requirement | Category | Dependencies | Source |
|----|-------------|----------|--------------|--------|
| AR-BROWSER-001 | Contextual browser navigation (continuation of active tab/context) | E | AR-CORE-004, AR-DESKTOP-003 | Master §4.1, §3 |
| AR-BROWSER-002 | Search, inspect results, identify specific items, play/interact | E | AR-BROWSER-003 | Master §4.1 |
| AR-BROWSER-003 | Hybrid interaction: APIs/structured data → DOM → vision fallback | E | AR-DESKTOP-002 | Master §13.2 |
| AR-BROWSER-004 | Connect to existing authenticated browser profiles (not fresh context) | A | AR-DESKTOP-008, AR-SEC-003 | Master §4.8 |
| AR-BROWSER-005 | Cross-application continuity (carry info from browser to terminal, etc.) | E | AR-CORE-004 | Master §4.4 |
| AR-BROWSER-006 | Verification of browser actions (clone succeeded, page loaded, element exists) | E | AR-CORE-020 | Master §4.4, §24.4 |

---

## 5. Multi-Agent Intelligence (AR-AGENTS)

| ID | Requirement | Category | Dependencies | Source |
|----|-------------|----------|--------------|--------|
| AR-AGENTS-001 | Central coordinator + specialist agents (not independent swarm) | E | AR-CORE-001 | Master §10 |
| AR-AGENTS-002 | Coordinator: understand, decompose, create agents, assign, track, resolve, review, report | E | AR-AGENTS-003 | Master §10 |
| AR-AGENTS-003 | Specialist roles: research, coding, computer-use, browser, files, system, comms, creative, memory, projects, agent-creation | E | AR-AGENTS-004 | Master §10.2 |
| AR-AGENTS-004 | Scoped agent permissions (not inherit coordinator authority) | S | AR-SEC-001 | Master §10.3 |
| AR-AGENTS-005 | Coordinator-mediated delegation (agents don't freely assign to each other) | E | AR-AGENTS-002 | Master §10.4 |
| AR-AGENTS-006 | Agent collaboration: exchange findings, share evidence, review, challenge, resolve via evidence | E | AR-AGENTS-007 | Master §10.5 |
| AR-AGENTS-007 | Independent verification: important results verified by another agent/trusted tool | E | AR-CORE-020, AR-AGENTS-003 | Master §10.6 |
| AR-AGENTS-008 | Agent lifecycle management (create, register, sandbox, observe, recover) | E | AR-AGENTS-001 | Master §10.1 |
| AR-AGENTS-009 | Agent failure recovery and conflict resolution | E | AR-CORE-019 | Master §10.5 |

---

## 6. Skills, Tools & Integrations (AR-SKILLS)

| ID | Requirement | Category | Dependencies | Source |
|----|-------------|----------|--------------|--------|
| AR-SKILLS-001 | Automatic discovery of apps, APIs, integrations, CLI tools, browser methods, AI services | A | AR-DESKTOP-005 | Master §11.1 |
| AR-SKILLS-002 | Trust assessment: source, trustworthiness, permissions, security, credentials, compatibility | S | AR-SEC-001 | Master §11.2 |
| AR-SKILLS-003 | Approval before installing/connecting new integrations | S | AR-SEC-002 | Master §11.3 |
| AR-SKILLS-004 | Shared skill library + project-specific skills + agent-specific assignments | A | AR-AGENTS-003, AR-PROJECTS-001 | Master §11.4 |
| AR-SKILLS-005 | Missing capability: search alternative → evaluate → propose new → approve | A | AR-SKILLS-001, AR-SKILLS-003 | Master §11.5 |

---

## 7. AI Model & Provider Intelligence (AR-MODELS)

| ID | Requirement | Category | Dependencies | Source |
|----|-------------|----------|--------------|--------|
| AR-MODELS-001 | Multiple online providers: Gemini (incl. Live), NVIDIA NIM, others | E | AR-MODELS-002 | Master §12 |
| AR-MODELS-002 | Intelligent model routing: task type, capabilities, reasoning, context, vision, audio, coding | E | AR-MODELS-001 | Master §12.1 |
| AR-MODELS-003 | Task-based model collaboration (not for every small action) | A | AR-MODELS-002 | Master §12.2 |
| AR-MODELS-004 | Automatic provider management (choose models without manual config per task) | A | AR-MODELS-002 | Master §12.3 |
| AR-MODELS-005 | Provider failure handling: detect, classify, retry, switch, preserve context, continue | E | AR-MODELS-001 | Master §12.4 |
| AR-MODELS-006 | Quality priority: best capability for task (not most expensive/largest) | E | AR-MODELS-002 | Master §12.5 |
| AR-MODELS-007 | Online API only — unavailable when internet down (no silent local LLM fallback) | E | AR-MODELS-001 | Master §12.6 |

---

## 8. Research & Web Intelligence (AR-RESEARCH)

| ID | Requirement | Category | Dependencies | Source |
|----|-------------|----------|--------------|--------|
| AR-RESEARCH-001 | Deep research: understand objective → subquestions → sources → retrieve → cross-check → evaluate → structure → cite | E | AR-MODELS-002 | Master §13 |
| AR-RESEARCH-002 | Cross-source verification: multiple credible independent sources | E | AR-RESEARCH-001 | Master §13.1 |
| AR-RESEARCH-003 | Hybrid web interaction: APIs → browser automation → vision fallback | E | AR-BROWSER-003 | Master §13.2 |
| AR-RESEARCH-004 | Citations always for factual research | E | AR-RESEARCH-001 | Master §13.3 |
| AR-RESEARCH-005 | Research depth scaling: simple=concise, complex=deep | A | AR-RESEARCH-001 | Master §13.4 |
| AR-RESEARCH-006 | Report: verified/uncertain/disagreements/unconfirmed/limitations | E | AR-RESEARCH-002 | Master §13.3 |

---

## 9. Project Management & Software Development (AR-PROJECTS)

| ID | Requirement | Category | Dependencies | Source |
|----|-------------|----------|--------------|--------|
| AR-PROJECTS-001 | Complete personal project manager: plan → completion | E | AR-MEMORY-001, AR-AGENTS-003 | Master §14 |
| AR-PROJECTS-002 | Repository understanding: structure, languages, frameworks, deps, build, config, architecture, components, decisions, implementation, features, bugs, debt, tests, git, branches, PRs, docs, deploy | E | AR-DESKTOP-011, AR-MEMORY-002 | Master §14.1 |
| AR-PROJECTS-003 | Project memory: why exists, objectives, implemented, incomplete, decisions, problems, solutions, failures, next steps | E | AR-MEMORY-001 | Master §14.2 |
| AR-PROJECTS-004 | Unfinished work identification: last completed, remaining, errors, in-progress, next logical step | E | AR-PROJECTS-003, AR-CORE-011 | Master §14.3 |
| AR-PROJECTS-005 | Multiple concurrent projects with separate contexts, shared priorities/resources | E | AR-CORE-010, AR-MEMORY-003 | Master §14.4 |
| AR-PROJECTS-006 | Project roadmap: objectives, milestones, deadlines, deps, progress, blockers, completed, pending, suggested next | A | AR-PROJECTS-003, AR-CORE-013 | Master §14.5 |
| AR-PROJECTS-007 | Development execution: inspect → understand conventions → read docs → determine changes → select coding agent → construct prompt → delegate → monitor → test → inspect failures → coordinate corrections → verify → summarize | E | AR-AGENTS-003, AR-DESKTOP-001 | Master §14.6 |
| AR-PROJECTS-008 | Task-specific prompts (not universal): relevant instructions, file context, exact bug, expected behavior, constraints, required tests | E | AR-AGENTS-003, AR-PROJECTS-002 | Master §14.7 |

---

## 10. Memory & Personal Knowledge (AR-MEMORY)

| ID | Requirement | Category | Dependencies | Source |
|----|-------------|----------|--------------|--------|
| AR-MEMORY-001 | Persistent memory across conversations/tasks: personal, project, episodic, knowledge, procedural, working | E | AR-SEC-004 | Master §15 |
| AR-MEMORY-002 | Memory categories with different retention/retrieval policies | E | AR-MEMORY-001 | Master §15.1 |
| AR-MEMORY-003 | Automatic memory creation + explicit instructions/corrections | E | AR-MEMORY-001 | Master §15.2 |
| AR-MEMORY-004 | Automatic relevant retrieval (project context when task concerns project) | E | AR-MEMORY-001, AR-PROJECTS-001 | Master §15.3 |
| AR-MEMORY-005 | Conflict resolution: identify, evidence, newer/authoritative, ask when uncertain | E | AR-MEMORY-001 | Master §15.4 |
| AR-MEMORY-006 | Management dashboard: inspect, edit, correct | A | AR-MEMORY-001 | Master §15.5 |
| AR-MEMORY-007 | Complete deletion across active memory, indexes, caches, task records, backups | S | AR-SEC-004 | Master §15.6 |
| AR-MEMORY-008 | Compact memory: summaries, decisions, essential facts, checkpoints, references (not full conversations) | E | AR-MEMORY-001, AR-PERF-002 | Master §15.7 |

---

## 11. System Monitoring & Hardware (AR-SYSTEM)

| ID | Requirement | Category | Dependencies | Source |
|----|-------------|----------|--------------|--------|
| AR-SYSTEM-001 | Comprehensive monitoring: CPU, RAM, GPU, VRAM, storage, temps, battery, network, processes, startup, services, hardware | E | AR-DESKTOP-005 | Master §16 |
| AR-SYSTEM-002 | Resource-efficient operation: avoid heavyweight processes, release temp resources, limit concurrent models, manage workers, monitor consumption | P | AR-MODELS-006, AR-CORE-014 | Master §16.2 |
| AR-SYSTEM-003 | Recommendation-first optimization: analyze, identify bottlenecks, recommend, explain benefits/risks, await approval | A | AR-SEC-002 | Master §16.3 |
| AR-SYSTEM-004 | Diagnosis-first troubleshooting: identify cause before recommending solution | E | AR-SYSTEM-001 | Master §16.4 |
| AR-SYSTEM-005 | Adaptive notifications: severity, urgency, current activity, immediate attention needed | A | AR-UI-001 | Master §16.5 |

---

## 12. UI & User Experience (AR-UI)

| ID | Requirement | Category | Dependencies | Source |
|----|-------------|----------|--------------|--------|
| AR-UI-001 | Full-screen futuristic command centre + floating companion (both modes) | E | AR-VOICE-009 | Master §17 |
| AR-UI-002 | Main interface: conversation, active/queued tasks, agent activity, projects, milestones, system, memory, notifications, history, evidence, providers, integrations | E | AR-CORE-010 | Master §17.1 |
| AR-UI-003 | Floating companion: accessible while other apps open, click→full-screen, state indicators | E | AR-VOICE-009 | Master §17.2 |
| AR-UI-004 | Floating states: dormant, listening, thinking, planning, executing, speaking, waiting-approval, error | E | AR-VOICE-009, AR-CORE-009 | Master §17.3 |
| AR-UI-005 | Dashboard categories: 20 items (tasks, agents, projects, system, hardware, memory, notifications, history, logs, evidence, providers, integrations) | E | AR-UI-002 | Master §17.4 |
| AR-UI-006 | Extensive customization: workspace, layout, visual, floating, shortcuts, interaction, accessibility | A | AR-UI-001 | Master §17.5 |
| AR-UI-007 | Adaptive accessibility: text size, contrast, motion, layout per preferences/context | A | AR-UI-006 | Master §17.5 |
| AR-UI-008 | Fully customizable global shortcuts (e.g., Alt+A) | E | AR-DEPLOY-001 | Master §17.6 |

---

## 13. Task Transparency & Outputs (AR-TRANS)

| ID | Requirement | Category | Dependencies | Source |
|----|-------------|----------|--------------|--------|
| AR-TRANS-001 | Evidence for all tasks: action, timestamp, agent, permission, result, verification, screenshot/log | E | AR-CORE-020 | Master §18 |
| AR-TRANS-002 | Evidence efficiency: compact records, retain relevant logs, avoid duplicate screenshots, reference large artifacts | P | AR-PERF-002 | Master §18.1 |
| AR-TRANS-003 | Adaptive progress reporting: meaningful milestones, not every internal action | E | AR-CORE-016 | Master §18.2 |
| AR-TRANS-004 | Linked generated artifacts: actual file locations, direct access | E | AR-PROJECTS-007 | Master §18.3 |
| AR-TRANS-005 | Verification-first for uncertain outcomes: independent verify + safe recover before report | E | AR-CORE-020, AR-AGENTS-007 | Master §18.4 |

---

## 14. Privacy, Security & Data Ownership (AR-SEC)

| ID | Requirement | Category | Dependencies | Source |
|----|-------------|----------|--------------|--------|
| AR-SEC-001 | Risk-based authentication for sensitive actions, permission changes, security-critical ops | S | AR-SEC-002 | Master §19.1 |
| AR-SEC-002 | Credential storage: Windows Credential Manager / OS credential storage (not plaintext) | S | — | Master §19.2 |
| AR-SEC-003 | Compact audit logging: action, agent/component, time, permission, success | S | AR-TRANS-001 | Master §19.3 |
| AR-SEC-004 | Malicious instruction defence: layered + strict (prompt injection, malicious web/docs/code, compromised integrations, unauthorized agent actions, untrusted instructions in external content) | S | AR-AGENTS-004, AR-BROWSER-004 | Master §19.4 |
| AR-SEC-005 | Sensitive info: task-only usage, not auto long-term memory | S | AR-MEMORY-001 | Master §19.5 |
| AR-SEC-006 | No external telemetry by default (provider API calls distinct) | S | — | Master §19.6 |
| AR-SEC-007 | Scoped permissions + temporary approvals + configurable risk rules | S | AR-CORE-008 | Master §9.3 |
| AR-SEC-008 | Explicit approval for: deletion, external messages, purchases, publishing, installs, system changes, security changes, account changes, sensitive sharing, shutdown with active tasks, irreversible actions | S | AR-CORE-008 | Master §9.1 |
| AR-SEC-009 | Approval ≠ acknowledgement (separate states: understand, preparing, need permission, completed) | S | AR-CORE-016 | Master §9.5 |

---

## 15. Backups & Data Recovery (AR-BACKUP)

| ID | Requirement | Category | Dependencies | Source |
|----|-------------|----------|--------------|--------|
| AR-BACKUP-001 | Compact retention: useful info, avoid unnecessary storage | P | AR-MEMORY-008 | Master §20.1 |
| AR-BACKUP-002 | Automatic scheduled local backups: config, memory, projects, tasks, checkpoints, app data | E | AR-MEMORY-001 | Master §20.2 |
| AR-BACKUP-003 | Credentials special protection (not in ordinary exports) | S | AR-SEC-002 | Master §20.2 |
| AR-BACKUP-004 | Backup verification: usable, not just copied | E | AR-BACKUP-002 | Master §20.3 |
| AR-BACKUP-005 | Selective recovery: restore affected without overwriting healthy | E | AR-BACKUP-002 | Master §20.4 |
| AR-BACKUP-006 | Complete export: settings, memory, projects, tasks, logs, configs, supporting data | A | AR-MEMORY-001 | Master §20.5 |

---

## 16. Remote Access & Mobile Companion (AR-REMOTE)

| ID | Requirement | Category | Dependencies | Source |
|----|-------------|----------|--------------|--------|
| AR-REMOTE-001 | Full remote control from mobile: commands, tasks, progress, projects, artifacts, approvals, desktop control | F | AR-UI-001, AR-SEC-001 | Master §21.1 |
| AR-REMOTE-002 | Explicitly trusted/paired devices | S | AR-SEC-001 | Master §21.2 |
| AR-REMOTE-003 | Same risk-based approval system on remote | S | AR-SEC-007 | Master §21.3 |
| AR-REMOTE-004 | Secure encrypted connectivity (no public internet exposure) | S | AR-SEC-001 | Master §21.4 |
| AR-REMOTE-005 | Device revocation: revoke trust, expire sessions, disable remote, revoke on loss | S | AR-REMOTE-002 | Master §21.5 |

---

## 17. Updates & Self-Maintenance (AR-UPDATE)

| ID | Requirement | Category | Dependencies | Source |
|----|-------------|----------|--------------|--------|
| AR-UPDATE-001 | Notification-first updates: notify, wait for approval before install | S | AR-SEC-002 | Master §22 |
| AR-UPDATE-002 | Isolated staging tests before activation | S | AR-UPDATE-001 | Master §22.1 |
| AR-UPDATE-003 | Automatic rollback if update breaks | S | AR-UPDATE-002 | Master §22.2 |
| AR-UPDATE-004 | Diagnostics-first maintenance: inspect health, deps, config, DB, services, providers, logs → recommend → wait for decision | A | AR-SYSTEM-001 | Master §22.3 |

---

## 18. Installation & Startup (AR-DEPLOY)

| ID | Requirement | Category | Dependencies | Source |
|----|-------------|----------|--------------|--------|
| AR-DEPLOY-001 | Proper Windows desktop installer (not dev scripts) | E | — | Master §23 |
| AR-DEPLOY-002 | Guided onboarding explaining important config decisions | A | AR-DEPLOY-001 | Master §23.1 |
| AR-DEPLOY-003 | Automatic initial discovery on first launch | E | AR-DESKTOP-005 | Master §23.2 |
| AR-DEPLOY-004 | Manual startup (user launches, e.g., Alt+A shortcut) | E | AR-UI-008 | Master §23.3 |
| AR-DEPLOY-005 | Dormant mode: wake-word listener available, full components inactive | A | AR-VOICE-011 | Master §23.4 |
| AR-DEPLOY-006 | Essential background services + on-demand activation for other components | E | AR-SYSTEM-002 | Master §23.5 |

---

## 19. Testing & Quality (AR-TEST)

| ID | Requirement | Category | Dependencies | Source |
|----|-------------|----------|--------------|--------|
| AR-TEST-001 | Layered testing: unit, integration, e2e, security, performance | E | — | Master §24 |
| AR-TEST-002 | Real Windows validation (not just simulation) | E | AR-DEPLOY-001 | Master §24 |
| AR-TEST-003 | Verified completion: impl finished + tests pass + behaviour independently verified | E | AR-CORE-020 | Master §24.1 |
| AR-TEST-004 | Strictest release gate: block if any required test/check/target/criterion fails | E | AR-TEST-001 | Master §24.2 |
| AR-TEST-005 | Failure recovery: detect, preserve state, diagnose, retry safely, recover, avoid duplicates, ask when authority needed | E | AR-CORE-019 | Master §24.3 |
| AR-TEST-006 | Task verification: independent postcondition checks (process/window exists, file exists, repo structure, message sent, test results) | E | AR-CORE-020, AR-AGENTS-007 | Master §24.4 |

---

## 20. Development Strategy (AR-DEV)

| ID | Requirement | Category | Dependencies | Source |
|----|-------------|----------|--------------|--------|
| AR-DEV-001 | Foundation-first development (core stable before expanding) | E | — | Master §25 |
| AR-DEV-002 | Overall capability/completeness priority without compromising safety/reliability | E | AR-SEC-001 | Master §25 |
| AR-DEV-003 | Incremental releases | E | AR-DEV-001 | Master §25 |
| AR-DEV-004 | Windows-first development | E | AR-DEPLOY-001 | Master §25 |
| AR-DEV-005 | Engineering principles: build foundations, avoid disconnected scripts, clear responsibilities, observable operations, verify behaviour, preserve work, avoid unnecessary deps, resource efficiency, build for extensibility, avoid premature distributed infra, keep security central | E | — | Master §25.1 |

---

## Unresolved Decisions (From Master §34)

| Area | Unresolved Detail |
|------|-------------------|
| First release | Exact first-release capabilities |
| Architecture | Final component boundaries and technology decisions |
| Voice | Exact voice provider and voice identity |
| Wake word | Actual chosen wake-word phrases |
| AI providers | Exact provider priority and model catalogue |
| Provider dashboard | Level of manual override and configuration |
| Integrations | Exact services and accounts to connect |
| Browser | Method for connecting to existing authenticated browser profiles |
| Camera | Specific camera capture and permission workflow |
| Mobile | Exact mobile platform and implementation timing |
| Remote access | Exact secure connectivity implementation |
| Backups | Backup frequency, retention, destination |
| Memory | Exact retention periods by category |
| Deletion | Treatment of protected backups and retention exceptions |
| Logging | Detailed log-retention duration |
| Authentication | PIN/password implementation and session policy |
| Startup | Exact shortcut and dormant-state behaviour |
| Notifications | Exact notification priorities and quiet periods |
| Deadlines | Exact reminder and scheduling interface |
| UI design | Final visual theme, animations, layouts, component styling |
| Testing | Numerical performance acceptance thresholds |
| Updates | Update distribution and signing strategy |
| Deployment | Final packaging and release process |

---

## Cross-Reference Index

| Requirement | References |
|-------------|------------|
| AR-CORE-001 | Foundation for all execution |
| AR-CORE-009 | Implements task lifecycle used by AR-AGENTS-008, AR-TRANS-001 |
| AR-SEC-007 | Gates AR-CORE-008, AR-AGENTS-003, AR-SKILLS-003 |
| AR-MEMORY-001 | Feeds AR-PROJECTS-003, AR-CORE-004, AR-RESEARCH-001 |
| AR-MODELS-002 | Used by AR-AGENTS-003, AR-RESEARCH-001, AR-PROJECTS-007 |
| AR-AGENTS-001 | Orchestrates AR-AGENTS-003 through AR-CORE-006 |
| AR-DESKTOP-002 | Strategy used by AR-BROWSER-003, AR-CORE-007 |
| AR-CORE-020 | Required by AR-TRANS-001, AR-AGENTS-007, AR-TEST-006 |