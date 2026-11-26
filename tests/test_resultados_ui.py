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


def test_los_ejemplos_rellenan_el_cuadro_de_texto(entorno):
    from src.ui.interfaz import EJEMPLOS

    at = _abrir()

    at.pills[0].set_value("Vivienda familiar").run()

    assert at.text_area[0].value == EJEMPLOS["Vivienda familiar"]
    assert at.pills[0].value is None, "debe poder elegirse otra vez el mismo ejemplo"


def _control(at, opcion):
    return next(c for c in at.segmented_control if opcion in c.options)


def test_el_visor_ofrece_capas_cambios_y_vista(entorno):
    from src.ui.resultados import VISTA_TERRENO, VISTA_VIVIENDA

    at = _con_plano()

    capas = next(p for p in at.pills if "Cambios" in p.options)
    vista = _control(at, VISTA_TERRENO)

    assert "Cambios" in capas.options
    assert vista.options == [VISTA_TERRENO, VISTA_VIVIENDA]
    assert vista.value == VISTA_VIVIENDA, "el plano fijo ocupa ~35 % del terreno"


def test_la_vista_3d_se_abre_desde_el_visor(entorno):
    from src.ui.resultados import MODO_2D, MODO_3D, VISTA_TERRENO

    at = _con_plano()
    modo = _control(at, MODO_3D)
    assert modo.value == MODO_2D

    modo.set_value(MODO_3D).run()

    assert not at.exception
    assert not any(VISTA_TERRENO in c.options for c in at.segmented_control)
    assert not [b for b in at.get("download_button") if "SVG" in b.proto.label]
    assert any("Techos abiertos" in c.value for c in at.caption)


def test_el_detalle_alto_es_opcional(entorno):
    from src.ui.resultados import MODO_3D

    at = _con_plano()
    _control(at, MODO_3D).set_value(MODO_3D).run()

    detalle = next(t for t in at.toggle if t.label == "Detalle alto")
    assert detalle.value is False

    detalle.set_value(True).run()

    assert not at.exception


def test_se_ofrece_el_modelo_bim(entorno):
    at = _con_plano()

    etiquetas = [b.proto.label for b in at.get("download_button")]

    assert "Modelo BIM (IFC)" in etiquetas
    assert not at.exception
