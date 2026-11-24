
from src.models.requirements import RequerimientosArquitectonicos


# Pesos relativos para distribuir la superficie.
PESOS_AMBIENTES = {
    "sala": 18,
    "comedor": 12,
    "cocina": 12,
    "dormitorio": 15,
    "dormitorio principal": 17,
    "baño": 6,
    "lavandería": 5,
    "estudio": 10,
    "terraza": 5,
}

# Superficies de referencia en m².
# Son valores iniciales del sistema, no normas obligatorias.
AREAS_REFERENCIA = {
    "sala": 18,
    "comedor": 12,
    "cocina": 12,
    "dormitorio": 15,
    "dormitorio principal": 17,
    "baño": 6,
    "lavandería": 5,
    "estudio": 10,
    "terraza": 5,
}

PORCENTAJE_CIRCULACION = 0.12


def normalizar_nombre(nombre: str) -> str:
    return nombre.strip().lower()


def obtener_peso(nombre: str) -> float:

    nombre = normalizar_nombre(nombre)

    if nombre in PESOS_AMBIENTES:
        return PESOS_AMBIENTES[nombre]

    if "dormitorio" in nombre:
        return PESOS_AMBIENTES["dormitorio"]

    if "baño" in nombre:
        return PESOS_AMBIENTES["baño"]

    return 8


def obtener_area_referencia(nombre: str) -> float:

    nombre = normalizar_nombre(nombre)

    if nombre in AREAS_REFERENCIA:
        return AREAS_REFERENCIA[nombre]

    if "dormitorio" in nombre:
        return AREAS_REFERENCIA["dormitorio"]

    if "baño" in nombre:
        return AREAS_REFERENCIA["baño"]

    return 8


def estimar_area_total_vivienda(
    requerimientos: RequerimientosArquitectonicos
):
    """
    Estima el área total de vivienda cuando el usuario
    no proporciona una superficie total.

    La estimación considera las áreas de referencia,
    cantidades y superficies mínimas especificadas.
    """

    if not requerimientos.ambientes:
        raise ValueError("No se han especificado ambientes.")

    area_ambientes = 0

    for ambiente in requerimientos.ambientes:

        if ambiente.cantidad < 1:
            raise ValueError(
                f"Cantidad inválida para {ambiente.nombre}."
            )

        area_referencia = obtener_area_referencia(
            ambiente.nombre
        )

        area_minima = ambiente.area_minima_m2 or 0
        area_objetivo = ambiente.area_objetivo_m2 or 0

        area_individual = max(
            area_referencia,
            area_minima,
            area_objetivo
        )

        area_ambientes += (
            area_individual * ambiente.cantidad
        )

    area_total = area_ambientes / (
        1 - PORCENTAJE_CIRCULACION
    )

    requerimientos.area_total_vivienda_m2 = round(
        area_total, 2
    )

    return requerimientos


def calcular_areas_predeterminadas(
    requerimientos: RequerimientosArquitectonicos
):
    """
    Distribuye proporcionalmente las superficies
    disponibles entre los ambientes sin área objetivo.

    Las áreas mínimas y objetivos proporcionados
    se respetan como superficies reservadas.
    """

    area_total = requerimientos.area_total_vivienda_m2

    if area_total is None or area_total <= 0:
        raise ValueError("El área total debe ser mayor que cero.")

    if not requerimientos.ambientes:
        raise ValueError("No se han especificado ambientes.")

    area_util = area_total * (1 - PORCENTAJE_CIRCULACION)

    area_reservada = 0
    ambientes_pendientes = []
    pesos_totales = 0

    for ambiente in requerimientos.ambientes:

        if ambiente.cantidad < 1:
            raise ValueError(
                f"Cantidad inválida para {ambiente.nombre}."
            )

        area_fija = ambiente.area_objetivo_m2

        if area_fija is None:
            area_fija = ambiente.area_minima_m2

        if area_fija is not None:

            if area_fija <= 0:
                raise ValueError(
                    f"Área inválida para {ambiente.nombre}."
                )

            if (
                ambiente.area_minima_m2 is not None
                and area_fija < ambiente.area_minima_m2
            ):
                raise ValueError(
                    f"El área objetivo de {ambiente.nombre} "
                    "es inferior a su área mínima."
                )

            ambiente.area_objetivo_m2 = area_fija

            area_reservada += (
                area_fija * ambiente.cantidad
            )

        else:

            peso = obtener_peso(ambiente.nombre)
            peso_grupo = peso * ambiente.cantidad

            ambientes_pendientes.append(
                (ambiente, peso_grupo)
            )

            pesos_totales += peso_grupo

    area_restante = area_util - area_reservada

    if area_restante < -0.001:
        raise ValueError(
            "Las áreas especificadas superan "
            "la superficie disponible."
        )

    if ambientes_pendientes and area_restante <= 0:
        raise ValueError(
            "No queda superficie disponible para "
            "los ambientes pendientes."
        )

    for ambiente, peso in ambientes_pendientes:

        proporcion = peso / pesos_totales

        area_grupo = area_restante * proporcion

        area_individual = (
            area_grupo / ambiente.cantidad
        )

        ambiente.area_objetivo_m2 = round(
            area_individual, 2
        )

        if (
            ambiente.area_minima_m2 is not None
            and ambiente.area_objetivo_m2
            < ambiente.area_minima_m2
        ):
            raise ValueError(
                f"La distribución no alcanza el área mínima "
                f"de {ambiente.nombre}."
            )

    return requerimientos

import math


def completar_dimensiones_terreno(requerimientos):
    """
    Completa las dimensiones del terreno cuando el usuario
    proporciona solamente su superficie total.

    Las dimensiones calculadas son estimaciones.
    """

    ancho = requerimientos.ancho_terreno_m
    largo = requerimientos.largo_terreno_m
    area = requerimientos.area_terreno_m2

    # Caso 1: existen ambas dimensiones.

    if ancho is not None and largo is not None:

        if ancho <= 0 or largo <= 0:
            raise ValueError(
                "Las dimensiones del terreno deben ser positivas."
            )

        area_calculada = ancho * largo

        if area is not None and abs(area - area_calculada) > 0.1:
            raise ValueError(
                "El area del terreno no coincide con sus dimensiones."
            )

        requerimientos.area_terreno_m2 = round(
            area_calculada, 2
        )

        return requerimientos

    # Caso 2: solamente existe el ancho.

    if ancho is not None:

        if ancho <= 0 or area is None or area <= 0:
            raise ValueError(
                "Se necesita un area valida para estimar el largo."
            )

        requerimientos.largo_terreno_m = round(
            area / ancho, 2
        )

        return requerimientos

    # Caso 3: solamente existe el largo.

    if largo is not None:

        if largo <= 0 or area is None or area <= 0:
            raise ValueError(
                "Se necesita un area valida para estimar el ancho."
            )

        requerimientos.ancho_terreno_m = round(
            area / largo, 2
        )

        return requerimientos

    # Caso 4: solamente existe el area.

    if area is not None:

        if area <= 0:
            raise ValueError(
                "El area del terreno debe ser positiva."
            )

        # Se estima una forma rectangular cercana a un cuadrado.
        ancho_estimado = math.sqrt(area)
        largo_estimado = area / ancho_estimado

        requerimientos.ancho_terreno_m = round(
            ancho_estimado, 2
        )

        requerimientos.largo_terreno_m = round(
            largo_estimado, 2
        )

        return requerimientos

    # Caso 5: no existe ninguna dimension ni area.

    raise ValueError(
        "No se especifico el area ni las dimensiones del terreno. "
        "Es necesario solicitar esta informacion al usuario."
    )
