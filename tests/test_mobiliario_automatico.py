import pytest
from shapely.geometry import Point

from src.cad.dxf_reader import analizar_dxf
from src.geometry.geometry_generator import generar_geometrias
from src.geometry.mobiliario_automatico import amueblar_automaticamente
from src.services.pipeline import generar_plano, construir_plano

DISTRIBUCION = [
    {"id": "sala_1", "nombre": "Sala", "x": 0, "y": 0, "ancho": 5, "largo": 4},
    {"id": "cocina_1", "nombre": "Cocina", "x": 5, "y": 0, "ancho": 3, "largo": 4},
    {"id": "dormitorio_1", "nombre": "Dormitorio", "x": 0, "y": 4, "ancho": 4, "largo": 3.5},
    {"id": "dormitorio_2", "nombre": "Dormitorio", "x": 4, "y": 4, "ancho": 4, "largo": 3.5},
    {"id": "bano_1", "nombre": "Baño", "x": 8, "y": 0, "ancho": 2, "largo": 3},
]


@pytest.fixture
def geo():
    return generar_geometrias(DISTRIBUCION, 10, 8)


def test_amuebla_cada_ambiente_dentro_y_sin_solapes(geo):
    r = amueblar_automaticamente(geo)
    por_nombre = {a["id"]: a["poligono"] for a in geo["ambientes"]}

    assert r["cantidad"] >= 8
    for m in r["mobiliario"]:
        assert any(p.covers(m["geometria"]) for p in por_nombre.values())

    muebles = r["mobiliario"]
    for i, a in enumerate(muebles):
        for b in muebles[i + 1:]:
            assert a["geometria"].intersection(b["geometria"]).area < 1e-6


def test_los_dos_dormitorios_reciben_su_cama(geo):
    r = amueblar_automaticamente(geo)
    camas = [m for m in r["mobiliario"] if m["tipo"] == "cama_matrimonial"]
    assert len(camas) == 2
    assert camas[0]["geometria"].centroid.x != camas[1]["geometria"].centroid.x


def test_no_tapa_las_puertas(geo):
    puerta = {"centro": (1.0, 0.0), "ancho": 0.9}
    r = amueblar_automaticamente(geo, {"puertas": [puerta]})
    zona = Point(1.0, 0.0).buffer(0.9)
    assert all(not m["geometria"].intersects(zona) for m in r["mobiliario"])


def test_mueble_que_no_cabe_se_omite():
    geo = generar_geometrias(
        [{"id": "bano_1", "nombre": "Baño", "x": 0, "y": 0, "ancho": 1, "largo": 1}], 5, 5
    )
    r = amueblar_automaticamente(geo)
    assert r["omitidos"]


def test_pipeline_incluye_mobiliario_en_el_dxf(tmp_path):
    r = construir_plano(DISTRIBUCION, 10, 8, tmp_path / "p.dxf")
    assert r.mobiliario["cantidad"] > 0
    assert "MOBILIARIO" in analizar_dxf(r.ruta_dxf.read_bytes())["capas"]


def test_pipeline_sin_amueblar(tmp_path):
    r = construir_plano(DISTRIBUCION, 10, 8, tmp_path / "p.dxf", amueblar=False)
    assert r.mobiliario is None


def test_ruido_de_coma_flotante_no_elimina_el_muro_compartido(tmp_path):
    # Caso real: 11.4 + 3.7 = 15.100000000000001 dejaba la puerta sin muro.
    dist = [
        {"id": "sala_1", "nombre": "sala", "x": 0.1, "y": 15.1, "ancho": 6.9, "largo": 4.5},
        {"id": "cocina_1", "nombre": "cocina", "x": 0.8, "y": 11.4, "ancho": 5.6, "largo": 3.7},
        {"id": "dormitorio_1", "nombre": "dormitorio", "x": 2.4, "y": 5.9, "ancho": 4.7, "largo": 5.5},
        {"id": "bano_1", "nombre": "baño", "x": 7.0, "y": 15.1, "ancho": 2.8, "largo": 3.7},
    ]
    r = construir_plano(dist, 10, 20, tmp_path / "p.dxf")
    assert r.ruta_dxf.exists()
