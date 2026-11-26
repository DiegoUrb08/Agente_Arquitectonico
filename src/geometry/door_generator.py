
from shapely.geometry import LineString, box
from shapely.ops import unary_union

from src.geometry.adjacency_validator import detectar_adyacencias
from src.planning.reglas_acceso import (
    CIRCULACION,
    EXTERIOR,
    SOCIALES,
    asignar_en_suite,
    elegir_entrada,
    puede_dar_acceso,
    tipo_base,
)
from src.planning.reglas_ambientes import AMBIENTES_SIN_VENTANA


# ============================================================
# CONFIGURACIÓN PREDETERMINADA
# ============================================================

ANCHO_PUERTA_PREDETERMINADO = 0.90
ESPESOR_MURO_PREDETERMINADO = 0.15

LONGITUD_MINIMA_PARED = 1.10
SEPARACION_MINIMA_EXTREMOS = 0.10

TOLERANCIA = 0.001

ESPESOR_MURO_EXTERIOR_PREDETERMINADO = 0.20
# Con menos que esto a cada lado de la entrada no cabe una ventana de 0,9 m.
SITIO_VENTANA_JUNTO_A_PUERTA_M = 1.50

# Desde dónde es preferible abrir una puerta (menor = mejor).
PREFERENCIA_ORIGEN = {
    "pasillo": 0, "escalera": 1, "sala": 2, "comedor": 3, "cocina": 4,
}


# ============================================================
# 1. NORMALIZAR CONEXIONES
# ============================================================

def normalizar_conexion(ambiente_a: str, ambiente_b: str) -> frozenset:
    """
    Representa una conexión sin importar el orden de los ambientes.
    """

    return frozenset((ambiente_a, ambiente_b))


# ============================================================
# 2. CALCULAR CENTRO DE LA PARED COMPARTIDA
# ============================================================

def calcular_centro_segmento(segmento: dict) -> tuple:
    """
    Calcula el punto medio de un segmento compartido.
    """

    x1, y1 = segmento["inicio"]
    x2, y2 = segmento["fin"]

    centro_x = (x1 + x2) / 2
    centro_y = (y1 + y2) / 2

    return (
        round(centro_x, 4),
        round(centro_y, 4)
    )


# ============================================================
# 3. COMPROBAR SI CABE UNA PUERTA
# ============================================================

def comprobar_espacio_puerta(
    longitud_pared: float,
    ancho_puerta: float,
    separacion_extremos: float
) -> bool:
    """
    Comprueba si una puerta cabe en el segmento compartido,
    respetando una separación mínima en ambos extremos.
    """

    espacio_necesario = (
        ancho_puerta + 2 * separacion_extremos
    )

    return (
        longitud_pared + TOLERANCIA >= espacio_necesario
    )


# ============================================================
# 4. ELEGIR QUÉ PAREDES LLEVAN PUERTA
# ============================================================

def _elegir_conexiones(ids: list, paredes: dict, entrada: str) -> list:
    """
    Recorre la planta desde la entrada y abre una sola puerta hacia cada
    ambiente, según las reglas de acceso.

    `paredes` es {frozenset(a, b): adyacencia} con las paredes donde cabe
    una puerta. Devuelve la lista de claves elegidas.
    """

    en_suite = {
        bano: dormitorio
        for bano, dormitorio in asignar_en_suite(ids).items()
        if frozenset((bano, dormitorio)) in paredes
    }

    def segun_reglas(a, b):
        return puede_dar_acceso(a, b, en_suite, entrada)

    # Solo se usan, por orden, si quedan ambientes sin alcanzar.
    respaldos = (
        lambda a, b: tipo_base(a) == "dormitorio" and tipo_base(b) == "bano",
        lambda a, b: True,
    )

    alcanzados = {entrada}
    elegidas = _continuar(paredes, alcanzados, segun_reglas)

    for respaldo in respaldos:
        while puerta := _abrir_siguiente(paredes, alcanzados, respaldo):
            elegidas.append(puerta)
            elegidas += _continuar(paredes, alcanzados, segun_reglas)

    # Los ambientes sociales contiguos se comunican además entre sí.
    for clave in paredes:
        if (
            clave not in elegidas
            and clave <= alcanzados
            and all(tipo_base(i) in SOCIALES for i in clave)
        ):
            elegidas.append(clave)

    return elegidas


def _abrir_siguiente(paredes: dict, alcanzados: set, permitido):
    """
    Elige la mejor puerta que cumpla `permitido` hacia un ambiente aún no
    alcanzado, lo marca como alcanzado y devuelve su clave (o None).
    """

    candidatas = []

    for clave, pared in paredes.items():
        if len(clave & alcanzados) != 1:
            continue
        origen = next(iter(clave & alcanzados))
        destino = next(iter(clave - alcanzados))
        if permitido(origen, destino):
            # A un ambiente social se entra mejor desde otro (cocina desde
            # el comedor antes que desde el pasillo).
            lejos_de_lo_social = (
                tipo_base(destino) in SOCIALES
                and tipo_base(origen) not in SOCIALES
            )
            candidatas.append((
                # Primero se llega a la circulación, para repartir desde ella.
                tipo_base(destino) not in CIRCULACION,
                lejos_de_lo_social,
                PREFERENCIA_ORIGEN.get(tipo_base(origen), 9),
                -float(pared["longitud_m"]),
                destino,
                origen,
            ))

    if not candidatas:
        return None

    *_, destino, origen = min(candidatas)
    alcanzados.add(destino)
    return frozenset((origen, destino))


def _continuar(paredes: dict, alcanzados: set, permitido) -> list:
    """Amplía el recorrido mientras haya puertas que cumplan `permitido`."""

    nuevas = []

    while puerta := _abrir_siguiente(paredes, alcanzados, permitido):
        nuevas.append(puerta)

    return nuevas


# ============================================================
# 5. PUERTA EXTERIOR
# ============================================================

def _caja(ambiente: dict):
    x, y = float(ambiente["x"]), float(ambiente["y"])
    return box(x, y, x + float(ambiente["ancho"]), y + float(ambiente["largo"]))


def _tramos_exteriores(distribucion: list, identificador: str) -> list:
    """
    Tramos de pared de un ambiente que dan al exterior de la vivienda (no a
    huecos interiores), como (orientacion, valor, inicio, fin).
    """

    conjunto = unary_union([_caja(a) for a in distribucion])
    partes = getattr(conjunto, "geoms", [conjunto])
    contorno = unary_union([LineString(p.exterior.coords) for p in partes])

    ambiente = next(a for a in distribucion if a["id"] == identificador)
    x1, y1, x2, y2 = _caja(ambiente).bounds

    lados = (
        ("horizontal", y1, LineString([(x1, y1), (x2, y1)])),  # frente
        ("vertical", x1, LineString([(x1, y1), (x1, y2)])),
        ("vertical", x2, LineString([(x2, y1), (x2, y2)])),
        ("horizontal", y2, LineString([(x1, y2), (x2, y2)])),
    )

    tramos = []

    for orientacion, valor, lado in lados:
        comun = lado.intersection(contorno)
        for parte in getattr(comun, "geoms", [comun]):
            if parte.length <= TOLERANCIA:
                continue
            eje = 0 if orientacion == "horizontal" else 1
            extremos = sorted(punto[eje] for punto in parte.coords)
            tramos.append((orientacion, valor, extremos[0], extremos[-1]))

    return tramos


def _puerta_exterior(
    distribucion: list,
    entrada: str,
    ancho_puerta_m: float,
    espesor_muro_m: float,
    separacion_extremos_m: float,
) -> dict | None:
    """Puerta a la calle en la entrada, preferentemente en el frente."""

    margen = ancho_puerta_m / 2 + separacion_extremos_m

    # El ambiente de entrada primero; si está encerrado, cualquier otro.
    orden = [entrada] + [a["id"] for a in distribucion if a["id"] != entrada]

    for identificador in orden:

        for orientacion, valor, inicio, fin in _tramos_exteriores(
            distribucion, identificador
        ):

            if not comprobar_espacio_puerta(
                fin - inicio, ancho_puerta_m, separacion_extremos_m
            ):
                continue

            centro = (inicio + fin) / 2

            # En una fachada angosta, la puerta centrada deja sin sitio a la
            # ventana: se lleva a un extremo.
            al_lado = (fin - inicio - ancho_puerta_m) / 2
            if (
                al_lado < SITIO_VENTANA_JUNTO_A_PUERTA_M
                and tipo_base(identificador) not in AMBIENTES_SIN_VENTANA
            ):
                centro = inicio + margen

            # Se aparta un poco de las esquinas cuando hay sitio.
            centro = min(max(centro, inicio + margen), fin - margen)

            punto = (
                (centro, valor) if orientacion == "horizontal"
                else (valor, centro)
            )

            return {
                "tipo": "puerta",
                "centro": (round(punto[0], 4), round(punto[1], 4)),
                "ancho": float(ancho_puerta_m),
                "espesor_muro": float(espesor_muro_m),
                "orientacion": orientacion,
                "ambiente_a": identificador,
                "ambiente_b": EXTERIOR,
                "longitud_pared_m": round(fin - inicio, 3),
            }

    return None


# ============================================================
# 6. GENERAR PUERTAS AUTOMÁTICAMENTE
# ============================================================

def generar_puertas_automaticas(
    distribucion: list[dict],
    ancho_puerta_m: float = ANCHO_PUERTA_PREDETERMINADO,
    espesor_muro_m: float = ESPESOR_MURO_PREDETERMINADO,
    longitud_minima_m: float = LONGITUD_MINIMA_PARED,
    separacion_extremos_m: float = SEPARACION_MINIMA_EXTREMOS,
    conexiones_excluidas: list[tuple] | None = None,
    puerta_exterior: bool = True,
    espesor_exterior_m: float = ESPESOR_MURO_EXTERIOR_PREDETERMINADO,
) -> dict:
    """
    Propone las puertas de una planta: una por acceso lógico a cada
    ambiente (ver `reglas_acceso`), las de los ambientes sociales contiguos
    y, con `puerta_exterior`, la entrada desde la calle.

    Cada puerta propuesta contiene:

        tipo
        centro
        ancho
        espesor_muro
        orientacion
        ambiente_a
        ambiente_b

    Las conexiones excluidas no reciben puertas.

    IMPORTANTE:
    Este módulo genera propuestas geométricas.
    La comprobación definitiva de que las aberturas
    coincidan con los muros se realiza posteriormente
    mediante opening_generator.py.
    """

    # --------------------------------------------------------
    # VALIDAR PARÁMETROS
    # --------------------------------------------------------

    if ancho_puerta_m <= 0:
        raise ValueError(
            "El ancho de la puerta debe ser positivo."
        )

    if espesor_muro_m <= 0:
        raise ValueError(
            "El espesor del muro debe ser positivo."
        )

    if longitud_minima_m <= 0:
        raise ValueError(
            "La longitud mínima debe ser positiva."
        )

    if separacion_extremos_m < 0:
        raise ValueError(
            "La separación de extremos no puede ser negativa."
        )

    if not distribucion:
        raise ValueError(
            "No se proporcionó una distribución espacial."
        )

    # --------------------------------------------------------
    # NORMALIZAR CONEXIONES EXCLUIDAS
    # --------------------------------------------------------

    conexiones_excluidas = conexiones_excluidas or []

    exclusiones = {
        normalizar_conexion(a, b)
        for a, b in conexiones_excluidas
    }

    # --------------------------------------------------------
    # DETECTAR ADYACENCIAS
    # --------------------------------------------------------

    adyacencias = detectar_adyacencias(
        distribucion,
        longitud_minima_m=longitud_minima_m
    )

    paredes = {}
    rechazadas = []

    for adyacencia in adyacencias:

        conexion = normalizar_conexion(
            adyacencia["ambiente_a"],
            adyacencia["ambiente_b"]
        )

        # Evitar conexiones excluidas y duplicadas
        if conexion in exclusiones or conexion in paredes:
            continue

        longitud = float(adyacencia["longitud_m"])

        # Comprobar espacio disponible
        if not comprobar_espacio_puerta(
            longitud_pared=longitud,
            ancho_puerta=ancho_puerta_m,
            separacion_extremos=separacion_extremos_m
        ):

            rechazadas.append({
                "ambiente_a": adyacencia["ambiente_a"],
                "ambiente_b": adyacencia["ambiente_b"],
                "longitud_pared_m": longitud,
                "motivo": (
                    "La pared compartida no tiene "
                    "longitud suficiente para la puerta."
                )
            })

            continue

        paredes[conexion] = adyacencia

    # --------------------------------------------------------
    # PUERTAS INTERIORES Y EXTERIOR
    # --------------------------------------------------------

    ids = [ambiente["id"] for ambiente in distribucion]
    entrada = elegir_entrada(ids, planta_baja=puerta_exterior)

    puertas = []

    for conexion in _elegir_conexiones(ids, paredes, entrada):

        adyacencia = paredes[conexion]

        puertas.append({
            "tipo": "puerta",
            "centro": calcular_centro_segmento(adyacencia["segmento"]),
            "ancho": float(ancho_puerta_m),
            "espesor_muro": float(espesor_muro_m),
            "orientacion": adyacencia["orientacion"],
            "ambiente_a": adyacencia["ambiente_a"],
            "ambiente_b": adyacencia["ambiente_b"],
            "longitud_pared_m": float(adyacencia["longitud_m"])
        })

    if puerta_exterior:

        exterior = _puerta_exterior(
            distribucion, entrada, ancho_puerta_m,
            espesor_exterior_m, separacion_extremos_m,
        )

        if exterior:
            puertas.append(exterior)

    # --------------------------------------------------------
    # RESULTADO
    # --------------------------------------------------------

    return {
        "puertas": puertas,
        "cantidad_puertas": len(puertas),
        "puertas_rechazadas": rechazadas,
        "cantidad_rechazadas": len(rechazadas),
        "cantidad_adyacencias": len(adyacencias)
    }


# ============================================================
# 5. IMPRIMIR RESULTADOS
# ============================================================

def imprimir_puertas(resultado: dict):
    """
    Imprime un informe de las puertas propuestas.
    """

    print("\nGENERACIÓN AUTOMÁTICA DE PUERTAS")
    print("=" * 60)

    print(
        f"\nAdyacencias detectadas: "
        f"{resultado['cantidad_adyacencias']}"
    )

    print(
        f"Puertas propuestas: "
        f"{resultado['cantidad_puertas']}"
    )

    print(
        f"Conexiones rechazadas: "
        f"{resultado['cantidad_rechazadas']}"
    )

    print("\nPUERTAS GENERADAS")
    print("-" * 60)

    for i, puerta in enumerate(
        resultado["puertas"],
        start=1
    ):

        print(f"\nPuerta {i}")

        print(
            f"  Conecta: {puerta['ambiente_a']} "
            f"<-> {puerta['ambiente_b']}"
        )

        print(
            f"  Centro: {puerta['centro']}"
        )

        print(
            f"  Ancho: {puerta['ancho']} m"
        )

        print(
            f"  Orientación: {puerta['orientacion']}"
        )

    print("\nCONEXIONES RECHAZADAS")
    print("-" * 60)

    if resultado["puertas_rechazadas"]:

        for rechazo in resultado["puertas_rechazadas"]:

            print(
                f"\n{rechazo['ambiente_a']} "
                f"<-> {rechazo['ambiente_b']}"
            )

            print(
                f"  Longitud: {rechazo['longitud_pared_m']} m"
            )

            print(
                f"  Motivo: {rechazo['motivo']}"
            )

    else:

        print("No existen conexiones rechazadas.")
