"""Agregar y quitar ambientes, y casas de dos plantas."""

import pytest
from shapely.geometry import box

from src.ai.edit_interpreter import EditOperation, EditRequest
from src.models.defaults import calcular_areas_predeterminadas
from src.models.requirements import Ambiente, RequerimientosArquitectonicos
from src.planning.layout_optimizer import (
    contorno,
    relaciones_de_planta,
    repartir_en_plantas,
)
from src.services.edicion_multipisos import editar_plano_multipisos
from src.services.pipeline import (
    construir_multipisos,
    construir_plano,
    editar_plano,
    generar_plano,
)
from src.ui import proyecto as pry
from src.ui.plano_svg import etiquetas_ambientes


def _amb(identificador, x, y, ancho, largo):
    return {
        "id": identificador, "nombre": identificador.rsplit("_", 1)[0],
        "x": x, "y": y, "ancho": ancho, "largo": largo,
    }


UNA_PLANTA = [
    _amb("sala_1", 0, 0, 5, 3.5),
    _amb("cocina_1", 5, 0, 3, 3.5),
    _amb("pasillo_1", 0, 3.5, 8, 1.2),
    _amb("dormitorio_1", 0, 4.7, 3.5, 3),
    _amb("bano_1", 3.5, 4.7, 2, 3),
    _amb("dormitorio_2", 5.5, 4.7, 2.5, 3),
]

PLANTA_BAJA = [
    _amb("sala_1", 0, 0, 5, 4),
    _amb("cocina_1", 5, 0, 3, 4),
    _amb("escalera_1", 0, 4, 2.5, 1.6),
    _amb("comedor_1", 2.5, 4, 5.5, 3),
    _amb("bano_1", 0, 5.6, 2.5, 1.4),
]

PLANTA_ALTA = [
    _amb("escalera_1", 0, 4, 2.5, 1.6),
    _amb("pasillo_1", 2.5, 3.5, 1.5, 3.5),
    _amb("dormitorio_1", 4, 3.5, 4, 3.5),
    _amb("dormitorio_2", 0, 0, 4, 3.5),
    _amb("bano_2", 0, 5.6, 2.5, 1.4),
]


def _solicitud(**operacion):
    return EditRequest(operaciones=[EditOperation(**operacion)])


def _editar(tmp_path, **operacion):
    base = tmp_path / "base.dxf"
    construir_plano(UNA_PLANTA, 12, 14, base)
    return editar_plano(str(base), str(tmp_path / "e.dxf"), _solicitud(**operacion))


@pytest.fixture
def casa(tmp_path):
    return construir_multipisos(
        [PLANTA_BAJA, PLANTA_ALTA], 12, 14, tmp_path / "casa.dxf"
    )


def _editar_casa(casa, tmp_path, **operacion):
    return editar_plano_multipisos(
        casa, str(tmp_path / "e.dxf"), _solicitud(**operacion)
    )


def _ids(plano):
    return [a["id"] for a in plano.distribucion]


def _sin_solapes(distribucion):
    cajas = [
        box(a["x"], a["y"], a["x"] + a["ancho"], a["y"] + a["largo"])
        for a in distribucion
    ]
    return all(
        a.intersection(b).area < 1e-6
        for i, a in enumerate(cajas) for b in cajas[i + 1:]
    )


def _escalera(plano):
    escalera = next(a for a in plano.distribucion if a["id"] == "escalera_1")
    return tuple(escalera[k] for k in ("x", "y", "ancho", "largo"))


# ---------------- Una planta: agregar y quitar ----------------

def test_agregar_un_ambiente_junto_a_otro(tmp_path):
    r = _editar(tmp_path, tipo="agregar_ambiente", ambiente="estudio",
                area_objetivo=8, referencia="sala", relacion="junto_a")

    plano = r["plano"]
    assert "estudio_1" in _ids(plano)
    assert _sin_solapes(plano.distribucion)
    estudio = next(a for a in plano.distribucion if a["id"] == "estudio_1")
    assert estudio["ancho"] * estudio["largo"] == pytest.approx(8, rel=0.1)
    assert any(
        {a["ambiente_a"], a["ambiente_b"]} == {"estudio_1", "sala_1"}
        for a in plano.validacion["adyacencias"]
    )
    assert r["modificaciones"][0]["accion"] == "agregado"


def test_agregar_numera_a_continuacion(tmp_path):
    r = _editar(tmp_path, tipo="agregar_ambiente", ambiente="dormitorio",
                area_objetivo=8)

    assert r["modificaciones"][0]["id"] == "dormitorio_3"


def test_no_se_agrega_algo_fuera_del_catalogo(tmp_path):
    with pytest.raises(ValueError, match="tipos disponibles"):
        _editar(tmp_path, tipo="agregar_ambiente", ambiente="piscina")


def test_no_se_agrega_lo_que_no_cabe(tmp_path):
    with pytest.raises(ValueError, match="No es posible agregar"):
        _editar(tmp_path, tipo="agregar_ambiente", ambiente="estudio",
                area_objetivo=300)


def test_quitar_un_ambiente(tmp_path):
    r = _editar(tmp_path, tipo="quitar_ambiente", ambiente="dormitorio 2")

    assert "dormitorio_2" not in _ids(r["plano"])
    assert _sin_solapes(r["plano"].distribucion)
    assert r["plano"].validacion["distribucion_conectada"]
    assert pry.resumen_modificaciones(r["modificaciones"])[0] == "Quité Dormitorio 2"


def test_quitar_un_nombre_repetido_quita_el_ultimo(tmp_path):
    r = _editar(tmp_path, tipo="quitar_ambiente", ambiente="dormitorio")

    assert r["modificaciones"][0]["id"] == "dormitorio_2"


def test_una_planta_unica_no_tiene_planta_alta(tmp_path):
    with pytest.raises(ValueError, match="una sola planta"):
        _editar(tmp_path, tipo="quitar_ambiente", ambiente="bano", planta="alta")


# ---------------- Reparto y generación de dos plantas ----------------

def test_un_bano_baja_si_arriba_hay_dos_o_mas():
    ambientes = [Ambiente(nombre="sala"), Ambiente(nombre="dormitorio", cantidad=3),
                 Ambiente(nombre="baño", cantidad=2)]

    baja, alta = repartir_en_plantas(ambientes)

    assert [(a.nombre, a.cantidad) for a in baja] == [("sala", 1), ("baño", 1)]
    assert [(a.nombre, a.cantidad) for a in alta] == [("dormitorio", 3), ("baño", 1)]
    assert ambientes[2].cantidad == 2, "no modifica la entrada"


def test_la_terraza_sube_cuando_hay_privados_arriba():
    ambientes = [Ambiente(nombre="sala"), Ambiente(nombre="dormitorio", cantidad=2),
                 Ambiente(nombre="terraza")]

    baja, alta = repartir_en_plantas(ambientes)

    assert "terraza" not in [a.nombre for a in baja]
    assert "terraza" in [a.nombre for a in alta]


def test_la_terraza_se_queda_abajo_sin_planta_alta():
    ambientes = [Ambiente(nombre="sala"), Ambiente(nombre="cocina"),
                 Ambiente(nombre="terraza")]

    baja, alta = repartir_en_plantas(ambientes)

    assert alta == []
    assert "terraza" in [a.nombre for a in baja]


def test_las_relaciones_imposibles_en_una_planta_se_descartan():
    ambientes = [Ambiente(nombre="sala"), Ambiente(nombre="cocina")]
    relaciones = [["sala", "cocina"], ["sala", "dormitorio"], ["sala", "sala"]]

    assert relaciones_de_planta(relaciones, ambientes) == [["sala", "cocina"]]


def _dos_pisos(relaciones):
    req = RequerimientosArquitectonicos(
        ancho_terreno_m=10, largo_terreno_m=20, numero_pisos=2,
        area_total_vivienda_m2=120,
        ambientes=[Ambiente(nombre="sala"), Ambiente(nombre="cocina"),
                   Ambiente(nombre="dormitorio", cantidad=2),
                   Ambiente(nombre="baño", cantidad=2)],
        relaciones_adyacencia=relaciones,
    )
    return calcular_areas_predeterminadas(req)


def test_dos_pisos_con_relaciones_ya_no_fallan(tmp_path):
    """Antes: «No existe el ambiente 'sala'» al resolver la planta alta."""
    req = _dos_pisos([["sala", "cocina"], ["sala", "dormitorio"]])

    casa = generar_plano(req, tmp_path / "p.dxf")

    assert any("sala con dormitorio" in a for a in casa.pisos[0].avisos)
    baja, alta = casa.pisos
    assert _escalera(baja) == _escalera(alta)
    bx0, by0, bx1, by1 = contorno(baja.distribucion)
    ax0, ay0, ax1, ay1 = contorno(alta.distribucion)
    assert ax0 >= bx0 - 0.05 and ay0 >= by0 - 0.05
    assert ax1 <= bx1 + 0.05 and ay1 <= by1 + 0.05
    ids = [i for p in casa.pisos for i in _ids(p) if i != "escalera_1"]
    assert len(ids) == len(set(ids))


def test_una_relacion_con_un_ambiente_inexistente_sigue_fallando(tmp_path):
    with pytest.raises(ValueError, match="No existe el ambiente 'garaje'"):
        generar_plano(_dos_pisos([["sala", "garaje"]]), tmp_path / "p.dxf")


def test_en_la_planta_alta_se_numeran_los_que_no_son_el_primero():
    etiquetas = etiquetas_ambientes(PLANTA_ALTA)

    assert etiquetas["bano_2"] == "Bano 2"


# ---------------- Edición de dos plantas ----------------

def test_agregar_va_a_la_planta_habitual(casa, tmp_path):
    r = _editar_casa(casa, tmp_path, tipo="agregar_ambiente",
                     ambiente="estudio", area_objetivo=6)

    baja, alta = r["plano"].pisos
    assert "estudio_1" in _ids(baja) and "estudio_1" not in _ids(alta)
    assert _escalera(baja) == _escalera(alta) == _escalera(casa.pisos[0])
    assert r["modificaciones"][0]["planta"] == "baja"


def test_quitar_arriba(casa, tmp_path):
    r = _editar_casa(casa, tmp_path, tipo="quitar_ambiente", ambiente="dormitorio 2")

    baja, alta = r["plano"].pisos
    assert "dormitorio_2" not in _ids(alta)
    assert baja.distribucion == casa.pisos[0].distribucion
    assert _escalera(alta) == _escalera(casa.pisos[1])


def test_ampliar_abajo_mantiene_la_escalera(casa, tmp_path):
    r = _editar_casa(casa, tmp_path, tipo="modificar_area",
                     ambiente="sala", area_objetivo=23)

    baja, alta = r["plano"].pisos
    sala = next(a for a in baja.distribucion if a["id"] == "sala_1")
    assert sala["ancho"] * sala["largo"] == pytest.approx(23, rel=0.04)
    assert _escalera(baja) == _escalera(alta)
    assert _sin_solapes(baja.distribucion)


def test_mover_a_la_otra_planta(casa, tmp_path):
    r = _editar_casa(casa, tmp_path, tipo="mover_ambiente", ambiente="dormitorio 2",
                     referencia="sala", relacion="junto_a")

    baja, alta = r["plano"].pisos
    assert "dormitorio_2" not in _ids(alta)
    (hecho,) = r["modificaciones"]
    assert hecho["accion"] == "cambiado_de_planta" and hecho["planta"] == "baja"
    assert hecho["id"] in _ids(baja)


def test_la_escalera_no_se_toca(casa, tmp_path):
    with pytest.raises(ValueError, match="une las dos plantas"):
        _editar_casa(casa, tmp_path, tipo="quitar_ambiente", ambiente="escalera")


def test_nombre_en_ambas_plantas_pide_aclarar(casa, tmp_path):
    with pytest.raises(ValueError, match="en las dos plantas"):
        _editar_casa(casa, tmp_path, tipo="modificar_area", ambiente="bano",
                     area_objetivo=5)


def test_ambiente_que_no_esta_en_la_planta_pedida(casa, tmp_path):
    with pytest.raises(ValueError, match="en la planta baja"):
        _editar_casa(casa, tmp_path, tipo="quitar_ambiente",
                     ambiente="dormitorio 1", planta="baja")


def test_el_proyecto_de_dos_plantas_admite_cambios_y_deshacer(casa):
    proyecto = pry.proyecto_inicial(None, "casa", casa, casa.ruta_dxf.read_bytes())
    assert "arriba" in proyecto["mensajes"][1]["texto"]

    pry.aplicar_edicion(
        proyecto, "quita el dormitorio 2",
        _solicitud(tipo="quitar_ambiente", ambiente="dormitorio 2"),
    )

    assert "Quité Dormitorio 2 (planta alta)" in proyecto["mensajes"][-1]["texto"]
    assert pry.deshacer(proyecto)
    assert "dormitorio_2" in _ids(pry.version_actual(proyecto)["resultado"].pisos[1])


# ---------------- Intérprete ----------------

def test_el_interprete_admite_las_operaciones_nuevas():
    EditOperation(tipo="agregar_ambiente", ambiente="estudio", planta="alta")
    EditOperation(tipo="quitar_ambiente", ambiente="baño")
    with pytest.raises(ValueError):
        EditOperation(tipo="quitar_ambiente", ambiente="baño", planta="sotano")


# ---------- Abrir un DXF de dos plantas ----------

def _geometrias(distribucion):
    return {
        a["id"]: tuple(round(a[k], 3) for k in ("x", "y", "ancho", "largo"))
        for a in distribucion
    }


def _dxf_dos_plantas(ruta, alta=PLANTA_ALTA):
    construir_multipisos([PLANTA_BAJA, alta], 8, 15, ruta)
    return ruta.read_bytes()


def test_abrir_un_dxf_de_dos_plantas_recupera_cada_planta(tmp_path):
    dxf = _dxf_dos_plantas(tmp_path / "casa.dxf")

    proyecto = pry.abrir_proyecto(dxf, "casa.dxf")

    pisos = pry.pisos_de(pry.version_actual(proyecto)["resultado"])
    assert [_geometrias(p.distribucion) for p in pisos] == [
        _geometrias(PLANTA_BAJA), _geometrias(PLANTA_ALTA),
    ]
    assert pisos[1].geometrias["terreno"].bounds == (0, 0, 8, 15)
    assert "2 plantas" in proyecto["mensajes"][0]["texto"]
    assert "arriba" in proyecto["mensajes"][0]["texto"]


def test_el_dxf_reabierto_se_puede_editar_y_volver_a_abrir(tmp_path):
    proyecto = pry.abrir_proyecto(
        _dxf_dos_plantas(tmp_path / "casa.dxf"), "casa.dxf"
    )

    pry.aplicar_edicion(
        proyecto, "quita un baño arriba",
        _solicitud(tipo="quitar_ambiente", ambiente="baño", planta="alta"),
    )
    otra_vez = pry.abrir_proyecto(
        pry.version_actual(proyecto)["dxf"], "casa_v2.dxf"
    )

    editado = pry.pisos_de(pry.version_actual(proyecto)["resultado"])
    reabierto = pry.pisos_de(pry.version_actual(otra_vez)["resultado"])
    assert [_geometrias(p.distribucion) for p in reabierto] == [
        _geometrias(p.distribucion) for p in editado
    ]
    assert "bano_2" not in _geometrias(reabierto[1].distribucion)


def test_al_abrir_se_renumeran_los_ids_repetidos_entre_plantas(tmp_path):
    # Los DXF anteriores repetían "bano_1" en las dos plantas.
    antigua = [
        {**a, "id": "bano_1"} if a["id"] == "bano_2" else a
        for a in PLANTA_ALTA
    ]
    proyecto = pry.abrir_proyecto(
        _dxf_dos_plantas(tmp_path / "casa.dxf", antigua), "casa.dxf"
    )

    baja, alta = pry.pisos_de(pry.version_actual(proyecto)["resultado"])
    ids = [a["id"] for a in baja.distribucion + alta.distribucion]
    assert ids.count("escalera_1") == 2
    assert ids.count("bano_1") == 1 and "bano_2" in ids


def test_el_editor_de_una_planta_rechaza_un_dxf_de_dos(tmp_path):
    entrada = tmp_path / "casa.dxf"
    _dxf_dos_plantas(entrada)

    with pytest.raises(ValueError, match="varias plantas"):
        editar_plano(
            entrada, tmp_path / "salida.dxf",
            _solicitud(tipo="quitar_ambiente", ambiente="comedor"),
        )

