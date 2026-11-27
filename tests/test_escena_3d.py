"""Escena de la vista 3D (función pura) y su página HTML."""

import json
import re
from dataclasses import replace

import pytest

from src.services.pipeline import construir_multipisos, construir_plano
from src.ui.escena_3d import (
    ALTURA_ENTREPISO,
    ALTURA_MURO,
    ALTURA_PARAPETO_TERRAZA,
    ALTURA_PUERTA,
    ALTO_PARAPETO_AZOTEA,
    ANTEPECHO,
    ANTEPECHO_ALTO,
    GROSOR_LOSA,
    aclarar,
    documento_3d,
    generar_escena_3d,
    generar_escena_casa,
    json_seguro,
    lado_de_pared,
    piezas_de_mueble,
)
from src.ui.plano_svg import CAPAS_POR_DEFECTO, color_de_ambiente
from tests.plano_fijo import generar_plano_fijo


@pytest.fixture(scope="module")
def plano(tmp_path_factory):
    return generar_plano_fijo(None, tmp_path_factory.mktemp("3d") / "p.dxf")


def _materiales(escena, material):
    return [p for p in escena["piezas"] if p["material"] == material]


def test_es_json_valido_y_encuadra_la_vivienda(plano):
    escena = generar_escena_3d(plano)

    assert json.loads(json.dumps(escena)) == escena
    assert escena["terreno"] == [0, 0, 10, 20]
    assert escena["vivienda"] == [0, 0, 10, 7]


def test_los_muros_conservan_los_huecos_de_puertas_y_ventanas(plano):
    escena = generar_escena_3d(plano)
    muros = plano.aberturas["muros_con_aberturas"]

    assert len(escena["muros"]) == len(getattr(muros, "geoms", [muros]))
    assert all(m["h0"] == 0 and m["h1"] == ALTURA_MURO for m in escena["muros"])
    agujeros = sum(len(m["anillos"]) - 1 for m in escena["muros"])
    assert agujeros == sum(len(p.interiors) for p in getattr(muros, "geoms", [muros]))


def test_un_piso_por_ambiente_con_su_color(plano):
    escena = generar_escena_3d(plano)

    assert [p["id"] for p in escena["pisos"]] == [a["id"] for a in plano.distribucion]
    sala = next(p for p in escena["pisos"] if p["id"] == "sala_1")
    assert sala["color"] == aclarar(color_de_ambiente("sala"), 0.55)


def test_cada_puerta_tiene_dintel_y_hoja(plano):
    escena = generar_escena_3d(plano)
    puertas = len(plano.puertas["puertas"])

    dinteles = [p for p in _materiales(escena, "muro") if p["h0"] == ALTURA_PUERTA]
    hojas = _materiales(escena, "puerta")

    assert len(hojas) == puertas
    assert len(dinteles) >= puertas
    for hoja in hojas:
        largo = max(hoja["x1"] - hoja["x0"], hoja["y1"] - hoja["y0"])
        assert largo == pytest.approx(plano.puertas["puertas"][0]["ancho"])


def test_la_puerta_exterior_abre_hacia_dentro(plano):
    escena = generar_escena_3d(plano)
    exterior = next(
        p for p in plano.puertas["puertas"] if p["ambiente_b"] == "exterior"
    )
    cx, cy = exterior["centro"]

    hoja = min(
        _materiales(escena, "puerta"),
        key=lambda h: abs(h["x0"] - (cx - exterior["ancho"] / 2)) + abs(h["y0"] - cy),
    )

    assert hoja["y0"] >= cy - 1e-6, "la hoja queda dentro de la sala"


def test_cada_ventana_tiene_antepecho_dintel_y_vidrio(plano):
    escena = generar_escena_3d(plano)
    ventanas = plano.ventanas["ventanas"]

    vidrios = _materiales(escena, "vidrio")
    antepechos = [p for p in _materiales(escena, "muro") if p["h0"] == 0]

    assert len(antepechos) == len(ventanas)
    assert len([v for v in vidrios if v["h1"] == ALTURA_PUERTA]) == len(ventanas)
    altos = {v["h0"] for v in vidrios if v["h1"] == ALTURA_PUERTA}
    assert altos <= {ANTEPECHO, ANTEPECHO_ALTO}
    assert ANTEPECHO_ALTO in altos, "la ventana del baño es alta"


@pytest.mark.parametrize("capa, material", [
    ("puertas", "puerta"),
    ("ventanas", "vidrio"),
])
def test_apagar_una_capa_quita_sus_piezas(plano, capa, material):
    sin = generar_escena_3d(plano, CAPAS_POR_DEFECTO - {capa})

    assert not [p for p in _materiales(sin, material) if p["h1"] == ALTURA_PUERTA
                or material == "puerta"]
    assert len(sin["muros"]) == len(generar_escena_3d(plano)["muros"])


def test_sin_muebles_ni_etiquetas(plano):
    completa = generar_escena_3d(plano)
    vacia = generar_escena_3d(plano, frozenset())

    assert len(completa["rotulos"]) == len(plano.distribucion)
    assert vacia["rotulos"] == []
    assert len(vacia["piezas"]) < len(completa["piezas"])
    assert not _materiales(vacia, "colchon")


def test_resaltar_pinta_de_ambar_el_piso_cambiado(plano):
    escena = generar_escena_3d(plano, resaltar=frozenset({"cocina_1"}))
    apagada = generar_escena_3d(
        plano, CAPAS_POR_DEFECTO - {"cambios"}, resaltar=frozenset({"cocina_1"})
    )

    colores = {p["id"]: p["color"] for p in escena["pisos"]}
    assert colores["cocina_1"] == "#FBBF24"
    assert colores["sala_1"] != "#FBBF24"
    assert all(p["color"] != "#FBBF24" for p in apagada["pisos"])


def test_funciona_sin_ventanas_ni_mobiliario(plano):
    escena = generar_escena_3d(replace(plano, ventanas=None, mobiliario=None))

    assert escena["muros"] and not _materiales(escena, "vidrio")


# ---------------- Mobiliario ----------------

@pytest.mark.parametrize("caja, esperado", [
    ((0.05, 0.05, 1.45, 2.0), "s"),
    ((0.05, 2.0, 1.45, 3.95), "n"),
    ((0.05, 1.0, 1.0, 2.4), "o"),
    ((3.0, 1.0, 3.95, 2.4), "e"),
])
def test_lado_de_pared(caja, esperado):
    from shapely.geometry import box

    assert lado_de_pared(caja, box(0, 0, 4, 4)) == esperado


def test_el_cabecero_de_la_cama_va_contra_la_pared(plano):
    ambientes = plano.geometrias["ambientes"]
    # Dormitorio 1 va de y=4 a y=7; cama pegada a la pared norte.
    cama = {"tipo": "cama_matrimonial", "x": 1.0, "y": 5.05, "ancho": 1.4, "largo": 1.9}

    piezas = piezas_de_mueble(cama, ambientes)

    cabecero = max(piezas, key=lambda p: p["h1"])
    assert cabecero["h1"] == pytest.approx(1.0)
    assert cabecero["y1"] == pytest.approx(6.95)
    for pieza in piezas:
        assert 1.0 - 1e-6 <= pieza["x0"] and pieza["x1"] <= 2.4 + 1e-6


def test_un_mueble_desconocido_es_una_caja(plano):
    piezas = piezas_de_mueble(
        {"tipo": "piano", "x": 1, "y": 1, "ancho": 1.5, "largo": 0.6},
        plano.geometrias["ambientes"],
    )

    assert len(piezas) == 1 and piezas[0]["h1"] == 0.75


# ---------------- Casa completa, escaleras y terrazas ----------------

SIN_MUEBLES = CAPAS_POR_DEFECTO - {"muebles"}


def _plano_con(distribucion, ancho, largo, tmp_path):
    return construir_plano(distribucion, ancho, largo, tmp_path / "p.dxf")


def test_base_z_sube_toda_la_escena(plano):
    arriba = generar_escena_3d(plano, base_z=3.0)
    suelo = generar_escena_3d(plano)

    assert all(m["h0"] == 3.0 for m in arriba["muros"])
    assert min(p["h0"] for p in arriba["pisos"]) == 3.0
    assert all(r.get("z") == 3.0 for r in arriba["rotulos"])
    # El mismo número de piezas, solo desplazadas.
    assert len(arriba["piezas"]) == len(suelo["piezas"])
    assert min(p["h0"] for p in arriba["piezas"]) == pytest.approx(
        min(p["h0"] for p in suelo["piezas"]) + 3.0
    )


def test_la_escalera_recta_genera_peldanos_que_suben(tmp_path):
    distribucion = [
        {"id": "sala_1", "nombre": "sala", "x": 0.0, "y": 0.0, "ancho": 4.0, "largo": 5.0},
        {"id": "escalera_1", "nombre": "escalera", "x": 4.0, "y": 0.0,
         "ancho": 1.2, "largo": 5.0},
    ]
    escena = generar_escena_3d(_plano_con(distribucion, 10, 10, tmp_path), SIN_MUEBLES)

    peldanos = sorted(p["h1"] for p in _materiales(escena, "madera"))

    assert len(peldanos) >= 5
    assert peldanos[0] < peldanos[-1] == pytest.approx(ALTURA_ENTREPISO)
    assert peldanos == sorted(peldanos)


def test_la_escalera_cuadrada_es_de_caracol(tmp_path):
    distribucion = [
        {"id": "sala_1", "nombre": "sala", "x": 0.0, "y": 0.0, "ancho": 4.0, "largo": 4.0},
        {"id": "escalera_1", "nombre": "escalera", "x": 4.0, "y": 0.0,
         "ancho": 2.2, "largo": 2.2},
    ]
    escena = generar_escena_3d(_plano_con(distribucion, 10, 10, tmp_path), SIN_MUEBLES)

    postes = [p for p in _materiales(escena, "metal") if p["forma"] == "cilindro"]

    assert postes, "la escalera de caracol tiene un poste central"
    assert postes[0]["h1"] == pytest.approx(ALTURA_ENTREPISO)
    assert len(_materiales(escena, "madera")) >= 10


def test_la_terraza_tiene_parapeto_bajo_macetas_y_pergola(tmp_path):
    distribucion = [
        {"id": "sala_1", "nombre": "sala", "x": 0.0, "y": 0.0, "ancho": 4.0, "largo": 4.0},
        {"id": "terraza_1", "nombre": "terraza", "x": 4.0, "y": 0.0,
         "ancho": 4.0, "largo": 4.0},
    ]
    escena = generar_escena_3d(_plano_con(distribucion, 10, 10, tmp_path))

    parapetos = [m for m in escena["muros"] if m["material"] == "parapeto"]

    assert parapetos, "la terraza baja sus muros a la cadera"
    assert all(m["h1"] == pytest.approx(ALTURA_PARAPETO_TERRAZA) for m in parapetos)
    assert _materiales(escena, "maceta"), "la terraza lleva macetas"
    assert _materiales(escena, "pergola"), "la terraza lleva pérgola de madera"
    # Ningún muro completo coincide con el anillo del parapeto.
    assert all(m["h1"] == ALTURA_MURO for m in escena["muros"] if m["material"] == "muro")


def test_casa_completa_apila_pisos_con_entrepiso_y_azotea(tmp_path):
    baja = [
        {"id": "sala_1", "nombre": "sala", "x": 0.0, "y": 0.0, "ancho": 4.0, "largo": 4.0},
        {"id": "escalera_1", "nombre": "escalera", "x": 4.0, "y": 0.0,
         "ancho": 1.2, "largo": 4.0},
    ]
    alta = [
        {"id": "dormitorio_1", "nombre": "dormitorio", "x": 0.0, "y": 0.0,
         "ancho": 4.0, "largo": 4.0},
        {"id": "escalera_1", "nombre": "escalera", "x": 4.0, "y": 0.0,
         "ancho": 1.2, "largo": 4.0},
    ]
    resultado = construir_multipisos([baja, alta], 10, 10, tmp_path / "p.dxf")

    escena = generar_escena_casa(resultado.pisos)

    # Dos niveles de piso: planta baja a 0 y planta alta elevada.
    niveles = sorted({round(p["h0"], 2) for p in escena["pisos"]})
    assert niveles == [0.0, round(ALTURA_ENTREPISO, 2)]
    assert escena["altura_total"] == pytest.approx(
        2 * ALTURA_ENTREPISO + ALTO_PARAPETO_AZOTEA
    )

    losas = [m for m in escena["prismas"] if m["material"] == "losa"]
    parapetos = [m for m in escena["prismas"] if m["material"] == "parapeto"]
    assert losas and parapetos, "hay entrepiso/azotea y parapeto de azotea"
    # El entrepiso (a la altura del muro de la baja) no cubre la escalera.
    from shapely.geometry import Point, Polygon

    entrepisos = [m for m in losas if round(m["h0"], 2) == round(ALTURA_MURO, 2)]
    hueco = Point(4.6, 2.0)  # dentro de la escalera (x 4..5.2)
    assert not any(
        Polygon(m["anillos"][0], m["anillos"][1:]).covers(hueco) for m in entrepisos
    ), "el entrepiso deja libre el hueco de la escalera"


# ---------------- Página HTML ----------------

def test_el_json_incrustado_no_puede_cerrar_el_script():
    texto = json_seguro({"t": "</script><img src=x onerror=alert(1)>&"})

    assert "<" not in texto and ">" not in texto and "&" not in texto
    assert json.loads(texto) == {"t": "</script><img src=x onerror=alert(1)>&"}


def test_documento_con_nombres_hostiles(plano):
    hostil = [{**a, "nombre": "</script><script>alert(1)</script>"} for a in plano.distribucion]
    geometrias = {
        **plano.geometrias,
        "ambientes": [
            {**a, "nombre": "</script><script>alert(1)</script>"}
            for a in plano.geometrias["ambientes"]
        ],
    }
    pagina = documento_3d(
        generar_escena_3d(replace(plano, distribucion=hostil, geometrias=geometrias)),
        uid="</script>",
    )

    assert "alert(1)</script>" not in pagina
    assert "__ESCENA__" not in pagina and "__UID__" not in pagina
    datos = re.search(r'id="escena">(.*?)</script>', pagina, re.S).group(1)
    assert json.loads(datos)["rotulos"][0]["texto"].startswith("</script>")


RAIZ = __import__("pathlib").Path(__file__).resolve().parent.parent


def test_la_pagina_no_depende_de_internet():
    pagina = documento_3d({"x": 1})

    assert not re.findall(r"https?://(?!www\.w3\.org)", pagina)
    assert '"three": "/app/static/three/build/three.module.min.js"' in pagina
    assert '"three/addons/": "/app/static/three/examples/jsm/"' in pagina


def test_la_copia_local_de_three_esta_completa():
    base = RAIZ / "static" / "three"
    nucleo = (base / "build" / "three.module.min.js").read_text(encoding="utf-8")

    assert 'const t="160"' in nucleo[:300]
    assert (base / "LICENSE").read_text(encoding="utf-8").startswith("The MIT License")
    # Cada módulo importado (por la página o por otro módulo) existe.
    pagina = (RAIZ / "src" / "ui" / "visor_3d.html").read_text(encoding="utf-8")
    pendientes = [
        base / "examples" / "jsm" / ruta
        for ruta in re.findall(r'"three/addons/([^"]+)"', pagina)
    ]
    vistos = set()
    while pendientes:
        modulo = pendientes.pop()
        assert modulo.exists(), modulo
        if modulo in vistos:
            continue
        vistos.add(modulo)
        for relativa in re.findall(r"from '(\.[^']+)'", modulo.read_text(encoding="utf-8")):
            pendientes.append((modulo.parent / relativa).resolve())
    assert len(vistos) >= 10


def test_la_app_sirve_los_estaticos_como_javascript():
    import mimetypes
    import tomllib

    import app  # noqa: F401  registra el tipo de .js

    config = tomllib.loads((RAIZ / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
    assert config["server"]["enableStaticServing"] is True
    assert mimetypes.guess_type("three.module.min.js")[0] == "text/javascript"


def test_un_texto_con_marcadores_no_inyecta_html():
    """La escena se inserta la última: sus textos no se reemplazan después."""
    texto = "__PANTALLA_COMPLETA__ __UID__"

    pagina = documento_3d({"t": texto}, uid="u")

    datos = re.search(r'id="escena">(.*?)</script>', pagina, re.S).group(1)
    assert json.loads(datos) == {"t": texto}
    assert pagina.count('id="pantalla-completa"') == 1
