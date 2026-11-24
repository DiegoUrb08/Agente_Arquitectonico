
from shapely.geometry import box


# Dimensiones de referencia en metros:
# (ancho, largo)

DIMENSIONES_MOBILIARIO = {
    "cama_individual": (0.90, 1.90),
    "cama_matrimonial": (1.40, 1.90),
    "cama_queen": (1.60, 2.00),
    "sofa": (2.00, 0.90),
    "mesa_comedor": (1.40, 0.80),
    "silla": (0.45, 0.45),
    "escritorio": (1.20, 0.60),
    "refrigeradora": (0.70, 0.70),
    "cocina": (0.60, 0.60),
    "lavatorio": (0.60, 0.50),
    "inodoro": (0.40, 0.70),
    "ducha": (0.90, 0.90),
    "armario": (1.20, 0.60),
}


def obtener_dimensiones(tipo):
    """
    Obtiene las dimensiones de referencia
    correspondientes al mobiliario.
    """

    tipo = tipo.strip().lower()

    if tipo not in DIMENSIONES_MOBILIARIO:
        raise ValueError(
            f"Tipo de mobiliario no reconocido: {tipo}"
        )

    return DIMENSIONES_MOBILIARIO[tipo]


def construir_mobiliario(elemento):
    """
    Construye la geometría rectangular
    de un elemento de mobiliario.
    """

    x = float(elemento["x"])
    y = float(elemento["y"])

    tipo = elemento["tipo"].strip().lower()

    dimensiones = obtener_dimensiones(tipo)

    ancho = float(
        elemento.get("ancho", dimensiones[0])
    )

    largo = float(
        elemento.get("largo", dimensiones[1])
    )

    if ancho <= 0 or largo <= 0:
        raise ValueError(
            "Las dimensiones deben ser positivas."
        )

    geometria = box(
        x,
        y,
        x + ancho,
        y + largo
    )

    return {
        "tipo": tipo,
        "ambiente": elemento["ambiente"],
        "x": x,
        "y": y,
        "ancho": ancho,
        "largo": largo,
        "geometria": geometria,
    }


def generar_mobiliario(
    resultado_geometrias,
    elementos
):
    """
    Genera y valida el mobiliario dentro
    de los ambientes arquitectónicos.
    """

    if not resultado_geometrias["valido"]:
        raise ValueError(
            "No se puede generar mobiliario "
            "sobre una distribución inválida."
        )

    ambientes = resultado_geometrias["ambientes"]

    mobiliario_generado = []
    errores = []

    for elemento in elementos:

        try:
            mueble = construir_mobiliario(elemento)

            nombre_ambiente = (
                elemento["ambiente"].strip().lower()
            )

            ambiente_encontrado = None

            for ambiente in ambientes:

                if ambiente["nombre"].strip().lower() == nombre_ambiente:
                    ambiente_encontrado = ambiente
                    break

            if ambiente_encontrado is None:
                raise ValueError(
                    f"No existe el ambiente: "
                    f"{elemento['ambiente']}"
                )

            poligono_ambiente = (
                ambiente_encontrado["poligono"]
            )

            if not poligono_ambiente.covers(
                mueble["geometria"]
            ):
                raise ValueError(
                    f"El elemento {mueble['tipo']} "
                    f"no cabe dentro del ambiente "
                    f"{elemento['ambiente']}."
                )

            mobiliario_generado.append(mueble)

        except (ValueError, KeyError, TypeError) as error:

            errores.append(str(error))

    # Verificar superposición entre muebles.
    for i in range(len(mobiliario_generado)):

        for j in range(i + 1, len(mobiliario_generado)):

            mueble_a = mobiliario_generado[i]
            mueble_b = mobiliario_generado[j]

            if mueble_a["geometria"].intersection(
                mueble_b["geometria"]
            ).area > 1e-6:

                errores.append(
                    f"Superposición entre "
                    f"{mueble_a['tipo']} y "
                    f"{mueble_b['tipo']}."
                )

    return {
        "mobiliario": mobiliario_generado,
        "cantidad": len(mobiliario_generado),
        "errores": errores,
        "valido": len(errores) == 0,
    }
