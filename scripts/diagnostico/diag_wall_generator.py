
from src.geometry.geometry_generator import generar_geometrias
from src.geometry.wall_generator import generar_muros


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

# Primero generamos las geometrías
resultado_geometrias = generar_geometrias(
    distribucion,
    ancho_terreno_m=10,
    largo_terreno_m=10
)

if not resultado_geometrias["valido"]:
    raise ValueError(resultado_geometrias["errores"])

# Después generamos los muros
resultado_muros = generar_muros(
    resultado_geometrias["ambientes"],
    espesor_exterior_m=0.20,
    espesor_interior_m=0.15
)

print("Muros exteriores:")
print("Área:", resultado_muros["muros_exteriores"].area, "m²")

print("\nMuros interiores:")
print("Área:", resultado_muros["muros_interiores"].area, "m²")

print("\nTotal:")
print("Área:", resultado_muros["area_muros_m2"], "m²")

print(
    "\nLímites compartidos:",
    resultado_muros["cantidad_segmentos_interiores"]
)
