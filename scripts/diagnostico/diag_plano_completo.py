
from pathlib import Path

from src.geometry.geometry_generator import generar_geometrias
from src.geometry.wall_generator import generar_muros
from src.geometry.opening_generator import generar_aberturas
from src.geometry.furniture_generator import generar_mobiliario

from src.cad.dxf_generator import generar_dxf_desde_geometrias


# ==================================================
# 1. CONFIGURACIÓN DEL TERRENO
# ==================================================

ANCHO_TERRENO = 12
LARGO_TERRENO = 10

RUTA_SALIDA = "output/vivienda_completa.dxf"


# ==================================================
# 2. DISTRIBUCIÓN DE AMBIENTES
# ==================================================

distribucion = [

    {
        "id": "sala_1",
        "nombre": "Sala",
        "x": 0,
        "y": 0,
        "ancho": 5,
        "largo": 5
    },

    {
        "id": "comedor_1",
        "nombre": "Comedor",
        "x": 5,
        "y": 0,
        "ancho": 3,
        "largo": 5
    },

    {
        "id": "cocina_1",
        "nombre": "Cocina",
        "x": 8,
        "y": 0,
        "ancho": 4,
        "largo": 5
    },

    {
        "id": "dormitorio_principal",
        "nombre": "Dormitorio principal",
        "x": 0,
        "y": 5,
        "ancho": 5,
        "largo": 4
    },

    {
        "id": "dormitorio_secundario",
        "nombre": "Dormitorio secundario",
        "x": 5,
        "y": 5,
        "ancho": 4,
        "largo": 4
    },

    {
        "id": "bano_principal",
        "nombre": "Baño principal",
        "x": 9,
        "y": 5,
        "ancho": 3,
        "largo": 2
    },

    {
        "id": "bano_secundario",
        "nombre": "Baño secundario",
        "x": 9,
        "y": 7,
        "ancho": 3,
        "largo": 2
    },

]


# ==================================================
# 3. GENERAR GEOMETRÍAS
# ==================================================

print("\n" + "=" * 55)
print("ETAPA 1: GENERACIÓN DE GEOMETRÍAS")
print("=" * 55)

resultado_geometrias = generar_geometrias(
    distribucion,
    ANCHO_TERRENO,
    LARGO_TERRENO
)

if not resultado_geometrias["valido"]:

    raise ValueError(
        f"Error en geometrías: "
        f"{resultado_geometrias['errores']}"
    )

print("Geometrías generadas correctamente.")

for ambiente in resultado_geometrias["ambientes"]:

    print(
        f"- {ambiente['nombre']}: "
        f"{ambiente['area_m2']:.2f} m2"
    )


# ==================================================
# 4. GENERAR MUROS
# ==================================================

print("\n" + "=" * 55)
print("ETAPA 2: GENERACIÓN DE MUROS")
print("=" * 55)

resultado_muros = generar_muros(
    resultado_geometrias["ambientes"]
)

print("Muros generados correctamente.")


# ==================================================
# 5. DEFINIR PUERTAS Y VENTANAS
# ==================================================

print("\n" + "=" * 55)
print("ETAPA 3: DEFINICIÓN DE ABERTURAS")
print("=" * 55)

aberturas = [

    # PUERTA PRINCIPAL
    {
        "tipo": "puerta",
        "centro": (0, 2.5),
        "ancho": 0.90,
        "espesor_muro": 0.20,
        "orientacion": "vertical"
    },

    # SALA - COMEDOR
    {
        "tipo": "puerta",
        "centro": (5, 2.5),
        "ancho": 0.90,
        "espesor_muro": 0.15,
        "orientacion": "vertical"
    },

    # COMEDOR - COCINA
    {
        "tipo": "puerta",
        "centro": (8, 2.5),
        "ancho": 0.90,
        "espesor_muro": 0.15,
        "orientacion": "vertical"
    },

    # ACCESO DORMITORIO PRINCIPAL
    {
        "tipo": "puerta",
        "centro": (2.5, 5),
        "ancho": 0.90,
        "espesor_muro": 0.15,
        "orientacion": "horizontal"
    },

    # ACCESO DORMITORIO SECUNDARIO
    {
        "tipo": "puerta",
        "centro": (7, 5),
        "ancho": 0.80,
        "espesor_muro": 0.15,
        "orientacion": "horizontal"
    },

    # ACCESO BAÑO PRINCIPAL
    {
        "tipo": "puerta",
        "centro": (9, 6),
        "ancho": 0.80,
        "espesor_muro": 0.15,
        "orientacion": "vertical"
    },

    # ACCESO BAÑO SECUNDARIO
    {
        "tipo": "puerta",
        "centro": (9, 8),
        "ancho": 0.80,
        "espesor_muro": 0.15,
        "orientacion": "vertical"
    },

    # VENTANA SALA
    {
        "tipo": "ventana",
        "centro": (2.5, 0),
        "ancho": 1.50,
        "espesor_muro": 0.20,
        "orientacion": "horizontal"
    },

    # VENTANA COCINA
    {
        "tipo": "ventana",
        "centro": (10, 0),
        "ancho": 1.20,
        "espesor_muro": 0.20,
        "orientacion": "horizontal"
    },

    # VENTANA DORMITORIO PRINCIPAL
    {
        "tipo": "ventana",
        "centro": (2.5, 9),
        "ancho": 1.50,
        "espesor_muro": 0.20,
        "orientacion": "horizontal"
    },

    # VENTANA DORMITORIO SECUNDARIO
    {
        "tipo": "ventana",
        "centro": (7, 9),
        "ancho": 1.20,
        "espesor_muro": 0.20,
        "orientacion": "horizontal"
    },

    # VENTANA BAÑO PRINCIPAL
    {
        "tipo": "ventana",
        "centro": (12, 6),
        "ancho": 0.60,
        "espesor_muro": 0.20,
        "orientacion": "vertical"
    },

]

resultado_aberturas = generar_aberturas(
    resultado_muros,
    aberturas
)

print("Aberturas generadas correctamente.")

print(
    "Puertas:",
    len(resultado_aberturas["puertas"])
)

print(
    "Ventanas:",
    len(resultado_aberturas["ventanas"])
)


# ==================================================
# 6. DISTRIBUCIÓN DEL MOBILIARIO
# ==================================================

print("\n" + "=" * 55)
print("ETAPA 4: GENERACIÓN DE MOBILIARIO")
print("=" * 55)

elementos_mobiliario = [

    # ----------------------------------------------
    # SALA
    # ----------------------------------------------

    {
        "tipo": "sofa",
        "ambiente": "Sala",
        "x": 1.5,
        "y": 0.8
    },

    {
        "tipo": "silla",
        "ambiente": "Sala",
        "x": 0.5,
        "y": 2.5
    },

    {
        "tipo": "silla",
        "ambiente": "Sala",
        "x": 3.8,
        "y": 2.5
    },


    # ----------------------------------------------
    # COMEDOR
    # ----------------------------------------------

    {
        "tipo": "mesa_comedor",
        "ambiente": "Comedor",
        "x": 5.8,
        "y": 1.8
    },

    {
        "tipo": "silla",
        "ambiente": "Comedor",
        "x": 5.2,
        "y": 1.975
    },

    {
        "tipo": "silla",
        "ambiente": "Comedor",
        "x": 7.35,
        "y": 1.975
    },

    {
        "tipo": "silla",
        "ambiente": "Comedor",
        "x": 6.275,
        "y": 2.75
    },

    {
        "tipo": "silla",
        "ambiente": "Comedor",
        "x": 6.275,
        "y": 1.15
    },


    # ----------------------------------------------
    # COCINA
    # ----------------------------------------------

    {
        "tipo": "refrigeradora",
        "ambiente": "Cocina",
        "x": 8.3,
        "y": 0.5
    },

    {
        "tipo": "cocina",
        "ambiente": "Cocina",
        "x": 9.3,
        "y": 0.5
    },


    # ----------------------------------------------
    # DORMITORIO PRINCIPAL
    # ----------------------------------------------

    {
        "tipo": "cama_queen",
        "ambiente": "Dormitorio principal",
        "x": 0.5,
        "y": 5.5
    },

    {
        "tipo": "armario",
        "ambiente": "Dormitorio principal",
        "x": 3.0,
        "y": 5.5
    },

    {
        "tipo": "escritorio",
        "ambiente": "Dormitorio principal",
        "x": 3.0,
        "y": 7.0
    },


    # ----------------------------------------------
    # DORMITORIO SECUNDARIO
    # ----------------------------------------------

    {
        "tipo": "cama_individual",
        "ambiente": "Dormitorio secundario",
        "x": 5.4,
        "y": 5.5
    },

    {
        "tipo": "armario",
        "ambiente": "Dormitorio secundario",
        "x": 7.3,
        "y": 5.5
    },

    {
        "tipo": "escritorio",
        "ambiente": "Dormitorio secundario",
        "x": 7.3,
        "y": 7.0
    },


    # ----------------------------------------------
    # BAÑO PRINCIPAL
    # ----------------------------------------------

    {
        "tipo": "ducha",
        "ambiente": "Baño principal",
        "x": 9.2,
        "y": 5.2
    },

    {
        "tipo": "lavatorio",
        "ambiente": "Baño principal",
        "x": 10.3,
        "y": 5.2
    },

    {
        "tipo": "inodoro",
        "ambiente": "Baño principal",
        "x": 11.2,
        "y": 5.2
    },


    # ----------------------------------------------
    # BAÑO SECUNDARIO
    # ----------------------------------------------

    {
        "tipo": "ducha",
        "ambiente": "Baño secundario",
        "x": 9.2,
        "y": 7.2
    },

    {
        "tipo": "lavatorio",
        "ambiente": "Baño secundario",
        "x": 10.3,
        "y": 7.2
    },

    {
        "tipo": "inodoro",
        "ambiente": "Baño secundario",
        "x": 11.2,
        "y": 7.2
    },

]


resultado_mobiliario = generar_mobiliario(
    resultado_geometrias,
    elementos_mobiliario
)


# Comprobar errores del mobiliario

if not resultado_mobiliario["valido"]:

    for error in resultado_mobiliario["errores"]:
        print("ERROR:", error)

    raise ValueError(
        "El mobiliario contiene errores."
    )

print(
    "Muebles generados:",
    resultado_mobiliario["cantidad"]
)


# ==================================================
# 7. EXPORTAR DXF
# ==================================================

print("\n" + "=" * 55)
print("ETAPA 5: EXPORTACIÓN DXF")
print("=" * 55)

archivo_generado = generar_dxf_desde_geometrias(
    resultado_geometrias=resultado_geometrias,

    ancho_terreno_m=ANCHO_TERRENO,

    largo_terreno_m=LARGO_TERRENO,

    ruta_salida=RUTA_SALIDA,

    resultado_muros=resultado_muros,

    resultado_aberturas=resultado_aberturas,

    resultado_mobiliario=resultado_mobiliario
)


# ==================================================
# 8. RESUMEN FINAL
# ==================================================

print("\n" + "=" * 55)
print("RESUMEN DEL PROYECTO")
print("=" * 55)

print("Terreno:", ANCHO_TERRENO, "x", LARGO_TERRENO, "m")

print(
    "Ambientes:",
    len(resultado_geometrias["ambientes"])
)

print(
    "Puertas:",
    len(resultado_aberturas["puertas"])
)

print(
    "Ventanas:",
    len(resultado_aberturas["ventanas"])
)

print(
    "Mobiliario:",
    resultado_mobiliario["cantidad"]
)

print("\nARCHIVO GENERADO CORRECTAMENTE:")
print(Path(archivo_generado).resolve())
