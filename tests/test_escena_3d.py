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


def _caja_de(p):
    from shapely.geometry import box

    return box(p["x0"], p["y0"], p["x1"], p["y1"])


def _peldanos(escena):
    return [p for p in _materiales(escena, "madera") if p["forma"] == "caja"]


def test_la_escalera_genera_peldanos_flotantes_que_suben(tmp_path):
    distribucion = [
        {"id": "sala_1", "nombre": "sala", "x": 0.0, "y": 0.0, "ancho": 4.0, "largo": 5.0},
        {"id": "escalera_1", "nombre": "escalera", "x": 4.0, "y": 0.0,
         "ancho": 1.2, "largo": 5.0},
    ]
    plano = _plano_con(distribucion, 10, 10, tmp_path)
    escena = generar_escena_3d(plano, SIN_MUEBLES)
    escalera = next(a for a in plano.geometrias["ambientes"] if a["id"] == "escalera_1")

    peldanos = _peldanos(escena)
    altos = [p["h1"] for p in peldanos]

    assert len(peldanos) >= 10
    assert altos == sorted(altos), "los peldaños suben"
    # El último escalón es el piso de arriba: el tramo llega justo debajo.
    assert altos[-1] < ALTURA_ENTREPISO
    assert altos[-1] == pytest.approx(ALTURA_ENTREPISO, abs=0.2)
    # Cada peldaño mide una contrahuella, no es un bloque desde el suelo.
    assert all(p["h1"] - p["h0"] <= 0.2 for p in peldanos)
    holgado = escalera["poligono"].buffer(1e-3)
    assert all(holgado.covers(_caja_de(p)) for p in peldanos), "dentro del ambiente"


def test_la_escalera_cuadrada_es_de_caracol_con_peldanos_girados(tmp_path):
    distribucion = [
        {"id": "sala_1", "nombre": "sala", "x": 0.0, "y": 0.0, "ancho": 4.0, "largo": 4.0},
        {"id": "escalera_1", "nombre": "escalera", "x": 4.0, "y": 0.0,
         "ancho": 2.2, "largo": 2.2},
    ]
    escena = generar_escena_3d(_plano_con(distribucion, 10, 10, tmp_path), SIN_MUEBLES)

    postes = [p for p in _materiales(escena, "metal") if p["forma"] == "cilindro"]
    girados = [p for p in _materiales(escena, "madera") if p.get("giro")]

    assert postes, "la escalera de caracol tiene un poste central"
    assert postes[0]["h1"] >= ALTURA_ENTREPISO
    assert len(girados) >= 10, "los peldaños giran alrededor del poste"


def _casa_con_escalera(tmp_path, terraza=False):
    baja = [
        {"id": "sala_1", "nombre": "sala", "x": 0.0, "y": 0.0, "ancho": 4.0, "largo": 4.5},
        {"id": "escalera_1", "nombre": "escalera", "x": 4.0, "y": 0.0,
         "ancho": 2.0, "largo": 4.5},
    ]
    alta = [
        {"id": "pasillo_1", "nombre": "pasillo", "x": 0.0, "y": 0.0,
         "ancho": 4.0, "largo": 1.5},
        {"id": "dormitorio_1", "nombre": "dormitorio", "x": 0.0, "y": 1.5,
         "ancho": 4.0, "largo": 3.0},
        {"id": "escalera_1", "nombre": "escalera", "x": 4.0, "y": 0.0,
         "ancho": 2.0, "largo": 4.5},
    ]
    if terraza:
        alta.append({"id": "terraza_1", "nombre": "terraza", "x": 0.0, "y": 4.5,
                     "ancho": 4.0, "largo": 2.0})
    return construir_multipisos([baja, alta], 10, 10, tmp_path / "p.dxf")


def test_la_planta_alta_no_vuelve_a_subir_y_muestra_el_hueco(tmp_path):
    baja, alta = _casa_con_escalera(tmp_path).pisos

    escena = generar_escena_3d(alta, SIN_MUEBLES, piso_inferior=baja)

    assert not _peldanos(escena), "arriba no hay peldaños que suban"
    assert [m for m in escena["prismas"] if m["material"] == "hueco"]
    assert [p for p in _materiales(escena, "metal") if p["h1"] <= 1.0], "baranda"


def test_la_escalera_deja_paso_ante_sus_puertas(tmp_path):
    from src.ui.escalera_3d import puertas_de, zona_libre
    from src.ui.escena_3d import trazado_entre

    baja, alta = _casa_con_escalera(tmp_path).pisos
    escalera = next(a for a in baja.geometrias["ambientes"] if a["id"] == "escalera_1")

    trazado = trazado_entre(baja, alta)

    assert trazado["paso_libre"]
    zonas = [zona_libre(p, escalera["poligono"]) for p in puertas_de(baja, "escalera_1")]
    assert zonas
    for p in trazado["piezas"]:
        if p["material"] == "madera" and p["h0"] < 2.0:
            assert all(_caja_de(p).intersection(z).area < 0.01 for z in zonas)


def test_la_terraza_tiene_parapeto_bajo_macetas_y_pergola(tmp_path):
    distribucion = [
        {"id": "sala_1", "nombre": "sala", "x": 0.0, "y": 0.0, "ancho": 4.0, "largo": 4.0},
        {"id": "terraza_1", "nombre": "terraza", "x": 4.0, "y": 0.0,
         "ancho": 4.0, "largo": 4.0},
    ]
    escena = generar_escena_3d(_plano_con(distribucion, 10, 10, tmp_path))

    parapetos = [m for m in escena["muros"] if m["material"] == "parapeto"]

    assert parapetos, "la terraza baja a la cadera sus muros exteriores"
    assert all(m["h1"] == pytest.approx(ALTURA_PARAPETO_TERRAZA) for m in parapetos)
    assert _materiales(escena, "maceta"), "la terraza lleva macetas"
    assert _materiales(escena, "pergola"), "la terraza lleva pérgola de madera"


TERRAZA_JUNTO_A_SALA = [
    {"id": "sala_1", "nombre": "sala", "x": 0.0, "y": 0.0, "ancho": 4.0, "largo": 4.0},
    {"id": "terraza_1", "nombre": "terraza", "x": 4.0, "y": 0.0,
     "ancho": 4.0, "largo": 4.0},
]


def _en(muro, punto):
    from shapely.geometry import Polygon

    return Polygon(muro["anillos"][0], muro["anillos"][1:]).buffer(1e-3).covers(punto)


def test_entre_la_terraza_y_su_vecino_hay_una_mampara(tmp_path):
    from shapely.geometry import Point

    plano = _plano_con(TERRAZA_JUNTO_A_SALA, 10, 10, tmp_path)
    escena = generar_escena_3d(plano)
    puerta = next(
        p for p in plano.puertas["puertas"]
        if {p["ambiente_a"], p.get("ambiente_b")} == {"sala_1", "terraza_1"}
    )
    # Un punto del muro común lejos de la puerta.
    y = 0.6 if puerta["centro"][1] > 2.0 else 3.4
    compartido = Point(4.0, y)

    vidrios = [m for m in escena["muros"] if m["material"] == "vidrio"]
    assert any(_en(m, compartido) for m in vidrios), "la pared común es mampara"
    assert any(_en(m, compartido) and m["h1"] == ALTURA_MURO
               for m in escena["muros"] if m["material"] == "muro"), "con su dintel"
    # El muro exterior de la sala sigue completo junto a la terraza.
    assert not any(_en(m, Point(3.5, 0.0)) for m in escena["muros"]
                   if m["material"] == "parapeto")


def test_la_terraza_no_tiene_ventanas_flotantes(tmp_path):
    plano = _plano_con(TERRAZA_JUNTO_A_SALA, 10, 10, tmp_path)
    ventanas = [v for v in plano.ventanas["ventanas"] if v["ambiente_a"] == "terraza_1"]
    assert ventanas, "el plano 2D sí propone ventanas en la terraza"

    escena = generar_escena_3d(plano)

    for v in ventanas:
        cx, cy = v["centro"]
        encima = [
            p for p in escena["piezas"]
            if p["h0"] >= ALTURA_PUERTA - 0.01 and p["material"] in ("muro", "vidrio")
            and p["x0"] - 1e-3 <= cx <= p["x1"] + 1e-3
            and p["y0"] - 1e-3 <= cy <= p["y1"] + 1e-3
        ]
        assert not encima, "ningún dintel flota sobre el parapeto"
        assert not [p for p in escena["piezas"] if p["material"] == "vidrio"
                    and p["x0"] - 1e-3 <= cx <= p["x1"] + 1e-3
                    and p["y0"] - 1e-3 <= cy <= p["y1"] + 1e-3]


def test_casa_completa_apila_pisos_con_entrepiso_y_azotea(tmp_path):
    from shapely.geometry import Point, Polygon
    from src.ui.escena_3d import trazado_entre

    resultado = _casa_con_escalera(tmp_path, terraza=True)
    baja, alta = resultado.pisos

    escena = generar_escena_casa(resultado.pisos)

    niveles = sorted({round(p["h0"], 2) for p in escena["pisos"]})
    assert niveles == [0.0, round(ALTURA_ENTREPISO, 2)]
    assert escena["altura_total"] == pytest.approx(
        2 * ALTURA_ENTREPISO + ALTO_PARAPETO_AZOTEA
    )

    losas = [m for m in escena["prismas"] if m["material"] == "losa"]
    parapetos = [m for m in escena["prismas"] if m["material"] == "parapeto"]
    assert losas and parapetos, "hay entrepiso/azotea y parapeto de azotea"

    def cubre(nivel, punto):
        return any(
            Polygon(m["anillos"][0], m["anillos"][1:]).covers(punto)
            for m in losas if round(m["h0"], 2) == round(nivel, 2)
        )

    hueco = trazado_entre(baja, alta)["hueco"].representative_point()
    assert not cubre(ALTURA_MURO, hueco), "el entrepiso deja libre el hueco"
    assert cubre(ALTURA_MURO, Point(2.0, 2.0)), "pero cubre la planta baja"
    azotea = ALTURA_ENTREPISO + ALTURA_MURO
    assert not cubre(azotea, Point(2.0, 5.5)), "la terraza alta queda a cielo abierto"
    assert cubre(azotea, Point(2.0, 3.0))
    # Solo sube la escalera de la planta baja; la alta no sube a la azotea.
    sin_muebles = generar_escena_casa(resultado.pisos, SIN_MUEBLES)
    assert max(p["h1"] for p in _peldanos(sin_muebles)) < ALTURA_ENTREPISO


def test_el_entorno_solo_aparece_con_detalle(plano):
    from shapely.ops import unary_union

    sencilla = generar_escena_3d(plano, entorno=True)
    detallada = generar_escena_3d(plano, detalle=True, entorno=True)

    assert not _materiales(sencilla, "asfalto")
    assert _materiales(detallada, "asfalto"), "hay calle"
    assert _materiales(detallada, "follaje") or _materiales(detallada, "follaje_claro")
    assert _materiales(detallada, "piel"), "hay personas"
    # La calle va por delante del terreno, no lo invade.
    ty0 = detallada["terreno"][1]
    assert all(p["y1"] <= ty0 + 1e-6 for p in _materiales(detallada, "asfalto"))
    # Ningún árbol cae dentro de la casa.
    casa = unary_union([a["poligono"] for a in plano.geometrias["ambientes"]])
    assert all(not casa.intersects(_caja_de(p)) for p in _materiales(detallada, "tronco"))


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


def test_la_casa_completa_no_muestra_rotulos_flotantes(tmp_path):
    resultado = _casa_con_escalera(tmp_path, terraza=True)

    escena = generar_escena_casa(resultado.pisos)

    assert escena["rotulos"] == []


def test_la_planta_alta_sola_queda_sobre_la_baja_con_techo_abierto(tmp_path):
    baja, alta = _casa_con_escalera(tmp_path).pisos

    escena = generar_escena_3d(alta, SIN_MUEBLES, piso_inferior=baja, ver_inferior=True)

    # El piso de la planta alta está elevado sobre el volumen de la baja.
    assert min(p["h0"] for p in escena["pisos"]) == pytest.approx(ALTURA_ENTREPISO)
    fantasmas = [m for m in escena["prismas"] if m["material"] == "fantasma"]
    assert fantasmas and all(m["h0"] == 0.0 for m in fantasmas)
    # El entrepiso va bajo la planta alta, pero no hay losa de techo encima.
    entrepisos = [m for m in escena["prismas"] if m["material"] == "losa"]
    assert entrepisos and all(m["h1"] <= ALTURA_ENTREPISO + 1e-6 for m in entrepisos)
    assert not [m for m in escena["prismas"] if m["material"] == "parapeto"]
    # La escalera sube del suelo hasta la planta alta.
    assert max(p["h1"] for p in _peldanos(escena)) == pytest.approx(
        ALTURA_ENTREPISO, abs=0.2
    )
    assert escena["altura_total"] == pytest.approx(ALTURA_ENTREPISO + ALTURA_MURO)
