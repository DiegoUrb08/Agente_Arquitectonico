"""
Escena 3D del plano (función pura: no depende de Streamlit).

Todo se calcula aquí en coordenadas del plano (x, y en metros, más una
altura); el visor (`visor_3d.html`) solo dibuja prismas, cajas y cilindros.
"""

import json
from pathlib import Path

from shapely.geometry import Point

from src.geometry.opening_generator import construir_abertura
from src.ui import detalle_3d
from src.ui.pantalla_completa import BOTON as BOTON_PANTALLA_COMPLETA
from src.planning.reglas_acceso import CIRCULACION, EXTERIOR, tipo_base
from src.ui.plano_svg import (
    CAPAS_POR_DEFECTO,
    color_de_ambiente,
    etiquetas_ambientes,
)

ALTURA_MURO = 2.60
ALTURA_PUERTA = 2.10
ANTEPECHO = 0.90
ANTEPECHO_ALTO = 1.50  # baños: ventana alta
ALTURA_VENTANA = 2.10
GROSOR_PISO = 0.04
GROSOR_HOJA = 0.04
GROSOR_VIDRIO = 0.02
TINTE_PISO = 0.55  # cuánto se aclara el color del ambiente para el piso

PLANTILLA = Path(__file__).with_name("visor_3d.html")


# ------------------------------------------------------------
# Utilidades
# ------------------------------------------------------------

def _r(valor: float) -> float:
    return round(float(valor), 3)


def aclarar(color: str, fraccion: float) -> str:
    """Mezcla un color #RRGGBB con blanco."""
    canales = [int(color[i:i + 2], 16) for i in (1, 3, 5)]
    mezcla = [round(c + (255 - c) * fraccion) for c in canales]
    return "#" + "".join(f"{c:02X}" for c in mezcla)


def _caja(x0, y0, x1, y1, h0, h1, material, forma="caja"):
    return {
        "forma": forma,
        "x0": _r(min(x0, x1)), "y0": _r(min(y0, y1)),
        "x1": _r(max(x0, x1)), "y1": _r(max(y0, y1)),
        "h0": _r(h0), "h1": _r(h1),
        "material": material,
    }


def _anillos(poligono) -> list:
    return [
        [[_r(x), _r(y)] for x, y in list(anillo.coords)[:-1]]
        for anillo in (poligono.exterior, *poligono.interiors)
    ]


def _poligonos(geometria) -> list:
    if geometria is None or geometria.is_empty:
        return []
    return [
        p for p in getattr(geometria, "geoms", [geometria])
        if p.geom_type == "Polygon" and not p.is_empty
    ]


def _ambiente_en(ambientes, punto):
    return next(
        (a for a in ambientes if a["poligono"].buffer(1e-6).covers(punto)),
        None,
    )


# ------------------------------------------------------------
# Puertas y ventanas
# ------------------------------------------------------------

def _destino_de(puerta) -> str:
    """Ambiente hacia el que abre la hoja (el que no es de paso)."""
    a, b = puerta["ambiente_a"], puerta.get("ambiente_b")
    if b in (None, EXTERIOR):
        return a
    if tipo_base(b) in CIRCULACION and tipo_base(a) not in CIRCULACION:
        return a
    return b


def _puerta(puerta, ambientes, detalle=False) -> tuple[list, list]:
    """(dintel, hoja) de una puerta. La hoja queda abierta a 90°.

    Con `detalle`, la hoja lleva manija a ambos lados, junto al canto libre.
    """
    cx, cy = puerta["centro"]
    ancho = puerta["ancho"]
    hueco = construir_abertura(
        (cx, cy), ancho, puerta["espesor_muro"], puerta["orientacion"]
    )
    dintel = _caja(*hueco.bounds[:2], *hueco.bounds[2:], ALTURA_PUERTA,
                   ALTURA_MURO, "muro")

    destino = next(
        (a for a in ambientes if a["id"] == _destino_de(puerta)), None
    )
    horizontal = puerta["orientacion"] == "horizontal"
    normal = (0.0, 1.0) if horizontal else (1.0, 0.0)
    prueba = Point(cx + normal[0] * 0.3, cy + normal[1] * 0.3)
    signo = 1 if destino is None or destino["poligono"].covers(prueba) else -1

    medio = puerta["espesor_muro"] / 2
    if horizontal:
        bisagra_x = cx - ancho / 2
        y_inicio = cy + signo * medio
        hoja = _caja(bisagra_x, y_inicio, bisagra_x + GROSOR_HOJA,
                     y_inicio + signo * ancho, 0.01, ALTURA_PUERTA - 0.02,
                     "puerta")
        libre = y_inicio + signo * (ancho - 0.1)
        manija = _caja(bisagra_x - 0.03, libre - 0.06, bisagra_x + GROSOR_HOJA + 0.03,
                       libre + 0.06, 0.95, 1.0, "metal")
    else:
        bisagra_y = cy - ancho / 2
        x_inicio = cx + signo * medio
        hoja = _caja(x_inicio, bisagra_y, x_inicio + signo * ancho,
                     bisagra_y + GROSOR_HOJA, 0.01, ALTURA_PUERTA - 0.02,
                     "puerta")
        libre = x_inicio + signo * (ancho - 0.1)
        manija = _caja(libre - 0.06, bisagra_y - 0.03, libre + 0.06,
                       bisagra_y + GROSOR_HOJA + 0.03, 0.95, 1.0, "metal")
    return [dintel], [hoja, manija] if detalle else [hoja]


def _antepecho(ventana) -> float:
    alto = tipo_base(ventana.get("ambiente_a") or "") == "bano"
    return ANTEPECHO_ALTO if alto else ANTEPECHO


def _ventana(ventana) -> tuple[list, list]:
    """(antepecho y dintel, vidrio) de una ventana."""
    x0, y0, x1, y1 = construir_abertura(
        tuple(ventana["centro"]), ventana["ancho"],
        ventana["espesor_muro"], ventana["orientacion"],
    ).bounds
    antepecho = _antepecho(ventana)

    muro = [
        _caja(x0, y0, x1, y1, 0, antepecho, "muro"),
        _caja(x0, y0, x1, y1, ALTURA_VENTANA, ALTURA_MURO, "muro"),
    ]
    if ventana["orientacion"] == "horizontal":
        medio = (y0 + y1) / 2
        vidrio = _caja(x0, medio - GROSOR_VIDRIO / 2, x1,
                       medio + GROSOR_VIDRIO / 2, antepecho, ALTURA_VENTANA,
                       "vidrio")
    else:
        medio = (x0 + x1) / 2
        vidrio = _caja(medio - GROSOR_VIDRIO / 2, y0,
                       medio + GROSOR_VIDRIO / 2, y1, antepecho,
                       ALTURA_VENTANA, "vidrio")
    return muro, [vidrio]


# ------------------------------------------------------------
# Mobiliario
# ------------------------------------------------------------

# Muebles que se apoyan en la pared por su lado corto (cabecero, cisterna).
APOYO_CORTO = {"cama_individual", "cama_matrimonial", "cama_queen", "inodoro", "tina"}


def lado_de_pared(caja, poligono, tipo=None) -> str:
    """
    Lado del ambiente ('s', 'n', 'o', 'e') al que el mueble da la espalda.

    Con `tipo`, la espalda es el lado largo del mueble (sofá, armario,
    cocina…) o el corto (camas, inodoro) más cercano a una pared, aunque el
    mueble no llegue a tocarla.
    """
    x0, y0, x1, y1 = caja
    ax0, ay0, ax1, ay1 = poligono.bounds
    distancias = {"s": y0 - ay0, "n": ay1 - y1, "o": x0 - ax0, "e": ax1 - x1}
    mas_cercano = min(distancias, key=distancias.get)

    if tipo is None or abs((x1 - x0) - (y1 - y0)) < 0.05:
        return mas_cercano

    largo_en_x = (x1 - x0) > (y1 - y0)
    paralelos_a_x = ("s", "n")
    apoyo_largo = paralelos_a_x if largo_en_x else ("o", "e")
    apoyo_corto = ("o", "e") if largo_en_x else paralelos_a_x
    candidatos = apoyo_corto if tipo in APOYO_CORTO else apoyo_largo
    return min(candidatos, key=distancias.get)


def _mapear(caja, lado):
    """
    Convierte coordenadas locales del mueble (u a lo largo de la pared,
    v alejándose de ella) a coordenadas del plano. Devuelve (W, D, f).
    """
    x0, y0, x1, y1 = caja
    if lado in ("s", "n"):
        ancho, fondo = x1 - x0, y1 - y0
        if lado == "s":
            return ancho, fondo, lambda u, v: (x0 + u, y0 + v)
        return ancho, fondo, lambda u, v: (x0 + u, y1 - v)
    ancho, fondo = y1 - y0, x1 - x0
    if lado == "o":
        return ancho, fondo, lambda u, v: (x0 + v, y0 + u)
    return ancho, fondo, lambda u, v: (x1 - v, y0 + u)


def _cama(W, D):
    piezas = [
        (0, W, 0, D, 0.0, 0.38, "madera"),
        (0.03, W - 0.03, 0.06, D - 0.03, 0.38, 0.58, "colchon"),
        (0, W, 0, 0.07, 0.0, 1.0, "madera"),
        (0.03, W - 0.03, 0.75, D - 0.03, 0.58, 0.63, "tela"),
    ]
    n = 2 if W >= 1.2 else 1
    paso = (W - 0.1) / n
    for i in range(n):
        u0 = 0.05 + i * paso + 0.04
        piezas.append((u0, u0 + paso - 0.08, 0.12, 0.45, 0.58, 0.7, "blanco"))
    return piezas


def _sofa(W, D):
    return [
        (0, W, 0, D, 0.0, 0.42, "tela"),
        (0, W, 0, 0.22, 0.42, 0.85, "tela"),
        (0, 0.18, 0, D, 0.42, 0.62, "tela"),
        (W - 0.18, W, 0, D, 0.42, 0.62, "tela"),
        (0.2, W - 0.2, 0.24, D - 0.05, 0.42, 0.5, "tela_clara"),
    ]


def _mesa(W, D, alto=0.75):
    pata = 0.06
    piezas = [(0, W, 0, D, alto - 0.04, alto, "madera")]
    for u0 in (0.04, W - 0.04 - pata):
        for v0 in (0.04, D - 0.04 - pata):
            piezas.append((u0, u0 + pata, v0, v0 + pata, 0, alto - 0.04, "madera"))
    return piezas


def _armario(W, D):
    return [
        (0, W, 0, D, 0.0, 2.0, "madera"),
        (W / 2 - 0.01, W / 2 + 0.01, D - 0.005, D, 0.05, 1.95, "oscuro"),
    ]


def _refrigeradora(W, D):
    return [
        (0, W, 0, D, 0.0, 1.8, "metal"),
        (0.05, W - 0.05, D - 0.005, D, 1.15, 1.17, "oscuro"),
        (W - 0.12, W - 0.09, D, D + 0.03, 1.25, 1.6, "oscuro"),
    ]


def _cocina(W, D):
    piezas = [
        (0, W, 0, D, 0.0, 0.88, "blanco"),
        (0, W, 0, D, 0.88, 0.92, "oscuro"),
    ]
    for u in (W * 0.3, W * 0.7):
        for v in (D * 0.32, D * 0.68):
            piezas.append((u - 0.08, u + 0.08, v - 0.08, v + 0.08, 0.92,
                           0.94, "metal", "cilindro"))
    return piezas


def _inodoro(W, D):
    return [
        (0.04, W - 0.04, 0, 0.18, 0.0, 0.8, "blanco"),
        (0.03, W - 0.03, 0.2, D, 0.0, 0.42, "blanco", "cilindro"),
    ]


def _lavatorio(W, D):
    return [
        (0, W, 0, D, 0.0, 0.8, "madera"),
        (0.08, W - 0.08, 0.08, D - 0.06, 0.8, 0.86, "blanco"),
    ]


def _ducha(W, D):
    return [
        (0, W, 0, D, 0.0, 0.05, "blanco"),
        (0, W, D - 0.02, D, 0.05, 1.95, "vidrio"),
    ]


def _lavadora(W, D):
    return [
        (0, W, 0, D, 0.0, 0.85, "blanco"),
        (0.15, W - 0.15, D, D + 0.01, 0.25, 0.6, "oscuro"),
    ]


def _tina(W, D):
    return [
        (0, W, 0, D, 0.0, 0.55, "blanco"),
        (0.08, W - 0.08, 0.08, D - 0.08, 0.5, 0.56, "agua"),
    ]


MUEBLES = {
    "cama_individual": _cama,
    "cama_matrimonial": _cama,
    "cama_queen": _cama,
    "sofa": _sofa,
    "mesa_comedor": _mesa,
    "escritorio": lambda W, D: _mesa(W, D, 0.74),
    "silla": lambda W, D: _mesa(W, D, 0.45),
    "armario": _armario,
    "refrigeradora": _refrigeradora,
    "cocina": _cocina,
    "inodoro": _inodoro,
    "lavatorio": _lavatorio,
    "ducha": _ducha,
    "lavadora": _lavadora,
    "secadora": _lavadora,
    "tina": _tina,
}


def ubicar_mueble(mueble, ambientes) -> dict:
    """Caja, ambiente y lado de la pared que el mueble tiene detrás."""
    x0, y0 = mueble["x"], mueble["y"]
    caja = (x0, y0, x0 + mueble["ancho"], y0 + mueble["largo"])
    centro = Point((caja[0] + caja[2]) / 2, (caja[1] + caja[3]) / 2)
    ambiente = _ambiente_en(ambientes, centro)
    lado = (
        lado_de_pared(caja, ambiente["poligono"], mueble["tipo"])
        if ambiente else "s"
    )
    return {"tipo": mueble["tipo"], "caja": caja, "lado": lado, "ambiente": ambiente}


def piezas_de_mueble(mueble, ambientes) -> list:
    """Piezas 3D de un mueble, orientadas según la pared que tiene detrás."""
    ubicado = ubicar_mueble(mueble, ambientes)
    caja, lado = ubicado["caja"], ubicado["lado"]

    W, D, mapear = _mapear(caja, lado)
    plantilla = MUEBLES.get(mueble["tipo"], lambda W, D: [
        (0, W, 0, D, 0.0, 0.75, "madera")
    ])

    piezas = []
    for u0, u1, v0, v1, h0, h1, material, *forma in plantilla(W, D):
        (ax, ay), (bx, by) = mapear(u0, v0), mapear(u1, v1)
        piezas.append(_caja(ax, ay, bx, by, h0, h1, material,
                            forma[0] if forma else "caja"))
    return piezas


# ------------------------------------------------------------
# Escena completa
# ------------------------------------------------------------

def generar_escena_3d(
    piso, capas=CAPAS_POR_DEFECTO, resaltar=frozenset(), detalle=False
) -> dict:
    """Escena serializable a JSON de un `ResultadoPlano`.

    Con `detalle` añade decoración, marcos, zócalos, la vereda de entrada y
    acabados de piso (ver `detalle_3d`); sin él la escena es la sencilla.
    """
    ambientes = piso.geometrias["ambientes"]
    etiquetas = etiquetas_ambientes(piso.distribucion)

    muros = [
        {"anillos": _anillos(p), "h0": 0.0, "h1": ALTURA_MURO, "material": "muro"}
        for p in _poligonos((piso.aberturas or {}).get("muros_con_aberturas"))
    ]

    pisos = []
    rotulos = []
    for ambiente in ambientes:
        cambiado = "cambios" in capas and ambiente["id"] in resaltar
        color = color_de_ambiente(ambiente["nombre"])
        pisos.append({
            "anillos": _anillos(ambiente["poligono"]),
            "h0": 0.0, "h1": GROSOR_PISO,
            "color": "#FBBF24" if cambiado else aclarar(color, TINTE_PISO),
            "id": ambiente["id"],
        })
        if "etiquetas" in capas:
            c = ambiente["poligono"].centroid
            rotulos.append({
                "x": _r(c.x), "y": _r(c.y),
                "texto": etiquetas.get(ambiente["id"], ambiente["nombre"]),
                "detalle": f"{ambiente['poligono'].area:.1f} m²",
                "color": color,
            })

    piezas = []
    for puerta in (piso.puertas or {}).get("puertas", []):
        dintel, hoja = _puerta(puerta, ambientes, detalle)
        piezas += dintel
        if "puertas" in capas:
            piezas += hoja
            if detalle:
                piezas += detalle_3d.marco_de_puerta(puerta)

    for ventana in (piso.ventanas or {}).get("ventanas", []):
        muro, vidrio = _ventana(ventana)
        piezas += muro
        if "ventanas" in capas:
            piezas += vidrio
            if detalle:
                piezas += detalle_3d.marco_de_ventana(ventana, _antepecho(ventana))

    muebles = (piso.mobiliario or {}).get("mobiliario", [])
    if "muebles" in capas:
        for mueble in muebles:
            piezas += piezas_de_mueble(mueble, ambientes)
        if detalle:
            piezas += detalle_3d.decoracion(
                piso, [ubicar_mueble(m, ambientes) for m in muebles]
            )

    tx0, ty0, tx1, ty1 = piso.geometrias["terreno"].bounds
    vx0 = min(a["poligono"].bounds[0] for a in ambientes)
    vy0 = min(a["poligono"].bounds[1] for a in ambientes)
    vx1 = max(a["poligono"].bounds[2] for a in ambientes)
    vy1 = max(a["poligono"].bounds[3] for a in ambientes)

    escena = {
        "terreno": [_r(tx0), _r(ty0), _r(tx1), _r(ty1)],
        "vivienda": [_r(vx0), _r(vy0), _r(vx1), _r(vy1)],
        "altura_muro": ALTURA_MURO,
        "muros": muros,
        "pisos": pisos,
        "piezas": piezas,
        "rotulos": rotulos,
    }

    if detalle:
        for p in pisos:
            p["acabado"] = detalle_3d.acabado_de(p["id"])
        escena["detalle"] = True
        escena["terreno_acabado"] = "cesped"
        escena["prismas"] = detalle_3d.zocalos(piso)
        escena["piezas"] += detalle_3d.entrada(piso)

    return escena


def json_seguro(datos) -> str:
    """JSON que se puede incrustar en un <script> sin cerrarlo."""
    return (
        json.dumps(datos, ensure_ascii=False)
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )


def documento_3d(escena: dict, uid: str = "plano") -> str:
    """Página HTML completa del visor 3D con la escena incrustada."""
    plantilla = PLANTILLA.read_text(encoding="utf-8")
    return (
        plantilla
        .replace("__PANTALLA_COMPLETA__", BOTON_PANTALLA_COMPLETA)
        .replace("__UID__", json_seguro(uid))
        # La escena (con textos del usuario) va al final: así ningún nombre
        # puede contener un marcador que se reemplace después.
        .replace("__ESCENA__", json_seguro(escena))
    )
