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
        elif provider_name == "claude":
            return LLMConfig._validar_claude()
        elif provider_name == "openai":
            return LLMConfig._validar_openai()
        elif provider_name == "mock":
            return "mock", {}
        else:
            raise ValueError(
                f"Proveedor LLM desconocido: {provider_name}. "
                f"Opciones: groq, ollama, claude, openai, mock"
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
    def _validar_claude() -> tuple[str, dict]:
        """Valida configuración de Claude."""
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError(
                "\n❌ ANTHROPIC_API_KEY no configurada.\n"
                "Para usar Claude:\n"
                "  1. Visita: https://console.anthropic.com/keys\n"
                "  2. Genera una clave\n"
                "  3. Copia en .env: ANTHROPIC_API_KEY=sk_...\n"
            )
        return "claude", {"api_key": api_key}

    @staticmethod
    def _validar_openai() -> tuple[str, dict]:
        """Valida configuración de OpenAI."""
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "\n❌ OPENAI_API_KEY no configurada.\n"
                "Para usar OpenAI:\n"
                "  1. Visita: https://platform.openai.com/api-keys\n"
                "  2. Genera una clave\n"
                "  3. Copia en .env: OPENAI_API_KEY=sk_...\n"
            )
        return "openai", {"api_key": api_key}

    @staticmethod
    def mensaje_bienvenida() -> str:
        """Devuelve un mensaje de bienvenida con instrucciones."""
        provider = os.getenv("LLM_PROVIDER", "groq").lower()

        if provider == "groq":
            return (
                "🚀 Agente Arquitectónico con Groq (gratis)\n"
                "━" * 40 + "\n"
                "Proveedor: Groq Mixtral 8x7B\n"
                "Precio: Gratis, sin tarjeta de crédito\n"
                "Velocidad: 100+ tokens/s\n"
            )
        elif provider == "ollama":
            host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
            return (
                f"🚀 Agente Arquitectónico con Ollama (local)\n"
                "━" * 40 + "\n"
                f"Host: {host}\n"
                f"Modelo: qwen3:8b (u otro instalado)\n"
                "Precio: Gratis (local)\n"
            )
        elif provider == "mock":
            return (
                "🧪 Agente Arquitectónico (Modo Mock - Tests)\n"
                "━" * 40 + "\n"
                "Proveedor: MockProvider (respuestas simuladas)\n"
                "Uso: solo para testing\n"
            )
        else:
            return f"🚀 Agente Arquitectónico con {provider.upper()}\n"
