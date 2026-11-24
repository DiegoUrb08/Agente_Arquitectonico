"""Proveedor LLM: Proxy (servidor demo de un operador, sin clave propia)."""

import os
from .base import LLMProvider


class ProxyProvider(LLMProvider):
    """
    Proveedor que habla con un servidor proxy (server/proxy_server.py)
    operado por un tercero que guarda su propia GROQ_API_KEY.

    Útil para probar el agente sin crear cuenta en Groq; sujeto al
    rate limit que imponga el operador del proxy.
    """

    def __init__(
        self,
        proxy_url: str | None = None,
        access_token: str | None = None,
        model: str = "openai/gpt-oss-20b",
        timeout: int = 60,
    ):
        self.proxy_url = (proxy_url or os.getenv("PROXY_URL", "")).rstrip("/")
        self.access_token = access_token or os.getenv("PROXY_ACCESS_TOKEN")
        self._modelo = model
        self.timeout = timeout

        if not self.proxy_url:
            raise ValueError(
                "PROXY_URL no configurada. "
                "Pide la URL del servidor demo al operador del proxy, "
                "o usa tu propia GROQ_API_KEY con LLM_PROVIDER=groq."
            )

        try:
            import requests
        except ImportError:
            raise ImportError(
                "requests no instalado. Ejecuta: pip install requests"
            )

        self.requests = requests

    @property
    def nombre(self) -> str:
        return "proxy"

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
        """Envía la petición al servidor proxy."""
        headers = {}
        if self.access_token:
            headers["X-Proxy-Token"] = self.access_token

        try:
            respuesta = self.requests.post(
                f"{self.proxy_url}/chat",
                json={
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens or 2048,
                    "model": self._modelo,
                },
                headers=headers,
                timeout=self.timeout,
            )

        except self.requests.exceptions.RequestException as error:
            raise RuntimeError(
                f"No se pudo conectar al servidor proxy ({self.proxy_url}): {error}"
            ) from error

        if respuesta.status_code == 429:
            detalle = respuesta.json().get("error", "Límite de uso alcanzado.")
            raise RuntimeError(f"Proxy: {detalle}")

        if respuesta.status_code != 200:
            detalle = respuesta.json().get("error", respuesta.text)
            raise RuntimeError(f"Error del servidor proxy ({respuesta.status_code}): {detalle}")

        datos = respuesta.json()
        return {"message": datos["message"]}
