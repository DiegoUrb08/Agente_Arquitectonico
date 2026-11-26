
from shapely.geometry import box
from shapely.ops import unary_union


TOLERANCIA = 1e-6


def construir_abertura(
    centro: tuple[float, float],
    ancho: float,
    espesor_muro: float,
    orientacion: str
):
    """
    Construye el rectángulo que representa una abertura.

    orientacion:
        horizontal: muro horizontal.
        vertical: muro vertical.
    """

    x, y = centro

    if ancho <= 0 or espesor_muro <= 0:
        raise ValueError(
            "Las dimensiones de la abertura deben ser positivas."
        )

    if orientacion == "horizontal":

        return box(
            x - ancho / 2,
            y - espesor_muro / 2,
            x + ancho / 2,
            y + espesor_muro / 2
        )

    elif orientacion == "vertical":

        return box(
            x - espesor_muro / 2,
            y - ancho / 2,
            x + espesor_muro / 2,
            y + ancho / 2
        )

    else:
        raise ValueError(
            "La orientación debe ser horizontal o vertical."
        )


def generar_aberturas(
    resultado_muros: dict,
    aberturas: list[dict]
) -> dict:
    """
    Genera puertas y ventanas como aberturas
    que se descuentan de la geometría de los muros.

    Cada abertura debe contener:

        tipo: puerta o ventana.
        centro: coordenadas x, y.
        ancho: dimensión de la abertura.
        espesor_muro: espesor del muro atravesado.
        orientacion: horizontal o vertical.
    """

    muros = resultado_muros["todos_los_muros"]

    if muros.is_empty:
        raise ValueError(
            "No existe geometría de muros."
        )

    huecos = []
    puertas = []
    ventanas = []

    for abertura in aberturas:

        tipo = abertura["tipo"].strip().lower()

        if tipo not in ("puerta", "ventana"):
            raise ValueError(
                f"Tipo de abertura no reconocido: {tipo}"
            )

        orientacion = abertura["orientacion"].strip().lower()

        geometria = construir_abertura(
            centro=tuple(abertura["centro"]),
            ancho=float(abertura["ancho"]),
            espesor_muro=float(abertura["espesor_muro"]),
            orientacion=orientacion
        )

        # Comprobar que la abertura esté dentro del muro
        if not muros.buffer(TOLERANCIA).covers(geometria):
            raise ValueError(
                f"La {tipo} ubicada en {abertura['centro']} "
                "no está completamente dentro de un muro. "
                "Comprueba sus coordenadas y dimensiones."
            )

        huecos.append(geometria)

        elemento = {
            "tipo": tipo,
            "centro": tuple(abertura["centro"]),
            "ancho": float(abertura["ancho"]),
            "espesor_muro": float(abertura["espesor_muro"]),
            "orientacion": orientacion,
            "geometria": geometria,
            # El portón de un garaje se dibuja distinto.
            **({"vehicular": True} if abertura.get("vehicular") else {}),
        }

        if tipo == "puerta":
            puertas.append(elemento)

        else:
            ventanas.append(elemento)

    # Comprobar que las aberturas no se superpongan
    if huecos:

        conjunto_huecos = unary_union(huecos)

        suma_areas = sum(
            hueco.area for hueco in huecos
        )

        if abs(conjunto_huecos.area - suma_areas) > TOLERANCIA:
            raise ValueError(
                "Se detectaron aberturas superpuestas."
            )

        muros_modificados = muros.difference(
            conjunto_huecos
        )

    else:

        muros_modificados = muros

    return {
        "muros_originales": muros,
        "muros_con_aberturas": muros_modificados,
        "puertas": puertas,
        "ventanas": ventanas,
        "cantidad_puertas": len(puertas),
        "cantidad_ventanas": len(ventanas),
    }
