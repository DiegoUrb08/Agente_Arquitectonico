"""Símbolos DXF de puertas y ventanas."""

# ==========================================
# PUERTAS
# ==========================================


def dibujar_puerta(msp, puerta):
    """
    Representa una puerta mediante:
    - Dos jambas.
    - Una hoja abierta.
    - Un arco de apertura de 90 grados.

    sentido_apertura:
        positivo: apertura hacia el lado positivo
        negativo: apertura hacia el lado negativo
    """

    x, y = puerta["centro"]

    ancho = puerta["ancho"]
    espesor = puerta["espesor_muro"]

    orientacion = puerta["orientacion"]

    sentido = puerta.get(
        "sentido_apertura",
        "positivo"
    )

    if ancho <= 0 or espesor <= 0:
        raise ValueError("Dimensiones de puerta inválidas.")

    if sentido not in ("positivo", "negativo"):
        raise ValueError("Sentido de apertura inválido.")

    signo = 1 if sentido == "positivo" else -1

    # ----------------------------------
    # PUERTA EN MURO HORIZONTAL
    # ----------------------------------

    if orientacion == "horizontal":

        x1 = x - ancho / 2
        x2 = x + ancho / 2

        bisagra = (x1, y)

        # Jambas
        for px in (x1, x2):

            msp.add_line(
                (px, y - espesor / 2),
                (px, y + espesor / 2),
                dxfattribs={"layer": "PUERTAS"}
            )

        # Hoja abierta
        msp.add_line(
            bisagra,
            (x1, y + signo * ancho),
            dxfattribs={"layer": "PUERTAS"}
        )

        # Arco de apertura
        if signo > 0:
            angulo_inicio = 0
            angulo_fin = 90
        else:
            angulo_inicio = 270
            angulo_fin = 360

        msp.add_arc(
            center=bisagra,
            radius=ancho,
            start_angle=angulo_inicio,
            end_angle=angulo_fin,
            dxfattribs={"layer": "PUERTAS"}
        )

    # ----------------------------------
    # PUERTA EN MURO VERTICAL
    # ----------------------------------

    elif orientacion == "vertical":

        y1 = y - ancho / 2
        y2 = y + ancho / 2

        bisagra = (x, y1)

        # Jambas
        for py in (y1, y2):

            msp.add_line(
                (x - espesor / 2, py),
                (x + espesor / 2, py),
                dxfattribs={"layer": "PUERTAS"}
            )

        # Hoja abierta
        msp.add_line(
            bisagra,
            (x + signo * ancho, y1),
            dxfattribs={"layer": "PUERTAS"}
        )

        # Arco de apertura
        if signo > 0:
            angulo_inicio = 0
            angulo_fin = 90
        else:
            angulo_inicio = 90
            angulo_fin = 180

        msp.add_arc(
            center=bisagra,
            radius=ancho,
            start_angle=angulo_inicio,
            end_angle=angulo_fin,
            dxfattribs={"layer": "PUERTAS"}
        )

    else:
        raise ValueError(
            f"Orientación de puerta desconocida: {orientacion}"
        )



# ==========================================
# VENTANAS
# ==========================================


def dibujar_ventana(msp, ventana):
    """
    Representación arquitectónica de una ventana:
    - Dos líneas de marco.
    - Dos jambas laterales.
    """

    x, y = ventana["centro"]

    ancho = ventana["ancho"]
    espesor = ventana["espesor_muro"]

    orientacion = ventana["orientacion"]

    if ancho <= 0 or espesor <= 0:
        raise ValueError("Dimensiones de ventana inválidas.")

    desplazamiento = espesor / 4

    # ----------------------------------
    # VENTANA HORIZONTAL
    # ----------------------------------

    if orientacion == "horizontal":

        x1 = x - ancho / 2
        x2 = x + ancho / 2

        # Marcos paralelos
        for desplazamiento_y in (
            -desplazamiento,
            desplazamiento
        ):

            msp.add_line(
                (x1, y + desplazamiento_y),
                (x2, y + desplazamiento_y),
                dxfattribs={"layer": "VENTANAS"}
            )

        # Jambas laterales
        for px in (x1, x2):

            msp.add_line(
                (px, y - espesor / 2),
                (px, y + espesor / 2),
                dxfattribs={"layer": "VENTANAS"}
            )

    # ----------------------------------
    # VENTANA VERTICAL
    # ----------------------------------

    elif orientacion == "vertical":

        y1 = y - ancho / 2
        y2 = y + ancho / 2

        # Marcos paralelos
        for desplazamiento_x in (
            -desplazamiento,
            desplazamiento
        ):

            msp.add_line(
                (x + desplazamiento_x, y1),
                (x + desplazamiento_x, y2),
                dxfattribs={"layer": "VENTANAS"}
            )

        # Jambas laterales
        for py in (y1, y2):

            msp.add_line(
                (x - espesor / 2, py),
                (x + espesor / 2, py),
                dxfattribs={"layer": "VENTANAS"}
            )

    else:
        raise ValueError(
            f"Orientación de ventana desconocida: {orientacion}"
        )
