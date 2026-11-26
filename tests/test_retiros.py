"""Retiros del terreno y ubicación de la casa en el lote."""

import pytest

from src.ai.edit_interpreter import EditOperation, EditRequest
from src.ai.interpreter import interpretar_instruccion
from src.models.requirements import (
    Ambiente,
    RequerimientosArquitectonicos,
    Retiros,
)
from src.planning.retiros import area_edificable, detectar_retiros, ubicar
from src.services.pipeline import generar_plano
from src.ui import guardado
from src.ui import proyecto as pry
from src.ui.plano_svg import generar_svg_plano


def _lados(frontal=0, posterior=0, izquierdo=0, derecho=0):
    return Retiros(
        frontal=frontal, posterior=posterior,
        izquierdo=izquierdo, derecho=derecho,
    )


@pytest.mark.parametrize("texto, esperado", [
    ("Casa de 10 x 20 m con retiro frontal de 3 m", _lados(frontal=3)),
    ("retiro de 3 metros", _lados(frontal=3)),
    ("con un retiro municipal de 2,5 m.", _lados(frontal=2.5)),
    ("retiro frontal 3 y posterior 2", _lados(3, 2)),
    ("retiros: frontal 3 m, posterior 2.5 m", _lados(3, 2.5)),
    ("retiro de 3 m al frente y 2 m al fondo", _lados(3, 2)),
    ("retiros laterales de 1 m", _lados(izquierdo=1, derecho=1)),
    ("retiros laterales y posterior de 1,5 m", _lados(0, 1.5, 1.5, 1.5)),
    ("retiro a la izquierda de 1 m", _lados(izquierdo=1)),
    ("retiro frontal de 3 m y sala de 20 m2", _lados(frontal=3)),
    ("retiro frontal de 3 m, con 2 dormitorios", _lados(frontal=3)),
    ("retiro frontal de 3 m en un terreno de 10 x 20 m", _lados(frontal=3)),
    ("Casa sin retiros de 10 x 20 m", None),
    ("Casa de 10 x 20 m con sala al frente de 18 m2", None),
    ("quiero un retiro espiritual en casa", None),
])
def test_se_leen_los_retiros_de_la_descripcion(texto, esperado):
    assert detectar_retiros(texto) == esperado


def test_el_interprete_toma_los_retiros_del_texto():
    requerimientos = interpretar_instruccion(
        "Casa en un terreno de 10 x 20 m con retiro frontal de 3 m"
    )

    assert requerimientos.retiros == _lados(frontal=3)


def test_area_edificable():
    assert area_edificable(10, 20, _lados(3, 2, 1, 1.5)) == (7.5, 15)
    assert area_edificable(10, 20, None) == (10, 20)
    with pytest.raises(ValueError, match="no dejan sitio"):
        area_edificable(10, 20, _lados(izquierdo=5, derecho=5))


@pytest.mark.parametrize("retiros, x, y", [
    (None, 3.0, 0.0),
    (_lados(3, 2, 1, 0), 3.5, 3.0),
])
def test_se_ubica_al_frente_y_centrada(retiros, x, y):
    planta = [{"id": "sala_1", "nombre": "sala", "x": 0.4, "y": 5.0,
               "ancho": 4.0, "largo": 3.0}]

    ((movida,),) = ubicar([planta], 10, 20, retiros)

    assert (movida["x"], movida["y"]) == (x, y)
    assert planta[0]["x"] == 0.4, "no modifica la entrada"


def _requerimientos(pisos=1, retiros=None):
    return RequerimientosArquitectonicos(
        ancho_terreno_m=12, largo_terreno_m=22, numero_pisos=pisos,
        retiros=retiros,
        ambientes=[
            Ambiente(nombre="sala", area_objetivo_m2=18),
            Ambiente(nombre="cocina", area_objetivo_m2=9),
            Ambiente(nombre="dormitorio", cantidad=2, area_objetivo_m2=12),
            Ambiente(nombre="baño", area_objetivo_m2=4),
        ],
    )


def _comprobar(resultado, retiros, centrada=True):
    todos = [a for p in pry.pisos_de(resultado) for a in p.distribucion]
    x0 = min(a["x"] for a in todos)
    x1 = max(a["x"] + a["ancho"] for a in todos)
    y0 = min(a["y"] for a in todos)
    y1 = max(a["y"] + a["largo"] for a in todos)

    assert x0 >= retiros.izquierdo - 1e-6
    assert x1 <= 12 - retiros.derecho + 1e-6
    assert y0 >= retiros.frontal - 1e-6
    assert y1 <= 22 - retiros.posterior + 1e-6
    if centrada:
        assert y0 == pytest.approx(retiros.frontal)
        izquierda = x0 - retiros.izquierdo
        derecha = 12 - retiros.derecho - x1
        assert abs(izquierda - derecha) <= 0.11


@pytest.mark.parametrize("pisos", [1, 2])
def test_la_casa_respeta_los_retiros_tambien_al_editarla(pisos, tmp_path):
    retiros = _lados(3, 3, 1, 1.5)
    requerimientos = _requerimientos(pisos, retiros)
    ruta = tmp_path / "p.dxf"
    resultado = generar_plano(requerimientos, ruta)

    _comprobar(resultado, retiros)
    assert any(
        "Área edificable: 9.5 × 16 m" in n
        for n in pry.pisos_de(resultado)[0].notas
    )
    # El plano conserva el terreno completo.
    assert pry.dimensiones_terreno(pry.pisos_de(resultado)[0]) == (12, 22)

    proyecto = pry.proyecto_inicial(
        requerimientos, "Casa", resultado, ruta.read_bytes()
    )
    for operacion in (
        EditOperation(tipo="agregar_ambiente", ambiente="estudio"),
        EditOperation(tipo="quitar_ambiente", ambiente="estudio"),
    ):
        pry.aplicar_edicion(proyecto, "x", EditRequest(operaciones=[operacion]))
        _comprobar(
            pry.version_actual(proyecto)["resultado"], retiros, centrada=False
        )

    recuperado = guardado.importar(guardado.exportar(proyecto))
    assert recuperado["requerimientos"].retiros == retiros


def test_sin_retiros_la_casa_queda_al_frente_y_centrada(tmp_path):
    resultado = generar_plano(_requerimientos(), tmp_path / "p.dxf")

    _comprobar(resultado, _lados())
    assert not any("Retiros" in n for n in resultado.notas)


def test_si_no_cabe_dentro_de_los_retiros_se_explica(tmp_path):
    requerimientos = _requerimientos(retiros=_lados(frontal=21.5))

    with pytest.raises(ValueError, match="Dentro de los retiros quedan 12 × 0.5 m"):
        generar_plano(requerimientos, tmp_path / "p.dxf")


def test_el_plano_marca_el_limite_de_los_retiros(tmp_path):
    resultado = generar_plano(
        _requerimientos(retiros=_lados(frontal=3)), tmp_path / "p.dxf"
    )

    con = generar_svg_plano(resultado, retiros=_lados(frontal=3).model_dump())

    assert 'class="retiros"' in con
    assert 'class="retiros"' not in generar_svg_plano(resultado)
