import math

from ortools.sat.python import cp_model

from src.planning.space_graph import construir_grafo
from src.planning.reglas_ambientes import (  # noqa: F401
    MIN_LADO_DM,
    TIEMPO_MAXIMO_SEGUNDOS,
    LONGITUD_MINIMA_ADYACENCIA_DM,
    PROPORCIONES_AMBIENTES,
    PROPORCION_DEFAULT,
    AMBIENTES_SOCIALES,
    AMBIENTES_PRIVADOS,
    AMBIENTES_SERVICIO,
    DIMENSIONES_REFERENCIA,
    obtener_dimensiones_referencia,
    obtener_proporcion_maxima,
    obtener_areas_ambiente,
)
from src.planning.restricciones import agregar_adyacencia_fisica  # noqa: F401
from src.utils.texto import normalizar_nombre


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
