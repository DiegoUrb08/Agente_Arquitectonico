"""
Amueblado automático: coloca el mobiliario básico de cada ambiente
contra las paredes, sin tapar las puertas ni superponer muebles.
"""

from itertools import permutations

from shapely.geometry import Point, box

from src.geometry.furniture_generator import construir_mobiliario
from src.utils.texto import normalizar_nombre

HOLGURA_PARED_M = 0.05
# Medidas reducidas, solo para ambientes donde no entra la habitual.
COMPACTAS = {"ducha": (0.70, 0.90)}
PASO_BUSQUEDA_M = 0.25

# Mobiliario por tipo de ambiente. "centrado" lo coloca en el centro.
PLANTILLAS = {
    "sala": [{"tipo": "sofa"}],
    "comedor": [{"tipo": "mesa_comedor", "centrado": True}],
    "cocina": [{"tipo": "cocina"}, {"tipo": "refrigeradora"}],
    "dormitorio": [{"tipo": "cama_matrimonial"}, {"tipo": "armario"}],
    "dormitorio principal": [{"tipo": "cama_queen"}, {"tipo": "armario"}],
    "bano": [{"tipo": "inodoro"}, {"tipo": "lavatorio"}, {"tipo": "ducha"}],
    "estudio": [{"tipo": "escritorio"}],
    "oficina": [{"tipo": "escritorio"}],
    "lavanderia": [{"tipo": "lavadora"}, {"tipo": "secadora"}],
    "terraza": [{"tipo": "mesa_comedor", "centrado": True}],
    "closet": [{"tipo": "armario"}],
}


def _tipo_base(ambiente):
    """'dormitorio_2' -> 'dormitorio'."""
    base = ambiente["id"].rsplit("_", 1)[0]
    return normalizar_nombre(base)


def _zonas_de_puertas(puertas, ajustadas=False):
    """
    Zona libre de muebles ante cada puerta: holgada (un círculo de su ancho) o
    `ajustadas`, solo lo que barre la hoja: su ancho, a ambos lados del muro.
    El portón de un garaje no abre hacia los ambientes.
    """

    zonas = []

    for puerta in (puertas or {}).get("puertas", []):
        if puerta.get("vehicular"):
            continue
        cx, cy = puerta["centro"]
        ancho = puerta["ancho"]
        medio = ancho / 2 - 0.01  # tocar el borde no estorba
        if not ajustadas:
            zonas.append(Point(cx, cy).buffer(ancho))
        elif puerta.get("orientacion") == "vertical":
            zonas.append(box(cx - ancho, cy - medio, cx + ancho, cy + medio))
        else:
            zonas.append(box(cx - medio, cy - ancho, cx + medio, cy + ancho))

    return zonas


def _candidatos(poligono, ancho, largo, centrado):
    """Posiciones (x, y) a probar: centro, esquinas y luego las paredes."""

    xmin, ymin, xmax, ymax = poligono.bounds
    g = HOLGURA_PARED_M

    if centrado:
        # En el centro o, si una puerta lo impide, lo más cerca posible.
        cx, cy = (xmin + xmax - ancho) / 2, (ymin + ymax - largo) / 2
        pasos_x = int(max(0.0, cx - xmin - g) / PASO_BUSQUEDA_M)
        pasos_y = int(max(0.0, cy - ymin - g) / PASO_BUSQUEDA_M)
        desplazamientos = sorted(
            (
                (i * PASO_BUSQUEDA_M, j * PASO_BUSQUEDA_M)
                for i in range(-pasos_x, pasos_x + 1)
                for j in range(-pasos_y, pasos_y + 1)
            ),
            key=lambda d: d[0] ** 2 + d[1] ** 2,
        )
        for dx, dy in desplazamientos:
            yield cx + dx, cy + dy
        return

    xs = [xmin + g, xmax - ancho - g]
    ys = [ymin + g, ymax - largo - g]

    for y in ys:
        for x in xs:
            yield x, y

    x = xmin + g
    while x <= xmax - ancho - g:
        yield x, ys[0]
        yield x, ys[1]
        x += PASO_BUSQUEDA_M

    y = ymin + g
    while y <= ymax - largo - g:
        yield xs[0], y
        yield xs[1], y
        y += PASO_BUSQUEDA_M


def _colocar(ambiente, plantilla, zonas, compactas=False):
    """(muebles colocados, tipos que no cupieron) para un orden de plantilla."""

    poligono = ambiente["poligono"]
    colocados = []
    omitidos = []

    for item in plantilla:

        colocado = None

        for ancho, largo in _orientaciones(item["tipo"], compactas):

            for x, y in _candidatos(
                poligono, ancho, largo, item.get("centrado", False)
            ):

                geometria = box(x, y, x + ancho, y + largo)

                if not poligono.covers(geometria):
                    continue

                if any(
                    geometria.intersects(otro["geometria"])
                    for otro in colocados
                ):
                    continue

                if any(geometria.intersects(z) for z in zonas):
                    continue

                colocado = construir_mobiliario({
                    "tipo": item["tipo"],
                    "ambiente": ambiente["nombre"],
                    "x": round(x, 3),
                    "y": round(y, 3),
                    "ancho": ancho,
                    "largo": largo,
                })
                break

            if colocado:
                break

        if colocado:
            colocados.append(colocado)
        else:
            omitidos.append(item["tipo"])

    return colocados, omitidos


def _amueblar_ambiente(ambiente, plantilla, holgadas, ajustadas):
    """
    El primer reparto en el que cabe todo: probando otros órdenes y, solo si
    hace falta, acercándose más a las puertas y al final con medidas reducidas.
    Si no, el que más muebles tenga.
    """

    mejor = None

    etapas = [(holgadas, False), (ajustadas, False)]
    if any(item["tipo"] in COMPACTAS for item in plantilla):
        etapas.append((ajustadas, True))

    for zonas, compactas in etapas:
        for orden in permutations(plantilla):
            colocados, omitidos = _colocar(ambiente, orden, zonas, compactas)
            if not omitidos:
                return colocados, omitidos
            if mejor is None or len(colocados) > len(mejor[0]):
                mejor = colocados, omitidos

    return mejor


def amueblar_automaticamente(resultado_geometrias, resultado_puertas=None):
    """
    Devuelve un resultado con el mismo formato que `generar_mobiliario`
    más la lista `omitidos` (muebles que no cupieron).
    """

    holgadas = _zonas_de_puertas(resultado_puertas)
    ajustadas = _zonas_de_puertas(resultado_puertas, ajustadas=True)
    colocados = []
    omitidos = []

    for ambiente in resultado_geometrias["ambientes"]:

        plantilla = PLANTILLAS.get(_tipo_base(ambiente), [])

        if not plantilla:
            continue

        del_ambiente, faltan = _amueblar_ambiente(
            ambiente, plantilla, holgadas, ajustadas
        )
        colocados.extend(del_ambiente)
        omitidos.extend(f"{tipo} en {ambiente['id']}" for tipo in faltan)

    return {
        "mobiliario": colocados,
        "cantidad": len(colocados),
        "errores": [],
        "valido": True,
        "omitidos": omitidos,
    }


def _orientaciones(tipo, compactas=False):
    from src.geometry.furniture_generator import obtener_dimensiones

    ancho, largo = obtener_dimensiones(tipo)
    opciones = [(ancho, largo), (largo, ancho)]

    if compactas and tipo in COMPACTAS:
        ancho, largo = COMPACTAS[tipo]
        opciones += [(ancho, largo), (largo, ancho)]

    return opciones
