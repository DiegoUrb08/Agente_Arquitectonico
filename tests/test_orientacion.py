"""Norte y orientación de la sala y los dormitorios."""

import json

import pytest

from src.ai.interpreter import interpretar_instruccion
from src.ai.providers.mock_provider import MockProvider
from src.models.requirements import Ambiente, RequerimientosArquitectonicos
from src.planning.layout_optimizer import optimizar_distribucion
from src.planning.orientacion import (
    LADOS,
    detectar_norte,
    punto_de,
    ventanas_por_ambiente,
)
from src.services.pipeline import construir_plano, generar_plano
from src.ui import proyecto as pry
from src.ui.plano_svg import generar_svg_plano
from tests.plano_fijo import DISTRIBUCION_FIJA


@pytest.mark.parametrize("norte, esperado", [
    ("fondo", ["norte", "este", "sur", "oeste"]),
    ("derecha", ["oeste", "norte", "este", "sur"]),
    ("frente", ["sur", "oeste", "norte", "este"]),
    ("izquierda", ["este", "sur", "oeste", "norte"]),
])
def test_punto_cardinal_de_cada_lado(norte, esperado):
    # Lados en el orden fondo, derecha, frente, izquierda.
    assert [punto_de(lado, norte) for lado in LADOS] == esperado


@pytest.mark.parametrize("texto, norte", [
    ("Casa de 10 x 20. El norte está al fondo.", "fondo"),
    ("el norte queda hacia la calle", "frente"),
    ("terreno con el norte a la derecha", "derecha"),
    ("Norte a la izquierda", "izquierda"),
    ("la fachada mira al norte", "frente"),
    ("la fachada da al sur", "fondo"),
    ("casa orientada al este", "derecha"),
    ("el fondo da al oeste", "derecha"),
    ("Casa de 10 x 20 con sala y cocina", None),
    ("en este terreno quiero una casa al norte de Lima", None),
    ("Casa con sala al frente y 2 dormitorios al fondo", None),
])
def test_se_lee_el_norte_de_la_descripcion(texto, norte):
    assert detectar_norte(texto) == norte


def test_el_interprete_toma_el_norte_del_texto():
    requerimientos = interpretar_instruccion(
        "Casa en un terreno de 10 x 20 m, el norte está a la derecha"
    )
    sin_dato = interpretar_instruccion("Casa en un terreno de 10 x 20 m")

    assert requerimientos.norte == "derecha"
    assert sin_dato.norte is None


def test_hacia_donde_mira_cada_ventana(tmp_path):
    plano = construir_plano(DISTRIBUCION_FIJA, 10, 20, tmp_path / "p.dxf")

    al_fondo = ventanas_por_ambiente(
        plano.distribucion, plano.ventanas["ventanas"], "fondo"
    )
    al_frente = ventanas_por_ambiente(
        plano.distribucion, plano.ventanas["ventanas"], "frente"
    )

    assert "oeste" in al_fondo["sala_1"]
    assert "este" in al_frente["sala_1"]


def _requerimientos(norte):
    return RequerimientosArquitectonicos(
        ancho_terreno_m=10, largo_terreno_m=20, norte=norte,
        ambientes=[
            Ambiente(nombre="sala", area_objetivo_m2=18),
            Ambiente(nombre="cocina", area_objetivo_m2=9),
            Ambiente(nombre="dormitorio", cantidad=2, area_objetivo_m2=12),
            Ambiente(nombre="baño", area_objetivo_m2=4),
        ],
    )


def _toca(distribucion, identificador, lado):
    a = next(x for x in distribucion if x["id"] == identificador)
    bordes = {
        "izquierda": (a["x"], min(x["x"] for x in distribucion)),
        "derecha": (a["x"] + a["ancho"],
                    max(x["x"] + x["ancho"] for x in distribucion)),
    }
    propio, borde = bordes[lado]
    return abs(propio - borde) < 0.01


@pytest.mark.parametrize("norte, este", [("fondo", "derecha"), ("frente", "izquierda")])
def test_los_dormitorios_buscan_el_sol_de_la_manana(norte, este, monkeypatch):
    monkeypatch.setattr(
        "src.planning.layout_optimizer.TIEMPO_COMPACTACION_SEGUNDOS", 6
    )

    distribucion = optimizar_distribucion(_requerimientos(norte))

    al_este = [
        i for i in ("dormitorio_1", "dormitorio_2")
        if _toca(distribucion, i, este)
    ]
    assert al_este, distribucion


def test_la_nota_y_la_flecha_solo_aparecen_con_norte(tmp_path):
    con = generar_plano(_requerimientos("fondo"), tmp_path / "a.dxf")
    sin = generar_plano(_requerimientos(None), tmp_path / "b.dxf")

    assert any("Con el norte al fondo" in n for n in con.notas)
    assert not any("norte" in n for n in sin.notas)
    assert 'class="norte"' in generar_svg_plano(con, norte="fondo")
    assert 'class="norte"' not in generar_svg_plano(sin)


def test_las_ediciones_reciben_el_norte(tmp_path, monkeypatch):
    plano = construir_plano(DISTRIBUCION_FIJA, 10, 20, tmp_path / "p.dxf")
    contenido = MockProvider().chat(messages=[{"role": "user", "content": "terreno"}])
    requerimientos = RequerimientosArquitectonicos(
        **json.loads(contenido["message"]["content"])
    )
    requerimientos.norte = "izquierda"
    proyecto = pry.proyecto_inicial(
        requerimientos, "Casa", plano, plano.ruta_dxf.read_bytes()
    )
    recibido = {}

    def editar(entrada, salida, solicitud, norte=None, retiros=None):
        recibido["norte"] = norte
        raise ValueError("basta")

    monkeypatch.setattr("src.ui.proyecto.editar_plano", editar)

    with pytest.raises(ValueError, match="basta"):
        pry.aplicar_edicion(proyecto, "algo", None)

    assert recibido == {"norte": "izquierda"}
