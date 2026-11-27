"""
Escalera 3D: un trazado que sube de una planta a la siguiente sin salirse de
su ambiente y dejando libre el paso ante sus puertas.

Se prueban varios trazados (recta, en U, en L y caracol, en todas sus
orientaciones) y se elige el que cabe en el ambiente, no pisa la zona de paso
ante las puertas, arranca junto a la puerta de abajo y llega junto a la de
arriba. Funciones puras: devuelven piezas como las de `escena_3d`.
"""

import math
from functools import lru_cache

from shapely import affinity, wkt
from shapely.geometry import Point, box
from shapely.ops import linemerge, unary_union

CONTRAHUELLA_OBJETIVO = 0.175
HUELLAS = (0.28, 0.25, 0.22)   # de la más cómoda a la más apretada
ANCHO_TRAMO = 0.90
ANCHO_MINIMO_TRAMO = 0.60
FONDO_ZONA_LIBRE = 0.80        # paso libre ante cada puerta
MARGEN = 0.03                  # holgura con los muros
GROSOR_DESCANSO = 0.12
ALTO_BARANDA = 0.90
CONTACTO = 0.35                # el primer/último peldaño, a esta distancia de su puerta
ALTURA_LIBRE = 2.0             # se puede pasar bajo un peldaño a esta altura
BARRIDOS_CARACOL = (300, 330, 270)


# ------------------------------------------------------------
# Utilidades
# ------------------------------------------------------------

def _r(valor: float) -> float:
    return round(float(valor), 3)


def _caja(x0, y0, x1, y1, h0, h1, material, forma="caja", giro=0.0):
    pieza = {
        "forma": forma,
        "x0": _r(min(x0, x1)), "y0": _r(min(y0, y1)),
        "x1": _r(max(x0, x1)), "y1": _r(max(y0, y1)),
        "h0": _r(h0), "h1": _r(h1),
        "material": material,
    }
    if giro:
        pieza["giro"] = round(giro, 4)
    return pieza


def _segmento(a, b, h0, h1, grosor, material):
    """Caja fina de `a` a `b` (girada si el tramo no sigue un eje)."""
    (ax, ay), (bx, by) = a, b
    largo = math.hypot(bx - ax, by - ay)
    if largo < 1e-6:
        return None
    mx, my = (ax + bx) / 2, (ay + by) / 2
    giro = math.atan2(by - ay, bx - ax)
    if abs(math.sin(giro)) < 1e-6:
        return _caja(mx - largo / 2, my - grosor / 2, mx + largo / 2,
                     my + grosor / 2, h0, h1, material)
    if abs(math.cos(giro)) < 1e-6:
        return _caja(mx - grosor / 2, my - largo / 2, mx + grosor / 2,
                     my + largo / 2, h0, h1, material)
    return _caja(mx - largo / 2, my - grosor / 2, mx + largo / 2,
                 my + grosor / 2, h0, h1, material, giro=giro)


def _poste(x, y, h0, h1):
    return _caja(x - 0.02, y - 0.02, x + 0.02, y + 0.02, h0, h1, "metal")


def puertas_de(piso, identificador) -> list:
    """Puertas del ambiente `identificador` en una planta."""
    return [
        p for p in (getattr(piso, "puertas", None) or {}).get("puertas", [])
        if identificador in (p.get("ambiente_a"), p.get("ambiente_b"))
    ]


def zona_libre(puerta, poligono):
    """Rectángulo de paso ante la puerta, hacia dentro del ambiente."""
    cx, cy = puerta["centro"]
    medio = puerta["ancho"] / 2 + 0.05
    holgado = poligono.buffer(1e-6)
    if puerta["orientacion"] == "horizontal":
        signo = 1 if holgado.covers(Point(cx, cy + 0.3)) else -1
        y1 = cy + signo * FONDO_ZONA_LIBRE
        zona = box(cx - medio, min(cy, y1), cx + medio, max(cy, y1))
    else:
        signo = 1 if holgado.covers(Point(cx + 0.3, cy)) else -1
        x1 = cx + signo * FONDO_ZONA_LIBRE
        zona = box(min(cx, x1), cy - medio, max(cx, x1), cy + medio)
    return zona.intersection(poligono)


# ------------------------------------------------------------
# Trazados en coordenadas locales (u a lo largo, v a lo ancho)
# ------------------------------------------------------------
# Cada paso: {"r": (u0, u1, v0, v1), "tipo": "peldano"|"descanso",
#             "borde": (ua, va, ub, vb) lado libre (baranda) o None}

def _recta(Lu, Lv, T, h, inicio=0.0):
    w = min(ANCHO_TRAMO, Lv)
    if w < ANCHO_MINIMO_TRAMO or inicio + T * h > Lu + 1e-9:
        return None
    libre = w < Lv - 0.05
    return [
        {"r": (inicio + i * h, inicio + (i + 1) * h, 0, w), "tipo": "peldano",
         "borde": (inicio + i * h, w, inicio + (i + 1) * h, w) if libre else None}
        for i in range(T)
    ]


def _rectas(Lu, Lv, T, h):
    """Tramo recto pegado a un extremo, centrado o tras la zona de una puerta."""
    sobra = Lu - T * h
    if sobra < -1e-9:
        return []
    pasos = max(1, int(sobra / 0.15))
    inicios = {round(k * sobra / pasos, 3) for k in range(pasos + 1)}
    return [p for p in (_recta(Lu, Lv, T, h, s) for s in sorted(inicios)) if p]


def _en_u(Lu, Lv, T, h, descanso=None, t1=None):
    """
    Ida y vuelta: dos tramos paralelos (`t1` peldaños de ida) y un descanso
    que empieza en `descanso` (por defecto, al fondo del ambiente).
    """
    w = min(ANCHO_TRAMO, (Lv - 0.04) / 2)
    if w < ANCHO_MINIMO_TRAMO:
        return None
    t1 = T // 2 if t1 is None else t1
    t2 = T - 1 - t1
    fondo = w
    descanso = Lu - fondo if descanso is None else descanso
    if (
        min(t1, t2) < 2 or descanso + fondo > Lu + 1e-9
        or descanso - max(t1, t2) * h < -1e-9
    ):
        return None
    inicio = descanso - t1 * h
    pasos = [
        {"r": (inicio + i * h, inicio + (i + 1) * h, 0, w), "tipo": "peldano",
         "borde": (inicio + i * h, w, inicio + (i + 1) * h, w)}
        for i in range(t1)
    ]
    pasos.append({"r": (descanso, descanso + fondo, 0, Lv), "tipo": "descanso",
                  "borde": None})
    for j in range(t2):
        u1 = descanso - j * h
        pasos.append({"r": (u1 - h, u1, Lv - w, Lv), "tipo": "peldano",
                      "borde": (u1, Lv - w, u1 - h, Lv - w)})
    return pasos


PASO_POSICIONES = 0.15


def _variantes_u(Lu, Lv, T, h):
    """La U corrida a lo largo del ambiente y con la ida algo más larga o corta."""
    w = min(ANCHO_TRAMO, (Lv - 0.04) / 2)
    variantes = []
    for t1 in {T // 2 - 1, T // 2, T // 2 + 1}:
        desde = max(t1, T - 1 - t1) * h
        descanso = desde
        while descanso + w <= Lu + 1e-9:
            pasos = _en_u(Lu, Lv, T, h, descanso, t1)
            if pasos:
                variantes.append(pasos)
            descanso += PASO_POSICIONES
    return variantes


def _en_l(Lu, Lv, T, h):
    """Un tramo a lo largo, descanso en la esquina y otro a lo ancho."""
    w = min(ANCHO_TRAMO, Lv, Lu)
    if w < ANCHO_MINIMO_TRAMO:
        return None
    t2 = min(int((Lv - w) / h + 1e-9), T - 3)
    t1 = T - 1 - t2
    if t2 < 2 or t1 < 2 or t1 * h + w > Lu + 1e-9:
        return None
    a = t1 * h
    pasos = [
        {"r": (i * h, (i + 1) * h, 0, w), "tipo": "peldano",
         "borde": (i * h, w, (i + 1) * h, w)}
        for i in range(t1)
    ]
    pasos.append({"r": (a, a + w, 0, w), "tipo": "descanso", "borde": None})
    pasos += [
        {"r": (a, a + w, w + j * h, w + (j + 1) * h), "tipo": "peldano",
         "borde": (a, w + j * h, a, w + (j + 1) * h)}
        for j in range(t2)
    ]
    return pasos


def _comprimida(Lu, Lv, T):
    """Último recurso: la que mejor quepa, con la huella que haga falta."""
    w = min(ANCHO_TRAMO, (Lv - 0.04) / 2)
    if w >= ANCHO_MINIMO_TRAMO and Lu > w + 0.5:
        h = (Lu - w) / ((T + 1) // 2)
        return _en_u(Lu, Lv, T, h)
    return _recta(Lu, max(Lv, ANCHO_MINIMO_TRAMO), T, Lu / T)


def _una(trazar):
    def variantes(Lu, Lv, T, h):
        pasos = trazar(Lu, Lv, T, h)
        return [pasos] if pasos else []
    return variantes


TRAZADOS = (("recta", _rectas), ("u", _variantes_u), ("l", _una(_en_l)))


def _a_plano(pasos, bounds, eje, fu, fv):
    """Lleva un trazado local a coordenadas del plano."""
    X0, Y0, X1, Y1 = bounds

    def punto(u, v):
        if eje == "x":
            return (X1 - u if fu else X0 + u), (Y1 - v if fv else Y0 + v)
        return (X1 - v if fv else X0 + v), (Y1 - u if fu else Y0 + u)

    resultado = []
    for paso in pasos:
        u0, u1, v0, v1 = paso["r"]
        (ax, ay), (bx, by) = punto(u0, v0), punto(u1, v1)
        borde = None
        if paso["borde"]:
            ua, va, ub, vb = paso["borde"]
            borde = (punto(ua, va), punto(ub, vb))
        resultado.append({
            "poly": box(min(ax, bx), min(ay, by), max(ax, bx), max(ay, by)),
            "tipo": paso["tipo"], "borde": borde, "giro": 0.0,
        })
    return resultado


def _caracol(cx, cy, radio, T, angulo0, sentido, barrido):
    paso_ang = math.radians(barrido) / T
    largo = radio - 0.06
    medio = 0.06 + largo / 2
    ancho = 2 * radio * math.sin(paso_ang / 2) + 0.02
    pasos = []
    for i in range(T):
        ang = angulo0 + sentido * (i + 0.5) * paso_ang
        mx, my = cx + medio * math.cos(ang), cy + medio * math.sin(ang)
        rect = box(mx - largo / 2, my - ancho / 2, mx + largo / 2, my + ancho / 2)
        a0 = ang - sentido * paso_ang / 2
        a1 = ang + sentido * paso_ang / 2
        pasos.append({
            "poly": affinity.rotate(rect, ang, origin=(mx, my), use_radians=True),
            "tipo": "peldano",
            "borde": ((cx + radio * math.cos(a0), cy + radio * math.sin(a0)),
                      (cx + radio * math.cos(a1), cy + radio * math.sin(a1))),
            "giro": ang, "centro": (mx, my), "medidas": (largo, ancho),
        })
    return pasos


# ------------------------------------------------------------
# Elección del trazado
# ------------------------------------------------------------

def _evaluar(pasos, poligono, zonas_baja, zonas_alta, c, sube):
    fuera = sum(p["poly"].difference(poligono).area for p in pasos)
    pisa = 0.0
    for i, p in enumerate(pasos):
        alto = (i + 1) * c
        if alto - c < ALTURA_LIBRE:  # por debajo no se puede pasar
            pisa += sum(p["poly"].intersection(z).area for z in zonas_baja)
        if alto > sube - ALTURA_LIBRE:  # chocaría con el piso de arriba
            pisa += sum(p["poly"].intersection(z).area for z in zonas_alta)
    arranca = not zonas_baja or min(
        pasos[0]["poly"].distance(z) for z in zonas_baja) <= CONTACTO
    llega = not zonas_alta or min(
        pasos[-1]["poly"].distance(z) for z in zonas_alta) <= CONTACTO
    return fuera, pisa, arranca, llega


def _candidatos(poligono, T, casi_cuadrado):
    """(tipo, rango de huella, rango de tipo, pasos en el plano)."""
    x0, y0, x1, y1 = poligono.bounds
    bounds = (x0 + MARGEN, y0 + MARGEN, x1 - MARGEN, y1 - MARGEN)
    ancho, largo = bounds[2] - bounds[0], bounds[3] - bounds[1]
    variantes = [(e, fu, fv) for e in ("x", "y") for fu in (0, 1) for fv in (0, 1)]

    for rango_h, h in enumerate(HUELLAS):
        for rango_t, (tipo, trazar) in enumerate(TRAZADOS):
            for eje, fu, fv in variantes:
                Lu, Lv = (ancho, largo) if eje == "x" else (largo, ancho)
                for pasos in trazar(Lu, Lv, T, h):
                    yield tipo, rango_h, rango_t + 1, _a_plano(pasos, bounds, eje, fu, fv)

    for eje, fu, fv in variantes:
        Lu, Lv = (ancho, largo) if eje == "x" else (largo, ancho)
        pasos = _comprimida(Lu, Lv, T)
        if pasos:
            yield "comprimida", len(HUELLAS), 9, _a_plano(pasos, bounds, eje, fu, fv)

    if casi_cuadrado:
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        radio = min(x1 - x0, y1 - y0) / 2 - MARGEN - 0.02
        for barrido in BARRIDOS_CARACOL:
            for k in range(16):
                for sentido in (1, -1):
                    yield "caracol", 0, 0, _caracol(
                        cx, cy, radio, T, k * math.pi / 8, sentido, barrido
                    )


def _es_casi_cuadrado(poligono) -> bool:
    x0, y0, x1, y1 = poligono.bounds
    ancho, largo = x1 - x0, y1 - y0
    return abs(ancho - largo) < 0.15 * max(ancho, largo) and min(ancho, largo) >= 1.6


def _clave_puertas(puertas):
    return tuple(
        (tuple(round(v, 3) for v in p["centro"]), round(p["ancho"], 3),
         p["orientacion"])
        for p in puertas
    )


def trazar_escalera(poligono, puertas_baja=(), puertas_alta=(), sube=2.8) -> dict:
    """
    Escalera que sube `sube` m dentro de `poligono`.

    `puertas_baja` / `puertas_alta`: puertas del ambiente en la planta de abajo
    y en la de arriba. Devuelve {"tipo", "piezas", "hueco", "desembarco"}: las
    piezas van con alturas desde 0 (la planta de abajo), el hueco es lo que hay
    que dejar abierto en el entrepiso y el desembarco, el piso de llegada.
    """
    return _trazar(
        poligono.wkt, _clave_puertas(puertas_baja), _clave_puertas(puertas_alta),
        round(sube, 3),
    )


@lru_cache(maxsize=64)
def _trazar(poligono_wkt, baja, alta, sube):
    poligono = wkt.loads(poligono_wkt)

    def zonas(clave):
        return [
            z for z in (
                zona_libre({"centro": c, "ancho": a, "orientacion": o}, poligono)
                for c, a, o in clave
            ) if not z.is_empty
        ]

    zonas_baja, zonas_alta = zonas(baja), zonas(alta)
    n = max(3, round(sube / CONTRAHUELLA_OBJETIVO))
    c = sube / n
    T = n - 1  # el último escalón es el piso de arriba

    mejor = None
    for tipo, rango_h, rango_t, pasos in _candidatos(
        poligono, T, _es_casi_cuadrado(poligono)
    ):
        fuera, pisa, arranca, llega = _evaluar(
            pasos, poligono, zonas_baja, zonas_alta, c, sube
        )
        clave = (fuera > 0.01, pisa > 0.02, not arranca, not llega,
                 rango_h, rango_t, round(pisa, 3), round(fuera, 3))
        if mejor is None or clave < mejor[0]:
            mejor = (clave, tipo, pasos)

    clave, tipo, pasos = mejor
    desembarco = unary_union(zonas_alta) if zonas_alta else None
    huella = unary_union([p["poly"].buffer(0.03, join_style=2) for p in pasos]).buffer(
        -0.03, join_style=2
    )
    if tipo == "caracol":
        x0, y0, x1, y1 = poligono.bounds
        radio = min(x1 - x0, y1 - y0) / 2 - MARGEN
        huella = Point((x0 + x1) / 2, (y0 + y1) / 2).buffer(radio)
    hueco = huella.intersection(poligono)
    if desembarco is not None:
        hueco = hueco.difference(desembarco)

    return {
        "tipo": tipo,
        "piezas": _piezas(pasos, tipo, poligono, c, sube),
        "hueco": hueco,
        "desembarco": desembarco,
        "ultimo": pasos[-1]["poly"],
        # Qué cumple: paso libre ante las puertas, arranque y llegada junto a ellas.
        "paso_libre": not clave[1],
        "arranca_en_puerta": not clave[2],
        "llega_a_puerta": not clave[3],
    }


# ------------------------------------------------------------
# Piezas 3D
# ------------------------------------------------------------

def _piezas(pasos, tipo, poligono, c, sube) -> list:
    piezas = []

    if tipo == "caracol":
        x0, y0, x1, y1 = poligono.bounds
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        piezas.append(_caja(cx - 0.07, cy - 0.07, cx + 0.07, cy + 0.07, 0,
                            sube + ALTO_BARANDA, "metal", "cilindro"))

    for i, paso in enumerate(pasos):
        alto = (i + 1) * c
        if paso.get("centro"):
            mx, my = paso["centro"]
            largo, ancho = paso["medidas"]
            piezas.append(_caja(mx - largo / 2, my - ancho / 2, mx + largo / 2,
                                my + ancho / 2, alto - 0.05, alto, "madera",
                                giro=paso["giro"]))
        else:
            x0, y0, x1, y1 = paso["poly"].bounds
            grosor = GROSOR_DESCANSO if paso["tipo"] == "descanso" else c
            piezas.append(_caja(x0, y0, x1, y1, alto - grosor, alto, "madera"))

        if paso["borde"]:
            a, b = paso["borde"]
            if tipo != "caracol":
                zanca = _segmento(a, b, max(0.0, alto - c - 0.15), alto - c + 0.02,
                                  0.05, "oscuro")
                if zanca:
                    piezas.append(zanca)
            # Un barrote por peldaño: sus remates dibujan la pendiente.
            medio = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            piezas.append(_poste(*medio, alto, alto + ALTO_BARANDA))
    return piezas


def baranda_de_llegada(trazado, poligono, h0=0.0) -> list:
    """Baranda alrededor del hueco en la planta de arriba (no en la llegada)."""
    hueco = trazado["hueco"]
    if hueco is None or hueco.is_empty:
        return []
    bordes = hueco.boundary.difference(poligono.boundary.buffer(0.06))
    bordes = bordes.difference(trazado["ultimo"].buffer(0.08))
    if bordes.is_empty:
        return []
    lineas = linemerge(bordes) if bordes.geom_type == "MultiLineString" else bordes
    piezas = []
    for linea in getattr(lineas, "geoms", [lineas]):
        if linea.geom_type != "LineString" or linea.length < 0.15:
            continue
        coords = list(linea.coords)
        for a, b in zip(coords, coords[1:]):
            tramo = _segmento(a, b, h0 + ALTO_BARANDA - 0.04, h0 + ALTO_BARANDA,
                              0.04, "metal")
            if tramo:
                piezas.append(tramo)
        paso = max(1, int(linea.length / 0.9))
        for k in range(paso + 1):
            p = linea.interpolate(k / paso, normalized=True)
            piezas.append(_poste(p.x, p.y, h0, h0 + ALTO_BARANDA))
    return piezas
