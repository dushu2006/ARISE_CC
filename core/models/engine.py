"""
Model Router Engine for ARISE.

Implements intelligent model routing with:
- Provider registration and management
- Task-based model selection with routing rules
- Circuit breaker per provider
- Privacy mode enforcement (local_only -> ollama only)
- Cost tracking integration
- Event emission for requests/errors (follows policy_engine pattern)
- Fallback chain with automatic failover
- Streaming and embedding support
- Health checks and usage statistics
"""

from __future__ import annotations
import asyncio
import logging
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Set

from core.config import load_config
from core.config.models import ModelRouterConfig as ConfigModelRouterConfig
from core.events import get_event_bus
from core.events.models import Event, EventPriority, EventTypes
from core.structured_logging import get_logger, log_structured
from core.models.cost_tracker import CostTracker, get_cost_tracker
from core.models.models import (
    CircuitState,
    CompletionRequest,
    CompletionResponse,
    LatencyTier,
    Message,
    ModelCapability,
    ModelSpec,
    PrivacyMode,
    ProviderHealth,
    RoutingRule,
    StreamChunk,
    TaskType,
    UsageStats,
    DEFAULT_ROUTING_RULES,
)
from core.models.privacy import PrivacyFilter, PrivacyMode as PrivacyFilterMode
from core.models.providers.base import ModelProvider, provider_registry

logger = get_logger(__name__)


class CircuitBreaker:
    """
    Circuit breaker for individual model providers.

    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Too many failures, requests fail fast
    - HALF_OPEN: Testing if provider recovered, limited requests
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        success_threshold: int = 2,
        timeout_seconds: int = 60,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.timeout_seconds = timeout_seconds

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[datetime] = None
        self._last_state_change = datetime.now(timezone.utc)
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        return self._state

    async def can_execute(self) -> bool:
        """Check if a request can be executed."""
        async with self._lock:
            if self._state == CircuitState.CLOSED:
                return True

            if self._state == CircuitState.OPEN:
                # Check if timeout has elapsed to transition to HALF_OPEN
                if self._last_failure_time:
                    elapsed = (datetime.now(timezone.utc) - self._last_failure_time).total_seconds()
                    if elapsed >= self.timeout_seconds:
                        self._state = CircuitState.HALF_OPEN
                        self._success_count = 0
                        self._last_state_change = datetime.now(timezone.utc)
                        log_structured(
                            logger, logging.INFO,
                            "Circuit breaker transitioned to HALF_OPEN",
                            provider=self.name,
                        )
                        return True
                return False

            # HALF_OPEN - allow limited requests
            return True

    async def record_success(self) -> None:
        """Record a successful request."""
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._success_count = 0
                    self._last_state_change = datetime.now(timezone.utc)
                    log_structured(
                        logger, logging.INFO,
                        "Circuit breaker CLOSED after recovery",
                        provider=self.name,
                    )
            elif self._state == CircuitState.CLOSED:
                self._failure_count = 0  # Reset failure count on success

    async def record_failure(self) -> None:
        """Record a failed request."""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = datetime.now(timezone.utc)

            if self._state == CircuitState.HALF_OPEN:
                # Any failure in HALF_OPEN goes back to OPEN
                self._state = CircuitState.OPEN
                self._success_count = 0
                self._last_state_change = datetime.now(timezone.utc)
                log_structured(
                    logger, logging.WARNING,
                    "Circuit breaker OPENED after HALF_OPEN failure",
                    provider=self.name,
                )
            elif self._state == CircuitState.CLOSED:
                if self._failure_count >= self.failure_threshold:
                    self._state = CircuitState.OPEN
                    self._last_state_change = datetime.now(timezone.utc)
                    log_structured(
                        logger, logging.WARNING,
                        "Circuit breaker OPENED due to threshold",
                        provider=self.name,
                        failure_count=self._failure_count,
                        threshold=self.failure_threshold,
                    )

    def get_status(self) -> Dict[str, Any]:
        """Get circuit breaker status for monitoring."""
        return {
            "provider": self.name,
            "state": self._state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "failure_threshold": self.failure_threshold,
            "success_threshold": self.success_threshold,
            "timeout_seconds": self.timeout_seconds,
            "last_failure_time": self._last_failure_time.isoformat() if self._last_failure_time else None,
            "last_state_change": self._last_state_change.isoformat(),
        }


@dataclass
class ModelRouterConfig:
    """Model router configuration from config system."""
    default_provider: str = "anthropic"
    privacy_mode: PrivacyMode = PrivacyMode.STANDARD
    fallback_chain: List[str] = field(default_factory=lambda: [
        "anthropic", "openai", "google", "ollama"
    ])
    providers: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    cost_tracking_enabled: bool = True
    circuit_breaker_enabled: bool = True
    circuit_breaker_threshold: int = 5
    circuit_breaker_timeout: int = 60
    routing_rules: List[Dict[str, Any]] = field(default_factory=list)
    health_check_interval_seconds: int = 30

    @classmethod
    def from_config(cls, config: ConfigModelRouterConfig) -> "ModelRouterConfig":
        """Create from Pydantic config model."""
        return cls(
            default_provider=config.default_provider.value,
            privacy_mode=PrivacyMode(config.privacy_mode.value),
            fallback_chain=[p.value for p in config.fallback_chain],
            providers={
                k.value: v.model_dump() for k, v in config.providers.items()
            },
            cost_tracking_enabled=config.cost_tracking_enabled,
            circuit_breaker_enabled=config.circuit_breaker_enabled,
            circuit_breaker_threshold=config.circuit_breaker_threshold,
            circuit_breaker_timeout=config.circuit_breaker_timeout,
            health_check_interval_seconds=30,
        )


class ModelRouter:
    """
    Main model router for intelligent model selection and execution.

    Features:
    - Provider registration and lifecycle management
    - Task-based model selection with configurable routing rules
    - Circuit breaker per provider for fault tolerance
    - Privacy mode enforcement (local_only forces Ollama)
    - Cost tracking integration
    - Event emission for requests/errors
    - Fallback chain with automatic failover
    - Streaming and embedding support
    - Health checks and usage statistics
    """

    def __init__(
        self,
        config: ModelRouterConfig,
        cost_tracker: Optional[CostTracker] = None,
        privacy_filter: Optional[PrivacyFilter] = None,
    ):
        self.config = config
        self._cost_tracker = cost_tracker or get_cost_tracker()
        self._privacy_filter = privacy_filter or PrivacyFilter(
            mode=PrivacyFilterMode(config.privacy_mode.value)
        )

        # Provider management
        self._providers: Dict[str, ModelProvider] = {}
        self._provider_configs: Dict[str, Dict[str, Any]] = config.providers
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        self._provider_health: Dict[str, ProviderHealth] = {}

        # Routing rules
        self._routing_rules: List[RoutingRule] = []
        self._load_routing_rules()

        # Lifecycle
        self._running = False
        self._health_check_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()

        # Event emission
        self._event_bus = None

        # Stats
        self._request_count = 0
        self._error_count = 0

    def _load_routing_rules(self) -> None:
        """Load routing rules from config and defaults."""
        # Start with defaults
        self._routing_rules = DEFAULT_ROUTING_RULES.copy()

        # Override with config rules if provided
        if self.config.routing_rules:
            for rule_data in self.config.routing_rules:
                rule = RoutingRule.from_dict(rule_data)
                # Replace existing rule for same task_type or add new
                existing_idx = next(
                    (i for i, r in enumerate(self._routing_rules) if r.task_type == rule.task_type),
                    None
                )
                if existing_idx is not None:
                    self._routing_rules[existing_idx] = rule
                else:
                    self._routing_rules.append(rule)

        # Sort by priority (higher first)
        self._routing_rules.sort(key=lambda r: -r.priority)

    async def initialize(self) -> None:
        """Initialize the model router - register providers, start health checks."""
        log_structured(logger, logging.INFO, "Initializing Model Router")

        # Get event bus
        try:
            self._event_bus = await get_event_bus()
        except Exception as e:
            log_structured(logger, logging.DEBUG, "Event bus not available", error=str(e))

        # Register providers from config
        for provider_name, provider_config in self._provider_configs.items():
            if provider_config.get("enabled", True):
                await self._register_provider_from_config(provider_name, provider_config)

        # Initialize circuit breakers for registered providers
        if self.config.circuit_breaker_enabled:
            for provider_name in self._providers:
                self._circuit_breakers[provider_name] = CircuitBreaker(
                    name=provider_name,
                    failure_threshold=self.config.circuit_breaker_threshold,
                    timeout_seconds=self.config.circuit_breaker_timeout,
                )

        # Start health check loop
        self._running = True
        self._health_check_task = asyncio.create_task(self._health_check_loop())

        # Emit startup event
        await self._emit_event(
            EventTypes.MODEL_REQUEST,  # Using existing event type
            {
                "event_type": "model_router_initialized",
                "providers": list(self._providers.keys()),
                "privacy_mode": self.config.privacy_mode.value,
            },
            source="model_router",
        )

        log_structured(logger, logging.INFO, "Model Router initialized", providers=list(self._providers.keys()))

    async def _register_provider_from_config(self, name: str, config: Dict[str, Any]) -> None:
        """Register a provider from configuration."""
        try:
            # Import provider class dynamically
            if name == "anthropic":
                from core.models.providers.anthropic import AnthropicProvider
                provider = AnthropicProvider(config.get("api_key", ""), config)
            elif name == "google" or name == "gemini":
                from core.models.providers.gemini import GeminiProvider
                provider = GeminiProvider(config.get("api_key", ""), config)
            elif name == "ollama":
                from core.models.providers.ollama import OllamaProvider
                provider = OllamaProvider(config)
            else:
                # Try to get from registry
                if name in provider_registry:
                    provider = provider_registry.get(name)
                else:
                    raise ValueError(f"Unknown provider: {name}")

            await self.register_provider(provider)

        except Exception as e:
            log_structured(logger, logging.ERROR, "Failed to register provider", provider=name, error=str(e))

    async def register_provider(self, provider: ModelProvider) -> None:
        """Register a provider instance."""
        if provider.name in self._providers:
            log_structured(logger, logging.WARNING, "Provider already registered, replacing", provider=provider.name)

        self._providers[provider.name] = provider
        self._provider_health[provider.name] = ProviderHealth(
            name=provider.name,
            healthy=True,
        )

        # Create circuit breaker for this provider if enabled
        if self.config.circuit_breaker_enabled and provider.name not in self._circuit_breakers:
            self._circuit_breakers[provider.name] = CircuitBreaker(
                name=provider.name,
                failure_threshold=self.config.circuit_breaker_threshold,
                timeout_seconds=self.config.circuit_breaker_timeout,
            )

        # Register in global registry too
        try:
            provider_registry.register(provider)
        except ValueError:
            pass  # Already registered

        log_structured(logger, logging.INFO, "Provider registered", provider=provider.name)

    async def shutdown(self) -> None:
        """Shutdown the model router - close all providers."""
        log_structured(logger, logging.INFO, "Shutting down Model Router")
        self._running = False
        self._shutdown_event.set()

        # Stop health check loop
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass

        # Close all providers
        for name, provider in self._providers.items():
            try:
                await provider.close()
                log_structured(logger, logging.INFO, "Provider closed", provider=name)
            except Exception as e:
                log_structured(logger, logging.ERROR, "Error closing provider", provider=name, error=str(e))

        self._providers.clear()

        # Emit shutdown event
        await self._emit_event(
            EventTypes.MODEL_REQUEST,
            {
                "event_type": "model_router_shutdown",
            },
            source="model_router",
        )

        log_structured(logger, logging.INFO, "Model Router stopped")

    # =========================================================================
    # Model Selection
    # =========================================================================

    async def select_model(
        self,
        task_type: TaskType,
        required_capabilities: Optional[List[ModelCapability]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> tuple[str, ModelSpec]:
        """
        Select the best model for a task based on routing rules.

        Returns:
            Tuple of (provider_name, ModelSpec)

        Raises:
            ValueError: If no suitable model found
        """
        context = context or {}
        required_capabilities = required_capabilities or []

        # Get applicable routing rule
        rule = self._get_routing_rule(task_type, required_capabilities)

        # Check privacy mode
        if self.config.privacy_mode == PrivacyMode.LOCAL_ONLY:
            # Force Ollama only
            if "ollama" not in self._providers:
                raise ValueError("LOCAL_ONLY mode requires Ollama provider")
            return await self._select_from_provider("ollama", required_capabilities, rule)

        # Check preferred providers from rule
        for provider_name in rule.preferred_providers:
            if provider_name in self._providers:
                # Check circuit breaker
                if await self._is_provider_available(provider_name):
                    result = await self._select_from_provider(provider_name, required_capabilities, rule)
                    if result:
                        return result

        # Check fallback providers from rule
        for provider_name in rule.fallback_providers:
            if provider_name in self._providers:
                if await self._is_provider_available(provider_name):
                    result = await self._select_from_provider(provider_name, required_capabilities, rule)
                    if result:
                        return result

        # Fall back to global fallback chain
        for provider_name in self.config.fallback_chain:
            if provider_name in self._providers:
                if await self._is_provider_available(provider_name):
                    result = await self._select_from_provider(provider_name, required_capabilities, rule)
                    if result:
                        return result

        # Last resort: any available provider
        for provider_name, provider in self._providers.items():
            if await self._is_provider_available(provider_name):
                result = await self._select_from_provider(provider_name, required_capabilities, rule)
                if result:
                    return result

        raise ValueError(f"No suitable model found for task_type={task_type.value}")

    def _get_routing_rule(
        self,
        task_type: TaskType,
        required_capabilities: List[ModelCapability],
    ) -> RoutingRule:
        """Find the best matching routing rule."""
        for rule in self._routing_rules:
            if rule.task_type == task_type:
                # Check if rule capabilities are satisfied
                if all(cap in required_capabilities for cap in rule.required_capabilities):
                    return rule
        # Default rule
        return RoutingRule(
            task_type=task_type,
            required_capabilities=required_capabilities,
            preferred_providers=self.config.fallback_chain,
            fallback_providers=[],
        )

    async def _select_from_provider(
        self,
        provider_name: str,
        required_capabilities: List[ModelCapability],
        rule: RoutingRule,
    ) -> Optional[tuple[str, ModelSpec]]:
        """Select best model from a specific provider."""
        provider = self._providers.get(provider_name)
        if not provider:
            return None

        # Try to get models from provider's list_models() method first
        # Fall back to defaults if not available
        try:
            models = await provider.list_models()
            if models:
                default_models = models
            else:
                default_models = self._get_default_models_for_provider(provider_name)
        except Exception:
            default_models = self._get_default_models_for_provider(provider_name)

        for model_spec in default_models:
            # Check capabilities
            if all(model_spec.has_capability(cap) for cap in required_capabilities):
                # Check latency tier if specified
                if rule.max_latency_ms and model_spec.latency_tier == LatencyTier.QUALITY:
                    continue  # Skip slow models if latency constraint

                # Check cost if specified
                if rule.max_cost_per_request:
                    estimated_cost = model_spec.estimate_cost(1000, 1000)
                    if estimated_cost > rule.max_cost_per_request:
                        continue

                return (provider_name, model_spec)

        return None

    def _get_default_models_for_provider(self, provider_name: str) -> List[ModelSpec]:
        """Get default model specs for a provider (fallback when list_models not available)."""
        defaults = {
            "anthropic": [
                ModelSpec(
                    id="claude-3-5-sonnet-20241022",
                    name="Claude 3.5 Sonnet",
                    provider="anthropic",
                    capabilities=[ModelCapability.CHAT, ModelCapability.TOOL_CALLING, ModelCapability.REASONING, ModelCapability.VISION, ModelCapability.STREAMING],
                    context_window=200000,
                    max_output_tokens=8192,
                    pricing={"input": 3.0, "output": 15.0, "cached_input": 0.3},
                    latency_tier=LatencyTier.BALANCED,
                ),
                ModelSpec(
                    id="claude-3-5-haiku-20241022",
                    name="Claude 3.5 Haiku",
                    provider="anthropic",
                    capabilities=[ModelCapability.CHAT, ModelCapability.TOOL_CALLING, ModelCapability.STREAMING],
                    context_window=200000,
                    max_output_tokens=8192,
                    pricing={"input": 0.8, "output": 4.0, "cached_input": 0.08},
                    latency_tier=LatencyTier.FAST,
                ),
                ModelSpec(
                    id="claude-3-opus-20240229",
                    name="Claude 3 Opus",
                    provider="anthropic",
                    capabilities=[ModelCapability.CHAT, ModelCapability.TOOL_CALLING, ModelCapability.REASONING, ModelCapability.VISION, ModelCapability.STREAMING],
                    context_window=200000,
                    max_output_tokens=4096,
                    pricing={"input": 15.0, "output": 75.0, "cached_input": 1.5},
                    latency_tier=LatencyTier.QUALITY,
                ),
            ],
            "openai": [
                ModelSpec(
                    id="gpt-4o",
                    name="GPT-4o",
                    provider="openai",
                    capabilities=[ModelCapability.CHAT, ModelCapability.TOOL_CALLING, ModelCapability.REASONING, ModelCapability.VISION, ModelCapability.STREAMING],
                    context_window=128000,
                    max_output_tokens=16384,
                    pricing={"input": 5.0, "output": 15.0, "cached_input": 2.5},
                    latency_tier=LatencyTier.BALANCED,
                ),
                ModelSpec(
                    id="gpt-4o-mini",
                    name="GPT-4o Mini",
                    provider="openai",
                    capabilities=[ModelCapability.CHAT, ModelCapability.TOOL_CALLING, ModelCapability.STREAMING],
                    context_window=128000,
                    max_output_tokens=16384,
                    pricing={"input": 0.15, "output": 0.6, "cached_input": 0.075},
                    latency_tier=LatencyTier.FAST,
                ),
            ],
            "google": [
                ModelSpec(
                    id="gemini-1.5-pro",
                    name="Gemini 1.5 Pro",
                    provider="google",
                    capabilities=[ModelCapability.CHAT, ModelCapability.TOOL_CALLING, ModelCapability.REASONING, ModelCapability.VISION, ModelCapability.STREAMING],
                    context_window=2000000,
                    max_output_tokens=8192,
                    pricing={"input": 3.5, "output": 10.5, "cached_input": 0.0},
                    latency_tier=LatencyTier.BALANCED,
                ),
                ModelSpec(
                    id="gemini-1.5-flash",
                    name="Gemini 1.5 Flash",
                    provider="google",
                    capabilities=[ModelCapability.CHAT, ModelCapability.TOOL_CALLING, ModelCapability.STREAMING],
                    context_window=1000000,
                    max_output_tokens=8192,
                    pricing={"input": 0.075, "output": 0.3, "cached_input": 0.0},
                    latency_tier=LatencyTier.FAST,
                ),
            ],
            "ollama": [
                ModelSpec(
                    id="llama3.1",
                    name="Llama 3.1",
                    provider="ollama",
                    capabilities=[ModelCapability.CHAT, ModelCapability.TOOL_CALLING, ModelCapability.STREAMING],
                    context_window=128000,
                    max_output_tokens=4096,
                    pricing={"input": 0.0, "output": 0.0, "cached_input": 0.0},
                    latency_tier=LatencyTier.BALANCED,
                ),
                ModelSpec(
                    id="llama3.2",
                    name="Llama 3.2",
                    provider="ollama",
                    capabilities=[ModelCapability.CHAT, ModelCapability.STREAMING],
                    context_window=128000,
                    max_output_tokens=4096,
                    pricing={"input": 0.0, "output": 0.0, "cached_input": 0.0},
                    latency_tier=LatencyTier.FAST,
                ),
            ],
        }
        return defaults.get(provider_name, [])

    async def _is_provider_available(self, provider_name: str) -> bool:
        """Check if provider is available (healthy and circuit closed)."""
        # Check health
        health = self._provider_health.get(provider_name)
        if health and not health.healthy:
            return False

        # Check circuit breaker
        if self.config.circuit_breaker_enabled:
            cb = self._circuit_breakers.get(provider_name)
            if cb:
                if not await cb.can_execute():
                    return False

        return True

    # =========================================================================
    # Completion Execution
    # =========================================================================

    async def complete(
        self,
        task_type: TaskType,
        request: CompletionRequest,
        context: Optional[Dict[str, Any]] = None,
    ) -> CompletionResponse:
        """
        Execute a completion request with fallback chain.

        Args:
            task_type: Type of task for routing
            request: Completion request
            context: Additional context

        Returns:
            CompletionResponse from the model
        """
        context = context or {}
        correlation_id = context.get("correlation_id", str(uuid.uuid4())[:12])
        start_time = time.perf_counter()

        # Apply privacy filter
        filtered_request = self._privacy_filter.filter_request(request)

        # Determine required capabilities from request
        required_capabilities = self._infer_capabilities(filtered_request)

        # Select model
        provider_name, model_spec = await self.select_model(task_type, required_capabilities, context)

        # Set model in request if not specified
        if not filtered_request.model:
            filtered_request.model = model_spec.id

        # Emit request event
        await self._emit_event(
            EventTypes.MODEL_REQUEST,
            {
                "event_type": "completion_request",
                "task_type": task_type.value,
                "provider": provider_name,
                "model": model_spec.id,
                "privacy_mode": self.config.privacy_mode.value,
                "stream": filtered_request.stream,
                "correlation_id": correlation_id,
            },
            source="model_router",
            correlation_id=correlation_id,
        )

        # Execute with fallback
        last_error = None
        providers_tried: Set[str] = set()

        while True:
            provider = self._providers.get(provider_name)
            if not provider:
                break

            providers_tried.add(provider_name)

            try:
                # Check circuit breaker
                if self.config.circuit_breaker_enabled:
                    cb = self._circuit_breakers.get(provider_name)
                    if cb and not await cb.can_execute():
                        raise RuntimeError(f"Circuit breaker OPEN for {provider_name}")

                # Execute request
                response = await provider.complete(filtered_request)

                # Record success
                if self.config.circuit_breaker_enabled:
                    cb = self._circuit_breakers.get(provider_name)
                    if cb:
                        await cb.record_success()

                # Update health
                self._update_provider_health(provider_name, True, time.perf_counter() - start_time)

                # Track cost
                if self.config.cost_tracking_enabled:
                    self._track_cost(provider_name, model_spec.id, task_type, response.usage, time.perf_counter() - start_time)

                # Emit success event
                await self._emit_event(
                    EventTypes.MODEL_RESPONSE,
                    {
                        "event_type": "completion_success",
                        "task_type": task_type.value,
                        "provider": provider_name,
                        "model": model_spec.id,
                        "usage": response.usage,
                        "latency_ms": round((time.perf_counter() - start_time) * 1000, 2),
                        "correlation_id": correlation_id,
                    },
                    source="model_router",
                    correlation_id=correlation_id,
                )

                self._request_count += 1
                return response

            except Exception as e:
                last_error = e
                latency_ms = round((time.perf_counter() - start_time) * 1000, 2)

                # Record failure
                if self.config.circuit_breaker_enabled:
                    cb = self._circuit_breakers.get(provider_name)
                    if cb:
                        await cb.record_failure()

                # Update health
                self._update_provider_health(provider_name, False, latency_ms / 1000.0, str(e))

                # Emit error event
                await self._emit_event(
                    EventTypes.MODEL_ERROR,
                    {
                        "event_type": "completion_error",
                        "task_type": task_type.value,
                        "provider": provider_name,
                        "model": model_spec.id,
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "latency_ms": latency_ms,
                        "correlation_id": correlation_id,
                    },
                    source="model_router",
                    correlation_id=correlation_id,
                )

                log_structured(logger, logging.WARNING, "Provider failed, trying fallback",
                    provider=provider_name, error=str(e), correlation_id=correlation_id)

                # Try next fallback
                provider_name = self._get_next_fallback(provider_name, providers_tried, task_type, required_capabilities)
                if not provider_name:
                    break

                # Get new model spec for fallback provider
                rule = self._get_routing_rule(task_type, required_capabilities)
                fallback_result = await self._select_from_provider(provider_name, required_capabilities, rule)
                if fallback_result:
                    provider_name, model_spec = fallback_result
                    if not filtered_request.model:
                        filtered_request.model = model_spec.id
                else:
                    break

        # All providers failed
        self._error_count += 1
        await self._emit_event(
            EventTypes.MODEL_ERROR,
            {
                "event_type": "completion_failed_all",
                "task_type": task_type.value,
                "providers_tried": list(providers_tried),
                "last_error": str(last_error),
                "correlation_id": correlation_id,
            },
            source="model_router",
            correlation_id=correlation_id,
            priority=EventPriority.HIGH,
        )

        raise RuntimeError(f"All providers failed for task {task_type.value}. Last error: {last_error}")

    async def stream_complete(
        self,
        task_type: TaskType,
        request: CompletionRequest,
        context: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Execute a streaming completion request with fallback chain.

        Args:
            task_type: Type of task for routing
            request: Completion request (stream=True)
            context: Additional context

        Yields:
            StreamChunk from the model
        """
        context = context or {}
        correlation_id = context.get("correlation_id", str(uuid.uuid4())[:12])
        start_time = time.perf_counter()

        # Apply privacy filter
        filtered_request = self._privacy_filter.filter_request(request)
        filtered_request.stream = True

        # Determine required capabilities
        required_capabilities = self._infer_capabilities(filtered_request)

        # Select model
        provider_name, model_spec = await self.select_model(task_type, required_capabilities, context)

        if not filtered_request.model:
            filtered_request.model = model_spec.id

        # Emit request event
        await self._emit_event(
            EventTypes.MODEL_STREAM_CHUNK,
            {
                "event_type": "stream_request",
                "task_type": task_type.value,
                "provider": provider_name,
                "model": model_spec.id,
                "correlation_id": correlation_id,
            },
            source="model_router",
            correlation_id=correlation_id,
        )

        # Execute with fallback
        providers_tried: Set[str] = set()
        chunk_count = 0

        while True:
            provider = self._providers.get(provider_name)
            if not provider:
                break

            providers_tried.add(provider_name)

            try:
                # Check circuit breaker
                if self.config.circuit_breaker_enabled:
                    cb = self._circuit_breakers.get(provider_name)
                    if cb and not await cb.can_execute():
                        raise RuntimeError(f"Circuit breaker OPEN for {provider_name}")

                # Stream response
                async for chunk in provider.stream_complete(filtered_request):
                    chunk_count += 1
                    yield chunk

                # Record success
                if self.config.circuit_breaker_enabled:
                    cb = self._circuit_breakers.get(provider_name)
                    if cb:
                        await cb.record_success()

                # Update health
                self._update_provider_health(provider_name, True, time.perf_counter() - start_time)

                # Emit completion event
                await self._emit_event(
                    EventTypes.MODEL_RESPONSE,
                    {
                        "event_type": "stream_completed",
                        "task_type": task_type.value,
                        "provider": provider_name,
                        "model": model_spec.id,
                        "chunks": chunk_count,
                        "latency_ms": round((time.perf_counter() - start_time) * 1000, 2),
                        "correlation_id": correlation_id,
                    },
                    source="model_router",
                    correlation_id=correlation_id,
                )

                self._request_count += 1
                return

            except Exception as e:
                latency_ms = round((time.perf_counter() - start_time) * 1000, 2)

                # Record failure
                if self.config.circuit_breaker_enabled:
                    cb = self._circuit_breakers.get(provider_name)
                    if cb:
                        await cb.record_failure()

                # Update health
                self._update_provider_health(provider_name, False, latency_ms / 1000.0, str(e))

                # Emit error event
                await self._emit_event(
                    EventTypes.MODEL_ERROR,
                    {
                        "event_type": "stream_error",
                        "task_type": task_type.value,
                        "provider": provider_name,
                        "model": model_spec.id,
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "latency_ms": latency_ms,
                        "chunks_before_error": chunk_count,
                        "correlation_id": correlation_id,
                    },
                    source="model_router",
                    correlation_id=correlation_id,
                )

                log_structured(logger, logging.WARNING, "Stream provider failed, trying fallback",
                    provider=provider_name, error=str(e), correlation_id=correlation_id)

                # Try next fallback (for streaming, we may not want to switch mid-stream)
                # Only fallback if no chunks were emitted yet
                if chunk_count == 0:
                    provider_name = self._get_next_fallback(provider_name, providers_tried, task_type, required_capabilities)
                    if not provider_name:
                        break

                    rule = self._get_routing_rule(task_type, required_capabilities)
                    fallback_result = self._select_from_provider(provider_name, required_capabilities, rule)
                    if fallback_result:
                        provider_name, model_spec = fallback_result
                        if not filtered_request.model:
                            filtered_request.model = model_spec.id
                    else:
                        break
                else:
                    # Already sent chunks, can't switch providers
                    break

        # All providers failed
        self._error_count += 1
        await self._emit_event(
            EventTypes.MODEL_ERROR,
            {
                "event_type": "stream_failed_all",
                "task_type": task_type.value,
                "providers_tried": list(providers_tried),
                "correlation_id": correlation_id,
            },
            source="model_router",
            correlation_id=correlation_id,
            priority=EventPriority.HIGH,
        )

        raise RuntimeError(f"All providers failed for streaming task {task_type.value}")

    async def embeddings(
        self,
        texts: List[str],
        task_type: Optional[TaskType] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> List[List[float]]:
        """
        Generate embeddings for a list of texts.

        Args:
            texts: List of text strings to embed
            task_type: Optional task type for routing
            context: Additional context

        Returns:
            List of embedding vectors
        """
        context = context or {}
        correlation_id = context.get("correlation_id", str(uuid.uuid4())[:12])
        start_time = time.perf_counter()

        task_type = task_type or TaskType.EMBEDDING
        required_capabilities = [ModelCapability.EMBEDDINGS]

        # Select model
        provider_name, model_spec = await self.select_model(task_type, required_capabilities, context)

        provider = self._providers.get(provider_name)
        if not provider:
            raise ValueError(f"Provider {provider_name} not available")

        try:
            embeddings = await provider.embeddings(texts, model_spec.id)

            # Update health
            self._update_provider_health(provider_name, True, time.perf_counter() - start_time)

            # Emit event
            await self._emit_event(
                EventTypes.MODEL_RESPONSE,
                {
                    "event_type": "embeddings_success",
                    "provider": provider_name,
                    "model": model_spec.id,
                    "text_count": len(texts),
                    "embedding_dim": len(embeddings[0]) if embeddings else 0,
                    "latency_ms": round((time.perf_counter() - start_time) * 1000, 2),
                    "correlation_id": correlation_id,
                },
                source="model_router",
                correlation_id=correlation_id,
            )

            return embeddings

        except Exception as e:
            self._update_provider_health(provider_name, False, time.perf_counter() - start_time, str(e))

            await self._emit_event(
                EventTypes.MODEL_ERROR,
                {
                    "event_type": "embeddings_error",
                    "provider": provider_name,
                    "model": model_spec.id,
                    "error": str(e),
                    "correlation_id": correlation_id,
                },
                source="model_router",
                correlation_id=correlation_id,
            )

            raise

    # =========================================================================
    # Health Checks
    # =========================================================================

    async def health_check_all(self) -> Dict[str, ProviderHealth]:
        """Check health of all registered providers."""
        results = {}

        for name, provider in self._providers.items():
            try:
                start = time.perf_counter()
                healthy = await provider.health_check()
                latency_ms = (time.perf_counter() - start) * 1000

                self._provider_health[name] = ProviderHealth(
                    name=name,
                    healthy=healthy,
                    latency_ms=latency_ms if healthy else None,
                    error=None if healthy else "Health check failed",
                    last_check=datetime.now(timezone.utc),
                    consecutive_failures=0 if healthy else self._provider_health.get(name, ProviderHealth(name=name, healthy=True)).consecutive_failures + 1,
                    consecutive_successes=self._provider_health.get(name, ProviderHealth(name=name, healthy=True)).consecutive_successes + 1 if healthy else 0,
                )
                results[name] = self._provider_health[name]

            except Exception as e:
                self._provider_health[name] = ProviderHealth(
                    name=name,
                    healthy=False,
                    error=str(e),
                    last_check=datetime.now(timezone.utc),
                    consecutive_failures=self._provider_health.get(name, ProviderHealth(name=name, healthy=True)).consecutive_failures + 1,
                    consecutive_successes=0,
                )
                results[name] = self._provider_health[name]

        return results

    async def _health_check_loop(self) -> None:
        """Background health check loop."""
        while self._running:
            try:
                await asyncio.sleep(self.config.health_check_interval_seconds)

                if not self._running:
                    break

                await self.health_check_all()

            except asyncio.CancelledError:
                break
            except Exception as e:
                log_structured(logger, logging.ERROR, "Health check loop error", error=str(e))

    def _update_provider_health(
        self,
        provider_name: str,
        healthy: bool,
        latency: float,
        error: Optional[str] = None,
    ) -> None:
        """Update provider health status."""
        current = self._provider_health.get(provider_name)
        if current:
            current.healthy = healthy
            current.latency_ms = latency * 1000 if healthy else current.latency_ms
            current.error = error
            current.last_check = datetime.now(timezone.utc)
            if healthy:
                current.consecutive_successes += 1
                current.consecutive_failures = 0
            else:
                current.consecutive_failures += 1
                current.consecutive_successes = 0
        else:
            self._provider_health[provider_name] = ProviderHealth(
                name=provider_name,
                healthy=healthy,
                latency_ms=latency * 1000 if healthy else None,
                error=error,
                consecutive_failures=0 if healthy else 1,
                consecutive_successes=1 if healthy else 0,
            )

    # =========================================================================
    # Usage Statistics
    # =========================================================================

    def get_usage_stats(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> UsageStats:
        """Get aggregated usage statistics."""
        return self._cost_tracker.get_stats(start_date, end_date)

    def _track_cost(
        self,
        provider: str,
        model: str,
        task_type: TaskType,
        usage: Dict[str, int],
        latency_seconds: float,
    ) -> None:
        """Track cost for a request."""
        self._cost_tracker.record(
            provider=provider,
            model=model,
            task_type=task_type,
            usage_dict=usage,
            latency_ms=round(latency_seconds * 1000),
        )

    # =========================================================================
    # Helpers
    # =========================================================================

    def _infer_capabilities(self, request: CompletionRequest) -> List[ModelCapability]:
        """Infer required capabilities from request."""
        capabilities = [ModelCapability.CHAT]

        if request.tools:
            capabilities.append(ModelCapability.TOOL_CALLING)

        if request.stream:
            capabilities.append(ModelCapability.STREAMING)

        # Check for vision content in messages
        for msg in request.messages:
            if isinstance(msg.content, list):
                for item in msg.content:
                    if isinstance(item, dict) and item.get("type") == "image":
                        capabilities.append(ModelCapability.VISION)
                        break

        return capabilities

    def _get_next_fallback(
        self,
        current_provider: str,
        tried: Set[str],
        task_type: TaskType,
        required_capabilities: List[ModelCapability],
    ) -> Optional[str]:
        """Get next fallback provider."""
        rule = self._get_routing_rule(task_type, required_capabilities)

        # Check rule fallbacks
        for p in rule.fallback_providers:
            if p not in tried and p in self._providers:
                return p

        # Check global fallback chain
        for p in self.config.fallback_chain:
            if p not in tried and p in self._providers:
                return p

        # Any other available provider
        for p in self._providers:
            if p not in tried:
                return p

        return None

    async def _emit_event(
        self,
        event_type: str,
        payload: Dict[str, Any],
        source: str = "model_router",
        correlation_id: Optional[str] = None,
        priority: EventPriority = EventPriority.NORMAL,
    ) -> None:
        """Emit an event to the event bus."""
        if not self._event_bus:
            return

        try:
            event = Event(
                type=event_type,
                payload=payload,
                source=source,
                correlation_id=correlation_id or str(uuid.uuid4())[:12],
                priority=priority,
            )
            await self._event_bus.publish(event)
        except Exception as e:
            log_structured(logger, logging.DEBUG, "Failed to emit event", error=str(e))

    def get_provider_status(self) -> Dict[str, Any]:
        """Get status of all providers."""
        return {
            name: {
                "healthy": health.healthy,
                "latency_ms": health.latency_ms,
                "error": health.error,
                "last_check": health.last_check.isoformat(),
                "consecutive_failures": health.consecutive_failures,
                "consecutive_successes": health.consecutive_successes,
                "circuit_breaker": self._circuit_breakers.get(name, CircuitBreaker(name)).get_status()
                if self.config.circuit_breaker_enabled else None,
            }
            for name, health in self._provider_health.items()
        }

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def providers(self) -> List[str]:
        return list(self._providers.keys())


# Global model router instance
_model_router: Optional[ModelRouter] = None


async def get_model_router() -> Optional[ModelRouter]:
    """Get the global model router instance."""
    return _model_router


async def init_model_router(
    config: Optional[ModelRouterConfig] = None,
    cost_tracker: Optional[CostTracker] = None,
    privacy_filter: Optional[PrivacyFilter] = None,
) -> ModelRouter:
    """Initialize the global model router."""
    global _model_router

    if config is None:
        app_config = load_config()
        config = ModelRouterConfig.from_config(app_config.model_router)

    _model_router = ModelRouter(config, cost_tracker, privacy_filter)
    await _model_router.initialize()
    return _model_router


async def shutdown_model_router() -> None:
    """Shutdown the global model router."""
    global _model_router
    if _model_router:
        await _model_router.shutdown()
        _model_router = None