"""
Amueblado automático: coloca el mobiliario básico de cada ambiente
contra las paredes, sin tapar las puertas ni superponer muebles.
"""

from shapely.geometry import Point, box

from src.geometry.complementos import complementar, complementos_esperados
from src.geometry.furniture_generator import construir_mobiliario
from src.utils.texto import normalizar_nombre

HOLGURA_PARED_M = 0.05
# Medidas reducidas, solo para ambientes donde no entra la habitual.
COMPACTAS = {
    "sofa": (1.40, 0.80),
    "mesa_comedor": (0.90, 0.70),
    "cama_matrimonial": (1.35, 1.90),
    "cama_queen": (1.50, 1.90),
    "armario": (0.90, 0.50),
    "escritorio": (1.00, 0.50),
    "refrigeradora": (0.60, 0.60),
    "lavatorio": (0.45, 0.35),
    "ducha": (0.70, 0.70),
    "lavadora": (0.55, 0.55),
    "secadora": (0.55, 0.55),
}
PASO_FINO_M = 0.05
# Franja mínima libre ante una puerta (que entonces abriría hacia el otro lado).
FONDO_DE_PASO_M = 0.40
# Repartos que se prueban por ambiente y etapa antes de rendirse.
INTENTOS_MAXIMOS = 400
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
    # La terraza es exterior: en 3D lleva macetas y pérgola, no muebles de interior.
    "terraza": [],
    "closet": [{"tipo": "armario"}],
}


def _tipo_base(ambiente):
    """'dormitorio_2' -> 'dormitorio'."""
    base = ambiente["id"].rsplit("_", 1)[0]
    return normalizar_nombre(base)


def _zonas_de_puertas(puertas, ajustadas=False, fondo=None):
    """
    Zona libre de muebles ante cada puerta: holgada (un círculo de su ancho) o
    `ajustadas`, solo lo que barre la hoja: su ancho, a ambos lados del muro.
    Con `fondo`, apenas esa franja de paso a cada lado.
    El portón de un garaje no abre hacia los ambientes.
    """

    zonas = []

    for puerta in (puertas or {}).get("puertas", []):
        if puerta.get("vehicular"):
            continue
        cx, cy = puerta["centro"]
        ancho = puerta["ancho"]
        medio = ancho / 2 - 0.01  # tocar el borde no estorba
        alcance = fondo or ancho
        if not ajustadas:
            zonas.append(Point(cx, cy).buffer(ancho))
        elif puerta.get("orientacion") == "vertical":
            zonas.append(box(cx - alcance, cy - medio, cx + alcance, cy + medio))
        else:
            zonas.append(box(cx - medio, cy - alcance, cx + medio, cy + alcance))

    return zonas


def _candidatos(poligono, ancho, largo, centrado, paso=PASO_BUSQUEDA_M):
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
        x += paso

    y = ymin + g
    while y <= ymax - largo - g:
        yield xs[0], y
        yield xs[1], y
        y += paso


def _posiciones(ambiente, item, zonas, compactas):
    """Muebles posibles para un elemento, del lugar preferido al menos."""

    poligono = ambiente["poligono"]
    paso = PASO_FINO_M if compactas else PASO_BUSQUEDA_M

    for ancho, largo in _orientaciones(item["tipo"], compactas):

        for x, y in _candidatos(
            poligono, ancho, largo, item.get("centrado", False), paso
        ):

            geometria = box(x, y, x + ancho, y + largo)

            if not poligono.covers(geometria):
                continue

            if any(geometria.intersects(z) for z in zonas):
                continue

            yield construir_mobiliario({
                "tipo": item["tipo"],
                "ambiente": ambiente["nombre"],
                "x": round(x, 3),
                "y": round(y, 3),
                "ancho": ancho,
                "largo": largo,
            })


def _repartos(ambiente, plantilla, zonas, compactas):
    """
    Repartos con todos los muebles: si uno no deja sitio a los siguientes, se
    mueve y se vuelve a probar.
    """

    opciones = [
        list(_posiciones(ambiente, item, zonas, compactas))
        for item in plantilla
    ]
    if not all(opciones):
        return

    # El que tiene menos sitios posibles se coloca antes.
    orden = sorted(range(len(plantilla)), key=lambda i: len(opciones[i]))
    presupuesto = [INTENTOS_MAXIMOS * len(plantilla)]

    def seguir(puestos):
        if len(puestos) == len(orden):
            yield list(puestos)
            return
        for mueble in opciones[orden[len(puestos)]]:
            if presupuesto[0] <= 0:
                return
            if any(
                mueble["geometria"].intersects(otro["geometria"])
                for otro in puestos
            ):
                continue
            presupuesto[0] -= 1
            yield from seguir(puestos + [mueble])

    yield from seguir([])


def _los_que_quepan(ambiente, plantilla, zonas):
    """Cuando no entra todo: tantos como se pueda, en el orden de la plantilla."""

    colocados, omitidos = [], []

    for item in plantilla:
        mueble = next((
            m for m in _posiciones(ambiente, item, zonas, True)
            if not any(m["geometria"].intersects(o["geometria"]) for o in colocados)
        ), None)
        if mueble:
            colocados.append(mueble)
        else:
            omitidos.append(item["tipo"])

    return colocados, omitidos


def _amueblar_ambiente(ambiente, plantilla, etapas):
    """
    (muebles, tipos que no cupieron). `etapas` va de la más holgada a la más
    apretada; se busca el primer reparto en el que entran todos los muebles y
    también sus complementos (sillas, mesa de centro, auto).
    """

    esperados = complementos_esperados(ambiente["id"], plantilla)
    mejor = None  # (nº de complementos, muebles con complementos)

    for zonas, compactas in etapas:
        for probados, reparto in enumerate(
            _repartos(ambiente, plantilla, zonas, compactas)
        ):
            extra = complementar(ambiente, reparto, zonas)
            if len(extra) >= esperados:
                return reparto + extra, []
            if mejor is None or len(extra) > mejor[0]:
                mejor = len(extra), reparto + extra
            if probados >= INTENTOS_MAXIMOS:
                break

    if mejor is not None:
        return mejor[1], []

    zonas = etapas[-1][0]
    colocados, omitidos = _los_que_quepan(ambiente, plantilla, zonas)
    return colocados + complementar(ambiente, colocados, zonas), omitidos


def amueblar_automaticamente(resultado_geometrias, resultado_puertas=None):
    """
    Devuelve un resultado con el mismo formato que `generar_mobiliario`
    más la lista `omitidos` (muebles que no cupieron).
    """

    holgadas = _zonas_de_puertas(resultado_puertas)
    ajustadas = _zonas_de_puertas(resultado_puertas, ajustadas=True)
    de_paso = _zonas_de_puertas(
        resultado_puertas, ajustadas=True, fondo=FONDO_DE_PASO_M
    )
    etapas = [
        (holgadas, False), (ajustadas, False), (ajustadas, True),
        (de_paso, True),
    ]
    colocados = []
    omitidos = []

    for ambiente in resultado_geometrias["ambientes"]:

        plantilla = PLANTILLAS.get(_tipo_base(ambiente), [])

        del_ambiente, faltan = _amueblar_ambiente(ambiente, plantilla, etapas)
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
