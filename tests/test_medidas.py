"""Rectas de medición de cada ambiente (vista 2D y DXF)."""

import xml.etree.ElementTree as ET

import ezdxf
import pytest

from src.geometry.medidas import SEPARACION_M, medidas_de_ambiente
from src.services.pipeline import generar_plano_multipisos
from src.ui.plano_svg import CAPAS_POR_DEFECTO, generar_svg_plano
from tests.plano_fijo import DISTRIBUCION_FIJA, generar_plano_fijo

NS = {"s": "http://www.w3.org/2000/svg"}


@pytest.fixture(scope="module")
def plano(tmp_path_factory):
    return generar_plano_fijo(None, tmp_path_factory.mktemp("medidas") / "p.dxf")


def test_las_rectas_van_dentro_y_miden_el_ambiente():
    medidas = medidas_de_ambiente(1, 2, 6, 5)

    ancho, largo = medidas["ancho"], medidas["largo"]
    assert ancho["valor"] == 5 and largo["valor"] == 3
    assert ancho["inicio"] == (1, 5 - SEPARACION_M)
    assert ancho["fin"] == (6, 5 - SEPARACION_M)
    assert largo["inicio"] == (1 + SEPARACION_M, 2)
    assert 2 < largo["texto"][1] < 3.5, "bajo el centro, donde va el nombre"


def test_en_un_ambiente_pequeno_se_acercan_a_la_pared():
    medidas = medidas_de_ambiente(0, 0, 1, 1.2)

    assert medidas["ancho"]["inicio"][1] == pytest.approx(1.2 - 0.22)


def test_el_svg_muestra_ancho_y_largo_de_cada_ambiente(plano):
    raiz = ET.fromstring(generar_svg_plano(plano))

    grupos = raiz.findall(".//s:g[@class='medida']", NS)

    assert len(grupos) == len(plano.distribucion)
    for grupo, ambiente in zip(grupos, plano.distribucion):
        textos = [t.text for t in grupo.findall("s:text", NS)]
        assert textos == [f"{ambiente['ancho']:.2f} m", f"{ambiente['largo']:.2f} m"]


def test_la_capa_medidas_se_puede_apagar(plano):
    svg = generar_svg_plano(plano, capas=CAPAS_POR_DEFECTO - {"medidas"})

    assert 'class="medida"' not in svg


def _cotas(ruta):
    documento = ezdxf.readfile(str(ruta))
    assert not documento.audit().errors
    return list(documento.modelspace().query("DIMENSION"))


def test_el_dxf_lleva_dos_cotas_por_ambiente(plano):
    cotas = _cotas(plano.ruta_dxf)

    assert len(cotas) == 2 * len(DISTRIBUCION_FIJA)
    assert {c.dxf.layer for c in cotas} == {"MEDIDAS"}
    esperadas = sorted(
        round(a[lado], 2) for a in DISTRIBUCION_FIJA for lado in ("ancho", "largo")
    )
    assert sorted(round(c.get_measurement(), 2) for c in cotas) == esperadas


def test_el_dxf_de_dos_plantas_tambien(tmp_path):
    from tests.test_pipeline_y_ui import _requerimientos_dos_pisos

    ruta = tmp_path / "dos.dxf"
    resultado = generar_plano_multipisos(_requerimientos_dos_pisos(), 10, 20, ruta)

    ambientes = sum(len(p.distribucion) for p in resultado.pisos)
    assert len(_cotas(ruta)) == 2 * ambientes
