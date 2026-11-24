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
from src.utils.texto import normalizar_nombre as _normalizar_nombre
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
# COTAS
# ==========================================

_TICK = 0.14   # tamaño de los ticks de los extremos de la cota


def _tick_extremo(msp, px, py, angulo_grad, capa):
    """Dibuja el tick (flecha diagonal) en el extremo de una línea de cota."""
    import math
    rad = math.radians(angulo_grad)
    dx = _TICK * math.cos(rad)
    dy = _TICK * math.sin(rad)
    msp.add_line((px, py), (px + dx, py + dy), dxfattribs={"layer": capa})
    msp.add_line((px, py), (px - dx, py - dy), dxfattribs={"layer": capa})


def dibujar_cotas(msp, ancho, largo, y_offset=0):
    """
    Anota las dimensiones del terreno junto al plano.

    Dibuja una cota horizontal (ancho) debajo del terreno y una cota
    vertical (largo) a la derecha.
    """
    capa = "TEXTOS"
    ext = 0.30   # extensión de la línea de proyección más allá de la cota
    sep = 0.80   # separación de la línea de cota al borde del terreno

    # ---- Cota horizontal (ancho) ----
    y_cota = y_offset - sep

    msp.add_line((0, y_offset), (0, y_cota - ext), dxfattribs={"layer": capa})
    msp.add_line((ancho, y_offset), (ancho, y_cota - ext), dxfattribs={"layer": capa})
    msp.add_line((0, y_cota), (ancho, y_cota), dxfattribs={"layer": capa})
    _tick_extremo(msp, 0, y_cota, 45, capa)
    _tick_extremo(msp, ancho, y_cota, 45, capa)

    texto_h = msp.add_text(
        f"{ancho:.2f} m",
        dxfattribs={"layer": capa, "height": 0.25},
    )
    texto_h.set_placement(
        (ancho / 2, y_cota + 0.08),
        align=TextEntityAlignment.BOTTOM_CENTER,
    )

    # ---- Cota vertical (largo) ----
    x_cota = ancho + sep

    msp.add_line((ancho, y_offset), (x_cota + ext, y_offset), dxfattribs={"layer": capa})
    msp.add_line((ancho, y_offset + largo), (x_cota + ext, y_offset + largo), dxfattribs={"layer": capa})
    msp.add_line((x_cota, y_offset), (x_cota, y_offset + largo), dxfattribs={"layer": capa})
    _tick_extremo(msp, x_cota, y_offset, 135, capa)
    _tick_extremo(msp, x_cota, y_offset + largo, 135, capa)

    texto_v = msp.add_text(
        f"{largo:.2f} m",
        dxfattribs={"layer": capa, "height": 0.25, "rotation": 90},
    )
    texto_v.set_placement(
        (x_cota + 0.08, y_offset + largo / 2),
        align=TextEntityAlignment.BOTTOM_CENTER,
    )


# ==========================================
# CUADRO DE ÁREAS
# ==========================================

_COL_NOMBRE = 3.8
_COL_AREA = 1.6
_COL_DIMS = 2.4
_ROW_H = 0.55


def dibujar_cuadro_areas(msp, ambientes, x_inicio, y_inicio):
    """
    Dibuja un cuadro de áreas a la derecha del plano.

    `ambientes`: lista de dicts con al menos {nombre, poligono} y
    opcionalmente {area_m2}.
    `(x_inicio, y_inicio)`: esquina superior izquierda del cuadro.
    """
    capa = "TEXTOS"
    total_w = _COL_NOMBRE + _COL_AREA + _COL_DIMS
    n_filas = len(ambientes) + 3   # título + cabeceras + datos + total
    total_h = n_filas * _ROW_H

    # Borde exterior
    msp.add_lwpolyline(
        [
            (x_inicio, y_inicio - total_h),
            (x_inicio + total_w, y_inicio - total_h),
            (x_inicio + total_w, y_inicio),
            (x_inicio, y_inicio),
        ],
        close=True,
        dxfattribs={"layer": capa},
    )

    y = y_inicio

    # --- Fila de título ---
    dibujar_texto_centrado(msp, "CUADRO DE ÁREAS", x_inicio + total_w / 2, y - _ROW_H / 2, 0.22, capa)
    y -= _ROW_H
    msp.add_line((x_inicio, y), (x_inicio + total_w, y), dxfattribs={"layer": capa})

    # --- Cabeceras de columna ---
    _celda_texto(msp, "AMBIENTE", x_inicio, y, _COL_NOMBRE, _ROW_H, 0.20, capa)
    _celda_texto(msp, "M²", x_inicio + _COL_NOMBRE, y, _COL_AREA, _ROW_H, 0.20, capa)
    _celda_texto(msp, "DIM. (m)", x_inicio + _COL_NOMBRE + _COL_AREA, y, _COL_DIMS, _ROW_H, 0.20, capa)
    y -= _ROW_H
    msp.add_line((x_inicio, y), (x_inicio + total_w, y), dxfattribs={"layer": capa})

    # Separadores de columna (tramo cabeceras)
    for xsep in (x_inicio + _COL_NOMBRE, x_inicio + _COL_NOMBRE + _COL_AREA):
        msp.add_line((xsep, y_inicio - _ROW_H), (xsep, y_inicio - 2 * _ROW_H), dxfattribs={"layer": capa})

    # --- Filas de datos ---
    total_area = 0.0
    for amb in sorted(ambientes, key=lambda a: a["nombre"]):
        area = amb.get("area_m2", amb["poligono"].area)
        total_area += area
        xmin, ymin, xmax, ymax = amb["poligono"].bounds
        dims = f"{(xmax - xmin):.1f}×{(ymax - ymin):.1f}"   # × unicode

        _celda_texto(msp, amb["nombre"][:22], x_inicio, y, _COL_NOMBRE, _ROW_H, 0.18, capa, alinear="izquierda")
        _celda_texto(msp, f"{area:.2f}", x_inicio + _COL_NOMBRE, y, _COL_AREA, _ROW_H, 0.18, capa)
        _celda_texto(msp, dims, x_inicio + _COL_NOMBRE + _COL_AREA, y, _COL_DIMS, _ROW_H, 0.18, capa)
        y -= _ROW_H

    # --- Fila de total ---
    msp.add_line((x_inicio, y), (x_inicio + total_w, y), dxfattribs={"layer": capa})
    _celda_texto(msp, "TOTAL", x_inicio, y, _COL_NOMBRE, _ROW_H, 0.20, capa)
    _celda_texto(msp, f"{total_area:.2f}", x_inicio + _COL_NOMBRE, y, _COL_AREA, _ROW_H, 0.20, capa)

    # Separadores de columna (tramo datos + total)
    for xsep in (x_inicio + _COL_NOMBRE, x_inicio + _COL_NOMBRE + _COL_AREA):
        msp.add_line((xsep, y_inicio - 2 * _ROW_H), (xsep, y), dxfattribs={"layer": capa})


def _celda_texto(msp, contenido, x_col, y_fila, ancho_col, alto_fila, altura_texto, capa, alinear="centro"):
    if alinear == "izquierda":
        texto = msp.add_text(str(contenido), dxfattribs={"layer": capa, "height": altura_texto})
        texto.set_placement((x_col + 0.12, y_fila - alto_fila / 2), align=TextEntityAlignment.MIDDLE_LEFT)
    else:
        dibujar_texto_centrado(msp, contenido, x_col + ancho_col / 2, y_fila - alto_fila / 2, altura_texto, capa)


# ==========================================
# ESCALERA
# ==========================================

_ALTO_PELDAN_M = 0.17  # altura estándar de un peldaño (m)


def dibujar_escalera(msp, poligono):
    """
    Dibuja el patrón de peldaños de una escalera dentro de su polígono.
    Los peldaños se representan como líneas horizontales equidistantes.
    """
    xmin, ymin, xmax, ymax = poligono.bounds
    alto = ymax - ymin
    n_peldanos = max(3, round(alto / _ALTO_PELDAN_M))
    paso = alto / n_peldanos

    for i in range(1, n_peldanos):
        y = ymin + i * paso
        msp.add_line(
            (xmin + 0.05, y),
            (xmax - 0.05, y),
            dxfattribs={"layer": "AMBIENTES"},
        )

    # Flecha central indicando sentido de subida.
    xc = (xmin + xmax) / 2
    msp.add_line(
        (xc, ymin + 0.10),
        (xc, ymax - 0.10),
        dxfattribs={"layer": "AMBIENTES"},
    )


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

        if _normalizar_nombre(ambiente["nombre"]).startswith("escalera"):
            dibujar_escalera(msp, poligono)

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
    # COTAS Y CUADRO DE ÁREAS
    # --------------------------------------

    dibujar_cotas(msp, ancho_terreno_m, largo_terreno_m)

    x_cuadro = ancho_terreno_m + 2.0
    dibujar_cuadro_areas(
        msp,
        resultado_geometrias["ambientes"],
        x_cuadro,
        largo_terreno_m,
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
        if _normalizar_nombre(ambiente["nombre"]).startswith("escalera"):
            dibujar_escalera(msp, poly_shifted)

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

    # Cotas del terreno de este piso
    dibujar_cotas(msp, ancho_m, largo_m, y_offset)


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

    todos_ambientes = []

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

        for amb in geometrias["ambientes"]:
            todos_ambientes.append(
                {**amb, "poligono": shapely_translate(amb["poligono"], yoff=y_offset)}
            )

    # Cuadro de áreas agregado de todos los pisos
    alto_total = (len(pisos) - 1) * paso + largo_terreno_m
    dibujar_cuadro_areas(
        msp,
        todos_ambientes,
        ancho_terreno_m + 2.0,
        alto_total,
    )

    archivo = Path(ruta_salida)
    archivo.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(str(archivo))
    return str(archivo)

