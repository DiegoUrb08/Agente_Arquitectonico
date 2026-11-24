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
from src.geometry.opening_generator import generar_aberturas
from src.geometry.wall_generator import generar_muros
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

    avisar("Generando aberturas en los muros...")
    aberturas = generar_aberturas(
        resultado_muros=muros,
        aberturas=puertas["puertas"],
    )

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
    )

    return ResultadoPlano(
        distribucion=distribucion,
        validacion=validacion,
        geometrias=geometrias,
        muros=muros,
        puertas=puertas,
        aberturas=aberturas,
        ruta_dxf=ruta,
    )
