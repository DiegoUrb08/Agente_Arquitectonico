"""
Generación automática de ventanas sobre los muros exteriores.

Una pared es exterior cuando pertenece al perímetro del conjunto de
ambientes (no la comparte con otro ambiente) o da a un hueco interior lo
bastante grande para ser un patio.

La ventana va centrada en la pared; si ahí hay una puerta, se corre al tramo
libre más amplio.
"""

from shapely.geometry import LineString, MultiLineString, Polygon, box
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
ANCHO_MINIMO_M = 0.50
SEPARACION_M = 0.05
# Distancia a una puerta cuando la ventana no puede ir centrada.
SEPARACION_CORRIDA_M = 0.15
# Un hueco entre ambientes solo ilumina si es un patio.
AREA_MINIMA_PATIO_M2 = 4.0
ANCHO_MINIMO_PATIO_M = 1.5
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


def _perimetro_exterior(conjunto):
    """Contorno de la vivienda más el de sus patios."""
    anillos = []
    for parte in getattr(conjunto, "geoms", [conjunto]):
        anillos.append(parte.exterior)
        for interior in parte.interiors:
            hueco = Polygon(interior)
            if (
                hueco.area >= AREA_MINIMA_PATIO_M2
                and not hueco.buffer(-ANCHO_MINIMO_PATIO_M / 2).is_empty
            ):
                anillos.append(interior)
    return unary_union([LineString(a.coords) for a in anillos])


def _posiciones(tramo, ancho_ideal, espesor, ocupados):
    """
    (centro, ancho) candidatos a lo largo del tramo, el preferido primero:
    centrada y, si no, en los espacios que dejan los huecos ya ocupados.
    """
    orientacion, valor, lo, hi = tramo
    inicio, fin = lo + MARGEN_EXTREMOS_M, hi - MARGEN_EXTREMOS_M
    ancho = min(ancho_ideal, fin - inicio)

    if ancho < ANCHO_MINIMO_M:
        return

    yield (lo + hi) / 2, ancho

    medio = espesor / 2
    if orientacion == "h":
        franja = box(lo, valor - medio, hi, valor + medio)
        eje = 0
    else:
        franja = box(valor - medio, lo, valor + medio, hi)
        eje = 1

    bloqueados = sorted(
        (parte.bounds[eje] - SEPARACION_CORRIDA_M,
         parte.bounds[eje + 2] + SEPARACION_CORRIDA_M)
        for parte in (franja.intersection(o) for o in ocupados)
        if parte.area > TOLERANCIA
    )

    libres = []
    for desde, hasta in bloqueados:
        if desde > inicio:
            libres.append((inicio, min(desde, fin)))
        inicio = max(inicio, hasta)
    libres.append((inicio, fin))

    for desde, hasta in sorted(libres, key=lambda t: t[1] - t[0], reverse=True):
        ancho = min(ancho_ideal, hasta - desde)
        if ancho >= ANCHO_MINIMO_M - TOLERANCIA:
            # Redondeo hacia abajo: no debe invadir la separación.
            yield (desde + hasta) / 2, int(ancho * 1000) / 1000


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
    perimetro = _perimetro_exterior(conjunto)

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

        for tramo in tramos:

            if colocadas >= MAX_VENTANAS_POR_AMBIENTE:
                break

            orientacion, valor = tramo[:2]

            for medio, ancho in _posiciones(
                tramo, ancho_ideal, espesor_muro_m, ocupados
            ):
                if orientacion == "h":
                    centro = (round(medio, 4), round(valor, 4))
                    orient = "horizontal"
                else:
                    centro = (round(valor, 4), round(medio, 4))
                    orient = "vertical"

                ancho = round(ancho, 3)
                hueco = construir_abertura(centro, ancho, espesor_muro_m, orient)

                if any(hueco.intersects(o) for o in ocupados):
                    continue

                ocupados.append(hueco.buffer(SEPARACION_M))
                ventanas.append({
                    "tipo": "ventana",
                    "centro": centro,
                    "ancho": ancho,
                    "espesor_muro": espesor_muro_m,
                    "orientacion": orient,
                    "ambiente_a": ambiente["id"],
                    "ambiente_b": None,
                })
                colocadas += 1
                break

        if colocadas == 0:
            omitidos.append(ambiente["id"])

    return {"ventanas": ventanas, "omitidos": omitidos}

