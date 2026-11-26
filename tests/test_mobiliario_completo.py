"""Todo ambiente con espacio recibe sus muebles y complementos."""

from collections import Counter

import pytest
from shapely.geometry import box

from src.geometry.geometry_generator import generar_geometrias
from src.geometry.mobiliario_automatico import PLANTILLAS, amueblar_automaticamente
from src.ui.escena_3d import _destino_de


def _ambiente(identificador, ancho, largo):
    nombre = identificador.rsplit("_", 1)[0]
    return {"id": identificador, "nombre": nombre, "x": 0.0, "y": 0.0,
            "ancho": ancho, "largo": largo}


def _puerta(x, y, orientacion="horizontal"):
    return {"centro": (x, y), "ancho": 0.9, "orientacion": orientacion}


def _puertas_en(ancho, largo, donde):
    todas = {
        "abajo": _puerta(ancho / 2, 0),
        "arriba": _puerta(ancho / 2, largo),
        "izquierda": _puerta(0, largo / 2, "vertical"),
        "derecha": _puerta(ancho, largo / 2, "vertical"),
        "esquina": _puerta(0.65, 0),
    }
    return [todas[d] for d in donde]


def _amueblar(ambiente, puertas):
    geometrias = generar_geometrias([ambiente], 15, 15)
    return amueblar_automaticamente(geometrias, {"puertas": puertas})


def _comprobar(resultado, ambiente, puertas):
    muebles = resultado["mobiliario"]
    interior = box(0, 0, ambiente["ancho"], ambiente["largo"])

    for i, a in enumerate(muebles):
        assert interior.buffer(1e-6).covers(a["geometria"]), a["tipo"]
        for b in muebles[i + 1:]:
            assert a["geometria"].intersection(b["geometria"]).area < 1e-6
        for p in puertas:
            x, y = p["centro"]
            # Al menos el paso queda libre.
            dx, dy = (0.4, 0.43) if p["orientacion"] == "vertical" else (0.43, 0.4)
            paso = box(x - dx, y - dy, x + dx, y + dy)
            assert a["geometria"].intersection(paso).area < 1e-6, a["tipo"]


@pytest.mark.parametrize("donde", [
    ["abajo"], ["izquierda", "derecha"], ["abajo", "arriba", "izquierda"],
    ["esquina", "derecha"],
])
@pytest.mark.parametrize("identificador, ancho, largo", [
    ("comedor_1", 2.8, 4.3), ("comedor_1", 4.6, 2.6), ("comedor_1", 3.0, 3.0),
    ("sala_1", 3.4, 5.3), ("sala_1", 4.5, 3.2),
    ("garaje_1", 2.7, 5.0), ("garaje_1", 3.0, 5.5),
    ("cocina_1", 2.2, 2.4), ("bano_1", 2.4, 1.6),
    ("dormitorio_1", 3.0, 3.2), ("lavanderia_1", 1.7, 3.0),
])
def test_entran_todos_los_muebles_y_complementos(identificador, ancho, largo, donde):
    ambiente = _ambiente(identificador, ancho, largo)
    puertas = _puertas_en(ancho, largo, donde)

    resultado = _amueblar(ambiente, puertas)

    tipos = Counter(m["tipo"] for m in resultado["mobiliario"])
    tipo = identificador.rsplit("_", 1)[0]
    for item in PLANTILLAS.get(tipo, []):
        assert tipos[item["tipo"]] == 1, (item["tipo"], tipos)
    assert resultado["omitidos"] == []
    complemento = {
        "comedor": ("silla", 4), "sala": ("mesa_centro", 1), "garaje": ("auto", 1),
    }.get(tipo)
    if complemento:
        assert tipos[complemento[0]] == complemento[1], tipos
    _comprobar(resultado, ambiente, puertas)


def test_un_garaje_sin_fondo_para_un_auto_queda_vacio():
    resultado = _amueblar(_ambiente("garaje_1", 5.0, 3.0), [])

    assert resultado["mobiliario"] == []


@pytest.mark.parametrize("a, b", [("garaje_1", "sala_1"), ("sala_1", "garaje_1"),
                                  ("garaje_1", "cocina_1")])
def test_la_puerta_del_garaje_abre_hacia_la_casa(a, b):
    destino = _destino_de({"ambiente_a": a, "ambiente_b": b})

    assert not destino.startswith("garaje")
