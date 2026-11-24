"""Diagnóstico manual del optimizador (extraído de layout_optimizer.py)."""

from src.planning.layout_optimizer import optimizar_distribucion
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
