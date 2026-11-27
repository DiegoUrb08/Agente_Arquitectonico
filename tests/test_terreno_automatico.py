"""Terreno calculado desde el área de la vivienda: holgura y casa centrada."""

import tempfile
from pathlib import Path

import pytest

from src.models.defaults import (
    FACTOR_TERRENO_VIVIENDA,
    calcular_areas_predeterminadas,
    estimar_terreno_para_vivienda,
)
from src.models.requirements import Ambiente, RequerimientosArquitectonicos as Req
from src.services.pipeline import generar_plano

PROGRAMA = ["sala", "cocina", "dormitorio", "baño"]


def _plano(ambientes, area=40, terreno=None):
    datos = {
        "area_total_vivienda_m2": area,
        "numero_pisos": 1,
        "ambientes": [Ambiente(nombre=n) for n in ambientes],
    }
    if terreno:
        datos.update(ancho_terreno_m=terreno[0], largo_terreno_m=terreno[1])
    req = calcular_areas_predeterminadas(Req(**datos))
    plano = generar_plano(req, Path(tempfile.mkdtemp()) / "p.dxf")
    return req, plano


def _margenes(plano):
    x0, y0, x1, y1 = plano.geometrias["terreno"].bounds
    cajas = [a["poligono"].bounds for a in plano.geometrias["ambientes"]]
    vx0 = min(b[0] for b in cajas)
    vy0 = min(b[1] for b in cajas)
    vx1 = max(b[2] for b in cajas)
    vy1 = max(b[3] for b in cajas)
    return {
        "izquierda": vx0 - x0, "derecha": x1 - vx1,
        "frente": vy0 - y0, "fondo": y1 - vy1,
    }


def test_sin_terreno_se_calcula_un_lote_mayor_que_la_casa():
    req = estimar_terreno_para_vivienda(Req(area_total_vivienda_m2=40))

    assert req.terreno_estimado
    assert req.ancho_terreno_m * req.largo_terreno_m >= 40 * FACTOR_TERRENO_VIVIENDA - 1


def test_el_terreno_dado_por_el_usuario_no_se_cambia():
    req = estimar_terreno_para_vivienda(
        Req(area_total_vivienda_m2=40, ancho_terreno_m=8, largo_terreno_m=10)
    )

    assert not req.terreno_estimado
    assert (req.ancho_terreno_m, req.largo_terreno_m) == (8, 10)


def test_la_casa_queda_en_el_centro_del_lote(tmp_path):
    _, plano = _plano(PROGRAMA)

    margenes = _margenes(plano)

    assert abs(margenes["izquierda"] - margenes["derecha"]) <= 0.2
    assert abs(margenes["frente"] - margenes["fondo"]) <= 0.2
    assert min(margenes.values()) > 0.5, "hay jardín alrededor de la casa"


def test_con_garaje_la_casa_sigue_dando_a_la_calle():
    _, plano = _plano(["garaje"] + PROGRAMA)

    assert _margenes(plano)["frente"] == pytest.approx(0, abs=0.05)


def test_con_terreno_dado_la_casa_sigue_al_frente():
    _, plano = _plano(PROGRAMA, terreno=(10, 20))

    assert _margenes(plano)["frente"] == pytest.approx(0, abs=0.05)
