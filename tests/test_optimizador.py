from src.geometry.adjacency_validator import validar_distribucion
from src.models.defaults import calcular_areas_predeterminadas
from src.models.requirements import Ambiente, RequerimientosArquitectonicos
from src.planning.layout_optimizer import optimizar_distribucion


def test_optimizador_humo_vivienda_pequena():
    req = RequerimientosArquitectonicos(
        area_total_vivienda_m2=100,
        ancho_terreno_m=10,
        largo_terreno_m=20,
        ambientes=[
            Ambiente(nombre="sala"),
            Ambiente(nombre="cocina"),
            Ambiente(nombre="dormitorio", cantidad=2),
            Ambiente(nombre="baño"),
        ],
        relaciones_adyacencia=[["sala", "cocina"]],
    )
    req = calcular_areas_predeterminadas(req)
    dist = optimizar_distribucion(req)

    assert len(dist) == 5
    for a in dist:
        assert a["ancho"] > 0 and a["largo"] > 0
        assert a["x"] >= 0 and a["y"] >= 0
        assert a["x"] + a["ancho"] <= 10 + 1e-6
        assert a["y"] + a["largo"] <= 20 + 1e-6
    assert validar_distribucion(dist)["distribucion_conectada"] is True
