"""
Nombres de habitaciones escritos en DXF de otros programas.

Traduce los textos del dibujo ("LIVING", "Dorm. 2", "WC", "Kitchen") a los
tipos del catálogo del agente.
"""

import re

from src.utils.texto import normalizar_nombre

# Frases (ya normalizadas: minúsculas, sin tildes) -> nombre del catálogo.
SINONIMOS = {
    "sala": ("sala", "sala de estar", "estar", "living", "living room",
             "lounge", "salon", "family", "family room", "sala comedor"),
    "comedor": ("comedor", "dining", "dining room", "comedor diario"),
    "cocina": ("cocina", "kitchen", "kitchenette", "cocineta"),
    "dormitorio principal": (
        "dormitorio principal", "dorm principal", "dorm princ",
        "habitacion principal", "recamara principal", "cuarto principal",
        "master", "master bedroom", "suite", "main bedroom",
    ),
    "dormitorio": ("dormitorio", "dorm", "habitacion", "hab", "recamara",
                   "alcoba", "cuarto", "bedroom", "bed", "bed room"),
    "baño": ("bano", "banos", "medio bano", "bath", "bathroom", "wc",
             "toilet", "aseo", "ss hh", "sshh", "s h", "servicio higienico",
             "servicios higienicos", "half bath", "restroom", "powder room"),
    "pasillo": ("pasillo", "hall", "hallway", "corridor", "circulacion",
                "distribuidor", "corredor", "vestibulo", "recibidor",
                "foyer", "lobby", "entrada", "hall de entrada"),
    "lavandería": ("lavanderia", "lavadero", "laundry", "cuarto de lavado",
                   "patio de servicio", "utility", "utility room"),
    "estudio": ("estudio", "oficina", "escritorio", "study", "office",
                "biblioteca", "library", "den"),
    "closet": ("closet", "vestidor", "walk in", "walk in closet",
               "ropero", "armario", "wardrobe"),
    "depósito": ("deposito", "bodega", "despensa", "almacen", "storage",
                 "pantry", "trastero", "cuarto util"),
    "terraza": ("terraza", "balcon", "terrace", "balcony", "deck", "porch",
                "porche", "galeria"),
    "garaje": ("garaje", "garage", "cochera", "estacionamiento",
               "parking", "carport"),
    "escalera": ("escalera", "escaleras", "stair", "stairs", "staircase",
                 "caja de escalera"),
}

# Abreviaturas frecuentes ("DORM.", "COC.", "LAV."), por prefijo de palabra.
ABREVIATURAS = {
    "dorm": "dormitorio", "habit": "dormitorio", "recam": "dormitorio",
    "coc": "cocina", "kitch": "cocina", "com": "comedor",
    "lav": "lavandería", "esc": "escalera", "estud": "estudio",
    "ofic": "estudio", "depos": "depósito", "terr": "terraza",
    "gar": "garaje", "pas": "pasillo", "bedr": "dormitorio",
    "bathr": "baño",
}

_FRASES = sorted(
    ((frase, tipo) for tipo, frases in SINONIMOS.items() for frase in frases),
    key=lambda par: -len(par[0]),
)

# Cotas, áreas, niveles y números sueltos: no son nombres.
_NO_ES_NOMBRE = re.compile(
    r"^[\s\d.,:+\-x×=()°/]*(m2|m²|m|cm|mm|ft|sf|sq ?ft|npt|nfp)?[\s\d.,]*$"
)


def limpiar(texto: str) -> str:
    """Normaliza y deja solo letras y espacios ("Dorm.2" -> "dorm 2")."""
    texto = normalizar_nombre(texto).replace("ñ", "n")
    texto = re.sub(r"[^a-z0-9]+", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def es_nombre(texto: str) -> bool:
    """False para áreas, cotas, niveles o números sueltos."""
    limpio = normalizar_nombre(texto).strip()
    if re.search(r"\d", limpio) and re.search(
        r"\b(m2|area|sup|npt|nfp|nivel|n p t)\b|m²", limpiar(texto) + " " + limpio
    ):
        return False
    return bool(limpio) and not _NO_ES_NOMBRE.match(limpio) and bool(
        re.search(r"[a-z]{2,}", limpiar(texto))
    )


def tipo_desde_texto(texto: str) -> str | None:
    """Tipo del catálogo para un texto del dibujo, o None si no se reconoce."""
    limpio = limpiar(texto)
    if not limpio:
        return None

    for frase, tipo in _FRASES:
        if re.search(rf"(^| ){re.escape(frase)}( |$)", limpio):
            # "baño principal" es un baño; "dorm principal" ya está arriba.
            return tipo

    for palabra in limpio.split():
        for prefijo, tipo in ABREVIATURAS.items():
            if palabra.startswith(prefijo):
                return tipo

    return None


# Etiquetas de planta escritas en el dibujo.
_PLANTA_ALTA = re.compile(
    r"planta alta|segundo (piso|nivel)|2 ?(do|°|º)? ?(piso|nivel)|"
    r"second floor|upper floor|upper level|nivel superior|altillo"
)
_PLANTA_BAJA = re.compile(
    r"planta baja|primer (piso|nivel)|1 ?(er|ro|°|º)? ?(piso|nivel)|"
    r"ground floor|ground level|planta principal"
)


def planta_de_texto(texto: str) -> str | None:
    """'alta', 'baja' o None según una etiqueta como «PLANTA ALTA»."""
    limpio = normalizar_nombre(texto)
    if _PLANTA_ALTA.search(limpio):
        return "alta"
    if _PLANTA_BAJA.search(limpio):
        return "baja"
    return None
