"""
Anthropic provider implementation for ARISE model routing.
"""

from typing import Any, AsyncGenerator, Dict, List

from anthropic import AsyncAnthropic

from core.models.models import (
    ModelSpec,
    ModelCapability,
    CompletionRequest,
    CompletionResponse,
    Message,
    LatencyTier,
)
from core.models.providers.base import ModelProvider


class AnthropicProvider(ModelProvider):
    """Anthropic model provider."""

    name = "anthropic"

    def __init__(self, api_key: str, config: Dict[str, Any]):
        self.client = AsyncAnthropic(api_key=api_key)
        self.config = config
        self._models_cache: List[ModelSpec] = []

    async def list_models(self) -> List[ModelSpec]:
        if not self._models_cache:
            # Static model specs for known Anthropic models
            self._models_cache = [
                ModelSpec(
                    id="claude-4-opus-20250514",
                    name="Claude 4 Opus",
                    provider="anthropic",
                    capabilities=[
                        ModelCapability.CHAT,
                        ModelCapability.VISION,
                        ModelCapability.TOOL_CALLING,
                        ModelCapability.REASONING,
                    ],
                    context_window=200000,
                    max_output_tokens=32768,
                    pricing={"input": 15.00, "output": 75.00, "cached_input": 1.50},  # per 1M tokens
                    latency_tier=LatencyTier.QUALITY,
                ),
                ModelSpec(
                    id="claude-4-sonnet-20250514",
                    name="Claude 4 Sonnet",
                    provider="anthropic",
                    capabilities=[
                        ModelCapability.CHAT,
                        ModelCapability.VISION,
                        ModelCapability.TOOL_CALLING,
                        ModelCapability.REASONING,
                    ],
                    context_window=200000,
                    max_output_tokens=32768,
                    pricing={"input": 3.00, "output": 15.00, "cached_input": 0.30},  # per 1M tokens
                    latency_tier=LatencyTier.BALANCED,
                ),
                ModelSpec(
                    id="claude-3-5-sonnet-20241022",
                    name="Claude 3.5 Sonnet",
                    provider="anthropic",
                    capabilities=[
                        ModelCapability.CHAT,
                        ModelCapability.VISION,
                        ModelCapability.TOOL_CALLING,
                        ModelCapability.REASONING,
                    ],
                    context_window=200000,
                    max_output_tokens=8192,
                    pricing={"input": 3.00, "output": 15.00, "cached_input": 0.30},  # per 1M tokens
                    latency_tier=LatencyTier.BALANCED,
                ),
                ModelSpec(
                    id="claude-3-5-haiku-20241022",
                    name="Claude 3.5 Haiku",
                    provider="anthropic",
                    capabilities=[
                        ModelCapability.CHAT,
                        ModelCapability.VISION,
                        ModelCapability.TOOL_CALLING,
                    ],
                    context_window=200000,
                    max_output_tokens=8192,
                    pricing={"input": 0.80, "output": 4.00, "cached_input": 0.08},  # per 1M tokens
                    latency_tier=LatencyTier.FAST,
                ),
            ]
        return self._models_cache

    def _convert_messages(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """Convert ARISE messages to Anthropic format."""
        anthropic_messages = []
        system_prompt = None

        for msg in messages:
            if msg.role == "system":
                system_prompt = msg.content
            elif msg.role == "user":
                anthropic_messages.append({"role": "user", "content": msg.content})
            elif msg.role == "assistant":
                anthropic_messages.append({"role": "assistant", "content": msg.content})
            elif msg.role == "tool":
                # Tool results are handled via tool_use/tool_result in Anthropic
                # This would need more complex handling for tool calls
                pass

        return anthropic_messages, system_prompt

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        model_id = request.model or "claude-3-5-sonnet-20241022"
        messages, system_prompt = self._convert_messages(request.messages)

        # Build the request parameters
        params = {
            "model": model_id,
            "messages": messages,
            "max_tokens": request.max_tokens or 4096,
            "temperature": request.temperature,
            "stream": False,
        }

        if system_prompt:
            params["system"] = system_prompt

        if request.tools:
            # Convert tools to Anthropic format
            params["tools"] = request.tools

        if request.tool_choice:
            params["tool_choice"] = request.tool_choice

        response = await self.client.messages.create(**params)

        # Extract usage
        usage = {
            "prompt_tokens": response.usage.input_tokens,
            "completion_tokens": response.usage.output_tokens,
            "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
        }

        # Extract tool calls if any
        tool_calls = None
        if response.content:
            for block in response.content:
                if block.type == "tool_use":
                    if tool_calls is None:
                        tool_calls = []
                    tool_calls.append({
                        "id": block.id,
                        "name": block.name,
                        "arguments": block.input,
                    })

        return CompletionResponse(
            content=response.content[0].text if response.content else "",
            model=model_id,
            usage=usage,
            finish_reason=response.stop_reason or "stop",
            tool_calls=tool_calls,
        )

    async def stream_complete(self, request: CompletionRequest) -> AsyncGenerator[str, None]:
        model_id = request.model or "claude-3-5-sonnet-20241022"
        messages, system_prompt = self._convert_messages(request.messages)

        params = {
            "model": model_id,
            "messages": messages,
            "max_tokens": request.max_tokens or 4096,
            "temperature": request.temperature,
            "stream": True,
        }

        if system_prompt:
            params["system"] = system_prompt

        if request.tools:
            params["tools"] = request.tools

        if request.tool_choice:
            params["tool_choice"] = request.tool_choice

        async with self.client.messages.stream(**params) as stream:
            async for text in stream.text_stream:
                yield text

    async def embeddings(self, texts: List[str], model: str) -> List[List[float]]:
        # Anthropic doesn't provide embeddings API
        # Raise NotImplementedError with a helpful message
        raise NotImplementedError(
            "Anthropic does not provide an embeddings API. "
            "Use OpenAI, Google, or other providers for embeddings."
        )

    async def health_check(self) -> bool:
        try:
            # Simple health check - try a minimal completion
            response = await self.client.messages.create(
                model="claude-3-5-haiku-20241022",
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=10,
            )
            return response is not None
        except Exception:
            return False

    async def close(self) -> None:
        await self.client.close()