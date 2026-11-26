"""
Orientación respecto al sol: dónde está el norte y hacia dónde conviene que
miren la sala y los dormitorios.

El norte se indica con el lado del terreno en el plano: "frente" (la calle,
abajo), "fondo" (arriba), "izquierda" o "derecha".
"""

import re

from src.planning.reglas_acceso import tipo_base
from src.utils.texto import normalizar_nombre

# Ambos en sentido horario, empezando arriba / en el norte.
LADOS = ("fondo", "derecha", "frente", "izquierda")
PUNTOS = ("norte", "este", "sur", "oeste")

# Pensado para Perú (hemisferio sur, trópico), de mejor a peor: la sala
# aprovecha la luz pareja del norte; el dormitorio, el sol de la mañana. El
# oeste queda último por el calor de la tarde.
PREFERENCIAS = {
    "sala": ("norte", "este", "sur", "oeste"),
    "dormitorio": ("este", "norte", "sur", "oeste"),
}

NOMBRES_NORTE = {
    "fondo": "al fondo del terreno",
    "frente": "hacia la calle",
    "derecha": "a la derecha",
    "izquierda": "a la izquierda",
}


def punto_de(lado: str, norte: str) -> str:
    """Punto cardinal hacia el que mira un lado del terreno."""
    return PUNTOS[(LADOS.index(lado) - LADOS.index(norte)) % 4]


def coste(tipo: str, punto: str) -> int:
    """0 para la mejor orientación de ese ambiente; 3 para la peor."""
    return PREFERENCIAS[tipo].index(punto)


_NORTE_EN = re.compile(
    r"\bnorte\b(?:\s+(?:esta|queda|es|da))?\s+"
    r"(?:al|a la|en el|en la|hacia el|hacia la)\s+"
    r"(fondo|frente|calle|derecha|izquierda|atras)\b"
)
_LADO_MIRA = re.compile(
    r"\b(frente|fachada|entrada|casa|vivienda|fondo|derecha|izquierda)\b"
    r"(?:\s+principal)?"
    r"(?:\s+(?:que\s+)?(?:da|mira|ve|esta|queda|orientad[ao]))?"
    r"\s+(?:al|hacia el)\s+(norte|sur|este|oeste)\b"
    r"(?!\s+de\b)"  # «al norte de Lima» es un lugar
)


def detectar_norte(texto: str) -> str | None:
    """
    Lado del norte según la descripción («el norte está al fondo», «la
    fachada mira al este»), o None si no se dice.
    """
    texto = normalizar_nombre(texto)

    directo = _NORTE_EN.search(texto)
    if directo:
        lado = directo.group(1)
        return {"calle": "frente", "atras": "fondo"}.get(lado, lado)

    indirecto = _LADO_MIRA.search(texto)
    if indirecto:
        lado, punto = indirecto.groups()
        if lado not in LADOS:
            lado = "frente"
        return next(n for n in LADOS if punto_de(lado, n) == punto)

    return None


def ventanas_por_ambiente(distribucion, ventanas, norte: str) -> dict:
    """{id: ["norte", "este"]} con hacia dónde miran sus ventanas."""
    por_id = {a["id"]: a for a in distribucion}
    miran: dict[str, set] = {}

    for ventana in ventanas:
        ambiente = por_id[ventana["ambiente_a"]]
        cx, cy = ventana["centro"]
        if ventana["orientacion"] == "vertical":
            medio = ambiente["x"] + ambiente["ancho"] / 2
            lado = "izquierda" if cx < medio else "derecha"
        else:
            medio = ambiente["y"] + ambiente["largo"] / 2
            lado = "frente" if cy < medio else "fondo"
        miran.setdefault(ambiente["id"], set()).add(punto_de(lado, norte))

    return {i: sorted(p, key=PUNTOS.index) for i, p in miran.items()}


def nota_de_orientacion(distribucion, ventanas, norte, nombres) -> str | None:
    """Resumen para el chat de la sala y los dormitorios, o None."""
    miran = ventanas_por_ambiente(distribucion, ventanas, norte)
    partes = [
        f"{nombres[a['id']]} al {' y al '.join(miran[a['id']])}"
        for a in distribucion
        if tipo_base(a["id"]) in PREFERENCIAS and a["id"] in miran
    ]
    if not partes:
        return None
    return (
        f"Con el norte {NOMBRES_NORTE[norte]}, las ventanas miran así: "
        + "; ".join(partes) + "."
    )
