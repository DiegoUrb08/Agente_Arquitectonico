"""Lámina en PDF: una hoja A3 a escala por planta."""

import base64
import re
import zlib
from datetime import date

import pytest
from reportlab.lib.units import mm

from src.lamina.pdf import elegir_escala, generar_lamina, titulos_de_plantas
from src.models.requirements import RequerimientosArquitectonicos, Retiros
from src.services.pipeline import construir_multipisos, construir_plano

SALA = {"id": "sala_1", "nombre": "sala", "x": 0.0, "y": 0.0, "ancho": 4.0, "largo": 4.0}
COCINA = {"id": "cocina_1", "nombre": "cocina", "x": 4.0, "y": 0.0, "ancho": 3.0, "largo": 4.0}
BANO = {"id": "baño_2", "nombre": "baño", "x": 0.0, "y": 0.0, "ancho": 2.5, "largo": 2.0}
DORMITORIO = {"id": "dormitorio_1", "nombre": "dormitorio", "x": 2.5, "y": 0.0,
              "ancho": 3.5, "largo": 3.5}


def _hojas(pdf: bytes) -> list[str]:
    """Instrucciones de dibujo de cada hoja, con sus textos legibles."""
    hojas = []
    for datos in re.findall(rb"stream\r?\n(.*?)endstream", pdf, re.S):
        crudo = zlib.decompress(base64.a85decode(datos.strip(), adobe=True))
        hojas.append(crudo.decode("latin-1"))
    return hojas


def _textos(hoja: str) -> str:
    """Los textos de una hoja, con las tildes ya decodificadas."""
    def decodificar(texto):
        return re.sub(
            r"\\([0-7]{3})|\\(.)",
            lambda m: chr(int(m[1], 8)) if m[1] else m[2], texto,
        )

    return "\n".join(
        decodificar(t) for t in re.findall(r"\(((?:\\.|[^\\)])*)\) Tj", hoja)
    )


def _paginas(pdf: bytes) -> int:
    return len(re.findall(rb"/Type /Page\b(?!s)", pdf))


@pytest.fixture
def una_planta(tmp_path):
    return construir_plano([SALA, COCINA], 10, 15, tmp_path / "p.dxf")


def _requerimientos(**extra):
    return RequerimientosArquitectonicos(
        ancho_terreno_m=10, largo_terreno_m=15, ambientes=[], **extra
    )


def test_una_planta_es_una_hoja_a3_con_su_cuadro_de_areas(una_planta):
    pdf = generar_lamina(una_planta, "Casa de prueba", fecha=date(2026, 3, 5))

    assert pdf.startswith(b"%PDF")
    assert _paginas(pdf) == 1
    # A3 apaisado, en puntos.
    assert re.search(rb"/MediaBox \[ 0 0 1190\.5\d* 841\.8\d* \]", pdf)
    texto = _textos(_hojas(pdf)[0])
    for esperado in (
        "Casa de prueba", "PLANTA ÚNICA", "CUADRO DE ÁREAS", "Sala", "Cocina",
        "SALA", "16.00 m²", "4.00 × 4.00", "28.00", "10.00 m", "15.00 m",
        "1:75", "05/03/2026", "A-01  (1 de 1)", "ESCALA GRÁFICA",
    ):
        assert esperado in texto, esperado


def test_sin_requerimientos_no_inventa_norte_ni_calle(una_planta):
    texto = _textos(_hojas(generar_lamina(una_planta))[0]).split("\n")

    assert "N" not in texto
    assert "CALLE" not in texto
    assert "Límite de retiros" not in texto


@pytest.mark.parametrize("norte", ["frente", "fondo", "derecha", "izquierda"])
def test_con_requerimientos_muestra_norte_calle_y_retiros(una_planta, norte):
    requerimientos = _requerimientos(norte=norte, retiros=Retiros(frontal=3))

    texto = _textos(_hojas(generar_lamina(una_planta, "x", requerimientos))[0]).split("\n")

    assert "N" in texto
    assert "CALLE" in texto
    assert "Límite de retiros" in texto


def test_dos_plantas_son_dos_hojas_con_total_conjunto(tmp_path):
    resultado = construir_multipisos(
        [[SALA, COCINA], [BANO, DORMITORIO]], 10, 15, tmp_path / "p.dxf"
    )
    requerimientos = _requerimientos(retiros=Retiros(frontal=2))

    pdf = generar_lamina(resultado, "Casa", requerimientos)

    assert _paginas(pdf) == 2
    baja, alta = map(_textos, _hojas(pdf))
    assert "PLANTA BAJA" in baja and "PLANTA ALTA" in alta
    assert "Dormitorio" not in baja and "Dormitorio" in alta
    assert "Baño 2" in alta
    total = f"{28 + 5 + 12.25:.2f}"
    assert total in baja and total in alta
    # Los retiros solo se marcan en la planta baja.
    assert "retiros" in baja and "retiros" not in alta


def test_con_muchos_ambientes_el_cuadro_resume_y_conserva_el_total(tmp_path):
    ambientes = [
        {"id": f"deposito_{i + 1}", "nombre": "deposito", "x": (i % 10) * 2.0,
         "y": (i // 10) * 2.0, "ancho": 2.0, "largo": 2.0}
        for i in range(80)
    ]
    resultado = construir_plano(ambientes, 20, 16, tmp_path / "p.dxf")

    texto = _textos(_hojas(generar_lamina(resultado))[0])

    assert re.search(r"Otros \d+ ambientes", texto)
    assert "320.00" in texto


@pytest.mark.parametrize("nombre", [
    "", "palabra " * 80, "x" * 400, "Casa (ampliación) \\ 🏠",
])
def test_cualquier_nombre_de_proyecto_genera_la_lamina(una_planta, nombre):
    assert generar_lamina(una_planta, nombre).startswith(b"%PDF")


def test_un_terreno_enorme_usa_una_escala_mayor(tmp_path):
    resultado = construir_plano([SALA], 900, 900, tmp_path / "p.dxf")

    assert "1:3500" in _textos(_hojas(generar_lamina(resultado))[0])


@pytest.mark.parametrize("ancho, largo, escala", [
    (5, 8, 50), (12, 25, 100), (20, 40, 200), (100, 60, 400),
])
def test_elige_la_mayor_escala_normalizada_que_entra(ancho, largo, escala):
    disponible = (259 * mm, 259 * mm)

    assert elegir_escala(ancho, largo, *disponible) == escala


def test_titulos_de_plantas():
    assert titulos_de_plantas(1) == ["PLANTA ÚNICA"]
    assert titulos_de_plantas(2) == ["PLANTA BAJA", "PLANTA ALTA"]
    assert titulos_de_plantas(3) == ["PLANTA BAJA", "PLANTA ALTA 1", "PLANTA ALTA 2"]
