"""Los resultados de la UI persisten entre interacciones y se muestran por pestañas."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

RAIZ = Path(__file__).resolve().parent.parent
PESTANAS = ["Plano", "Ambientes", "Conectividad", "Puertas", "Requerimientos"]


@pytest.fixture(scope="module")
def app_con_plano():
    """App con proveedor mock y un plano ya generado (se genera una sola vez)."""
    import os

    anterior = os.environ.get("LLM_PROVIDER")
    os.environ["LLM_PROVIDER"] = "mock"
    try:
        at = AppTest.from_file(str(RAIZ / "app.py"), default_timeout=90).run()
        at.text_area[0].input("Casa en un terreno de 10 x 20 m con sala y cocina")
        at.button[0].click().run()
        yield at
    finally:
        if anterior is None:
            os.environ.pop("LLM_PROVIDER", None)
        else:
            os.environ["LLM_PROVIDER"] = anterior


def test_generar_muestra_tarjetas_y_pestanas(app_con_plano):
    at = app_con_plano

    assert not at.exception
    assert [t.label for t in at.tabs] == PESTANAS
    etiquetas = [m.label for m in at.metric]
    for esperada in ("Terreno", "Ambientes", "Superficie construida", "Ambientes conectados"):
        assert esperada in etiquetas


def test_el_resultado_sobrevive_a_otra_interaccion(app_con_plano):
    """Antes, pulsar 'Descargar' (o cualquier widget) borraba el plano."""
    at = app_con_plano

    at.run()

    assert not at.exception
    assert [t.label for t in at.tabs] == PESTANAS
    assert at.success


def test_una_nueva_generacion_vacia_reemplaza_al_resultado_anterior(app_con_plano):
    at = app_con_plano
    at.text_area[0].input("   ")
    at.button[0].click().run()

    assert [w.value for w in at.warning if "descripción" in w.value]
    assert "generado" not in at.session_state
