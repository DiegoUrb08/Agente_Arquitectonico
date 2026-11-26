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
from src.planning.reacomodo import (
    cumple_relacion,
    reacomodar_para_area,
    reubicar_ambiente,
)
from src.utils.texto import normalizar_nombre


TOLERANCIA = 1e-6


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


def _desplazar_textos(modelo, ambiente, desplazamiento_x, desplazamiento_y):

    """
    Mueve las etiquetas del ambiente el mismo desplazamiento que su poligono.
    """

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


def _contacto_total(poligono, ambiente, ambientes):

    """
    Longitud de pared que `poligono` comparte con los demas ambientes.
    """

    return sum(
        poligono.boundary.intersection(otro["poligono"].boundary).length
        for otro in ambientes
        if otro is not ambiente
    )


def _candidatos_redimension(poligono, nuevo_ancho, nuevo_alto):

    """
    Rectangulos del nuevo tamano: centrado y anclado a cada esquina.
    """

    xmin, ymin, xmax, ymax = poligono.bounds
    centro = poligono.centroid

    return [
        box(
            centro.x - nuevo_ancho / 2, centro.y - nuevo_alto / 2,
            centro.x + nuevo_ancho / 2, centro.y + nuevo_alto / 2
        ),
        box(xmin, ymin, xmin + nuevo_ancho, ymin + nuevo_alto),
        box(xmax - nuevo_ancho, ymin, xmax, ymin + nuevo_alto),
        box(xmin, ymax - nuevo_alto, xmin + nuevo_ancho, ymax),
        box(xmax - nuevo_ancho, ymax - nuevo_alto, xmax, ymax),
    ]


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
    Cambia el area de una habitacion rectangular conservando su
    proporcion. Se ancla a la esquina (o al centro) que mantiene mas
    pared compartida con los ambientes vecinos.

    Si al ampliar no hay sitio libre, se reacomoda la planta entera
    (los vecinos ceden algo de superficie o se desplazan) y el resultado
    incluye `ajustes` con los demas ambientes cuya area cambio.
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

    # Se prueba centrado y anclado a cada esquina; gana el que conserva
    # mas pared compartida con los vecinos (el centrado gana los empates).
    validos = []
    primer_error = None

    for orden, candidato in enumerate(
        _candidatos_redimension(poligono, nuevo_ancho, nuevo_alto)
    ):

        error = _comprobar_ubicacion(candidato, ambiente, ambientes, terreno)

        if error:
            primer_error = primer_error or error
            continue

        validos.append((
            -round(_contacto_total(candidato, ambiente, ambientes), 6),
            orden,
            candidato
        ))

    ajustes = []

    if validos:

        _aplicar_poligono(
            modelo, ambiente, min(validos, key=lambda v: v[:2])[2]
        )

    elif area_objetivo > area_actual:

        ajustes = _reacomodar(
            modelo, ambientes, terreno, ambiente, area_objetivo, primer_error
        )

    else:
        raise ValueError(primer_error)

    resultado = {
        "ambiente": ambiente["nombre"],
        "id": ambiente["id"],
        "area_anterior": round(area_actual, 2),
        "area_nueva": round(ambiente["poligono"].area, 2)
    }

    if ajustes:
        resultado["ajustes"] = ajustes

    return resultado


def _aplicar_poligono(modelo, ambiente, nuevo_poligono):

    """
    Sustituye la geometria de un ambiente y actualiza sus etiquetas.
    """

    anterior = ambiente["poligono"].centroid

    _actualizar_poligono(ambiente, nuevo_poligono)

    _desplazar_textos(
        modelo,
        ambiente,
        nuevo_poligono.centroid.x - anterior.x,
        nuevo_poligono.centroid.y - anterior.y
    )

    for texto in buscar_textos(modelo, ambiente):

        if _es_etiqueta_area(texto):
            texto.dxf.text = f"{nuevo_poligono.area:.2f} m2"


def _reacomodar(
    modelo, ambientes, terreno, ambiente, area_objetivo, motivo
):

    """
    Redistribuye la planta para que `ambiente` alcance el area pedida.
    Devuelve los cambios de area del resto de ambientes.
    """

    x0, y0, x1, y1 = terreno.bounds

    nueva = reacomodar_para_area(
        _distribucion_en_terreno(ambientes, terreno),
        ambiente["id"], area_objetivo, x1 - x0, y1 - y0
    )

    if nueva is None:
        raise ValueError(
            f"{motivo} Tampoco es posible reacomodar los demas ambientes "
            "para darle esa superficie: prueba con un area menor."
        )

    return [
        ajuste
        for ajuste in _aplicar_distribucion(modelo, ambientes, terreno, nueva)
        if ajuste["id"] != ambiente["id"]
    ]


def _distribucion_en_terreno(ambientes, terreno):

    """
    Distribucion con las coordenadas relativas al origen del terreno.
    """

    x0, y0, _, _ = terreno.bounds

    distribucion = distribucion_desde_ambientes(ambientes)

    for datos in distribucion:
        datos["x"] -= x0
        datos["y"] -= y0

    return distribucion


def _aplicar_distribucion(modelo, ambientes, terreno, nueva):

    """
    Mueve los ambientes del DXF a la nueva distribucion y devuelve los
    que cambiaron de area (salvo diferencias minimas).
    """

    x0, y0, _, _ = terreno.bounds
    por_id = {datos["id"]: datos for datos in nueva}
    ajustes = []

    for otro in ambientes:

        datos = por_id[otro["id"]]
        area_anterior = otro["poligono"].area
        x, y = datos["x"] + x0, datos["y"] + y0

        _aplicar_poligono(
            modelo, otro,
            box(x, y, x + datos["ancho"], y + datos["largo"])
        )

        area_nueva = otro["poligono"].area

        if abs(area_nueva - area_anterior) >= 0.05:
            ajustes.append({
                "id": otro["id"],
                "area_anterior": round(area_anterior, 2),
                "area_nueva": round(area_nueva, 2)
            })

    return ajustes


# ==========================================
# 3. MOVER UN AMBIENTE
# ==========================================

RELACIONES = {
    "izquierda_de": "a la izquierda de",
    "derecha_de": "a la derecha de",
    "arriba_de": "arriba de",
    "abajo_de": "abajo de",
    "junto_a": "junto a",
    "cerca_de": "cerca de",
    "lejos_de": "lejos de",
}


def _legible(ambiente):
    return str(ambiente["id"]).replace("_", " ").capitalize()


def resolver_referencias(ambientes, referencia):

    """
    Como `resolver_ambiente`, pero un nombre repetido ("dormitorio")
    vale por cualquiera de ellos.
    """

    clave = normalizar_nombre(referencia)

    por_nombre = [
        a for a in ambientes
        if normalizar_nombre(a["nombre"]) == clave
    ]

    if len(por_nombre) > 1:
        return por_nombre

    return [resolver_ambiente(ambientes, referencia)]


def mover_ambiente(
    modelo,
    ambientes,
    terreno,
    nombre,
    referencia,
    relacion
):

    """
    Reubica un ambiente respecto a otro (al lado, a la izquierda, derecha,
    arriba o abajo, o lejos de el). Reorganiza la planta lo menos posible,
    por lo que otros ambientes pueden desplazarse o ceder algo de area.
    """

    if relacion not in RELACIONES:
        raise ValueError(f"Relacion espacial desconocida: {relacion}.")

    candidatos = resolver_referencias(ambientes, nombre)
    guias = resolver_referencias(ambientes, referencia)

    parejas = [(a, g) for a in candidatos for g in guias if a is not g]

    if not parejas:
        raise ValueError(
            "Un ambiente no puede moverse respecto a si mismo."
        )

    x0, y0, x1, y1 = terreno.bounds
    distribucion = _distribucion_en_terreno(ambientes, terreno)
    por_id = {datos["id"]: datos for datos in distribucion}
    descripcion = RELACIONES[relacion]

    for candidato, guia in parejas:

        if cumple_relacion(
            por_id[candidato["id"]], por_id[guia["id"]], relacion
        ):
            raise ValueError(
                f"{_legible(candidato)} ya esta {descripcion} "
                f"{_legible(guia).lower()}: no hice cambios."
            )

    # Si hay varios ambientes con ese nombre, se mueve el mas cercano.
    ambiente = min(
        parejas,
        key=lambda p: p[0]["poligono"].centroid.distance(
            p[1]["poligono"].centroid
        )
    )[0]
    referencias = [g for g in guias if g is not ambiente]

    nueva = reubicar_ambiente(
        distribucion,
        ambiente["id"],
        [ref["id"] for ref in referencias],
        relacion,
        x1 - x0,
        y1 - y0
    )

    if nueva is None:
        raise ValueError(
            f"No es posible colocar {ambiente['nombre']} {descripcion} "
            f"{referencia} dentro del terreno, ni reorganizando los demas "
            "ambientes."
        )

    antes = ambiente["poligono"].bounds
    area_anterior = ambiente["poligono"].area

    ajustes = _aplicar_distribucion(modelo, ambientes, terreno, nueva)

    # Entre varias referencias, la que cumple la relacion.
    finales = {datos["id"]: datos for datos in nueva}
    elegida = next(
        (
            ref for ref in referencias
            if cumple_relacion(
                finales[ambiente["id"]], finales[ref["id"]], relacion
            )
        ),
        referencias[0]
    )

    despues = ambiente["poligono"].bounds

    if abs(ambiente["poligono"].area - area_anterior) >= 0.05:
        ajustes.insert(0, {
            "id": ambiente["id"],
            "area_anterior": round(area_anterior, 2),
            "area_nueva": round(ambiente["poligono"].area, 2)
        })

    # El numero solo hace falta si el nombre de la referencia se repite.
    repetida = sum(a["nombre"] == elegida["nombre"] for a in ambientes) > 1

    resultado = {
        "ambiente": ambiente["nombre"],
        "id": ambiente["id"],
        "referencia": elegida["id"] if repetida else elegida["nombre"],
        "relacion": relacion,
        "desplazamiento": (
            round(despues[0] - antes[0], 2),
            round(despues[1] - antes[1], 2),
        ),
    }

    if ajustes:
        resultado["ajustes"] = ajustes

    return resultado


# ==========================================
# 4. MOTOR PRINCIPAL DE EDICION
# ==========================================

ADVERTENCIA_ELEMENTOS = (
    "Los muros, puertas, ventanas y mobiliario del DXF no se "
    "recalculan al editar ambientes; regenera el plano para "
    "actualizarlos."
)


def cargar_y_editar(ruta_entrada, solicitud):

    """
    Abre el DXF y aplica las operaciones en memoria.

    Con `solicitud=None` solo lo abre, sin modificar nada.
    Devuelve (documento, ambientes, terreno, resultados) sin guardar.
    """

    entrada = Path(ruta_entrada)

    if not entrada.exists():
        raise FileNotFoundError(
            f"No existe el archivo: {entrada}"
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

    operaciones = solicitud.operaciones if solicitud is not None else []

    for operacion in operaciones:

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

    return documento, ambientes, terreno, resultados


def distribucion_desde_ambientes(ambientes):

    """
    Convierte los ambientes (rectangulares) del DXF en una distribucion
    compatible con el pipeline, redondeando a milimetros.
    """

    distribucion = []

    for ambiente in ambientes:

        xmin, ymin, xmax, ymax = _rectangulo_o_error(ambiente["poligono"])

        distribucion.append({
            "id": ambiente["id"],
            "nombre": ambiente["nombre"],
            "x": round(xmin, 3),
            "y": round(ymin, 3),
            "ancho": round(xmax - xmin, 3),
            "largo": round(ymax - ymin, 3),
        })

    return distribucion


def editar_dxf(ruta_entrada, ruta_salida, solicitud):

    """
    Ejecuta las operaciones interpretadas por Qwen
    y guarda un nuevo archivo DXF.
    """

    entrada = Path(ruta_entrada)
    salida = Path(ruta_salida)

    if entrada.exists() and entrada.resolve() == salida.resolve():
        raise ValueError(
            "El archivo de salida debe ser diferente "
            "del archivo original."
        )

    documento, _, _, resultados = cargar_y_editar(entrada, solicitud)

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
