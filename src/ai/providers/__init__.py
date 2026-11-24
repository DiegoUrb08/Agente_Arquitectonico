"""Proveedores LLM: abstracción para múltiples backends."""

import os
from .base import LLMProvider
from .groq_provider import GroqProvider
from .ollama_provider import OllamaProvider
from .mock_provider import MockProvider


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
    elif provider_name == "mock":
        return MockProvider()
    else:
        raise ValueError(
            f"Proveedor LLM desconocido: {provider_name}. "
            f"Opciones: groq, ollama, mock"
        )


__all__ = ["LLMProvider", "GroqProvider", "OllamaProvider", "MockProvider", "get_provider"]
