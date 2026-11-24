from pathlib import Path

import ezdxf
from ezdxf.enums import TextEntityAlignment
from shapely.affinity import translate as shapely_translate
from shapely.geometry import box as shapely_box
from shapely.geometry import (
    Polygon,
    MultiPolygon,
    GeometryCollection
)

from src.cad.dxf_base import APP_ID, UNIDADES_METROS, registrar_metadatos
from src.cad.dxf_aberturas import dibujar_puerta, dibujar_ventana
from src.cad.dxf_mobiliario import (
    agregar_rectangulo,
    agregar_linea,
    agregar_circulo,
    dibujar_simbolo_mueble,
    dibujar_mobiliario,
)


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
    doc.header["$INSUNITS"] = UNIDADES_METROS
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


# ==========================================
# GENERADOR MULTI-PISO
# ==========================================

SEPARACION_PISOS_M = 3.0
ETIQUETAS_DEFAULT = ["PLANTA BAJA", "PLANTA ALTA"]


def _desplazar_mobiliario(resultado_mobiliario, y_offset):
    """Crea una copia del resultado de mobiliario con coordenadas desplazadas."""
    if resultado_mobiliario is None:
        return None
    muebles = [
        {
            **m,
            "y": m["y"] + y_offset,
            "geometria": shapely_translate(m["geometria"], yoff=y_offset),
        }
        for m in resultado_mobiliario["mobiliario"]
    ]
    return {**resultado_mobiliario, "mobiliario": muebles}


def _dibujar_piso(
    msp,
    geometrias,
    geometria_muros,
    resultado_aberturas,
    resultado_mobiliario,
    ancho_m,
    largo_m,
    y_offset,
    label,
):
    """Dibuja un piso completo en el model space con un desplazamiento vertical."""

    # Terreno
    msp.add_lwpolyline(
        [(0, y_offset), (ancho_m, y_offset), (ancho_m, y_offset + largo_m), (0, y_offset + largo_m)],
        close=True,
        dxfattribs={"layer": "TERRENO"},
    )

    # Etiqueta del piso (encima del terreno)
    if label:
        dibujar_texto_centrado(msp, label, ancho_m / 2, y_offset + largo_m + 0.5, 0.5)

    # Mobiliario desplazado (para usar en etiquetas y en dibujo)
    mob_shifted = _desplazar_mobiliario(resultado_mobiliario, y_offset)

    # Ambientes
    for ambiente in geometrias["ambientes"]:
        poly_shifted = shapely_translate(ambiente["poligono"], yoff=y_offset)
        puntos = list(poly_shifted.exterior.coords)[:-1]
        entidad = msp.add_lwpolyline(puntos, close=True, dxfattribs={"layer": "AMBIENTES"})
        registrar_metadatos(entidad, ambiente["id"], ambiente["nombre"])
        ambiente_shifted = {**ambiente, "poligono": poly_shifted}
        dibujar_etiqueta_ambiente(msp, ambiente_shifted, mob_shifted)

    # Muros
    if geometria_muros is not None:
        dibujar_geometria(msp, shapely_translate(geometria_muros, yoff=y_offset), "MUROS")

    # Puertas y ventanas
    if resultado_aberturas is not None:
        for puerta in resultado_aberturas["puertas"]:
            cx, cy = puerta["centro"]
            dibujar_puerta(msp, {**puerta, "centro": (cx, cy + y_offset)})
        for ventana in resultado_aberturas["ventanas"]:
            cx, cy = ventana["centro"]
            dibujar_ventana(msp, {**ventana, "centro": (cx, cy + y_offset)})

    # Mobiliario
    if mob_shifted is not None:
        dibujar_mobiliario(msp, mob_shifted)


def generar_dxf_multipisos(
    pisos,
    ancho_terreno_m,
    largo_terreno_m,
    ruta_salida,
    etiquetas=None,
):
    """
    Genera un DXF con varios pisos apilados verticalmente.

    `pisos` es una lista de dicts con las claves:
        geometrias, resultado_muros, resultado_aberturas, resultado_mobiliario
    Cada piso se dibuja con un desplazamiento en Y de
    (largo_terreno_m + SEPARACION_PISOS_M) por número de piso.
    """

    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = UNIDADES_METROS
    doc.header["$MEASUREMENT"] = 1
    doc.header["$LWDISPLAY"] = 1

    if not doc.appids.has_entry(APP_ID):
        doc.appids.new(APP_ID)

    crear_capas(doc)
    msp = doc.modelspace()

    paso = largo_terreno_m + SEPARACION_PISOS_M

    for i, datos in enumerate(pisos):
        y_offset = i * paso
        label = (etiquetas or ETIQUETAS_DEFAULT + [f"PISO {n + 3}" for n in range(len(pisos))])[i]

        geometrias = datos["geometrias"]
        resultado_aberturas = datos.get("resultado_aberturas")
        resultado_muros = datos.get("resultado_muros")
        resultado_mobiliario = datos.get("resultado_mobiliario")

        if resultado_aberturas is not None:
            geometria_muros = resultado_aberturas["muros_con_aberturas"]
        elif resultado_muros is not None:
            geometria_muros = resultado_muros["todos_los_muros"]
        else:
            geometria_muros = None

        _dibujar_piso(
            msp,
            geometrias,
            geometria_muros,
            resultado_aberturas,
            resultado_mobiliario,
            ancho_terreno_m,
            largo_terreno_m,
            y_offset,
            label,
        )

    archivo = Path(ruta_salida)
    archivo.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(str(archivo))
    return str(archivo)

