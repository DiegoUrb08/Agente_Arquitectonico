import pytest

from src.cad.dxf_reader import analizar_dxf
from src.geometry.geometry_generator import generar_geometrias
from src.geometry.wall_generator import generar_muros
from src.geometry.window_generator import generar_ventanas_automaticas
from src.geometry.opening_generator import generar_aberturas
from src.services.pipeline import construir_plano

DISTRIBUCION = [
    {"id": "sala_1", "nombre": "Sala", "x": 0, "y": 0, "ancho": 5, "largo": 4},
    {"id": "cocina_1", "nombre": "Cocina", "x": 5, "y": 0, "ancho": 3, "largo": 4},
    {"id": "dormitorio_1", "nombre": "Dormitorio", "x": 0, "y": 4, "ancho": 4, "largo": 3.5},
    {"id": "bano_1", "nombre": "Baño", "x": 4, "y": 4, "ancho": 2, "largo": 3.5},
]


@pytest.fixture
def geo():
    return generar_geometrias(DISTRIBUCION, 8, 7.5)


def test_las_ventanas_solo_van_en_paredes_exteriores(geo):
    r = generar_ventanas_automaticas(geo)
    assert r["ventanas"]

    from shapely.geometry import Point
    from shapely.ops import unary_union
    perimetro = unary_union([a["poligono"] for a in geo["ambientes"]]).boundary

    for v in r["ventanas"]:
        assert Point(v["centro"]).distance(perimetro) < 1e-6


def test_cada_ambiente_exterior_recibe_ventana(geo):
    r = generar_ventanas_automaticas(geo)
    ambientes = {v["ambiente_a"] for v in r["ventanas"]}
    assert {"sala_1", "cocina_1", "dormitorio_1"} <= ambientes
    assert len([v for v in r["ventanas"] if v["ambiente_a"] == "sala_1"]) <= 2


def test_ancho_segun_tipo_y_limite_por_pared(geo):
    r = generar_ventanas_automaticas(geo)
    bano = [v for v in r["ventanas"] if v["ambiente_a"] == "bano_1"]
    assert all(v["ancho"] <= 0.6 for v in bano)
    for v in r["ventanas"]:
        assert 0.5 <= v["ancho"] <= 1.8


def test_ambiente_sin_tramo_exterior_util_se_reporta_como_omitido():
    pequeno = [{"id": "x_1", "nombre": "X", "x": 0, "y": 0, "ancho": 0.8, "largo": 0.8}]
    g = generar_geometrias(pequeno, 5, 5)
    assert generar_ventanas_automaticas(g)["omitidos"] == ["x_1"]


def test_no_tapa_puertas(geo):
    puerta = {"centro": (2.5, 0.0), "ancho": 0.9, "espesor_muro": 0.15, "orientacion": "horizontal"}
    sin = generar_ventanas_automaticas(geo)
    con = generar_ventanas_automaticas(geo, puertas={"puertas": [puerta]})
    assert len(con["ventanas"]) <= len(sin["ventanas"])
    for v in con["ventanas"]:
        if v["orientacion"] == "horizontal" and abs(v["centro"][1]) < 1e-6:
            assert abs(v["centro"][0] - 2.5) > v["ancho"] / 2 + 0.45 - 1e-6


def test_las_ventanas_caben_en_los_muros(geo):
    muros = generar_muros(geo["ambientes"], 0.20, 0.15)
    ventanas = generar_ventanas_automaticas(geo)["ventanas"]
    r = generar_aberturas(muros, ventanas)
    assert r["cantidad_ventanas"] == len(ventanas)


def test_pipeline_dibuja_ventanas(tmp_path):
    r = construir_plano(DISTRIBUCION, 8, 7.5, tmp_path / "p.dxf")
    assert r.aberturas["cantidad_ventanas"] > 0
    assert r.ventanas["ventanas"]
    assert "VENTANAS" in analizar_dxf(r.ruta_dxf.read_bytes())["capas"]


def test_tramos_sueltos_no_rompen_la_fusion():
    # Regresion: linemerge fallaba con tramos de una sola linea.
    from shapely.geometry import LineString, MultiLineString
    from src.geometry.window_generator import _fusionar_colineales, _tramos_rectos

    g = MultiLineString([
        LineString([(3, 9.8), (3, 6.6)]),
        LineString([(0, 0), (2, 0)]),
        LineString([(2, 0), (4, 0)]),
    ])
    tramos = _fusionar_colineales(_tramos_rectos(g))
    assert ("v", 3.0, 6.6, 9.8) in tramos
    assert ("h", 0.0, 0.0, 4.0) in tramos


def test_ventana_no_solapa_con_otra_abertura_cercana(geo):
    puerta = {"centro": (1.0, 0.0), "ancho": 0.9, "espesor_muro": 0.15, "orientacion": "horizontal"}
    r = generar_ventanas_automaticas(geo, puertas={"puertas": [puerta]})
    muros = generar_muros(geo["ambientes"], 0.20, 0.15)
    generar_aberturas(muros, [{**puerta, "tipo": "puerta"}] + r["ventanas"])
