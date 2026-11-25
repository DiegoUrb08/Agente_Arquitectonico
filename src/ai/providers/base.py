"""Base class para proveedores LLM."""

from abc import ABC, abstractmethod
from typing import Any


class LLMProviderError(RuntimeError):
    """Fallo esperable al consultar un proveedor (red, cuota, clave, rechazo).

    El mensaje está pensado para mostrarse tal cual al usuario.
    """


class LLMProvider(ABC):
    """Interfaz de un proveedor LLM."""

    @property
    @abstractmethod
    def nombre(self) -> str:
        """Nombre del proveedor (ej: 'groq', 'ollama', 'claude')."""
        pass

    @property
    @abstractmethod
    def modelo(self) -> str:
        """Modelo en uso (ej: 'mixtral-8x7b-32768', 'qwen3:8b')."""
        pass

    @abstractmethod
    def chat(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs,
    ) -> dict:
        """
        Envía un mensaje y devuelve la respuesta.

        Devuelve dict con al menos:
            {
                "message": {
                    "content": "respuesta del modelo",
                    "role": "assistant"
                }
            }
        """
        pass
