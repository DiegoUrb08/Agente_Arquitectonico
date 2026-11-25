"""Flujo de la interfaz: inicio, espacio de trabajo, edición por conversación y deshacer."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src.ai.edit_interpreter import EditOperation, EditRequest
from tests.plano_fijo import generar_plano_fijo

RAIZ = Path(__file__).resolve().parent.parent
PESTANAS = ["Plano", "Ambientes", "Conectividad", "Puertas", "Requerimientos"]


@pytest.fixture
def entorno(monkeypatch):
    """Proveedor mock, sin .env real y con un plano fijo (rápido y determinista)."""
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)
    monkeypatch.setattr("src.ui.proyecto.generar_plano", generar_plano_fijo)
    return monkeypatch


def _abrir():
    return AppTest.from_file(str(RAIZ / "app.py"), default_timeout=90).run()


def _con_plano():
    at = _abrir()
    at.text_area[0].input("Casa en un terreno de 10 x 20 m con sala y cocina")
    return at.button[0].click().run()


def _reducir(texto):
    return EditRequest(operaciones=[
        EditOperation(tipo="modificar_area", ambiente="dormitorio 1", area_objetivo=8)
    ])


def _boton(at, fragmento):
    return next(b for b in at.button if fragmento in b.label)


def _version(at):
    return next(c.value for c in at.caption if c.value.startswith("Versión"))


def test_al_abrir_se_muestra_el_inicio(entorno):
    at = _abrir()

    assert not at.exception
    assert [h.value for h in at.header] == ["Nuevo proyecto"]
    assert at.text_area and not at.chat_input


def test_generar_abre_el_espacio_de_trabajo(entorno):
    at = _con_plano()

    assert not at.exception
    assert len(at.chat_input) == 1
    assert [m.name for m in at.chat_message] == ["user", "assistant"]
    assert [t.label for t in at.tabs] == PESTANAS
    etiquetas = [m.label for m in at.metric]
    for esperada in ("Terreno", "Ambientes", "Superficie construida", "Ambientes conectados"):
        assert esperada in etiquetas
    assert _version(at).startswith("Versión 1")


def test_el_plano_sobrevive_a_otra_interaccion(entorno):
    """Antes, pulsar 'Descargar' (o cualquier widget) borraba el plano."""
    at = _con_plano()

    at.run()

    assert not at.exception
    assert [t.label for t in at.tabs] == PESTANAS
    assert len(at.chat_message) == 2


def test_una_descripcion_vacia_no_crea_proyecto(entorno):
    at = _abrir()
    at.text_area[0].input("   ")
    at.button[0].click().run()

    assert [w.value for w in at.warning if "descripción" in w.value]
    assert "proyecto" not in at.session_state


def test_un_cambio_por_conversacion_crea_una_version(entorno):
    entorno.setattr("src.ui.interfaz.interpretar_edicion", _reducir)
    at = _con_plano()

    at.chat_input[0].set_value("reduce el dormitorio 1 a 8 m2").run()

    assert not at.exception
    assert len(at.chat_message) == 4
    assert "Dormitorio 1: 12.0 → 8.0 m²" in at.chat_message[3].markdown[0].value
    assert _version(at).startswith("Versión 2")


def test_deshacer_vuelve_a_la_version_anterior(entorno):
    entorno.setattr("src.ui.interfaz.interpretar_edicion", _reducir)
    at = _con_plano()
    at.chat_input[0].set_value("reduce el dormitorio 1 a 8 m2").run()

    _boton(at, "Deshacer").click().run()

    assert _version(at).startswith("Versión 1")
    assert "Deshice" in at.chat_message[-1].markdown[0].value
    assert _boton(at, "Deshacer").disabled


def test_no_se_puede_deshacer_sin_cambios(entorno):
    at = _con_plano()

    assert _boton(at, "Deshacer").disabled


def test_un_cambio_imposible_se_explica_y_no_crea_version(entorno):
    def rechazar(texto):
        raise ValueError("No entendí qué ambiente quieres cambiar.")

    entorno.setattr("src.ui.interfaz.interpretar_edicion", rechazar)
    at = _con_plano()

    at.chat_input[0].set_value("haz algo raro").run()

    assert not at.exception
    assert any("No entendí" in e.value for e in at.error)
    assert _version(at).startswith("Versión 1")


def test_nuevo_proyecto_vuelve_al_inicio(entorno):
    at = _con_plano()

    _boton(at, "Nuevo proyecto").click().run()

    assert [h.value for h in at.header] == ["Nuevo proyecto"]
    assert "proyecto" not in at.session_state


def test_con_varias_plantas_la_conversacion_queda_desactivada(entorno):
    entorno.setattr("src.ui.proyecto.puede_editar", lambda resultado: False)
    at = _con_plano()

    assert at.chat_input[0].disabled
    assert "varias plantas" in at.chat_message[1].markdown[0].value
