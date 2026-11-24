"""Configuración y reglas por tipo de ambiente para el optimizador."""

import math

from src.utils.texto import normalizar_nombre


# ============================================================
# 1. CONFIGURACIÓN GENERAL
# ============================================================

# Todas las dimensiones se trabajan en decímetros (dm).
# Las áreas se trabajan en decímetros cuadrados (dm²).

MIN_LADO_DM = 10

TIEMPO_MAXIMO_SEGUNDOS = 15

# Longitud mínima de frontera compartida entre dos ambientes.
# 8 dm = 0.80 metros.

LONGITUD_MINIMA_ADYACENCIA_DM = 8


# ------------------------------------------------------------
# PROPORCIONES MÁXIMAS POR TIPO DE AMBIENTE
# ------------------------------------------------------------

PROPORCIONES_AMBIENTES = {
    "sala": 1.8,
    "comedor": 1.8,
    "cocina": 1.8,
    "dormitorio": 1.6,
    "bano": 1.5,
    "lavanderia": 1.8,
    "estudio": 1.6,
    "terraza": 2.0,
    "escalera": 2.5,
}

PROPORCION_DEFAULT = 2.0


# ------------------------------------------------------------
# CLASIFICACIÓN DE AMBIENTES POR ZONAS
# ------------------------------------------------------------

AMBIENTES_SOCIALES = {
    "sala",
    "comedor",
    "cocina",
    "terraza",
}

AMBIENTES_PRIVADOS = {
    "dormitorio",
    "dormitorio principal",
    "estudio",
}

AMBIENTES_SERVICIO = {
    "bano",
    "lavanderia",
}

# Tipos de ambiente reconocidos por el sistema.
# Cualquier nombre que no sea prefijado por una clave de esta lista
# se rechaza antes de llegar al optimizador.
AMBIENTES_VALIDOS = {
    "sala",
    "comedor",
    "cocina",
    "dormitorio",
    "dormitorio principal",
    "bano",
    "lavanderia",
    "estudio",
    "oficina",
    "terraza",
    "garaje",
    "cochera",
    "pasillo",
    "closet",
    "deposito",
    "escalera",
}

# Ambientes que van preferentemente en la planta baja.
AMBIENTES_PLANTA_BAJA = {
    "sala", "comedor", "cocina", "lavanderia", "garaje", "cochera",
    "terraza", "estudio", "oficina", "deposito",
}

# Ambientes que van preferentemente en pisos superiores.
AMBIENTES_PLANTA_ALTA = {
    "dormitorio", "dormitorio principal", "bano", "closet", "pasillo",
}


# ------------------------------------------------------------
# DIMENSIONES DE REFERENCIA EN DECÍMETROS
# ------------------------------------------------------------

DIMENSIONES_REFERENCIA = {
    "dormitorio": (30, 30),
    "sala": (40, 40),
    "cocina": (30, 30),
    "bano": (15, 20),
    "comedor": (30, 30),
    "lavanderia": (20, 20),
    "estudio": (30, 30),
    "terraza": (30, 30),
    "escalera": (25, 15),
}


# ============================================================
# 2. FUNCIONES AUXILIARES
# ============================================================

# ------------------------------------------------------------
# OBTENER DIMENSIONES DE REFERENCIA
# ------------------------------------------------------------

def obtener_dimensiones_referencia(nombre: str):
    """
    Obtiene las dimensiones de referencia
    de un ambiente.
    """

    nombre = normalizar_nombre(nombre)

    if nombre in DIMENSIONES_REFERENCIA:
        return DIMENSIONES_REFERENCIA[nombre]

    if "dormitorio" in nombre:
        return DIMENSIONES_REFERENCIA["dormitorio"]

    if "bano" in nombre:
        return DIMENSIONES_REFERENCIA["bano"]

    return (30, 30)


# ------------------------------------------------------------
# OBTENER PROPORCIÓN MÁXIMA
# ------------------------------------------------------------

def obtener_proporcion_maxima(nombre: str) -> float:
    """
    Obtiene la proporción máxima permitida
    según el tipo de ambiente.
    """

    nombre = normalizar_nombre(nombre)

    if nombre in PROPORCIONES_AMBIENTES:
        return PROPORCIONES_AMBIENTES[nombre]

    if "dormitorio" in nombre:
        return PROPORCIONES_AMBIENTES["dormitorio"]

    if "bano" in nombre:
        return PROPORCIONES_AMBIENTES["bano"]

    return PROPORCION_DEFAULT


# ------------------------------------------------------------
# OBTENER ÁREAS DEL AMBIENTE
# ------------------------------------------------------------

def obtener_areas_ambiente(nodo: dict):
    """
    Determina el área mínima y el área objetivo.

    Prioridad:
    1. Utiliza las áreas proporcionadas o calculadas.
    2. Si no existen, utiliza dimensiones de referencia.

    Retorna áreas en dm².
    """

    area_minima = nodo.get("area_minima_m2")
    area_objetivo = nodo.get("area_objetivo_m2")

    if area_minima is not None and area_minima <= 0:
        raise ValueError(
            f"El área mínima de {nodo['nombre']} "
            "debe ser mayor que cero."
        )

    if area_objetivo is not None and area_objetivo <= 0:
        raise ValueError(
            f"El área objetivo de {nodo['nombre']} "
            "debe ser mayor que cero."
        )

    # Utilizar dimensiones de referencia.
    if area_minima is None and area_objetivo is None:

        ancho, largo = obtener_dimensiones_referencia(
            nodo["nombre"]
        )

        area_referencia = ancho * largo

        return area_referencia, area_referencia

    # Convertir m² a dm².
    if area_minima is None:

        area_minima_dm2 = MIN_LADO_DM ** 2

    else:

        area_minima_dm2 = math.ceil(
            area_minima * 100
        )

    if area_objetivo is None:

        area_objetivo_dm2 = area_minima_dm2

    else:

        area_objetivo_dm2 = math.ceil(
            area_objetivo * 100
        )

    if area_objetivo_dm2 < area_minima_dm2:
        raise ValueError(
            f"El área objetivo de {nodo['nombre']} "
            "es inferior a su área mínima."
        )

    return area_minima_dm2, area_objetivo_dm2
