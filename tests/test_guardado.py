"""Guardar y retomar proyectos: archivo exportado y autoguardado local."""

import json
import time

import pytest

from src.ai.edit_interpreter import EditOperation, EditRequest
from src.ai.providers.mock_provider import MockProvider
from src.models.requirements import RequerimientosArquitectonicos
from src.services.pipeline import (
    ResultadoPlanoMultipisos,
    construir_multipisos,
    construir_plano,
)
from src.ui import almacen, guardado
from src.ui import proyecto as pry
from tests.plano_fijo import DISTRIBUCION_FIJA

ESCALERA = {"id": "escalera_1", "nombre": "escalera", "x": 0.0, "y": 0.0,
            "ancho": 2.0, "largo": 4.0}
BAJA = [
    ESCALERA,
    {"id": "sala_1", "nombre": "sala", "x": 2.0, "y": 0.0, "ancho": 5.0, "largo": 4.0},
    {"id": "cocina_1", "nombre": "cocina", "x": 7.0, "y": 0.0, "ancho": 3.0, "largo": 4.0},
]
ALTA = [
    ESCALERA,
    {"id": "dormitorio_1", "nombre": "dormitorio", "x": 2.0, "y": 0.0,
     "ancho": 5.0, "largo": 4.0},
    {"id": "bano_1", "nombre": "baño", "x": 7.0, "y": 0.0, "ancho": 3.0, "largo": 4.0},
]


def _requerimientos():
    contenido = MockProvider().chat(messages=[{"role": "user", "content": "terreno"}])
    return RequerimientosArquitectonicos(**json.loads(contenido["message"]["content"]))


def _cambiar_area(ambiente, area):
    return EditRequest(operaciones=[
        EditOperation(tipo="modificar_area", ambiente=ambiente, area_objetivo=area)
    ])


def _proyecto(tmp_path, distribuciones):
    ruta = tmp_path / "plano.dxf"
    if len(distribuciones) > 1:
        resultado = construir_multipisos(distribuciones, 12, 20, ruta)
    else:
        resultado = construir_plano(distribuciones[0], 10, 20, ruta)
    piso = pry.pisos_de(resultado)[0]
    piso.notas = ["Una nota del sistema"]
    piso.avisos = ["Un aviso que no se puede recalcular"]
    return pry.proyecto_inicial(
        _requerimientos(), "Casa de 10 x 20 m", resultado, ruta.read_bytes()
    )


@pytest.fixture
def editado(tmp_path):
    proyecto = _proyecto(tmp_path, [DISTRIBUCION_FIJA])
    pry.registrar_usuario(proyecto, "reduce el dormitorio 1")
    pry.aplicar_edicion(
        proyecto, "reduce el dormitorio 1", _cambiar_area("dormitorio 1", 8)
    )
    pry.registrar_error(proyecto, "Error inesperado", "Traceback: C:/Users/alguien")
    return proyecto


def _comparable(proyecto):
    return [
        (
            v["etiqueta"], v["cambiados"], v["csv"], type(v["resultado"]),
            [
                (
                    p.distribucion, p.notas, p.avisos, p.puertas, p.ventanas,
                    p.mobiliario, p.geometrias["terreno"].bounds,
                )
                for p in pry.pisos_de(v["resultado"])
            ],
        )
        for v in proyecto["versiones"]
    ]


def _datos(proyecto):
    return json.loads(guardado.exportar(proyecto))


# ---------------------------------------------------------------- archivo

def test_ida_y_vuelta_conserva_versiones_y_conversacion(editado):
    recuperado = guardado.importar(guardado.exportar(editado))

    assert _comparable(recuperado) == _comparable(editado)
    assert recuperado["nombre"] == "Casa de 10 x 20 m"
    assert recuperado["requerimientos"] == editado["requerimientos"]
    assert [(m["rol"], m["texto"]) for m in recuperado["mensajes"]] == [
        (m["rol"], m["texto"]) for m in editado["mensajes"]
    ]
    assert recuperado["versiones"][-1]["dxf"].startswith(b"  0")
    assert "id" not in recuperado


def test_no_se_guardan_las_trazas(editado):
    contenido = guardado.exportar(editado)

    assert b"Traceback" not in contenido
    assert guardado.importar(contenido)["mensajes"][-1]["detalle"] is None


def test_tras_importar_funcionan_deshacer_y_editar(editado):
    recuperado = guardado.importar(guardado.exportar(editado))

    pry.aplicar_edicion(recuperado, "amplía", _cambiar_area("dormitorio 1", 9))
    assert len(recuperado["versiones"]) == 3
    assert pry.deshacer(recuperado) and pry.deshacer(recuperado)

    assert _comparable(recuperado) == _comparable(editado)[:1]


def test_dos_plantas(tmp_path):
    proyecto = _proyecto(tmp_path, [BAJA, ALTA])

    recuperado = guardado.importar(guardado.exportar(proyecto))

    assert _comparable(recuperado) == _comparable(proyecto)
    assert isinstance(recuperado["versiones"][0]["resultado"], ResultadoPlanoMultipisos)
    pry.aplicar_edicion(recuperado, "reduce", _cambiar_area("cocina 1", 10))
    assert len(recuperado["versiones"]) == 2


def test_proyecto_abierto_desde_un_dxf_con_ambientes_sin_nombre(tmp_path):
    ambientes = [
        {"id": f"ambiente_{i}", "nombre": "ambiente", "x": 4.0 * (i - 1), "y": 0.0,
         "ancho": 4.0, "largo": 3.0}
        for i in (1, 2)
    ]
    construir_plano(ambientes, 10, 10, tmp_path / "origen.dxf")
    proyecto = pry.abrir_proyecto(
        (tmp_path / "origen.dxf").read_bytes(), "mi plano.dxf"
    )

    recuperado = guardado.importar(guardado.exportar(proyecto))

    assert recuperado["nombre"] == "mi plano"
    assert recuperado["requerimientos"] is None
    assert _comparable(recuperado) == _comparable(proyecto)


def test_el_nombre_se_acorta():
    assert pry._nombre_corto("casa " * 40).endswith("…")
    assert len(pry._nombre_corto("casa " * 40)) <= 61
    assert pry._nombre_corto("  \n ") == "Proyecto"


@pytest.mark.parametrize("contenido", [
    b"", b"no es json", b"\xff\xfe\x00", b"[1, 2]", b'{"formato": "otro"}',
    b"[" * 100_000,
], ids=["vacio", "texto", "binario", "lista", "otro_formato", "anidado"])
def test_un_archivo_que_no_es_un_proyecto(contenido):
    with pytest.raises(ValueError, match="no es un proyecto válido"):
        guardado.importar(contenido)


def test_un_proyecto_de_una_version_mas_nueva(editado):
    datos = _datos(editado) | {"version": 2}

    with pytest.raises(ValueError, match="versión más nueva"):
        guardado.importar(json.dumps(datos).encode())


def test_un_archivo_demasiado_grande():
    with pytest.raises(ValueError, match="demasiado grande"):
        guardado.importar(b" " * (guardado.TAMANO_MAXIMO + 1))


@pytest.mark.parametrize("cambio", [
    {"id": "sala"},
    {"x": -1},
    {"ancho": 0},
    {"largo": float("nan")},
    {"ancho": 1e9},
    {"nombre": ""},
])
def test_ambientes_mal_formados(editado, cambio):
    datos = _datos(editado)
    datos["versiones"][0]["pisos"][0]["distribucion"][0].update(cambio)

    with pytest.raises(ValueError, match="no es un proyecto válido"):
        guardado.importar(json.dumps(datos).encode())


@pytest.mark.parametrize("cambio", [
    {"x": 6.0},            # se superpone con la cocina
    {"x": 900.0},          # fuera del terreno
    {"id": "cocina_1"},    # repetido
])
def test_una_geometria_imposible(editado, cambio):
    datos = _datos(editado)
    datos["versiones"][0]["pisos"][0]["distribucion"][0].update(cambio)

    with pytest.raises(ValueError, match="dañado .versión 1"):
        guardado.importar(json.dumps(datos).encode())


# ---------------------------------------------------------------- almacén

def test_guardar_listar_abrir_y_borrar(editado, carpeta_de_proyectos):
    ruta = almacen.guardar(editado)

    assert ruta.parent == carpeta_de_proyectos
    proyectos, danados = almacen.listar()
    assert danados == 0
    assert [(p["id"], p["nombre"], p["versiones"]) for p in proyectos] == [
        (editado["id"], "Casa de 10 x 20 m", 2)
    ]

    recuperado = almacen.abrir(editado["id"])
    assert _comparable(recuperado) == _comparable(editado)
    assert recuperado["id"] == editado["id"]
    assert recuperado["modificado"] == editado["modificado"]

    almacen.borrar(editado["id"])
    assert almacen.listar() == ([], 0)
    with pytest.raises(ValueError, match="ya no existe"):
        almacen.abrir(editado["id"])


def test_volver_a_guardar_actualiza_el_mismo_archivo(editado, carpeta_de_proyectos):
    almacen.guardar(editado)
    creado = editado["creado"]
    pry.deshacer(editado)
    almacen.guardar(editado)

    assert editado["creado"] == creado
    assert len(list(carpeta_de_proyectos.iterdir())) == 1
    assert almacen.listar()[0][0]["versiones"] == 1


def test_el_mas_reciente_va_primero(editado):
    otro = dict(editado, nombre="Otro", id="f" * 32)
    almacen.guardar(editado)
    time.sleep(0.02)
    almacen.guardar(otro)

    assert [p["nombre"] for p in almacen.listar()[0]] == [
        "Otro", "Casa de 10 x 20 m"
    ]

    time.sleep(0.02)
    almacen.guardar(editado)

    assert [p["nombre"] for p in almacen.listar()[0]] == [
        "Casa de 10 x 20 m", "Otro"
    ]


def test_un_archivo_danado_se_cuenta_y_no_se_borra(editado, carpeta_de_proyectos):
    almacen.guardar(editado)
    roto = carpeta_de_proyectos / ("a" * 32 + guardado.EXTENSION)
    roto.write_text("{", encoding="utf-8")

    proyectos, danados = almacen.listar()

    assert len(proyectos) == 1 and danados == 1
    assert roto.exists()


@pytest.mark.parametrize("identificador", ["../secreto", "a" * 31, "A" * 32, ""])
def test_un_identificador_no_puede_salir_de_la_carpeta(identificador):
    with pytest.raises(ValueError, match="no válido"):
        almacen.abrir(identificador)
    with pytest.raises(ValueError, match="no válido"):
        almacen.borrar(identificador)


def test_viene_desactivado_por_defecto(editado, monkeypatch, carpeta_de_proyectos):
    monkeypatch.delenv("AUTOGUARDADO")

    assert almacen.guardar(editado) is None
    assert almacen.listar() == ([], 0)
    assert not carpeta_de_proyectos.exists()


def test_desactivado(editado, monkeypatch, carpeta_de_proyectos):
    monkeypatch.setenv("AUTOGUARDADO", "0")

    assert almacen.guardar(editado) is None
    assert almacen.listar() == ([], 0)
    assert not carpeta_de_proyectos.exists()


def test_un_bloqueo_pasajero_se_reintenta(editado, monkeypatch):
    real = almacen.os.replace
    fallos = [PermissionError(), PermissionError()]

    def bloqueado(origen, destino):
        if fallos:
            raise fallos.pop()
        real(origen, destino)

    monkeypatch.setattr(almacen.os, "replace", bloqueado)
    monkeypatch.setattr(almacen, "ESPERA_S", 0)

    assert almacen.guardar(editado).exists()


def test_si_falla_la_escritura_se_conserva_lo_anterior(
    editado, monkeypatch, carpeta_de_proyectos
):
    ruta = almacen.guardar(editado)
    anterior = ruta.read_bytes()

    def bloqueado(origen, destino):
        raise PermissionError("bloqueado")

    monkeypatch.setattr(almacen.os, "replace", bloqueado)
    monkeypatch.setattr(almacen, "ESPERA_S", 0)
    pry.deshacer(editado)

    with pytest.raises(PermissionError):
        almacen.guardar(editado)

    assert ruta.read_bytes() == anterior
    assert list(carpeta_de_proyectos.iterdir()) == [ruta], "sin temporales"
