"""Vista previa SVG del plano (función pura)."""

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from src.ai.providers.mock_provider import MockProvider
from src.models.requirements import RequerimientosArquitectonicos
from src.services.pipeline import generar_plano
from src.ui.plano_svg import CAPAS_POR_DEFECTO, color_de_ambiente, generar_svg_plano

NS = {"s": "http://www.w3.org/2000/svg"}


@pytest.fixture(scope="module")
def resultado(tmp_path_factory):
    contenido = MockProvider().chat(messages=[{"role": "user", "content": "terreno"}])
    datos = json.loads(contenido["message"]["content"])
    ruta = tmp_path_factory.mktemp("svg") / "plano.dxf"
    return generar_plano(RequerimientosArquitectonicos(**datos), ruta)


def _raiz(svg: str):
    return ET.fromstring(svg)


def _contar(svg: str, clase: str) -> int:
    return len(_raiz(svg).findall(f".//s:rect[@class='{clase}']", NS))


def test_es_un_svg_valido(resultado):
    raiz = _raiz(generar_svg_plano(resultado))

    assert raiz.tag.endswith("svg")
    assert raiz.get("viewBox")


def test_dibuja_una_habitacion_por_ambiente(resultado):
    raiz = _raiz(generar_svg_plano(resultado))

    habitaciones = raiz.findall(".//s:g[@class='amb']", NS)

    assert len(habitaciones) == len(resultado.distribucion)


def test_muestra_nombres_y_areas(resultado):
    svg = generar_svg_plano(resultado)

    for ambiente in resultado.distribucion:
        assert f"{ambiente['area_m2']:.1f} m²" in svg
    assert "Sala" in svg and "Baño" in svg


def test_numera_solo_los_ambientes_repetidos(resultado):
    svg = generar_svg_plano(resultado)

    assert "Dormitorio 1" in svg and "Dormitorio 2" in svg
    assert "Sala 1" not in svg


def test_el_eje_y_se_invierte_como_en_el_dxf(resultado):
    """El origen del DXF (abajo a la izquierda) queda abajo en el SVG."""
    raiz = _raiz(generar_svg_plano(resultado))
    _, miny, _, maxy = resultado.geometrias["terreno"].bounds
    rects = raiz.findall(".//s:g[@class='amb']/s:rect", NS)

    for ambiente, rect in zip(resultado.distribucion, rects):
        y_esperada = maxy - (ambiente["y"] + ambiente["largo"])
        assert float(rect.get("y")) == pytest.approx(y_esperada, abs=1e-3)

    inferior = min(resultado.distribucion, key=lambda a: a["y"])
    superior = max(resultado.distribucion, key=lambda a: a["y"])
    if inferior is not superior:
        y_de = lambda a: float(rects[resultado.distribucion.index(a)].get("y"))
        assert y_de(inferior) > y_de(superior)


def test_dibuja_todas_las_puertas_y_ventanas(resultado):
    svg = generar_svg_plano(resultado)

    assert _contar(svg, "puerta") == len(resultado.puertas["puertas"])
    assert _contar(svg, "ventana") == len(resultado.ventanas["ventanas"])


@pytest.mark.parametrize("capa, clase", [
    ("puertas", "puerta"),
    ("ventanas", "ventana"),
    ("muebles", "mueble"),
])
def test_las_capas_se_pueden_apagar(resultado, capa, clase):
    con = generar_svg_plano(resultado, capas=CAPAS_POR_DEFECTO)
    sin = generar_svg_plano(resultado, capas=CAPAS_POR_DEFECTO - {capa})

    assert _contar(con, clase) > 0
    assert _contar(sin, clase) == 0


def test_sin_etiquetas_ni_cotas_no_hay_texto(resultado):
    svg = generar_svg_plano(resultado, capas=frozenset())

    assert "<text" not in svg


def test_las_cotas_muestran_las_dimensiones_del_terreno(resultado):
    minx, miny, maxx, maxy = resultado.geometrias["terreno"].bounds
    svg = generar_svg_plano(resultado)

    assert f"{maxx - minx:.2f} m" in svg
    assert f"{maxy - miny:.2f} m" in svg


def test_dibuja_los_muros(resultado):
    raiz = _raiz(generar_svg_plano(resultado))

    muros = [p for p in raiz.findall(".//s:path", NS) if p.get("fill-rule") == "evenodd"]

    assert len(muros) == 1 and muros[0].get("d").startswith("M")


def test_funciona_sin_ventanas_ni_mobiliario(resultado):
    from dataclasses import replace

    pelado = replace(resultado, ventanas=None, mobiliario=None)

    raiz = _raiz(generar_svg_plano(pelado))

    assert raiz.tag.endswith("svg")


@pytest.mark.parametrize("nombre, esperado", [
    ("sala", "#38BDF8"),
    ("Baño", "#34D399"),
    ("dormitorio principal", "#A78BFA"),
    ("cuarto raro", "#7DD3FC"),
])
def test_color_por_tipo_de_ambiente(nombre, esperado):
    assert color_de_ambiente(nombre) == esperado


def test_escapa_el_texto_para_no_inyectar_html(resultado):
    """El SVG se incrusta en un iframe con acceso al origen de la app."""
    from dataclasses import replace

    hostil = [
        {**a, "nombre": "<script>alert(1)</script>", "id": f"<img onerror=x>_{i}"}
        for i, a in enumerate(resultado.distribucion)
    ]

    svg = generar_svg_plano(replace(resultado, distribucion=hostil))

    assert "<script>" not in svg
    assert "<img" not in svg
    assert "&lt;script&gt;" in svg
    ET.fromstring(svg)


def test_ocupar_contenedor_usa_alto_completo(resultado):
    normal = _raiz(generar_svg_plano(resultado))
    lleno = _raiz(generar_svg_plano(resultado, ocupar_contenedor=True))

    assert normal.get("height") is None
    assert lleno.get("height") == "100%"


def test_proporcion_de_la_vista_coincide_con_el_viewbox(resultado):
    _, _, ancho, alto = (float(v) for v in _raiz(generar_svg_plano(resultado)).get("viewBox").split())

    from src.ui.plano_svg import proporcion_vista

    assert proporcion_vista(resultado) == pytest.approx(alto / ancho, rel=1e-3)
