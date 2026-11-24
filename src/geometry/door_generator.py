
from src.geometry.adjacency_validator import detectar_adyacencias


# ============================================================
# CONFIGURACIÓN PREDETERMINADA
# ============================================================

ANCHO_PUERTA_PREDETERMINADO = 0.90
ESPESOR_MURO_PREDETERMINADO = 0.15

LONGITUD_MINIMA_PARED = 1.10
SEPARACION_MINIMA_EXTREMOS = 0.10

TOLERANCIA = 0.001


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
# 4. GENERAR PUERTAS AUTOMÁTICAMENTE
# ============================================================

def generar_puertas_automaticas(
    distribucion: list[dict],
    ancho_puerta_m: float = ANCHO_PUERTA_PREDETERMINADO,
    espesor_muro_m: float = ESPESOR_MURO_PREDETERMINADO,
    longitud_minima_m: float = LONGITUD_MINIMA_PARED,
    separacion_extremos_m: float = SEPARACION_MINIMA_EXTREMOS,
    conexiones_excluidas: list[tuple] | None = None
) -> dict:
    """
    Propone puertas sobre las paredes compartidas
    entre ambientes.

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

    puertas = []
    rechazadas = []
    conexiones_procesadas = set()

    # --------------------------------------------------------
    # GENERAR UNA PUERTA POR ADYACENCIA
    # --------------------------------------------------------

    for adyacencia in adyacencias:

        ambiente_a = adyacencia["ambiente_a"]
        ambiente_b = adyacencia["ambiente_b"]

        conexion = normalizar_conexion(
            ambiente_a,
            ambiente_b
        )

        # Evitar conexiones excluidas
        if conexion in exclusiones:
            continue

        # Evitar duplicados
        if conexion in conexiones_procesadas:
            continue

        conexiones_procesadas.add(conexion)

        longitud = float(adyacencia["longitud_m"])

        # Comprobar espacio disponible
        if not comprobar_espacio_puerta(
            longitud_pared=longitud,
            ancho_puerta=ancho_puerta_m,
            separacion_extremos=separacion_extremos_m
        ):

            rechazadas.append({
                "ambiente_a": ambiente_a,
                "ambiente_b": ambiente_b,
                "longitud_pared_m": longitud,
                "motivo": (
                    "La pared compartida no tiene "
                    "longitud suficiente para la puerta."
                )
            })

            continue

        # Calcular ubicación
        centro = calcular_centro_segmento(
            adyacencia["segmento"]
        )

        puerta = {
            "tipo": "puerta",
            "centro": centro,
            "ancho": float(ancho_puerta_m),
            "espesor_muro": float(espesor_muro_m),
            "orientacion": adyacencia["orientacion"],
            "ambiente_a": ambiente_a,
            "ambiente_b": ambiente_b,
            "longitud_pared_m": longitud
        }

        puertas.append(puerta)

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
