"""
Base Provider Classes for Model Providers.

Defines the abstract base class for model providers and a registry pattern
for managing multiple providers.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Dict, List, Optional

from core.models.models import CompletionRequest, CompletionResponse, ModelSpec


class ModelProvider(ABC):
    """
    Abstract base class for model providers.

    All provider implementations must inherit from this class and implement
    the required abstract methods.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the provider's unique name (e.g., 'anthropic', 'openai', 'google')."""
        pass

    @abstractmethod
    async def list_models(self) -> List[ModelSpec]:
        """
        List all available models from this provider.

        Returns:
            List of ModelSpec objects describing available models.
        """
        pass

    @abstractmethod
    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        """
        Perform a non-streaming completion request.

        Args:
            request: The completion request with messages and parameters.

        Returns:
            CompletionResponse with the model's response.
        """
        pass

    @abstractmethod
    async def stream_complete(
        self, request: CompletionRequest
    ) -> AsyncGenerator[str, None]:
        """
        Perform a streaming completion request.

        Args:
            request: The completion request with stream=True.

        Yields:
            String chunks of the response as they arrive.
        """
        pass

    @abstractmethod
    async def embeddings(
        self, texts: List[str], model: str
    ) -> List[List[float]]:
        """
        Generate embeddings for a list of texts.

        Args:
            texts: List of text strings to embed.
            model: The embedding model to use.

        Returns:
            List of embedding vectors (list of floats for each text).
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if the provider is healthy and available.

        Returns:
            True if the provider is healthy, False otherwise.
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """
        Close any open connections and clean up resources.

        Should be called when the provider is no longer needed.
        """
        pass


class ProviderRegistry:
    """
    Registry for managing model providers.

    Follows the registry pattern from core/task_engine/kinds/__init__.py
    for consistent provider management.
    """

    def __init__(self):
        self._providers: Dict[str, ModelProvider] = {}

    def register(self, provider: ModelProvider) -> None:
        """
        Register a provider in the registry.

        Args:
            provider: The ModelProvider instance to register.

        Raises:
            ValueError: If a provider with the same name is already registered.
        """
        if provider.name in self._providers:
            raise ValueError(f"Provider '{provider.name}' is already registered")
        self._providers[provider.name] = provider

    def get(self, name: str) -> ModelProvider:
        """
        Get a provider by name.

        Args:
            name: The provider's name.

        Returns:
            The registered ModelProvider instance.

        Raises:
            KeyError: If no provider with the given name is registered.
        """
        if name not in self._providers:
            raise KeyError(f"Provider '{name}' not found in registry")
        return self._providers[name]

    def list(self) -> List[ModelProvider]:
        """
        List all registered providers.

        Returns:
            List of all registered ModelProvider instances.
        """
        return list(self._providers.values())

    async def health_check_all(self) -> Dict[str, bool]:
        """
        Check health of all registered providers.

        Returns:
            Dictionary mapping provider names to their health status.
        """
        results: Dict[str, bool] = {}
        for name, provider in self._providers.items():
            try:
                results[name] = await provider.health_check()
            except Exception:
                results[name] = False
        return results

    def unregister(self, name: str) -> None:
        """
        Unregister a provider by name.

        Args:
            name: The provider's name to remove.

        Raises:
            KeyError: If no provider with the given name is registered.
        """
        if name not in self._providers:
            raise KeyError(f"Provider '{name}' not found in registry")
        del self._providers[name]

    def clear(self) -> None:
        """Remove all providers from the registry."""
        self._providers.clear()

    def __contains__(self, name: str) -> bool:
        """Check if a provider is registered."""
        return name in self._providers

    def __len__(self) -> int:
        """Return the number of registered providers."""
        return len(self._providers)


# Global provider registry instance
provider_registry = ProviderRegistry()