"""Pantalla de bienvenida cuando falta configurar el proveedor LLM."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

RAIZ = Path(__file__).resolve().parent.parent


@pytest.fixture
def entorno_vacio(monkeypatch):
    """Sin .env real ni claves: lo que vería quien acaba de clonar el repo."""
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)
    for variable in ("GROQ_API_KEY", "PROXY_URL", "ANTHROPIC_API_KEY", "LLM_PROVIDER"):
        monkeypatch.delenv(variable, raising=False)
    return monkeypatch


def _abrir_app():
    return AppTest.from_file(str(RAIZ / "app.py"), default_timeout=30).run()


def test_sin_configurar_muestra_bienvenida_en_lugar_de_una_traza(entorno_vacio):
    at = _abrir_app()

    assert not at.exception
    assert at.subheader[0].value == "Falta un paso para empezar"
    assert [t.label for t in at.tabs] == [
        "Groq (gratis)", "Servidor demo", "Ollama (local)", "Claude (de pago)",
    ]
    assert "setup_llm.py" in at.info[0].value


def test_no_muestra_las_secciones_de_la_app_sin_configurar(entorno_vacio):
    at = _abrir_app()

    assert len(at.header) == 0
    assert not at.text_area


def test_explica_que_falla_exactamente(entorno_vacio):
    at = _abrir_app()

    detalles = [c.value for c in at.code]
    assert any("GROQ_API_KEY no configurada" in d for d in detalles)


def test_proxy_sin_url_tambien_muestra_bienvenida(entorno_vacio):
    entorno_vacio.setenv("LLM_PROVIDER", "proxy")

    at = _abrir_app()

    assert not at.exception
    assert at.subheader[0].value == "Falta un paso para empezar"
    assert any("PROXY_URL no configurada" in c.value for c in at.code)


def test_proveedor_desconocido_tambien_muestra_bienvenida(entorno_vacio):
    entorno_vacio.setenv("LLM_PROVIDER", "inventado")

    at = _abrir_app()

    assert not at.exception
    assert any("desconocido" in c.value for c in at.code)


def test_con_proveedor_valido_va_directo_a_la_app(entorno_vacio):
    entorno_vacio.setenv("LLM_PROVIDER", "mock")

    at = _abrir_app()

    assert not at.exception
    assert [h.value for h in at.header] == ["Nuevo proyecto"]
    assert len(at.subheader) == 0 or at.subheader[0].value != "Falta un paso para empezar"


def test_una_salida_sin_utf8_no_se_confunde_con_un_error_de_configuracion(entorno_vacio):
    """UnicodeEncodeError es un ValueError: el aviso con emojis no debe disparar la bienvenida."""
    import io
    import sys

    entorno_vacio.setenv("LLM_PROVIDER", "mock")
    entorno_vacio.setattr(sys, "stdout", io.TextIOWrapper(io.BytesIO(), encoding="cp1252"))

    at = _abrir_app()

    assert not at.exception
    assert [h.value for h in at.header] == ["Nuevo proyecto"]
