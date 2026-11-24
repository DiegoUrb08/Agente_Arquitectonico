"""Traducción de errores de validación del modelo a mensajes para el usuario."""

from pydantic import ValidationError

PISTAS = (
    (
        "area_objetivo",
        "el modelo no pudo asignar una superficie a lo pedido; "
        "probablemente no es un ambiente soportado "
        "(p. ej. piscina, garaje o jardín)",
    ),
    (
        "operaciones",
        "no se reconoció ninguna modificación válida",
    ),
    (
        "tipo",
        "la operación pedida no existe; solo se puede cambiar el área "
        "de un ambiente o moverlo respecto a otro",
    ),
    (
        "relacion",
        "no se entendió la posición pedida; usa izquierda, derecha, "
        "arriba, abajo, junto a o cerca de",
    ),
    (
        "referencia",
        "falta indicar respecto a qué ambiente se debe mover",
    ),
)


def mensaje_amigable(error: Exception, contexto: str) -> str:
    """
    Construye un mensaje legible a partir de un error de validación.

    `contexto` describe la operación ("la edición", "los requerimientos").
    El detalle técnico se conserva al final entre paréntesis.
    """

    texto = str(error)
    motivos = []

    if isinstance(error, ValidationError):
        campos = " ".join(
            ".".join(str(parte) for parte in fallo["loc"])
            for fallo in error.errors()
        )
    else:
        campos = texto

    for clave, explicacion in PISTAS:
        if clave in campos and explicacion not in motivos:
            motivos.append(explicacion)

    if not motivos:
        motivos.append("la respuesta del modelo no tiene el formato esperado")

    resumen = "; ".join(motivos)

    return (
        f"No se pudo validar {contexto}: {resumen}. "
        "Reformula la petición con ambientes habituales de una vivienda. "
        f"(Detalle: {_primera_linea(texto)})"
    )


def _primera_linea(texto: str) -> str:
    for linea in texto.splitlines():
        if linea.strip():
            return linea.strip()
    return "sin detalle"
