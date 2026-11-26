from pathlib import Path

import ezdxf

from shapely.geometry import Polygon, box

from src.cad.dxf_base import (
    registrar_metadatos,
    APP_ID,
    CAPA_AMBIENTES,
    CAPA_TERRENO,
    CAPA_TEXTOS,
    UNIDADES_METROS,
)
from src.models.defaults import obtener_area_referencia
from src.planning.reacomodo import (
    agregar_a_planta,
    cumple_relacion,
    quitar_de_planta,
    reacomodar_para_area,
    reubicar_ambiente,
)
from src.planning.reglas_ambientes import AMBIENTES_VALIDOS
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


def obtener_terrenos(modelo):

    """
    Poligonos de terreno del DXF, de abajo hacia arriba (uno por planta).
    """

    terrenos = []

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
            terrenos.append(terreno)

    if not terrenos:
        raise ValueError(
            "No se encontro un terreno valido en el DXF."
        )

    return sorted(terrenos, key=lambda t: t.bounds[1])


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
    area_objetivo,
    planta=None
):

    """
    Cambia el area de una habitacion rectangular conservando su
    proporcion. Se ancla a la esquina (o al centro) que mantiene mas
    pared compartida con los ambientes vecinos.

    Si al ampliar no hay sitio libre, se reacomoda la planta entera
    (los vecinos ceden algo de superficie o se desplazan) y el resultado
    incluye `ajustes` con los demas ambientes cuya area cambio.
    """

    planta = planta or {}
    ambiente = resolver_ambiente(ambientes, nombre)
    _comprobar_modificable(ambiente, planta)

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

        limites = planta.get("limites")
        zona = box(*limites) if limites else terreno

        error = _comprobar_ubicacion(candidato, ambiente, ambientes, zona)

        if not error and not _cubre(
            planta.get("cubrir"), candidato, ambiente, ambientes
        ):
            error = "La planta alta quedaria sobresaliendo."

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

    elif area_objetivo > area_actual or planta.get("cubrir"):

        ajustes = _reacomodar(
            modelo, ambientes, terreno, ambiente, area_objetivo, primer_error,
            planta
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


def _cubre(contorno, candidato, ambiente, ambientes):

    """
    True si, con `candidato` en lugar de `ambiente`, la planta sigue
    llegando hasta los bordes de `contorno`.
    """

    if not contorno:
        return True

    cajas = [
        (candidato if a is ambiente else a["poligono"]).bounds
        for a in ambientes
    ]
    x0, y0, x1, y1 = contorno

    return (
        min(c[0] for c in cajas) <= x0 + TOLERANCIA
        and min(c[1] for c in cajas) <= y0 + TOLERANCIA
        and max(c[2] for c in cajas) >= x1 - TOLERANCIA
        and max(c[3] for c in cajas) >= y1 - TOLERANCIA
    )


def _comprobar_modificable(ambiente, planta):
    if ambiente["id"] in planta.get("fijos", ()):
        raise ValueError(
            f"{_legible(ambiente)} une las dos plantas y no se puede cambiar."
        )


def _reacomodar(
    modelo, ambientes, terreno, ambiente, area_objetivo, motivo, planta
):

    """
    Redistribuye la planta para que `ambiente` alcance el area pedida.
    Devuelve los cambios de area del resto de ambientes.
    """

    x0, y0, x1, y1 = terreno.bounds

    nueva = reacomodar_para_area(
        _distribucion_en_terreno(ambientes, terreno),
        ambiente["id"], area_objetivo, x1 - x0, y1 - y0, **planta
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
    relacion,
    planta=None
):

    """
    Reubica un ambiente respecto a otro (al lado, a la izquierda, derecha,
    arriba o abajo, o lejos de el). Reorganiza la planta lo menos posible,
    por lo que otros ambientes pueden desplazarse o ceder algo de area.
    """

    if relacion not in RELACIONES:
        raise ValueError(f"Relacion espacial desconocida: {relacion}.")

    planta = planta or {}
    candidatos = [
        a for a in resolver_referencias(ambientes, nombre)
        if a["id"] not in planta.get("fijos", ())
    ]
    if not candidatos:
        _comprobar_modificable(resolver_ambiente(ambientes, nombre), planta)
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
        y1 - y0,
        **planta
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
# 4. AGREGAR Y QUITAR AMBIENTES
# ==========================================

def renombrar_ambiente(
    modelo, ambientes, nombre, nombre_nuevo, planta=None, numeros=None
):

    """Cambia el tipo de un ambiente sin moverlo ("llama cocina al ambiente 1")."""

    planta = planta or {}

    if not nombre_nuevo:
        raise ValueError("Indica el nuevo nombre del ambiente.")

    ambiente = resolver_ambiente(ambientes, nombre)
    _comprobar_modificable(ambiente, planta)

    otros = [a for a in ambientes if a is not ambiente]
    nuevo = nombre_de_ambiente(nombre_nuevo, otros)

    if normalizar_nombre(nuevo) == normalizar_nombre(ambiente["nombre"]):
        raise ValueError(f"{_legible(ambiente)} ya es {nuevo}.")

    anterior = ambiente["id"]
    identificador = _siguiente_id(otros, nuevo, numeros)

    for entidad in [ambiente["entidad"], *buscar_textos(modelo, ambiente)]:
        registrar_metadatos(entidad, identificador, nuevo)

    ambiente["id"] = identificador
    ambiente["nombre"] = nuevo

    return {
        "accion": "renombrado",
        "ambiente": nuevo,
        "id": identificador,
        "id_anterior": anterior,
    }


def nombre_de_ambiente(texto, ambientes=()):

    """
    Nombre de catalogo para lo que escribio el usuario ("estudios" no vale).
    Si ya hay ambientes de ese tipo, conserva su escritura (p. ej. con ñ).
    """

    clave = normalizar_nombre(texto)

    for ambiente in ambientes:
        if normalizar_nombre(ambiente["nombre"]) == clave:
            return ambiente["nombre"]

    if clave not in AMBIENTES_VALIDOS and not clave.startswith(
        ("dormitorio", "bano")
    ):
        catalogo = ", ".join(sorted(AMBIENTES_VALIDOS))
        raise ValueError(
            f"No puedo agregar '{texto}'. Los tipos disponibles son: "
            f"{catalogo}."
        )

    return texto.strip().lower()


def _siguiente_id(ambientes, nombre, numeros):

    base = normalizar_nombre(nombre)
    usados = [
        int(a["id"].rsplit("_", 1)[1])
        for a in ambientes
        if normalizar_nombre(a["id"].rsplit("_", 1)[0]) == base
    ]
    return f"{base}_{max([*usados, (numeros or {}).get(base, 0)]) + 1}"


def agregar_ambiente(
    modelo, ambientes, terreno, nombre, area_objetivo=None, referencia=None,
    relacion=None, planta=None, numeros=None
):

    """
    Incorpora un ambiente nuevo y reorganiza la planta. `numeros` es el
    ultimo numero usado de cada tipo en otras plantas.
    """

    planta = planta or {}
    nombre = nombre_de_ambiente(nombre, ambientes)
    area = area_objetivo or obtener_area_referencia(nombre)
    identificador = _siguiente_id(ambientes, nombre, numeros)

    guias = (
        resolver_referencias(ambientes, referencia) if referencia else []
    )
    x0, y0, x1, y1 = terreno.bounds

    nueva = agregar_a_planta(
        _distribucion_en_terreno(ambientes, terreno),
        {"id": identificador, "nombre": nombre, "area_m2": area},
        x1 - x0, y1 - y0,
        referencias=[g["id"] for g in guias],
        relacion=relacion or "junto_a",
        id_pasillo=_siguiente_id(ambientes, "pasillo", numeros),
        **planta
    )

    if nueva is None:
        raise ValueError(
            f"No es posible agregar {nombre} de {area:g} m2 en este terreno: "
            "prueba con un area menor o quita algun ambiente."
        )

    existentes = {a["id"] for a in ambientes}

    for datos in nueva:

        if datos["id"] in existentes:
            continue

        x, y = datos["x"] + x0, datos["y"] + y0
        poligono = box(x, y, x + datos["ancho"], y + datos["largo"])
        entidad = modelo.add_lwpolyline(
            list(poligono.exterior.coords)[:-1], close=True,
            dxfattribs={"layer": CAPA_AMBIENTES}
        )
        registrar_metadatos(entidad, datos["id"], datos["nombre"])
        ambientes.append({
            "entidad": entidad, "id": datos["id"],
            "nombre": datos["nombre"], "poligono": poligono
        })

    ajustes = _aplicar_distribucion(modelo, ambientes, terreno, nueva)
    anadido = next(a for a in ambientes if a["id"] == identificador)
    tambien = [
        d["id"] for d in nueva
        if d["id"] not in existentes and d["id"] != identificador
    ]

    resultado = {
        "accion": "agregado",
        "ambiente": nombre,
        "id": identificador,
        "area_nueva": round(anadido["poligono"].area, 2)
    }

    if tambien:
        resultado["tambien"] = tambien

    if ajustes:
        resultado["ajustes"] = ajustes

    return resultado


def quitar_ambiente(modelo, ambientes, terreno, nombre, planta=None):

    """
    Elimina un ambiente; los demas ocupan su sitio. Si hay varios con ese
    nombre ("quita un bano"), quita el ultimo.
    """

    planta = planta or {}
    candidatos = resolver_referencias(ambientes, nombre)
    ambiente = max(
        candidatos, key=lambda a: int(a["id"].rsplit("_", 1)[1])
    )
    _comprobar_modificable(ambiente, planta)

    if len(ambientes) < 2:
        raise ValueError("No se puede quitar el unico ambiente de la planta.")

    x0, y0, x1, y1 = terreno.bounds

    nueva = quitar_de_planta(
        _distribucion_en_terreno(ambientes, terreno),
        ambiente["id"], x1 - x0, y1 - y0, **planta
    )

    if nueva is None:
        raise ValueError(
            f"No pude reorganizar la planta sin {_legible(ambiente)}."
        )

    quedan = {d["id"] for d in nueva}
    tambien = []

    for otro in [a for a in ambientes if a["id"] not in quedan]:
        for texto in buscar_textos(modelo, otro):
            modelo.delete_entity(texto)
        modelo.delete_entity(otro["entidad"])
        ambientes.remove(otro)
        if otro is not ambiente:
            tambien.append(otro["id"])

    resultado = {
        "accion": "quitado",
        "ambiente": ambiente["nombre"],
        "id": ambiente["id"]
    }

    if tambien:
        resultado["tambien"] = tambien

    ajustes = _aplicar_distribucion(modelo, ambientes, terreno, nueva)

    if ajustes:
        resultado["ajustes"] = ajustes

    return resultado


# ==========================================
# 5. MOTOR PRINCIPAL DE EDICION
# ==========================================

ADVERTENCIA_ELEMENTOS = (
    "Los muros, puertas, ventanas y mobiliario del DXF no se "
    "recalculan al editar ambientes; regenera el plano para "
    "actualizarlos."
)


def tiene_metadatos(documento) -> bool:

    """True si el DXF lo genero este proyecto (ambientes con XDATA)."""

    return any(
        obtener_nombre(entidad)
        for entidad in documento.modelspace().query("LWPOLYLINE")
        if entidad.dxf.layer == CAPA_AMBIENTES
    )


def _abrir_documento(ruta_entrada):

    """
    Abre un DXF generado por el proyecto y devuelve
    (documento, ambientes, terrenos).
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
    terrenos = obtener_terrenos(modelo)

    if not ambientes:
        raise ValueError(
            "No se encontraron ambientes con metadatos. "
            "Genera nuevamente el plano con el generador actualizado."
        )

    return documento, ambientes, terrenos


def _ids_unicos(distribuciones):

    """
    Renumera los ids repetidos entre plantas (DXF de versiones
    anteriores). La escalera es la misma en todas.
    """

    ocupados = {a["id"] for d in distribuciones for a in d}
    usados = set()

    for distribucion in distribuciones:

        for ambiente in distribucion:

            base = ambiente["id"].rsplit("_", 1)[0]

            if base != "escalera" and ambiente["id"] in usados:

                numero = 1

                while f"{base}_{numero}" in ocupados:
                    numero += 1

                ambiente["id"] = f"{base}_{numero}"
                ocupados.add(ambiente["id"])

            usados.add(ambiente["id"])

    return distribuciones


def leer_plantas(ruta_entrada):

    """
    Distribucion de cada planta del DXF, con coordenadas relativas a su
    terreno. Devuelve (distribuciones, ancho, largo), de abajo hacia arriba.
    """

    _, ambientes, terrenos = _abrir_documento(ruta_entrada)

    por_terreno = [[] for _ in terrenos]

    for ambiente in ambientes:

        punto = ambiente["poligono"].representative_point()
        indice = next(
            (i for i, t in enumerate(terrenos) if t.covers(punto)),
            None
        )

        if indice is None:
            raise ValueError(
                f"El ambiente {ambiente['id'] or ambiente['nombre']} "
                "esta fuera del terreno."
            )

        por_terreno[indice].append(ambiente)

    plantas = [
        (terreno, suyos)
        for terreno, suyos in zip(terrenos, por_terreno)
        if suyos
    ]

    if len(plantas) > 2:
        raise ValueError("Solo se admiten planos de hasta dos plantas.")

    distribuciones = []

    for terreno, suyos in plantas:

        x0, y0 = terreno.bounds[:2]
        distribucion = distribucion_desde_ambientes(suyos)

        for ambiente in distribucion:
            ambiente["x"] = round(ambiente["x"] - x0, 3)
            ambiente["y"] = round(ambiente["y"] - y0, 3)

        distribuciones.append(distribucion)

    xmin, ymin, xmax, ymax = plantas[0][0].bounds

    return (
        _ids_unicos(distribuciones),
        round(xmax - xmin, 3),
        round(ymax - ymin, 3),
    )


def cargar_y_editar(ruta_entrada, solicitud, planta=None, numeros=None):

    """
    Abre el DXF y aplica las operaciones en memoria.

    En una casa de varias plantas, `planta` fija la escalera y los limites
    (ver `reacomodo`) y `numeros` evita repetir ids de otras plantas.

    Con `solicitud=None` solo lo abre, sin modificar nada.
    Devuelve (documento, ambientes, terreno, resultados) sin guardar.
    """

    documento, ambientes, terrenos = _abrir_documento(ruta_entrada)

    if len(terrenos) > 1:
        raise ValueError(
            "Este DXF tiene varias plantas: abrelo desde la aplicacion."
        )

    modelo = documento.modelspace()
    terreno = terrenos[0]

    resultados = []

    operaciones = solicitud.operaciones if solicitud is not None else []

    for operacion in operaciones:

        if (
            getattr(operacion, "planta", None) == "alta"
            and "fijos" not in (planta or {})  # solo en casas de dos
        ):
            raise ValueError("Este plano tiene una sola planta.")

        if operacion.tipo == "agregar_ambiente":

            resultados.append(agregar_ambiente(
                modelo=modelo,
                ambientes=ambientes,
                terreno=terreno,
                nombre=operacion.ambiente,
                area_objetivo=operacion.area_objetivo,
                referencia=operacion.referencia,
                relacion=operacion.relacion,
                planta=planta,
                numeros=numeros
            ))

        elif operacion.tipo == "renombrar_ambiente":

            resultados.append(renombrar_ambiente(
                modelo=modelo,
                ambientes=ambientes,
                nombre=operacion.ambiente,
                nombre_nuevo=operacion.nombre_nuevo,
                planta=planta,
                numeros=numeros
            ))

        elif operacion.tipo == "quitar_ambiente":

            resultados.append(quitar_ambiente(
                modelo=modelo,
                ambientes=ambientes,
                terreno=terreno,
                nombre=operacion.ambiente,
                planta=planta
            ))

        elif operacion.tipo == "modificar_area":

            resultados.append(modificar_area(
                modelo=modelo,
                ambientes=ambientes,
                terreno=terreno,
                nombre=operacion.ambiente,
                area_objetivo=operacion.area_objetivo,
                planta=planta
            ))

        elif operacion.tipo == "mover_ambiente":

            resultados.append(mover_ambiente(
                modelo=modelo,
                ambientes=ambientes,
                terreno=terreno,
                nombre=operacion.ambiente,
                referencia=operacion.referencia,
                relacion=operacion.relacion,
                planta=planta
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
