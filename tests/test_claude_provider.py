"""Tests de ClaudeProvider y de LLMProviderError (sin red ni claves reales)."""

import os
import pytest
from unittest.mock import MagicMock, patch

from src.ai.providers import LLMProviderError, get_provider
from src.ai.providers.claude_provider import ClaudeProvider

MENSAJE_USUARIO = [{"role": "user", "content": "hola"}]


def _respuesta(texto="hola", stop_reason="end_turn"):
    bloque = MagicMock()
    bloque.type = "text"
    bloque.text = texto
    return MagicMock(stop_reason=stop_reason, content=[bloque])


@pytest.fixture
def provider():
    p = ClaudeProvider(api_key="sk-ant-test")
    p.client = MagicMock()
    p.client.messages.create.return_value = _respuesta()
    return p


class TestClaudeProvider:
    def test_sin_api_key_lanza_error(self):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
                ClaudeProvider()

    def test_modelo_por_defecto_y_por_variable_de_entorno(self):
        with patch.dict(os.environ, {}, clear=True):
            assert ClaudeProvider(api_key="k").modelo == "claude-opus-5-5"
        with patch.dict(os.environ, {"LLM_CLAUDE_MODEL": "claude-haiku-5-5"}, clear=True):
            assert ClaudeProvider(api_key="k").modelo == "claude-haiku-5-5"

    def test_factory_devuelve_claude(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}):
            assert get_provider("claude").nombre == "claude"

    def test_los_mensajes_system_van_en_el_campo_system(self, provider):
        provider.chat(messages=[
            {"role": "system", "content": "Eres un arquitecto."},
            {"role": "user", "content": "hola"},
        ])

        kwargs = provider.client.messages.create.call_args.kwargs
        assert kwargs["system"] == "Eres un arquitecto."
        assert kwargs["messages"] == [{"role": "user", "content": "hola"}]

    def test_sin_mensaje_system_no_envia_el_campo(self, provider):
        provider.chat(messages=MENSAJE_USUARIO)

        assert "system" not in provider.client.messages.create.call_args.kwargs

    def test_no_envia_temperature_ni_kwargs_de_otros_proveedores(self, provider):
        """Los modelos Claude 5 rechazan temperature con un 400."""
        provider.chat(
            messages=MENSAJE_USUARIO,
            temperature=0.1,
            format={"type": "object"},
        )

        kwargs = provider.client.messages.create.call_args.kwargs
        assert "temperature" not in kwargs
        assert "format" not in kwargs
        assert kwargs["model"] == "claude-opus-5-5"
        assert kwargs["output_config"] == {"effort": "low"}
        assert kwargs["max_tokens"] == 16000

    def test_solo_concatena_bloques_de_texto(self, provider):
        pensamiento = MagicMock(type="thinking")
        texto_a, texto_b = MagicMock(type="text"), MagicMock(type="text")
        texto_a.text, texto_b.text = '{"a":', " 1}"
        provider.client.messages.create.return_value = MagicMock(
            stop_reason="end_turn", content=[pensamiento, texto_a, texto_b]
        )

        r = provider.chat(messages=MENSAJE_USUARIO)

        assert r["message"] == {"content": '{"a": 1}', "role": "assistant"}

    def test_rechazo_por_seguridad_lanza_error_claro(self, provider):
        provider.client.messages.create.return_value = _respuesta("", "refusal")

        with pytest.raises(LLMProviderError, match="rechaz"):
            provider.chat(messages=MENSAJE_USUARIO)

    @pytest.mark.parametrize("excepcion, codigo, fragmento", [
        ("AuthenticationError", 401, "ANTHROPIC_API_KEY"),
        ("RateLimitError", 429, "límite de peticiones"),
        ("BadRequestError", 400, r"\(400\)"),
    ])
    def test_errores_de_la_api_se_convierten_en_llmprovidererror(
        self, provider, excepcion, codigo, fragmento
    ):
        import anthropic
        import httpx2

        peticion = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
        respuesta = httpx2.Response(codigo, request=peticion)
        provider.client.messages.create.side_effect = getattr(anthropic, excepcion)(
            "fallo", response=respuesta, body=None
        )

        with pytest.raises(LLMProviderError, match=fragmento):
            provider.chat(messages=MENSAJE_USUARIO)

    def test_error_de_conexion_se_convierte_en_llmprovidererror(self, provider):
        import anthropic
        import httpx2

        peticion = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
        provider.client.messages.create.side_effect = anthropic.APIConnectionError(
            request=peticion
        )

        with pytest.raises(LLMProviderError, match="No se pudo conectar"):
            provider.chat(messages=MENSAJE_USUARIO)


class TestLLMProviderError:
    """Los fallos esperables de los proveedores usan una excepción propia."""

    def test_es_un_runtime_error(self):
        assert issubclass(LLMProviderError, RuntimeError)

    def test_groq_envuelve_los_errores_de_la_api(self):
        from src.ai.providers.groq_provider import GroqProvider

        with patch("groq.Groq"):
            p = GroqProvider(api_key="gsk_test")
        p.client = MagicMock()
        p.client.chat.completions.create.side_effect = Exception("cuota agotada")

        with pytest.raises(LLMProviderError, match="cuota agotada"):
            p.chat(messages=MENSAJE_USUARIO)

    def test_proxy_rate_limit_es_llmprovidererror(self):
        from src.ai.providers.proxy_provider import ProxyProvider

        p = ProxyProvider(proxy_url="http://localhost:8000")
        p.requests = MagicMock()
        p.requests.post.return_value.status_code = 429
        p.requests.post.return_value.json.return_value = {"error": "Límite de uso alcanzado"}

        with pytest.raises(LLMProviderError, match="Límite de uso"):
            p.chat(messages=MENSAJE_USUARIO)

    def test_la_ui_lo_trata_como_error_esperado(self):
        """Sin esto, el límite del proxy saldría como 'Error inesperado' con traza."""
        from src.ui.interfaz import ERRORES_CONTROLADOS

        assert LLMProviderError in ERRORES_CONTROLADOS
