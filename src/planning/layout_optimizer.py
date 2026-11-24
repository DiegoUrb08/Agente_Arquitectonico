
import math
import unicodedata

from ortools.sat.python import cp_model

from src.planning.space_graph import construir_grafo


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
}


# ============================================================
# 2. FUNCIONES AUXILIARES
# ============================================================

def normalizar_nombre(nombre: str) -> str:
    """
    Normaliza nombres de ambientes.

    - Convierte a minúsculas.
    - Elimina espacios innecesarios.
    - Elimina tildes.
    """

    nombre = nombre.strip().lower()

    nombre = unicodedata.normalize(
        "NFD",
        nombre
    )

    return "".join(
        caracter
        for caracter in nombre
        if unicodedata.category(caracter) != "Mn"
    )


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


# ============================================================
# 3. ADYACENCIA FÍSICA
# ============================================================

def agregar_adyacencia_fisica(
    modelo,
    ambiente_a,
    ambiente_b,
    identificador,
    ancho_terreno_dm,
    largo_terreno_dm
):
    """
    Obliga a dos ambientes rectangulares a compartir
    una frontera de longitud mínima.

    Se consideran cuatro posibilidades:

    1. A a la izquierda de B.
    2. B a la izquierda de A.
    3. A debajo de B.
    4. B debajo de A.

    Retorna una variable booleana que indica
    si ambos ambientes son adyacentes.
    """

    minimo = LONGITUD_MINIMA_ADYACENCIA_DM

    # --------------------------------------------------------
    # VARIABLES DE POSICIÓN Y DIMENSIONES
    # --------------------------------------------------------

    x_a = ambiente_a["x"]
    y_a = ambiente_a["y"]

    fin_x_a = ambiente_a["fin_x"]
    fin_y_a = ambiente_a["fin_y"]

    x_b = ambiente_b["x"]
    y_b = ambiente_b["y"]

    fin_x_b = ambiente_b["fin_x"]
    fin_y_b = ambiente_b["fin_y"]

    # --------------------------------------------------------
    # SOLAPAMIENTO VERTICAL
    # --------------------------------------------------------

    inicio_vertical = modelo.NewIntVar(
        0,
        largo_terreno_dm,
        f"inicio_vertical_{identificador}"
    )

    fin_vertical = modelo.NewIntVar(
        0,
        largo_terreno_dm,
        f"fin_vertical_{identificador}"
    )

    modelo.AddMaxEquality(
        inicio_vertical,
        [y_a, y_b]
    )

    modelo.AddMinEquality(
        fin_vertical,
        [fin_y_a, fin_y_b]
    )

    solapamiento_vertical = modelo.NewIntVar(
        -largo_terreno_dm,
        largo_terreno_dm,
        f"solapamiento_vertical_{identificador}"
    )

    modelo.Add(
        solapamiento_vertical ==
        fin_vertical - inicio_vertical
    )

    # --------------------------------------------------------
    # SOLAPAMIENTO HORIZONTAL
    # --------------------------------------------------------

    inicio_horizontal = modelo.NewIntVar(
        0,
        ancho_terreno_dm,
        f"inicio_horizontal_{identificador}"
    )

    fin_horizontal = modelo.NewIntVar(
        0,
        ancho_terreno_dm,
        f"fin_horizontal_{identificador}"
    )

    modelo.AddMaxEquality(
        inicio_horizontal,
        [x_a, x_b]
    )

    modelo.AddMinEquality(
        fin_horizontal,
        [fin_x_a, fin_x_b]
    )

    solapamiento_horizontal = modelo.NewIntVar(
        -ancho_terreno_dm,
        ancho_terreno_dm,
        f"solapamiento_horizontal_{identificador}"
    )

    modelo.Add(
        solapamiento_horizontal ==
        fin_horizontal - inicio_horizontal
    )

    # --------------------------------------------------------
    # VARIABLES BOOLEANAS DE ORIENTACIÓN
    # --------------------------------------------------------

    a_izquierda = modelo.NewBoolVar(
        f"a_izquierda_{identificador}"
    )

    b_izquierda = modelo.NewBoolVar(
        f"b_izquierda_{identificador}"
    )

    a_abajo = modelo.NewBoolVar(
        f"a_abajo_{identificador}"
    )

    b_abajo = modelo.NewBoolVar(
        f"b_abajo_{identificador}"
    )

    # --------------------------------------------------------
    # A ESTÁ A LA IZQUIERDA DE B
    # --------------------------------------------------------

    modelo.Add(
        fin_x_a == x_b
    ).OnlyEnforceIf(a_izquierda)

    modelo.Add(
        solapamiento_vertical >= minimo
    ).OnlyEnforceIf(a_izquierda)

    # --------------------------------------------------------
    # B ESTÁ A LA IZQUIERDA DE A
    # --------------------------------------------------------

    modelo.Add(
        fin_x_b == x_a
    ).OnlyEnforceIf(b_izquierda)

    modelo.Add(
        solapamiento_vertical >= minimo
    ).OnlyEnforceIf(b_izquierda)

    # --------------------------------------------------------
    # A ESTÁ DEBAJO DE B
    # --------------------------------------------------------

    modelo.Add(
        fin_y_a == y_b
    ).OnlyEnforceIf(a_abajo)

    modelo.Add(
        solapamiento_horizontal >= minimo
    ).OnlyEnforceIf(a_abajo)

    # --------------------------------------------------------
    # B ESTÁ DEBAJO DE A
    # --------------------------------------------------------

    modelo.Add(
        fin_y_b == y_a
    ).OnlyEnforceIf(b_abajo)

    modelo.Add(
        solapamiento_horizontal >= minimo
    ).OnlyEnforceIf(b_abajo)

    # --------------------------------------------------------
    # AL MENOS UNA ORIENTACIÓN DEBE CUMPLIRSE
    # --------------------------------------------------------

    adyacente = modelo.NewBoolVar(
        f"adyacente_{identificador}"
    )

    orientaciones = [
        a_izquierda,
        b_izquierda,
        a_abajo,
        b_abajo
    ]

    modelo.AddBoolOr(
        orientaciones
    ).OnlyEnforceIf(adyacente)

    modelo.AddBoolAnd(
        [variable.Not() for variable in orientaciones]
    ).OnlyEnforceIf(adyacente.Not())

    return adyacente


# ============================================================
# 4. OPTIMIZACIÓN DE LA DISTRIBUCIÓN
# ============================================================

def optimizar_distribucion(requerimientos):
    """
    Genera una distribución espacial preliminar
    mediante programación por restricciones.

    Objetivos:

    1. Aproximar las superficies a sus áreas objetivo.
    2. Cumplir las relaciones de adyacencia.
    3. Minimizar las distancias entre ambientes relacionados.
    4. Agrupar los ambientes sociales.
    5. Garantizar conectividad global entre ambientes.

    Restricciones:

    - Ambientes dentro del terreno.
    - Sin superposición entre ambientes.
    - Respeto de las áreas mínimas.
    - Control de proporciones geométricas.
    - Adyacencia física cuando se solicita.
    - Conectividad global de la distribución.
    """

    # --------------------------------------------------------
    # 4.1. VALIDACIÓN DEL TERRENO
    # --------------------------------------------------------

    ancho_terreno = requerimientos.ancho_terreno_m
    largo_terreno = requerimientos.largo_terreno_m

    if ancho_terreno is None or largo_terreno is None:
        raise ValueError(
            "Se deben especificar el ancho y largo del terreno."
        )

    if ancho_terreno <= 0 or largo_terreno <= 0:
        raise ValueError(
            "Las dimensiones del terreno deben ser mayores que cero."
        )

    ancho_terreno_dm = math.floor(
        ancho_terreno * 10
    )

    largo_terreno_dm = math.floor(
        largo_terreno * 10
    )

    if (
        ancho_terreno_dm < MIN_LADO_DM
        or largo_terreno_dm < MIN_LADO_DM
    ):
        raise ValueError(
            "El terreno es demasiado pequeño "
            "para las dimensiones mínimas."
        )

    area_terreno_dm2 = (
        ancho_terreno_dm * largo_terreno_dm
    )

    # --------------------------------------------------------
    # 4.2. CONSTRUCCIÓN DEL GRAFO ESPACIAL
    # --------------------------------------------------------

    grafo = construir_grafo(requerimientos)

    nodos = grafo["nodos"]
    relaciones = grafo["relaciones"]

    if not nodos:
        raise ValueError(
            "No existen ambientes para distribuir."
        )

    identificadores = [
        nodo["id"]
        for nodo in nodos
    ]

    if len(identificadores) != len(set(identificadores)):
        raise ValueError(
            "Existen identificadores duplicados."
        )

    identificadores_validos = set(identificadores)

    # --------------------------------------------------------
    # VALIDAR RELACIONES
    # --------------------------------------------------------

    for relacion in relaciones:

        for par in relacion["pares"]:

            origen, destino = par

            if (
                origen not in identificadores_validos
                or destino not in identificadores_validos
            ):
                raise ValueError(
                    f"La relación {par} hace referencia "
                    "a un ambiente inexistente."
                )

    # --------------------------------------------------------
    # 4.3. INICIALIZACIÓN DEL MODELO
    # --------------------------------------------------------

    modelo = cp_model.CpModel()

    variables = {}

    intervalos_x = []
    intervalos_y = []

    variables_area = []
    desviaciones = []

    # --------------------------------------------------------
    # 4.4. CREACIÓN DE VARIABLES Y RESTRICCIONES
    # --------------------------------------------------------

    for nodo in nodos:

        identificador = nodo["id"]

        nombre_ambiente = normalizar_nombre(
            nodo["nombre"]
        )

        area_minima, area_objetivo = obtener_areas_ambiente(
            nodo
        )

        if area_minima > area_terreno_dm2:
            raise ValueError(
                f"El área mínima de {nodo['nombre']} "
                "supera la superficie del terreno."
            )

        # --------------------------------------------
        # POSICIÓN DEL AMBIENTE
        # --------------------------------------------

        x = modelo.NewIntVar(
            0,
            ancho_terreno_dm,
            f"x_{identificador}"
        )

        y = modelo.NewIntVar(
            0,
            largo_terreno_dm,
            f"y_{identificador}"
        )

        # --------------------------------------------
        # DIMENSIONES DEL AMBIENTE
        # --------------------------------------------

        ancho = modelo.NewIntVar(
            MIN_LADO_DM,
            ancho_terreno_dm,
            f"ancho_{identificador}"
        )

        largo = modelo.NewIntVar(
            MIN_LADO_DM,
            largo_terreno_dm,
            f"largo_{identificador}"
        )

        # --------------------------------------------
        # RESTRICCIÓN DE PROPORCIONES
        # --------------------------------------------

        proporcion_maxima = obtener_proporcion_maxima(
            nombre_ambiente
        )

        proporcion_entera = round(
            proporcion_maxima * 10
        )

        modelo.Add(
            ancho * 10 <= largo * proporcion_entera
        )

        modelo.Add(
            largo * 10 <= ancho * proporcion_entera
        )

        # --------------------------------------------
        # RESTRICCIÓN DE ÁREA
        # --------------------------------------------

        area = modelo.NewIntVar(
            area_minima,
            area_terreno_dm2,
            f"area_{identificador}"
        )

        modelo.AddMultiplicationEquality(
            area,
            [ancho, largo]
        )

        variables_area.append(area)

        # --------------------------------------------
        # LÍMITES DEL TERRENO
        # --------------------------------------------

        fin_x = modelo.NewIntVar(
            0,
            ancho_terreno_dm,
            f"fin_x_{identificador}"
        )

        fin_y = modelo.NewIntVar(
            0,
            largo_terreno_dm,
            f"fin_y_{identificador}"
        )

        modelo.Add(
            fin_x == x + ancho
        )

        modelo.Add(
            fin_y == y + largo
        )

        modelo.Add(
            fin_x <= ancho_terreno_dm
        )

        modelo.Add(
            fin_y <= largo_terreno_dm
        )

        # --------------------------------------------
        # INTERVALOS PARA EVITAR SUPERPOSICIONES
        # --------------------------------------------

        intervalo_x = modelo.NewIntervalVar(
            x,
            ancho,
            fin_x,
            f"intervalo_x_{identificador}"
        )

        intervalo_y = modelo.NewIntervalVar(
            y,
            largo,
            fin_y,
            f"intervalo_y_{identificador}"
        )

        intervalos_x.append(intervalo_x)
        intervalos_y.append(intervalo_y)

        # --------------------------------------------
        # GUARDAR VARIABLES
        # --------------------------------------------

        variables[identificador] = {
            "x": x,
            "y": y,
            "ancho": ancho,
            "largo": largo,
            "fin_x": fin_x,
            "fin_y": fin_y,
            "area": area,
            "area_objetivo": area_objetivo,
        }

    # --------------------------------------------------------
    # 4.5. AGRUPACIÓN DE AMBIENTES SOCIALES
    # --------------------------------------------------------

    proximidad_social = []
    ambientes_sociales = []

    for nodo in nodos:

        nombre = normalizar_nombre(
            nodo["nombre"]
        )

        if nombre in AMBIENTES_SOCIALES:

            ambientes_sociales.append(
                variables[nodo["id"]]
            )

    # Calcular distancias entre centros de ambientes sociales.
    for i in range(len(ambientes_sociales)):

        for j in range(i + 1, len(ambientes_sociales)):

            ambiente_a = ambientes_sociales[i]
            ambiente_b = ambientes_sociales[j]

            centro_x_a = (
                ambiente_a["x"] * 2
                + ambiente_a["ancho"]
            )

            centro_y_a = (
                ambiente_a["y"] * 2
                + ambiente_a["largo"]
            )

            centro_x_b = (
                ambiente_b["x"] * 2
                + ambiente_b["ancho"]
            )

            centro_y_b = (
                ambiente_b["y"] * 2
                + ambiente_b["largo"]
            )

            distancia_x = modelo.NewIntVar(
                0,
                ancho_terreno_dm * 2,
                f"distancia_social_x_{i}_{j}"
            )

            distancia_y = modelo.NewIntVar(
                0,
                largo_terreno_dm * 2,
                f"distancia_social_y_{i}_{j}"
            )

            modelo.AddAbsEquality(
                distancia_x,
                centro_x_a - centro_x_b
            )

            modelo.AddAbsEquality(
                distancia_y,
                centro_y_a - centro_y_b
            )

            proximidad_social.append(
                distancia_x + distancia_y
            )

    # --------------------------------------------------------
    # 4.6. RESTRICCIÓN DE NO SUPERPOSICIÓN
    # --------------------------------------------------------

    modelo.AddNoOverlap2D(
        intervalos_x,
        intervalos_y
    )

    # --------------------------------------------------------
    # 4.7. ADYACENCIA FÍSICA ENTRE TODOS LOS AMBIENTES
    # --------------------------------------------------------

    adyacencias_fisicas = {}

    # Crear una variable de adyacencia para cada pareja
    # posible de ambientes.

    for i in range(len(nodos)):

        for j in range(i + 1, len(nodos)):

            identificador_a = nodos[i]["id"]
            identificador_b = nodos[j]["id"]

            clave = tuple(sorted((
                identificador_a,
                identificador_b
            )))

            adyacente = agregar_adyacencia_fisica(
                modelo=modelo,
                ambiente_a=variables[identificador_a],
                ambiente_b=variables[identificador_b],
                identificador=f"global_{i}_{j}",
                ancho_terreno_dm=ancho_terreno_dm,
                largo_terreno_dm=largo_terreno_dm
            )

            adyacencias_fisicas[clave] = adyacente

    # --------------------------------------------------------
    # 4.7.1. CONECTIVIDAD GLOBAL MEDIANTE FLUJO
    # --------------------------------------------------------

    cantidad_ambientes = len(nodos)

    if cantidad_ambientes > 1:

        # El primer ambiente funciona como raíz.
        indice_raiz = 0

        capacidad_flujo = cantidad_ambientes - 1

        # Registrar flujos entrantes y salientes.
        flujos_salientes = {
            nodo["id"]: []
            for nodo in nodos
        }

        flujos_entrantes = {
            nodo["id"]: []
            for nodo in nodos
        }

        # Crear flujos dirigidos para cada pareja.
        for i in range(cantidad_ambientes):

            for j in range(i + 1, cantidad_ambientes):

                id_a = nodos[i]["id"]
                id_b = nodos[j]["id"]

                clave = tuple(sorted((id_a, id_b)))

                adyacente = adyacencias_fisicas[clave]

                # Flujo de A hacia B.
                flujo_ab = modelo.NewIntVar(
                    0,
                    capacidad_flujo,
                    f"flujo_{i}_{j}"
                )

                # Flujo de B hacia A.
                flujo_ba = modelo.NewIntVar(
                    0,
                    capacidad_flujo,
                    f"flujo_{j}_{i}"
                )

                # Solo puede circular flujo si existe
                # adyacencia física entre ambos ambientes.
                modelo.Add(
                    flujo_ab <= capacidad_flujo * adyacente
                )

                modelo.Add(
                    flujo_ba <= capacidad_flujo * adyacente
                )

                # Registrar los flujos.
                flujos_salientes[id_a].append(flujo_ab)
                flujos_entrantes[id_b].append(flujo_ab)

                flujos_salientes[id_b].append(flujo_ba)
                flujos_entrantes[id_a].append(flujo_ba)

        # ----------------------------------------------------
        # CONSERVACIÓN DEL FLUJO
        # ----------------------------------------------------

        for indice, nodo in enumerate(nodos):

            identificador = nodo["id"]

            flujo_neto = (
                sum(flujos_salientes[identificador])
                -
                sum(flujos_entrantes[identificador])
            )

            if indice == indice_raiz:

                # La raíz distribuye una unidad de flujo
                # a cada uno de los demás ambientes.
                modelo.Add(
                    flujo_neto == capacidad_flujo
                )

            else:

                # Cada ambiente recibe una unidad neta.
                modelo.Add(
                    flujo_neto == -1
                )

    # --------------------------------------------------------
    # 4.7.2. CUMPLIMIENTO DE RELACIONES DEL USUARIO
    # --------------------------------------------------------

    for indice_relacion, relacion in enumerate(relaciones):

        modo = relacion["modo"]
        pares = relacion["pares"]

        adyacencias_pares = []

        for par in pares:

            identificador_a, identificador_b = par

            if identificador_a == identificador_b:
                raise ValueError(
                    "Un ambiente no puede establecer "
                    "una relación de adyacencia consigo mismo."
                )

            clave = tuple(sorted((
                identificador_a,
                identificador_b
            )))

            adyacente = adyacencias_fisicas[clave]

            adyacencias_pares.append(adyacente)

        # --------------------------------------------
        # MODO: TODOS
        # --------------------------------------------

        if modo == "todos":

            for adyacente in adyacencias_pares:

                modelo.Add(
                    adyacente == 1
                )

        # --------------------------------------------
        # MODO: AL MENOS UNO
        # --------------------------------------------

        elif modo == "al_menos_uno":

            if not adyacencias_pares:
                raise ValueError(
                    "La relación al_menos_uno "
                    "no contiene parejas posibles."
                )

            modelo.AddBoolOr(
                adyacencias_pares
            )

        # --------------------------------------------
        # MODO: CORRESPONDIENTE
        # --------------------------------------------

        elif modo == "correspondiente":

            for adyacente in adyacencias_pares:

                modelo.Add(
                    adyacente == 1
                )

        else:

            raise ValueError(
                f"Modo de adyacencia desconocido: {modo}"
            )

    # --------------------------------------------------------
    # 4.8. SUPERFICIE TOTAL OCUPADA
    # --------------------------------------------------------

    area_total = modelo.NewIntVar(
        0,
        area_terreno_dm2,
        "area_total"
    )

    modelo.Add(
        area_total == sum(variables_area)
    )

    # --------------------------------------------------------
    # 4.9. PRIMERA OPTIMIZACIÓN:
    #      MINIMIZAR DESVIACIONES DE ÁREAS
    # --------------------------------------------------------

    for nodo in nodos:

        identificador = nodo["id"]

        datos = variables[identificador]

        area = datos["area"]
        objetivo = datos["area_objetivo"]

        area_minima_dm2, _ = obtener_areas_ambiente(
            nodo
        )

        desviacion_maxima = max(
            abs(area_minima_dm2 - objetivo),
            abs(area_terreno_dm2 - objetivo)
        )

        desviacion = modelo.NewIntVar(
            0,
            desviacion_maxima,
            f"desviacion_{identificador}"
        )

        modelo.AddAbsEquality(
            desviacion,
            area - objetivo
        )

        desviaciones.append(
            desviacion
        )

    desviacion_total = sum(
        desviaciones
    )

    modelo.Minimize(
        desviacion_total
    )

    solver = cp_model.CpSolver()

    solver.parameters.max_time_in_seconds = (
        TIEMPO_MAXIMO_SEGUNDOS
    )

    estado = solver.Solve(
        modelo
    )

    if estado not in (
        cp_model.OPTIMAL,
        cp_model.FEASIBLE
    ):
        raise ValueError(
            "No se encontró una distribución espacial factible. "
            "Comprueba las áreas solicitadas, las relaciones "
            "de adyacencia y las dimensiones del terreno. "
            "También puede existir una incompatibilidad "
            "con la conectividad global."
        )

    mejor_desviacion = solver.Value(
        desviacion_total
    )

    # --------------------------------------------------------
    # 4.10. SEGUNDA OPTIMIZACIÓN:
    #       MINIMIZAR DISTANCIAS ESPACIALES
    # --------------------------------------------------------

    # Conservar la mejor desviación de superficies.
    modelo.Add(
        desviacion_total == mejor_desviacion
    )

    distancias = []

    # --------------------------------------------------------
    # DISTANCIAS ENTRE AMBIENTES RELACIONADOS
    # --------------------------------------------------------

    for indice_relacion, relacion in enumerate(relaciones):

        # Las relaciones al_menos_uno ya garantizan
        # una conexión física entre al menos una pareja.
        # No es necesario acercar artificialmente
        # todas las combinaciones posibles.

        if relacion["modo"] == "al_menos_uno":
            continue

        for indice_par, par in enumerate(relacion["pares"]):

            origen, destino = par

            datos_origen = variables[origen]
            datos_destino = variables[destino]

            centro_x_origen = (
                datos_origen["x"] * 2
                + datos_origen["ancho"]
            )

            centro_y_origen = (
                datos_origen["y"] * 2
                + datos_origen["largo"]
            )

            centro_x_destino = (
                datos_destino["x"] * 2
                + datos_destino["ancho"]
            )

            centro_y_destino = (
                datos_destino["y"] * 2
                + datos_destino["largo"]
            )

            distancia_x = modelo.NewIntVar(
                0,
                ancho_terreno_dm * 2,
                f"distancia_x_{indice_relacion}_{indice_par}"
            )

            distancia_y = modelo.NewIntVar(
                0,
                largo_terreno_dm * 2,
                f"distancia_y_{indice_relacion}_{indice_par}"
            )

            modelo.AddAbsEquality(
                distancia_x,
                centro_x_origen - centro_x_destino
            )

            modelo.AddAbsEquality(
                distancia_y,
                centro_y_origen - centro_y_destino
            )

            distancias.extend([
                distancia_x,
                distancia_y
            ])

    # --------------------------------------------------------
    # OBJETIVO DE PROXIMIDAD PONDERADA
    # --------------------------------------------------------

    PESO_RELACIONES_USUARIO = 3
    PESO_ZONIFICACION_SOCIAL = 1

    objetivo_proximidad = (
        PESO_RELACIONES_USUARIO * sum(distancias)
        + PESO_ZONIFICACION_SOCIAL * sum(proximidad_social)
    )

    modelo.Minimize(
        objetivo_proximidad
    )

    solver_final = cp_model.CpSolver()

    solver_final.parameters.max_time_in_seconds = (
        TIEMPO_MAXIMO_SEGUNDOS
    )

    estado_final = solver_final.Solve(
        modelo
    )

    # Conservar la primera solución si la segunda
    # no encuentra una solución factible.
    if estado_final in (
        cp_model.OPTIMAL,
        cp_model.FEASIBLE
    ):
        solver_resultado = solver_final
    else:
        solver_resultado = solver

    # --------------------------------------------------------
    # 4.11. RECUPERACIÓN DE RESULTADOS
    # --------------------------------------------------------

    resultado = []

    for nodo in nodos:

        identificador = nodo["id"]

        datos = variables[identificador]

        x_dm = solver_resultado.Value(
            datos["x"]
        )

        y_dm = solver_resultado.Value(
            datos["y"]
        )

        ancho_dm = solver_resultado.Value(
            datos["ancho"]
        )

        largo_dm = solver_resultado.Value(
            datos["largo"]
        )

        area_dm2 = solver_resultado.Value(
            datos["area"]
        )

        ambiente = {
            "id": identificador,
            "nombre": nodo["nombre"],

            "x": x_dm / 10,
            "y": y_dm / 10,

            "ancho": ancho_dm / 10,
            "largo": largo_dm / 10,

            "area_m2": area_dm2 / 100,

            "area_objetivo_m2": (
                datos["area_objetivo"] / 100
            ),
        }

        resultado.append(
            ambiente
        )

    return resultado


# ============================================================
# 5. PRUEBA DEL OPTIMIZADOR
# ============================================================

if __name__ == "__main__":

    from src.models.requirements import (
        RequerimientosArquitectonicos,
        Ambiente
    )

    from src.models.defaults import (
        calcular_areas_predeterminadas
    )

    requerimientos = RequerimientosArquitectonicos(
        tipo_proyecto="vivienda",

        ancho_terreno_m=10,
        largo_terreno_m=20,

        area_total_vivienda_m2=100,

        ambientes=[
            Ambiente(nombre="sala"),
            Ambiente(nombre="comedor"),
            Ambiente(nombre="cocina"),
            Ambiente(nombre="dormitorio", cantidad=2),
            Ambiente(nombre="baño", cantidad=2),
            Ambiente(nombre="lavandería"),
        ],

        relaciones_adyacencia=[
            {
                "ambiente_a": "sala",
                "ambiente_b": "comedor",
                "modo": "todos"
            },
            {
                "ambiente_a": "comedor",
                "ambiente_b": "cocina",
                "modo": "todos"
            },
            {
                "ambiente_a": "sala",
                "ambiente_b": "dormitorio",
                "modo": "al_menos_uno"
            },
            {
                "ambiente_a": "dormitorio",
                "ambiente_b": "baño",
                "modo": "al_menos_uno"
            },
            {
                "ambiente_a": "baño",
                "ambiente_b": "baño",
                "modo": "todos"
            }
        ],
    )

    requerimientos = calcular_areas_predeterminadas(
        requerimientos
    )

    resultado = optimizar_distribucion(
        requerimientos
    )

    print("\nDISTRIBUCIÓN ESPACIAL GENERADA\n")

    for ambiente in resultado:

        print(
            f"{ambiente['nombre']}: "
            f"{ambiente['area_m2']:.2f} m² "
            f"(objetivo: "
            f"{ambiente['area_objetivo_m2']:.2f} m²)"
        )

        print(
            f"  ID: {ambiente['id']}"
        )

        print(
            f"  Posición: "
            f"({ambiente['x']:.1f}, "
            f"{ambiente['y']:.1f}) m"
        )

        print(
            f"  Dimensiones: "
            f"{ambiente['ancho']:.1f} x "
            f"{ambiente['largo']:.1f} m\n"
        )

    # --------------------------------------------------------
    # 6. VALIDACIÓN DE CONECTIVIDAD
    # --------------------------------------------------------

    from src.geometry.adjacency_validator import (
        validar_distribucion,
        imprimir_validacion
    )

    print("\nVALIDACIÓN DE CONECTIVIDAD\n")

    validacion = validar_distribucion(
        resultado,
        longitud_minima_m=0.8,
        tolerancia_m=0.01
    )

    imprimir_validacion(validacion)