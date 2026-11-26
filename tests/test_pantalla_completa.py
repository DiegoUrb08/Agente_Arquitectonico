"""Botón de pantalla completa de los visores 2D y 3D."""

from src.ui.escena_3d import documento_3d
from src.ui.pantalla_completa import BOTON, TEXTO_ENTRAR, TEXTO_SALIR, documento_svg


def test_el_boton_usa_la_api_de_pantalla_completa():
    assert "requestFullscreen" in BOTON and "exitFullscreen" in BOTON
    assert "fullscreenchange" in BOTON
    assert TEXTO_ENTRAR in BOTON and TEXTO_SALIR in BOTON


def test_el_boton_se_oculta_si_el_navegador_no_lo_admite():
    assert "hidden>" in BOTON
    assert "document.fullscreenEnabled" in BOTON


def test_visor_2d_con_boton_y_fondo_en_pantalla_completa():
    pagina = documento_svg("<svg></svg>")

    assert pagina.count('id="pantalla-completa"') == 1
    assert "<svg></svg>" in pagina
    assert "html:fullscreen" in pagina


def test_visor_3d_con_boton_junto_a_los_demas():
    pagina = documento_3d({"x": 1})

    assert pagina.count('id="pantalla-completa"') == 1
    assert "__PANTALLA_COMPLETA__" not in pagina
    botones = pagina[pagina.index('<div id="botones"'):pagina.index('<div id="ayuda"')]
    assert 'id="pantalla-completa"' in botones
