"""Sillas, mesa de centro y auto."""

import ezdxf
import pytest

from src.bim.ifc import generar_ifc
from src.services.pipeline import construir_plano
from src.ui.escena_3d import generar_escena_3d
from src.ui.plano_svg import generar_svg_plano


def _ambiente(identificador, x, y, ancho, largo):
    nombre = identificador.rsplit("_", 1)[0]
    return {"id": identificador, "nombre": nombre, "x": x, "y": y,
            "ancho": ancho, "largo": largo}


CASA = [
    _ambiente("sala_1", 0, 0, 5, 4),
    _ambiente("garaje_1", 5, 0, 3, 5.5),
    _ambiente("comedor_1", 0, 4, 5, 4),
]


@pytest.fixture(scope="module")
def plano(tmp_path_factory):
    return construir_plano(
        CASA, 10, 15, tmp_path_factory.mktemp("mob") / "p.dxf"
    )


def _de(plano, tipo):
    return [m for m in plano.mobiliario["mobiliario"] if m["tipo"] == tipo]


def test_se_completan_sala_comedor_y_garaje(plano):
    assert len(_de(plano, "silla")) >= 2
    assert len(_de(plano, "mesa_centro")) == 1
    (auto,) = _de(plano, "auto")
    assert 5 < auto["x"] and auto["x"] + auto["ancho"] < 8
    assert plano.mobiliario["omitidos"] == []


def test_los_muebles_no_se_superponen(plano):
    muebles = plano.mobiliario["mobiliario"]

    for i, a in enumerate(muebles):
        for b in muebles[i + 1:]:
            assert a["geometria"].intersection(b["geometria"]).area < 1e-6


def test_se_dibujan_en_todas_las_salidas(plano):
    modelo = ezdxf.readfile(plano.ruta_dxf).modelspace()
    sillas = [
        e for e in modelo.query("INSERT") if "SILLA" in e.dxf.name
    ]
    assert {e.dxf.rotation % 180 for e in sillas} <= {0, 90}
    assert any("AUTO" in e.dxf.name for e in modelo.query("INSERT"))
    assert 'rx="0.45"' in generar_svg_plano(plano, {"muebles"})
    assert generar_escena_3d(plano, {"muebles"}, detalle=True)
    assert b"Auto" not in generar_ifc(plano)
