"""
Gemini provider implementation for ARISE model routing.
"""

import google.generativeai as genai
from typing import Any, Dict, List, Optional
from core.models.providers.base import ModelProvider
from core.models.models import (
    ModelSpec,
    ModelCapability,
    CompletionRequest,
    CompletionResponse,
    Message,
    LatencyTier,
)


class GeminiProvider(ModelProvider):
    """Gemini model provider."""

    name = "gemini"

    def __init__(self, api_key: str, config: Dict[str, Any]):
        genai.configure(api_key=api_key)
        self.config = config
        self._models_cache: List[ModelSpec] = []

    async def list_models(self) -> List[ModelSpec]:
        if not self._models_cache:
            # Static model specs for known models (API doesn't list all)
            self._models_cache = [
                ModelSpec(
                    id="gemini-3.8-live",
                    name="Gemini 3.8 Live",
                    provider="gemini",
                    capabilities=[
                        ModelCapability.REALTIME_AUDIO,
                        ModelCapability.TOOL_CALLING,
                        ModelCapability.REASONING,
                    ],
                    context_window=131072,
                    max_output_tokens=65536,
                    pricing={"input_audio": 0.005, "output_audio": 0.018},  # per minute
                    latency_tier=LatencyTier.FAST,
                ),
                ModelSpec(
                    id="gemini-3.8-live-extended-thinking",
                    name="Gemini 3.8 Live Extended Thinking",
                    provider="gemini",
                    capabilities=[
                        ModelCapability.REALTIME_AUDIO,
                        ModelCapability.TOOL_CALLING,
                        ModelCapability.REASONING,
                    ],
                    context_window=131072,
                    max_output_tokens=65536,
                    pricing={"input_audio": 0.005, "output_audio": 0.018},
                    latency_tier=LatencyTier.BALANCED,
                ),
                ModelSpec(
                    id="gemini-2.5-pro",
                    name="Gemini 2.5 Pro",
                    provider="gemini",
                    capabilities=[
                        ModelCapability.CHAT,
                        ModelCapability.VISION,
                        ModelCapability.TOOL_CALLING,
                        ModelCapability.REASONING,
                    ],
                    context_window=2000000,
                    max_output_tokens=8192,
                    pricing={"input": 1.25, "output": 5.00},  # per 1M tokens
                    latency_tier=LatencyTier.QUALITY,
                ),
                ModelSpec(
                    id="gemini-2.5-flash",
                    name="Gemini 2.5 Flash",
                    provider="gemini",
                    capabilities=[
                        ModelCapability.CHAT,
                        ModelCapability.VISION,
                        ModelCapability.TOOL_CALLING,
                    ],
                    context_window=1000000,
                    max_output_tokens=8192,
                    pricing={"input": 0.075, "output": 0.30},
                    latency_tier=LatencyTier.FAST,
                ),
            ]
        return self._models_cache

    def _convert_messages(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """Convert ARISE messages to Gemini format."""
        contents = []
        for msg in messages:
            if msg.role == "system":
                # Gemini doesn't have system role, prepend to first user message
                continue
            role = "user" if msg.role == "user" else "model"
            contents.append({"role": role, "parts": [{"text": msg.content}]})
        return contents

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        model = genai.GenerativeModel(request.model or "gemini-2.5-flash")
        # Convert messages to Gemini format
        contents = self._convert_messages(request.messages)

        # Build generation config using dict (older API)
        generation_config = {
            "temperature": request.temperature,
        }
        if request.max_tokens:
            generation_config["max_output_tokens"] = request.max_tokens

        response = await model.generate_content_async(
            contents,
            generation_config=generation_config,
            tools=request.tools,
        )
        return CompletionResponse(
            content=response.text,
            model=request.model or "gemini-2.5-flash",
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},  # TODO: extract usage
            finish_reason="stop",
        )

    async def stream_complete(self, request: CompletionRequest):
        model = genai.GenerativeModel(request.model or "gemini-2.5-flash")
        contents = self._convert_messages(request.messages)

        generation_config = {"temperature": request.temperature}

        response = await model.generate_content_async(
            contents,
            generation_config=generation_config,
            stream=True,
        )
        async for chunk in response:
            if chunk.text:
                yield chunk.text

    async def embeddings(self, texts: List[str], model: str) -> List[List[float]]:
        result = await genai.embed_content_async(
            model=model or "text-embedding-004",
            content=texts,
        )
        return result["embedding"]

    async def health_check(self) -> bool:
        try:
            await self.embeddings(["health check"], "text-embedding-004")
            return True
        except Exception:
            return False

    async def close(self):
        # No-op for genai
        pass