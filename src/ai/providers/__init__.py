"""Proveedores LLM: abstracción para múltiples backends."""

import os
from .base import LLMProvider, LLMProviderError
from .claude_provider import ClaudeProvider
from .groq_provider import GroqProvider
from .ollama_provider import OllamaProvider
from .mock_provider import MockProvider
from .proxy_provider import ProxyProvider


def get_provider(provider_name: str | None = None) -> LLMProvider:
    """
    Factory que devuelve el proveedor LLM configurado.

    Lee LLM_PROVIDER del ambiente si no se pasa explícitamente.
    Default: 'groq'.
    """
    provider_name = provider_name or os.getenv("LLM_PROVIDER", "groq").lower()

    if provider_name == "groq":
        return GroqProvider()
    elif provider_name == "ollama":
        return OllamaProvider()
    elif provider_name == "proxy":
        return ProxyProvider()
    elif provider_name == "claude":
        return ClaudeProvider()
    elif provider_name == "mock":
        return MockProvider()
    else:
        raise ValueError(
            f"Proveedor LLM desconocido: {provider_name}. "
            f"Opciones: groq, ollama, proxy, claude, mock"
        )


__all__ = [
    "LLMProvider", "LLMProviderError", "ClaudeProvider", "GroqProvider",
    "OllamaProvider", "ProxyProvider", "MockProvider", "get_provider",
]
