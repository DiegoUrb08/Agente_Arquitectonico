"""Símbolos DXF de mobiliario."""

from src.cad.furniture_symbols import (
    dibujar_cama,
    dibujar_sofa,
    dibujar_mesa,
    dibujar_silla,
    dibujar_armario,
    dibujar_refrigeradora,
    dibujar_cocina,
    dibujar_lavatorio,
    dibujar_inodoro,
    dibujar_ducha,
)
from src.cad.dxf_base import registrar_metadatos


# ==========================================
# MOBILIARIO
# ==========================================

def agregar_rectangulo(msp, x1, y1, x2, y2):
    """Dibuja un rectángulo cerrado."""
    return msp.add_lwpolyline(
        [
            (x1, y1),
            (x2, y1),
            (x2, y2),
            (x1, y2)
        ],
        close=True,
        dxfattribs={"layer": "MOBILIARIO"}
    )


def agregar_linea(msp, x1, y1, x2, y2):
    """Dibuja una línea de mobiliario."""
    return msp.add_line(
        (x1, y1),
        (x2, y2),
        dxfattribs={"layer": "MOBILIARIO"}
    )


def agregar_circulo(msp, x, y, radio):
    """Dibuja un círculo de mobiliario."""
    return msp.add_circle(
        (x, y),
        radio,
        dxfattribs={"layer": "MOBILIARIO"}
    )


def dibujar_simbolo_mueble(msp, mueble):
    """
    Genera el símbolo arquitectónico correspondiente
    al tipo de mobiliario.

    Todas las dimensiones están expresadas en metros.
    """

    x = mueble["x"]
    y = mueble["y"]
    ancho = mueble["ancho"]
    largo = mueble["largo"]
    tipo = mueble["tipo"]

    entidades = []

    # Función local para dibujar rectángulos.
    def rect(x1, y1, x2, y2):
        entidades.append(
            agregar_rectangulo(msp, x1, y1, x2, y2)
        )

    # Función local para dibujar líneas.
    def linea(x1, y1, x2, y2):
        entidades.append(
            agregar_linea(msp, x1, y1, x2, y2)
        )

    # Función local para dibujar círculos.
    def circulo(cx, cy, radio):
        entidades.append(
            agregar_circulo(msp, cx, cy, radio)
        )

    # -------------------------------------------------
    # CAMAS
    # -------------------------------------------------

    if tipo in [
        "cama_individual",
        "cama_matrimonial",
        "cama_queen"
    ]:

        # Contorno de la cama.
        rect(x, y, x + ancho, y + largo)

        # Cabecera.
        altura_cabecera = largo * 0.09

        rect(
            x + ancho * 0.04,
            y + largo - altura_cabecera,
            x + ancho * 0.96,
            y + largo - largo * 0.02
        )

        # Almohadas.
        separacion = ancho * 0.04
        ancho_almohada = (ancho - 3 * separacion) / 2

        y_almohada = y + largo * 0.70
        alto_almohada = largo * 0.19

        rect(
            x + separacion,
            y_almohada,
            x + separacion + ancho_almohada,
            y_almohada + alto_almohada
        )

        rect(
            x + 2 * separacion + ancho_almohada,
            y_almohada,
            x + 2 * separacion + 2 * ancho_almohada,
            y_almohada + alto_almohada
        )

        # Línea que representa la zona de cobertores.
        linea(
            x + ancho * 0.04,
            y + largo * 0.65,
            x + ancho * 0.96,
            y + largo * 0.65
        )

    # -------------------------------------------------
    # SOFÁ
    # -------------------------------------------------

    elif tipo == "sofa":

        rect(x, y, x + ancho, y + largo)

        # Brazos laterales.
        brazo = ancho * 0.10

        rect(
            x,
            y,
            x + brazo,
            y + largo
        )

        rect(
            x + ancho - brazo,
            y,
            x + ancho,
            y + largo
        )

        # Respaldo.
        rect(
            x + brazo,
            y + largo * 0.78,
            x + ancho - brazo,
            y + largo
        )

        # Cojines.
        cantidad_cojines = 2
        espacio = ancho * 0.04
        ancho_cojin = (
            ancho - 2 * brazo - 3 * espacio
        ) / cantidad_cojines

        for i in range(cantidad_cojines):

            cx = (
                x + brazo + espacio
                + i * (ancho_cojin + espacio)
            )

            rect(
                cx,
                y + largo * 0.12,
                cx + ancho_cojin,
                y + largo * 0.70
            )

    # -------------------------------------------------
    # MESA DE COMEDOR
    # -------------------------------------------------

    elif tipo == "mesa_comedor":

        rect(x, y, x + ancho, y + largo)

        # Borde interior de la superficie.
        rect(
            x + ancho * 0.06,
            y + largo * 0.06,
            x + ancho * 0.94,
            y + largo * 0.94
        )

        # Eje central.
        linea(
            x + ancho / 2,
            y + largo * 0.06,
            x + ancho / 2,
            y + largo * 0.94
        )

    # -------------------------------------------------
    # SILLAS
    # -------------------------------------------------

    elif tipo == "silla":

        rect(x, y, x + ancho, y + largo)

        # Superficie del asiento.
        rect(
            x + ancho * 0.12,
            y + largo * 0.12,
            x + ancho * 0.88,
            y + largo * 0.75
        )

        # Respaldo.
        linea(
            x + ancho * 0.08,
            y + largo * 0.88,
            x + ancho * 0.92,
            y + largo * 0.88
        )

    # -------------------------------------------------
    # ESCRITORIO
    # -------------------------------------------------

    elif tipo == "escritorio":

        rect(x, y, x + ancho, y + largo)

        # Superficie de trabajo.
        rect(
            x + ancho * 0.05,
            y + largo * 0.05,
            x + ancho * 0.95,
            y + largo * 0.95
        )

        # Representación de un espacio para accesorios.
        rect(
            x + ancho * 0.10,
            y + largo * 0.70,
            x + ancho * 0.35,
            y + largo * 0.88
        )

    # -------------------------------------------------
    # REFRIGERADORA
    # -------------------------------------------------

    elif tipo == "refrigeradora":

        rect(x, y, x + ancho, y + largo)

        # División de compartimentos.
        linea(
            x + ancho * 0.05,
            y + largo * 0.65,
            x + ancho * 0.95,
            y + largo * 0.65
        )

        # Tiradores.
        linea(
            x + ancho * 0.85,
            y + largo * 0.35,
            x + ancho * 0.85,
            y + largo * 0.58
        )

        linea(
            x + ancho * 0.85,
            y + largo * 0.75,
            x + ancho * 0.85,
            y + largo * 0.90
        )

    # -------------------------------------------------
    # COCINA
    # -------------------------------------------------

    elif tipo == "cocina":

        rect(x, y, x + ancho, y + largo)

        # Cuatro quemadores.
        posiciones = [
            (0.30, 0.30),
            (0.70, 0.30),
            (0.30, 0.70),
            (0.70, 0.70)
        ]

        radio = min(ancho, largo) * 0.12

        for px, py in posiciones:
            circulo(
                x + ancho * px,
                y + largo * py,
                radio
            )

    # -------------------------------------------------
    # LAVATORIO
    # -------------------------------------------------

    elif tipo == "lavatorio":

        rect(x, y, x + ancho, y + largo)

        # Cubeta.
        circulo(
            x + ancho / 2,
            y + largo / 2,
            min(ancho, largo) * 0.27
        )

        # Grifo.
        circulo(
            x + ancho / 2,
            y + largo * 0.83,
            min(ancho, largo) * 0.045
        )

    # -------------------------------------------------
    # INODORO
    # -------------------------------------------------

    elif tipo == "inodoro":

        # Depósito posterior.
        rect(
            x + ancho * 0.15,
            y + largo * 0.78,
            x + ancho * 0.85,
            y + largo
        )

        # Taza.
        entidades.append(
            msp.add_ellipse(
                center=(
                    x + ancho / 2,
                    y + largo * 0.38
                ),
                major_axis=(ancho * 0.42, 0),
                ratio=0.65,
                dxfattribs={"layer": "MOBILIARIO"}
            )
        )

        # Contorno interior de la taza.
        entidades.append(
            msp.add_ellipse(
                center=(
                    x + ancho / 2,
                    y + largo * 0.38
                ),
                major_axis=(ancho * 0.25, 0),
                ratio=0.65,
                dxfattribs={"layer": "MOBILIARIO"}
            )
        )

    # -------------------------------------------------
    # DUCHA
    # -------------------------------------------------

    elif tipo == "ducha":

        rect(x, y, x + ancho, y + largo)

        # Diagonales de la zona de ducha.
        linea(
            x + ancho * 0.08,
            y + largo * 0.08,
            x + ancho * 0.92,
            y + largo * 0.92
        )

        linea(
            x + ancho * 0.08,
            y + largo * 0.92,
            x + ancho * 0.92,
            y + largo * 0.08
        )

        # Desagüe.
        circulo(
            x + ancho / 2,
            y + largo / 2,
            min(ancho, largo) * 0.045
        )

    # -------------------------------------------------
    # ARMARIO
    # -------------------------------------------------

    elif tipo == "armario":

        rect(x, y, x + ancho, y + largo)

        # División de puertas.
        linea(
            x + ancho / 2,
            y,
            x + ancho / 2,
            y + largo
        )

        # Tiradores.
        circulo(
            x + ancho * 0.43,
            y + largo / 2,
            min(ancho, largo) * 0.025
        )

        circulo(
            x + ancho * 0.57,
            y + largo / 2,
            min(ancho, largo) * 0.025
        )

    # -------------------------------------------------
    # OTROS TIPOS
    # -------------------------------------------------

    else:

        # Representación genérica para futuros muebles.
        rect(x, y, x + ancho, y + largo)

    return entidades





def dibujar_mobiliario(
    msp,
    resultado_mobiliario
):
    """
    Dibuja el mobiliario como bloques reutilizables
    de AutoCAD y registra sus metadatos.
    """

    if resultado_mobiliario is None:
        return

    if not resultado_mobiliario["valido"]:
        raise ValueError(
            "El mobiliario contiene errores. "
            "No se puede exportar."
        )

    simbolos = {
        "cama_individual": dibujar_cama,
        "cama_matrimonial": dibujar_cama,
        "cama_queen": dibujar_cama,
        "sofa": dibujar_sofa,
        "mesa_comedor": dibujar_mesa,
        "silla": dibujar_silla,
        "escritorio": dibujar_mesa,
        "armario": dibujar_armario,
        "refrigeradora": dibujar_refrigeradora,
        "cocina": dibujar_cocina,
        "lavatorio": dibujar_lavatorio,
        "inodoro": dibujar_inodoro,
        "ducha": dibujar_ducha,
    }

    doc = msp.doc

    for indice, mueble in enumerate(
        resultado_mobiliario["mobiliario"]
    ):

        tipo = mueble["tipo"]

        if tipo not in simbolos:
            raise ValueError(
                f"No existe un símbolo CAD "
                f"para el mobiliario: {tipo}"
            )

        x = float(mueble["x"])
        y = float(mueble["y"])
        ancho = float(mueble["ancho"])
        largo = float(mueble["largo"])

        # Nombre único según tipo y dimensiones.
        nombre_bloque = (
            f"MUEBLE_{tipo.upper()}_"
            f"{ancho:.3f}_{largo:.3f}"
        ).replace(".", "_")

        # Crear la definición solamente si no existe.
        if nombre_bloque not in doc.blocks:

            bloque = doc.blocks.new(
                name=nombre_bloque
            )

            # Dibujar el símbolo respecto al origen (0, 0).
            simbolos[tipo](
                bloque,
                0,
                0,
                ancho,
                largo
            )

        # Insertar el bloque en el plano.
        insercion = msp.add_blockref(
            nombre_bloque,
            insert=(x, y),
            dxfattribs={
                "layer": "MOBILIARIO"
            }
        )

        # Registrar metadatos sobre el bloque completo.
        registrar_metadatos(
            insercion,
            f"mueble_{indice}",
            tipo
        )
