"""Lógica del proyecto: versiones, edición sobre el plano actual y deshacer."""

import json

import pytest

from src.ai.edit_interpreter import EditOperation, EditRequest
from src.ai.providers.mock_provider import MockProvider
from src.models.requirements import RequerimientosArquitectonicos
from src.services.pipeline import ResultadoPlanoMultipisos, construir_plano
from tests.plano_fijo import DISTRIBUCION_FIJA
from src.ui import proyecto as pry



def _requerimientos():
    contenido = MockProvider().chat(messages=[{"role": "user", "content": "terreno"}])
    return RequerimientosArquitectonicos(**json.loads(contenido["message"]["content"]))


def _reducir(ambiente, area):
    return EditRequest(operaciones=[
        EditOperation(tipo="modificar_area", ambiente=ambiente, area_objetivo=area)
    ])


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    ruta = tmp_path_factory.mktemp("proyecto") / "plano.dxf"
    resultado = construir_plano(DISTRIBUCION_FIJA, 10, 20, ruta)
    return pry.proyecto_inicial(
        _requerimientos(), "Casa de 10 x 20 m", resultado, ruta.read_bytes()
    )


def test_crear_proyecto_genera_el_plano_con_el_pipeline(tmp_path):
    creado = pry.crear_proyecto(_requerimientos(), "Casa de 10 x 20 m")

    assert len(creado["versiones"]) == 1
    assert pry.pisos_de(creado["versiones"][0]["resultado"])[0].distribucion


@pytest.fixture
def proyecto(base):
    """Copia independiente: cada test puede modificar las listas."""
    return {
        "requerimientos": base["requerimientos"],
        "versiones": list(base["versiones"]),
        "mensajes": list(base["mensajes"]),
    }


def _area(version, identificador):
    piso = pry.pisos_de(version["resultado"])[0]
    return next(
        a["ancho"] * a["largo"] for a in piso.distribucion if a["id"] == identificador
    )


def test_crear_proyecto_tiene_una_version_y_la_conversacion_inicial(base):
    assert len(base["versiones"]) == 1
    assert base["versiones"][0]["dxf"].startswith(b"  0")
    assert base["versiones"][0]["csv"].startswith("piso,")
    assert [m["rol"] for m in base["mensajes"]] == ["usuario", "agente"]
    assert "Plano generado" in base["mensajes"][1]["texto"]
    assert "cambiar el área" in base["mensajes"][1]["texto"]


def test_editar_agrega_una_version_sin_tocar_la_anterior(proyecto):
    antes = _area(proyecto["versiones"][0], "dormitorio_1")

    pry.aplicar_edicion(proyecto, "reduce el dormitorio 1", _reducir("dormitorio 1", 8))

    assert len(proyecto["versiones"]) == 2
    assert antes == pytest.approx(12)
    assert _area(proyecto["versiones"][0], "dormitorio_1") == antes
    assert _area(proyecto["versiones"][1], "dormitorio_1") == pytest.approx(8, abs=0.05)
    assert "Dormitorio 1: " in proyecto["mensajes"][-1]["texto"]
    assert "→ 8.0 m²" in proyecto["mensajes"][-1]["texto"]


def test_las_ediciones_se_encadenan_sobre_el_plano_actual(proyecto):
    pry.aplicar_edicion(proyecto, "uno", _reducir("dormitorio 1", 8))
    pry.aplicar_edicion(proyecto, "dos", _reducir("cocina", 12))

    assert len(proyecto["versiones"]) == 3
    ultima = proyecto["versiones"][-1]
    assert _area(ultima, "dormitorio_1") == pytest.approx(8, abs=0.05)
    assert _area(ultima, "cocina_1") == pytest.approx(12, abs=0.05)


def test_deshacer_vuelve_a_la_version_anterior(proyecto):
    pry.aplicar_edicion(proyecto, "uno", _reducir("dormitorio 1", 8))

    assert pry.deshacer(proyecto) is True

    assert len(proyecto["versiones"]) == 1
    assert "Deshice" in proyecto["mensajes"][-1]["texto"]


def test_no_se_puede_deshacer_la_version_inicial(proyecto):
    assert pry.deshacer(proyecto) is False
    assert len(proyecto["versiones"]) == 1


def test_una_edicion_rechazada_no_crea_version(proyecto):
    with pytest.raises(ValueError):
        pry.aplicar_edicion(proyecto, "x", _reducir("ambiente inexistente", 8))

    assert len(proyecto["versiones"]) == 1


def test_abrir_proyecto_reconstruye_el_plano_desde_un_dxf(base):
    abierto = pry.abrir_proyecto(base["versiones"][0]["dxf"], "mi_plano.dxf")

    original = pry.pisos_de(base["versiones"][0]["resultado"])[0]
    reabierto = pry.pisos_de(abierto["versiones"][0]["resultado"])[0]
    assert len(reabierto.distribucion) == len(original.distribucion)
    assert abierto["requerimientos"] is None
    assert "mi_plano.dxf" in abierto["mensajes"][0]["texto"]


@pytest.mark.parametrize("contenido", [b"no es un dxf", b"", b"0\nSECTION\n" * 3])
def test_abrir_un_archivo_invalido_da_un_error_claro(contenido):
    with pytest.raises(ValueError, match="no es un archivo DXF válido"):
        pry.abrir_proyecto(contenido, "roto.dxf")


def test_se_puede_editar_un_piso_pero_no_varias_plantas(base):
    unico = base["versiones"][0]["resultado"]
    varios = ResultadoPlanoMultipisos(pisos=[unico, unico], ruta_dxf=None, numero_pisos=2)

    assert pry.puede_editar(unico) is True
    assert pry.puede_editar(varios) is False
    assert len(pry.pisos_de(varios)) == 2


def test_resumen_de_modificaciones():
    lineas = pry.resumen_modificaciones([
        {"ambiente": "comedor", "id": "comedor_1", "area_anterior": 12.0, "area_nueva": 8.0},
        {"ambiente": "dormitorio", "id": "dormitorio_2", "referencia": "cocina",
         "relacion": "derecha_de", "desplazamiento": (5.4, 8.0)},
    ])

    assert lineas == [
        "Comedor 1: 12.0 → 8.0 m²",
        "Dormitorio 2 movido a la derecha de cocina",
    ]


def test_registrar_error_y_usuario_añaden_mensajes(proyecto):
    pry.registrar_usuario(proyecto, "hola")
    pry.registrar_error(proyecto, "falló", "traza")

    assert [m["rol"] for m in proyecto["mensajes"][-2:]] == ["usuario", "error"]
    assert proyecto["mensajes"][-1]["detalle"] == "traza"
