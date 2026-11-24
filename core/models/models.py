"""
Core Models for ARISE.

Defines core data structures for model routing and completion:
- Model capabilities and specifications
- Completion request/response types
- Streaming chunks
- Provider health tracking
- Routing rules
- Usage statistics
- Circuit breaker states
"""

from __future__ import annotations
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class ModelCapability(str, Enum):
    """Model capabilities for routing and selection."""
    TEXT_GENERATION = "text_generation"
    CHAT = "chat"
    EMBEDDINGS = "embeddings"
    VISION = "vision"
    AUDIO_INPUT = "audio_input"
    AUDIO_OUTPUT = "audio_output"
    TOOL_CALLING = "tool_calling"
    REASONING = "reasoning"
    REALTIME_AUDIO = "realtime_audio"
    STREAMING = "streaming"


class LatencyTier(str, Enum):
    """Latency tier classification."""
    FAST = "fast"
    BALANCED = "balanced"
    QUALITY = "quality"


class PrivacyMode(str, Enum):
    """Privacy mode for requests."""
    OFF = "off"
    STANDARD = "standard"
    PRIVATE = "private"
    ENTERPRISE = "enterprise"
    LOCAL_ONLY = "local_only"


class CircuitState(str, Enum):
    """Circuit breaker states."""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class TaskType(str, Enum):
    """Task types for routing."""
    CHAT = "chat"
    COMPLETION = "completion"
    EMBEDDING = "embedding"
    VISION = "vision"
    AUDIO_TRANSCRIPTION = "audio_transcription"
    AUDIO_GENERATION = "audio_generation"
    TOOL_CALLING = "tool_calling"
    REASONING = "reasoning"
    REALTIME = "realtime"
    CODE_GENERATION = "code_generation"
    SUMMARIZATION = "summarization"
    CLASSIFICATION = "classification"
    EXTRACTION = "extraction"


@dataclass
class ModelSpec:
    """Model specification with capabilities and pricing."""
    id: str
    name: str
    provider: str
    capabilities: List[ModelCapability] = field(default_factory=list)
    context_window: int = 4096
    max_output_tokens: int = 4096
    pricing: Dict[str, float] = field(default_factory=dict)  # input, output, cached_input per 1M tokens
    latency_tier: LatencyTier = LatencyTier.BALANCED
    supports_streaming: bool = True
    supports_json_mode: bool = False
    supports_parallel_tool_calls: bool = False
    deprecated: bool = False

    def __post_init__(self):
        # Ensure pricing has required keys with defaults
        if "input" not in self.pricing:
            self.pricing["input"] = 0.0
        if "output" not in self.pricing:
            self.pricing["output"] = 0.0
        if "cached_input" not in self.pricing:
            self.pricing["cached_input"] = 0.0
        # Convert string capabilities to enum if needed
        self.capabilities = [
            ModelCapability(c) if isinstance(c, str) else c
            for c in self.capabilities
        ]

    def has_capability(self, capability: ModelCapability) -> bool:
        """Check if model has a specific capability."""
        return capability in self.capabilities

    def estimate_cost(self, input_tokens: int, output_tokens: int, cached_input_tokens: int = 0) -> float:
        """Estimate cost for a request in USD."""
        input_cost = (input_tokens - cached_input_tokens) * self.pricing.get("input", 0.0) / 1_000_000
        cached_cost = cached_input_tokens * self.pricing.get("cached_input", 0.0) / 1_000_000
        output_cost = output_tokens * self.pricing.get("output", 0.0) / 1_000_000
        return input_cost + cached_cost + output_cost

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "provider": self.provider,
            "capabilities": [c.value for c in self.capabilities],
            "context_window": self.context_window,
            "max_output_tokens": self.max_output_tokens,
            "pricing": self.pricing,
            "latency_tier": self.latency_tier.value,
            "supports_streaming": self.supports_streaming,
            "supports_json_mode": self.supports_json_mode,
            "supports_parallel_tool_calls": self.supports_parallel_tool_calls,
            "deprecated": self.deprecated,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModelSpec":
        return cls(
            id=data["id"],
            name=data["name"],
            provider=data["provider"],
            capabilities=[ModelCapability(c) for c in data.get("capabilities", [])],
            context_window=data.get("context_window", 4096),
            max_output_tokens=data.get("max_output_tokens", 4096),
            pricing=data.get("pricing", {}),
            latency_tier=LatencyTier(data.get("latency_tier", "balanced")),
            supports_streaming=data.get("supports_streaming", True),
            supports_json_mode=data.get("supports_json_mode", False),
            supports_parallel_tool_calls=data.get("supports_parallel_tool_calls", False),
            deprecated=data.get("deprecated", False),
        )


@dataclass
class Message:
    """A chat message."""
    role: str  # system, user, assistant, tool
    content: str
    name: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {"role": self.role, "content": self.content}
        if self.name:
            result["name"] = self.name
        if self.tool_call_id:
            result["tool_call_id"] = self.tool_call_id
        if self.tool_calls:
            result["tool_calls"] = self.tool_calls
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        return cls(
            role=data["role"],
            content=data["content"],
            name=data.get("name"),
            tool_call_id=data.get("tool_call_id"),
            tool_calls=data.get("tool_calls"),
        )


@dataclass
class ToolCall:
    """A tool call from the model."""
    id: str
    name: str
    arguments: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "arguments": self.arguments,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolCall":
        return cls(
            id=data["id"],
            name=data["name"],
            arguments=data["arguments"],
        )


@dataclass
class CompletionRequest:
    """Request for model completion."""
    messages: List[Message]
    model: Optional[str] = None
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[Any] = None  # "auto", "none", or specific tool name
    response_format: Optional[Dict[str, Any]] = None
    stream: bool = False
    metadata: Optional[Dict[str, Any]] = None
    privacy_mode: PrivacyMode = PrivacyMode.STANDARD

    def __post_init__(self):
        # Convert dict messages to Message objects
        self.messages = [
            Message.from_dict(m) if isinstance(m, dict) else m
            for m in self.messages
        ]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "messages": [m.to_dict() for m in self.messages],
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "tools": self.tools,
            "tool_choice": self.tool_choice,
            "response_format": self.response_format,
            "stream": self.stream,
            "metadata": self.metadata,
            "privacy_mode": self.privacy_mode.value,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CompletionRequest":
        return cls(
            messages=[Message.from_dict(m) for m in data.get("messages", [])],
            model=data.get("model"),
            temperature=data.get("temperature", 0.7),
            max_tokens=data.get("max_tokens"),
            tools=data.get("tools"),
            tool_choice=data.get("tool_choice"),
            response_format=data.get("response_format"),
            stream=data.get("stream", False),
            metadata=data.get("metadata"),
            privacy_mode=PrivacyMode(data.get("privacy_mode", "standard")),
        )


@dataclass
class CompletionResponse:
    """Response from model completion."""
    content: str
    model: str
    usage: Dict[str, int]  # prompt_tokens, completion_tokens, total_tokens
    finish_reason: str  # stop, length, tool_calls, content_filter
    tool_calls: Optional[List[ToolCall]] = None
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        # Ensure usage has required keys
        if "prompt_tokens" not in self.usage:
            self.usage["prompt_tokens"] = 0
        if "completion_tokens" not in self.usage:
            self.usage["completion_tokens"] = 0
        if "total_tokens" not in self.usage:
            self.usage["total_tokens"] = self.usage.get("prompt_tokens", 0) + self.usage.get("completion_tokens", 0)
        # Convert tool_calls to ToolCall objects if dicts
        if self.tool_calls:
            self.tool_calls = [
                ToolCall.from_dict(tc) if isinstance(tc, dict) else tc
                for tc in self.tool_calls
            ]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "model": self.model,
            "usage": self.usage,
            "finish_reason": self.finish_reason,
            "tool_calls": [tc.to_dict() for tc in self.tool_calls] if self.tool_calls else None,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CompletionResponse":
        return cls(
            content=data["content"],
            model=data["model"],
            usage=data["usage"],
            finish_reason=data["finish_reason"],
            tool_calls=[ToolCall.from_dict(tc) for tc in data.get("tool_calls", [])] if data.get("tool_calls") else None,
            metadata=data.get("metadata"),
        )


@dataclass
class StreamChunk:
    """A streaming chunk from model response."""
    delta: str
    finish_reason: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None

    def __post_init__(self):
        if self.tool_calls:
            self.tool_calls = [
                ToolCall.from_dict(tc) if isinstance(tc, dict) else tc
                for tc in self.tool_calls
            ]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "delta": self.delta,
            "finish_reason": self.finish_reason,
            "tool_calls": [tc.to_dict() for tc in self.tool_calls] if self.tool_calls else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StreamChunk":
        return cls(
            delta=data["delta"],
            finish_reason=data.get("finish_reason"),
            tool_calls=[ToolCall.from_dict(tc) for tc in data.get("tool_calls", [])] if data.get("tool_calls") else None,
        )


@dataclass
class ProviderHealth:
    """Health status of a model provider."""
    name: str
    healthy: bool
    latency_ms: Optional[float] = None
    error: Optional[str] = None
    last_check: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    consecutive_failures: int = 0
    consecutive_successes: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "healthy": self.healthy,
            "latency_ms": self.latency_ms,
            "error": self.error,
            "last_check": self.last_check.isoformat(),
            "consecutive_failures": self.consecutive_failures,
            "consecutive_successes": self.consecutive_successes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProviderHealth":
        return cls(
            name=data["name"],
            healthy=data["healthy"],
            latency_ms=data.get("latency_ms"),
            error=data.get("error"),
            last_check=datetime.fromisoformat(data["last_check"]) if data.get("last_check") else datetime.now(timezone.utc),
            consecutive_failures=data.get("consecutive_failures", 0),
            consecutive_successes=data.get("consecutive_successes", 0),
        )


@dataclass
class RoutingRule:
    """Routing rule for model selection."""
    task_type: TaskType
    required_capabilities: List[ModelCapability] = field(default_factory=list)
    preferred_providers: List[str] = field(default_factory=list)
    fallback_providers: List[str] = field(default_factory=list)
    max_latency_ms: Optional[int] = None
    max_cost_per_request: Optional[float] = None
    privacy_mode: PrivacyMode = PrivacyMode.STANDARD
    priority: int = 0  # Higher priority rules evaluated first

    def __post_init__(self):
        self.required_capabilities = [
            ModelCapability(c) if isinstance(c, str) else c
            for c in self.required_capabilities
        ]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_type": self.task_type.value,
            "required_capabilities": [c.value for c in self.required_capabilities],
            "preferred_providers": self.preferred_providers,
            "fallback_providers": self.fallback_providers,
            "max_latency_ms": self.max_latency_ms,
            "max_cost_per_request": self.max_cost_per_request,
            "privacy_mode": self.privacy_mode.value,
            "priority": self.priority,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RoutingRule":
        return cls(
            task_type=TaskType(data["task_type"]),
            required_capabilities=[ModelCapability(c) for c in data.get("required_capabilities", [])],
            preferred_providers=data.get("preferred_providers", []),
            fallback_providers=data.get("fallback_providers", []),
            max_latency_ms=data.get("max_latency_ms"),
            max_cost_per_request=data.get("max_cost_per_request"),
            privacy_mode=PrivacyMode(data.get("privacy_mode", "standard")),
            priority=data.get("priority", 0),
        )


@dataclass
class UsageStats:
    """Usage statistics for tracking."""
    total_requests: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    by_provider: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    by_model: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    by_task_type: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def record_request(
        self,
        provider: str,
        model: str,
        task_type: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost: float
    ) -> None:
        """Record a request for statistics."""
        self.total_requests += 1
        self.total_tokens += prompt_tokens + completion_tokens
        self.total_cost += cost

        # By provider
        if provider not in self.by_provider:
            self.by_provider[provider] = {"requests": 0, "tokens": 0, "cost": 0.0}
        self.by_provider[provider]["requests"] += 1
        self.by_provider[provider]["tokens"] += prompt_tokens + completion_tokens
        self.by_provider[provider]["cost"] += cost

        # By model
        if model not in self.by_model:
            self.by_model[model] = {"requests": 0, "tokens": 0, "cost": 0.0}
        self.by_model[model]["requests"] += 1
        self.by_model[model]["tokens"] += prompt_tokens + completion_tokens
        self.by_model[model]["cost"] += cost

        # By task type
        if task_type not in self.by_task_type:
            self.by_task_type[task_type] = {"requests": 0, "tokens": 0, "cost": 0.0}
        self.by_task_type[task_type]["requests"] += 1
        self.by_task_type[task_type]["tokens"] += prompt_tokens + completion_tokens
        self.by_task_type[task_type]["cost"] += cost

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_requests": self.total_requests,
            "total_tokens": self.total_tokens,
            "total_cost": self.total_cost,
            "by_provider": self.by_provider,
            "by_model": self.by_model,
            "by_task_type": self.by_task_type,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UsageStats":
        return cls(
            total_requests=data.get("total_requests", 0),
            total_tokens=data.get("total_tokens", 0),
            total_cost=data.get("total_cost", 0.0),
            by_provider=data.get("by_provider", {}),
            by_model=data.get("by_model", {}),
            by_task_type=data.get("by_task_type", {}),
        )


# Default routing rules
DEFAULT_ROUTING_RULES = [
    RoutingRule(
        task_type=TaskType.CHAT,
        required_capabilities=[ModelCapability.CHAT],
        preferred_providers=["anthropic", "openai"],
        fallback_providers=["google", "mistral"],
        max_latency_ms=5000,
        priority=10,
    ),
    RoutingRule(
        task_type=TaskType.COMPLETION,
        required_capabilities=[ModelCapability.TEXT_GENERATION],
        preferred_providers=["anthropic", "openai"],
        fallback_providers=["google", "mistral"],
        max_latency_ms=5000,
        priority=10,
    ),
    RoutingRule(
        task_type=TaskType.EMBEDDING,
        required_capabilities=[ModelCapability.EMBEDDINGS],
        preferred_providers=["openai", "google"],
        fallback_providers=["mistral", "cohere"],
        max_latency_ms=3000,
        priority=10,
    ),
    RoutingRule(
        task_type=TaskType.VISION,
        required_capabilities=[ModelCapability.VISION],
        preferred_providers=["anthropic", "openai", "google"],
        fallback_providers=[],
        max_latency_ms=10000,
        priority=10,
    ),
    RoutingRule(
        task_type=TaskType.TOOL_CALLING,
        required_capabilities=[ModelCapability.TOOL_CALLING],
        preferred_providers=["anthropic", "openai"],
        fallback_providers=["google"],
        max_latency_ms=8000,
        priority=10,
    ),
    RoutingRule(
        task_type=TaskType.REASONING,
        required_capabilities=[ModelCapability.REASONING],
        preferred_providers=["anthropic", "openai"],
        fallback_providers=[],
        max_latency_ms=15000,
        priority=10,
    ),
    RoutingRule(
        task_type=TaskType.REALTIME,
        required_capabilities=[ModelCapability.REALTIME_AUDIO, ModelCapability.STREAMING],
        preferred_providers=["openai"],
        fallback_providers=[],
        max_latency_ms=500,
        priority=10,
    ),
    RoutingRule(
        task_type=TaskType.CODE_GENERATION,
        required_capabilities=[ModelCapability.CHAT, ModelCapability.TOOL_CALLING],
        preferred_providers=["anthropic", "openai"],
        fallback_providers=["google", "mistral"],
        max_latency_ms=10000,
        priority=10,
    ),
    RoutingRule(
        task_type=TaskType.SUMMARIZATION,
        required_capabilities=[ModelCapability.CHAT],
        preferred_providers=["anthropic", "openai"],
        fallback_providers=["google", "mistral"],
        max_latency_ms=5000,
        priority=5,
    ),
    RoutingRule(
        task_type=TaskType.CLASSIFICATION,
        required_capabilities=[ModelCapability.CHAT],
        preferred_providers=["anthropic", "openai"],
        fallback_providers=["google", "mistral"],
        max_latency_ms=3000,
        priority=5,
    ),
    RoutingRule(
        task_type=TaskType.EXTRACTION,
        required_capabilities=[ModelCapability.CHAT, ModelCapability.TOOL_CALLING],
        preferred_providers=["anthropic", "openai"],
        fallback_providers=["google", "mistral"],
        max_latency_ms=5000,
        priority=5,
    ),
]