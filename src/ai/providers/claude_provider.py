"""Proveedor LLM: Claude (API de Anthropic)."""

import os
from .base import LLMProvider, LLMProviderError

MODELO_POR_DEFECTO = "claude-opus-5-5"


class ClaudeProvider(LLMProvider):
    """Proveedor que usa la API de Anthropic (https://console.anthropic.com)."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = 120.0,
    ):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self._modelo = model or os.getenv("LLM_CLAUDE_MODEL", MODELO_POR_DEFECTO)

        if not self.api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY no configurada. "
                "Genera una clave en https://console.anthropic.com/settings/keys "
                "y settea ANTHROPIC_API_KEY en .env"
            )

        try:
            import anthropic
        except ImportError:
            raise ImportError(
                "anthropic no instalado. "
                "Ejecuta: pip install anthropic"
            )

        self.anthropic = anthropic
        self.client = anthropic.Anthropic(api_key=self.api_key, timeout=timeout)

    @property
    def nombre(self) -> str:
        return "claude"

    @property
    def modelo(self) -> str:
        return self._modelo

    def chat(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs,
    ) -> dict:
        """Envía la conversación a Claude.

        `temperature` y los kwargs propios de otros proveedores (p. ej.
        `format` de Ollama) se ignoran: los modelos Claude 5 rechazan
        `temperature` con un error 400.
        """
        sistema = "\n\n".join(
            m["content"] for m in messages if m["role"] == "system"
        )
        conversacion = [m for m in messages if m["role"] != "system"]

        argumentos = {
            "model": self._modelo,
            "max_tokens": max_tokens or 16000,
            "messages": conversacion,
            # La extracción de JSON no necesita razonamiento largo.
            "output_config": {"effort": "low"},
        }
        if sistema:
            argumentos["system"] = sistema

        try:
            respuesta = self.client.messages.create(**argumentos)

        except self.anthropic.AuthenticationError as error:
            raise LLMProviderError(
                "Clave de Anthropic inválida. Revisa ANTHROPIC_API_KEY en .env."
            ) from error
        except self.anthropic.RateLimitError as error:
            raise LLMProviderError(
                "Anthropic: límite de peticiones alcanzado. "
                "Espera un momento e inténtalo de nuevo."
            ) from error
        except self.anthropic.APIConnectionError as error:
            raise LLMProviderError(
                "No se pudo conectar con la API de Anthropic. "
                "Revisa tu conexión a internet."
            ) from error
        except self.anthropic.APIStatusError as error:
            raise LLMProviderError(
                f"Error en la API de Anthropic ({error.status_code}): {error.message}"
            ) from error

        if respuesta.stop_reason == "refusal":
            raise LLMProviderError(
                "Claude rechazó la solicitud por sus políticas de seguridad. "
                "Reformula la descripción del proyecto."
            )

        texto = "".join(b.text for b in respuesta.content if b.type == "text")

        return {"message": {"content": texto, "role": "assistant"}}
