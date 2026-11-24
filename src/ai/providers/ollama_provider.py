"""Proveedor LLM: Ollama (local o remoto)."""

import os
import time
from .base import LLMProvider


class OllamaProvider(LLMProvider):
    """Proveedor que usa Ollama (local o servidor remoto)."""

    def __init__(
        self,
        host: str | None = None,
        model: str = "qwen3:8b",
        timeout: int = 180,
        reintentos: int = 2,
    ):
        self.host = host or os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self._modelo = model
        self.timeout = timeout
        self.reintentos = reintentos

        try:
            import ollama
        except ImportError:
            raise ImportError(
                "ollama no instalado. "
                "Ejecuta: pip install ollama>=0.6.3"
            )

        self.ollama = ollama

    @property
    def nombre(self) -> str:
        return "ollama"

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
        """Envía request a Ollama con reintentos."""
        cliente = self.ollama.Client(host=self.host, timeout=self.timeout)
        ultimo_error = None

        for intento in range(self.reintentos + 1):
            try:
                response = cliente.chat(
                    model=self._modelo,
                    messages=messages,
                    **kwargs,
                )
                return response

            except self.ollama.ResponseError as error:
                ultimo_error = error
                if 400 <= getattr(error, "status_code", 0) < 500:
                    break

            except (ConnectionError, TimeoutError, OSError) as error:
                ultimo_error = error

            except Exception as error:
                ultimo_error = error

            if intento < self.reintentos:
                time.sleep(2)

        raise RuntimeError(
            f"No se pudo conectar a Ollama ({self.host}, modelo '{self._modelo}'): "
            f"{ultimo_error}"
        ) from ultimo_error
