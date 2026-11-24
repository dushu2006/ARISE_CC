# ARISE — Voice Architecture

## Overview

This document specifies the complete voice pipeline architecture for ARISE, implementing a dormant-first, privacy-preserving, low-latency voice interaction system. The pipeline follows: **Wake Word → VAD/ASR → Model (Gemini Live) → TTS**, with full barge-in support and session resumption.

---

## 1. Architecture Principles

| Principle | Implementation |
|-----------|----------------|
| **Dormant-First** | Only wake word detector runs continuously (Porcupine, ~1% CPU) |
| **Privacy by Default** | No audio leaves device until wake word + user speech detected |
| **Local-First Processing** | VAD/ASR runs locally (Sherpa-ONNX), cloud only for LLM |
| **Barge-In Native** | User can interrupt at any time, system responds immediately |
| **Session Resumption** | Gemini Live sessions persist across interruptions (30min token) |
| **Multi-Language** | Code-switching support (English + Telugu via Sherpa-ONNX) |
| **Fallback Chain** | Local → Cloud TTS, Local → Cloud ASR, Graceful degradation |

---

## 2. Complete Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              VOICE PIPELINE ARCHITECTURE                         │
└─────────────────────────────────────────────────────────────────────────────────┘

┌──────────────┐     Audio In      ┌──────────────┐     Wake Event    ┌──────────────┐
│  MICROPHONE  │ ────────────────► │  PORCUPINE   │ ────────────────► │  VOICE       │
│  (16kHz mono)│   Raw PCM frames  │  WAKE WORD   │   Keyword index   │  PIPELINE    │
└──────────────┘                   │  DETECTOR    │                   │  ORCHESTRATOR│
       ▲                            └──────────────┘                   └──────┬───────┘
       │                                                                       │
       │                    ┌─────────────────────────────────────────────────┘
       │                    ▼
       │            ┌──────────────┐     Speech Event    ┌──────────────┐
       │            │  SHERPA-ONNX │ ──────────────────► │  VOICE       │
       │            │   VAD + ASR  │   Transcript chunks │  PIPELINE    │
       │            └──────────────┘                     └──────┬───────┘
       │                                                         │
       │                    ┌────────────────────────────────────┘
       │                    ▼
       │            ┌──────────────────┐    Text/Tool Calls   ┌──────────────┐
       │            │   GEMINI LIVE    │ ◄──────────────────► │  MODEL       │
       │            │  (Realtime API)  │   Audio response     │  ROUTER      │
       │            └──────────────────┘                     └──────┬───────┘
       │                                                            │
       │                    ┌──────────────────────────────────────┘
       │                    ▼
       │            ┌──────────────────┐     Audio Out        ┌──────────────┐
       │            │   PLAYBACK       │ ──────────────────►  │  SPEAKERS    │
       │            │   (cpal/Tauri)   │   PCM chunks         │  (16kHz)     │
       │            └──────────────────┘                     └──────────────┘
       │
       │                    ┌──────────────────┐
       └───────────────────│   TTS FALLBACK   │
                            │ (ElevenLabs/     │
                            │  OpenAI/Local)   │
                            └──────────────────┘
```

---

## 3. Component Specifications

### 3.1 Wake Word Detector (Porcupine)

**Technology:** Picovoice Porcupine (on-device, no cloud)
- **Model:** Built-in keywords + custom `.ppn` files
- **Languages:** English (built-in), custom for "Hey ARISE"
- **Sensitivity:** Configurable 0.0-1.0 (default 0.5)
- **CPU:** ~1-2% on modern CPU (always-on)
- **Audio:** 16kHz, 16-bit mono, 512-sample frames (32ms)

**Configuration:**
```python
@dataclass
class WakeWordConfig:
    keywords: List[str] = ["hey arise", "computer"]
    sensitivity: float = 0.5
    access_key: str  # From Picovoice Console
    custom_models: Dict[str, Path] = {}  # keyword -> .ppn path
    audio_device_index: int = -1  # Default
```

**Custom Keyword Training:**
1. Record 3-5 samples of "Hey ARISE" in target environment
2. Use Picovoice Console to train `.ppn` file
3. Deploy to `models/wake_words/hey_arise.ppn`
4. Register in config: `{"hey arise": "models/wake_words/hey_arise.ppn"}`

### 3.2 VAD + Streaming ASR (Sherpa-ONNX)

**Technology:** Sherpa-ONNX with Silero VAD + Zipformer/CTC transducer
- **VAD:** Silero VAD v5 (ONNX), configurable sensitivity
- **ASR:** Streaming Zipformer transducer (English + Telugu multilingual)
- **Model Size:** ~120MB (encoder+decoder+joiner+tokens)
- **Latency:** <200ms end-to-end (first token)
- **Languages:** English (en), Telugu (te), auto code-switching

**Models Required:**
```
models/sherpa/
├── tokens.txt                    # Vocabulary
├── encoder-ep20.onnx             # Zipformer encoder
├── decoder-ep20.onnx             # Decoder
├── joiner-ep20.onnx              # Joiner
├── silero_vad.onnx               # VAD model
└── provider_options.json         # CPU/GPU config
```

**Configuration:**
```python
@dataclass
class VadAsrConfig:
    # VAD
    vad_threshold: float = 0.5          # 0.3 low, 0.5 medium, 0.7 high
    vad_min_speech_duration: float = 0.1
    vad_min_silence_duration: float = 0.5  # 500ms
    vad_window_size: int = 512
    
    # ASR
    model_dir: Path = "models/sherpa"
    decoding_method: str = "greedy_search"
    enable_endpoint_detection: bool = True
    rule1_min_trailing_silence: float = 2.4
    rule2_min_trailing_silence: float = 1.2
    rule3_min_utterance_length: int = 300
    
    # Language
    language: str = "auto"  # auto, en, te
    
    # Performance
    num_threads: int = 2
    sample_rate: int = 16000
    feature_dim: int = 80
```

**Endpoint Detection Rules (Sherpa-ONNX):**
- Rule 1: Trailing silence > 2.4s → endpoint
- Rule 2: Trailing silence > 1.2s + utterance > 300 frames → endpoint
- Rule 3: Utterance > 30s → forced endpoint

### 3.3 Gemini Live API Client

**Technology:** Google Gemini Live API (WebSocket, bidirectional audio)
- **Model:** `gemini-3.8-live` (or `gemini-3.8-live-extended-thinking`)
- **Audio Format:** 16kHz, 16-bit PCM, mono (input/output)
- **Session Resumption:** 30-minute resumption token
- **Tool Calling:** Full function calling support
- **Interruption:** Native server-side barge-in support

**Session Management:**
```python
class GeminiLiveSession:
    def __init__(self, api_key: str, model: str = "gemini-3.8-live"):
        self.api_key = api_key
        self.model = model
        self.ws: WebSocket = None
        self.session_id: str = None
        self.resumption_token: str = None
        self.connected = False
        
        # Callbacks
        self.on_audio: Callable[[bytes], Awaitable] = None
        self.on_interrupted: Callable[[], Awaitable] = None
        self.on_tool_call: Callable[[Dict], Awaitable] = None
        self.on_transcript: Callable[[str, bool], Awaitable] = None  # text, is_final
        self.on_turn_complete: Callable[[], Awaitable] = None
    
    async def connect(
        self,
        session_id: str = None,
        resumption_token: str = None,
        system_instruction: str = None,
        tools: List[Dict] = None,
    ):
        """Establish WebSocket connection to Gemini Live"""
        url = f"wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService/BidiGenerateContent?key={self.api_key}"
        
        self.ws = await websockets.connect(url)
        
        # Send setup message
        setup = {
            "setup": {
                "model": f"models/{self.model}",
                "generation_config": {
                    "response_modalities": ["AUDIO"],
                    "speech_config": {
                        "voice_config": {
                            "prebuilt_voice_config": {"voice_name": "Puck"}
                        }
                    }
                },
                "system_instruction": {"parts": [{"text": system_instruction}]} if system_instruction else None,
                "tools": tools,
            }
        }
        
        if session_id:
            setup["setup"]["session_resumption"] = {"handle": session_id}
        
        await self.ws.send(json.dumps(setup))
        
        # Wait for setup complete
        response = await self.ws.recv()
        data = json.loads(response)
        if "setupComplete" in data:
            self.connected = True
            self.session_id = data.get("session_id")
        elif "error" in data:
            raise GeminiLiveError(data["error"])
    
    async def send_audio(self, pcm_bytes: bytes):
        """Stream audio to Gemini"""
        if not self.connected:
            raise RuntimeError("Not connected")
        
        # Chunk into 512-sample frames (32ms at 16kHz)
        for i in range(0, len(pcm_bytes), 1024):  # 512 samples * 2 bytes
            chunk = pcm_bytes[i:i+1024]
            if len(chunk) == 1024:
                await self.ws.send(base64.b64encode(chunk).decode())
    
    async def send_text(self, text: str):
        """Send text input (alternative to audio)"""
        await self.ws.send(json.dumps({
            "clientContent": {
                "turns": [{"role": "user", "parts": [{"text": text}]}],
                "turnComplete": True,
            }
        }))
    
    async def send_tool_result(self, call_id: str, result: Any):
        """Return tool call result"""
        await self.ws.send(json.dumps({
            "toolResponse": {
                "functionResponses": [{
                    "id": call_id,
                    "response": {"result": result}
                }]
            }
        }))
    
    async def send_interrupt(self):
        """Signal user interruption (barge-in)"""
        await self.ws.send(json.dumps({"clientContent": {"turns": [], "turnComplete": True, "interrupted": True}}))
    
    async def receive_loop(self):
        """Main receive loop - dispatches to callbacks"""
        async for message in self.ws:
            data = json.loads(message)
            
            if "serverContent" in data:
                content = data["serverContent"]
                
                # Audio response
                if "modelTurn" in content:
                    for part in content["modelTurn"]["parts"]:
                        if "inlineData" in part:
                            audio_b64 = part["inlineData"]["data"]
                            audio_bytes = base64.b64decode(audio_b64)
                            if self.on_audio:
                                await self.on_audio(audio_bytes)
                
                # Transcript
                if "outputTranscription" in content:
                    text = content["outputTranscription"]["text"]
                    is_final = content.get("turnComplete", False)
                    if self.on_transcript:
                        await self.on_transcript(text, is_final)
                
                # Tool calls
                if "toolCalls" in content:
                    for tc in content["toolCalls"]:
                        if self.on_tool_call:
                            await self.on_tool_call(tc)
                
                # Turn complete
                if content.get("turnComplete"):
                    if self.on_turn_complete:
                        await self.on_turn_complete()
            
            # Session resumption update
            if "sessionResumptionUpdate" in data:
                self.resumption_token = data["sessionResumptionUpdate"]["newHandle"]
            
            # Error handling
            if "error" in data:
                logger.error(f"Gemini Live error: {data['error']}")
```

### 3.4 TTS Fallback Chain

**Priority Order:**
1. **ElevenLabs Turbo v2.5** - Highest quality, streaming, ~300ms latency
2. **OpenAI TTS (tts-1-hd)** - Good quality, streaming, ~500ms latency
3. **Local (Piper/Coqui)** - Offline, no API key, ~800ms latency

```python
class TTSFallback:
    def __init__(self, config: TTSConfig):
        self.providers = [
            ElevenLabsTTS(config.elevenlabs_api_key, voice=config.voice),
            OpenAITTS(config.openai_api_key, voice=config.voice),
            LocalTTS(model_path=config.local_model_path),
        ]
    
    async def synthesize_stream(self, text: str, voice: str = None) -> AsyncGenerator[bytes, None]:
        """Stream audio from first working provider"""
        for provider in self.providers:
            try:
                async for chunk in provider.stream(text, voice):
                    yield chunk
                return  # Success, don't try fallbacks
            except Exception as e:
                logger.warning(f"TTS provider {provider.name} failed: {e}")
                continue
        raise TTSError("All TTS providers failed")
    
    async def synthesize(self, text: str, voice: str = None) -> bytes:
        """Non-streaming synthesis (collects all chunks)"""
        chunks = []
        async for chunk in self.synthesize_stream(text, voice):
            chunks.append(chunk)
        return b"".join(chunks)
```

**ElevenLabs Streaming:**
```python
class ElevenLabsTTS:
    def __init__(self, api_key: str, voice: str = "Rachel"):
        self.api_key = api_key
        self.voice_id = voice
        self.base_url = "https://api.elevenlabs.io/v1"
    
    async def stream(self, text: str, voice: str = None) -> AsyncGenerator[bytes, None]:
        url = f"{self.base_url}/text-to-speech/{voice or self.voice_id}/stream"
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                headers={"xi-api-key": self.api_key, "Accept": "audio/mpeg"},
                json={
                    "text": text,
                    "model_id": "eleven_turbo_v2_5",
                    "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
                    "optimize_streaming_latency": 4,
                }
            ) as resp:
                async for chunk in resp.content.iter_chunked(1024):
                    if chunk:
                        # Convert MP3 to PCM if needed
                        yield await self._mp3_to_pcm(chunk)
```

---

## 4. Audio Routing & Processing

### 4.1 Audio Flow (Windows)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        WINDOWS AUDIO ARCHITECTURE                        │
└─────────────────────────────────────────────────────────────────────────┘

MICROPHONE
    │
    ▼
Windows Audio Engine (WASAPI Shared Mode)
    │
    ├──────────────────────┬──────────────────────┐
    ▼                      ▼                      ▼
┌─────────┐          ┌─────────┐          ┌─────────┐
│Porcupine│          │ Sherpa  │          │  Apps   │
│(Exclusive│          │(Shared) │          │(System) │
│ Capture) │          │         │          │         │
└─────────┘          └─────────┘          └─────────┘
    │                      │
    │              ┌───────┴───────┐
    │              ▼               ▼
    │         VAD Engine        ASR Engine
    │              │               │
    └──────────────┴───────────────┘
                       │
                       ▼
              ┌───────────────┐
              │ Voice Pipeline│
              │ (Orchestrator)│
              └───────┬───────┘
                      │
          ┌───────────┼───────────┐
          ▼           ▼           ▼
      ┌────────┐ ┌────────┐  ┌─────────┐
      │Gemini  │ │ TTS    │  │ System  │
      │ Live   │ │Fallback│  │ Sounds  │
      └────┬───┘ └────┬───┘  └─────────┘
           │          │
           ▼          ▼
      ┌─────────────────────┐
      │  Playback Mixer     │  (cpal/Tauri audio)
      │  (WebAudio / WASAPI)│
      └──────────┬──────────┘
                 │
                 ▼
            SPEAKERS
```

### 4.2 CPAL Audio Backend (Rust/Tauri)

```rust
// src-tauri/src/audio.rs
use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use cpal::{SampleFormat, StreamConfig};
use std::sync::{Arc, Mutex};
use tokio::sync::mpsc;

pub struct AudioPlayback {
    stream: cpal::Stream,
    sender: mpsc::Sender<Vec<f32>>,
    buffer: Arc<Mutex<Vec<f32>>>,
    sample_rate: u32,
    channels: u16,
}

impl AudioPlayback {
    pub fn new() -> Result<Self, AudioError> {
        let host = cpal::default_host();
        let device = host.default_output_device()
            .ok_or(AudioError::NoOutputDevice)?;
        
        let config = StreamConfig {
            channels: 1,
            sample_rate: cpal::SampleRate(16000),
            buffer_size: cpal::BufferSize::Fixed(1024),
        };
        
        let (tx, mut rx) = mpsc::channel::<Vec<f32>>(10);
        let buffer = Arc::new(Mutex::new(Vec::with_capacity(4096)));
        let buffer_clone = buffer.clone();
        
        let stream = device.build_output_stream(
            &config,
            move |data: &mut [f32], _: &cpal::OutputCallbackInfo| {
                let mut buffer = buffer_clone.lock().unwrap();
                if buffer.len() < data.len() {
                    // Pull more from channel
                    while let Ok(chunk) = rx.try_recv() {
                        buffer.extend(chunk);
                    }
                }
                
                let available = buffer.len().min(data.len());
                if available > 0 {
                    data[..available].copy_from_slice(&buffer[..available]);
                    buffer.drain(..available);
                }
                
                // Fill rest with silence
                for sample in &mut data[available..] {
                    *sample = 0.0;
                }
            },
            |err| eprintln!("Audio stream error: {}", err),
            None,
        )?;
        
        stream.play()?;
        
        Ok(Self {
            stream,
            sender: tx,
            buffer,
            sample_rate: 16000,
            channels: 1,
        })
    }
    
    pub async fn write(&self, pcm_bytes: &[u8]) -> Result<(), AudioError> {
        // Convert i16 PCM to f32
        let samples: Vec<f32> = pcm_bytes
            .chunks_exact(2)
            .map(|chunk| i16::from_le_bytes([chunk[0], chunk[1]]) as f32 / 32768.0)
            .collect();
        
        self.sender.send(samples).await
            .map_err(|_| AudioError::ChannelClosed)
    }
    
    pub async fn stop(&self) -> Result<(), AudioError> {
        // Send silence to flush buffer
        let silence = vec![0.0f32; 16000]; // 1 second
        self.sender.send(silence).await?;
        tokio::time::sleep(Duration::from_millis(100)).await;
        Ok(())
    }
}

// Tauri commands
#[tauri::command]
async fn audio_start_playback(state: State<'_, AudioState>) -> Result<(), String> {
    state.playback.lock().await.start()?;
    Ok(())
}

#[tauri::command]
async fn audio_write_chunk(state: State<'_, AudioState>, chunk: Vec<u8>) -> Result<(), String> {
    state.playback.lock().await.write(&chunk).await?;
    Ok(())
}

#[tauri::command]
async fn audio_stop_playback(state: State<'_, AudioState>) -> Result<(), String> {
    state.playback.lock().await.stop().await?;
    Ok(())
}
```

---

## 5. Voice Pipeline State Machine

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        VOICE PIPELINE STATE MACHINE                          │
└─────────────────────────────────────────────────────────────────────────────┘

         ┌─────────────┐
         │  DORMANT    │ ◄──────────────────────────────────────┐
         │ (Wake only) │                                          │
         └──────┬──────┘                                          │
                │ Wake detected                                   │
                ▼                                                 │
         ┌─────────────┐                                          │
         │ DETECTING   │ ──────────────────────────────────────┐  │
         │(Activating) │                                         │  │
         └──────┬──────┘                                         │  │
                │ VAD started                                    │  │
                ▼                                                 │  │
         ┌─────────────┐         Speech detected                 │  │
         │  LISTENING  │ ──────────────────────────────────┐    │  │
         │  (VAD/ASR)  │                                   │    │  │
         └──────┬──────┘                                   │    │  │
                │ Speech end / final transcript            │    │  │
                ▼                                          │    │  │
         ┌─────────────┐                                   │    │  │
         │ PROCESSING  │ ◄─────────────────────────────────┘    │  │
         │ (Model)     │                                        │  │
         └──────┬──────┘                                        │  │
                │ First audio chunk                              │  │
                ▼                                                │  │
         ┌─────────────┐         Barge-in                       │  │
         │  SPEAKING   │ ◄───────────────────────────────────────┘  │
         │ (Playback)  │              detected                    │
         └──────┬──────┘                                            │
                │ Playback complete / interrupt                     │
                ▼                                                   │
         ┌─────────────┐                                            │
         │  DORMANT    │ ──────────────────────────────────────────┘
         │ (Wake only) │
         └─────────────┘

         ┌─────────────┐
         │   MUTED     │ (Explicit user mute)
         │  (Paused)   │
         └─────────────┘
```

### State Transition Table

| From State | Trigger | To State | Actions |
|------------|---------|----------|---------|
| DORMANT | Wake word detected | DETECTING | Start VAD/ASR |
| DETECTING | VAD ready | LISTENING | Begin capturing |
| LISTENING | Speech start | LISTENING | Visual feedback |
| LISTENING | Final transcript | PROCESSING | Stop VAD, send to model |
| PROCESSING | First audio response | SPEAKING | Start playback |
| SPEAKING | Barge-in detected | LISTENING | Stop playback, restart VAD |
| SPEAKING | Playback complete | DORMANT | Stop playback, restart wake detector |
| ANY | User mute | MUTED | Stop all, preserve session |
| MUTED | User unmute | DORMANT | Restart wake detector |

---

## 6. Session Resumption & Persistence

### 6.1 Gemini Live Session Resumption

```python
class SessionManager:
    """Manages Gemini Live session persistence across interruptions"""
    
    def __init__(self, storage_path: Path):
        self.storage_path = storage_path
        self.current_session: Optional[GeminiLiveSession] = None
    
    async def get_or_create_session(
        self,
        system_instruction: str,
        tools: List[Dict],
    ) -> GeminiLiveSession:
        # Try to resume existing session
        if self.current_session and self.current_session.connected:
            return self.current_session
        
        # Load resumption token from disk
        resumption_token = await self._load_resumption_token()
        session_id = await self._load_session_id()
        
        # Create new session with resumption
        session = GeminiLiveSession(
            api_key=self.api_key,
            model=self.model,
        )
        
        await session.connect(
            session_id=session_id,
            resumption_token=resumption_token,
            system_instruction=system_instruction,
            tools=tools,
        )
        
        # Persist new tokens
        await self._save_session_id(session.session_id)
        await self._save_resumption_token(session.resumption_token)
        
        self.current_session = session
        return session
    
    async def _save_session_id(self, session_id: str):
        (self.storage_path / "session_id").write_text(session_id)
    
    async def _save_resumption_token(self, token: str):
        (self.storage_path / "resumption_token").write_text(token)
    
    async def _load_session_id(self) -> Optional[str]:
        path = self.storage_path / "session_id"
        if path.exists():
            return path.read_text().strip()
        return None
    
    async def _load_resumption_token(self) -> Optional[str]:
        path = self.storage_path / "resumption_token"
        if path.exists():
            return path.read_text().strip()
        return None
    
    async def clear(self):
        """Clear persisted session (e.g., on explicit reset)"""
        for f in ["session_id", "resumption_token"]:
            path = self.storage_path / f
            if path.exists():
                path.unlink()
        self.current_session = None
```

### 6.2 Resumption Token Lifetime

- **Token validity:** 30 minutes from last activity
- **Auto-refresh:** Token updated on each `sessionResumptionUpdate` from server
- **Persistence:** Encrypted in Windows Credential Manager (DPAPI)
- **Cleanup:** Expired tokens automatically discarded on next connection attempt

---

## 7. Barge-In Implementation

### 7.1 Detection Strategies

| Strategy | Latency | Accuracy | Implementation |
|----------|---------|----------|----------------|
| **VAD during playback** | ~50ms | High | Sherpa VAD runs continuously |
| **Energy threshold** | ~10ms | Medium | Simple RMS comparison |
| **Gemini server-side** | ~100ms | Highest | Native interruption signal |

### 7.2 Barge-In Flow

```python
class BargeInHandler:
    def __init__(self, voice_pipeline: VoicePipeline):
        self.pipeline = voice_pipeline
        self.vad_active_during_playback = True
    
    async def handle_barge_in(self):
        """Called when VAD detects speech during SPEAKING state"""
        
        # 1. Immediately stop playback
        await self.pipeline.audio_output.clear()  # Clear queued chunks
        if self.pipeline.playback_task:
            self.pipeline.playback_task.cancel()
            try:
                await self.pipeline.playback_task
            except asyncio.CancelledError:
                pass
        await self.pipeline.runtime.tauri_commands.audio_stop_playback()
        
        # 2. Signal Gemini Live to stop generating
        if self.pipeline.gemini_live.connected:
            await self.pipeline.gemini_live.send_interrupt()
        
        # 3. Restart VAD/ASR for new input
        await self.pipeline.vad_asr.restart()
        
        # 4. Transition state
        self.pipeline._set_state(VoiceState.LISTENING)
        
        # 5. Notify UI
        await self.pipeline.runtime.events.emit("voice.barge_in", {
            "previous_state": "speaking",
            "timestamp": datetime.utcnow().isoformat(),
        })
```

### 7.3 Audio Ducking (Alternative to Full Stop)

For softer interruptions, implement ducking:
```rust
// In Rust audio mixer
pub fn set_ducking(&mut self, enabled: bool, duck_level: f32) {
    self.ducking = enabled;
    self.duck_level = duck_level;  // 0.0 = mute, 1.0 = full volume
}

// In playback callback
if self.ducking && self.vad_detected_speech {
    let gain = self.duck_level;
    for sample in data.iter_mut() {
        *sample *= gain;
    }
}
```

---

## 8. Multi-Language Support (English + Telugu)

### 8.1 Language Detection

```python
class LanguageDetector:
    """Detect language from ASR output for code-switching"""
    
    def __init__(self):
        self.fasttext_model = fasttext.load_model("models/lid.176.ftz")
    
    def detect(self, text: str) -> Tuple[str, float]:
        """Returns (language_code, confidence)"""
        # FastText lid.176 supports 176 languages including Telugu
        predictions = self.fasttext_model.predict(text, k=2)
        lang = predictions[0][0].replace("__label__", "")
        conf = predictions[1][0]
        return lang, conf
    
    def detect_streaming(self, chunks: List[str]) -> str:
        """Detect dominant language from recent chunks"""
        combined = " ".join(chunks[-5:])  # Last 5 chunks
        lang, conf = self.detect(combined)
        return lang if conf > 0.8 else "en"  # Default to English
```

### 8.2 Sherpa-ONNX Multilingual Configuration

```python
# Sherpa-ONNX supports multilingual ASR via single model
# Model trained on English + Telugu (and others)
# Language ID emitted in output: "en" or "te"

@dataclass
class MultilingualASRConfig:
    # Model handles both languages internally
    # No separate model needed
    
    # Language hints (optional)
    language_hints: List[str] = ["en", "te"]
    
    # Code-switching: model automatically handles
    # mid-sentence language switches
    
    # Post-processing: format Telugu in native script
    telugu_output_script: str = "native"  # native, transliterated
```

### 8.3 Gemini Live Multilingual

```python
# Gemini Live automatically handles multilingual input
# System instruction can specify:
SYSTEM_INSTRUCTION_MULTILINGUAL = """
You are ARISE, a bilingual voice assistant fluent in English and Telugu.
- Respond in the same language as the user
- If user code-switches, follow their lead
- For technical terms, use English terms commonly used in Telugu tech community
- Telugu responses should use native script (తెలుగు)
"""
```

---

## 9. Privacy & Security

### 9.1 Data Flow Privacy

| Stage | Data Leaves Device? | Encryption | Retention |
|-------|---------------------|------------|-----------|
| Wake Word | No | N/A | None (processed in RAM) |
| VAD/ASR | No | N/A | None (streaming) |
| Gemini Live | Yes (audio/text) | TLS 1.3 | Google policy (configurable) |
| TTS (Cloud) | Yes (text) | TLS 1.3 | Provider policy |
| TTS (Local) | No | N/A | None |

### 9.2 Privacy Modes

```python
class PrivacyMode(Enum):
    STANDARD = "standard"      # Cloud ASR + Cloud LLM + Cloud TTS
    PRIVATE = "private"        # Local ASR + Cloud LLM (no audio logging) + Cloud TTS
    LOCAL_ONLY = "local_only"  # Local ASR + Local LLM (Ollama) + Local TTS

class VoicePrivacyConfig:
    mode: PrivacyMode = PrivacyMode.STANDARD
    
    # For PRIVATE mode
    gemini_data_logging_opt_out: bool = True  # Via API parameters
    
    # For LOCAL_ONLY mode
    local_llm_endpoint: str = "http://localhost:11434"
    local_tts_model: str = "piper"
    
    # Audio retention
    delete_audio_after_seconds: int = 0  # 0 = immediate
    save_transcripts: bool = True
    encrypt_transcripts: bool = True
```

### 9.3 Audio Buffer Security

```python
class SecureAudioBuffer:
    """In-memory audio buffer with automatic zeroization"""
    
    def __init__(self, max_seconds: int = 30):
        self.max_samples = max_seconds * 16000
        self.buffer = bytearray()
        self._lock = asyncio.Lock()
    
    async def write(self, data: bytes):
        async with self._lock:
            self.buffer.extend(data)
            if len(self.buffer) > self.max_samples * 2:  # 2 bytes per sample
                # Keep only recent
                self.buffer = self.buffer[-self.max_samples * 2:]
    
    async def read_all(self) -> bytes:
        async with self._lock:
            data = bytes(self.buffer)
            self.buffer.clear()
            return data
    
    def zeroize(self):
        """Securely wipe buffer (called on mute/shutdown)"""
        for i in range(len(self.buffer)):
            self.buffer[i] = 0
        self.buffer.clear()
    
    def __del__(self):
        self.zeroize()
```

---

## 10. Performance Targets

| Metric | Target | Measurement |
|--------|--------|-------------|
| Wake word detection latency | <100ms | Porcupine benchmark |
| VAD first speech detection | <200ms | Sherpa-ONNX benchmark |
| ASR first token latency | <300ms | End-to-end (mic → text) |
| Gemini Live first audio | <800ms | End-to-end (mic → speaker) |
| Barge-in response | <150ms | Interrupt → new audio |
| Session resumption | <500ms | Reconnect + context restore |
| CPU (dormant) | <2% | Porcupine only |
| CPU (active) | <15% | Full pipeline |
| Memory (dormant) | <50MB | Porcupine + buffers |
| Memory (active) | <500MB | All models loaded |

---

## 11. Fallback & Degradation Matrix

| Failure | Detection | Fallback | User Impact |
|---------|-----------|----------|-------------|
| Porcupine crash | Health check fail | Restart detector | Brief wake word downtime |
| Sherpa-ONNX OOM | Memory monitor | Unload model, reload | ~2s ASR downtime |
| Gemini Live disconnect | WS close/error | Reconnect with token | <1s if token valid |
| Gemini API quota exceeded | 429 response | Switch to fallback model | Seamless |
| TTS provider fail | Exception | Next provider in chain | Slight quality change |
| Audio device lost | CPAL error | Re-enumerate devices | ~500ms silence |
| Network offline | Connectivity check | Local-only mode | Reduced capabilities |

---

## 12. Testing Strategy

### 12.1 Unit Tests

```python
# tests/voice/test_pipeline.py

async def test_wake_word_detection():
    detector = WakeWordDetector(["hey arise"], sensitivity=0.5)
    await detector.start(callback)
    
    # Feed synthetic audio with wake word
    audio = generate_wake_word_audio("hey arise")
    await detector.process_audio(audio)
    
    assert callback_called_with("hey arise")

async def test_vad_asr_streaming():
    vad_asr = SherpaVADASR(vad_sensitivity="medium")
    await vad_asr.start(on_start, on_end, on_transcript)
    
    # Feed speech audio in chunks
    for chunk in split_audio(speech_audio, chunk_size=512):
        await vad_asr.push_audio(chunk)
    
    assert final_transcript_received

async def test_barge_in_handling():
    pipeline = VoicePipeline(config)
    pipeline._set_state(VoiceState.SPEAKING)
    
    # Simulate VAD detecting speech during playback
    await pipeline.vad_asr.simulate_speech_detected()
    
    assert pipeline.state == VoiceState.LISTENING
    assert playback_stopped
    assert gemini_interrupt_sent
```

### 12.2 Integration Tests

| Test | Scenario | Success Criteria |
|------|----------|------------------|
| `test_full_voice_turn` | Wake → Speak → Response | <2s end-to-end |
| `test_barge_in` | Interrupt during response | <150ms new response |
| `test_session_resume` | Disconnect + reconnect | Context preserved |
| `test_multilingual` | English → Telugu switch | Correct language detected |
| `test_fallback_chain` | Primary TTS fails | Fallback activates |
| `test_privacy_modes` | Each privacy mode | No data leaks |

### 12.3 Load Testing

```python
async def test_concurrent_voice_sessions():
    """Simulate multiple rapid voice interactions"""
    for i in range(50):
        await pipeline.simulate_voice_turn(f"Test command {i}")
        assert pipeline.state == VoiceState.DORMANT
    
    # No memory leaks, no audio glitches
```

---

## 13. Configuration Reference

```toml
# config/voice.toml

[wake_word]
keywords = ["hey arise", "computer"]
sensitivity = 0.5
access_key = "${PORCUPINE_ACCESS_KEY}"
custom_models = { "hey arise" = "models/wake_words/hey_arise.ppn" }

[vad_asr]
vad_threshold = 0.5
vad_min_silence_ms = 500
model_dir = "models/sherpa"
language = "auto"
num_threads = 2

[gemini_live]
model = "gemini-3.8-live"
api_key = "${GEMINI_API_KEY}"
system_instruction = "You are ARISE, a helpful voice assistant..."
voice_name = "Puck"
session_resumption = true

[tts]
primary = "elevenlabs"
fallback_chain = ["elevenlabs", "openai", "local"]
elevenlabs_voice = "Rachel"
elevenlabs_model = "eleven_turbo_v2_5"
openai_voice = "alloy"
openai_model = "tts-1-hd"
local_model_path = "models/piper/en_US-lessac-medium.onnx"

[privacy]
mode = "standard"  # standard, private, local_only
delete_audio_after_seconds = 0
save_transcripts = true
encrypt_transcripts = true

[audio]
sample_rate = 16000
channels = 1
input_device = "default"
output_device = "default"
buffer_size_ms = 100

[performance]
max_concurrent_streams = 1
preload_models = true
model_cache_dir = "cache/models"
```

---

## 14. Open Voice Architecture Decisions

| Decision | Options | Considerations |
|----------|---------|----------------|
| Wake word engine | Porcupine / Raven / Custom | Porcupine: mature, licensing; Raven: newer, same vendor |
| ASR engine | Sherpa-ONNX / Whisper.cpp / Vosk | Sherpa: streaming, multilingual; Whisper: higher accuracy, batch |
| Local LLM for privacy | Ollama / llama.cpp / MLX | Ollama: easy; llama.cpp: flexible; MLX: Apple Silicon |
| Audio backend | CPAL / rodio / WASAPI direct | CPAL: cross-platform; WASAPI: Windows exclusive mode |
| Speaker diarization | None / pyannote / Sherpa | Needed for multi-user? |
| Voice activity UI | Waveform / Orb / Text only | Accessibility vs aesthetics |
| Custom wake word training | Picovoice Console / OpenWakeWord | Picovoice: paid, accurate; OpenWakeWord: free, less accurate |