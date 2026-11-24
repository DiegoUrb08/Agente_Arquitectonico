
from src.geometry.geometry_generator import generar_geometrias
from src.geometry.wall_generator import generar_muros
from src.geometry.door_generator import generar_puertas_automaticas
from src.geometry.opening_generator import generar_aberturas


# ============================================================
# 1. DISTRIBUCIÓN ESPACIAL DE PRUEBA
# ============================================================

distribucion = [
    {
        "id": "sala_1",
        "nombre": "sala",
        "x": 6.7,
        "y": 5.9,
        "ancho": 3.3,
        "largo": 5.4
    },
    {
        "id": "comedor_1",
        "nombre": "comedor",
        "x": 4.0,
        "y": 6.4,
        "ancho": 2.7,
        "largo": 4.4
    },
    {
        "id": "cocina_1",
        "nombre": "cocina",
        "x": 1.3,
        "y": 6.4,
        "ancho": 2.7,
        "largo": 4.4
    },
    {
        "id": "dormitorio_1",
        "nombre": "dormitorio",
        "x": 2.9,
        "y": 13.5,
        "ancho": 3.9,
        "largo": 3.8
    },
    {
        "id": "dormitorio_2",
        "nombre": "dormitorio",
        "x": 4.4,
        "y": 2.1,
        "ancho": 3.9,
        "largo": 3.8
    },
    {
        "id": "bano_1",
        "nombre": "baño",
        "x": 3.9,
        "y": 10.8,
        "ancho": 2.2,
        "largo": 2.7
    },
    {
        "id": "bano_2",
        "nombre": "baño",
        "x": 1.7,
        "y": 10.8,
        "ancho": 2.2,
        "largo": 2.7
    },
    {
        "id": "lavanderia_1",
        "nombre": "lavandería",
        "x": 1.8,
        "y": 4.5,
        "ancho": 2.6,
        "largo": 1.9
    }
]


# ============================================================
# 2. GENERAR GEOMETRÍAS
# ============================================================

print("\nETAPA 1: GENERACIÓN DE GEOMETRÍAS")
print("=" * 60)

resultado_geometrias = generar_geometrias(
    distribucion=distribucion,
    ancho_terreno_m=10,
    largo_terreno_m=20
)

if not resultado_geometrias["valido"]:

    for error in resultado_geometrias["errores"]:
        print(error)

    raise ValueError(
        "No se pueden generar los muros: "
        "existen errores geométricos."
    )

print(
    f"Ambientes generados: "
    f"{len(resultado_geometrias['ambientes'])}"
)


# ============================================================
# 3. GENERAR MUROS
# ============================================================

print("\nETAPA 2: GENERACIÓN DE MUROS")
print("=" * 60)

resultado_muros = generar_muros(
    ambientes_geometricos=resultado_geometrias["ambientes"],
    espesor_exterior_m=0.20,
    espesor_interior_m=0.15
)

from shapely.geometry import Point, box

print("\nDIAGNÓSTICO DEL MURO ENTRE BAÑOS")
print("=" * 60)

punto = Point(3.9, 12.15)

# Consultar las tres geometrías
for nombre, geometria in [
    ("Muros exteriores", resultado_muros["muros_exteriores"]),
    ("Muros interiores", resultado_muros["muros_interiores"]),
    ("Todos los muros", resultado_muros["todos_los_muros"])
]:

    print(f"\n{nombre}")
    print(f"  Distancia al centro: {geometria.distance(punto):.6f} m")
    print(f"  ¿Contiene el centro?: {geometria.covers(punto)}")

# Construir una región de inspección alrededor del muro
region = box(
    3.7,
    11.9,
    4.1,
    12.4
)

interseccion = resultado_muros["muros_interiores"].intersection(
    region
)

print("\nINSPECCIÓN DE LA REGIÓN")
print(f"  Área de intersección: {interseccion.area:.6f} m²")
print(f"  Geometría: {interseccion.geom_type}")
print(f"  Límites: {interseccion.bounds}")

# Identificar el segmento compartido entre los baños
ambientes = resultado_geometrias["ambientes"]

bano_1 = next(
    a for a in ambientes if a["id"] == "bano_1"
)

bano_2 = next(
    a for a in ambientes if a["id"] == "bano_2"
)

segmento = bano_1["poligono"].boundary.intersection(
    bano_2["poligono"].boundary
)

print("\nSEGMENTO COMPARTIDO ENTRE BAÑOS")
print(f"  Geometría: {segmento.geom_type}")
print(f"  Longitud: {segmento.length:.6f} m")
print(f"  Límites: {segmento.bounds}")

print(
    f"Segmentos interiores: "
    f"{resultado_muros['cantidad_segmentos_interiores']}"
)

print(
    f"Área total de muros: "
    f"{resultado_muros['area_muros_m2']:.3f} m²"
)


# ============================================================
# 4. GENERAR PUERTAS AUTOMÁTICAMENTE
# ============================================================

print("\nETAPA 3: GENERACIÓN DE PUERTAS")
print("=" * 60)

resultado_puertas = generar_puertas_automaticas(
    distribucion=distribucion,
    ancho_puerta_m=0.90,
    espesor_muro_m=0.15
)

print(
    f"Puertas propuestas: "
    f"{resultado_puertas['cantidad_puertas']}"
)


# ============================================================
# 5. CONVERTIR PUERTAS EN ABERTURAS
# ============================================================

print("\nETAPA 4: GENERACIÓN DE ABERTURAS")
print("=" * 60)

from shapely.geometry import box

print("\nDIAGNÓSTICO DE PUERTAS")
print("=" * 60)

muros = resultado_muros["todos_los_muros"]

for i, puerta in enumerate(resultado_puertas["puertas"], start=1):

    x, y = puerta["centro"]
    ancho = puerta["ancho"]
    espesor = puerta["espesor_muro"]

    if puerta["orientacion"] == "vertical":

        geometria_puerta = box(
            x - espesor / 2,
            y - ancho / 2,
            x + espesor / 2,
            y + ancho / 2
        )

    else:

        geometria_puerta = box(
            x - ancho / 2,
            y - espesor / 2,
            x + ancho / 2,
            y + espesor / 2
        )

    cubierta = muros.buffer(0.001).covers(
        geometria_puerta
    )

    interseccion = muros.intersection(
        geometria_puerta
    )

    diferencia = geometria_puerta.difference(
        muros.buffer(0.001)
    )

    print(f"\nPuerta {i}:")
    print(
        f"  Conexión: {puerta['ambiente_a']} "
        f"<-> {puerta['ambiente_b']}"
    )
    print(f"  Centro: {puerta['centro']}")
    print(f"  Cubierta completamente: {cubierta}")
    print(
        f"  Área de puerta: "
        f"{geometria_puerta.area:.6f} m²"
    )
    print(
        f"  Área dentro de muros: "
        f"{interseccion.area:.6f} m²"
    )
    print(
        f"  Área fuera de muros: "
        f"{diferencia.area:.6f} m²"
    )

resultado_aberturas = generar_aberturas(
    resultado_muros=resultado_muros,
    aberturas=resultado_puertas["puertas"]
)

print(
    f"Puertas procesadas: "
    f"{resultado_aberturas['cantidad_puertas']}"
)

print(
    f"Área original de muros: "
    f"{resultado_aberturas['muros_originales'].area:.3f} m²"
)

print(
    f"Área de muros con aberturas: "
    f"{resultado_aberturas['muros_con_aberturas'].area:.3f} m²"
)

print(
    f"Área eliminada: "
    f"{(
        resultado_aberturas['muros_originales'].area
        - resultado_aberturas['muros_con_aberturas'].area
    ):.3f} m²"
)


# ============================================================
# 6. VALIDACIÓN FINAL
# ============================================================

print("\nETAPA 5: VALIDACIÓN FINAL")
print("=" * 60)

if (
    resultado_aberturas["cantidad_puertas"]
    != resultado_puertas["cantidad_puertas"]
):
    raise AssertionError(
        "No todas las puertas propuestas se procesaron."
    )

if (
    resultado_aberturas["muros_con_aberturas"].area
    >= resultado_aberturas["muros_originales"].area
):
    raise AssertionError(
        "Las aberturas no modificaron correctamente los muros."
    )

if not resultado_aberturas["muros_con_aberturas"].is_valid:
    raise AssertionError(
        "La geometría final de los muros es inválida."
    )

print("Todas las puertas fueron procesadas correctamente.")
print("Las aberturas se descontaron de los muros.")
print("La geometría final es válida.")

print("\nPRUEBA DE INTEGRACIÓN COMPLETADA")
