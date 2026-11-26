"""Abrir DXF dibujados con otros programas (sin los metadatos del agente)."""

import math

import ezdxf
import pytest
from shapely.affinity import rotate
from shapely.geometry import box
from shapely.ops import unary_union

from src.ai.edit_interpreter import EditOperation, EditRequest
from src.cad.importador_dxf import importar_dxf
from src.cad.nombres_dxf import es_nombre, planta_de_texto, tipo_desde_texto
from src.ui import proyecto as pry

# (texto, x, y, ancho, largo) en metros
CASA = [
    ("LIVING", 0, 0, 5, 4),
    ("KITCHEN", 5, 0, 3, 4),
    ("BEDROOM 1", 0, 4, 4, 3.5),
    ("WC", 4, 4, 1.8, 3.5),
    ("Dorm. 2", 5.8, 4, 2.2, 3.5),
]
TIPOS_CASA = ["sala", "cocina", "dormitorio", "baño", "dormitorio"]


def _documento(unidades):
    documento = ezdxf.new("R2010")
    documento.header["$INSUNITS"] = unidades
    return documento


def _texto(msp, texto, x, y, escala, mtext=False):
    if mtext:
        msp.add_mtext(texto, dxfattribs={
            "insert": (x * escala, y * escala), "char_height": 0.2 * escala,
            "layer": "A-ANNO-ROOM",
        })
    else:
        msp.add_text(texto, dxfattribs={
            "insert": (x * escala, y * escala), "height": 0.2 * escala,
            "layer": "A-ANNO-ROOM",
        })


def _contornos(ruta, casa=CASA, unidades=4, escala=1000, giro=0):
    """Cada habitación como polilínea cerrada, más el perímetro y una cama."""
    documento = _documento(unidades)
    msp = documento.modelspace()

    def poner(poligono, capa):
        poligono = rotate(poligono, giro, origin=(0, 0))
        msp.add_lwpolyline(
            [(x * escala, y * escala) for x, y in poligono.exterior.coords[:-1]],
            close=True, dxfattribs={"layer": capa},
        )

    for texto, x, y, ancho, largo in casa:
        poner(box(x, y, x + ancho, y + largo), "A-AREA")
        centro = rotate(box(x, y, x + ancho, y + largo), giro, origin=(0, 0)).centroid
        if texto:
            _texto(msp, texto, centro.x, centro.y, escala)
        _texto(msp, f"{ancho * largo:.2f} m2", centro.x, centro.y - 0.4, escala)

    poner(unary_union([box(x, y, x + a, y + l) for _, x, y, a, l in casa]).envelope, "A-WALL")

    cama = documento.blocks.new("CAMA")
    cama.add_lwpolyline([(0, 0), (1.6 * escala, 0), (1.6 * escala, 2 * escala), (0, 2 * escala)], close=True)
    msp.add_blockref("CAMA", (0.5 * escala, 4.5 * escala), dxfattribs={"layer": "A-FURN"})

    documento.saveas(ruta)
    return ruta


def _muros(casa, puertas):
    """Polígono de muros (0,15 m a eje) con los vanos de puerta recortados."""
    ejes = unary_union([box(x, y, x + a, y + l).exterior for _, x, y, a, l in casa])
    muros = ejes.buffer(0.075, cap_style="square", join_style="mitre")
    vanos = [box(cx - 0.45, cy - 0.2, cx + 0.45, cy + 0.2) if horizontal
             else box(cx - 0.2, cy - 0.45, cx + 0.2, cy + 0.45)
             for cx, cy, horizontal in puertas]
    return muros.difference(unary_union(vanos))


PUERTAS = [
    (2.5, 0, True),      # entrada a la sala
    (5, 2, False),       # sala - cocina
    (2, 4, True),        # sala - dormitorio 1
    (4.5, 4, True),      # sala - baño
    (6.9, 4, True),      # cocina - dormitorio 2
]


def _dibujar_muros(destino, muros, escala, capa):
    for parte in getattr(muros, "geoms", [muros]):
        for anillo in [parte.exterior, *parte.interiors]:
            destino.add_lwpolyline(
                [(x * escala, y * escala) for x, y in anillo.coords[:-1]],
                close=True, dxfattribs={"layer": capa},
            )


def _solo_muros(ruta, unidades=5, escala=100, en_bloque=False):
    documento = _documento(unidades)
    msp = documento.modelspace()
    muros = _muros(CASA, PUERTAS)

    if en_bloque:
        bloque = documento.blocks.new("PLANTA")
        _dibujar_muros(bloque, muros, escala, "0")
        msp.add_blockref("PLANTA", (0, 0), dxfattribs={"layer": "MUROS"})
    else:
        _dibujar_muros(msp, muros, escala, "A-WALL")

    for texto, x, y, ancho, largo in CASA:
        _texto(msp, texto, x + ancho / 2, y + largo / 2, escala, mtext=True)

    documento.saveas(ruta)
    return ruta


def _por_tipo(distribucion):
    return sorted(
        (a["nombre"], round(a["ancho"] * a["largo"], 1)) for a in distribucion
    )


def _comparte_arista(a, b):
    return box(a["x"], a["y"], a["x"] + a["ancho"], a["y"] + a["largo"]).intersection(
        box(b["x"], b["y"], b["x"] + b["ancho"], b["y"] + b["largo"])
    ).length > 0.5


# ---------- Nombres ----------

@pytest.mark.parametrize("texto, tipo", [
    ("LIVING", "sala"), ("Sala de estar", "sala"), ("KITCHEN", "cocina"),
    ("Dorm. 2", "dormitorio"), ("DORMITORIO PRINCIPAL", "dormitorio principal"),
    ("Master Bedroom", "dormitorio principal"), ("BAÑO PRINC.", "baño"),
    ("S.H.", "baño"), ("WC", "baño"), ("Hall", "pasillo"),
    ("LAVANDERÍA", "lavandería"), ("Garage", "garaje"), ("STAIRS", "escalera"),
    ("Ropero", "closet"), ("Despensa", "depósito"), ("Balcón", "terraza"),
    ("Piscina", None),
])
def test_traduce_los_nombres_del_dibujo(texto, tipo):
    assert tipo_desde_texto(texto) == tipo


@pytest.mark.parametrize("texto", ["12.50 m2", "3.20", "A= 9.5 m²", "N.P.T. +0.15"])
def test_las_cotas_y_areas_no_son_nombres(texto):
    assert not es_nombre(texto)


def test_etiquetas_de_planta():
    assert planta_de_texto("PLANTA ALTA") == "alta"
    assert planta_de_texto("Segundo piso") == "alta"
    assert planta_de_texto("PRIMER PISO") == "baja"
    assert planta_de_texto("Cocina") is None


# ---------- Contornos ----------

def test_contornos_en_milimetros(tmp_path):
    distribuciones, ancho, largo, notas = importar_dxf(_contornos(tmp_path / "a.dxf"))

    assert len(distribuciones) == 1
    casa = distribuciones[0]
    assert _por_tipo(casa) == sorted(
        (t, round(a * l, 1)) for t, (_, _, _, a, l) in zip(TIPOS_CASA, CASA)
    )
    sala = next(a for a in casa if a["nombre"] == "sala")
    cocina = next(a for a in casa if a["nombre"] == "cocina")
    assert _comparte_arista(sala, cocina)
    assert (ancho, largo) == (10, 9.5)       # casa más 1 m por lado
    assert sala["x"] == 1 and sala["y"] == 1
    assert "Unidades del dibujo: milímetros." in notas
    assert any("detectadas por sus contornos" in n for n in notas)


def test_un_plano_girado_se_endereza(tmp_path):
    distribuciones, _, _, notas = importar_dxf(_contornos(tmp_path / "a.dxf", giro=30))

    assert _por_tipo(distribuciones[0]) == sorted(
        (t, round(a * l, 1)) for t, (_, _, _, a, l) in zip(TIPOS_CASA, CASA)
    )
    assert any("girado 30°" in n for n in notas)


def test_sin_unidades_las_deduce(tmp_path):
    distribuciones, _, _, notas = importar_dxf(
        _contornos(tmp_path / "a.dxf", unidades=0, escala=100)
    )

    assert sum(a["ancho"] * a["largo"] for a in distribuciones[0]) == pytest.approx(60, abs=0.1)
    assert any("supuse centímetros" in n for n in notas)


def test_habitacion_en_l_se_aproxima_a_rectangulo(tmp_path):
    documento = _documento(6)
    msp = documento.modelspace()
    msp.add_lwpolyline([(0, 0), (6, 0), (6, 3), (3, 3), (3, 5), (0, 5)],
                       close=True, dxfattribs={"layer": "AREAS"})
    msp.add_lwpolyline([(3, 3), (6, 3), (6, 5), (3, 5)], close=True,
                       dxfattribs={"layer": "AREAS"})
    msp.add_text("SALA", dxfattribs={"insert": (1, 1), "height": 0.2})
    msp.add_text("COCINA", dxfattribs={"insert": (4.5, 4), "height": 0.2})
    documento.saveas(tmp_path / "l.dxf")

    distribuciones, _, _, notas = importar_dxf(tmp_path / "l.dxf")

    sala = next(a for a in distribuciones[0] if a["nombre"] == "sala")
    assert (sala["ancho"], sala["largo"]) == (6, 3)
    assert any("Sala 1 tenía forma irregular" in n and "6.0 m²" in n for n in notas)


# ---------- Muros ----------

@pytest.mark.parametrize("en_bloque", [False, True])
def test_solo_muros_en_centimetros(tmp_path, en_bloque):
    proyecto = pry.abrir_proyecto(
        _solo_muros(tmp_path / "m.dxf", en_bloque=en_bloque).read_bytes(), "m.dxf"
    )

    plano = pry.version_actual(proyecto)["resultado"]
    assert sorted(a["nombre"] for a in plano.distribucion) == sorted(TIPOS_CASA)
    for (texto, _, _, ancho, largo), tipo in zip(CASA, TIPOS_CASA):
        areas = [a["ancho"] * a["largo"] for a in plano.distribucion if a["nombre"] == tipo]
        assert any(abs(area - ancho * largo) <= 0.1 * ancho * largo for area in areas), texto
    assert plano.validacion["distribucion_conectada"]
    assert "detectadas por los muros" in proyecto["mensajes"][0]["texto"]


# ---------- Nombres desconocidos y renombrar ----------

def test_sin_nombre_y_renombrar_por_chat(tmp_path):
    casa = [("", 0, 0, 4, 3), ("", 4, 0, 3, 3), ("BAÑO", 7, 0, 2, 3)]
    proyecto = pry.abrir_proyecto(
        _contornos(tmp_path / "a.dxf", casa=casa, unidades=6, escala=1).read_bytes(),
        "a.dxf",
    )
    ids = {a["id"] for a in pry.version_actual(proyecto)["resultado"].distribucion}
    assert {"ambiente_1", "ambiente_2", "bano_1"} <= ids
    assert "llama cocina al ambiente 1" in proyecto["mensajes"][0]["texto"]

    pry.aplicar_edicion(proyecto, "llama cocina al ambiente 1", EditRequest(operaciones=[
        EditOperation(tipo="renombrar_ambiente", ambiente="ambiente 1", nombre_nuevo="cocina"),
    ]))

    actual = pry.version_actual(proyecto)["resultado"].distribucion
    assert "cocina_1" in {a["id"] for a in actual}
    assert "ambiente_1" not in {a["id"] for a in actual}
    assert "Ambiente 1 ahora es Cocina 1" in proyecto["mensajes"][-1]["texto"]


def test_renombrar_a_un_tipo_fuera_del_catalogo_se_rechaza(tmp_path):
    casa = [("", 0, 0, 4, 3), ("SALA", 4, 0, 4, 3)]
    proyecto = pry.abrir_proyecto(
        _contornos(tmp_path / "a.dxf", casa=casa, unidades=6, escala=1).read_bytes(),
        "a.dxf",
    )
    with pytest.raises(ValueError, match="tipos disponibles"):
        pry.aplicar_edicion(proyecto, "x", EditRequest(operaciones=[
            EditOperation(tipo="renombrar_ambiente", ambiente="ambiente 1", nombre_nuevo="piscina"),
        ]))


# ---------- Dos plantas ----------

def test_dos_grupos_son_dos_plantas_con_la_escalera_alineada(tmp_path):
    documento = _documento(6)
    msp = documento.modelspace()
    baja = [("SALA", 0, 0, 5, 4), ("COCINA", 5, 0, 3, 4), ("ESCALERA", 0, 4, 2.5, 2)]
    alta = [("DORMITORIO", 0, 0, 5, 4), ("BAÑO", 5, 0, 3, 4), ("ESCALERA", 0, 4, 2.5, 2)]
    for grupo, dx, titulo in ((baja, 0, "PLANTA BAJA"), (alta, 20, "PLANTA ALTA")):
        for texto, x, y, ancho, largo in grupo:
            msp.add_lwpolyline(
                [(x + dx, y), (x + dx + ancho, y), (x + dx + ancho, y + largo), (x + dx, y + largo)],
                close=True, dxfattribs={"layer": "AREAS"},
            )
            msp.add_text(texto, dxfattribs={"insert": (x + dx + 0.5, y + 0.5), "height": 0.2})
        msp.add_text(titulo, dxfattribs={"insert": (dx + 2, -1.5), "height": 0.4})
    documento.saveas(tmp_path / "dos.dxf")

    proyecto = pry.abrir_proyecto((tmp_path / "dos.dxf").read_bytes(), "dos.dxf")

    abajo, arriba = pry.pisos_de(pry.version_actual(proyecto)["resultado"])
    assert {a["nombre"] for a in abajo.distribucion} == {"sala", "cocina", "escalera"}
    assert {a["nombre"] for a in arriba.distribucion} == {"dormitorio", "baño", "escalera"}

    def escalera(piso):
        return next(
            tuple(a[k] for k in ("x", "y", "ancho", "largo"))
            for a in piso.distribucion if a["nombre"] == "escalera"
        )

    assert escalera(abajo) == escalera(arriba)
    assert not any("escalera no coincide" in a for a in arriba.avisos)


# ---------- Errores y edición ----------

def test_un_dxf_sin_habitaciones_da_un_error_claro(tmp_path):
    documento = _documento(6)
    documento.modelspace().add_text("Hola", dxfattribs={"insert": (0, 0)})
    documento.saveas(tmp_path / "t.dxf")

    with pytest.raises(ValueError, match="No encontré habitaciones"):
        pry.abrir_proyecto((tmp_path / "t.dxf").read_bytes(), "t.dxf")


def test_tras_importar_se_edita_y_se_reabre_como_propio(tmp_path):
    proyecto = pry.abrir_proyecto(_contornos(tmp_path / "a.dxf").read_bytes(), "a.dxf")

    pry.aplicar_edicion(proyecto, "amplía la sala", EditRequest(operaciones=[
        EditOperation(tipo="modificar_area", ambiente="sala", area_objetivo=23),
    ]))
    otra_vez = pry.abrir_proyecto(pry.version_actual(proyecto)["dxf"], "v2.dxf")

    def geometria(p):
        return sorted(
            (a["id"], *(round(a[k], 3) for k in ("x", "y", "ancho", "largo")))
            for a in pry.version_actual(p)["resultado"].distribucion
        )

    assert geometria(otra_vez) == geometria(proyecto)
    sala = next(
        a for a in pry.version_actual(proyecto)["resultado"].distribucion
        if a["nombre"] == "sala"
    )
    assert math.isclose(sala["ancho"] * sala["largo"], 23, rel_tol=0.05)
    # Reabierto por la vía propia: sin notas de importación.
    assert "Importé" not in otra_vez["mensajes"][0]["texto"]
