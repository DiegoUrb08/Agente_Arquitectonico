from src.planning.space_graph import (
    Ambiente,
    GrafoEspacial
)


grafo = GrafoEspacial()

# Crear ambientes
grafo.agregar_ambiente(
    Ambiente(
        nombre="Sala",
        categoria="social",
        area_minima=8,
        area_objetivo=8,
        zona="social"
    )
)

grafo.agregar_ambiente(
    Ambiente(
        nombre="Baño 1",
        categoria="servicio",
        area_minima=4,
        area_objetivo=8,
        zona="servicio"
    )
)

grafo.agregar_ambiente(
    Ambiente(
        nombre="Baño 2",
        categoria="servicio",
        area_minima=4,
        area_objetivo=8,
        zona="servicio"
    )
)

# Establecer relacion
grafo.agregar_relacion(
    "baño 1",
    "baño 2",
    "adyacente",
    peso=5
)

# Validar
errores = grafo.validar()

if errores:
    print("ERRORES:", errores)
else:
    print("GRAFO ESPACIAL CREADO CORRECTAMENTE")

# Mostrar informacion
print(grafo.exportar())