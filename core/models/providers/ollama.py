"""
Ollama provider implementation for ARISE model routing.

Provides local model inference via Ollama for privacy-sensitive workloads.
"""

import httpx
from typing import Any, AsyncGenerator, Dict, List, Optional

from core.models.models import (
    ModelSpec,
    ModelCapability,
    CompletionRequest,
    CompletionResponse,
    Message,
    LatencyTier,
)
from core.models.providers.base import ModelProvider


class OllamaProvider(ModelProvider):
    """Ollama local model provider."""

    name = "ollama"

    def __init__(self, config: Dict[str, Any]):
        self.base_url = config.get("base_url", "http://localhost:11434")
        self.timeout = config.get("timeout", 120)
        self._client: Optional[httpx.AsyncClient] = None
        self._models_cache: List[ModelSpec] = []

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
            )
        return self._client

    async def list_models(self) -> List[ModelSpec]:
        """List available Ollama models."""
        if not self._models_cache:
            try:
                client = await self._get_client()
                response = await client.get("/api/tags")
                response.raise_for_status()
                data = response.json()

                for model_info in data.get("models", []):
                    model_name = model_info.get("name", "")
                    # Parse model capabilities based on name
                    capabilities = self._infer_capabilities(model_name)

                    self._models_cache.append(ModelSpec(
                        id=model_name,
                        name=model_name,
                        provider="ollama",
                        capabilities=capabilities,
                        context_window=self._get_context_window(model_name),
                        max_output_tokens=self._get_max_output_tokens(model_name),
                        pricing={"input": 0.0, "output": 0.0, "cached_input": 0.0},
                        latency_tier=LatencyTier.BALANCED,
                        supports_streaming=True,
                    ))
            except Exception:
                # Return defaults if API fails
                pass

        # Add default models if cache is still empty
        if not self._models_cache:
            self._models_cache = self._get_default_models()

        return self._models_cache

    def _infer_capabilities(self, model_name: str) -> List[ModelCapability]:
        """Infer capabilities from model name."""
        name_lower = model_name.lower()
        capabilities = [ModelCapability.CHAT, ModelCapability.STREAMING]

        if any(x in name_lower for x in ["llama3", "llama-3", "nemotron", "command-r"]):
            capabilities.append(ModelCapability.TOOL_CALLING)
        if any(x in name_lower for x in ["vision", "llava", "bakllava", "moondream"]):
            capabilities.append(ModelCapability.VISION)
        if any(x in name_lower for x in ["code", "coder", "starcoder", "deepseek-coder"]):
            capabilities.append(ModelCapability.TOOL_CALLING)
            capabilities.append(ModelCapability.REASONING)

        return capabilities

    def _get_context_window(self, model_name: str) -> int:
        """Get context window for model."""
        name_lower = model_name.lower()
        if "llama3.1" in name_lower or "llama-3.1" in name_lower:
            return 128000
        elif "llama3" in name_lower or "llama-3" in name_lower:
            return 8192
        elif "nemotron" in name_lower:
            return 128000
        elif "command-r" in name_lower:
            return 128000
        return 4096

    def _get_max_output_tokens(self, model_name: str) -> int:
        """Get max output tokens for model."""
        name_lower = model_name.lower()
        if "llama3.1" in name_lower or "llama-3.1" in name_lower:
            return 4096
        elif "nemotron" in name_lower:
            return 4096
        return 2048

    def _get_default_models(self) -> List[ModelSpec]:
        """Get default model specs when API is unavailable."""
        return [
            ModelSpec(
                id="llama3.1",
                name="Llama 3.1",
                provider="ollama",
                capabilities=[
                    ModelCapability.CHAT,
                    ModelCapability.TOOL_CALLING,
                    ModelCapability.REASONING,
                    ModelCapability.STREAMING,
                ],
                context_window=128000,
                max_output_tokens=4096,
                pricing={"input": 0.0, "output": 0.0, "cached_input": 0.0},
                latency_tier=LatencyTier.BALANCED,
            ),
            ModelSpec(
                id="llama3.2",
                name="Llama 3.2",
                provider="ollama",
                capabilities=[
                    ModelCapability.CHAT,
                    ModelCapability.STREAMING,
                ],
                context_window=128000,
                max_output_tokens=4096,
                pricing={"input": 0.0, "output": 0.0, "cached_input": 0.0},
                latency_tier=LatencyTier.FAST,
            ),
            ModelSpec(
                id="nemotron3-ultra",
                name="Nemotron 3 Ultra",
                provider="ollama",
                capabilities=[
                    ModelCapability.CHAT,
                    ModelCapability.TOOL_CALLING,
                    ModelCapability.REASONING,
                    ModelCapability.STREAMING,
                ],
                context_window=128000,
                max_output_tokens=4096,
                pricing={"input": 0.0, "output": 0.0, "cached_input": 0.0},
                latency_tier=LatencyTier.QUALITY,
            ),
            ModelSpec(
                id="llava",
                name="LLaVA",
                provider="ollama",
                capabilities=[
                    ModelCapability.CHAT,
                    ModelCapability.VISION,
                    ModelCapability.STREAMING,
                ],
                context_window=4096,
                max_output_tokens=2048,
                pricing={"input": 0.0, "output": 0.0, "cached_input": 0.0},
                latency_tier=LatencyTier.BALANCED,
            ),
        ]

    def _convert_messages(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """Convert ARISE messages to Ollama format."""
        ollama_messages = []
        for msg in messages:
            ollama_messages.append({
                "role": msg.role,
                "content": msg.content,
            })
        return ollama_messages

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        model_id = request.model or "llama3.1"
        messages = self._convert_messages(request.messages)

        client = await self._get_client()

        payload = {
            "model": model_id,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": request.temperature,
            },
        }

        if request.max_tokens:
            payload["options"]["num_predict"] = request.max_tokens

        if request.tools:
            payload["tools"] = request.tools

        response = await client.post("/api/chat", json=payload)
        response.raise_for_status()
        data = response.json()

        message = data.get("message", {})
        content = message.get("content", "")

        # Extract tool calls
        tool_calls = None
        if "tool_calls" in message:
            tool_calls = []
            for tc in message["tool_calls"]:
                tool_calls.append({
                    "id": tc.get("id", ""),
                    "name": tc.get("function", {}).get("name", ""),
                    "arguments": tc.get("function", {}).get("arguments", {}),
                })

        # Usage info (Ollama provides this in newer versions)
        usage = {
            "prompt_tokens": data.get("prompt_eval_count", 0),
            "completion_tokens": data.get("eval_count", 0),
            "total_tokens": data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
        }

        return CompletionResponse(
            content=content,
            model=model_id,
            usage=usage,
            finish_reason=data.get("done_reason", "stop"),
            tool_calls=tool_calls,
        )

    async def stream_complete(self, request: CompletionRequest) -> AsyncGenerator[str, None]:
        model_id = request.model or "llama3.1"
        messages = self._convert_messages(request.messages)

        client = await self._get_client()

        payload = {
            "model": model_id,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": request.temperature,
            },
        }

        if request.max_tokens:
            payload["options"]["num_predict"] = request.max_tokens

        if request.tools:
            payload["tools"] = request.tools

        async with client.stream("POST", "/api/chat", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                import json
                try:
                    data = json.loads(line)
                    if "message" in data and "content" in data["message"]:
                        yield data["message"]["content"]
                    if data.get("done", False):
                        break
                except json.JSONDecodeError:
                    continue

    async def embeddings(self, texts: List[str], model: str) -> List[List[float]]:
        """Generate embeddings using Ollama."""
        client = await self._get_client()

        # Use a dedicated embedding model if specified, otherwise use the chat model
        embed_model = model if "embed" in model.lower() else "nomic-embed-text"

        embeddings = []
        for text in texts:
            payload = {
                "model": embed_model,
                "prompt": text,
            }
            response = await client.post("/api/embeddings", json=payload)
            response.raise_for_status()
            data = response.json()
            embeddings.append(data.get("embedding", []))

        return embeddings

    async def health_check(self) -> bool:
        """Check if Ollama is running and accessible."""
        try:
            client = await self._get_client()
            response = await client.get("/api/tags")
            return response.status_code == 200
        except Exception:
            return False

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None