from src.geometry.geometry_generator import generar_geometrias


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

resultado = generar_geometrias(
    distribucion=distribucion,
    ancho_terreno_m=10,
    largo_terreno_m=10,
)

print("¿Distribución válida?:", resultado["valido"])

for ambiente in resultado["ambientes"]:
    print(
        ambiente["nombre"],
        "Área:", ambiente["area_m2"],
        "m²"
    )

for error in resultado["errores"]:
    print("ERROR:", error)
