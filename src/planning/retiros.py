"""
Retiros del terreno y ubicación de la casa en el lote.

La planta se resuelve dentro del área edificable (el terreno menos los
retiros) y después se coloca pegada al retiro frontal y centrada a lo ancho.
"""

import math
import re

from src.models.requirements import RequerimientosArquitectonicos, Retiros
from src.utils.texto import normalizar_nombre

_ZONAS = {
    "frontal": ("frontal",), "frente": ("frontal",), "delantero": ("frontal",),
    "calle": ("frontal",),
    "posterior": ("posterior",), "fondo": ("posterior",),
    "atras": ("posterior",),
    "lateral": ("izquierdo", "derecho"), "laterales": ("izquierdo", "derecho"),
    "lados": ("izquierdo", "derecho"),
    "izquierdo": ("izquierdo",), "izquierda": ("izquierdo",),
    "derecho": ("derecho",), "derecha": ("derecho",),
}
_ZONA = re.compile(r"\b(" + "|".join(_ZONAS) + r")\b")
# Metros, no metros cuadrados.
_METROS = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(?:metros?(?!\s+cuadrados)|mts?|m)(?![\w²^])"
)
# Un número sin unidad solo vale justo detrás de la zona: "frontal 3".
_SUELTO = re.compile(
    r"(?:" + "|".join(_ZONAS) + r")\s*(?:de|:|=)?\s*(\d+(?:[.,]\d+)?)"
    r"(?!\s*(?:m2|m²|x\b|\d))\b"
)
_CORTES = re.compile(r",(?!\d)|\by\b|\be\b")


def detectar_retiros(texto: str) -> Retiros | None:
    """
    Retiros que menciona la descripción («retiro frontal de 3 m», «retiros
    laterales y posterior de 1,5 m»). Sin zona se entiende el frontal.
    """
    texto = normalizar_nombre(texto)
    valores: dict[str, float] = {}

    for frase in re.split(r"[;\n]|\.(?!\d)", texto):
        inicio = frase.find("retiro")
        if inicio < 0 or re.search(r"\bsin\s+$", frase[:inicio]):
            continue

        pendientes: list[str] = []
        for trozo in _CORTES.split(frase[inicio:]):
            zonas = [z for m in _ZONA.findall(trozo) for z in _ZONAS[m]]
            numero = _METROS.search(trozo) or _SUELTO.search(trozo)
            # Otro asunto de la misma frase: se terminaron los retiros.
            if not zonas and "retiro" not in trozo and not (
                pendientes and numero
            ):
                if numero or trozo.strip():
                    break
            pendientes += zonas
            if numero:
                metros = float(numero.group(1).replace(",", "."))
                for zona in pendientes or ["frontal"]:
                    valores[zona] = metros
                pendientes = []

    valores = {z: v for z, v in valores.items() if 0 < v <= 100}
    return Retiros(**valores) if valores else None


def area_edificable(
    ancho: float, largo: float, retiros: Retiros | None
) -> tuple[float, float]:
    """(ancho, largo) que quedan para construir."""
    retiros = retiros or Retiros()
    util_ancho = round(ancho - retiros.izquierdo - retiros.derecho, 4)
    util_largo = round(largo - retiros.frontal - retiros.posterior, 4)
    if util_ancho <= 0 or util_largo <= 0:
        raise ValueError(
            f"Los retiros no dejan sitio para construir en un terreno de "
            f"{ancho:g} × {largo:g} m."
        )
    return util_ancho, util_largo


def reducir_al_area_edificable(
    requerimientos: RequerimientosArquitectonicos,
) -> RequerimientosArquitectonicos:
    """Los mismos requerimientos sobre un terreno sin las franjas de retiro."""
    ancho, largo = area_edificable(
        requerimientos.ancho_terreno_m, requerimientos.largo_terreno_m,
        requerimientos.retiros,
    )
    return requerimientos.model_copy(update={
        "ancho_terreno_m": ancho,
        "largo_terreno_m": largo,
        "retiros": None,
    })


def trasladar(distribucion: list[dict], dx: float, dy: float) -> list[dict]:
    return [
        {**a, "x": round(a["x"] + dx, 4), "y": round(a["y"] + dy, 4)}
        for a in distribucion
    ]


def ubicar(
    distribuciones: list[list[dict]], ancho: float, largo: float,
    retiros: Retiros | None, centrar: bool = False,
) -> list[list[dict]]:
    """
    Lleva las plantas, resueltas en el área edificable, a su sitio en el
    terreno: al frente y centradas a lo ancho. Todas se mueven igual.

    Con `centrar`, la casa también queda centrada en profundidad (y no pegada
    a la calle): para lotes calculados desde el área de la vivienda.
    """
    retiros = retiros or Retiros()
    util_ancho, util_largo = area_edificable(ancho, largo, retiros)
    todos = [a for distribucion in distribuciones for a in distribucion]
    x0 = min(a["x"] for a in todos)
    x1 = max(a["x"] + a["ancho"] for a in todos)
    y0 = min(a["y"] for a in todos)
    y1 = max(a["y"] + a["largo"] for a in todos)

    # Hacia abajo al decímetro: nunca invade el retiro derecho.
    margen = math.floor((util_ancho - (x1 - x0)) / 2 * 10 + 1e-6) / 10
    dx = retiros.izquierdo + max(0.0, margen) - x0
    if centrar:
        holgura = math.floor((util_largo - (y1 - y0)) / 2 * 10 + 1e-6) / 10
        dy = retiros.frontal + max(0.0, holgura) - y0
    else:
        dy = retiros.frontal - y0

    return [trasladar(d, dx, dy) for d in distribuciones]


def nota_de_retiros(ancho: float, largo: float, retiros: Retiros) -> str:
    util_ancho, util_largo = area_edificable(ancho, largo, retiros)
    partes = [
        f"{zona} {valor:g} m"
        for zona, valor in retiros.model_dump().items() if valor
    ]
    return (
        f"Retiros aplicados: {', '.join(partes)}. Área edificable: "
        f"{util_ancho:g} × {util_largo:g} m."
    )
