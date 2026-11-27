"""
Entorno de la vivienda en la vista 3D (solo con «Detalle alto»): la calle al
frente con su vereda y alumbrado, árboles en el terreno libre y algunas
personas para dar escala. Función pura: devuelve piezas como `escena_3d`.

La calle va por el frente del terreno (y = mínimo), donde están la entrada y
el garaje.
"""

from shapely.geometry import Point, box
from shapely.ops import unary_union

from src.planning.reglas_acceso import EXTERIOR

ANCHO_VEREDA = 1.5
ANCHO_SARDINEL = 0.15
ANCHO_PISTA = 7.0
SOBRESALE_CALLE = 6.0      # la calle sigue a los lados del terreno
SEPARACION_ARBOLES = 2.6
DISTANCIA_A_LA_CASA = 1.2
MAX_ARBOLES = 8
PASO_ALUMBRADO = 10.0


def _r(valor: float) -> float:
    return round(float(valor), 3)


def _caja(x0, y0, x1, y1, h0, h1, material, forma="caja"):
    return {
        "forma": forma,
        "x0": _r(min(x0, x1)), "y0": _r(min(y0, y1)),
        "x1": _r(max(x0, x1)), "y1": _r(max(y0, y1)),
        "h0": _r(h0), "h1": _r(h1),
        "material": material,
    }


# ------------------------------------------------------------
# Elementos
# ------------------------------------------------------------

def arbol(x, y, variante=0) -> list:
    """Tronco y copa; `variante` cambia el tamaño y el tono."""
    alto, radio = ((1.6, 1.0), (2.0, 1.25), (1.3, 0.8))[variante % 3]
    copa = "follaje" if variante % 2 == 0 else "follaje_claro"
    return [
        _caja(x - 0.11, y - 0.11, x + 0.11, y + 0.11, 0.0, alto + 0.3,
              "tronco", "cilindro"),
        _caja(x - radio, y - radio, x + radio, y + radio, alto - 0.2,
              alto - 0.2 + 1.8 * radio, copa, "esfera"),
    ]


def persona(x, y, variante=0) -> list:
    """Figura sencilla de 1.7 m (piernas, torso, brazos y cabeza)."""
    ropa = ("ropa", "ropa_2", "ropa_3")[variante % 3]
    return [
        _caja(x - 0.15, y - 0.07, x - 0.03, y + 0.07, 0.0, 0.85, "oscuro"),
        _caja(x + 0.03, y - 0.07, x + 0.15, y + 0.07, 0.0, 0.85, "oscuro"),
        _caja(x - 0.19, y - 0.12, x + 0.19, y + 0.12, 0.85, 1.45, ropa, "cilindro"),
        _caja(x - 0.27, y - 0.05, x - 0.19, y + 0.05, 0.9, 1.42, ropa),
        _caja(x + 0.19, y - 0.05, x + 0.27, y + 0.05, 0.9, 1.42, ropa),
        _caja(x - 0.11, y - 0.11, x + 0.11, y + 0.11, 1.47, 1.72, "piel", "esfera"),
    ]


def _farol(x, y) -> list:
    """Poste junto al sardinel con el brazo y la luminaria sobre la pista."""
    return [
        _caja(x - 0.06, y - 0.06, x + 0.06, y + 0.06, 0.0, 4.5, "metal", "cilindro"),
        _caja(x - 0.04, y - 1.0, x + 0.04, y + 0.04, 4.4, 4.5, "metal"),
        _caja(x - 0.14, y - 1.05, x + 0.14, y - 0.75, 4.3, 4.4, "luz"),
    ]


# ------------------------------------------------------------
# Composición
# ------------------------------------------------------------

def _accesos(piso, ty0) -> list:
    """Franjas del terreno que van de cada puerta exterior a la calle."""
    franjas = []
    for puerta in (piso.puertas or {}).get("puertas", []):
        if puerta.get("ambiente_b") != EXTERIOR:
            continue
        cx, cy = puerta["centro"]
        medio = puerta["ancho"] / 2 + (0.5 if puerta.get("vehicular") else 0.4)
        if puerta["orientacion"] == "horizontal":
            franjas.append((box(cx - medio, ty0, cx + medio, cy), puerta))
        else:
            franjas.append((box(cx - 0.8, ty0, cx + 0.8, cy), puerta))
    return franjas


def _calle(tx0, tx1, ty0) -> list:
    x0, x1 = tx0 - SOBRESALE_CALLE, tx1 + SOBRESALE_CALLE
    vereda = ty0 - ANCHO_VEREDA
    sardinel = vereda - ANCHO_SARDINEL
    pista = sardinel - ANCHO_PISTA
    piezas = [
        _caja(x0, vereda, x1, ty0, 0.0, 0.15, "cemento"),
        _caja(x0, sardinel, x1, vereda, 0.0, 0.18, "cemento"),
        _caja(x0, pista, x1, sardinel, 0.0, 0.02, "asfalto"),
        # Vereda de enfrente.
        _caja(x0, pista - ANCHO_VEREDA, x1, pista, 0.0, 0.15, "cemento"),
    ]
    medio = (pista + sardinel) / 2
    x = x0 + 0.5
    while x + 2.0 <= x1:
        piezas.append(_caja(x, medio - 0.06, x + 2.0, medio + 0.06, 0.02, 0.025,
                            "linea_via"))
        x += 3.0
    return piezas


def _puntos_libres(libre, separacion, limite):
    """Puntos de una rejilla dentro de `libre`, separados entre sí."""
    x0, y0, x1, y1 = libre.bounds
    elegidos = []
    y = y0 + separacion / 2
    while y <= y1:
        x = x0 + separacion / 2
        while x <= x1:
            p = Point(x, y)
            if libre.covers(p.buffer(0.6)) and all(
                p.distance(q) >= separacion for q in elegidos
            ):
                elegidos.append(p)
                if len(elegidos) >= limite:
                    return elegidos
            x += separacion / 2
        y += separacion / 2
    return elegidos


def entorno(piso) -> list:
    """Piezas del entorno de una planta baja."""
    tx0, ty0, tx1, ty1 = piso.geometrias["terreno"].bounds
    vivienda = unary_union([a["poligono"] for a in piso.geometrias["ambientes"]])
    accesos = _accesos(piso, ty0)

    piezas = _calle(tx0, tx1, ty0)

    # Rampa de cemento hasta el portón del garaje.
    for franja, puerta in accesos:
        if puerta.get("vehicular"):
            fx0, fy0, fx1, fy1 = franja.bounds
            piezas.append(_caja(fx0, fy0, fx1, fy1 - puerta["espesor_muro"] / 2,
                                0.0, 0.03, "cemento"))

    # Árboles en el terreno libre (lejos de la casa y de los accesos).
    libre = box(tx0, ty0, tx1, ty1).difference(
        unary_union([vivienda.buffer(DISTANCIA_A_LA_CASA)]
                    + [f.buffer(0.3) for f, _ in accesos])
    )
    arboles = _puntos_libres(libre, SEPARACION_ARBOLES, MAX_ARBOLES)
    for i, p in enumerate(arboles):
        piezas += arbol(p.x, p.y, i)

    # Árboles de alineación y alumbrado en la vereda, sin tapar los accesos.
    cruces = unary_union([f for f, _ in accesos]).buffer(0.8) if accesos else None
    y_arbol = ty0 - ANCHO_VEREDA / 2
    alineacion = []
    x = tx0 + 1.5
    for i in range(int((tx1 - tx0) / 5) + 1):
        if x > tx1 - 0.5:
            break
        if cruces is None or not cruces.covers(Point(x, ty0 - 0.01)):
            piezas.append(_caja(x - 0.45, y_arbol - 0.45, x + 0.45, y_arbol + 0.45,
                                0.15, 0.17, "tierra"))
            piezas += arbol(x, y_arbol, i + 1)
            alineacion.append(x)
        x += 5.0
    # Faroles en el borde de la vereda, lejos de las copas de los árboles.
    y_farol = ty0 - ANCHO_VEREDA + 0.2
    x = tx0 - SOBRESALE_CALLE + 2.0
    while x < tx1 + SOBRESALE_CALLE:
        if all(abs(x - xa) >= 1.6 for xa in alineacion):
            piezas += _farol(x, y_farol)
        x += PASO_ALUMBRADO

    # Personas: en la vereda, junto a la entrada y en el jardín.
    lugares = [((tx0 + tx1) / 2 + 2.3, ty0 - 0.45)]
    for franja, puerta in accesos:
        if not puerta.get("vehicular"):
            fx0, fy0, fx1, fy1 = franja.bounds
            lugares.append((fx1 + 0.35, fy0 + min(1.5, (fy1 - fy0) / 2)))
            break
    sin_arboles = (
        libre.difference(unary_union([p.buffer(1.0) for p in arboles]))
        if arboles else libre
    )
    jardin = _puntos_libres(sin_arboles, 2.0, 1)
    lugares += [(p.x, p.y) for p in jardin]
    for i, (x, y) in enumerate(lugares):
        piezas += persona(x, y, i)

    return piezas
