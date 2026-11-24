from pathlib import Path

import ezdxf

from shapely.geometry import Polygon, box

from src.cad.dxf_base import (
    APP_ID,
    CAPA_AMBIENTES,
    CAPA_TERRENO,
    CAPA_TEXTOS,
    UNIDADES_METROS,
)
from src.utils.texto import normalizar_nombre


TOLERANCIA = 1e-6
PASO_BUSQUEDA_M = 0.1


# ==========================================
# 1. FUNCIONES AUXILIARES
# ==========================================

def _xdata(entidad):

    if not entidad.has_xdata(APP_ID):
        return None

    datos = entidad.get_xdata(APP_ID)

    # XDATA = [identificador, nombre] (ver registrar_metadatos).
    if not datos or len(datos) < 2:
        return None

    return str(datos[0].value), str(datos[1].value)


def obtener_nombre(entidad):

    """
    Recupera el nombre del ambiente guardado
    en los metadatos XDATA.
    """

    datos = _xdata(entidad)

    return datos[1] if datos else None


def obtener_id(entidad):

    """
    Recupera el identificador del ambiente (p. ej. dormitorio_2).
    """

    datos = _xdata(entidad)

    return datos[0] if datos else None


def obtener_poligono(entidad):

    """
    Convierte una polilinea cerrada en un poligono Shapely.
    """

    if not entidad.closed:
        raise ValueError(
            "Se encontro una polilinea de ambiente abierta."
        )

    puntos = [
        (punto[0], punto[1])
        for punto in entidad.get_points("xy")
    ]

    poligono = Polygon(puntos)

    if not poligono.is_valid or poligono.area <= 0:
        raise ValueError(
            "El ambiente contiene una geometria invalida."
        )

    return poligono


def obtener_ambientes(modelo):

    """
    Recupera los ambientes identificados en el DXF.
    """

    ambientes = []

    for entidad in modelo.query("LWPOLYLINE"):

        if entidad.dxf.layer != CAPA_AMBIENTES:
            continue

        nombre = obtener_nombre(entidad)

        if not nombre:
            continue

        poligono = obtener_poligono(entidad)

        ambientes.append({
            "entidad": entidad,
            "id": obtener_id(entidad),
            "nombre": nombre,
            "poligono": poligono
        })

    return ambientes


def obtener_terreno(modelo):

    """
    Busca el poligono que representa el terreno.
    """

    for entidad in modelo.query("LWPOLYLINE"):

        if entidad.dxf.layer != CAPA_TERRENO:
            continue

        if not entidad.closed:
            continue

        puntos = [
            (punto[0], punto[1])
            for punto in entidad.get_points("xy")
        ]

        terreno = Polygon(puntos)

        if terreno.is_valid and terreno.area > 0:
            return terreno

    raise ValueError(
        "No se encontro un terreno valido en el DXF."
    )


def resolver_ambiente(ambientes, referencia):

    """
    Encuentra un ambiente a partir de lo que escribio el usuario.

    Acepta el identificador ("dormitorio_2"), el nombre unico
    ("sala"), o el nombre con numero ("dormitorio 2"). Ignora
    mayusculas y tildes.
    """

    clave = normalizar_nombre(referencia)
    clave_id = clave.replace(" ", "_")

    por_id = [
        a for a in ambientes
        if a["id"] and normalizar_nombre(a["id"]) == clave_id
    ]

    if len(por_id) == 1:
        return por_id[0]

    por_nombre = [
        a for a in ambientes
        if normalizar_nombre(a["nombre"]) == clave
    ]

    if len(por_nombre) == 1:
        return por_nombre[0]

    if len(por_nombre) > 1:
        ids = ", ".join(a["id"] or a["nombre"] for a in por_nombre)
        raise ValueError(
            f"El nombre {referencia} es ambiguo. "
            f"Indica cual de estos ambientes: {ids}."
        )

    raise ValueError(
        f"No se encontro el ambiente: {referencia}."
    )


def buscar_textos(modelo, ambiente):

    """
    Devuelve las etiquetas (nombre y area) del ambiente,
    identificadas por su id en los metadatos.
    """

    etiquetas = []

    for entidad in modelo.query("TEXT"):

        if entidad.dxf.layer != CAPA_TEXTOS:
            continue

        if obtener_id(entidad) == ambiente["id"]:
            etiquetas.append(entidad)

    return etiquetas


def _es_etiqueta_area(texto):
    return texto.dxf.text.strip().lower().endswith("m2")


def _comprobar_ubicacion(candidato, ambiente, ambientes, terreno):

    """
    Devuelve None si el poligono es valido, o un mensaje de error.
    """

    if not terreno.buffer(TOLERANCIA).covers(candidato):
        return (
            "La modificacion haria que el ambiente "
            "salga de los limites del terreno."
        )

    for otro in ambientes:

        if otro is ambiente:
            continue

        if candidato.intersection(otro["poligono"]).area > TOLERANCIA:
            return (
                f"La modificacion se superpone con "
                f"el ambiente {otro['nombre']}."
            )

    return None


def _actualizar_poligono(ambiente, nuevo_poligono):

    ambiente["entidad"].set_points(
        list(nuevo_poligono.exterior.coords)[:-1],
        format="xy"
    )

    ambiente["poligono"] = nuevo_poligono


def _rectangulo_o_error(poligono):

    xmin, ymin, xmax, ymax = poligono.bounds

    rectangulo = box(xmin, ymin, xmax, ymax)

    if poligono.symmetric_difference(rectangulo).area > TOLERANCIA:
        raise ValueError(
            "Por ahora solo se pueden modificar "
            "habitaciones rectangulares."
        )

    return xmin, ymin, xmax, ymax


# ==========================================
# 2. MODIFICAR EL AREA DE UNA HABITACION
# ==========================================

def modificar_area(
    modelo,
    ambientes,
    terreno,
    nombre,
    area_objetivo
):

    """
    Cambia el area de una habitacion rectangular,
    conservando su centro y proporcion.
    """

    ambiente = resolver_ambiente(ambientes, nombre)

    poligono = ambiente["poligono"]

    xmin, ymin, xmax, ymax = _rectangulo_o_error(poligono)

    if area_objetivo <= 0:
        raise ValueError(
            "El area objetivo debe ser mayor que cero."
        )

    area_actual = poligono.area
    factor = (area_objetivo / area_actual) ** 0.5

    nuevo_ancho = (xmax - xmin) * factor
    nuevo_alto = (ymax - ymin) * factor

    centro = poligono.centroid

    nuevo_poligono = box(
        centro.x - nuevo_ancho / 2,
        centro.y - nuevo_alto / 2,
        centro.x + nuevo_ancho / 2,
        centro.y + nuevo_alto / 2
    )

    error = _comprobar_ubicacion(
        nuevo_poligono, ambiente, ambientes, terreno
    )

    if error:
        raise ValueError(error)

    _actualizar_poligono(ambiente, nuevo_poligono)

    # El centro se conserva: solo cambia el texto del area.
    for texto in buscar_textos(modelo, ambiente):

        if _es_etiqueta_area(texto):
            texto.dxf.text = f"{nuevo_poligono.area:.2f} m2"

    return {
        "ambiente": ambiente["nombre"],
        "id": ambiente["id"],
        "area_anterior": round(area_actual, 2),
        "area_nueva": round(nuevo_poligono.area, 2)
    }


# ==========================================
# 3. MOVER UN AMBIENTE
# ==========================================

LADOS_POR_RELACION = {
    "izquierda_de": ("izquierda",),
    "derecha_de": ("derecha",),
    "arriba_de": ("arriba",),
    "abajo_de": ("abajo",),
    # Contacto en cualquier lado; se elige el mas cercano.
    "junto_a": ("izquierda", "derecha", "arriba", "abajo"),
    "cerca_de": ("izquierda", "derecha", "arriba", "abajo"),
}


def _candidatos_junto_a(rect_ref, ancho, alto, lado):

    """
    Posiciones (xmin, ymin) del ambiente pegado a `rect_ref`
    por el lado indicado, recorriendo toda la arista compartida.
    """

    rx0, ry0, rx1, ry1 = rect_ref

    if lado in ("izquierda", "derecha"):

        x = rx0 - ancho if lado == "izquierda" else rx1

        inicio = ry0 - alto + PASO_BUSQUEDA_M
        fin = ry1 - PASO_BUSQUEDA_M

        pasos = int((fin - inicio) / PASO_BUSQUEDA_M) + 1

        return [
            (x, inicio + i * PASO_BUSQUEDA_M)
            for i in range(max(pasos, 1))
        ]

    y = ry0 - alto if lado == "abajo" else ry1

    inicio = rx0 - ancho + PASO_BUSQUEDA_M
    fin = rx1 - PASO_BUSQUEDA_M

    pasos = int((fin - inicio) / PASO_BUSQUEDA_M) + 1

    return [
        (inicio + i * PASO_BUSQUEDA_M, y)
        for i in range(max(pasos, 1))
    ]


def mover_ambiente(
    modelo,
    ambientes,
    terreno,
    nombre,
    referencia,
    relacion
):

    """
    Mueve una habitacion rectangular para que quede pegada a otra
    (izquierda, derecha, arriba o abajo de ella). Conserva sus
    dimensiones. Elige la posicion valida mas cercana a la actual
    que no salga del terreno ni se superponga con otros ambientes.
    """

    if relacion == "lejos_de":
        raise NotImplementedError(
            "La relacion 'lejos_de' no esta implementada."
        )

    if relacion not in LADOS_POR_RELACION:
        raise ValueError(f"Relacion espacial desconocida: {relacion}.")

    ambiente = resolver_ambiente(ambientes, nombre)
    ambiente_ref = resolver_ambiente(ambientes, referencia)

    if ambiente is ambiente_ref:
        raise ValueError(
            "Un ambiente no puede moverse respecto a si mismo."
        )

    xmin, ymin, xmax, ymax = _rectangulo_o_error(ambiente["poligono"])
    rect_ref = _rectangulo_o_error(ambiente_ref["poligono"])

    ancho = xmax - xmin
    alto = ymax - ymin

    centro_actual = ambiente["poligono"].centroid

    mejor = None
    ultimo_error = None

    for lado in LADOS_POR_RELACION[relacion]:

        for x0, y0 in _candidatos_junto_a(rect_ref, ancho, alto, lado):

            candidato = box(x0, y0, x0 + ancho, y0 + alto)

            error = _comprobar_ubicacion(
                candidato, ambiente, ambientes, terreno
            )

            if error:
                ultimo_error = error
                continue

            distancia = candidato.centroid.distance(centro_actual)

            if mejor is None or distancia < mejor[0]:
                mejor = (distancia, candidato)

    if mejor is None:
        raise ValueError(
            f"No hay espacio libre para colocar "
            f"{ambiente['nombre']} {relacion.replace('_', ' ')} "
            f"{ambiente_ref['nombre']}"
            + (f" ({ultimo_error})" if ultimo_error else ".")
        )

    nuevo_poligono = mejor[1]

    desplazamiento_x = nuevo_poligono.bounds[0] - xmin
    desplazamiento_y = nuevo_poligono.bounds[1] - ymin

    _actualizar_poligono(ambiente, nuevo_poligono)

    for texto in buscar_textos(modelo, ambiente):

        x, y, z = texto.dxf.insert

        texto.dxf.insert = (
            x + desplazamiento_x,
            y + desplazamiento_y,
            z
        )

        # Los textos centrados usan tambien align_point.
        if texto.dxf.hasattr("align_point"):

            ax, ay, az = texto.dxf.align_point

            texto.dxf.align_point = (
                ax + desplazamiento_x,
                ay + desplazamiento_y,
                az
            )

    return {
        "ambiente": ambiente["nombre"],
        "id": ambiente["id"],
        "referencia": ambiente_ref["nombre"],
        "relacion": relacion,
        "desplazamiento": (
            round(desplazamiento_x, 2),
            round(desplazamiento_y, 2),
        ),
    }


# ==========================================
# 4. MOTOR PRINCIPAL DE EDICION
# ==========================================

ADVERTENCIA_ELEMENTOS = (
    "Los muros, puertas, ventanas y mobiliario del DXF no se "
    "recalculan al editar ambientes; regenera el plano para "
    "actualizarlos."
)


def editar_dxf(ruta_entrada, ruta_salida, solicitud):

    """
    Ejecuta las operaciones interpretadas por Qwen
    y guarda un nuevo archivo DXF.
    """

    entrada = Path(ruta_entrada)
    salida = Path(ruta_salida)

    if not entrada.exists():
        raise FileNotFoundError(
            f"No existe el archivo: {entrada}"
        )

    if entrada.resolve() == salida.resolve():
        raise ValueError(
            "El archivo de salida debe ser diferente "
            "del archivo original."
        )

    documento = ezdxf.readfile(str(entrada))

    unidades = documento.header.get("$INSUNITS", 0)

    if unidades != UNIDADES_METROS:
        raise ValueError(
            "Este editor inicial requiere un DXF "
            "con unidades configuradas en metros."
        )

    modelo = documento.modelspace()

    ambientes = obtener_ambientes(modelo)
    terreno = obtener_terreno(modelo)

    if not ambientes:
        raise ValueError(
            "No se encontraron ambientes con metadatos. "
            "Genera nuevamente el plano con el generador actualizado."
        )

    resultados = []

    for operacion in solicitud.operaciones:

        if operacion.tipo == "modificar_area":

            resultados.append(modificar_area(
                modelo=modelo,
                ambientes=ambientes,
                terreno=terreno,
                nombre=operacion.ambiente,
                area_objetivo=operacion.area_objetivo
            ))

        elif operacion.tipo == "mover_ambiente":

            resultados.append(mover_ambiente(
                modelo=modelo,
                ambientes=ambientes,
                terreno=terreno,
                nombre=operacion.ambiente,
                referencia=operacion.referencia,
                relacion=operacion.relacion
            ))

    salida.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    documento.saveas(str(salida))

    observaciones = list(solicitud.observaciones)

    if resultados and ADVERTENCIA_ELEMENTOS not in observaciones:
        observaciones.append(ADVERTENCIA_ELEMENTOS)

    return {
        "archivo": str(salida),
        "modificaciones": resultados,
        "observaciones": observaciones
    }
