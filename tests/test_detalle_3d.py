"""Modo «detalle alto» de la vista 3D: decoración, arquitectura y acabados."""

import pytest
from shapely.geometry import Point, box
from shapely.ops import unary_union

from src.geometry.opening_generator import construir_abertura
from src.ui import detalle_3d
from src.ui.escena_3d import generar_escena_3d, ubicar_mueble
from src.ui.plano_svg import CAPAS_POR_DEFECTO
from tests.plano_fijo import generar_plano_fijo

DECORATIVOS = {"alfombra", "luz", "maceta", "planta", "espejo", "pantalla", "toalla"}


@pytest.fixture(scope="module")
def plano(tmp_path_factory):
    return generar_plano_fijo(None, tmp_path_factory.mktemp("detalle") / "p.dxf")


@pytest.fixture(scope="module")
def muebles(plano):
    ambientes = plano.geometrias["ambientes"]
    return [ubicar_mueble(m, ambientes) for m in plano.mobiliario["mobiliario"]]


@pytest.fixture(scope="module")
def decoracion(plano, muebles):
    return detalle_3d.decoracion(plano, muebles)


def _caja(p):
    return box(p["x0"], p["y0"], p["x1"], p["y1"])


def test_sin_detalle_la_escena_no_cambia(plano):
    assert generar_escena_3d(plano) == generar_escena_3d(plano, detalle=False)
    assert "detalle" not in generar_escena_3d(plano)


def test_la_decoracion_queda_dentro_de_un_ambiente(plano, decoracion):
    ambientes = [a["poligono"].buffer(1e-6) for a in plano.geometrias["ambientes"]]

    assert decoracion
    for pieza in decoracion:
        assert any(a.covers(_caja(pieza)) for a in ambientes), pieza


def test_la_decoracion_no_choca_con_muebles_ni_puertas(plano, muebles, decoracion):
    ocupado = unary_union([box(*m["caja"]) for m in muebles])
    barridos = unary_union([
        Point(*p["centro"]).buffer(p["ancho"]) for p in plano.puertas["puertas"]
    ])

    for pieza in decoracion:
        if pieza["material"] == "alfombra" or pieza["h0"] >= 1.0:
            continue  # va debajo de los muebles o colgada en la pared
        huella = _caja(pieza)
        assert huella.intersection(ocupado).area < 1e-6, pieza
        assert not huella.intersects(barridos), pieza


def test_veladores_a_los_lados_de_la_cama(plano):
    dormitorio = next(a for a in plano.geometrias["ambientes"] if a["id"] == "dormitorio_1")
    cama = {"tipo": "cama_matrimonial", "caja": (1.3, 5.05, 2.7, 6.95), "lado": "n",
            "ambiente": dormitorio}

    piezas = detalle_3d.decoracion(plano, [cama])

    luces = [_caja(p).centroid.x for p in piezas if p["material"] == "luz"]
    assert len(luces) == 2
    assert min(luces) < 1.3 < 2.7 < max(luces)


def test_sin_sitio_no_se_fuerza_el_velador(muebles, decoracion):
    """En el plano fijo las camas quedan entre pared, armario y puerta."""
    for cama in (m for m in muebles if m["tipo"].startswith("cama")):
        lado = box(*cama["caja"])
        assert all(_caja(p).intersection(lado).area < 1e-6 for p in decoracion
                   if p["material"] != "alfombra")


def test_las_sillas_rodean_la_mesa(plano):
    mesa = {"tipo": "mesa_comedor", "caja": (6.3, 1.6, 7.7, 2.4), "lado": "s",
            "ambiente": next(a for a in plano.geometrias["ambientes"]
                             if a["id"] == "cocina_1")}

    piezas = detalle_3d.decoracion(plano, [mesa])

    asientos = [p for p in piezas if p["h0"] == 0.43]
    centro = box(*mesa["caja"]).centroid
    lados = {
        ("s" if _caja(p).centroid.y < centro.y else "n")
        if abs(_caja(p).centroid.x - centro.x) < 0.7 else "e/o"
        for p in asientos
    }
    assert len(asientos) >= 4
    assert {"s", "n"} <= lados


def test_apagar_muebles_quita_la_decoracion(plano):
    escena = generar_escena_3d(plano, CAPAS_POR_DEFECTO - {"muebles"}, detalle=True)

    assert not {p["material"] for p in escena["piezas"]} & DECORATIVOS


def test_marco_por_cada_puerta_y_ventana(plano):
    escena = generar_escena_3d(plano, detalle=True)
    marcos = [_caja(p) for p in escena["piezas"] if p["material"] == "marco"]

    for abertura in plano.puertas["puertas"] + plano.ventanas["ventanas"]:
        hueco = construir_abertura(
            tuple(abertura["centro"]), abertura["ancho"],
            abertura["espesor_muro"], abertura["orientacion"],
        )
        assert sum(m.intersects(hueco) for m in marcos) >= 3, abertura["centro"]


def test_manijas_en_las_hojas(plano):
    escena = generar_escena_3d(plano, detalle=True)
    manijas = [p for p in escena["piezas"]
               if p["material"] == "metal" and p["h0"] == 0.95]

    assert len(manijas) == len(plano.puertas["puertas"])


def test_los_zocalos_se_cortan_en_las_puertas(plano):
    zocalos = unary_union([
        box(*_anillo_bounds(z)) for z in detalle_3d.zocalos(plano)
    ])
    assert not zocalos.is_empty
    for puerta in plano.puertas["puertas"]:
        hueco = construir_abertura(
            tuple(puerta["centro"]), puerta["ancho"],
            puerta["espesor_muro"], puerta["orientacion"],
        )
        assert zocalos.intersection(hueco).area < 1e-6


def _anillo_bounds(prisma):
    xs = [x for x, _ in prisma["anillos"][0]]
    ys = [y for _, y in prisma["anillos"][0]]
    return min(xs), min(ys), max(xs), max(ys)


def test_escalon_frente_a_la_puerta_exterior(plano):
    exterior = next(p for p in plano.puertas["puertas"] if p["ambiente_b"] == "exterior")
    vivienda = unary_union([a["poligono"] for a in plano.geometrias["ambientes"]])

    (escalon, *_) = detalle_3d.entrada(plano)

    assert escalon["material"] == "cemento" and escalon["h1"] == pytest.approx(0.12)
    assert _caja(escalon).distance(Point(*exterior["centro"])) < 0.2
    assert _caja(escalon).intersection(vivienda).area < 1e-6


@pytest.mark.parametrize("identificador, acabado", [
    ("sala_1", "madera"), ("dormitorio_2", "madera"), ("bano_1", "ceramica"),
    ("cocina_1", "ceramica"), ("garaje_1", "cemento"), ("raro_1", "madera"),
])
def test_acabados_por_tipo(identificador, acabado):
    assert detalle_3d.acabado_de(identificador) == acabado


def test_la_escena_detallada_lleva_acabados_y_cesped(plano):
    escena = generar_escena_3d(plano, detalle=True)

    assert escena["detalle"] is True and escena["terreno_acabado"] == "cesped"
    assert {p["id"]: p["acabado"] for p in escena["pisos"]}["bano_1"] == "ceramica"
    assert escena["prismas"]


def test_el_sofa_da_la_espalda_por_su_lado_largo():
    from src.ui.escena_3d import lado_de_pared

    habitacion = box(0, 0, 4, 5)
    # Sofá de 2 x 0,9 arrimado de costado a la pared oeste.
    assert lado_de_pared((0.05, 1.05, 2.05, 1.95), habitacion, "sofa") == "s"
    assert lado_de_pared((0.05, 1.05, 2.05, 1.95), habitacion) == "o"
    # La cama apoya el cabecero (lado corto).
    assert lado_de_pared((1.0, 3.05, 2.4, 4.95), habitacion, "cama_matrimonial") == "n"
