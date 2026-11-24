
from src.geometry.geometry_generator import generar_geometrias
from src.geometry.furniture_generator import generar_mobiliario


# Distribución de prueba
distribucion = [
    {
        "id": "sala_1",
        "nombre": "Sala",
        "x": 0,
        "y": 0,
        "ancho": 5,
        "largo": 4,
    },
    {
        "id": "cocina_1",
        "nombre": "Cocina",
        "x": 5,
        "y": 0,
        "ancho": 3,
        "largo": 4,
    },
]


# Generar geometrías
resultado_geometrias = generar_geometrias(
    distribucion,
    10,
    10
)


# Mobiliario de prueba
elementos = [
    {
        "tipo": "sofa",
        "ambiente": "Sala",
        "x": 0.5,
        "y": 0.5,
    },
    {
        "tipo": "mesa_comedor",
        "ambiente": "Sala",
        "x": 2.5,
        "y": 2,
    },
    {
        "tipo": "refrigeradora",
        "ambiente": "Cocina",
        "x": 5.2,
        "y": 0.5,
    },
    {
        "tipo": "cocina",
        "ambiente": "Cocina",
        "x": 6.2,
        "y": 0.5,
    },
]


# Generar mobiliario
resultado = generar_mobiliario(
    resultado_geometrias,
    elementos
)


print("MOBILIARIO GENERADO")

for mueble in resultado["mobiliario"]:
    print(
        mueble["tipo"],
        mueble["ambiente"],
        mueble["ancho"],
        mueble["largo"]
    )

print("Cantidad:", resultado["cantidad"])
print("Errores:", resultado["errores"])
print("¿Distribución válida?:", resultado["valido"])

from src.geometry.wall_generator import generar_muros
from src.geometry.opening_generator import generar_aberturas
from src.cad.dxf_generator import generar_dxf_desde_geometrias


# Generar muros
resultado_muros = generar_muros(
    resultado_geometrias["ambientes"]
)


# Generar aberturas
aberturas = [
    {
        "tipo": "puerta",
        "centro": (5, 2),
        "ancho": 0.90,
        "espesor_muro": 0.15,
        "orientacion": "vertical",
    },
    {
        "tipo": "ventana",
        "centro": (2.5, 0),
        "ancho": 1.20,
        "espesor_muro": 0.20,
        "orientacion": "horizontal",
    },
]

resultado_aberturas = generar_aberturas(
    resultado_muros,
    aberturas
)


# Exportar plano completo
generar_dxf_desde_geometrias(
    resultado_geometrias=resultado_geometrias,
    ancho_terreno_m=10,
    largo_terreno_m=10,
    ruta_salida="output/plano_con_mobiliario.dxf",
    resultado_muros=resultado_muros,
    resultado_aberturas=resultado_aberturas,
    resultado_mobiliario=resultado
)

print("DXF generado correctamente.")