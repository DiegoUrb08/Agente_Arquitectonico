"""Proveedor LLM: Groq API (gratis, sin tarjeta)."""

import os
from .base import LLMProvider, LLMProviderError


class GroqProvider(LLMProvider):
    """Proveedor que usa Groq API (https://console.groq.com)."""

    def __init__(self, api_key: str | None = None, model: str = "openai/gpt-oss-20b"):
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        self._modelo = model

        if not self.api_key:
            raise ValueError(
                "GROQ_API_KEY no configurada. "
                "Genera una gratis en https://console.groq.com (sin tarjeta) "
                "y settea GROQ_API_KEY en .env"
            )

        try:
            from groq import Groq
        except ImportError:
            raise ImportError(
                "groq no instalado. "
                "Ejecuta: pip install groq>=0.9"
            )

        self.client = Groq(api_key=self.api_key)

    @property
    def nombre(self) -> str:
        return "groq"

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
        """Envía request a Groq API."""
        try:
            response = self.client.chat.completions.create(
                model=self._modelo,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens or 2048,
                **kwargs,
            )

            return {
                "message": {
                    "content": response.choices[0].message.content,
                    "role": "assistant",
                }
            }

        except Exception as e:
            raise LLMProviderError(f"Error en Groq API: {e}") from e
