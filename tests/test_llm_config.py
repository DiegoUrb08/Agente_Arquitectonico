"""Tests para configuración de proveedores LLM."""

import os
import pytest
from unittest.mock import patch

from src.ai.config import LLMConfig


class TestLLMConfigValidation:
    """Tests para validación de configuración."""

    def test_validar_provider_claude_sin_key_lanza_error(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "claude"}, clear=True):
            with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
                LLMConfig.validar_provider()

    def test_validar_provider_claude_con_key(self):
        with patch.dict(os.environ, {
            "LLM_PROVIDER": "claude",
            "ANTHROPIC_API_KEY": "sk-ant-test",
        }, clear=True):
            nombre, config = LLMConfig.validar_provider()
            assert nombre == "claude"
            assert config["api_key"] == "sk-ant-test"

    def test_mensaje_bienvenida_claude_muestra_el_modelo(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "claude"}, clear=True):
            assert "claude-opus-5-5" in LLMConfig.mensaje_bienvenida()

    def test_openai_ya_no_es_un_proveedor_valido(self):
        """get_provider nunca lo implementó; validarlo solo daba falsas esperanzas."""
        with patch.dict(os.environ, {"LLM_PROVIDER": "openai"}, clear=True):
            with pytest.raises(ValueError, match="desconocido"):
                LLMConfig.validar_provider()

    def test_validar_provider_groq_sin_key_lanza_error(self):
        """Groq sin GROQ_API_KEY debe lanzar ValueError claro."""
        with patch.dict(os.environ, {"LLM_PROVIDER": "groq"}, clear=True):
            with pytest.raises(ValueError, match="GROQ_API_KEY"):
                LLMConfig.validar_provider()

    def test_validar_provider_groq_con_key(self):
        """Groq con GROQ_API_KEY devuelve config."""
        with patch.dict(os.environ, {
            "LLM_PROVIDER": "groq",
            "GROQ_API_KEY": "gsk_test123"
        }):
            nombre, config = LLMConfig.validar_provider()
            assert nombre == "groq"
            assert config["api_key"] == "gsk_test123"

    def test_validar_provider_ollama(self):
        """Ollama devuelve config con host."""
        with patch.dict(os.environ, {
            "LLM_PROVIDER": "ollama",
            "OLLAMA_HOST": "http://localhost:11434"
        }):
            nombre, config = LLMConfig.validar_provider()
            assert nombre == "ollama"
            assert config["host"] == "http://localhost:11434"

    def test_validar_provider_ollama_host_por_defecto(self):
        """Ollama sin OLLAMA_HOST usa default."""
        with patch.dict(os.environ, {"LLM_PROVIDER": "ollama"}, clear=True):
            nombre, config = LLMConfig.validar_provider()
            assert nombre == "ollama"
            assert "localhost" in config["host"]

    def test_validar_provider_mock(self):
        """Mock provider no requiere configuración."""
        with patch.dict(os.environ, {"LLM_PROVIDER": "mock"}, clear=True):
            nombre, config = LLMConfig.validar_provider()
            assert nombre == "mock"
            assert config == {}

    def test_validar_provider_desconocido_lanza_error(self):
        """Proveedor desconocido lanza ValueError."""
        with patch.dict(os.environ, {"LLM_PROVIDER": "desconocido"}, clear=True):
            with pytest.raises(ValueError, match="desconocido"):
                LLMConfig.validar_provider()

    def test_mensaje_bienvenida_groq(self):
        """Mensaje de bienvenida incluye info de Groq."""
        with patch.dict(os.environ, {"LLM_PROVIDER": "groq"}):
            msg = LLMConfig.mensaje_bienvenida()
            assert "Groq" in msg
            assert "gratis" in msg.lower()

    def test_mensaje_bienvenida_ollama(self):
        """Mensaje de bienvenida incluye host de Ollama."""
        with patch.dict(os.environ, {
            "LLM_PROVIDER": "ollama",
            "OLLAMA_HOST": "http://ejemplo.com:11434"
        }):
            msg = LLMConfig.mensaje_bienvenida()
            assert "ejemplo.com" in msg
            assert "Ollama" in msg

    def test_mensaje_bienvenida_mock(self):
        """Mensaje de bienvenida incluye indicador de testing."""
        with patch.dict(os.environ, {"LLM_PROVIDER": "mock"}):
            msg = LLMConfig.mensaje_bienvenida()
            assert "Mock" in msg or "Test" in msg
