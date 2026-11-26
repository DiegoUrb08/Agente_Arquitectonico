"""
Reorganiza una planta ya resuelta para ampliar o reubicar un ambiente.

Parte de la distribución actual, la altera lo menos posible, deja que los
ambientes cedan algo de superficie y mantiene las reglas de acceso. Si el
cambio pedido es incompatible con ellas, las relaja.
"""

import math

from ortools.sat.python import cp_model

from src.planning import layout_optimizer as optimizador
from src.planning.reglas_acceso import asignar_en_suite, elegir_entrada
from src.planning.restricciones import agregar_separacion

# Cuánto puede variar la superficie de los ambientes que no se piden cambiar,
# y cuánto puede diferir la del ambiente ampliado respecto a lo pedido.
HOLGURA_VECINOS = 0.15
HOLGURA_PEDIDA = 0.03

TIEMPO_REACOMODO_SEGUNDOS = 8

PESO_AREA_PEDIDA = 50
PESO_DESPLAZAMIENTO = 20
PESO_AREA_VECINOS = 5
PESO_HUECOS = 30
PESO_SIN_VENTANA = 2000

# Al reubicar, quien debe moverse es el ambiente pedido y no su referencia.
FACTOR_MOVIDO = 0.1
FACTOR_REFERENCIA = 3
PESO_LEJANIA = 60
# "Lejos": sin tocarse y con los centros al menos esto más separados.
ALEJAMIENTO_MINIMO_DM = 10

# Pared compartida (o solapamiento) con la referencia: cabe una puerta.
CONTACTO_DM = 12

# (reglas de acceso, preferencias: baño en suite y cocina junto al comedor)
NIVELES = ((True, True), (True, False), (False, False))

RELACIONES_DE_CONTACTO = ("junto_a", "cerca_de")
# relación -> (eje en que quedan pegados, eje en que se solapan, ¿va antes?)
DIRECCIONES = {
    "izquierda_de": ("x", "y", True),
    "derecha_de": ("x", "y", False),
    "abajo_de": ("y", "x", True),
    "arriba_de": ("y", "x", False),
}

_FIN = {"x": "fin_x", "y": "fin_y"}
_LADO = {"x": "ancho", "y": "largo"}


def _nodos(distribucion, holguras=None, objetivos=None):
    nodos = []
    for ambiente in distribucion:
        identificador = ambiente["id"]
        objetivo = (objetivos or {}).get(
            identificador, ambiente["ancho"] * ambiente["largo"]
        )
        holgura = (holguras or {}).get(identificador, HOLGURA_VECINOS)
        nodos.append({
            "id": identificador,
            "nombre": ambiente["nombre"],
            "area_minima_m2": objetivo * (1 - holgura),
            "area_objetivo_m2": objetivo,
            "holgura": holgura,
        })
    return nodos


def _resolver(
    distribucion, nodos, ancho_dm, largo_dm, con_reglas, preferencias,
    peso_area, factores=None, pedido=None, pares_pedidos=(),
):
    """
    `pedido(modelo, variables, adyacencias)` impone el cambio solicitado y
    puede devolver un término adicional a minimizar.
    """
    modelo = cp_model.CpModel()
    ids = [n["id"] for n in nodos]

    variables, intervalos_x, intervalos_y, areas = (
        optimizador._crear_variables_ambientes(modelo, nodos, ancho_dm, largo_dm)
    )
    modelo.AddNoOverlap2D(intervalos_x, intervalos_y)

    adyacencias = optimizador._Adyacencias(modelo, variables, ancho_dm, largo_dm)

    if con_reglas:
        entrada = elegir_entrada(ids)
        optimizador._reglas_de_acceso(
            modelo, ids, adyacencias, entrada,
            asignar_en_suite(ids) if preferencias else {},
        )
        optimizador._entrada_al_frente(modelo, ids, variables, entrada)
        optimizador._separar_banos(
            modelo, ids, variables, [{"pares": list(pares_pedidos)}]
        )
        if preferencias:
            optimizador._cocina_junto_al_comedor(modelo, ids, adyacencias)
    else:
        optimizador._conectividad(modelo, ids, ids[0], adyacencias.par)

    termino_pedido = pedido(modelo, variables, adyacencias) if pedido else 0

    desviaciones = optimizador._desviaciones_de_area(
        modelo, nodos, variables, ancho_dm * largo_dm
    )
    coste_areas = []
    for desviacion, nodo in zip(desviaciones, nodos):
        objetivo = variables[nodo["id"]]["area_objetivo"]
        modelo.Add(desviacion <= int(objetivo * nodo["holgura"]) + 1)
        coste_areas.append(
            peso_area.get(nodo["id"], PESO_AREA_VECINOS) * desviacion
        )

    area_total = modelo.NewIntVar(0, ancho_dm * largo_dm, "area_total")
    modelo.Add(area_total == sum(areas))
    huecos, bordes = optimizador._huecos(
        modelo, variables, area_total, ancho_dm, largo_dm
    )
    interiores = optimizador._ambientes_interiores(modelo, ids, variables, bordes)

    desplazamientos = []
    for ambiente in distribucion:
        datos = variables[ambiente["id"]]
        factor = (factores or {}).get(ambiente["id"], 1)
        peso = int(PESO_DESPLAZAMIENTO * factor)
        for clave, limite in (
            ("x", ancho_dm), ("y", largo_dm),
            ("ancho", ancho_dm), ("largo", largo_dm),
        ):
            antes = min(max(round(ambiente[clave] * 10), 0), limite)
            cambio = modelo.NewIntVar(0, limite, f"cambio_{clave}_{ambiente['id']}")
            modelo.AddAbsEquality(cambio, datos[clave] - antes)
            desplazamientos.append(peso * cambio)
            modelo.AddHint(datos[clave], antes)

    modelo.Minimize(
        sum(coste_areas)
        + sum(desplazamientos)
        + PESO_HUECOS * huecos
        + PESO_SIN_VENTANA * sum(interiores)
        + termino_pedido
    )

    solver, estado = optimizador._resolver(modelo, TIEMPO_REACOMODO_SEGUNDOS)

    if estado not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None

    return optimizador._extraer_resultado(solver, nodos, variables)


def _por_niveles(distribucion, nodos, ancho_terreno_m, largo_terreno_m, **opciones):
    """Primera solución cumpliendo el máximo de reglas posible, o None."""
    ancho_dm = math.floor(ancho_terreno_m * 10 + 1e-6)
    largo_dm = math.floor(largo_terreno_m * 10 + 1e-6)

    minima_m2 = sum(n["area_minima_m2"] for n in nodos)
    if minima_m2 * 100 > ancho_dm * largo_dm:
        return None

    for con_reglas, preferencias in NIVELES:
        resultado = _resolver(
            distribucion, nodos, ancho_dm, largo_dm, con_reglas, preferencias,
            **opciones,
        )
        if resultado is not None:
            return resultado

    return None


def reacomodar_para_area(
    distribucion: list[dict],
    identificador: str,
    area_m2: float,
    ancho_terreno_m: float,
    largo_terreno_m: float,
) -> list[dict] | None:
    """Nueva distribución en la que `identificador` mide `area_m2`, o None."""
    nodos = _nodos(
        distribucion,
        holguras={identificador: HOLGURA_PEDIDA},
        objetivos={identificador: area_m2},
    )
    return _por_niveles(
        distribucion, nodos, ancho_terreno_m, largo_terreno_m,
        peso_area={identificador: PESO_AREA_PEDIDA},
    )


def cumple_relacion(ambiente: dict, referencia: dict, relacion: str) -> bool:
    """True si `ambiente` ya está junto a `referencia` en el sentido pedido."""
    if relacion == "lejos_de":
        return False

    def contacto(pegado, solape, antes):
        primero, segundo = (
            (ambiente, referencia) if antes else (referencia, ambiente)
        )
        junta = primero[pegado] + primero[_LADO[pegado]] - segundo[pegado]
        comun = min(a[solape] + a[_LADO[solape]] for a in (ambiente, referencia))
        comun -= max(ambiente[solape], referencia[solape])
        return abs(junta) < 0.01 and comun >= 0.8 - 0.01

    if relacion in RELACIONES_DE_CONTACTO:
        return any(contacto(*caso) for caso in DIRECCIONES.values())

    return contacto(*DIRECCIONES[relacion])


def _centros(variables, a, b, modelo, ancho_dm, largo_dm):
    """Distancia Manhattan entre centros (en medios decímetros)."""
    dx, dy = optimizador._distancia_manhattan(
        modelo, variables[a], variables[b], ancho_dm, largo_dm,
        f"lejos_x_{a}_{b}", f"lejos_y_{a}_{b}",
    )
    return dx + dy


def reubicar_ambiente(
    distribucion: list[dict],
    identificador: str,
    referencias: list[str],
    relacion: str,
    ancho_terreno_m: float,
    largo_terreno_m: float,
) -> list[dict] | None:
    """
    Nueva distribución en la que `identificador` cumple `relacion` respecto a
    alguna de las `referencias` (respecto a todas si es "lejos_de"), o None.
    """
    por_id = {a["id"]: a for a in distribucion}
    ancho_dm = math.floor(ancho_terreno_m * 10 + 1e-6)
    largo_dm = math.floor(largo_terreno_m * 10 + 1e-6)

    def contacto(modelo, variables, adyacencias):
        modelo.AddBoolOr([
            adyacencias.par(identificador, ref, CONTACTO_DM)
            for ref in referencias
        ])
        return 0

    def direccion(modelo, variables, adyacencias):
        pegado, solape, antes = DIRECCIONES[relacion]
        opciones = []
        for ref in referencias:
            a, b = variables[identificador], variables[ref]
            primero, segundo = (a, b) if antes else (b, a)
            opcion = modelo.NewBoolVar(f"direccion_{ref}")
            for condicion in (
                primero[_FIN[pegado]] == segundo[pegado],
                a[solape] + CONTACTO_DM <= b[_FIN[solape]],
                b[solape] + CONTACTO_DM <= a[_FIN[solape]],
            ):
                modelo.Add(condicion).OnlyEnforceIf(opcion)
            opciones.append(opcion)
        modelo.AddBoolOr(opciones)
        return 0

    def lejos(modelo, variables, adyacencias):
        distancias = []
        for ref in referencias:
            a, b = por_id[identificador], por_id[ref]
            actual = sum(
                abs((a[eje] * 2 + a[_LADO[eje]]) - (b[eje] * 2 + b[_LADO[eje]]))
                for eje in ("x", "y")
            )
            distancia = _centros(
                variables, identificador, ref, modelo, ancho_dm, largo_dm
            )
            modelo.Add(
                distancia >= round(actual * 10) + 2 * ALEJAMIENTO_MINIMO_DM
            )
            agregar_separacion(
                modelo, variables[identificador], variables[ref],
                f"lejos_{ref}", ALEJAMIENTO_MINIMO_DM,
            )
            distancias.append(distancia)
        return -PESO_LEJANIA * sum(distancias)

    if relacion in RELACIONES_DE_CONTACTO:
        pedido = contacto
    elif relacion == "lejos_de":
        pedido = lejos
    else:
        pedido = direccion

    return _por_niveles(
        distribucion,
        _nodos(distribucion),
        ancho_terreno_m,
        largo_terreno_m,
        peso_area={identificador: PESO_AREA_PEDIDA},
        factores={
            identificador: FACTOR_MOVIDO,
            **{ref: FACTOR_REFERENCIA for ref in referencias},
        },
        pedido=pedido,
        pares_pedidos=[
            (identificador, ref) for ref in referencias if relacion != "lejos_de"
        ],
    )
