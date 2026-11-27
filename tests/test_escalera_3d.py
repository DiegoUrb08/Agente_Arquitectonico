"""Trazado 3D de la escalera: cabe, deja paso ante las puertas y sube."""

import pytest
from shapely.affinity import rotate
from shapely.geometry import box

from src.ui.escalera_3d import trazar_escalera, zona_libre

SUBE = 2.8


def _puerta(cx, cy, orientacion, ancho=0.9):
    return {"centro": (cx, cy), "ancho": ancho, "orientacion": orientacion}


def _huella(pieza):
    caja = box(pieza["x0"], pieza["y0"], pieza["x1"], pieza["y1"])
    if pieza.get("giro"):
        caja = rotate(caja, pieza["giro"], origin="centroid", use_radians=True)
    return caja


def _peldanos(trazado):
    return [p for p in trazado["piezas"] if p["material"] == "madera"]


CASOS = {
    # Caja típica del optimizador, puertas en la misma pared.
    "recta": (box(9.9, 3.1, 11.7, 7.4),
              [_puerta(9.9, 4.95, "vertical")], [_puerta(9.9, 6.75, "vertical")]),
    # Más ancha que larga: cabe en U o en L.
    "ancha": (box(0, 0, 3.5, 2.5),
              [_puerta(0, 0.8, "vertical")], [_puerta(3.5, 0.8, "vertical")]),
    # Casi cuadrada: caracol.
    "cuadrada": (box(0, 0, 2.2, 2.2),
                 [_puerta(1.1, 0, "horizontal")], [_puerta(0, 1.1, "vertical")]),
    # Demasiado pequeña: se comprime, pero no se sale.
    "pequena": (box(0, 0, 2.5, 1.5),
                [_puerta(0.6, 0, "horizontal")], [_puerta(0.6, 1.5, "horizontal")]),
}


@pytest.mark.parametrize("caso", CASOS)
def test_todas_las_piezas_quedan_dentro_del_ambiente(caso):
    poligono, baja, alta = CASOS[caso]

    trazado = trazar_escalera(poligono, baja, alta, SUBE)

    holgado = poligono.buffer(0.02)
    for pieza in _peldanos(trazado):
        assert holgado.covers(_huella(pieza)), pieza


@pytest.mark.parametrize("caso", CASOS)
def test_los_peldanos_suben_de_una_contrahuella(caso):
    poligono, baja, alta = CASOS[caso]

    peldanos = _peldanos(trazar_escalera(poligono, baja, alta, SUBE))
    altos = [p["h1"] for p in peldanos]

    assert altos == sorted(altos)
    assert altos[-1] < SUBE and altos[-1] == pytest.approx(SUBE, abs=0.2)
    assert all(p["h1"] - p["h0"] <= 0.2 for p in peldanos), "no son bloques macizos"


@pytest.mark.parametrize("caso", ["recta", "ancha"])
def test_con_sitio_deja_paso_y_une_las_dos_puertas(caso):
    poligono, baja, alta = CASOS[caso]

    trazado = trazar_escalera(poligono, baja, alta, SUBE)

    assert trazado["paso_libre"]
    assert trazado["arranca_en_puerta"]
    assert trazado["llega_a_puerta"]
    zona = zona_libre(baja[0], poligono)
    for pieza in _peldanos(trazado):
        if pieza["h0"] < 2.0:
            assert _huella(pieza).intersection(zona).area < 0.01


def test_la_cuadrada_es_de_caracol_y_gira():
    poligono, baja, alta = CASOS["cuadrada"]

    trazado = trazar_escalera(poligono, baja, alta, SUBE)

    assert trazado["tipo"] == "caracol"
    assert sum(1 for p in _peldanos(trazado) if p.get("giro")) >= 10


def test_el_hueco_no_incluye_el_desembarco():
    poligono, baja, alta = CASOS["recta"]

    trazado = trazar_escalera(poligono, baja, alta, SUBE)

    assert trazado["hueco"].area > 1.0
    assert trazado["hueco"].intersection(trazado["desembarco"]).area < 1e-6


def test_sin_puertas_tambien_traza_una_escalera():
    trazado = trazar_escalera(box(0, 0, 4.5, 1.2), (), (), SUBE)

    assert len(_peldanos(trazado)) >= 10
