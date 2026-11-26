"""
Muebles que acompañan a los principales: sillas alrededor de la mesa, mesa de
centro frente al sofá y el auto del garaje.
"""

from shapely.geometry import box

from src.geometry.furniture_generator import (
    construir_mobiliario,
    obtener_dimensiones,
)
from src.planning.reglas_acceso import tipo_base

SILLAS_POR_MESA = 4
SEPARACION_SILLA_M = 0.05
SILLA_COMPACTA_M = 0.40
DISTANCIAS_MESA_CENTRO_M = (0.40, 0.30, 0.20)
MESA_CENTRO_COMPACTA_M = (0.60, 0.40)
AUTOS_M = ((1.80, 4.40), (1.60, 4.00), (1.50, 3.60))
PASO_M = 0.10


def _intentar(ambiente, tipo, x, y, ancho, largo, ocupados, zonas):
    """El mueble en esa posición, o None si no cabe o estorba."""
    geometria = box(x, y, x + ancho, y + largo)
    if not ambiente["poligono"].buffer(-0.04, join_style="mitre").covers(geometria):
        return None
    if any(geometria.intersects(m["geometria"]) for m in ocupados):
        return None
    if any(geometria.intersects(z) for z in zonas):
        return None
    return construir_mobiliario({
        "tipo": tipo, "ambiente": ambiente["nombre"],
        "x": round(x, 3), "y": round(y, 3), "ancho": ancho, "largo": largo,
    })


def _sillas(ambiente, mesa, ocupados, zonas):
    """
    Hasta cuatro sillas con el respaldo hacia fuera: primero en los lados
    largos y, si ahí no entran, en las cabeceras.
    """
    x0, y0 = mesa["x"], mesa["y"]
    x1, y1 = x0 + mesa["ancho"], y0 + mesa["largo"]
    horizontal = mesa["ancho"] >= mesa["largo"]
    nuevas = []

    for lado in (obtener_dimensiones("silla")[0], SILLA_COMPACTA_M):
        s = SEPARACION_SILLA_M
        # (x, y, borde con respaldo): u0/u1 = izquierda/derecha, v0/v1 = abajo/arriba.
        largos, cabeceras = [], []
        for fraccion in (0.25, 0.75, 0.5):
            if horizontal:
                x = x0 + (x1 - x0) * fraccion - lado / 2
                largos += [(x, y0 - lado - s, "v0"), (x, y1 + s, "v1")]
            else:
                y = y0 + (y1 - y0) * fraccion - lado / 2
                largos += [(x0 - lado - s, y, "u0"), (x1 + s, y, "u1")]
        if horizontal:
            y = (y0 + y1 - lado) / 2
            cabeceras = [(x0 - lado - s, y, "u0"), (x1 + s, y, "u1")]
        else:
            x = (x0 + x1 - lado) / 2
            cabeceras = [(x, y0 - lado - s, "v0"), (x, y1 + s, "v1")]

        # Dos por lado largo, luego cabeceras y por último el centro del lado.
        for x, y, respaldo in largos[:4] + cabeceras + largos[4:]:
            if len(nuevas) == SILLAS_POR_MESA:
                return nuevas
            silla = _intentar(
                ambiente, "silla", x, y, lado, lado, ocupados + nuevas, zonas
            )
            if silla:
                silla["respaldo"] = respaldo
                nuevas.append(silla)

    return nuevas


def _mesa_de_centro(ambiente, sofa, ocupados, zonas):
    """Delante del sofá, es decir, hacia el interior de la sala."""
    centro = ambiente["poligono"].centroid
    horizontal = sofa["ancho"] >= sofa["largo"]

    for largo_mesa, fondo in (
        obtener_dimensiones("mesa_centro"), MESA_CENTRO_COMPACTA_M
    ):
        ancho, largo = (
            (largo_mesa, fondo) if horizontal else (fondo, largo_mesa)
        )
        for d in DISTANCIAS_MESA_CENTRO_M:
            # Centrada con el sofá o algo corrida hacia un extremo.
            for desvio in (0.0, -0.3, 0.3, -0.5, 0.5):
                if horizontal:
                    x = sofa["x"] + (sofa["ancho"] - ancho) / 2 + desvio
                    arriba = centro.y > sofa["y"] + sofa["largo"] / 2
                    y = (
                        sofa["y"] + sofa["largo"] + d if arriba
                        else sofa["y"] - d - largo
                    )
                else:
                    y = sofa["y"] + (sofa["largo"] - largo) / 2 + desvio
                    derecha = centro.x > sofa["x"] + sofa["ancho"] / 2
                    x = (
                        sofa["x"] + sofa["ancho"] + d if derecha
                        else sofa["x"] - d - ancho
                    )
                mesa = _intentar(
                    ambiente, "mesa_centro", x, y, ancho, largo, ocupados, zonas
                )
                if mesa:
                    return [mesa]

    return []


def _auto(ambiente, ocupados, zonas):
    """Entra de frente desde la calle: lo más centrado que se pueda."""
    x0, y0, x1, y1 = ambiente["poligono"].bounds

    for ancho, largo in AUTOS_M:
        centro_x = (x0 + x1 - ancho) / 2
        centro_y = (y0 + y1 - largo) / 2
        pasos = int(max(x1 - x0, y1 - y0) / 2 / PASO_M)
        desvios = sorted(
            (i * PASO_M for i in range(-pasos, pasos + 1)), key=abs
        )
        for dy in desvios:
            for dx in desvios:
                auto = _intentar(
                    ambiente, "auto", centro_x + dx, centro_y + dy,
                    ancho, largo, ocupados, zonas,
                )
                if auto:
                    return [auto]

    return []


def complementos_esperados(identificador: str, plantilla: list) -> int:
    """Cuántos complementos debe llevar un ambiente."""
    tipos = [item["tipo"] for item in plantilla]
    return (
        SILLAS_POR_MESA * tipos.count("mesa_comedor")
        + tipos.count("sofa")
        + (1 if tipo_base(identificador) == "garaje" else 0)
    )


def complementar(ambiente, muebles, zonas) -> list[dict]:
    """Complementos de un ambiente ya amueblado."""
    if tipo_base(ambiente["id"]) == "garaje":
        return _auto(ambiente, muebles, zonas)

    nuevos = []
    for mueble in muebles:
        if mueble["tipo"] == "mesa_comedor":
            nuevos += _sillas(ambiente, mueble, muebles + nuevos, zonas)
        elif mueble["tipo"] == "sofa":
            nuevos += _mesa_de_centro(ambiente, mueble, muebles + nuevos, zonas)
    return nuevos
