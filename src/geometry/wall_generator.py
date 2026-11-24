from shapely.ops import unary_union, snap


def generar_muros(
    ambientes_geometricos: list[dict],
    espesor_exterior_m: float = 0.20,
    espesor_interior_m: float = 0.15,
) -> dict:
    """
    Genera muros exteriores e interiores a partir
    de los polígonos de los ambientes.

    Los espesores están expresados en metros.
    """

    # -----------------------------------------
    # 1. VALIDACIONES
    # -----------------------------------------

    if espesor_exterior_m <= 0:
        raise ValueError(
            "El espesor exterior debe ser positivo."
        )

    if espesor_interior_m <= 0:
        raise ValueError(
            "El espesor interior debe ser positivo."
        )

    if not ambientes_geometricos:
        raise ValueError(
            "No existen ambientes para generar muros."
        )

    poligonos = [
        ambiente["poligono"]
        for ambiente in ambientes_geometricos
    ]

    # -----------------------------------------
    # 2. UNIFICAR AMBIENTES
    # -----------------------------------------

    conjunto_ambientes = unary_union(poligonos)

    # -----------------------------------------
    # 3. GENERAR MUROS EXTERIORES
    # -----------------------------------------

    # El espesor se distribuye a ambos lados
    # del perímetro exterior.

    muros_exteriores = conjunto_ambientes.boundary.buffer(
        espesor_exterior_m / 2,
        join_style=2
    )

    # -----------------------------------------
    # 4. IDENTIFICAR LÍMITES COMPARTIDOS
    # -----------------------------------------

    segmentos_compartidos = []

    for i in range(len(poligonos)):
        for j in range(i + 1, len(poligonos)):

            # Ajustar pequeñas diferencias de precisión
            # entre los límites de ambientes adyacentes.
            limite_b = snap(
                poligonos[j].boundary,
                poligonos[i].boundary,
                1e-6
            )

            # Calcular la intersección después del ajuste.
            limite_compartido = poligonos[i].boundary.intersection(
                limite_b
            )

            if limite_compartido.length > 1e-6:
                segmentos_compartidos.append(limite_compartido)

    # -----------------------------------------
    # 5. GENERAR MUROS INTERIORES
    # -----------------------------------------

    if segmentos_compartidos:

        lineas_internas = unary_union(
            segmentos_compartidos
        )

        muros_interiores = lineas_internas.buffer(
            espesor_interior_m / 2,
            cap_style=2,
            join_style=2
        )

        # Los muros interiores permanecen
        # dentro del conjunto de ambientes.

        muros_interiores = muros_interiores.intersection(
            conjunto_ambientes
        )

    else:

        muros_interiores = unary_union([])

    # -----------------------------------------
    # 6. UNIFICAR TODOS LOS MUROS
    # -----------------------------------------

    todos_los_muros = unary_union([
        muros_exteriores,
        muros_interiores
    ])

    # -----------------------------------------
    # 7. DEVOLVER RESULTADOS
    # -----------------------------------------

    return {
        "muros_exteriores": muros_exteriores,
        "muros_interiores": muros_interiores,
        "todos_los_muros": todos_los_muros,
        "area_muros_m2": todos_los_muros.area,
        "cantidad_segmentos_interiores": len(
            segmentos_compartidos
        ),
    }
