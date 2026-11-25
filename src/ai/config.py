"""Gestión de configuración de proveedores LLM."""

import os
from typing import Optional


class LLMConfig:
    """Validación y gestión de configuración de proveedores LLM."""

    @staticmethod
    def validar_provider() -> tuple[str, dict]:
        """
        Valida que el proveedor LLM esté configurado correctamente.

        Devuelve: (nombre_provider, config_dict)
        Lanza: ValueError si falta configuración crítica.
        """
        provider_name = os.getenv("LLM_PROVIDER", "groq").lower()

        if provider_name == "groq":
            return LLMConfig._validar_groq()
        elif provider_name == "ollama":
            return LLMConfig._validar_ollama()
        elif provider_name == "proxy":
            return LLMConfig._validar_proxy()
        elif provider_name == "claude":
            return LLMConfig._validar_claude()
        elif provider_name == "mock":
            return "mock", {}
        else:
            raise ValueError(
                f"Proveedor LLM desconocido: {provider_name}. "
                f"Opciones: groq, ollama, proxy, claude, mock"
            )

    @staticmethod
    def _validar_groq() -> tuple[str, dict]:
        """Valida configuración de Groq."""
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError(
                "\n❌ GROQ_API_KEY no configurada.\n"
                "Para usar Groq (gratis, sin tarjeta):\n"
                "  1. Visita: https://console.groq.com/keys\n"
                "  2. Genera una clave (1 min, solo email)\n"
                "  3. Copia en .env: GROQ_API_KEY=gsk_...\n"
            )
        return "groq", {"api_key": api_key}

    @staticmethod
    def _validar_ollama() -> tuple[str, dict]:
        """Valida configuración de Ollama."""
        host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        # La validación real ocurre cuando OllamaProvider intenta conectar
        return "ollama", {"host": host}

    @staticmethod
    def _validar_proxy() -> tuple[str, dict]:
        """Valida configuración del proveedor proxy (servidor de un tercero)."""
        proxy_url = os.getenv("PROXY_URL")
        if not proxy_url:
            raise ValueError(
                "\n❌ PROXY_URL no configurada.\n"
                "Para usar el modo demo (sin clave propia):\n"
                "  1. Pide la URL del servidor demo al operador del proxy\n"
                "  2. Copia en .env: PROXY_URL=https://...\n"
                "  3. Si el operador exige token, agrega: PROXY_ACCESS_TOKEN=...\n"
                "\n"
                "Alternativa: usa tu propia clave con LLM_PROVIDER=groq\n"
                "(gratis, sin límites del operador): https://console.groq.com/keys\n"
            )
        return "proxy", {
            "proxy_url": proxy_url,
            "access_token": os.getenv("PROXY_ACCESS_TOKEN"),
        }

    @staticmethod
    def _validar_claude() -> tuple[str, dict]:
        """Valida configuración de Claude."""
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError(
                "\n❌ ANTHROPIC_API_KEY no configurada.\n"
                "Para usar Claude:\n"
                "  1. Visita: https://console.anthropic.com/settings/keys\n"
                "  2. Genera una clave\n"
                "  3. Copia en .env: ANTHROPIC_API_KEY=sk-ant-...\n"
            )
        return "claude", {"api_key": api_key}

    @staticmethod
    def mensaje_bienvenida() -> str:
        """Devuelve un mensaje de bienvenida con instrucciones."""
        provider = os.getenv("LLM_PROVIDER", "groq").lower()

        def banner(titulo: str, *lineas: str) -> str:
            return "\n".join([titulo, "━" * 40, *lineas]) + "\n"

        if provider == "groq":
            return banner(
                "🚀 Agente Arquitectónico con Groq (gratis)",
                "Proveedor: Groq (openai/gpt-oss-20b)",
                "Precio: Gratis, sin tarjeta de crédito",
                "Velocidad: 100+ tokens/s",
            )
        elif provider == "ollama":
            host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
            return banner(
                "🚀 Agente Arquitectónico con Ollama (local)",
                f"Host: {host}",
                "Modelo: qwen3:8b (u otro instalado)",
                "Precio: Gratis (local)",
            )
        elif provider == "proxy":
            proxy_url = os.getenv("PROXY_URL", "(no configurada)")
            return banner(
                "🚀 Agente Arquitectónico con servidor Proxy (demo)",
                f"Servidor: {proxy_url}",
                "Precio: Gratis, sujeto al límite del operador",
                "Nota: para uso ilimitado, usa tu propia clave Groq",
            )
        elif provider == "claude":
            modelo = os.getenv("LLM_CLAUDE_MODEL", "claude-opus-5-5")
            return banner(
                "🚀 Agente Arquitectónico con Claude (API de Anthropic)",
                f"Modelo: {modelo}",
                "Precio: de pago, según uso de tu cuenta de Anthropic",
            )
        elif provider == "mock":
            return banner(
                "🧪 Agente Arquitectónico (Modo Mock - Tests)",
                "Proveedor: MockProvider (respuestas simuladas)",
                "Uso: solo para testing",
            )
        else:
            return f"🚀 Agente Arquitectónico con {provider.upper()}\n"
