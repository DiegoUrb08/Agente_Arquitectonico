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
    AMBIENTES_VALIDOS,
    AMBIENTES_PLANTA_BAJA,
    AMBIENTES_PLANTA_ALTA,
    DIMENSIONES_REFERENCIA,
    obtener_dimensiones_referencia,
    obtener_proporcion_maxima,
    obtener_areas_ambiente,
)
from src.planning.restricciones import agregar_adyacencia_fisica  # noqa: F401
from src.utils.texto import normalizar_nombre


PESO_RELACIONES_USUARIO = 3
PESO_ZONIFICACION_SOCIAL = 1


# ============================================================
# 1. VALIDACIONES DE ENTRADA
# ============================================================

def _validar_terreno(requerimientos):
    """Devuelve (ancho, largo) del terreno en dm, validado."""

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

    ancho_dm = math.floor(ancho_terreno * 10)
    largo_dm = math.floor(largo_terreno * 10)

    if ancho_dm < MIN_LADO_DM or largo_dm < MIN_LADO_DM:
        raise ValueError(
            "El terreno es demasiado pequeño "
            "para las dimensiones mínimas."
        )

    return ancho_dm, largo_dm


def _validar_capacidad_terreno(requerimientos, nodos, area_terreno_dm2):
    """
    Comprueba que lo solicitado quepa en el terreno antes de resolver.

    El optimizador distribuye todos los ambientes en una sola planta,
    por lo que la suma de las áreas mínimas debe caber en el terreno.
    """

    area_terreno_m2 = area_terreno_dm2 / 100

    pisos = requerimientos.numero_pisos
    if pisos is not None and pisos < 1:
        raise ValueError("El número de pisos debe ser al menos 1.")

    minima_m2 = sum(
        obtener_areas_ambiente(nodo)[0] for nodo in nodos
    ) / 100

    if minima_m2 > area_terreno_m2:
        raise ValueError(
            f"Los ambientes pedidos necesitan al menos {minima_m2:.1f} m² "
            f"y el terreno solo tiene {area_terreno_m2:.1f} m². "
            "Aumenta el terreno o reduce los ambientes."
        )

    total = requerimientos.area_total_vivienda_m2
    if total is not None and pisos and pisos >= 1:
        por_piso = total / pisos
        if por_piso > area_terreno_m2:
            raise ValueError(
                f"Con {pisos} piso(s), cada planta ocuparía {por_piso:.1f} m² "
                f"y el terreno solo tiene {area_terreno_m2:.1f} m². "
                "Aumenta el terreno o el número de pisos."
            )


def _es_tipo_valido(nombre: str) -> bool:
    """True si el nombre normalizado corresponde a un tipo soportado."""
    n = normalizar_nombre(nombre)
    if n in AMBIENTES_VALIDOS:
        return True
    # Prefijos compuestos: "dormitorio principal", "bano visitas", etc.
    for prefijo in ("dormitorio", "bano"):
        if n.startswith(prefijo):
            return True
    return False


def _validar_ambientes(nodos):
    """
    Rechaza tipos de ambiente que el optimizador no soporta.
    Acumula todos los inválidos y los informa en un solo mensaje.
    """
    invalidos = sorted({
        nodo["nombre"]
        for nodo in nodos
        if not _es_tipo_valido(nodo["nombre"])
    })
    if not invalidos:
        return

    catalogo = ", ".join(sorted(AMBIENTES_VALIDOS))
    lista = ", ".join(f"'{n}'" for n in invalidos)
    raise ValueError(
        f"El tipo de ambiente {lista} no está en el catálogo del sistema. "
        f"Los tipos disponibles son: {catalogo}."
    )


def _validar_grafo(grafo):
    """Comprueba nodos, identificadores y relaciones."""

    nodos = grafo["nodos"]
    relaciones = grafo["relaciones"]

    if not nodos:
        raise ValueError(
            "No existen ambientes para distribuir."
        )

    identificadores = [nodo["id"] for nodo in nodos]

    if len(identificadores) != len(set(identificadores)):
        raise ValueError(
            "Existen identificadores duplicados."
        )

    validos = set(identificadores)

    for relacion in relaciones:
        for par in relacion["pares"]:

            origen, destino = par

            if origen not in validos or destino not in validos:
                raise ValueError(
                    f"La relación {par} hace referencia "
                    "a un ambiente inexistente."
                )


# ============================================================
# 2. VARIABLES Y RESTRICCIONES DEL MODELO
# ============================================================

def _centro_doble(datos):
    """Centro del ambiente multiplicado por 2 (evita fracciones)."""

    return (
        datos["x"] * 2 + datos["ancho"],
        datos["y"] * 2 + datos["largo"],
    )


def _distancia_manhattan(
    modelo, datos_a, datos_b, ancho_terreno_dm, largo_terreno_dm,
    nombre_x, nombre_y
):
    """Variables |dx| y |dy| entre los centros de dos ambientes."""

    centro_x_a, centro_y_a = _centro_doble(datos_a)
    centro_x_b, centro_y_b = _centro_doble(datos_b)

    distancia_x = modelo.NewIntVar(0, ancho_terreno_dm * 2, nombre_x)
    distancia_y = modelo.NewIntVar(0, largo_terreno_dm * 2, nombre_y)

    modelo.AddAbsEquality(distancia_x, centro_x_a - centro_x_b)
    modelo.AddAbsEquality(distancia_y, centro_y_a - centro_y_b)

    return distancia_x, distancia_y


def _crear_variables_ambientes(
    modelo, nodos, ancho_terreno_dm, largo_terreno_dm
):
    """
    Crea posición, dimensiones, área y límites de cada ambiente.

    Devuelve (variables, intervalos_x, intervalos_y, variables_area).
    """

    area_terreno_dm2 = ancho_terreno_dm * largo_terreno_dm

    variables = {}
    intervalos_x = []
    intervalos_y = []
    variables_area = []

    for nodo in nodos:

        identificador = nodo["id"]

        nombre_ambiente = normalizar_nombre(nodo["nombre"])

        area_minima, area_objetivo = obtener_areas_ambiente(nodo)

        if area_minima > area_terreno_dm2:
            raise ValueError(
                f"El área mínima de {nodo['nombre']} "
                "supera la superficie del terreno."
            )

        x = modelo.NewIntVar(0, ancho_terreno_dm, f"x_{identificador}")
        y = modelo.NewIntVar(0, largo_terreno_dm, f"y_{identificador}")

        ancho = modelo.NewIntVar(
            MIN_LADO_DM, ancho_terreno_dm, f"ancho_{identificador}"
        )
        largo = modelo.NewIntVar(
            MIN_LADO_DM, largo_terreno_dm, f"largo_{identificador}"
        )

        # Proporción máxima entre lados.
        proporcion_entera = round(
            obtener_proporcion_maxima(nombre_ambiente) * 10
        )

        modelo.Add(ancho * 10 <= largo * proporcion_entera)
        modelo.Add(largo * 10 <= ancho * proporcion_entera)

        # Área = ancho x largo, con el mínimo como cota inferior.
        area = modelo.NewIntVar(
            area_minima, area_terreno_dm2, f"area_{identificador}"
        )

        modelo.AddMultiplicationEquality(area, [ancho, largo])

        variables_area.append(area)

        # Límites del terreno.
        fin_x = modelo.NewIntVar(
            0, ancho_terreno_dm, f"fin_x_{identificador}"
        )
        fin_y = modelo.NewIntVar(
            0, largo_terreno_dm, f"fin_y_{identificador}"
        )

        modelo.Add(fin_x == x + ancho)
        modelo.Add(fin_y == y + largo)
        modelo.Add(fin_x <= ancho_terreno_dm)
        modelo.Add(fin_y <= largo_terreno_dm)

        # Intervalos para la no superposición.
        intervalos_x.append(modelo.NewIntervalVar(
            x, ancho, fin_x, f"intervalo_x_{identificador}"
        ))
        intervalos_y.append(modelo.NewIntervalVar(
            y, largo, fin_y, f"intervalo_y_{identificador}"
        ))

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

    return variables, intervalos_x, intervalos_y, variables_area


def _proximidad_ambientes_sociales(
    modelo, nodos, variables, ancho_terreno_dm, largo_terreno_dm
):
    """Distancias entre ambientes sociales (para agruparlos)."""

    sociales = [
        variables[nodo["id"]]
        for nodo in nodos
        if normalizar_nombre(nodo["nombre"]) in AMBIENTES_SOCIALES
    ]

    proximidad = []

    for i in range(len(sociales)):
        for j in range(i + 1, len(sociales)):

            distancia_x, distancia_y = _distancia_manhattan(
                modelo, sociales[i], sociales[j],
                ancho_terreno_dm, largo_terreno_dm,
                f"distancia_social_x_{i}_{j}",
                f"distancia_social_y_{i}_{j}",
            )

            proximidad.append(distancia_x + distancia_y)

    return proximidad


def _adyacencias_globales(
    modelo, nodos, variables, ancho_terreno_dm, largo_terreno_dm
):
    """Una variable de adyacencia física por cada pareja de ambientes."""

    adyacencias = {}

    for i in range(len(nodos)):
        for j in range(i + 1, len(nodos)):

            id_a = nodos[i]["id"]
            id_b = nodos[j]["id"]

            adyacencias[tuple(sorted((id_a, id_b)))] = (
                agregar_adyacencia_fisica(
                    modelo=modelo,
                    ambiente_a=variables[id_a],
                    ambiente_b=variables[id_b],
                    identificador=f"global_{i}_{j}",
                    ancho_terreno_dm=ancho_terreno_dm,
                    largo_terreno_dm=largo_terreno_dm,
                )
            )

    return adyacencias


def _conectividad_global(modelo, nodos, adyacencias):
    """
    Garantiza que todos los ambientes formen una sola red mediante
    un flujo desde el primer ambiente (raíz) que solo circula por
    pares físicamente adyacentes.
    """

    cantidad = len(nodos)

    if cantidad <= 1:
        return

    capacidad = cantidad - 1

    salientes = {nodo["id"]: [] for nodo in nodos}
    entrantes = {nodo["id"]: [] for nodo in nodos}

    for i in range(cantidad):
        for j in range(i + 1, cantidad):

            id_a = nodos[i]["id"]
            id_b = nodos[j]["id"]

            adyacente = adyacencias[tuple(sorted((id_a, id_b)))]

            flujo_ab = modelo.NewIntVar(0, capacidad, f"flujo_{i}_{j}")
            flujo_ba = modelo.NewIntVar(0, capacidad, f"flujo_{j}_{i}")

            modelo.Add(flujo_ab <= capacidad * adyacente)
            modelo.Add(flujo_ba <= capacidad * adyacente)

            salientes[id_a].append(flujo_ab)
            entrantes[id_b].append(flujo_ab)

            salientes[id_b].append(flujo_ba)
            entrantes[id_a].append(flujo_ba)

    for indice, nodo in enumerate(nodos):

        identificador = nodo["id"]

        flujo_neto = (
            sum(salientes[identificador])
            - sum(entrantes[identificador])
        )

        # La raíz reparte una unidad a cada otro ambiente.
        if indice == 0:
            modelo.Add(flujo_neto == capacidad)
        else:
            modelo.Add(flujo_neto == -1)


def _relaciones_usuario(modelo, relaciones, adyacencias):
    """Impone las adyacencias pedidas por el usuario."""

    for relacion in relaciones:

        modo = relacion["modo"]

        adyacencias_pares = []

        for id_a, id_b in relacion["pares"]:

            if id_a == id_b:
                raise ValueError(
                    "Un ambiente no puede establecer "
                    "una relación de adyacencia consigo mismo."
                )

            adyacencias_pares.append(
                adyacencias[tuple(sorted((id_a, id_b)))]
            )

        # "correspondiente" ya viene emparejado desde el grafo.
        if modo in ("todos", "correspondiente"):

            for adyacente in adyacencias_pares:
                modelo.Add(adyacente == 1)

        elif modo == "al_menos_uno":

            if not adyacencias_pares:
                raise ValueError(
                    "La relación al_menos_uno "
                    "no contiene parejas posibles."
                )

            modelo.AddBoolOr(adyacencias_pares)

        else:
            raise ValueError(
                f"Modo de adyacencia desconocido: {modo}"
            )


def _desviaciones_de_area(modelo, nodos, variables, area_terreno_dm2):
    """Variables |área - objetivo| de cada ambiente."""

    desviaciones = []

    for nodo in nodos:

        identificador = nodo["id"]

        datos = variables[identificador]

        area = datos["area"]
        objetivo = datos["area_objetivo"]

        area_minima_dm2, _ = obtener_areas_ambiente(nodo)

        desviacion = modelo.NewIntVar(
            0,
            max(
                abs(area_minima_dm2 - objetivo),
                abs(area_terreno_dm2 - objetivo),
            ),
            f"desviacion_{identificador}",
        )

        modelo.AddAbsEquality(desviacion, area - objetivo)

        desviaciones.append(desviacion)

    return desviaciones


def _distancias_relaciones(
    modelo, relaciones, variables, ancho_terreno_dm, largo_terreno_dm
):
    """
    Distancias entre ambientes relacionados por el usuario.

    Las relaciones "al_menos_uno" ya garantizan una conexión física,
    por lo que no se acercan artificialmente todas sus combinaciones.
    """

    distancias = []

    for indice_relacion, relacion in enumerate(relaciones):

        if relacion["modo"] == "al_menos_uno":
            continue

        for indice_par, (origen, destino) in enumerate(relacion["pares"]):

            distancias.extend(_distancia_manhattan(
                modelo, variables[origen], variables[destino],
                ancho_terreno_dm, largo_terreno_dm,
                f"distancia_x_{indice_relacion}_{indice_par}",
                f"distancia_y_{indice_relacion}_{indice_par}",
            ))

    return distancias


def _resolver(modelo):
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = TIEMPO_MAXIMO_SEGUNDOS
    estado = solver.Solve(modelo)
    return solver, estado


def _extraer_resultado(solver, nodos, variables):
    """Convierte la solución (dm) a la lista de ambientes (m)."""

    resultado = []

    for nodo in nodos:

        datos = variables[nodo["id"]]

        resultado.append({
            "id": nodo["id"],
            "nombre": nodo["nombre"],

            "x": solver.Value(datos["x"]) / 10,
            "y": solver.Value(datos["y"]) / 10,

            "ancho": solver.Value(datos["ancho"]) / 10,
            "largo": solver.Value(datos["largo"]) / 10,

            "area_m2": solver.Value(datos["area"]) / 100,
            "area_objetivo_m2": datos["area_objetivo"] / 100,
        })

    return resultado


# ============================================================
# 3. OPTIMIZACIÓN DE LA DISTRIBUCIÓN
# ============================================================

def optimizar_distribucion(requerimientos):
    """
    Genera una distribución espacial preliminar
    mediante programación por restricciones.

    Objetivos (en dos fases, lexicográficos):

    1. Aproximar las superficies a sus áreas objetivo.
    2. Con esa desviación fija, minimizar las distancias entre
       ambientes relacionados y agrupar los ambientes sociales.

    Restricciones:

    - Ambientes dentro del terreno.
    - Sin superposición entre ambientes.
    - Respeto de las áreas mínimas.
    - Control de proporciones geométricas.
    - Adyacencia física cuando se solicita.
    - Conectividad global de la distribución.
    """

    ancho_terreno_dm, largo_terreno_dm = _validar_terreno(requerimientos)

    area_terreno_dm2 = ancho_terreno_dm * largo_terreno_dm

    grafo = construir_grafo(requerimientos)

    _validar_grafo(grafo)

    nodos = grafo["nodos"]
    relaciones = grafo["relaciones"]

    _validar_ambientes(nodos)
    _validar_capacidad_terreno(requerimientos, nodos, area_terreno_dm2)

    modelo = cp_model.CpModel()

    # Variables y restricciones geométricas.
    variables, intervalos_x, intervalos_y, variables_area = (
        _crear_variables_ambientes(
            modelo, nodos, ancho_terreno_dm, largo_terreno_dm
        )
    )

    proximidad_social = _proximidad_ambientes_sociales(
        modelo, nodos, variables, ancho_terreno_dm, largo_terreno_dm
    )

    modelo.AddNoOverlap2D(intervalos_x, intervalos_y)

    # Adyacencia, conectividad y relaciones del usuario.
    adyacencias = _adyacencias_globales(
        modelo, nodos, variables, ancho_terreno_dm, largo_terreno_dm
    )

    _conectividad_global(modelo, nodos, adyacencias)

    _relaciones_usuario(modelo, relaciones, adyacencias)

    area_total = modelo.NewIntVar(0, area_terreno_dm2, "area_total")
    modelo.Add(area_total == sum(variables_area))

    # Fase 1: minimizar las desviaciones de área.
    desviacion_total = sum(
        _desviaciones_de_area(modelo, nodos, variables, area_terreno_dm2)
    )

    modelo.Minimize(desviacion_total)

    solver, estado = _resolver(modelo)

    if estado not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise ValueError(
            "No se encontró una distribución espacial factible. "
            "Comprueba las áreas solicitadas, las relaciones "
            "de adyacencia y las dimensiones del terreno. "
            "También puede existir una incompatibilidad "
            "con la conectividad global."
        )

    # Fase 2: conservar la mejor desviación y minimizar distancias.
    modelo.Add(desviacion_total == solver.Value(desviacion_total))

    distancias = _distancias_relaciones(
        modelo, relaciones, variables, ancho_terreno_dm, largo_terreno_dm
    )

    modelo.Minimize(
        PESO_RELACIONES_USUARIO * sum(distancias)
        + PESO_ZONIFICACION_SOCIAL * sum(proximidad_social)
    )

    solver_final, estado_final = _resolver(modelo)

    # Si la segunda fase no mejora o no es factible, se conserva la primera.
    if estado_final in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        solver_resultado = solver_final
    else:
        solver_resultado = solver

    return _extraer_resultado(solver_resultado, nodos, variables)


# ============================================================
# OPTIMIZACIÓN POR PISOS
# ============================================================

def optimizar_por_pisos(requerimientos) -> list[list[dict]]:
    """
    Para viviendas de más de un piso: divide los ambientes en planta baja
    (social + servicio) y planta(s) alta(s) (privados), añade una escalera
    a cada piso y los optimiza de forma independiente.

    Retorna una lista de distribuciones, una por piso.
    Si los ambientes privados quedan vacíos, cae en distribución de un piso.
    """
    from src.models.requirements import Ambiente

    n_pisos = max(2, requerimientos.numero_pisos or 2)

    baja: list = []
    alta: list = []

    for amb in requerimientos.ambientes:
        nombre_norm = normalizar_nombre(amb.nombre)
        es_alto = any(
            nombre_norm.startswith(t) for t in ("dormitorio", "bano", "closet", "pasillo")
        )
        if es_alto:
            alta.append(amb)
        else:
            baja.append(amb)

    # Si no hay ambientes privados, optimizar como un solo piso.
    if not alta:
        return [optimizar_distribucion(requerimientos)]

    distribuciones = []
    for piso_ambs in [baja, alta]:
        piso_ambs = list(piso_ambs) + [Ambiente(nombre="escalera", cantidad=1)]
        sub_req = requerimientos.model_copy(
            update={"ambientes": piso_ambs, "numero_pisos": 1}
        )
        distribuciones.append(optimizar_distribucion(sub_req))

    return distribuciones
