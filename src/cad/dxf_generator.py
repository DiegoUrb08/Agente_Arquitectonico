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

from shapely.geometry import box as shapely_box

from pathlib import Path

import ezdxf
from ezdxf.enums import TextEntityAlignment

from shapely.geometry import (
    Polygon,
    MultiPolygon,
    GeometryCollection
)


APP_ID = "AGENTE_ARQ"


# ==========================================
# CONFIGURACIÓN GRÁFICA
# ==========================================

def crear_capas(doc):
    """
    Crea las capas con una jerarquía gráfica
    apropiada para un plano arquitectónico.
    
    Los grosores se expresan en centésimas
    de milímetro.
    """

    capas = {
        "TERRENO": {
            "color": 7,
            "lineweight": 25,
        },
        "AMBIENTES": {
            "color": 8,
            "lineweight": 9,
        },
        "MUROS": {
            "color": 7,
            "lineweight": 50,
        },
        "TEXTOS": {
            "color": 2,
            "lineweight": 18,
        },
        "PUERTAS": {
            "color": 1,
            "lineweight": 25,
        },
        "VENTANAS": {
            "color": 4,
            "lineweight": 25,
        },
        "MOBILIARIO": {
            "color": 6,
            "lineweight": 18,
        },
    }

    for nombre, propiedades in capas.items():

        atributos = {
            "color": propiedades["color"],
            "lineweight": propiedades["lineweight"],
        }

        if nombre not in doc.layers:

            doc.layers.new(
                name=nombre,
                dxfattribs=atributos
            )

        else:

            capa = doc.layers.get(nombre)

            capa.dxf.color = propiedades["color"]
            capa.dxf.lineweight = propiedades["lineweight"]


# ==========================================
# METADATOS
# ==========================================

def registrar_metadatos(
    entidad,
    identificador,
    nombre
):
    """Guarda información mediante XDATA."""

    entidad.set_xdata(
        APP_ID,
        [
            (1000, str(identificador)),
            (1000, str(nombre)),
        ]
    )


# ==========================================
# GEOMETRÍAS
# ==========================================

def obtener_poligonos(geometria):
    """
    Extrae los polígonos de una geometría Shapely.
    """

    if geometria is None or geometria.is_empty:
        return []

    if isinstance(geometria, Polygon):
        return [geometria]

    if isinstance(
        geometria,
        (MultiPolygon, GeometryCollection)
    ):

        resultado = []

        for elemento in geometria.geoms:

            resultado.extend(
                obtener_poligonos(elemento)
            )

        return resultado

    return []


def dibujar_geometria(
    msp,
    geometria,
    capa
):
    """
    Dibuja los contornos de una geometría
    y devuelve las entidades creadas.
    """

    entidades = []

    for poligono in obtener_poligonos(geometria):

        puntos_exteriores = list(
            poligono.exterior.coords
        )[:-1]

        entidad = msp.add_lwpolyline(
            puntos_exteriores,
            close=True,
            dxfattribs={
                "layer": capa
            }
        )

        entidades.append(entidad)

        for anillo in poligono.interiors:

            puntos_interiores = list(
                anillo.coords
            )[:-1]

            entidad = msp.add_lwpolyline(
                puntos_interiores,
                close=True,
                dxfattribs={
                    "layer": capa
                }
            )

            entidades.append(entidad)

    return entidades


# ==========================================
# TEXTOS Y ETIQUETAS
# ==========================================

def dibujar_texto_centrado(
    msp,
    contenido,
    x,
    y,
    altura,
    capa="TEXTOS"
):
    """
    Crea un texto centrado en una posición.
    """

    texto = msp.add_text(
        str(contenido),
        dxfattribs={
            "layer": capa,
            "height": altura,
        }
    )

    texto.set_placement(
        (x, y),
        align=TextEntityAlignment.MIDDLE_CENTER
    )

    return texto




def dibujar_etiqueta_ambiente(
    msp,
    ambiente,
    resultado_mobiliario=None
):
    """
    Posiciona las etiquetas dentro de una zona segura,
    evitando paredes y mobiliario.
    """

    poligono = ambiente["poligono"]
    nombre = ambiente["nombre"]

    area = ambiente.get(
        "area_m2",
        poligono.area
    )

    min_x, min_y, max_x, max_y = poligono.bounds

    ancho = max_x - min_x
    largo = max_y - min_y

    centro = poligono.centroid

    # --------------------------------------
    # ZONA SEGURA: SEPARACIÓN DE LAS PAREDES
    # --------------------------------------

    margen_pared = min(
        0.20,
        ancho * 0.08,
        largo * 0.08
    )

    zona_segura = poligono.buffer(-margen_pared)

    if zona_segura.is_empty:
        zona_segura = poligono

    # --------------------------------------
    # OBTENER OBSTÁCULOS
    # --------------------------------------

    obstaculos = []

    if resultado_mobiliario is not None:

        for mueble in resultado_mobiliario["mobiliario"]:

            if (
                mueble["ambiente"].strip().lower()
                == nombre.strip().lower()
            ):
                obstaculos.append(
                    mueble["geometria"]
                )

    # --------------------------------------
    # TAMAÑO DE TEXTO
    # --------------------------------------

    texto_nombre = nombre.upper()
    texto_area = f"{area:.2f} m2"

    altura_nombre = min(
        0.20,
        ancho * 0.75 / (len(texto_nombre) * 0.65)
    )

    altura_nombre = max(
        0.07,
        altura_nombre
    )

    altura_area = altura_nombre * 0.70

    # Separación vertical entre las dos líneas.
    separacion_textos = altura_nombre * 0.40

    # Estimación del ancho total de la etiqueta.
    ancho_texto = max(
        len(texto_nombre) * altura_nombre * 0.65,
        len(texto_area) * altura_area * 0.65
    )

    alto_texto = (
        altura_nombre
        + altura_area
        + separacion_textos
    )

    # --------------------------------------
    # BUSCAR POSICIÓN DISPONIBLE
    # --------------------------------------

    posiciones = []

    proporciones = [
        0.20,
        0.35,
        0.50,
        0.65,
        0.80
    ]

    for px in proporciones:

        for py in proporciones:

            x = min_x + ancho * px
            y = min_y + largo * py

            rectangulo_texto = shapely_box(
                x - ancho_texto / 2,
                y - alto_texto / 2,
                x + ancho_texto / 2,
                y + alto_texto / 2
            )

            # Comprobar distancia a las paredes.
            if not zona_segura.covers(rectangulo_texto):
                continue

            # Comprobar distancia a los muebles.
            distancias = [
                rectangulo_texto.distance(obstaculo)
                for obstaculo in obstaculos
            ]

            distancia_minima = (
                min(distancias)
                if distancias
                else 999
            )

            distancia_centro = (
                (x - centro.x) ** 2
                + (y - centro.y) ** 2
            ) ** 0.5

            puntuacion = (
                distancia_minima
                - distancia_centro * 0.10
            )

            posiciones.append(
                (puntuacion, x, y)
            )

    # --------------------------------------
    # SELECCIONAR POSICIÓN
    # --------------------------------------

    if posiciones:

        posiciones.sort(
            key=lambda posicion: posicion[0],
            reverse=True
        )

        _, x, y = posiciones[0]

    else:

        punto = zona_segura.representative_point()

        x = punto.x
        y = punto.y

    # --------------------------------------
    # CALCULAR POSICIONES VERTICALES
    # --------------------------------------

    desplazamiento = (
        altura_nombre / 2
        + separacion_textos / 2
    )

    y_nombre = y + desplazamiento
    y_area = y - (
        altura_area / 2
        + separacion_textos / 2
    )

    # --------------------------------------
    # DIBUJAR ETIQUETAS
    # --------------------------------------

    entidad_nombre = dibujar_texto_centrado(
        msp,
        texto_nombre,
        x,
        y_nombre,
        altura_nombre
    )

    entidad_area = dibujar_texto_centrado(
        msp,
        texto_area,
        x,
        y_area,
        altura_area
    )

    # --------------------------------------
    # REGISTRAR METADATOS
    # --------------------------------------

    registrar_metadatos(
        entidad_nombre,
        ambiente["id"],
        nombre
    )

    registrar_metadatos(
        entidad_area,
        ambiente["id"],
        nombre
    )




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


# ==========================================
# GENERADOR PRINCIPAL
# ==========================================

def generar_dxf_desde_geometrias(
    resultado_geometrias,
    ancho_terreno_m,
    largo_terreno_m,
    ruta_salida,
    resultado_muros=None,
    resultado_aberturas=None,
    resultado_mobiliario=None
):
    """
    Exporta un plano arquitectónico DXF
    con capas, etiquetas y jerarquía gráfica.
    """

    # --------------------------------------
    # VALIDAR GEOMETRÍAS
    # --------------------------------------

    if not resultado_geometrias["valido"]:

        raise ValueError(
            f"Geometrías inválidas: "
            f"{resultado_geometrias['errores']}"
        )

    if resultado_aberturas is not None:

        geometria_muros = resultado_aberturas[
            "muros_con_aberturas"
        ]

    elif resultado_muros is not None:

        geometria_muros = resultado_muros[
            "todos_los_muros"
        ]

    else:

        geometria_muros = None

    # --------------------------------------
    # CREAR DOCUMENTO
    # --------------------------------------

    doc = ezdxf.new("R2010")

    # Unidades métricas
    doc.header["$INSUNITS"] = 6
    doc.header["$MEASUREMENT"] = 1
    doc.header["$LWDISPLAY"] = 1

    if not doc.appids.has_entry(APP_ID):
        doc.appids.new(APP_ID)

    crear_capas(doc)

    msp = doc.modelspace()

    # --------------------------------------
    # TERRENO
    # --------------------------------------

    puntos_terreno = [
        (0, 0),
        (ancho_terreno_m, 0),
        (ancho_terreno_m, largo_terreno_m),
        (0, largo_terreno_m),
    ]

    msp.add_lwpolyline(
        puntos_terreno,
        close=True,
        dxfattribs={
            "layer": "TERRENO"
        }
    )

    # --------------------------------------
    # AMBIENTES Y ETIQUETAS
    # --------------------------------------

    for ambiente in resultado_geometrias["ambientes"]:

        poligono = ambiente["poligono"]

        puntos = list(
            poligono.exterior.coords
        )[:-1]

        entidad = msp.add_lwpolyline(
            puntos,
            close=True,
            dxfattribs={
                "layer": "AMBIENTES"
            }
        )

        registrar_metadatos(
            entidad,
            ambiente["id"],
            ambiente["nombre"]
        )

        dibujar_etiqueta_ambiente(
            msp,
            ambiente,
            resultado_mobiliario
        )

    # --------------------------------------
    # MUROS
    # --------------------------------------

    if geometria_muros is not None:

        dibujar_geometria(
            msp,
            geometria_muros,
            "MUROS"
        )

    # --------------------------------------
    # PUERTAS Y VENTANAS
    # --------------------------------------

    if resultado_aberturas is not None:

        for puerta in resultado_aberturas["puertas"]:

            dibujar_puerta(
                msp,
                puerta
            )

        for ventana in resultado_aberturas["ventanas"]:

            dibujar_ventana(
                msp,
                ventana
            )

    # --------------------------------------
    # MOBILIARIO
    # --------------------------------------

    dibujar_mobiliario(
        msp,
        resultado_mobiliario
    )

    # --------------------------------------
    # GUARDAR ARCHIVO
    # --------------------------------------

    archivo = Path(ruta_salida)

    archivo.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    doc.saveas(str(archivo))

    return str(archivo)
