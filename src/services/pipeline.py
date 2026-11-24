"""
Orquestación del flujo de generación de planos, independiente de la UI.

requerimientos -> optimización -> validación -> geometrías -> muros
-> puertas -> aberturas -> DXF.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from src.cad.dxf_generator import generar_dxf_desde_geometrias
from src.geometry.adjacency_validator import validar_distribucion
from src.geometry.door_generator import generar_puertas_automaticas
from src.geometry.geometry_generator import generar_geometrias
from src.geometry.mobiliario_automatico import amueblar_automaticamente
from src.geometry.opening_generator import generar_aberturas
from src.geometry.wall_generator import generar_muros
from src.geometry.window_generator import generar_ventanas_automaticas
from src.models.distribucion import validar_esquema_distribucion
from src.planning.layout_optimizer import optimizar_distribucion

ESPESOR_EXTERIOR_M = 0.20
ESPESOR_INTERIOR_M = 0.15
ANCHO_PUERTA_M = 0.90


@dataclass
class ResultadoPlano:
    distribucion: list
    validacion: dict
    geometrias: dict
    muros: dict
    puertas: dict
    aberturas: dict
    ruta_dxf: Path
    mobiliario: dict | None = None
    ventanas: dict | None = None


def generar_plano(
    requerimientos,
    ruta_dxf,
    progreso: Callable[[str], None] | None = None,
) -> ResultadoPlano:
    """
    Ejecuta todo el flujo y guarda el DXF en `ruta_dxf`.

    `progreso` es un callback opcional que recibe el nombre de cada etapa.
    Lanza ValueError si los datos o el resultado intermedio no son válidos.
    """

    def avisar(mensaje: str):
        if progreso:
            progreso(mensaje)

    ancho = requerimientos.ancho_terreno_m
    largo = requerimientos.largo_terreno_m

    if not ancho or not largo:
        raise ValueError("Faltan las dimensiones del terreno.")

    avisar("Optimizando la distribución espacial...")
    distribucion = optimizar_distribucion(requerimientos)

    return construir_plano(distribucion, ancho, largo, ruta_dxf, progreso)


def construir_plano(
    distribucion,
    ancho,
    largo,
    ruta_dxf,
    progreso: Callable[[str], None] | None = None,
    amueblar: bool = True,
) -> ResultadoPlano:
    """
    Genera validación, geometrías, muros, puertas, aberturas y DXF
    a partir de una distribución ya resuelta (del optimizador o editada).
    """

    def avisar(mensaje: str):
        if progreso:
            progreso(mensaje)

    validar_esquema_distribucion(distribucion)

    avisar("Validando las conexiones entre ambientes...")
    validacion = validar_distribucion(distribucion)

    avisar("Generando las geometrías de los ambientes...")
    geometrias = generar_geometrias(distribucion, ancho, largo)

    if not geometrias["valido"]:
        raise ValueError(
            "La geometría contiene errores: " + "; ".join(geometrias["errores"])
        )

    avisar("Generando muros...")
    muros = generar_muros(
        ambientes_geometricos=geometrias["ambientes"],
        espesor_exterior_m=ESPESOR_EXTERIOR_M,
        espesor_interior_m=ESPESOR_INTERIOR_M,
    )

    avisar("Calculando puertas...")
    puertas = generar_puertas_automaticas(
        distribucion=distribucion,
        ancho_puerta_m=ANCHO_PUERTA_M,
        espesor_muro_m=ESPESOR_INTERIOR_M,
    )

    avisar("Colocando ventanas en los muros exteriores...")
    ventanas = generar_ventanas_automaticas(
        geometrias,
        espesor_muro_m=ESPESOR_EXTERIOR_M,
        puertas=puertas,
    )

    avisar("Generando aberturas en los muros...")
    aberturas = generar_aberturas(
        resultado_muros=muros,
        aberturas=puertas["puertas"] + ventanas["ventanas"],
    )

    mobiliario = None

    if amueblar:
        avisar("Colocando el mobiliario...")
        mobiliario = amueblar_automaticamente(geometrias, puertas)

    avisar("Construyendo el plano DXF...")
    ruta = Path(ruta_dxf)
    ruta.parent.mkdir(parents=True, exist_ok=True)

    generar_dxf_desde_geometrias(
        resultado_geometrias=geometrias,
        ancho_terreno_m=ancho,
        largo_terreno_m=largo,
        ruta_salida=str(ruta),
        resultado_muros=muros,
        resultado_aberturas=aberturas,
        resultado_mobiliario=mobiliario,
    )

    return ResultadoPlano(
        distribucion=distribucion,
        validacion=validacion,
        geometrias=geometrias,
        muros=muros,
        puertas=puertas,
        aberturas=aberturas,
        ruta_dxf=ruta,
        mobiliario=mobiliario,
        ventanas=ventanas,
    )


def editar_plano(
    ruta_entrada,
    ruta_salida,
    solicitud,
    progreso: Callable[[str], None] | None = None,
) -> dict:
    """
    Aplica la edición sobre la distribución del DXF y regenera el plano
    completo (muros, puertas, aberturas) para que quede coherente.

    Devuelve las claves de `editar_dxf` más `plano` (ResultadoPlano).
    """

    from src.cad.dxf_editor import (
        cargar_y_editar,
        distribucion_desde_ambientes,
    )

    entrada = Path(ruta_entrada)
    salida = Path(ruta_salida)

    if entrada.exists() and entrada.resolve() == salida.resolve():
        raise ValueError(
            "El archivo de salida debe ser diferente del archivo original."
        )

    _, ambientes, terreno, resultados = cargar_y_editar(entrada, solicitud)

    xmin, ymin, xmax, ymax = terreno.bounds
    distribucion = distribucion_desde_ambientes(ambientes)

    plano = construir_plano(
        distribucion,
        round(xmax - xmin, 3),
        round(ymax - ymin, 3),
        salida,
        progreso,
    )

    observaciones = list(solicitud.observaciones)

    if not plano.validacion["distribucion_conectada"]:
        observaciones.append(
            "Tras la edición hay ambientes sin pared compartida con el "
            "resto, por lo que no tienen puerta. Prueba a moverlos junto "
            "a otro ambiente."
        )

    return {
        "archivo": str(salida),
        "modificaciones": resultados,
        "observaciones": observaciones,
        "plano": plano,
    }
