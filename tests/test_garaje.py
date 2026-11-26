"""Garaje con acceso desde la calle."""

import ezdxf
import pytest

from src.ai.edit_interpreter import EditOperation, EditRequest
from src.bim.ifc import generar_ifc
from src.models.requirements import (
    Ambiente,
    RequerimientosArquitectonicos,
    Retiros,
)
from src.cad.dxf_editor import resolver_ambiente
from src.planning.garaje import como_se_llama, tiene_frente_libre
from src.services.pipeline import construir_plano, generar_plano
from src.ui import proyecto as pry
from src.ui.escena_3d import generar_escena_3d


def _ambiente(identificador, x, y, ancho, largo):
    nombre = identificador.rsplit("_", 1)[0]
    return {"id": identificador, "nombre": nombre, "x": x, "y": y,
            "ancho": ancho, "largo": largo}


CON_GARAJE = [
    _ambiente("sala_1", 0, 0, 5, 5),
    _ambiente("garaje_1", 5, 0, 3, 5),
    _ambiente("cocina_1", 0, 5, 5, 3),
]


def _puertas(piso, vehiculares):
    return [
        p for p in piso.puertas["puertas"]
        if bool(p.get("vehicular")) is vehiculares
        and p["ambiente_b"] == "exterior"
    ]


def test_el_garaje_tiene_porton_y_la_casa_conserva_su_entrada(tmp_path):
    plano = construir_plano(CON_GARAJE, 10, 15, tmp_path / "p.dxf")

    (porton,) = _puertas(plano, True)
    (entrada,) = _puertas(plano, False)

    assert porton["ambiente_a"] == "garaje_1"
    assert porton["centro"] == (6.5, 0)
    assert porton["ancho"] == 2.4
    assert entrada["ambiente_a"] == "sala_1"
    assert not any("Garaje" in a for a in plano.avisos)
    assert not [
        v for v in plano.ventanas["ventanas"]
        if v["ambiente_a"] == "garaje_1" and v["centro"][1] == 0
    ], "el portón ocupa el frente"


def test_el_porton_se_dibuja_sin_arco(tmp_path):
    con = construir_plano(CON_GARAJE, 10, 15, tmp_path / "con.dxf")
    modelo = ezdxf.readfile(tmp_path / "con.dxf").modelspace()
    arcos = [e for e in modelo.query("ARC") if e.dxf.layer == "PUERTAS"]

    assert len(arcos) == len(con.puertas["puertas"]) - 1
    assert all(e.dxf.radius < 1 for e in arcos)
    assert generar_escena_3d(con, frozenset({"puertas"}), detalle=True)
    assert generar_ifc(con)


@pytest.mark.parametrize("distribucion, aviso", [
    # Detrás de la sala: el auto no llega.
    ([_ambiente("sala_1", 0, 0, 5, 4), _ambiente("garaje_1", 0, 4, 3, 5)],
     "no tiene acceso desde la calle"),
    # Demasiado corto.
    ([_ambiente("sala_1", 0, 0, 5, 4), _ambiente("garaje_1", 5, 0, 3, 4)],
     "para un auto se necesitan"),
])
def test_se_avisa_si_no_puede_entrar_un_auto(distribucion, aviso, tmp_path):
    plano = construir_plano(distribucion, 10, 15, tmp_path / "p.dxf")

    assert any(aviso in a for a in plano.avisos), plano.avisos


def test_frente_libre_aunque_el_garaje_este_retranqueado():
    garaje = _ambiente("garaje_1", 5, 2, 3, 5)
    distribucion = [_ambiente("sala_1", 0, 0, 5, 4), garaje]

    assert tiene_frente_libre(distribucion, garaje)


def _requerimientos(pisos=1, **extra):
    return RequerimientosArquitectonicos(
        ancho_terreno_m=10, largo_terreno_m=20, numero_pisos=pisos, **extra,
        ambientes=[
            Ambiente(nombre="sala", area_objetivo_m2=18),
            Ambiente(nombre="cocina", area_objetivo_m2=9),
            Ambiente(nombre="dormitorio", cantidad=2, area_objetivo_m2=12),
            Ambiente(nombre="baño", area_objetivo_m2=4),
            # Área insuficiente a propósito: manda el tamaño del auto.
            Ambiente(nombre="garaje", area_objetivo_m2=9),
        ],
    )


def _comprobar_garaje(resultado):
    baja = pry.pisos_de(resultado)[0]
    garaje = next(a for a in baja.distribucion if a["id"] == "garaje_1")

    assert garaje["ancho"] >= 2.7 and garaje["largo"] >= 5.0
    assert garaje["y"] == pytest.approx(min(a["y"] for a in baja.distribucion))
    assert _puertas(baja, True) and _puertas(baja, False)
    assert not any("Garaje" in a for a in baja.avisos), baja.avisos


@pytest.mark.parametrize("pisos", [1, 2])
def test_el_optimizador_pone_el_garaje_a_la_calle(pisos, tmp_path):
    requerimientos = _requerimientos(pisos, retiros=Retiros(frontal=3))

    _comprobar_garaje(generar_plano(requerimientos, tmp_path / "p.dxf"))


def test_el_garaje_sigue_a_la_calle_al_editar(tmp_path):
    ruta = tmp_path / "p.dxf"
    requerimientos = _requerimientos()
    proyecto = pry.proyecto_inicial(
        requerimientos, "Casa",
        generar_plano(requerimientos, ruta), ruta.read_bytes(),
    )

    pry.aplicar_edicion(proyecto, "x", EditRequest(operaciones=[
        EditOperation(tipo="agregar_ambiente", ambiente="estudio")
    ]))

    _comprobar_garaje(pry.version_actual(proyecto)["resultado"])


def test_se_puede_agregar_un_garaje_por_chat(tmp_path):
    ruta = tmp_path / "p.dxf"
    requerimientos = _requerimientos()
    requerimientos.ambientes = requerimientos.ambientes[:-1]
    proyecto = pry.proyecto_inicial(
        requerimientos, "Casa",
        generar_plano(requerimientos, ruta), ruta.read_bytes(),
    )

    pry.aplicar_edicion(proyecto, "x", EditRequest(operaciones=[
        EditOperation(tipo="agregar_ambiente", ambiente="garaje")
    ]))

    _comprobar_garaje(pry.version_actual(proyecto)["resultado"])


def test_si_no_cabe_un_auto_se_explica(tmp_path):
    requerimientos = _requerimientos(retiros=Retiros(frontal=16))

    with pytest.raises(ValueError, match="garaje necesita 2.7 × 5 m"):
        generar_plano(requerimientos, tmp_path / "p.dxf")


@pytest.mark.parametrize("pedido, nombres, esperado", [
    ("garaje", ["sala", "cochera"], "cochera"),
    ("cochera 2", ["garaje", "garaje"], "garaje 2"),
    ("cochera_1", ["garaje"], "garaje_1"),
    ("garaje", ["garaje", "cochera"], "garaje"),
    ("garaje", ["sala"], "garaje"),
    ("sala", ["cochera"], "sala"),
])
def test_garaje_y_cochera_son_lo_mismo(pedido, nombres, esperado):
    assert como_se_llama(pedido, nombres) == esperado


def test_se_encuentra_la_cochera_al_pedir_el_garaje():
    ambientes = [{"id": "cochera_1", "nombre": "cochera"}]

    assert resolver_ambiente(ambientes, "garaje") is ambientes[0]
