"""Ventanas junto a la puerta de entrada y hacia patios."""

import pytest
from shapely.geometry import Point

from src.services.pipeline import construir_plano


def _ambiente(identificador, x, y, ancho, largo):
    nombre = identificador.rsplit("_", 1)[0]
    return {"id": identificador, "nombre": nombre, "x": x, "y": y,
            "ancho": ancho, "largo": largo}


def _de(aberturas, ambiente):
    return [a for a in aberturas if a["ambiente_a"] == ambiente]


@pytest.mark.parametrize("frente", [2.6, 3.0, 3.2, 3.8, 4.4, 6.0])
def test_la_sala_tiene_puerta_y_ventana_en_su_unica_fachada(frente, tmp_path):
    # La sala solo da a la calle: a los lados y detrás hay otros ambientes.
    plano = construir_plano([
        _ambiente("sala_1", 3, 0, frente, 4),
        _ambiente("estudio_1", 0, 0, 3, 4),
        _ambiente("comedor_1", 3 + frente, 0, 3, 4),
        _ambiente("cocina_1", 3, 4, frente, 3),
    ], 15, 10, tmp_path / "p.dxf")

    (puerta,) = [
        p for p in _de(plano.puertas["puertas"], "sala_1")
        if p["ambiente_b"] == "exterior"
    ]
    (ventana,) = _de(plano.ventanas["ventanas"], "sala_1")

    assert ventana["centro"][1] == puerta["centro"][1] == 0
    separacion = abs(ventana["centro"][0] - puerta["centro"][0])
    assert separacion >= (ventana["ancho"] + puerta["ancho"]) / 2 + 0.1
    extremo = abs(ventana["centro"][0] - (3 + frente / 2)) + ventana["ancho"] / 2
    assert extremo <= frente / 2 - 0.4 + 1e-3, "separada de las esquinas"
    assert ventana["ancho"] >= 0.5


def _anillo(hueco_ancho, hueco_largo):
    """Cuatro ambientes alrededor de un hueco central."""
    x1, y1 = 3 + hueco_ancho, 3 + hueco_largo
    return [
        _ambiente("sala_1", 0, 0, x1, 3),
        _ambiente("dormitorio_1", x1, 0, 3, y1),
        _ambiente("cocina_1", 3, y1, x1, 3),
        _ambiente("comedor_1", 0, 3, 3, y1),
    ]


@pytest.mark.parametrize("hueco, es_patio", [
    ((1.0, 1.0), False),   # un resto de la compactación
    ((6.0, 0.8), False),   # grande pero angosto
    ((3.0, 3.0), True),
])
def test_solo_los_patios_reciben_ventanas(hueco, es_patio, tmp_path):
    plano = construir_plano(_anillo(*hueco), 20, 20, tmp_path / "p.dxf")
    ancho, largo = hueco

    hacia_dentro = [
        v for v in plano.ventanas["ventanas"]
        if 3 - 0.01 <= Point(v["centro"]).x <= 3 + ancho + 0.01
        and 3 - 0.01 <= Point(v["centro"]).y <= 3 + largo + 0.01
    ]

    assert bool(hacia_dentro) is es_patio


def test_no_se_pone_una_segunda_ventana_hacia_una_ranura(tmp_path):
    # La sala tiene la calle delante y, a su derecha, otro ambiente a 1 m.
    plano = construir_plano([
        _ambiente("sala_1", 0, 0, 4, 4),
        _ambiente("cocina_1", 5, 0, 3, 4),
        _ambiente("comedor_1", 0, 4, 8, 3),
    ], 10, 10, tmp_path / "p.dxf")

    centros = [v["centro"] for v in _de(plano.ventanas["ventanas"], "sala_1")]

    assert centros
    assert all(x != 4 for x, _ in centros), centros
