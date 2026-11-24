# ARISE — Technology Research & Comparison

## Executive Summary

This document provides comprehensive technology comparisons for each major architectural component of ARISE. Recommendations are based on: (1) Windows-first deployment target, (2) voice-first interaction paradigm, (3) multi-agent orchestration requirements, (4) persistent local memory needs, (5) real-time performance constraints, and (6) existing repository foundation (FastAPI + Tauri 2 + React).

---

## 1. Backend Web Framework (Python)

### Options Compared

| Framework | Architecture | RPS (Baseline) | Latency P99 | WebSocket | Startup (ms) | Learning Curve | Ecosystem |
|-----------|--------------|----------------|-------------|-----------|--------------|----------------|-----------|
| **FastAPI** | ASGI (Starlette) | 17,155 | 12.48 ms | Native | 943 | Low | Excellent |
| **Starlette** | ASGI | 34,716 | 9.94 ms | Native | 619 | Low | Good |
| **aiohttp** | Custom | 590,654 | 13.00 ms | Native | — | Medium | Good |
| **Falcon** | ASGI/WSGI | 11,209 | 7.58 ms | Via Granian | 617 | Medium | Good |
| **BlackSheep** | ASGI | ~24,570 | 5.46 ms | Native | 709 | Medium | Growing |
| **Litestar** | ASGI | ~21,754 | 12.48 ms | Native | 1,146 | Medium | Growing |

### Key Findings

- **FastAPI** is the pragmatic choice: built on Starlette, adds automatic validation/docs, negligible overhead vs raw Starlette for real workloads (validation is the dominant cost anyway)
- **aiohttp** wins raw throughput but lacks ASGI ecosystem, no native OpenAPI, more boilerplate for API features
- **Starlette** alone requires reimplementing validation, serialization, docs — work FastAPI already does
- **Existing repository uses FastAPI** (`src/arise/server.py` — 139K composition root)

### Recommendation: **FastAPI (Current)**

```
✅ ASGI-native, WebSocket support
✅ Pydantic validation, automatic OpenAPI
✅ Dependency injection, lifespan management
✅ Uvicorn/Granian deployment flexibility
✅ Already implemented in repository
✅ Team knowledge: Python-first
```

---

## 2. Desktop Shell Framework

### Options Compared

| Factor | **Tauri 2** | Electron | Wails v2/v3 | WebView2 (.NET) | Neutralino |
|--------|-------------|----------|-------------|-----------------|------------|
| **Bundle Size** | ~1-10 MB | 50-150 MB | ~11-20 MB | ~30-50 MB | ~5-10 MB |
| **Runtime** | System WebView2 | Bundled Chromium | System WebView | System WebView2 | System WebView |
| **Backend Language** | Rust | Node.js | Go | C#/.NET | Any (JS bridge) |
| **Memory (idle)** | ~142 MB | ~149 MB | ~205 MB | ~100 MB | ~50 MB |
| **Mobile (iOS/Android)** | Stable (v2) | No | Experimental (v3) | MAUI | No |
| **Security Model** | Capabilities/Permissions | Sandbox (renderer) | Go methods | .NET sandbox | Permissions |
| **Auto-Update** | Built-in (signed) | Built-in | Built-in (v3) | MSIX/ClickOnce | Custom |
| **WebView Consistency** | Platform-native | Identical (Chromium) | Platform-native | Windows-only | Platform-native |
| **Ecosystem/Maturity** | 112k★, stable v2 Oct 2024 | 123k★, mature | 37k★, v3 alpha | Enterprise | 8.7k★ |
| **Windows 7 Support** | Dropped v2.12 (Sep 2026) | Supported | Supported | Supported | Supported |

### Key Findings

- **Tauri 2** is the only framework with: system WebView + Rust backend + capabilities-based security + stable mobile + small bundle + active maintenance
- **Electron** bundle size (100× larger) and memory unacceptable for always-running background agent
- **Wails** Go backend adds language complexity; v3 still alpha; higher memory
- **WebView2** requires .NET runtime, Windows-only, no cross-platform path
- **Existing repository uses Tauri 2** (`src-tauri/Cargo.toml`, `tauri.conf.json`)

### Recommendation: **Tauri 2 (Current)**

```
✅ System WebView2 on Windows 11 (preinstalled)
✅ Rust backend for system-level operations (UIA, credentials, process mgmt)
✅ Capabilities-based security model aligns with ARISE policy engine
✅ Small bundle, low memory — critical for dormant/background operation
✅ Mobile companion path (AR-REMOTE) exists without rewrite
✅ Auto-updater with mandatory signing (AR-UPDATE)
✅ Already implemented in repository
```

### Tauri 2 Configuration for ARISE

```toml
# tauri.conf.json key settings
{
  "bundle": {
    "windows": {
      "webviewInstallMode": "downloadBootstrapper",
      "certificateThumbprint": "<code-sign-cert>"
    }
  },
  "security": {
    "capabilities": ["desktop-control", "filesystem", "shell", "notifications", "clipboard", "global-shortcut", "webview-window"]
  },
  "updater": {
    "active": true,
    "endpoints": ["https://updates.arise.local/{{target}}/{{current_version}}"],
    "pubkey": "<ed25519-pubkey>"
  }
}
```

---

## 3. Voice Pipeline — Real-Time Conversational AI

### Provider Comparison

| Dimension | **Gemini Live API** | OpenAI Realtime API |
|-----------|---------------------|---------------------|
| **Transport** | WebSocket (BidiGenerateContent) | WebRTC + WebSocket + SIP |
| **Model (2026)** | Gemini 3.8 Live / 3.8 Extended Thinking | gpt-realtime-2.1 / gpt-realtime-2.1-mini |
| **Latency (median)** | ~380-1,016 ms (varies) | ~410-752 ms |
| **Barge-in** | Manual (flush queue on `interrupted` flag) | Free (WebRTC auto-truncate) |
| **Session Length** | 15 min audio / 2 min video (extendable via compression) | 60 min hard cap |
| **Session Resumption** | `SessionResumptionUpdate` (token valid ~2 hrs) | Not documented |
| **Pricing (audio in/out per 1M)** | $3 / $12 (~$0.005/$0.018 per min) | $32 / $64 (~$0.096/$0.24 per min) |
| **Billing Model** | Re-bills full context window each turn | Flat per audio token |
| **Languages** | 97, mid-conversation switching | Multilingual (exact list unpublished) |
| **Tool Calling** | Async by default, interleaved | Function calling, synchronous |
| **Reasoning Control** | `thinkingConfig` (level/budget) | `reasoning_effort` (minimal→xhigh) |
| **Transcription** | Native bidirectional (input/output) | Whisper/gpt-4o-transcribe sidecar |
| **Free Tier** | AI Studio rate-limited | None |
| **SIP/Telephony** | Via partners (LiveKit, Pipecat) | Native |

### TTS Fallback (When Not Using Live Speech-to-Speech)

| Provider | Model | Latency | Voices | Cloning | Price/1M chars |
|----------|-------|---------|--------|---------|----------------|
| **ElevenLabs** | v3 / Flash v2.5 | ~75 ms (Flash) | 10,000+ | Instant + Pro | $50-100 |
| **OpenAI** | gpt-4o-mini-tts | ~300 ms | 13 (HD) | No | ~$15 |
| **Google Cloud** | Chirp 3: HD | 200-500 ms | 380+ | Instant Custom ($60) | $4-160 |
| **Azure** | Neural HD | 200-500 ms | 400+ | Custom Neural ($24-48) | $16-22 |

### ASR (Speech-to-Text) for Wake-Word / Local VAD

| Option | Approach | Latency | Accuracy | Offline | Notes |
|--------|----------|---------|----------|---------|-------|
| **Vosk** | Local (Kaldi) | <100 ms | Good | ✅ | Small models (~50 MB) |
| **Whisper.cpp** | Local (transformer) | ~500 ms | Excellent | ✅ | Larger models, GPU accelerated |
| **Sherpa-ONNX** | Local (ONNX) | <200 ms | Excellent | ✅ | VAD + ASR integrated |
| **Windows Speech SDK** | Cloud + local | Variable | Good | Partial | System integration |

### Architecture Decision: **Hybrid Voice Pipeline**

```
┌─────────────────────────────────────────────────────────────────┐
│                        VOICE ARCHITECTURE                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  WAKE WORD (Always On)                                          │
│  ├─ Porcupine / Picovoice (commercial, accurate)               │
│  └─ Vosk / Sherpa-ONNX (open source, local)                    │
│        │                                                        │
│        ▼                                                        │
│  LOCAL VAD + ASR (Streaming)                                    │
│  ├─ Sherpa-ONNX (VAD + ASR unified, <200ms)                   │
│  └─ Silero VAD + Whisper.cpp (modular)                          │
│        │                                                        │
│        ▼                                                        │
│  CONVERSATIONAL MODEL (Gemini Live API)                         │
│  ├─ Primary: WebSocket bidirectional                            │
│  ├─ Barge-in: manual queue flush on `interrupted`              │
│  ├─ Session mgmt: resumption tokens for >15 min                │
│  └─ Tool calling: async, ARISE executes, returns result         │
│        │                                                        │
│        ▼                                                        │
│  TTS FALLBACK (If Live unavailable)                             │
│  ├─ Primary: ElevenLabs Flash v2.5 (75ms, expressive)          │
│  ├─ Fallback: OpenAI gpt-4o-mini-tts (integrated billing)      │
│  └─ Local: Piper / Coqui (offline, lower quality)              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Recommendation Summary

| Component | Choice | Rationale |
|-----------|--------|-----------|
| **Conversational Model** | **Gemini Live API** | 10× cheaper, 97 languages, native audio, tool calling, extensible thinking |
| **Wake Word** | **Porcupine (Picovoice)** | Commercial accuracy, cross-platform, low CPU, multiple wake words |
| **Local VAD/ASR** | **Sherpa-ONNX** | Unified VAD+ASR, ONNX runtime, <200ms, offline, streaming |
| **TTS Fallback** | **ElevenLabs Flash v2.5** | Best latency/quality, voice cloning for personality, streaming |
| **Audio I/O** | **cpal (Rust) + Web Audio API** | Cross-platform, low latency, Tauri integration |

---

## 4. Browser Automation

### Options Compared

| Criterion | **Playwright** | Selenium | Puppeteer |
|-----------|----------------|----------|-----------|
| **Protocol** | Custom + CDP | WebDriver (W3C) + BiDi | CDP + BiDi |
| **Browsers** | Chromium, Firefox, WebKit | Chrome, Firefox, Safari, Edge | Chrome, Firefox |
| **Languages** | JS/TS, Python, Java, .NET | Java, Python, C#, JS, Ruby | JS/TS |
| **Auto-waiting** | ✅ Built-in (locator actionability) | ❌ Explicit waits | Partial |
| **Test Runner** | ✅ @playwright/test (built-in) | External (pytest, Jest, etc.) | External |
| **Parallel Execution** | Browser contexts (isolated, fast) | Selenium Grid (heavy) | Manual contexts |
| **Debugging** | Trace Viewer, Inspector, Codegen | Driver logs, screenshots | DevTools, CDP |
| **Attach to Running Browser** | `connectOverCDP` (Chromium only) | `debuggerAddress` | `connect` via CDP |
| **Stealth/Undetected** | Moderate (stealth plugin) | Poor (detectable) | Good (stealth plugin) |
| **Network Interception** | Full, clean API | Limited | Full CDP access |
| **Performance (JS pages)** | Fast | Slowest | Fast |
| **Cross-browser Consistency** | Best (own browser builds) | Varies by driver | Chrome-only primarily |

### Key Findings

- **Playwright** is the only framework with: auto-waiting + multi-browser (Chromium/Firefox/WebKit) + built-in runner + browser contexts + trace debugging + Python support
- **Selenium** needed only for real Safari (not WebKit) — not required for Windows-first
- **Puppeteer** Chrome-only, no test runner, JS-only
- **Existing repository uses Playwright** (`src/arise/adapters/browser_playwright.py`)

### Recommendation: **Playwright (Current)**

```
✅ Python support (async API)
✅ Auto-waiting eliminates flakiness
✅ Browser contexts = isolated sessions = perfect for multi-agent
✅ Connect to existing browser profile via CDP (AR-BROWSER-004)
✅ Trace Viewer for evidence/debugging (AR-TRANS-001)
✅ WebKit = Safari engine rendering validation
✅ Network interception for API-first strategy (AR-DESKTOP-002)
✅ Already implemented in repository
```

### Playwright Configuration for ARISE

```python
# Browser launch for connecting to existing profile
browser = await playwright.chromium.launch_persistent_context(
    user_data_dir=r"C:\Users\{user}\AppData\Local\Microsoft\Edge\User Data",
    channel="msedge",  # or "chrome"
    headless=False,
    args=[
        "--disable-blink-features=AutomationControlled",
        "--force-renderer-accessibility",  # For UIA access to web content
    ],
    permissions=["clipboard-read", "clipboard-write"],
)
```

---

## 5. Windows UI Automation

### Options Compared

| Library | Backend | Architecture | COM Handling | Maintenance | Best For |
|---------|---------|--------------|--------------|-------------|----------|
| **uiautomation** (yinkaisheng) | UIA (COM) | Pure Python + comtypes | Manual (per-thread init) | Active (v2.0.29 Aug 2025) | Deep UIA tree access |
| **pywinauto** | Win32 + UIA | Wrapper (both backends) | Abstracted (Application/Desktop) | Active (v0.6.9 Jan 2025) | High-level app automation |
| **uiautomation-new / winuia-auto** | UIA (COM) | Refactored modular + comtypes | Improved thread safety | Active (v0.1.5 Oct 2026) | Modern architecture |
| **comtypes** (raw) | UIA (COM) | Direct COM | Manual | Standard lib | Maximum control |

### Key Findings

- **pywinauto** provides higher-level abstractions (`Application`, `Desktop`, `wait('visible')`) but dual-backend complexity
- **uiautomation** (original) is lower-level but more direct UIA access; requires admin, per-thread COM init
- **uiautomation-new/winuia-auto** is a modern refactor with better modularity, includes `pynput`, `opencv` for visual matching
- **All require**: Administrator privileges, Windows 7+, Python ≠ 3.7.6/3.8.1 (comtypes bug)
- **Existing repository has** `src/arise/adapters/windows_uia.py` using raw UIA via comtypes

### Recommendation: **Hybrid Approach (Current + Enhancement)**

```
┌─────────────────────────────────────────────────────────────────┐
│                   WINDOWS AUTOMATION LAYER                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  LOW LEVEL: uiautomation-new (winuia-auto)                      │
│  ├─ Direct UIA tree traversal, patterns, properties            │
│  ├─ Thread-safe singleton client                                │
│  ├─ Visual matching (OpenCV) for canvas/apps without UIA       │
│  ├─ Hotkey/input helpers (pynput)                               │
│  └─ Used for: element discovery, state reading, precise clicks │
│                                                                  │
│  HIGH LEVEL: pywinauto (UIA backend)                            │
│  ├─ Application/Desktop process-scoped automation              │
│  ├─ Wait conditions, retry logic, control identifiers          │
│  ├─ Used for: app launch, window management, workflows         │
│                                                                  │
│  FALLBACK: Computer Vision / OCR                                │
│  ├─ Screenshot + Tesseract / PaddleOCR / Vision model          │
│  ├─ Used when: UIA fails (games, canvas, disabled apps)        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Implementation Notes

- Run Python as Administrator (required for UIA enumeration on Win7+)
- Initialize COM per thread: `pythoncom.CoInitialize()` / `CoUninitialize()`
- Use `uiautomation.InitializeUIAutomationInCurrentThread()` for raw UIA
- For Electron apps (VS Code, Slack, Discord): launch with `--force-renderer-accessibility`

---

## 6. Vector Database (Local Embedded)

### Options Compared

| Feature | **ChromaDB** | Qdrant | Weaviate | LanceDB | pgvector |
|---------|--------------|--------|----------|---------|----------|
| **Architecture** | Embedded / Client-Server | Server (Docker/binary) | Server (Docker) | Embedded | Postgres ext |
| **Language** | Python (Rust core 2025) | Rust | Go | Rust | C/Postgres |
| **Embedded Mode** | ✅ In-process (zero config) | ❌ | ❌ | ✅ In-process | ❌ (needs PG) |
| **Max Vectors (embedded)** | ~1M (hundreds of thousands practical) | N/A | N/A | Millions | N/A |
| **HNSW Index** | ✅ (hnswlib → custom Rust) | ✅ Custom (fastest) | ✅ Custom | ✅ (Lance format) | ✅ (HNSW/IVF) |
| **Metadata Filtering** | Basic (`where` clauses) | ✅ Advanced (nested, geo, range) | ✅ GraphQL + filters | ✅ SQL-like | ✅ SQL |
| **Hybrid Search (BM25 + Vector)** | ❌ Dense only | ✅ Sparse + dense | ✅ Native | ✅ Full-text + vector | ✅ (tsvector + vector) |
| **Quantization** | ❌ | ✅ Scalar + Product | ✅ | ❌ | ❌ |
| **Multi-tenancy** | Collections | Native (payload index) | Native classes | Tables | Schemas |
| **Persistence** | Disk (SQLite + files) | Disk (custom) | Disk (LSM) | Disk (Lance/Parquet) | Postgres WAL |
| **Python Client** | ✅ Native | ✅ Native | ✅ Native | ✅ Native | ✅ psycopg |
| **Startup/Embed Overhead** | Minimal (import) | Docker/binary | Docker/JVM | Minimal (import) | Postgres server |

### Benchmarks (Filtered Query p95, 500K vectors)

| Database | Unfiltered | Filtered (tenant + date) | Memory (500K × 768) | Index Time |
|----------|------------|--------------------------|---------------------|------------|
| **Qdrant** | 4 ms | **5 ms** | 2.1 GB (0.8 GB quantized) | 45 sec |
| **Weaviate** | 8 ms | 15 ms | 3.4 GB | 90 sec |
| **ChromaDB** | 12 ms | 28 ms | 2.8 GB | 120 sec |
| **LanceDB** | ~10 ms | ~15 ms | ~2.5 GB | ~60 sec |

### Key Findings

- **ChromaDB**: Best developer experience, embedded, adequate for <500K vectors, no hybrid search
- **Qdrant**: Best filtered query performance, quantization, but requires separate server process
- **LanceDB**: Embedded, columnar (Lance format), scales on disk, multimodal, hybrid search — strong contender
- **pgvector**: Only if Postgres already required (not for ARISE)
- **ARISE memory needs**: Personal (semantic/episodic) + Project + Procedural + Working — likely <200K vectors initially

### Recommendation: **ChromaDB (Primary) + LanceDB (Future)**

```
Phase 1 (v1): ChromaDB embedded
├── Zero-config, in-process, persistent
├── Adequate for personal + project memory (<200K vectors)
├── Python-native, integrates with LangChain/LlamaIndex patterns
├── Client-server mode available if multi-process needed later
└── Migration path to LanceDB/Qdrant when scale demands

Phase 2 (scale): LanceDB
├── Embedded, no server
├── Columnar storage scales to millions on disk
├── Native hybrid search (BM25 + vector)
├── Multimodal (images, audio embeddings)
└── Object storage (S3) tiering for cold memory
```

### ChromaDB Configuration for ARISE

```python
# Embedded client
import chromadb
from chromadb.config import Settings

client = chromadb.Client(Settings(
    persist_directory=r"C:\Users\{user}\AppData\Local\ARISE\memory\chroma",
    anonymized_telemetry=False,
    is_persistent=True,
))

# Collections per memory kind
collections = {
    "semantic": client.get_or_create_collection("semantic", metadata={"hnsw:space": "cosine"}),
    "episodic": client.get_or_create_collection("episodic", metadata={"hnsw:space": "cosine"}),
    "procedural": client.get_or_create_collection("procedural", metadata={"hnsw:space": "cosine"}),
    "preference": client.get_or_create_collection("preference", metadata={"hnsw:space": "cosine"}),
    "working": client.get_or_create_collection("working", metadata={"hnsw:space": "cosine"}),
}
```

---

## 7. Text-to-Speech (Fallback/Non-Live)

### Options Compared

| Provider | Best Model | Latency | Quality | Voices | Cloning | Price/1M chars | Free Tier |
|----------|------------|---------|---------|--------|---------|----------------|-----------|
| **ElevenLabs** | Flash v2.5 / v3 | ~75 ms | ⭐⭐⭐⭐⭐ | 10,000+ | ✅ Instant + Pro | $50-100 | 10K credits/mo |
| **OpenAI** | gpt-4o-mini-tts | ~300 ms | ⭐⭐⭐⭐⭐ | 13 | ❌ | ~$15 | None |
| **Google Cloud** | Chirp 3: HD | 200-500 ms | ⭐⭐⭐⭐ | 380+ | ✅ Instant Custom | $4-160 | 4M chars/mo |
| **Azure** | Neural HD | 200-500 ms | ⭐⭐⭐⭐ | 400+ | ✅ Custom Neural | $16-22 | 0.5M chars/mo |

### Recommendation: **ElevenLabs Flash v2.5 (Primary) → OpenAI gpt-4o-mini-tts (Fallback)**

```
Rationale:
├── Lowest latency for real-time feel (~75ms TTFA)
├── Voice cloning enables adaptive personality (AR-VOICE-008)
├── Natural-language tone instructions (not just SSML)
├── Streaming support
├── Free tier for development
└── OpenAI fallback: unified billing if already using OpenAI for other models
```

---

## 8. AI Model Providers & Routing

### Provider Landscape (2026)

| Provider | Models | Strengths | Access |
|----------|--------|-----------|--------|
| **Google (Gemini)** | 3.8 Live, 3.8 Extended Thinking, 2.5 Flash, 2.5 Pro | Native audio, 97 languages, thinking control, cheapest | AI Studio / Vertex AI |
| **OpenAI** | gpt-realtime-2.1, gpt-5, o3, o3-mini, gpt-4o, gpt-4o-mini | Best reasoning, Realtime API, tool maturity, ecosystem | API |
| **NVIDIA NIM** | Nemotron, Llama, custom containers | Self-hosted, enterprise, GPU-optimized, data privacy | NGC / Docker |
| **Anthropic** | Claude 4 Opus, Sonnet, Haiku | Best coding, long context, constitutional AI | API |
| **xAI** | Grok 2, Grok 3 | Real-time X data, fewer restrictions | API |
| **Local (Ollama/LM Studio)** | Llama 3.1, Qwen 2.5, Phi 3.5, Gemma 2 | Offline, free, privacy | Local |

### Routing Strategy (AR-MODELS-002)

```python
# Model selection criteria (priority order)
ROUTING_RULES = [
    # Voice conversation → Gemini Live (native audio)
    {"task": "voice_conversation", "primary": "gemini-3.8-live", "fallback": "gpt-realtime-2.1-mini"},
    
    # Complex reasoning/coding → Claude 4 Opus / o3
    {"task": "complex_reasoning", "primary": "claude-4-opus", "fallback": "o3"},
    {"task": "software_engineering", "primary": "claude-4-opus", "fallback": "gpt-5"},
    
    # Fast classification/extraction → Flash/Mini models
    {"task": "intent_classification", "primary": "gemini-2.5-flash", "fallback": "gpt-4o-mini"},
    {"task": "entity_extraction", "primary": "gemini-2.5-flash", "fallback": "gpt-4o-mini"},
    
    # Research/synthesis → Pro models with large context
    {"task": "deep_research", "primary": "gemini-2.5-pro", "fallback": "claude-4-opus"},
    
    # Local/offline → Ollama (if available)
    {"task": "offline", "primary": "llama-3.1-70b", "fallback": "qwen-2.5-72b"},
]
```

### Circuit Breaker & Fallback (AR-MODELS-005)

```python
# Per-provider circuit breaker
CIRCUIT_BREAKER_CONFIG = {
    "failure_threshold": 5,
    "recovery_timeout": 30,  # seconds
    "half_open_max_calls": 3,
    "fallback_chain": ["gemini", "openai", "anthropic", "nvidia_nim", "local"],
}
```

---

## 9. Local-First Storage & Configuration

### Configuration: Pydantic Settings (Current)

```python
# src/arise/config/settings.py pattern
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    
    # Core
    app_name: str = "ARISE"
    environment: str = "development"
    data_dir: Path = Path.home() / "AppData" / "Local" / "ARISE"
    
    # Providers (encrypted in Credential Manager)
    gemini_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    elevenlabs_api_key: SecretStr | None = None
    # ...
```

### Credential Storage: Windows Credential Manager (AR-SEC-002)

```rust
// Tauri Rust side - credentials crate
use credentials::{Credential, CredentialBuilder};

fn store_credential(service: &str, account: &str, secret: &str) -> Result<()> {
    let cred = CredentialBuilder::new()
        .target(service)
        .username(account)
        .password(secret)
        .build()?;
    cred.save()?;
    Ok(())
}

fn get_credential(service: &str, account: &str) -> Result<String> {
    let cred = Credential::get(service, account)?;
    Ok(cred.password().unwrap_or_default())
}
```

---

## 10. Testing Frameworks

### Layered Testing Strategy (AR-TEST-001)

| Layer | Framework | Scope | Target |
|-------|-----------|-------|--------|
| **Unit (Python)** | `pytest` + `pytest-asyncio` | Pure functions, adapters, policy engine | >90% coverage |
| **Unit (Rust)** | `cargo test` | Tauri commands, system integration | >85% coverage |
| **Unit (TypeScript)** | `vitest` | React components, hooks, utilities | >80% coverage |
| **Integration** | `pytest` + `httpx.ASGITransport` | API endpoints, adapter composition, task engine | Critical paths |
| **E2E (Desktop)** | `playwright-python` + Tauri driver | Full app flows: voice → task → verification | User journeys |
| **E2E (Browser)** | `@playwright/test` | Browser automation adapters | Web interactions |
| **Contract** | `pytest-contract` / `schemathesis` | API schemas, provider contracts | Provider APIs |
| **Performance** | `locust` / custom | Latency, throughput, memory, concurrent tasks | SLA validation |
| **Security** | `bandit`, `cargo-audit`, `npm audit` + custom | Injection, permissions, credential handling | Vulnerability scan |

### Real Windows Validation (AR-TEST-002)

- CI must run on Windows runners (GitHub Actions `windows-latest`)
- UIA/Playwright tests require interactive desktop session
- Use `windows-runner` with auto-login for GUI tests
- Test on target hardware class (i5-13420H, RTX 2050, 16GB RAM)

---

## 11. Summary: Technology Stack Decision Matrix

| Layer | Decision | Status | Notes |
|-------|----------|--------|-------|
| **Backend API** | FastAPI + Uvicorn/Granian | ✅ Implemented | ASGI, WebSocket, DI, OpenAPI |
| **Desktop Shell** | Tauri 2 (Rust + WebView2) | ✅ Implemented | Capabilities, auto-update, mobile path |
| **Frontend** | React 18 + TypeScript + Vite | ✅ Implemented | Single-page dashboard + floating companion |
| **Voice Conversation** | Gemini Live API (WebSocket) | 🔄 Design | Primary; OpenAI Realtime fallback |
| **Wake Word** | Porcupine (Picovoice) | 🔄 Design | Commercial, multi-word, low CPU |
| **Local VAD/ASR** | Sherpa-ONNX | 🔄 Design | Unified streaming, offline, ONNX |
| **TTS Fallback** | ElevenLabs Flash v2.5 | 🔄 Design | 75ms, cloning, streaming |
| **Browser Automation** | Playwright (Python) | ✅ Implemented | Multi-browser, auto-wait, CDP attach |
| **Windows Automation** | uiautomation-new + pywinauto | 🔄 Partial | Hybrid low/high level, CV fallback |
| **Vector Memory** | ChromaDB (embedded) | 🔄 Design | Phase 1; LanceDB for scale |
| **Relational Data** | SQLite (embedded) | 🔄 Design | Tasks, projects, checkpoints, audit |
| **Configuration** | Pydantic Settings + .env | ✅ Implemented | Type-safe, env-specific |
| **Credentials** | Windows Credential Manager | 🔄 Design | Rust side, no plaintext |
| **Task Queue** | In-process async + persistence | 🔄 Design | 28-state machine, checkpoints |
| **Scheduler** | APScheduler / custom | 🔄 Design | Recurring, one-shot, deadlines |
| **Logging** | structlog + file rotation | 🔄 Design | Structured, audit-ready |
| **Testing** | pytest / cargo test / vitest / Playwright | 🔄 Partial | Layered, real Windows CI |

---

## 12. Open Technical Decisions (Requiring ADRs)

| Decision | Options | Impact |
|----------|---------|--------|
| **ADR-001**: Task queue persistence | SQLite vs Redis vs custom WAL | Durability, concurrency, recovery |
| **ADR-002**: Agent communication protocol | gRPC vs NATS vs in-process channels | Latency, distribution, debugging |
| **ADR-003**: Memory consolidation scheduler | Cron (APScheduler) vs custom event-driven | Resource usage, timeliness |
| **ADR-004**: Evidence storage format | JSONL + SQLite indexes vs Parquet vs custom | Query speed, compression, tooling |
| **ADR-005**: Plugin/skill sandbox | WASM (wasmtime) vs subprocess vs in-process | Security, performance, language support |
| **ADR-006**: Real-time audio transport | cpal (Rust) → Tauri → Web Audio API vs WebRTC data channel | Latency, complexity, browser compat |
| **ADR-007**: Multi-agent state synchronization | Event sourcing vs CRDT vs central coordinator | Consistency, complexity, audit |

---

## Sources

- [FastAPI Benchmarks](https://fastapi.tiangolo.com/benchmarks/)
- [Python ASGI Framework Benchmarks](http://klen.github.io/py-frameworks-bench/)
- [HttpArena Python Comparison](https://http-arena.com/compare/python/)
- [Wails vs Tauri vs Electron Comparison](https://oss-tanbou.dev/en/articles/wails-tauri-electron-comparison)
- [Tauri 2 vs Electron vs Wails](https://ludoprogramming.com/en/blog/desktop-tehnologii-web-electron-tauri-webview2-blazor-hybrid)
- [Electron Alternatives 2026](https://dawloom.com/blog/electron-alternatives/)
- [OpenAI Realtime vs Gemini Live](https://vadimall.com/posts/openai-realtime-vs-gemini-live-vs-pipecat-voice-ai-typescript)
- [OpenAI Realtime vs Gemini Live: Picking a Voice Agent Backend](https://dreaming.press/posts/openai-realtime-api-vs-gemini-live-voice-agents.html)
- [Speech-to-Speech 2026: OpenAI Realtime vs Gemini Live](https://www.forasoft.com/learn/ai-for-video-engineering/articles-ai/speech-to-speech-realtime-api-gemini-live-seamless)
- [Cross-Provider Realtime Voice Adaptation](https://zylos.ai/research/2026-07-19-realtime-voice-api-protocol-adaptation/)
- [Selenium vs Playwright vs Puppeteer](https://www.scrapeless.com/en/blog/selenium-vs-playwright-vs-puppeteer)
- [Playwright vs Selenium vs Puppeteer 2026](https://browser-use.com/posts/playwright-vs-selenium-vs-puppeteer)
- [Python UI Automation without COM Pain](https://fireal.dev/blog/python-ui-automation/)
- [uiautomation GitHub](https://github.com/yinkaisheng/Python-UIAutomation-for-Windows)
- [pywinauto Documentation](https://pywinauto.readthedocs.io/en/stable/getting_started.html)
- [ChromaDB vs Qdrant vs Weaviate vs Pinecone](https://mljourney.com/chromadb-vs-qdrant-vs-weaviate-vs-pinecone-vector-db-comparison-2026/)
- [Vector Database APIs Compared 2026](https://apiscout.dev/guides/pinecone-vs-weaviate-vs-qdrant-vs-chroma-2026)
- [Qdrant vs Pinecone vs ChromaDB vs Weaviate](https://toolhalla.ai/blog/qdrant-vs-pinecone-vs-chromadb-weaviate-2026)
- [Best Vector Databases 2026](https://www.firecrawl.dev/blog/best-vector-databases)
- [Text-to-Speech APIs 2026](https://stackbriefly.com/blog/text-to-speech-apis-2026-elevenlabs-openai-google-cloud-azure-speech-amazon-polly)
- [TTS API Comparison 2026](https://crazyrouter.com/en/blog/text-to-speech-api-comparison-2026)
- [Best Text to Speech APIs 2026](https://developer.puter.com/blog/best-text-to-speech-apis/)
- [ElevenLabs vs OpenAI vs Google TTS](https://futuretweets.com/elevenlabs-vs-openai-vs-google-cloud-tts-2026/)
- [Google vs Azure vs ElevenLabs vs OpenAI vs Gemini TTS](https://ttsforfree.com/en/blogs/google-vs-azure-vs-elevenlabs-tts-comparison/)