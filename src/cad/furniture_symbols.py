
def dibujar_cama(msp, x, y, ancho, largo):
    """Dibuja una cama en vista superior."""

    # Contorno de la cama
    msp.add_lwpolyline(
        [
            (x, y),
            (x + ancho, y),
            (x + ancho, y + largo),
            (x, y + largo),
        ],
        close=True,
        dxfattribs={"layer": "MOBILIARIO"}
    )

    # Cabecera
    altura_cabecera = largo * 0.12

    msp.add_lwpolyline(
        [
            (x, y + largo - altura_cabecera),
            (x + ancho, y + largo - altura_cabecera),
        ],
        dxfattribs={"layer": "MOBILIARIO"}
    )

    # Almohadas
    margen = ancho * 0.08
    separacion = ancho * 0.04
    ancho_almohada = (ancho - 2 * margen - separacion) / 2
    alto_almohada = largo * 0.18

    for i in range(2):
        px = x + margen + i * (ancho_almohada + separacion)
        py = y + largo - altura_cabecera - alto_almohada - largo * 0.04

        msp.add_lwpolyline(
            [
                (px, py),
                (px + ancho_almohada, py),
                (px + ancho_almohada, py + alto_almohada),
                (px, py + alto_almohada),
            ],
            close=True,
            dxfattribs={"layer": "MOBILIARIO"}
        )


def dibujar_sofa(msp, x, y, ancho, largo):
    """Dibuja un sofá en vista superior."""

    # Contorno exterior
    msp.add_lwpolyline(
        [
            (x, y),
            (x + ancho, y),
            (x + ancho, y + largo),
            (x, y + largo),
        ],
        close=True,
        dxfattribs={"layer": "MOBILIARIO"}
    )

    # Respaldo
    profundidad = largo * 0.25

    msp.add_lwpolyline(
        [
            (x, y + largo - profundidad),
            (x + ancho, y + largo - profundidad),
        ],
        dxfattribs={"layer": "MOBILIARIO"}
    )

    # División de asientos
    msp.add_lwpolyline(
        [
            (x + ancho / 2, y),
            (x + ancho / 2, y + largo - profundidad),
        ],
        dxfattribs={"layer": "MOBILIARIO"}
    )


def dibujar_mesa(msp, x, y, ancho, largo):
    """Dibuja una mesa en vista superior."""

    msp.add_lwpolyline(
        [
            (x, y),
            (x + ancho, y),
            (x + ancho, y + largo),
            (x, y + largo),
        ],
        close=True,
        dxfattribs={"layer": "MOBILIARIO"}
    )

    # Línea interior decorativa
    margen = min(ancho, largo) * 0.10

    msp.add_lwpolyline(
        [
            (x + margen, y + margen),
            (x + ancho - margen, y + margen),
            (x + ancho - margen, y + largo - margen),
            (x + margen, y + largo - margen),
        ],
        close=True,
        dxfattribs={"layer": "MOBILIARIO"}
    )


def dibujar_silla(msp, x, y, ancho, largo):
    """Dibuja una silla en vista superior."""

    msp.add_lwpolyline(
        [
            (x, y),
            (x + ancho, y),
            (x + ancho, y + largo),
            (x, y + largo),
        ],
        close=True,
        dxfattribs={"layer": "MOBILIARIO"}
    )

    # Respaldo
    msp.add_lwpolyline(
        [
            (x, y + largo * 0.75),
            (x + ancho, y + largo * 0.75),
        ],
        dxfattribs={"layer": "MOBILIARIO"}
    )


def dibujar_armario(msp, x, y, ancho, largo):
    """Dibuja un armario en vista superior."""

    msp.add_lwpolyline(
        [
            (x, y),
            (x + ancho, y),
            (x + ancho, y + largo),
            (x, y + largo),
        ],
        close=True,
        dxfattribs={"layer": "MOBILIARIO"}
    )

    msp.add_line(
        (x + ancho / 2, y),
        (x + ancho / 2, y + largo),
        dxfattribs={"layer": "MOBILIARIO"}
    )

def dibujar_refrigeradora(msp, x, y, ancho, largo):
    """Dibuja una refrigeradora en vista superior."""

    msp.add_lwpolyline(
        [
            (x, y),
            (x + ancho, y),
            (x + ancho, y + largo),
            (x, y + largo),
        ],
        close=True,
        dxfattribs={"layer": "MOBILIARIO"}
    )

    # División de compartimentos
    msp.add_line(
        (x, y + largo * 0.70),
        (x + ancho, y + largo * 0.70),
        dxfattribs={"layer": "MOBILIARIO"}
    )

    # Tirador
    msp.add_line(
        (x + ancho * 0.85, y + largo * 0.30),
        (x + ancho * 0.85, y + largo * 0.55),
        dxfattribs={"layer": "MOBILIARIO"}
    )


def dibujar_cocina(msp, x, y, ancho, largo):
    """Dibuja una cocina con cuatro quemadores."""

    msp.add_lwpolyline(
        [
            (x, y),
            (x + ancho, y),
            (x + ancho, y + largo),
            (x, y + largo),
        ],
        close=True,
        dxfattribs={"layer": "MOBILIARIO"}
    )

    radio = min(ancho, largo) * 0.13

    posiciones = [
        (x + ancho * 0.30, y + largo * 0.30),
        (x + ancho * 0.70, y + largo * 0.30),
        (x + ancho * 0.30, y + largo * 0.70),
        (x + ancho * 0.70, y + largo * 0.70),
    ]

    for cx, cy in posiciones:
        msp.add_circle(
            (cx, cy),
            radius=radio,
            dxfattribs={"layer": "MOBILIARIO"}
        )


def dibujar_lavatorio(msp, x, y, ancho, largo):
    """Dibuja un lavatorio en vista superior."""

    # Contorno exterior
    msp.add_lwpolyline(
        [
            (x, y),
            (x + ancho, y),
            (x + ancho, y + largo),
            (x, y + largo),
        ],
        close=True,
        dxfattribs={"layer": "MOBILIARIO"}
    )

    # Cubeta
    margen_x = ancho * 0.15
    margen_y = largo * 0.15

    msp.add_ellipse(
        center=(x + ancho / 2, y + largo / 2),
        major_axis=(ancho * 0.30, 0),
        ratio=0.55,
        dxfattribs={"layer": "MOBILIARIO"}
    )

    # Grifo
    msp.add_circle(
        (x + ancho / 2, y + largo * 0.12),
        radius=min(ancho, largo) * 0.035,
        dxfattribs={"layer": "MOBILIARIO"}
    )


def dibujar_inodoro(msp, x, y, ancho, largo):
    """Dibuja un inodoro en vista superior."""

    # Tanque
    tanque_largo = largo * 0.25

    msp.add_lwpolyline(
        [
            (x + ancho * 0.15, y + largo - tanque_largo),
            (x + ancho * 0.85, y + largo - tanque_largo),
            (x + ancho * 0.85, y + largo),
            (x + ancho * 0.15, y + largo),
        ],
        close=True,
        dxfattribs={"layer": "MOBILIARIO"}
    )

    # Taza
    msp.add_ellipse(
        center=(x + ancho / 2, y + largo * 0.38),
        major_axis=(ancho * 0.42, 0),
        ratio=0.65,
        dxfattribs={"layer": "MOBILIARIO"}
    )


def dibujar_ducha(msp, x, y, ancho, largo):
    """Dibuja una ducha en vista superior."""

    # Contorno
    msp.add_lwpolyline(
        [
            (x, y),
            (x + ancho, y),
            (x + ancho, y + largo),
            (x, y + largo),
        ],
        close=True,
        dxfattribs={"layer": "MOBILIARIO"}
    )

    # Desagüe
    msp.add_circle(
        (x + ancho / 2, y + largo / 2),
        radius=min(ancho, largo) * 0.04,
        dxfattribs={"layer": "MOBILIARIO"}
    )

    # Líneas diagonales
    msp.add_line(
        (x, y),
        (x + ancho, y + largo),
        dxfattribs={"layer": "MOBILIARIO"}
    )

    msp.add_line(
        (x + ancho, y),
        (x, y + largo),
        dxfattribs={"layer": "MOBILIARIO"}
    )


def dibujar_lavadora(msp, x, y, ancho, largo):
    """Dibuja una lavadora en vista superior."""

    msp.add_lwpolyline(
        [(x, y), (x + ancho, y), (x + ancho, y + largo), (x, y + largo)],
        close=True,
        dxfattribs={"layer": "MOBILIARIO"},
    )

    radio = min(ancho, largo) * 0.32
    msp.add_circle(
        (x + ancho / 2, y + largo / 2),
        radio,
        dxfattribs={"layer": "MOBILIARIO"},
    )

    msp.add_circle(
        (x + ancho / 2, y + largo / 2),
        radio * 0.45,
        dxfattribs={"layer": "MOBILIARIO"},
    )


def dibujar_secadora(msp, x, y, ancho, largo):
    """Dibuja una secadora en vista superior (igual que lavadora)."""

    msp.add_lwpolyline(
        [(x, y), (x + ancho, y), (x + ancho, y + largo), (x, y + largo)],
        close=True,
        dxfattribs={"layer": "MOBILIARIO"},
    )

    radio = min(ancho, largo) * 0.32
    msp.add_circle(
        (x + ancho / 2, y + largo / 2),
        radio,
        dxfattribs={"layer": "MOBILIARIO"},
    )

    # Rejilla de ventilación: tres líneas horizontales.
    for i in range(1, 4):
        yy = y + largo * (0.15 + i * 0.18)
        msp.add_line(
            (x + ancho * 0.15, yy),
            (x + ancho * 0.85, yy),
            dxfattribs={"layer": "MOBILIARIO"},
        )


def dibujar_tina(msp, x, y, ancho, largo):
    """Dibuja una bañera en vista superior."""

    msp.add_lwpolyline(
        [(x, y), (x + ancho, y), (x + ancho, y + largo), (x, y + largo)],
        close=True,
        dxfattribs={"layer": "MOBILIARIO"},
    )

    msp.add_ellipse(
        center=(x + ancho / 2, y + largo * 0.45),
        major_axis=(ancho * 0.38, 0),
        ratio=0.65,
        dxfattribs={"layer": "MOBILIARIO"},
    )

    # Grifo en la cabecera.
    msp.add_circle(
        (x + ancho / 2, y + largo * 0.88),
        min(ancho, largo) * 0.045,
        dxfattribs={"layer": "MOBILIARIO"},
    )
