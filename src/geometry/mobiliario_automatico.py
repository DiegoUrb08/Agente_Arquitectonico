"""
Amueblado automático: coloca el mobiliario básico de cada ambiente
contra las paredes, sin tapar las puertas ni superponer muebles.
"""

from shapely.geometry import Point, box

from src.geometry.furniture_generator import construir_mobiliario
from src.utils.texto import normalizar_nombre

HOLGURA_PARED_M = 0.05
PASO_BUSQUEDA_M = 0.25

# Mobiliario por tipo de ambiente. "centrado" lo coloca en el centro.
PLANTILLAS = {
    "sala": [{"tipo": "sofa"}],
    "comedor": [{"tipo": "mesa_comedor", "centrado": True}],
    "cocina": [{"tipo": "cocina"}, {"tipo": "refrigeradora"}],
    "dormitorio": [{"tipo": "cama_matrimonial"}, {"tipo": "armario"}],
    "bano": [{"tipo": "inodoro"}, {"tipo": "lavatorio"}, {"tipo": "ducha"}],
    "estudio": [{"tipo": "escritorio"}],
    "oficina": [{"tipo": "escritorio"}],
}


def _tipo_base(ambiente):
    """'dormitorio_2' -> 'dormitorio'."""
    base = ambiente["id"].rsplit("_", 1)[0]
    return normalizar_nombre(base)


def _zonas_de_puertas(puertas):
    """Zona libre de muebles alrededor de cada puerta."""

    zonas = []

    for puerta in (puertas or {}).get("puertas", []):
        cx, cy = puerta["centro"]
        zonas.append(Point(cx, cy).buffer(puerta["ancho"]))

    return zonas


def _candidatos(poligono, ancho, largo, centrado):
    """Posiciones (x, y) a probar: centro, esquinas y luego las paredes."""

    xmin, ymin, xmax, ymax = poligono.bounds
    g = HOLGURA_PARED_M

    if centrado:
        yield (xmin + xmax - ancho) / 2, (ymin + ymax - largo) / 2
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


def amueblar_automaticamente(resultado_geometrias, resultado_puertas=None):
    """
    Devuelve un resultado con el mismo formato que `generar_mobiliario`
    más la lista `omitidos` (muebles que no cupieron).
    """

    zonas = _zonas_de_puertas(resultado_puertas)
    colocados = []
    omitidos = []

    for ambiente in resultado_geometrias["ambientes"]:

        plantilla = PLANTILLAS.get(_tipo_base(ambiente), [])
        poligono = ambiente["poligono"]
        del_ambiente = []

        for item in plantilla:

            colocado = None

            for ancho, largo in _orientaciones(item["tipo"]):

                for x, y in _candidatos(
                    poligono, ancho, largo, item.get("centrado", False)
                ):

                    geometria = box(x, y, x + ancho, y + largo)

                    if not poligono.covers(geometria):
                        continue

                    if any(
                        geometria.intersects(otro["geometria"])
                        for otro in del_ambiente
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
                del_ambiente.append(colocado)
            else:
                omitidos.append(f"{item['tipo']} en {ambiente['id']}")

        colocados.extend(del_ambiente)

    return {
        "mobiliario": colocados,
        "cantidad": len(colocados),
        "errores": [],
        "valido": True,
        "omitidos": omitidos,
    }


def _orientaciones(tipo):
    from src.geometry.furniture_generator import obtener_dimensiones

    ancho, largo = obtener_dimensiones(tipo)

    return [(ancho, largo), (largo, ancho)]
