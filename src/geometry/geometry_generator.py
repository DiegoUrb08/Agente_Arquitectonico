
from shapely.geometry import Polygon


TOLERANCIA = 1e-6


def construir_poligono_ambiente(ambiente: dict) -> Polygon:
    """
    Convierte un ambiente rectangular en un polígono Shapely.

    Las coordenadas representan la esquina inferior izquierda.
    Las dimensiones están expresadas en metros.
    """

    x = float(ambiente["x"])
    y = float(ambiente["y"])
    ancho = float(ambiente["ancho"])
    largo = float(ambiente["largo"])

    if ancho <= 0 or largo <= 0:
        raise ValueError(
            f"Dimensiones inválidas en el ambiente: "
            f"{ambiente['nombre']}"
        )

    puntos = [
        (x, y),
        (x + ancho, y),
        (x + ancho, y + largo),
        (x, y + largo),
    ]

    return Polygon(puntos)


def construir_poligono_terreno(
    ancho_terreno_m: float,
    largo_terreno_m: float
) -> Polygon:
    """
    Construye el polígono rectangular del terreno.
    """

    if ancho_terreno_m <= 0 or largo_terreno_m <= 0:
        raise ValueError("Las dimensiones del terreno deben ser positivas.")

    return Polygon([
        (0, 0),
        (ancho_terreno_m, 0),
        (ancho_terreno_m, largo_terreno_m),
        (0, largo_terreno_m),
    ])


def generar_geometrias(
    distribucion: list[dict],
    ancho_terreno_m: float,
    largo_terreno_m: float
) -> dict:
    """
    Genera las geometrías de todos los ambientes
    y valida su ubicación dentro del terreno.
    """

    terreno = construir_poligono_terreno(
        ancho_terreno_m,
        largo_terreno_m
    )

    ambientes_geometricos = []
    errores = []

    # Construcción de polígonos
    for ambiente in distribucion:

        poligono = construir_poligono_ambiente(ambiente)

        if not poligono.is_valid:
            errores.append(
                f"El ambiente {ambiente['nombre']} "
                "tiene una geometría inválida."
            )

        if not terreno.buffer(TOLERANCIA).covers(poligono):
            errores.append(
                f"El ambiente {ambiente['nombre']} "
                "se encuentra fuera del terreno."
            )

        ambientes_geometricos.append({
            "id": ambiente["id"],
            "nombre": ambiente["nombre"],
            "poligono": poligono,
            "area_m2": poligono.area,
            "coordenadas": list(poligono.exterior.coords),
        })

    # Detección de superposiciones
    for i in range(len(ambientes_geometricos)):

        for j in range(i + 1, len(ambientes_geometricos)):

            ambiente_a = ambientes_geometricos[i]
            ambiente_b = ambientes_geometricos[j]

            interseccion = ambiente_a["poligono"].intersection(
                ambiente_b["poligono"]
            )

            if interseccion.area > TOLERANCIA:
                errores.append(
                    f"Los ambientes {ambiente_a['nombre']} "
                    f"y {ambiente_b['nombre']} se superponen."
                )

    return {
        "terreno": terreno,
        "ambientes": ambientes_geometricos,
        "errores": errores,
        "valido": len(errores) == 0,
    }
