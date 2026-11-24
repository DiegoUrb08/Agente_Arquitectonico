
from src.geometry.geometry_generator import generar_geometrias
from src.geometry.wall_generator import generar_muros
from src.cad.dxf_generator import generar_dxf_desde_geometrias


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

# 1. Generar geometrías
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

# 3. Exportar todo al DXF
archivo = generar_dxf_desde_geometrias(
    resultado_geometrias=resultado_geometrias,
    ancho_terreno_m=10,
    largo_terreno_m=10,
    ruta_salida="output/plano_con_muros.dxf",
    resultado_muros=resultado_muros
)

print("Archivo generado:", archivo)
print(
    "Área geométrica de muros:",
    resultado_muros["area_muros_m2"],
    "m²"
)
