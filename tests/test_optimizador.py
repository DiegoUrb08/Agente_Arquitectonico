import itertools

import pytest
from shapely.geometry import box

from src.geometry.adjacency_validator import validar_distribucion
from src.models.defaults import calcular_areas_predeterminadas
from src.models.distribucion import validar_esquema_distribucion
from src.models.requirements import Ambiente, RequerimientosArquitectonicos
from src.planning.layout_optimizer import optimizar_distribucion


def _req(ambientes, relaciones=(), ancho=10, largo=20):
    req = RequerimientosArquitectonicos(
        area_total_vivienda_m2=100,
        ancho_terreno_m=ancho,
        largo_terreno_m=largo,
        ambientes=ambientes,
        relaciones_adyacencia=list(relaciones),
    )
    return calcular_areas_predeterminadas(req)


def _par_adyacente(distribucion, id_a, id_b):
    adyacentes = validar_distribucion(distribucion)["adyacencias"]
    return any({a["ambiente_a"], a["ambiente_b"]} == {id_a, id_b} for a in adyacentes)


def _comprobar_invariantes(dist, ancho, largo):
    validar_esquema_distribucion(dist)
    cajas = {a["id"]: box(a["x"], a["y"], a["x"] + a["ancho"], a["y"] + a["largo"]) for a in dist}
    for a in dist:
        assert a["x"] + a["ancho"] <= ancho + 1e-6
        assert a["y"] + a["largo"] <= largo + 1e-6
        assert a["area_m2"] == pytest.approx(a["ancho"] * a["largo"])
    for (_, c1), (_, c2) in itertools.combinations(cajas.items(), 2):
        assert c1.intersection(c2).area == pytest.approx(0, abs=1e-6)
    assert validar_distribucion(dist)["distribucion_conectada"] is True


def test_caso_simple_cumple_areas_exactas_y_relacion():
    dist = optimizar_distribucion(_req(
        [Ambiente(nombre="sala"), Ambiente(nombre="cocina"),
         Ambiente(nombre="dormitorio", cantidad=2), Ambiente(nombre="baño")],
        [["sala", "cocina"]],
    ))

    assert len(dist) == 5
    _comprobar_invariantes(dist, 10, 20)
    assert _par_adyacente(dist, "sala_1", "cocina_1")
    # Óptimo conocido de la fase 1: las áreas objetivo se alcanzan exactamente.
    assert sum(abs(a["area_m2"] - a["area_objetivo_m2"]) for a in dist) == pytest.approx(0, abs=0.01)


def test_caso_completo_con_relaciones_de_todos_los_modos():
    dist = optimizar_distribucion(_req(
        [Ambiente(nombre="sala"), Ambiente(nombre="comedor"), Ambiente(nombre="cocina"),
         Ambiente(nombre="dormitorio", cantidad=2), Ambiente(nombre="baño", cantidad=2),
         Ambiente(nombre="lavandería")],
        [
            {"ambiente_a": "sala", "ambiente_b": "comedor", "modo": "todos"},
            {"ambiente_a": "comedor", "ambiente_b": "cocina", "modo": "todos"},
            {"ambiente_a": "dormitorio", "ambiente_b": "baño", "modo": "al_menos_uno"},
        ],
    ))

    assert len(dist) == 8
    _comprobar_invariantes(dist, 10, 20)
    assert _par_adyacente(dist, "sala_1", "comedor_1")
    assert _par_adyacente(dist, "comedor_1", "cocina_1")
    assert any(
        _par_adyacente(dist, d, b)
        for d in ("dormitorio_1", "dormitorio_2")
        for b in ("bano_1", "bano_2")
    )
    # El óptimo de la fase 1 para este caso es 0.09 m² de desviación total.
    assert sum(abs(a["area_m2"] - a["area_objetivo_m2"]) for a in dist) == pytest.approx(0.09, abs=0.011)


def test_modo_correspondiente():
    dist = optimizar_distribucion(_req(
        [Ambiente(nombre="dormitorio", cantidad=2), Ambiente(nombre="baño", cantidad=2)],
        [{"ambiente_a": "dormitorio", "ambiente_b": "baño", "modo": "correspondiente"}],
    ))
    assert _par_adyacente(dist, "dormitorio_1", "bano_1")
    assert _par_adyacente(dist, "dormitorio_2", "bano_2")


@pytest.mark.parametrize("ancho, largo, mensaje", [
    (None, 20, "ancho y largo"),
    (0, 20, "mayores que cero"),
    (0.5, 20, "demasiado pequeño"),
])
def test_terreno_invalido(ancho, largo, mensaje):
    req = _req([Ambiente(nombre="sala")])
    req.ancho_terreno_m = ancho
    req.largo_terreno_m = largo
    with pytest.raises(ValueError, match=mensaje):
        optimizar_distribucion(req)


def test_area_minima_mayor_que_el_terreno():
    req = _req([Ambiente(nombre="sala", area_minima_m2=50)], ancho=5, largo=5)
    with pytest.raises(ValueError, match="necesitan al menos"):
        optimizar_distribucion(req)


def test_relacion_con_ambiente_inexistente():
    with pytest.raises(ValueError, match="No existe"):
        optimizar_distribucion(_req([Ambiente(nombre="sala")], [["sala", "garaje"]]))


def test_ambientes_no_caben_en_el_terreno():
    req = _req(
        [Ambiente(nombre="sala", area_minima_m2=8, cantidad=3)],
        ancho=4, largo=5,
    )
    with pytest.raises(ValueError, match="necesitan al menos"):
        optimizar_distribucion(req)


def test_vivienda_por_piso_mayor_que_el_terreno():
    req = _req([Ambiente(nombre="sala")], ancho=5, largo=5)
    req.numero_pisos = 2
    req.area_total_vivienda_m2 = 100
    with pytest.raises(ValueError, match="cada planta"):
        optimizar_distribucion(req)


def test_numero_de_pisos_invalido():
    req = _req([Ambiente(nombre="sala")])
    req.numero_pisos = 0
    with pytest.raises(ValueError, match="pisos"):
        optimizar_distribucion(req)


def test_ambiente_fuera_de_catalogo_se_rechaza():
    with pytest.raises(ValueError, match="catálogo"):
        optimizar_distribucion(_req([
            Ambiente(nombre="sala"),
            Ambiente(nombre="piscina"),
        ]))


def test_ambiente_fuera_de_catalogo_lista_todos_los_invalidos():
    with pytest.raises(ValueError, match="'jacuzzi'") as exc:
        optimizar_distribucion(_req([
            Ambiente(nombre="sala"),
            Ambiente(nombre="jacuzzi"),
            Ambiente(nombre="cancha"),
        ]))
    assert "cancha" in str(exc.value)


def test_garaje_esta_en_catalogo():
    dist = optimizar_distribucion(_req([
        Ambiente(nombre="sala"), Ambiente(nombre="garaje"),
    ]))
    assert any(a["id"].startswith("garaje") for a in dist)


def test_dormitorio_compuesto_esta_en_catalogo():
    dist = optimizar_distribucion(_req([
        Ambiente(nombre="sala"),
        Ambiente(nombre="dormitorio principal"),
    ]))
    assert any("dormitorio" in a["id"] for a in dist)
