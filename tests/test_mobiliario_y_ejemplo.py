"""Mobiliario en ambientes ajustados y el ejemplo que lo muestra todo."""

import pytest

from src.geometry.geometry_generator import generar_geometrias
from src.geometry.mobiliario_automatico import PLANTILLAS, amueblar_automaticamente
from src.planning.orientacion import detectar_norte
from src.planning.retiros import detectar_retiros
from src.ui.interfaz import EJEMPLOS


def _ambiente(identificador, ancho, largo):
    nombre = identificador.rsplit("_", 1)[0]
    return {"id": identificador, "nombre": nombre, "x": 0.0, "y": 0.0,
            "ancho": ancho, "largo": largo}


def _puerta(x, y, ancho=0.9, orientacion="horizontal", **extra):
    return {"centro": (x, y), "ancho": ancho, "orientacion": orientacion, **extra}


def _amueblar(ambiente, *puertas):
    geometrias = generar_geometrias([ambiente], 12, 12)
    return amueblar_automaticamente(geometrias, {"puertas": list(puertas)})


def _libre_el_barrido(resultado, puerta):
    cx, cy = puerta["centro"]
    medio = puerta["ancho"] / 2
    return not any(
        m["geometria"].intersection(
            _caja(cx - medio, cy - 2 * medio, cx + medio, cy + 2 * medio)
        ).area > 1e-6
        for m in resultado["mobiliario"]
    )


def _caja(*limites):
    from shapely.geometry import box

    return box(*limites)


@pytest.mark.parametrize("ancho, largo", [(2.4, 1.6), (1.8, 2.2), (2.9, 2.0)])
def test_el_bano_pequeno_queda_completo(ancho, largo):
    puerta = _puerta(ancho / 2, largo)

    resultado = _amueblar(_ambiente("bano_1", ancho, largo), puerta)

    assert resultado["omitidos"] == []
    assert len(resultado["mobiliario"]) == len(PLANTILLAS["bano"])
    assert _libre_el_barrido(resultado, puerta)


def test_la_mesa_se_corre_si_una_puerta_ocupa_el_centro():
    # Comedor angosto: las puertas de los lados llegan hasta el centro.
    puertas = [
        _puerta(0, 2.0, orientacion="vertical"),
        _puerta(2.4, 2.0, orientacion="vertical"),
    ]

    resultado = _amueblar(_ambiente("comedor_1", 2.4, 4.4), *puertas)

    assert resultado["omitidos"] == []
    (mesa,) = resultado["mobiliario"]
    assert not any(
        mesa["geometria"].intersects(_caja(x - 0.9, 1.55, x + 0.9, 2.45))
        for x in (0, 2.4)
    )


def test_el_porton_no_quita_muebles_al_ambiente_vecino():
    porton = _puerta(4.0, 0, ancho=2.4, vehicular=True)

    resultado = _amueblar(_ambiente("sala_1", 4.0, 1.2), porton)

    assert resultado["omitidos"] == []


def test_lo_que_no_cabe_se_informa():
    resultado = _amueblar(_ambiente("bano_1", 1.0, 1.0))

    assert resultado["omitidos"]


def test_el_ejemplo_completo_pide_todo():
    texto = EJEMPLOS["Proyecto completo"]

    for palabra in ("dos pisos", "garaje", "sala", "comedor", "cocina",
                    "lavandería", "estudio", "dormitorios", "baños"):
        assert palabra in texto
    assert detectar_norte(texto) == "derecha"
    assert detectar_retiros(texto).frontal == 3
