"""Tests para los proveedores LLM."""

import os
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


# ---------------------------------------------------------------------------
# Contratos de interfaz: todos los proveedores deben cumplir la misma API
# ---------------------------------------------------------------------------

def _provider_groq_mockeado():
    """GroqProvider con cliente Groq simulado (sin red ni clave real).
    GroqProvider usa self.client (instancia de groq.Groq).
    """
    with patch("groq.Groq"):
        from src.ai.providers.groq_provider import GroqProvider
        p = GroqProvider(api_key="gsk_test_fake")
    mock_cliente = MagicMock()
    mock_cliente.chat.completions.create.return_value.choices = [
        MagicMock(message=MagicMock(content="hola"))
    ]
    p.client = mock_cliente
    return p


def _provider_ollama_mockeado():
    """OllamaProvider con módulo ollama simulado.
    OllamaProvider crea ollama.Client() en cada chat(); se mockea self.ollama.
    """
    from src.ai.providers.ollama_provider import OllamaProvider
    p = OllamaProvider(host="http://localhost:11434")
    mock_ollama = MagicMock()
    mock_ollama.Client.return_value.chat.return_value = {
        "message": {"content": "hola", "role": "assistant"}
    }
    p.ollama = mock_ollama
    return p


def _provider_proxy_mockeado():
    """ProxyProvider con requests simulado.
    ProxyProvider usa self.requests (módulo requests).
    """
    from src.ai.providers.proxy_provider import ProxyProvider
    p = ProxyProvider(proxy_url="http://localhost:8000")
    mock_req = MagicMock()
    mock_req.post.return_value.status_code = 200
    mock_req.post.return_value.json.return_value = {
        "message": {"content": "hola", "role": "assistant"}
    }
    p.requests = mock_req
    return p


PROVIDERS_MOCKEADOS = [
    pytest.param(MockProvider(), id="mock"),
    pytest.param(_provider_groq_mockeado(), id="groq"),
    pytest.param(_provider_ollama_mockeado(), id="ollama"),
    pytest.param(_provider_proxy_mockeado(), id="proxy"),
]


class TestContratosProveedores:
    """Verifica que todos los proveedores cumplen la interfaz LLMProvider."""

    @pytest.mark.parametrize("provider", PROVIDERS_MOCKEADOS)
    def test_nombre_es_string_no_vacio(self, provider):
        assert isinstance(provider.nombre, str)
        assert len(provider.nombre) > 0

    @pytest.mark.parametrize("provider", PROVIDERS_MOCKEADOS)
    def test_modelo_es_string_no_vacio(self, provider):
        assert isinstance(provider.modelo, str)
        assert len(provider.modelo) > 0

    @pytest.mark.parametrize("provider", PROVIDERS_MOCKEADOS)
    def test_es_subclase_de_llmprovider(self, provider):
        assert isinstance(provider, LLMProvider)

    @pytest.mark.parametrize("provider", PROVIDERS_MOCKEADOS)
    def test_chat_devuelve_estructura_message_content_role(self, provider):
        respuesta = provider.chat(messages=[{"role": "user", "content": "hola"}])
        assert isinstance(respuesta, dict), "chat() debe devolver un dict"
        assert "message" in respuesta, "Falta clave 'message'"
        assert "content" in respuesta["message"], "Falta 'message.content'"
        assert "role" in respuesta["message"], "Falta 'message.role'"

    @pytest.mark.parametrize("provider", PROVIDERS_MOCKEADOS)
    def test_chat_role_es_assistant(self, provider):
        respuesta = provider.chat(messages=[{"role": "user", "content": "hola"}])
        assert respuesta["message"]["role"] == "assistant"

    @pytest.mark.parametrize("provider", PROVIDERS_MOCKEADOS)
    def test_chat_content_es_string(self, provider):
        respuesta = provider.chat(messages=[{"role": "user", "content": "hola"}])
        assert isinstance(respuesta["message"]["content"], str)


class TestFactoryEnv:
    """Verifica que la factory responde correctamente a la variable de entorno."""

    @pytest.mark.parametrize("nombre_proveedor", ["mock"])
    def test_factory_lee_llm_provider_de_env(self, nombre_proveedor):
        with patch.dict(os.environ, {"LLM_PROVIDER": nombre_proveedor}):
            provider = get_provider()
            assert provider.nombre == nombre_proveedor

    def test_factory_proveedor_explicito_ignora_env(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "ollama"}):
            provider = get_provider("mock")
            assert provider.nombre == "mock"
