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
    assert "Lámina (PDF)" in etiquetas
    assert not at.exception


# ---------------------------------------------------------------- guardado

def test_el_proyecto_se_autoguarda_al_crear_editar_y_deshacer(entorno):
    from src.ui import almacen

    entorno.setattr("src.ui.interfaz.interpretar_edicion", _reducir)
    at = _con_plano()
    assert almacen.listar()[0][0]["versiones"] == 1

    at.chat_input[0].set_value("reduce el dormitorio 1").run()
    assert almacen.listar()[0][0]["versiones"] == 2

    _boton(at, "Deshacer").click().run()
    proyectos = almacen.listar()[0]
    assert len(proyectos) == 1 and proyectos[0]["versiones"] == 1
    assert any(
        b.proto.label == "Guardar en archivo" for b in at.get("download_button")
    )


def _casilla(at, rotulo):
    return next(t for t in at.text_input if t.label == rotulo)


def test_el_nombre_y_el_autor_se_guardan_y_se_recuperan(entorno):
    from src.ui import almacen

    at = _con_plano()
    _casilla(at, "Nombre del proyecto").set_value("Casa Pérez").run()
    _casilla(at, "Autor").set_value("  María   Núñez ").run()

    assert not at.exception
    guardado = almacen.abrir(almacen.listar()[0][0]["id"])
    assert (guardado["nombre"], guardado["autor"]) == ("Casa Pérez", "María Núñez")

    nuevo = _abrir()
    _boton(nuevo, "Abrir proyecto").click().run()
    assert _casilla(nuevo, "Nombre del proyecto").value == "Casa Pérez"
    assert _casilla(nuevo, "Autor").value == "María Núñez"


def test_el_nombre_no_puede_quedar_vacio_y_no_pasa_a_otro_proyecto(entorno):
    at = _con_plano()
    original = _casilla(at, "Nombre del proyecto").value

    _casilla(at, "Nombre del proyecto").set_value("   ").run()
    assert _casilla(at, "Nombre del proyecto").value == original

    _casilla(at, "Autor").set_value("Ana").run()
    _boton(at, "Nuevo proyecto").click().run()
    at.text_area[0].set_value("Casa en un terreno de 10 x 20 con sala y cocina")
    _boton(at, "Generar plano").click().run()

    assert not at.exception
    assert _casilla(at, "Autor").value == ""


def test_se_retoma_un_proyecto_de_la_lista(entorno):
    entorno.setattr("src.ui.interfaz.interpretar_edicion", _reducir)
    at = _con_plano()
    at.chat_input[0].set_value("reduce el dormitorio 1").run()

    nuevo = _abrir()
    opcion = nuevo.selectbox[0].options[0]
    assert "terreno de 10 x 20" in opcion and "versión 2" in opcion

    _boton(nuevo, "Abrir proyecto").click().run()

    assert not nuevo.exception
    assert _version(nuevo).startswith("Versión 2")
    _boton(nuevo, "Deshacer").click().run()
    assert _version(nuevo).startswith("Versión 1")


def test_borrar_un_proyecto_pide_confirmacion(entorno):
    from src.ui import almacen

    at = _con_plano()
    _boton(at, "Nuevo proyecto").click().run()

    _boton(at, "Borrar proyecto").click().run()
    assert len(almacen.listar()[0]) == 1
    _boton(at, "Cancelar").click().run()
    assert len(almacen.listar()[0]) == 1
    assert not [b for b in at.button if b.label == "Sí, borrar"]

    _boton(at, "Borrar proyecto").click().run()
    _boton(at, "Sí, borrar").click().run()

    assert not at.exception
    assert almacen.listar() == ([], 0)
    assert not at.selectbox


def test_si_no_se_puede_guardar_se_avisa_y_se_sigue(entorno):
    def fallar(proyecto):
        raise PermissionError("carpeta bloqueada")

    entorno.setattr("src.ui.almacen.guardar", fallar)
    at = _con_plano()

    assert not at.exception
    assert _version(at).startswith("Versión 1")
    assert any("No se pudo guardar" in w.value for w in at.warning)


def test_sin_autoguardado_no_hay_lista(entorno):
    entorno.setenv("AUTOGUARDADO", "0")
    at = _con_plano()
    _boton(at, "Nuevo proyecto").click().run()

    assert not at.selectbox
