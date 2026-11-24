import pytest

from src.models.requirements import Ambiente, RequerimientosArquitectonicos
from src.models.defaults import calcular_areas_predeterminadas
from src.planning.space_graph import (
    construir_grafo,
    interpretar_relacion,
    normalizar_nombre,
)


def test_normalizar_nombre_quita_tildes_y_mayusculas():
    assert normalizar_nombre("  LavanderÍa ") == "lavanderia"
    assert normalizar_nombre("Baño") == "bano"


def test_interpretar_relacion_formato_lista_y_dict():
    assert interpretar_relacion(["Sala", "Comedor"]) == ("sala", "comedor", "todos")
    rel = {"ambiente_a": "Baño", "ambiente_b": "Dormitorio", "modo": "al_menos_uno"}
    assert interpretar_relacion(rel) == ("bano", "dormitorio", "al_menos_uno")


def test_interpretar_relacion_invalida():
    with pytest.raises(ValueError):
        interpretar_relacion(["solo_uno"])
    with pytest.raises(ValueError):
        interpretar_relacion({"ambiente_a": "a", "ambiente_b": "b", "modo": "x"})


def test_construir_grafo_crea_nodos_y_pares():
    req = RequerimientosArquitectonicos(
        ambientes=[
            Ambiente(nombre="dormitorio", cantidad=2),
            Ambiente(nombre="baño", cantidad=2),
        ],
        relaciones_adyacencia=[
            {"ambiente_a": "dormitorio", "ambiente_b": "baño", "modo": "correspondiente"}
        ],
    )
    grafo = construir_grafo(req)
    assert [n["id"] for n in grafo["nodos"]] == [
        "dormitorio_1", "dormitorio_2", "bano_1", "bano_2",
    ]
    assert grafo["relaciones"][0]["pares"] == [
        ["dormitorio_1", "bano_1"],
        ["dormitorio_2", "bano_2"],
    ]


def test_construir_grafo_rechaza_ambiente_inexistente_y_vacio():
    req = RequerimientosArquitectonicos(
        ambientes=[Ambiente(nombre="sala")],
        relaciones_adyacencia=[["sala", "cocina"]],
    )
    with pytest.raises(ValueError):
        construir_grafo(req)
    with pytest.raises(ValueError):
        construir_grafo(RequerimientosArquitectonicos())


def test_areas_predeterminadas_asignan_area_objetivo():
    req = RequerimientosArquitectonicos(
        area_total_vivienda_m2=100,
        ambientes=[
            Ambiente(nombre="sala"),
            Ambiente(nombre="cocina"),
            Ambiente(nombre="dormitorio", cantidad=2),
            Ambiente(nombre="baño"),
        ],
    )
    resultado = calcular_areas_predeterminadas(req)
    assert all(a.area_objetivo_m2 and a.area_objetivo_m2 > 0 for a in resultado.ambientes)
    total = sum(a.area_objetivo_m2 * a.cantidad for a in resultado.ambientes)
    assert total <= 100
