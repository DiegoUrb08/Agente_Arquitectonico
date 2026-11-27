import math

from src.models.requirements import Ambiente, RequerimientosArquitectonicos
from src.utils.texto import normalizar_nombre


# Las claves están normalizadas (sin tildes): ver normalizar_nombre.

# Pesos relativos para distribuir la superficie.
PESOS_AMBIENTES = {
    "sala": 18,
    "comedor": 12,
    "cocina": 12,
    "dormitorio": 15,
    "dormitorio principal": 17,
    "bano": 6,
    "lavanderia": 5,
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
    "bano": 6,
    "lavanderia": 5,
    "estudio": 10,
    "terraza": 5,
}

PORCENTAJE_CIRCULACION = 0.12


def obtener_peso(nombre: str) -> float:

    nombre = normalizar_nombre(nombre)

    if nombre in PESOS_AMBIENTES:
        return PESOS_AMBIENTES[nombre]

    if "dormitorio" in nombre:
        return PESOS_AMBIENTES["dormitorio"]

    if "bano" in nombre:
        return PESOS_AMBIENTES["bano"]

    return 8


def obtener_area_referencia(nombre: str) -> float:

    nombre = normalizar_nombre(nombre)

    if nombre in AREAS_REFERENCIA:
        return AREAS_REFERENCIA[nombre]

    if "dormitorio" in nombre:
        return AREAS_REFERENCIA["dormitorio"]

    if "bano" in nombre:
        return AREAS_REFERENCIA["bano"]

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


# Casa básica: los ambientes que siempre lleva y su superficie en 25 m².
AREAS_CASA_BASICA = {
    "sala": 6.5,
    "comedor": 4.5,
    "cocina": 4.5,
    "dormitorio": 6.5,
    "baño": 3.0,
}
AREA_CASA_BASICA = 25.0
AREA_MINIMA_CASA_BASICA = 22.0   # por debajo, algún mueble no entra
AREA_MAXIMA_CASA_BASICA = 30.0


def _tipo_basico(nombre: str) -> str:
    """'Dormitorio principal' -> 'dormitorio'; 'Baño' -> 'bano'."""
    nombre = normalizar_nombre(nombre)
    return next(
        (t for t in ("dormitorio", "bano") if nombre.startswith(t)), nombre
    )


def completar_casa_basica(requerimientos):
    """
    En una casa de un piso sin lista de ambientes, o de hasta 30 m², añade los
    que falten de sala, comedor, cocina, dormitorio y baño. En las de hasta
    30 m² marca el programa compacto (sin pasillo ni reserva de circulación).
    """

    if (requerimientos.numero_pisos or 1) != 1:
        return requerimientos

    area = requerimientos.area_total_vivienda_m2
    sin_lista = not requerimientos.ambientes
    if sin_lista and area is None:
        area = requerimientos.area_total_vivienda_m2 = AREA_CASA_BASICA

    compacta = area is not None and area <= AREA_MAXIMA_CASA_BASICA
    if not (sin_lista or compacta):
        return requerimientos

    if compacta and area < AREA_MINIMA_CASA_BASICA:
        raise ValueError(
            f"La casa básica necesita al menos {AREA_MINIMA_CASA_BASICA:g} m² "
            f"para sala, comedor, cocina, dormitorio y baño; pediste {area:g} m²."
        )

    pedidos = {_tipo_basico(a.nombre) for a in requerimientos.ambientes}
    faltan = [n for n in AREAS_CASA_BASICA if _tipo_basico(n) not in pedidos]
    requerimientos.ambientes = [
        *requerimientos.ambientes, *(Ambiente(nombre=n) for n in faltan)
    ]
    requerimientos.ambientes_agregados = faltan

    if not compacta:
        return requerimientos

    requerimientos.programa_basico = True
    ambientes = requerimientos.ambientes
    solo_basicos = len(ambientes) == len(AREAS_CASA_BASICA) and all(
        a.cantidad == 1 and a.area_objetivo_m2 is None
        and a.area_minima_m2 is None for a in ambientes
    )
    if solo_basicos:
        areas = {_tipo_basico(n): v for n, v in AREAS_CASA_BASICA.items()}
        for ambiente in ambientes:
            valor = areas[_tipo_basico(ambiente.nombre)] * area / AREA_CASA_BASICA
            ambiente.area_objetivo_m2 = math.floor(valor * 100 + 1e-6) / 100

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

    # En una casa mínima la sala es la circulación: no se reserva superficie.
    circulacion = 0 if requerimientos.programa_basico else PORCENTAJE_CIRCULACION
    area_util = area_total * (1 - circulacion)

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


FACTOR_TERRENO_VIVIENDA = 2.5   # el lote es 2.5 veces la casa: sobra sitio para jardín y calle
ASPECTO_TERRENO = 1.25          # largo / ancho


def estimar_terreno_para_vivienda(requerimientos):
    """
    Si el usuario no dio el terreno, lo calcula desde el área de la vivienda
    (con holgura para jardín, árboles y calle). No hace nada si ya hay terreno
    o si todavía no se conoce el área de la vivienda.
    """

    ya_hay_terreno = (
        requerimientos.ancho_terreno_m is not None
        or requerimientos.largo_terreno_m is not None
        or requerimientos.area_terreno_m2 is not None
    )
    area_vivienda = requerimientos.area_total_vivienda_m2

    if ya_hay_terreno or not area_vivienda or area_vivienda <= 0:
        return requerimientos

    area = area_vivienda * FACTOR_TERRENO_VIVIENDA
    ancho = math.sqrt(area / ASPECTO_TERRENO)
    largo = ancho * ASPECTO_TERRENO

    requerimientos.ancho_terreno_m = round(ancho, 1)
    requerimientos.largo_terreno_m = round(largo, 1)
    requerimientos.area_terreno_m2 = round(
        requerimientos.ancho_terreno_m * requerimientos.largo_terreno_m, 2
    )
    requerimientos.terreno_estimado = True
    return requerimientos


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
