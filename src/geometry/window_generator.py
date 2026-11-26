"""
Generación automática de ventanas sobre los muros exteriores.

Una pared es exterior cuando pertenece al perímetro del conjunto de
ambientes (no la comparte con otro ambiente).
"""

from shapely.geometry import LineString, MultiLineString
from shapely.ops import unary_union

from src.geometry.opening_generator import construir_abertura
from src.planning.reglas_ambientes import AMBIENTES_SIN_VENTANA as SIN_VENTANA
from src.utils.texto import normalizar_nombre

# Ancho de ventana por tipo de ambiente (m). Resto: ANCHO_PREDETERMINADO.
ANCHO_PREDETERMINADO_M = 1.20
ANCHOS_POR_AMBIENTE = {
    "sala": 1.80,
    "comedor": 1.50,
    "dormitorio": 1.20,
    "cocina": 1.20,
    "bano": 0.60,
}

MARGEN_EXTREMOS_M = 0.40
SEPARACION_M = 0.05
MAX_VENTANAS_POR_AMBIENTE = 2
TOLERANCIA = 1e-6


def _tipo_base(ambiente):
    return normalizar_nombre(ambiente["id"].rsplit("_", 1)[0])


def _tramos_rectos(geometria):
    """Tramos horizontales/verticales de una geometría lineal."""

    if geometria.is_empty:
        return []

    if isinstance(geometria, LineString):
        lineas = [geometria]
    elif isinstance(geometria, MultiLineString):
        lineas = list(geometria.geoms)
    else:
        lineas = []
        for parte in getattr(geometria, "geoms", []):
            lineas.extend(_tramos_rectos(parte))
        return lineas

    tramos = []

    for linea in lineas:
        puntos = list(linea.coords)
        # Se parte en segmentos rectos entre vértices consecutivos.
        for (x1, y1), (x2, y2) in zip(puntos, puntos[1:]):
            if abs(x1 - x2) < TOLERANCIA or abs(y1 - y2) < TOLERANCIA:
                tramos.append(LineString([(x1, y1), (x2, y2)]))

    return tramos


def _fusionar_colineales(tramos):
    """Une tramos consecutivos de la misma recta: (orientacion, valor, lo, hi)."""

    por_recta = {}
    for t in tramos:
        (x1, y1), (x2, y2) = t.coords
        if abs(x1 - x2) < TOLERANCIA:
            clave = ("v", round(x1, 4))
            lo, hi = sorted((y1, y2))
        else:
            clave = ("h", round(y1, 4))
            lo, hi = sorted((x1, x2))
        por_recta.setdefault(clave, []).append((lo, hi))

    tramos_finales = []
    for (orientacion, valor), intervalos in por_recta.items():
        intervalos.sort()
        actual = list(intervalos[0])
        for lo, hi in intervalos[1:]:
            if lo <= actual[1] + 1e-4:
                actual[1] = max(actual[1], hi)
            else:
                tramos_finales.append((orientacion, valor, *actual))
                actual = [lo, hi]
        tramos_finales.append((orientacion, valor, *actual))

    return tramos_finales


def generar_ventanas_automaticas(
    resultado_geometrias,
    espesor_muro_m=0.20,
    puertas=None,
):
    """
    Propone ventanas en las paredes exteriores de cada ambiente.

    Devuelve {"ventanas": [...], "omitidos": [...]} con el mismo formato
    de abertura que `generar_puertas_automaticas`.
    """

    ambientes = resultado_geometrias["ambientes"]

    if not ambientes:
        raise ValueError("No hay ambientes para colocar ventanas.")

    conjunto = unary_union([a["poligono"] for a in ambientes])
    perimetro = conjunto.boundary

    # Huecos ya ocupados (puertas y ventanas aceptadas), con holgura.
    ocupados = [
        construir_abertura(
            tuple(p["centro"]), p["ancho"], p["espesor_muro"], p["orientacion"]
        ).buffer(SEPARACION_M)
        for p in (puertas or {}).get("puertas", [])
    ]

    ventanas = []
    omitidos = []

    for ambiente in ambientes:

        tipo = _tipo_base(ambiente)

        if tipo in SIN_VENTANA:
            continue

        exterior = ambiente["poligono"].boundary.intersection(perimetro)
        tramos = _fusionar_colineales(_tramos_rectos(exterior))
        tramos.sort(key=lambda t: t[3] - t[2], reverse=True)

        ancho_ideal = ANCHOS_POR_AMBIENTE.get(tipo, ANCHO_PREDETERMINADO_M)
        colocadas = 0

        for orientacion, valor, lo, hi in tramos:

            if colocadas >= MAX_VENTANAS_POR_AMBIENTE:
                break

            disponible = (hi - lo) - 2 * MARGEN_EXTREMOS_M
            ancho = min(ancho_ideal, disponible)

            if ancho < 0.5:
                continue

            medio = (lo + hi) / 2

            if orientacion == "h":
                centro, orient = (round(medio, 4), round(valor, 4)), "horizontal"
            else:
                centro, orient = (round(valor, 4), round(medio, 4)), "vertical"

            ventana = {
                "tipo": "ventana",
                "centro": centro,
                "ancho": round(ancho, 3),
                "espesor_muro": espesor_muro_m,
                "orientacion": orient,
                "ambiente_a": ambiente["id"],
                "ambiente_b": None,
            }

            hueco = construir_abertura(
                centro, ventana["ancho"], espesor_muro_m, orient
            )

            if any(hueco.intersects(o) for o in ocupados):
                continue

            ocupados.append(hueco.buffer(SEPARACION_M))
            ventanas.append(ventana)
            colocadas += 1

        if colocadas == 0:
            omitidos.append(ambiente["id"])

    return {"ventanas": ventanas, "omitidos": omitidos}

