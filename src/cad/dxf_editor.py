
from pathlib import Path

import ezdxf

from shapely.geometry import Polygon, box


# ==========================================
# 1. FUNCIONES AUXILIARES
# ==========================================

def obtener_nombre(entidad):

    """
    Recupera el nombre del ambiente guardado
    en los metadatos XDATA.
    """

    if not entidad.has_xdata("AGENTE_ARQ"):
        return None

    datos = entidad.get_xdata("AGENTE_ARQ")

    if not datos:
        return None

    return str(datos[0].value)


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

        if entidad.dxf.layer != "AMBIENTES":
            continue

        nombre = obtener_nombre(entidad)

        if not nombre:
            continue

        poligono = obtener_poligono(entidad)

        ambientes.append({
            "entidad": entidad,
            "nombre": nombre,
            "poligono": poligono
        })

    return ambientes


# ==========================================
# 2. BUSCAR EL TERRENO
# ==========================================

def obtener_terreno(modelo):

    """
    Busca el poligono que representa el terreno.
    """

    for entidad in modelo.query("LWPOLYLINE"):

        if entidad.dxf.layer != "TERRENO":
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


# ==========================================
# 3. BUSCAR LA ETIQUETA DEL AMBIENTE
# ==========================================

def buscar_texto(modelo, nombre):

    """
    Encuentra el texto asociado al ambiente.
    """

    coincidencias = []

    for entidad in modelo.query("TEXT"):

        if entidad.dxf.layer != "TEXTOS":
            continue

        nombre_texto = obtener_nombre(entidad)

        if nombre_texto and nombre_texto.casefold() == nombre.casefold():
            coincidencias.append(entidad)

    if len(coincidencias) > 1:
        raise ValueError(
            f"Hay varias etiquetas asociadas a {nombre}."
        )

    return coincidencias[0] if coincidencias else None


# ==========================================
# 4. MODIFICAR EL AREA DE UNA HABITACION
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

    coincidencias = [
        ambiente
        for ambiente in ambientes
        if ambiente["nombre"].casefold() == nombre.casefold()
    ]

    if len(coincidencias) == 0:
        raise ValueError(
            f"No se encontro el ambiente: {nombre}."
        )

    if len(coincidencias) > 1:
        raise ValueError(
            f"El nombre {nombre} es ambiguo. "
            "Hay mas de un ambiente con ese nombre."
        )

    ambiente = coincidencias[0]

    entidad = ambiente["entidad"]
    poligono = ambiente["poligono"]

    # Obtener los limites del ambiente
    xmin, ymin, xmax, ymax = poligono.bounds

    ancho = xmax - xmin
    alto = ymax - ymin

    # Verificar que sea un rectangulo alineado
    rectangulo = box(xmin, ymin, xmax, ymax)

    if poligono.symmetric_difference(rectangulo).area > 0.000001:
        raise ValueError(
            "Por ahora solo se pueden modificar "
            "habitaciones rectangulares."
        )

    # Calcular el factor de escala
    area_actual = poligono.area

    if area_objetivo <= 0:
        raise ValueError(
            "El area objetivo debe ser mayor que cero."
        )

    factor = (area_objetivo / area_actual) ** 0.5

    nuevo_ancho = ancho * factor
    nuevo_alto = alto * factor

    # Mantener el centro de la habitacion
    centro = poligono.centroid

    nuevo_poligono = box(
        centro.x - nuevo_ancho / 2,
        centro.y - nuevo_alto / 2,
        centro.x + nuevo_ancho / 2,
        centro.y + nuevo_alto / 2
    )

    # Comprobar que permanezca dentro del terreno
    if not terreno.covers(nuevo_poligono):
        raise ValueError(
            "La modificacion haria que el ambiente "
            "salga de los limites del terreno."
        )

    # Comprobar que no invada otros ambientes
    for otro in ambientes:

        if otro["entidad"].dxf.handle == entidad.dxf.handle:
            continue

        interseccion = nuevo_poligono.intersection(
            otro["poligono"]
        )

        if interseccion.area > 0.000001:
            raise ValueError(
                f"La modificacion se superpone con "
                f"el ambiente {otro['nombre']}."
            )

    # Actualizar los vertices de la polilinea
    nuevos_puntos = list(nuevo_poligono.exterior.coords)[:-1]

    entidad.set_points(
        nuevos_puntos,
        format="xy"
    )

    # Actualizar la posicion del nombre
    texto = buscar_texto(modelo, nombre)

    if texto is not None:
        texto.dxf.insert = (
            centro.x,
            centro.y,
            0
        )

    # Actualizar geometria en memoria
    ambiente["poligono"] = nuevo_poligono

    return {
        "ambiente": nombre,
        "area_anterior": round(area_actual, 2),
        "area_nueva": round(nuevo_poligono.area, 2)
    }


# ==========================================
# 5. MOTOR PRINCIPAL DE EDICION
# ==========================================

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

    # Comprobar unidades: 6 corresponde a metros
    unidades = documento.header.get("$INSUNITS", 0)

    if unidades != 6:
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

            resultado = modificar_area(
                modelo=modelo,
                ambientes=ambientes,
                terreno=terreno,
                nombre=operacion.ambiente,
                area_objetivo=operacion.area_objetivo
            )

            resultados.append(resultado)

        elif operacion.tipo == "mover_ambiente":

            raise NotImplementedError(
                "La operacion de mover ambientes "
                "todavia no esta implementada."
            )

    # Crear carpeta de salida
    salida.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    # Guardar una nueva version del plano
    documento.saveas(str(salida))

    return {
        "archivo": str(salida),
        "modificaciones": resultados,
        "observaciones": solicitud.observaciones
    }
