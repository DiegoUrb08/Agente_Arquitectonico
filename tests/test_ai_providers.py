"""Tests para los proveedores LLM."""

import pytest
from unittest.mock import patch, MagicMock

from src.ai.providers import get_provider, MockProvider, LLMProvider


class TestMockProvider:
    """Tests para MockProvider (siempre disponible)."""

    def test_mock_provider_chat(self):
        provider = MockProvider()
        respuesta = provider.chat(
            messages=[{"role": "user", "content": "Hola"}]
        )
        assert "message" in respuesta
        assert "content" in respuesta["message"]
        assert respuesta["message"]["role"] == "assistant"

    def test_mock_provider_propiedades(self):
        provider = MockProvider()
        assert provider.nombre == "mock"
        assert provider.modelo == "mock-model"


class TestGroqProvider:
    """Tests para GroqProvider (requiere GROQ_API_KEY)."""

    @patch("src.ai.providers.groq_provider.os.getenv")
    def test_groq_provider_sin_api_key_lanza_error(self, mock_getenv):
        mock_getenv.return_value = None
        from src.ai.providers.groq_provider import GroqProvider

        with pytest.raises(ValueError, match="GROQ_API_KEY"):
            GroqProvider(api_key=None)

    def test_groq_provider_propiedades(self):
        with patch("groq.Groq"):
            from src.ai.providers.groq_provider import GroqProvider

            provider = GroqProvider(api_key="gsk_test_key")
            assert provider.nombre == "groq"
            assert provider.modelo == "openai/gpt-oss-20b"


class TestOllamaProvider:
    """Tests para OllamaProvider (requiere Ollama local)."""

    def test_ollama_provider_propiedades(self):
        with patch("src.ai.providers.ollama_provider.os.getenv") as mock_getenv:
            mock_getenv.return_value = "http://localhost:11434"
            from src.ai.providers.ollama_provider import OllamaProvider

            provider = OllamaProvider()
            assert provider.nombre == "ollama"
            assert provider.modelo == "qwen3:8b"


class TestFactory:
    """Tests para el factory get_provider()."""

    def test_factory_devuelve_mock_por_defecto_en_tests(self):
        with patch("src.ai.providers.os.getenv") as mock_getenv:
            mock_getenv.return_value = "mock"
            provider = get_provider("mock")
            assert isinstance(provider, MockProvider)

    def test_factory_lanza_error_con_proveedor_desconocido(self):
        with pytest.raises(ValueError, match="desconocido"):
            get_provider("desconocido")


class TestInterpreterConProveedores:
    """Tests de integración: interpreter con diferentes proveedores."""

    def test_interpreter_con_mock_provider(self):
        """Prueba que el interpreter funciona con MockProvider."""
        from src.ai.interpreter import interpretar_instruccion

        with patch("src.ai.providers.os.getenv") as mock_getenv:
            mock_getenv.return_value = "mock"

            instruccion = "Casa de 10x20 metros con 2 dormitorios"
            resultado = interpretar_instruccion(instruccion)

            assert resultado.ancho_terreno_m is not None or resultado.largo_terreno_m is not None
            assert len(resultado.ambientes) > 0

    def test_interpreter_maneja_provider_indisponible_gracefully(self):
        """Si un provider falta pero es mock, funciona."""
        from src.ai.interpreter import interpretar_instruccion

        # Mock siempre funciona
        with patch("src.ai.providers.os.getenv") as mock_getenv:
            mock_getenv.return_value = "mock"
            instruccion = "Proyecto simple"
            resultado = interpretar_instruccion(instruccion)
            assert resultado is not None
