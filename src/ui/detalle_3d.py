"""
Piezas adicionales del modo «detalle alto» de la vista 3D (funciones puras).

Decoración alrededor del mobiliario existente, marcos de puertas y ventanas,
zócalos, la vereda de entrada y los acabados de los pisos. Nada de esto se
guarda en el DXF: solo enriquece la escena.
"""

from shapely.geometry import Point, box
from shapely.ops import unary_union

from src.geometry.opening_generator import construir_abertura
from src.planning.reglas_acceso import EXTERIOR, tipo_base

ALTURA_PUERTA = 2.10
ALTURA_VENTANA = 2.10
ALTO_ZOCALO = 0.08
GROSOR_ZOCALO = 0.012
ANCHO_MARCO = 0.05
SALIENTE_MARCO = 0.02
# Un mueble más alto que esto no debe quedar delante de una ventana.
ALTURA_LIBRE_VENTANA = 0.9
MARGEN_ALFOMBRA = 0.15
AREA_MINIMA_ALFOMBRA = 1.0

ACABADOS = {
    "sala": "madera", "comedor": "madera", "dormitorio": "madera",
    "estudio": "madera", "pasillo": "madera", "escalera": "madera",
    "bano": "ceramica", "cocina": "ceramica", "lavanderia": "ceramica",
    "garaje": "cemento", "deposito": "cemento", "terraza": "ceramica",
}


def acabado_de(identificador: str) -> str:
    return ACABADOS.get(tipo_base(identificador), "madera")


# ------------------------------------------------------------
# Utilidades geométricas
# ------------------------------------------------------------

def _r(valor):
    return round(float(valor), 3)


def _caja(x0, y0, x1, y1, h0, h1, material, forma="caja"):
    return {
        "forma": forma,
        "x0": _r(min(x0, x1)), "y0": _r(min(y0, y1)),
        "x1": _r(max(x0, x1)), "y1": _r(max(y0, y1)),
        "h0": _r(h0), "h1": _r(h1),
        "material": material,
    }


def _marco_local(caja, lado):
    """Igual que `escena_3d._mapear`, pero válido también fuera de la caja."""
    x0, y0, x1, y1 = caja
    if lado == "s":
        return x1 - x0, y1 - y0, lambda u, v: (x0 + u, y0 + v)
    if lado == "n":
        return x1 - x0, y1 - y0, lambda u, v: (x0 + u, y1 - v)
    if lado == "o":
        return y1 - y0, x1 - x0, lambda u, v: (x0 + v, y0 + u)
    return y1 - y0, x1 - x0, lambda u, v: (x1 - v, y0 + u)


def _colocar(mapear, partes):
    """Partes (u0, u1, v0, v1, h0, h1, material[, forma]) -> piezas del plano."""
    piezas = []
    for u0, u1, v0, v1, h0, h1, material, *forma in partes:
        (ax, ay), (bx, by) = mapear(u0, v0), mapear(u1, v1)
        piezas.append(_caja(ax, ay, bx, by, h0, h1, material,
                            forma[0] if forma else "caja"))
    return piezas


def _huella(piezas):
    return unary_union([box(p["x0"], p["y0"], p["x1"], p["y1"]) for p in piezas])


class Espacio:
    """Lo ocupado en una planta, para no poner decoración encima de nada."""

    def __init__(self, piso, ocupados):
        self.ambientes = piso.geometrias["ambientes"]
        self.muros = (piso.muros or {}).get("todos_los_muros")
        self.ocupados = list(ocupados)
        self.puertas = [
            Point(*p["centro"]).buffer(p["ancho"])
            for p in (piso.puertas or {}).get("puertas", [])
        ]
        self.ventanas = [
            construir_abertura(
                tuple(v["centro"]), v["ancho"], v["espesor_muro"], v["orientacion"]
            ).buffer(0.35)
            for v in (piso.ventanas or {}).get("ventanas", [])
        ]

    def interior(self, ambiente):
        """Suelo útil del ambiente (sin la mitad de muro que lo rodea)."""
        poligono = ambiente["poligono"]
        if self.muros is None or self.muros.is_empty:
            return poligono
        return poligono.difference(self.muros)

    def admite(self, piezas, ambiente, alto=None):
        """
        True si las piezas caben en el ambiente sin chocar con lo ocupado ni
        con el barrido de una puerta. Como el mobiliario del plano, pueden
        apoyarse hasta el eje del muro.
        """
        huella = _huella(piezas)
        if not ambiente["poligono"].buffer(1e-6).covers(huella):
            return False
        if any(huella.intersection(o).area > 1e-6 for o in self.ocupados):
            return False
        if any(huella.intersects(z) for z in self.puertas):
            return False
        alto = max(p["h1"] for p in piezas) if alto is None else alto
        if alto > ALTURA_LIBRE_VENTANA and any(huella.intersects(v) for v in self.ventanas):
            return False
        return True

    def agregar(self, piezas, ambiente, destino, alto=None):
        if not self.admite(piezas, ambiente, alto=alto):
            return False
        destino.extend(piezas)
        self.ocupados.append(_huella(piezas))
        return True

    def alfombra(self, pieza, ambiente, destino):
        """Las alfombras van debajo de los muebles: se recortan al ambiente."""
        x0, y0, x1, y1 = self.interior(ambiente).bounds
        m = MARGEN_ALFOMBRA
        recorte = box(pieza["x0"], pieza["y0"], pieza["x1"], pieza["y1"]).intersection(
            box(x0 + m, y0 + m, x1 - m, y1 - m)
        )
        if recorte.is_empty or recorte.area < AREA_MINIMA_ALFOMBRA:
            return False
        destino.append(_caja(*recorte.bounds, pieza["h0"], pieza["h1"], "alfombra"))
        return True


# ------------------------------------------------------------
# Decoración
# ------------------------------------------------------------

def _silla(u0, u1, v0, v1, respaldo):
    """Silla en coordenadas locales; `respaldo` es el borde con respaldo."""
    pata = 0.04
    partes = [(u0, u1, v0, v1, 0.43, 0.47, "madera")]
    for a in (u0 + 0.02, u1 - 0.02 - pata):
        for b in (v0 + 0.02, v1 - 0.02 - pata):
            partes.append((a, a + pata, b, b + pata, 0.0, 0.43, "madera"))
    franja = {
        "v0": (u0, u1, v0, v0 + 0.05), "v1": (u0, u1, v1 - 0.05, v1),
        "u0": (u0, u0 + 0.05, v0, v1), "u1": (u1 - 0.05, u1, v0, v1),
    }[respaldo]
    partes.append((*franja, 0.47, 0.92, "madera"))
    return partes


def _sillas_comedor(mesa, espacio, ambiente, destino):
    W, D, mapear = _marco_local(mesa["caja"], "s")
    lado, hueco = 0.45, 0.12
    n = max(1, int((W + 0.05) // 0.6))
    paso = W / n
    for i in range(n):
        u = i * paso + (paso - lado) / 2
        for v0, v1, respaldo in (
            (-hueco - lado, -hueco, "v0"), (D + hueco, D + hueco + lado, "v1"),
        ):
            espacio.agregar(
                _colocar(mapear, _silla(u, u + lado, v0, v1, respaldo)),
                ambiente, destino, alto=0.47,
            )
    v = (D - lado) / 2
    for u0, u1, respaldo in (
        (-hueco - lado, -hueco, "u0"), (W + hueco, W + hueco + lado, "u1"),
    ):
        espacio.agregar(
            _colocar(mapear, _silla(u0, u1, v, v + lado, respaldo)),
            ambiente, destino, alto=0.47,
        )


def _velador(u0, u1):
    medio = (u0 + u1) / 2
    return [
        (u0, u1, 0.03, 0.45, 0.0, 0.5, "madera"),
        (medio - 0.09, medio + 0.09, 0.15, 0.33, 0.5, 0.72, "luz", "cilindro"),
    ]


def _dormitorio(cama, espacio, ambiente, destino):
    W, D, mapear = _marco_local(cama["caja"], cama["lado"])
    for u0, u1 in ((-0.5, -0.06), (W + 0.06, W + 0.5)):
        espacio.agregar(_colocar(mapear, _velador(u0, u1)), ambiente, destino)
    espacio.alfombra(
        _colocar(mapear, [(-0.35, W + 0.35, D * 0.4, D + 0.6, 0.04, 0.055,
                           "alfombra")])[0],
        ambiente, destino,
    )


def _profundidad(ambiente_interior, caja, lado):
    """Distancia desde el respaldo del mueble hasta la pared de enfrente."""
    x0, y0, x1, y1 = caja
    ax0, ay0, ax1, ay1 = ambiente_interior.bounds
    return {"s": ay1 - y0, "n": y1 - ay0, "o": ax1 - x0, "e": x1 - ax0}[lado]


def _esquinas(interior, lado_pieza):
    x0, y0, x1, y1 = interior.bounds
    m, t = 0.08, lado_pieza
    return [
        (x0 + m, y0 + m), (x1 - m - t, y0 + m),
        (x0 + m, y1 - m - t), (x1 - m - t, y1 - m - t),
    ]


def _planta(x, y):
    return [
        _caja(x + 0.07, y + 0.07, x + 0.38, y + 0.38, 0.0, 0.38, "maceta", "cilindro"),
        _caja(x, y, x + 0.45, y + 0.45, 0.38, 1.05, "planta", "esfera"),
    ]


def _lampara(x, y):
    return [
        _caja(x + 0.07, y + 0.07, x + 0.33, y + 0.33, 0.0, 0.03, "metal", "cilindro"),
        _caja(x + 0.185, y + 0.185, x + 0.215, y + 0.215, 0.03, 1.4, "metal", "cilindro"),
        _caja(x, y, x + 0.4, y + 0.4, 1.35, 1.65, "luz", "cilindro"),
    ]


def _sala(sofa, espacio, ambiente, destino):
    W, D, mapear = _marco_local(sofa["caja"], sofa["lado"])
    espacio.alfombra(
        _colocar(mapear, [(0.1, W - 0.1, D + 0.2, D + 1.7, 0.04, 0.055,
                           "alfombra")])[0],
        ambiente, destino,
    )
    centro = W / 2
    espacio.agregar(
        _colocar(mapear, [(centro - 0.5, centro + 0.5, D + 0.45, D + 1.0,
                           0.0, 0.42, "madera")]),
        ambiente, destino,
    )
    fondo = _profundidad(ambiente["poligono"], sofa["caja"], sofa["lado"])
    if fondo > D + 1.6:
        # Frente al sofá; si ahí abre una puerta, se corre por la pared.
        desvios = sorted((i * 0.3 for i in range(-12, 13)), key=abs)
        colocado = False
        for medio_ancho in (0.8, 0.6):
            for desvio in desvios:
                u = centro + desvio
                pantalla = medio_ancho - 0.2
                colocado = espacio.agregar(
                    _colocar(mapear, [
                        (u - medio_ancho, u + medio_ancho, fondo - 0.45,
                         fondo - 0.02, 0.0, 0.5, "madera_oscura"),
                        (u - pantalla, u + pantalla, fondo - 0.25, fondo - 0.2,
                         0.55, 1.2, "pantalla"),
                        (u - 0.1, u + 0.1, fondo - 0.3, fondo - 0.15, 0.5, 0.55,
                         "oscuro"),
                    ]),
                    ambiente, destino, alto=0.5,
                )
                if colocado:
                    break
            if colocado:
                break
    pendientes = [_planta, _lampara]
    for x, y in _esquinas(ambiente["poligono"], 0.45):
        if not pendientes:
            break
        if espacio.agregar(pendientes[0](x, y), ambiente, destino):
            pendientes.pop(0)


def _cocina(cocina, espacio, ambiente, destino):
    W, D, mapear = _marco_local(cocina["caja"], cocina["lado"])
    tramo = [0.0, W]
    for paso in range(1, 4):
        for extremo in (0, 1):
            u0, u1 = (tramo[0] - 0.6, tramo[0]) if extremo == 0 else (tramo[1], tramo[1] + 0.6)
            mesada = _colocar(mapear, [
                (u0, u1, 0, D, 0.0, 0.88, "blanco"),
                (u0, u1, 0, D, 0.88, 0.92, "oscuro"),
            ])
            if espacio.agregar(mesada, ambiente, destino):
                tramo[extremo] = u0 if extremo == 0 else u1
    alto = _colocar(mapear, [(tramo[0], tramo[1], 0, 0.35, 1.45, 2.15, "blanco")])
    if not any(_huella(alto).intersects(v) for v in espacio.ventanas):
        destino.extend(alto)


def _bano(lavatorio, espacio, ambiente, destino):
    W, D, mapear = _marco_local(lavatorio["caja"], lavatorio["lado"])
    espejo = _colocar(mapear, [(0.05, W - 0.05, 0.0, 0.02, 1.05, 1.75, "espejo")])
    if not any(_huella(espejo).intersects(v) for v in espacio.ventanas):
        destino.extend(espejo)
    espacio.agregar(
        _colocar(mapear, [
            (W + 0.12, W + 0.62, 0.0, 0.05, 1.08, 1.12, "metal"),
            (W + 0.17, W + 0.57, 0.02, 0.07, 0.62, 1.1, "toalla"),
        ]),
        ambiente, destino, alto=0.5,
    )


def _estudio(escritorio, espacio, ambiente, destino):
    W, D, mapear = _marco_local(escritorio["caja"], escritorio["lado"])
    medio = W / 2
    espacio.agregar(
        _colocar(mapear, _silla(medio - 0.23, medio + 0.23, D + 0.08, D + 0.54, "v1")),
        ambiente, destino, alto=0.47,
    )


DECORADORES = {
    "mesa_comedor": _sillas_comedor,
    "cama_matrimonial": _dormitorio,
    "cama_queen": _dormitorio,
    "cama_individual": _dormitorio,
    "sofa": _sala,
    "cocina": _cocina,
    "lavatorio": _bano,
    "escritorio": _estudio,
}


def decoracion(piso, muebles: list[dict]) -> list[dict]:
    """
    Piezas decorativas. `muebles` son los del plano con `caja`, `lado` y
    `ambiente` (el dict de geometría donde están).
    """
    espacio = Espacio(piso, [box(*m["caja"]) for m in muebles])
    piezas: list[dict] = []
    for mueble in muebles:
        decorar = DECORADORES.get(mueble["tipo"])
        if decorar and mueble["ambiente"] is not None:
            decorar(mueble, espacio, mueble["ambiente"], piezas)
    return piezas


# ------------------------------------------------------------
# Arquitectura
# ------------------------------------------------------------

def _hueco(abertura):
    return construir_abertura(
        tuple(abertura["centro"]), abertura["ancho"],
        abertura["espesor_muro"], abertura["orientacion"],
    ).bounds


def _a_lo_largo(abertura, bounds, desde, hasta, salida, h0, h1, material):
    """Caja de `desde` a `hasta` a lo largo del muro, que sobresale `salida`."""
    x0, y0, x1, y1 = bounds
    if abertura["orientacion"] == "horizontal":
        return _caja(x0 + desde, y0 - salida, x0 + hasta, y1 + salida, h0, h1, material)
    return _caja(x0 - salida, y0 + desde, x1 + salida, y0 + hasta, h0, h1, material)


def marco_de_puerta(puerta):
    bounds = _hueco(puerta)
    ancho = puerta["ancho"]
    s, a = SALIENTE_MARCO, ANCHO_MARCO
    return [
        _a_lo_largo(puerta, bounds, 0, a, s, 0, ALTURA_PUERTA, "marco"),
        _a_lo_largo(puerta, bounds, ancho - a, ancho, s, 0, ALTURA_PUERTA, "marco"),
        _a_lo_largo(puerta, bounds, -a, ancho + a, s, ALTURA_PUERTA,
                    ALTURA_PUERTA + 0.07, "marco"),
    ]


def marco_de_ventana(ventana, antepecho):
    bounds = _hueco(ventana)
    ancho = ventana["ancho"]
    s, a = SALIENTE_MARCO, ANCHO_MARCO
    medio = ancho / 2
    piezas = [
        _a_lo_largo(ventana, bounds, 0, a, 0, antepecho, ALTURA_VENTANA, "marco"),
        _a_lo_largo(ventana, bounds, ancho - a, ancho, 0, antepecho, ALTURA_VENTANA, "marco"),
        _a_lo_largo(ventana, bounds, 0, ancho, 0, ALTURA_VENTANA - a, ALTURA_VENTANA, "marco"),
        _a_lo_largo(ventana, bounds, -0.04, ancho + 0.04, s + 0.04, antepecho - 0.03,
                    antepecho, "marco"),
    ]
    if ancho >= 0.9:
        piezas.append(_a_lo_largo(ventana, bounds, medio - 0.02, medio + 0.02, -0.08,
                                  antepecho, ALTURA_VENTANA, "marco"))
    return piezas


def zocalos(piso) -> list[dict]:
    """Franjas de zócalo junto a los muros, cortadas en los vanos de puertas."""
    muros = (piso.muros or {}).get("todos_los_muros")
    if muros is None or muros.is_empty:
        return []
    puertas = unary_union([
        box(*_hueco(p)).buffer(0.12)
        for p in (piso.puertas or {}).get("puertas", [])
    ])
    prismas = []
    for ambiente in piso.geometrias["ambientes"]:
        interior = ambiente["poligono"].difference(muros)
        franja = interior.boundary.buffer(GROSOR_ZOCALO).intersection(interior)
        if not puertas.is_empty:
            franja = franja.difference(puertas)
        for parte in getattr(franja, "geoms", [franja]):
            if parte.geom_type != "Polygon" or parte.area < 1e-4:
                continue
            prismas.append({
                "anillos": [
                    [[_r(x), _r(y)] for x, y in list(anillo.coords)[:-1]]
                    for anillo in (parte.exterior, *parte.interiors)
                ],
                "h0": 0.04, "h1": 0.04 + ALTO_ZOCALO, "material": "zocalo",
            })
    return prismas


def entrada(piso) -> list[dict]:
    """Escalón y vereda frente a la puerta exterior, hasta el borde del terreno."""
    tx0, ty0, tx1, ty1 = piso.geometrias["terreno"].bounds
    vivienda = unary_union([a["poligono"] for a in piso.geometrias["ambientes"]])
    piezas = []
    for puerta in (piso.puertas or {}).get("puertas", []):
        if puerta.get("ambiente_b") != EXTERIOR:
            continue
        cx, cy = puerta["centro"]
        horizontal = puerta["orientacion"] == "horizontal"
        normal = (0, 1) if horizontal else (1, 0)
        signo = -1 if vivienda.covers(Point(cx + normal[0] * 0.3, cy + normal[1] * 0.3)) else 1
        cara = puerta["espesor_muro"] / 2
        medio = puerta["ancho"] / 2 + 0.2
        if horizontal:
            y0 = cy + signo * cara
            piezas.append(_caja(cx - medio, y0, cx + medio, y0 + signo * 0.45, 0, 0.12, "cemento"))
            borde = ty0 if signo < 0 else ty1
            if abs(borde - y0) > 0.46:
                piezas.append(_caja(cx - 0.5, y0 + signo * 0.45, cx + 0.5, borde, 0, 0.03, "cemento"))
        else:
            x0 = cx + signo * cara
            piezas.append(_caja(x0, cy - medio, x0 + signo * 0.45, cy + medio, 0, 0.12, "cemento"))
            borde = tx0 if signo < 0 else tx1
            if abs(borde - x0) > 0.46:
                piezas.append(_caja(x0 + signo * 0.45, cy - 0.5, borde, cy + 0.5, 0, 0.03, "cemento"))
    return piezas
