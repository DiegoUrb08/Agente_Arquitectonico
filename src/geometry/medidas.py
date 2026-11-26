"""
Rectas de medición de cada ambiente (ancho y largo), compartidas por la vista
previa y el DXF. Se miden entre ejes de muro, igual que las áreas.
"""

# Distancia de la recta a la pared junto a la que se dibuja.
SEPARACION_M = 0.35
# El texto de la recta vertical va por debajo del centro, donde está el nombre.
POSICION_TEXTO_VERTICAL = 0.28


def medidas_de_ambiente(x0: float, y0: float, x1: float, y1: float) -> dict:
    """
    Rectas de un ambiente rectangular: la horizontal (ancho) junto a la pared
    superior y la vertical (largo) junto a la izquierda. Cada una trae sus
    extremos, la posición del texto y el valor en metros.
    """
    ancho, largo = x1 - x0, y1 - y0
    separacion = min(SEPARACION_M, 0.22 * min(ancho, largo))
    y = y1 - separacion
    x = x0 + separacion

    return {
        "ancho": {
            "inicio": (x0, y), "fin": (x1, y),
            "texto": (x0 + ancho / 2, y), "valor": ancho,
        },
        "largo": {
            "inicio": (x, y0), "fin": (x, y1),
            "texto": (x, y0 + largo * POSICION_TEXTO_VERTICAL), "valor": largo,
        },
    }
