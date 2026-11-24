import ezdxf

from src.cad.dxf_generator import generar_dxf_desde_geometrias
from src.cad.dxf_reader import analizar_dxf
from src.geometry.adjacency_validator import validar_distribucion
from src.geometry.door_generator import generar_puertas_automaticas
from src.geometry.geometry_generator import generar_geometrias
from src.geometry.opening_generator import generar_aberturas
from src.geometry.wall_generator import generar_muros


def test_generar_geometrias_areas(distribucion_simple):
    r = generar_geometrias(distribucion_simple, 10, 10)
    assert r["valido"] is True
    assert r["errores"] == []
    assert [a["area_m2"] for a in r["ambientes"]] == [20.0, 12.0]


def test_generar_geometrias_detecta_ambiente_fuera_del_terreno(distribucion_simple):
    r = generar_geometrias(distribucion_simple, 6, 10)
    assert r["valido"] is False
    assert r["errores"]


def test_adyacencia_detectada(distribucion_simple):
    r = validar_distribucion(distribucion_simple)
    assert r["cantidad_adyacencias"] == 1
    assert r["distribucion_conectada"] is True
    assert r["adyacencias"][0]["longitud_m"] == 4.0


def test_ambiente_aislado_rompe_conectividad(distribucion_simple):
    lejano = {"id": "bano_1", "nombre": "Baño", "x": 8, "y": 6, "ancho": 2, "largo": 2}
    r = validar_distribucion(distribucion_simple + [lejano])
    assert r["distribucion_conectada"] is False
    assert "bano_1" in r["ambientes_aislados"]


def test_puerta_automatica_en_pared_compartida(distribucion_simple):
    r = generar_puertas_automaticas(distribucion_simple)
    assert r["cantidad_puertas"] == 1
    assert r["puertas"][0]["centro"] == (5.0, 2.0)


def test_pipeline_completo_genera_dxf_legible(distribucion_simple, tmp_path):
    geo = generar_geometrias(distribucion_simple, 10, 10)
    muros = generar_muros(geo["ambientes"])
    assert muros["area_muros_m2"] > 0
    puertas = generar_puertas_automaticas(distribucion_simple)["puertas"]
    aberturas = generar_aberturas(muros, puertas)
    assert aberturas["cantidad_puertas"] == 1

    ruta = tmp_path / "plano.dxf"
    generar_dxf_desde_geometrias(
        geo, 10, 10, str(ruta),
        resultado_muros=muros, resultado_aberturas=aberturas,
    )
    assert ruta.exists()
    ezdxf.readfile(str(ruta))  # el DXF debe ser válido

    info = analizar_dxf(ruta.read_bytes())
    assert info["total_entidades"] > 0
    assert "MUROS" in info["capas"]
    assert "AMBIENTES" in info["capas"]
