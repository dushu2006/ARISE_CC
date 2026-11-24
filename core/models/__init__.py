"""
Core Models Package for ARISE.

Provides model routing, provider management, cost tracking, and privacy filtering.
"""

from core.models.models import (
    ModelCapability,
    LatencyTier,
    PrivacyMode,
    CircuitState,
    TaskType,
    ModelSpec,
    Message,
    ToolCall,
    CompletionRequest,
    CompletionResponse,
    StreamChunk,
    ProviderHealth,
    RoutingRule,
    UsageStats,
    DEFAULT_ROUTING_RULES,
)

from core.models.providers.base import ModelProvider, ProviderRegistry, provider_registry
from core.models.providers.anthropic import AnthropicProvider
from core.models.providers.gemini import GeminiProvider
from core.models.providers.ollama import OllamaProvider

from core.models.engine import (
    ModelRouter,
    ModelRouterConfig,
    CircuitBreaker,
    init_model_router,
    shutdown_model_router,
    get_model_router,
)

from core.models.cost_tracker import (
    CostTracker,
    UsageRecord,
    get_cost_tracker,
    init_cost_tracker,
    shutdown_cost_tracker,
)

from core.models.privacy import (
    PrivacyFilter,
    PrivacyMode as PrivacyFilterMode,
    RedactionEvent,
    create_privacy_filter,
)

__all__ = [
    # Models
    "ModelCapability",
    "LatencyTier",
    "PrivacyMode",
    "CircuitState",
    "TaskType",
    "ModelSpec",
    "Message",
    "ToolCall",
    "CompletionRequest",
    "CompletionResponse",
    "StreamChunk",
    "ProviderHealth",
    "RoutingRule",
    "UsageStats",
    "DEFAULT_ROUTING_RULES",

    # Providers
    "ModelProvider",
    "ProviderRegistry",
    "provider_registry",
    "AnthropicProvider",
    "GeminiProvider",
    "OllamaProvider",

    # Engine
    "ModelRouter",
    "ModelRouterConfig",
    "CircuitBreaker",
    "init_model_router",
    "shutdown_model_router",
    "get_model_router",

    # Cost Tracker
    "CostTracker",
    "UsageRecord",
    "get_cost_tracker",
    "init_cost_tracker",
    "shutdown_cost_tracker",

    # Privacy
    "PrivacyFilter",
    "PrivacyFilterMode",
    "RedactionEvent",
    "create_privacy_filter",
]

__version__ = "1.0.0"