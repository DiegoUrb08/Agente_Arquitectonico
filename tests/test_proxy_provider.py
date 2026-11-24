"""Tests para ProxyProvider y proxy_server."""

import os
import pytest
from unittest.mock import patch, MagicMock

from src.ai.providers.proxy_provider import ProxyProvider


class TestProxyProviderInit:
    def test_sin_proxy_url_lanza_error(self):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="PROXY_URL"):
                ProxyProvider(proxy_url=None)

    def test_con_proxy_url_explicita(self):
        provider = ProxyProvider(proxy_url="http://localhost:8000")
        assert provider.proxy_url == "http://localhost:8000"
        assert provider.nombre == "proxy"

    def test_quita_barra_final_de_url(self):
        provider = ProxyProvider(proxy_url="http://localhost:8000/")
        assert provider.proxy_url == "http://localhost:8000"

    def test_lee_proxy_url_de_env(self):
        with patch.dict(os.environ, {"PROXY_URL": "http://env-server:9000"}):
            provider = ProxyProvider()
            assert provider.proxy_url == "http://env-server:9000"


class TestProxyProviderChat:
    def test_chat_exitoso(self):
        provider = ProxyProvider(proxy_url="http://localhost:8000")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {"content": "respuesta de prueba", "role": "assistant"}
        }

        with patch.object(provider.requests, "post", return_value=mock_response):
            resultado = provider.chat(messages=[{"role": "user", "content": "hola"}])
            assert resultado["message"]["content"] == "respuesta de prueba"

    def test_chat_envia_token_si_configurado(self):
        provider = ProxyProvider(
            proxy_url="http://localhost:8000",
            access_token="secreto123",
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message": {"content": "ok", "role": "assistant"}}

        with patch.object(provider.requests, "post", return_value=mock_response) as mock_post:
            provider.chat(messages=[{"role": "user", "content": "hola"}])
            _, kwargs = mock_post.call_args
            assert kwargs["headers"]["X-Proxy-Token"] == "secreto123"

    def test_chat_rate_limit_lanza_error_claro(self):
        provider = ProxyProvider(proxy_url="http://localhost:8000")

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.json.return_value = {"error": "Límite de uso alcanzado"}

        with patch.object(provider.requests, "post", return_value=mock_response):
            with pytest.raises(RuntimeError, match="Límite de uso"):
                provider.chat(messages=[{"role": "user", "content": "hola"}])

    def test_chat_error_conexion_lanza_runtime_error(self):
        provider = ProxyProvider(proxy_url="http://servidor-inexistente:9999")

        with patch.object(
            provider.requests, "post",
            side_effect=provider.requests.exceptions.ConnectionError("no conecta")
        ):
            with pytest.raises(RuntimeError, match="No se pudo conectar"):
                provider.chat(messages=[{"role": "user", "content": "hola"}])

    def test_chat_error_servidor_lanza_runtime_error(self):
        provider = ProxyProvider(proxy_url="http://localhost:8000")

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.return_value = {"error": "GROQ_API_KEY no configurada"}

        with patch.object(provider.requests, "post", return_value=mock_response):
            with pytest.raises(RuntimeError, match="500"):
                provider.chat(messages=[{"role": "user", "content": "hola"}])


class TestProxyServerIntegration:
    """Tests del servidor Flask usando su test client (sin red real)."""

    @pytest.fixture
    def cliente_servidor(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
        monkeypatch.setenv("RATE_LIMIT_REQUESTS", "2")
        monkeypatch.setenv("RATE_LIMIT_WINDOW_S", "3600")
        import importlib
        from server import proxy_server
        importlib.reload(proxy_server)
        proxy_server._peticiones_por_ip.clear()
        return proxy_server.app.test_client()

    def test_health_devuelve_ok(self, cliente_servidor):
        resp = cliente_servidor.get("/health")
        assert resp.status_code == 200
        assert resp.get_json()["groq_configurado"] is True

    def test_chat_sin_messages_devuelve_400(self, cliente_servidor):
        resp = cliente_servidor.post("/chat", json={})
        assert resp.status_code == 400

    def test_chat_exitoso_llama_a_groq(self, cliente_servidor):
        with patch("server.proxy_server.Groq" if False else "groq.Groq") as MockGroq:
            mock_instancia = MagicMock()
            mock_instancia.chat.completions.create.return_value.choices = [
                MagicMock(message=MagicMock(content="plano generado"))
            ]
            MockGroq.return_value = mock_instancia

            resp = cliente_servidor.post(
                "/chat",
                json={"messages": [{"role": "user", "content": "hola"}]},
            )
            assert resp.status_code == 200
            assert resp.get_json()["message"]["content"] == "plano generado"

    def test_rate_limit_bloquea_tras_limite(self, cliente_servidor):
        with patch("groq.Groq") as MockGroq:
            mock_instancia = MagicMock()
            mock_instancia.chat.completions.create.return_value.choices = [
                MagicMock(message=MagicMock(content="ok"))
            ]
            MockGroq.return_value = mock_instancia

            payload = {"messages": [{"role": "user", "content": "hola"}]}
            # Límite configurado a 2 en el fixture
            r1 = cliente_servidor.post("/chat", json=payload)
            r2 = cliente_servidor.post("/chat", json=payload)
            r3 = cliente_servidor.post("/chat", json=payload)

            assert r1.status_code == 200
            assert r2.status_code == 200
            assert r3.status_code == 429

    def test_token_invalido_devuelve_401(self, cliente_servidor, monkeypatch):
        monkeypatch.setenv("PROXY_ACCESS_TOKEN", "correcto")
        import importlib
        from server import proxy_server
        importlib.reload(proxy_server)
        proxy_server._peticiones_por_ip.clear()
        cliente = proxy_server.app.test_client()

        resp = cliente.post(
            "/chat",
            json={"messages": [{"role": "user", "content": "hola"}]},
            headers={"X-Proxy-Token": "incorrecto"},
        )
        assert resp.status_code == 401
