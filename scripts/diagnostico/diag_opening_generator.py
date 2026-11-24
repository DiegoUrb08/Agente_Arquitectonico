
from src.geometry.geometry_generator import generar_geometrias
from src.geometry.wall_generator import generar_muros
from src.geometry.opening_generator import generar_aberturas


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

# 1. Generar ambientes
resultado_geometrias = generar_geometrias(
    distribucion,
    ancho_terreno_m=10,
    largo_terreno_m=10
)

if not resultado_geometrias["valido"]:
    raise ValueError(resultado_geometrias["errores"])

# 2. Generar muros
resultado_muros = generar_muros(
    resultado_geometrias["ambientes"],
    espesor_exterior_m=0.20,
    espesor_interior_m=0.15
)

# 3. Definir puertas y ventanas
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

# 4. Generar aberturas
resultado = generar_aberturas(
    resultado_muros,
    aberturas
)

print("Puertas:", resultado["cantidad_puertas"])
print("Ventanas:", resultado["cantidad_ventanas"])

print(
    "Área original de muros:",
    resultado["muros_originales"].area
)

print(
    "Área de muros con aberturas:",
    resultado["muros_con_aberturas"].area
)
