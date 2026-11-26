"""
Importación de DXF dibujados con otros programas (AutoCAD, LibreCAD...).

Convierte el dibujo en distribuciones rectangulares como las del optimizador:

1. Lee la geometría (también dentro de bloques) y la pasa a metros.
2. Endereza el plano si está girado.
3. Detecta las habitaciones por sus contornos cerrados o, si no los hay, por
   los espacios que encierran los muros.
4. Las nombra a partir de los textos del dibujo y las aproxima a rectángulos
   que comparten aristas.
5. Separa las plantas si hay dos grupos de habitaciones.
"""

import math
import re
from collections import defaultdict

import ezdxf
from ezdxf import bbox, recover
from ezdxf import path as rutas
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union
from shapely.prepared import prep

from src.cad.nombres_dxf import es_nombre, planta_de_texto, tipo_desde_texto
from src.utils.texto import normalizar_nombre

# $INSUNITS -> (metros por unidad, nombre)
UNIDADES = {
    1: (0.0254, "pulgadas"),
    2: (0.3048, "pies"),
    4: (0.001, "milímetros"),
    5: (0.01, "centímetros"),
    6: (1.0, "metros"),
    14: (0.1, "decímetros"),
}
CANDIDATAS = ((1.0, "metros"), (0.01, "centímetros"), (0.001, "milímetros"))
TAMANO_TIPICO_M = 20.0
TAMANO_MINIMO_M = 3.0
TAMANO_MAXIMO_M = 300.0

AREA_MINIMA_M2 = 1.2
AREA_MAXIMA_M2 = 250.0
ANCHO_MINIMO_M = 0.6
CIERRE_VANOS_M = 0.46       # cierra vanos de puerta de hasta ~0,9 m
JUNTA_MAXIMA_M = 0.45       # grueso máximo de un muro entre dos habitaciones
SOLAPE_MINIMO_M = 0.3
RECTANGULARIDAD = 0.9
SEPARACION_PLANTAS_M = 2.0
MARGEN_TERRENO_M = 1.0
GIRO_MINIMO_GRADOS = 0.5
MAXIMO_NIVELES_BLOQUE = 8

CAPAS_MUROS = re.compile(r"mur|wall|pared|tabique")
CAPAS_TERRENO = re.compile(
    r"lote|terreno|site|parcela|predio|lindero|property|plot|\blot\b"
)
CAPAS_EXCLUIDAS = re.compile(
    r"cot|dim|text|anno|mueb|mobil|furn|sanit|plum|door|puert|vent|wind|"
    r"equip|eqp|title|rotul|grid|axis|\beje"
)

SIN_HABITACIONES = (
    "No encontré habitaciones en el dibujo. Reconozco habitaciones "
    "dibujadas como contornos cerrados o encerradas por muros."
)


# ==========================================
# LECTURA
# ==========================================

def leer_dxf(ruta):
    """Abre el DXF; si está algo dañado, intenta recuperarlo."""
    try:
        return ezdxf.readfile(str(ruta))
    except ezdxf.DXFStructureError as error:
        try:
            documento, _ = recover.readfile(str(ruta))
        except Exception:  # con basura, recover falla de muchas formas
            raise error from None
        if not len(documento.modelspace()):
            raise error from None
        return documento


def _recorrer(entidades, ocultas, capa_padre=None, en_bloque=False, nivel=0):
    """(entidad, capa, en_bloque) explotando los bloques."""
    for entidad in entidades:
        capa = entidad.dxf.get("layer", "0")
        if capa == "0" and capa_padre:
            capa = capa_padre
        if capa in ocultas:
            continue

        if entidad.dxftype() == "INSERT":
            for atributo in entidad.attribs:
                if not atributo.is_invisible:
                    yield atributo, capa, True
            if nivel >= MAXIMO_NIVELES_BLOQUE:
                continue
            try:
                hijos = list(entidad.virtual_entities())
            except Exception:  # bloques dañados o con entidades no admitidas
                continue
            yield from _recorrer(hijos, ocultas, capa, True, nivel + 1)
            continue

        yield entidad, capa, en_bloque


def _puntos(ruta, paso):
    return [(v.x, v.y) for v in ruta.flattening(paso)]


def _extraer(documento):
    """Segmentos, contornos cerrados y textos, en unidades del dibujo."""
    ocultas = {
        capa.dxf.name for capa in documento.layers
        if capa.is_off() or capa.is_frozen()
    }
    entidades = list(_recorrer(documento.modelspace(), ocultas))

    geometricas = [
        e for e, _, _ in entidades
        if e.dxftype() in ("LINE", "LWPOLYLINE", "POLYLINE", "ARC")
    ]
    limites = bbox.extents(geometricas, fast=True)
    tamano = (
        max(limites.size.x, limites.size.y) if limites.has_data else 1.0
    )
    paso = max(tamano / 2000, 1e-6)

    segmentos, contornos, textos = [], [], []

    for entidad, capa, en_bloque in entidades:
        tipo = entidad.dxftype()
        capa = capa.lower()

        if tipo == "LINE":
            a, b = entidad.dxf.start, entidad.dxf.end
            segmentos.append((a.x, a.y, b.x, b.y, capa, en_bloque, False))

        elif tipo in ("LWPOLYLINE", "POLYLINE", "ARC"):
            if tipo == "POLYLINE" and not entidad.is_2d_polyline:
                continue
            puntos = _puntos(rutas.make_path(entidad), paso)
            for (x1, y1), (x2, y2) in zip(puntos, puntos[1:]):
                segmentos.append(
                    (x1, y1, x2, y2, capa, en_bloque, tipo == "ARC")
                )
            cerrada = tipo != "ARC" and (
                getattr(entidad, "closed", False)
                or getattr(entidad, "is_closed", False)
                or (len(puntos) > 3 and math.dist(puntos[0], puntos[-1]) < paso)
            )
            if cerrada and len(puntos) >= 3:
                if math.dist(puntos[0], puntos[-1]) > paso:
                    segmentos.append(
                        (*puntos[-1], *puntos[0], capa, en_bloque, False)
                    )
                contornos.append((puntos, capa, en_bloque))

        elif tipo == "HATCH":
            for ruta in rutas.from_hatch(entidad):
                puntos = _puntos(ruta, paso)
                if len(puntos) >= 3:
                    contornos.append((puntos, capa, en_bloque))

        elif tipo in ("TEXT", "ATTRIB", "MTEXT"):
            if tipo == "MTEXT":
                posicion = entidad.dxf.insert
            else:
                posicion = entidad.get_placement()[1]
            texto = entidad.plain_text().strip()
            if texto:
                textos.append((posicion.x, posicion.y, texto))

    return segmentos, contornos, textos


# ==========================================
# UNIDADES Y GIRO
# ==========================================

def _escala(documento, segmentos):
    if not segmentos:
        return 1.0, None

    xs = [v for s in segmentos for v in (s[0], s[2])]
    ys = [v for s in segmentos for v in (s[1], s[3])]
    tamano = max(max(xs) - min(xs), max(ys) - min(ys))

    codigo = documento.header.get("$INSUNITS", 0)
    if codigo in UNIDADES:
        factor, nombre = UNIDADES[codigo]
        if TAMANO_MINIMO_M <= tamano * factor <= TAMANO_MAXIMO_M:
            return factor, f"Unidades del dibujo: {nombre}."

    factor, nombre = min(
        CANDIDATAS,
        key=lambda u: abs(math.log(max(tamano * u[0], 1e-9) / TAMANO_TIPICO_M)),
    )
    return factor, f"El dibujo no indicaba bien sus unidades; supuse {nombre}."


def _giro(segmentos) -> float:
    """Ángulo (grados, entre −45 y 45) que tienen los muros respecto a los ejes."""
    pesos = defaultdict(float)
    for x1, y1, x2, y2, _, _, es_arco in segmentos:
        largo = math.hypot(x2 - x1, y2 - y1)
        if es_arco or largo < 0.3:
            continue
        angulo = math.degrees(math.atan2(y2 - y1, x2 - x1)) % 90
        pesos[round(angulo * 2) / 2 % 90] += largo

    if not pesos:
        return 0.0

    pico = max(pesos, key=pesos.get)
    suma = total = 0.0
    for angulo, peso in pesos.items():
        diferencia = (angulo - pico + 45) % 90 - 45
        if abs(diferencia) <= 1:
            suma += diferencia * peso
            total += peso

    angulo = (pico + suma / total + 45) % 90 - 45
    return angulo if abs(angulo) > GIRO_MINIMO_GRADOS else 0.0


def _transformador(factor, giro):
    coseno = math.cos(math.radians(-giro))
    seno = math.sin(math.radians(-giro))

    def transformar(x, y):
        x, y = x * factor, y * factor
        return x * coseno - y * seno, x * seno + y * coseno

    return transformar


# ==========================================
# HABITACIONES
# ==========================================

def _poligono(puntos):
    poligono = Polygon(puntos)
    if not poligono.is_valid:
        poligono = poligono.buffer(0)
    if poligono.geom_type == "MultiPolygon":
        poligono = max(poligono.geoms, key=lambda p: p.area)
    return poligono if poligono.geom_type == "Polygon" else None


def _aceptable(poligono) -> bool:
    return (
        poligono is not None
        and AREA_MINIMA_M2 <= poligono.area <= AREA_MAXIMA_M2
        and not poligono.buffer(-ANCHO_MINIMO_M / 2).is_empty
    )


def _depurar(candidatos):
    """
    Quita perímetros (contornos ocupados en su mayor parte por otros),
    duplicados y lo que queda dentro de una habitación ya elegida.
    """
    sin_perimetros = []
    for poligono in candidatos:
        holgado = prep(poligono.buffer(0.05))
        dentro = [
            q for q in candidatos
            if q is not poligono and q.area < poligono.area and holgado.covers(q)
        ]
        if unary_union(dentro).area < 0.6 * poligono.area if dentro else True:
            sin_perimetros.append(poligono)

    elegidos = []
    for poligono in sorted(sin_perimetros, key=lambda p: -p.area):
        if all(
            poligono.intersection(q).area < 0.1 * poligono.area
            for q in elegidos
        ):
            elegidos.append(poligono)
    return elegidos


def _por_contornos(contornos):
    candidatos, terrenos = [], []
    for puntos, capa, en_bloque in contornos:
        poligono = _poligono(puntos)
        if poligono is None:
            continue
        if CAPAS_TERRENO.search(capa):
            terrenos.append(poligono)
        elif (
            not en_bloque
            and not CAPAS_EXCLUIDAS.search(capa)
            and not CAPAS_MUROS.search(capa)
            and _aceptable(poligono)
        ):
            candidatos.append(poligono)

    terreno = max(terrenos, key=lambda p: p.area, default=None)
    return _depurar(candidatos), terreno


def _por_muros(segmentos):
    """
    Habitaciones = espacios que encierran los muros (con los vanos cerrados).

    Devuelve pares (habitación, hueco): el hueco es la habitación encogida
    `CIERRE_VANOS_M`, sin los entrantes de las puertas; de él sale el
    rectángulo.
    """
    muros = [s for s in segmentos if CAPAS_MUROS.search(s[4])]
    if not muros:
        muros = [
            s for s in segmentos
            if not s[5] and not s[6]
            and not CAPAS_EXCLUIDAS.search(s[4])
            and not CAPAS_TERRENO.search(s[4])
        ]

    lineas = [
        LineString([(s[0], s[1]), (s[2], s[3])])
        for s in muros if math.hypot(s[2] - s[0], s[3] - s[1]) > 1e-4
    ]
    if not lineas:
        return []

    # Extremos y esquinas en ángulo recto: los vanos se cierran sin dejar
    # picos dentro de las habitaciones.
    cuerpo = unary_union(lineas).buffer(
        CIERRE_VANOS_M, cap_style="square", join_style="mitre"
    )
    partes = getattr(cuerpo, "geoms", [cuerpo])

    huecos = {}
    for parte in partes:
        for anillo in parte.interiors:
            hueco = _poligono(anillo.coords)
            if hueco is None:
                continue
            habitacion = hueco.buffer(CIERRE_VANOS_M, quad_segs=4)
            if _aceptable(habitacion):
                huecos[habitacion] = hueco

    return [(h, huecos[h]) for h in _depurar(list(huecos))]


def _rectangulo(poligono, margen=0.0):
    """
    [x0, y0, x1, y1] y área perdida al aproximarlo a un rectángulo. Con
    `margen`, el polígono es la habitación encogida esa distancia.
    """
    x0, y0, x1, y1 = poligono.bounds
    if poligono.area >= RECTANGULARIDAD * (x1 - x0) * (y1 - y0):
        return [x0 - margen, y0 - margen, x1 + margen, y1 + margen], 0.0

    simple = poligono.simplify(0.05)
    xs = sorted({round(x, 3) for x, _ in simple.exterior.coords})
    ys = sorted({round(y, 3) for _, y in simple.exterior.coords})
    holgado = prep(poligono.buffer(0.03))

    mejor_area, mejor = 0.0, [x0, y0, x1, y1]
    for i, xa in enumerate(xs):
        for xb in xs[i + 1:]:
            for k, ya in enumerate(ys):
                for yb in ys[k + 1:]:
                    area = (xb - xa) * (yb - ya)
                    if area > mejor_area and holgado.covers(box(xa, ya, xb, yb)):
                        mejor_area, mejor = area, [xa, ya, xb, yb]

    xa, ya, xb, yb = mejor
    caja = [xa - margen, ya - margen, xb + margen, yb + margen]
    if not mejor_area:
        return caja, 0.0
    # La pérdida se mide en el hueco y se lleva al tamaño real.
    escala = (caja[2] - caja[0]) * (caja[3] - caja[1]) / mejor_area
    return caja, max(0.0, poligono.area - mejor_area) * escala


def _solape(a0, a1, b0, b1) -> float:
    return min(a1, b1) - max(a0, b0)


def _cerrar_juntas(cajas):
    """
    Lleva al eje del muro las caras enfrentadas de habitaciones vecinas, para
    que compartan arista (cada caja es [x0, y0, x1, y1]).
    """
    padre = {}

    def raiz(nodo):
        while padre.setdefault(nodo, nodo) != nodo:
            padre[nodo] = padre[padre[nodo]]
            nodo = padre[nodo]
        return nodo

    def unir(a, b):
        padre[raiz(a)] = raiz(b)

    for i, a in enumerate(cajas):
        for j, b in enumerate(cajas):
            if i == j:
                continue
            # a a la izquierda de b
            if (
                _solape(a[1], a[3], b[1], b[3]) > SOLAPE_MINIMO_M
                and abs(b[0] - a[2]) <= JUNTA_MAXIMA_M
                and a[0] < b[0] and a[2] < b[2]
            ):
                unir((i, 2), (j, 0))
            # a debajo de b
            if (
                _solape(a[0], a[2], b[0], b[2]) > SOLAPE_MINIMO_M
                and abs(b[1] - a[3]) <= JUNTA_MAXIMA_M
                and a[1] < b[1] and a[3] < b[3]
            ):
                unir((i, 3), (j, 1))

    grupos = defaultdict(list)
    for nodo in list(padre):
        grupos[raiz(nodo)].append(nodo)

    for nodos in grupos.values():
        valor = round(sum(cajas[i][k] for i, k in nodos) / len(nodos), 2)
        for i, k in nodos:
            cajas[i][k] = valor

    for caja in cajas:
        caja[:] = [round(v, 2) for v in caja]

    _quitar_solapes(cajas)


def _quitar_solapes(cajas):
    """Recorta lo poco que dos cajas puedan pisarse tras cerrar las juntas."""
    for i, a in enumerate(cajas):
        for b in cajas[i + 1:]:
            ancho = _solape(a[0], a[2], b[0], b[2])
            alto = _solape(a[1], a[3], b[1], b[3])
            if ancho <= 0.005 or alto <= 0.005:
                continue
            grande = a if (a[2] - a[0]) * (a[3] - a[1]) >= (
                b[2] - b[0]) * (b[3] - b[1]) else b
            otra = b if grande is a else a
            if ancho <= alto:
                if grande[0] < otra[0]:
                    grande[2] = otra[0]
                else:
                    grande[0] = otra[2]
            else:
                if grande[1] < otra[1]:
                    grande[3] = otra[1]
                else:
                    grande[1] = otra[3]


# ==========================================
# NOMBRES
# ==========================================

def _nombrar(poligonos, textos):
    """Tipo de cada habitación y textos que no se reconocieron."""
    tipos, desconocidos = [], []
    for poligono in poligonos:
        zona = prep(poligono.buffer(0.05))
        centro = poligono.centroid
        reconocidos = []
        for x, y, texto in textos:
            if not zona.contains(Point(x, y)) or not es_nombre(texto):
                continue
            tipo = tipo_desde_texto(texto)
            if tipo:
                reconocidos.append((centro.distance(Point(x, y)), tipo))
            elif not planta_de_texto(texto):
                desconocidos.append(texto)
        tipos.append(min(reconocidos)[1] if reconocidos else "ambiente")
    return tipos, list(dict.fromkeys(desconocidos))


def _legible(identificador):
    return identificador.replace("_", " ").capitalize()


# ==========================================
# PLANTAS
# ==========================================

def _separar_plantas(cajas, tipos, textos):
    """Índices de cada planta (baja primero)."""
    zonas = unary_union([
        box(*c).buffer(SEPARACION_PLANTAS_M / 2, join_style="mitre")
        for c in cajas
    ])
    zonas = list(getattr(zonas, "geoms", [zonas]))

    if len(zonas) > 2:
        raise ValueError(
            f"El dibujo tiene {len(zonas)} grupos de habitaciones separados; "
            "solo se admite una planta o dos (baja y alta)."
        )

    grupos = [[] for _ in zonas]
    for i, caja in enumerate(cajas):
        punto = box(*caja).centroid
        indice = min(range(len(zonas)), key=lambda z: zonas[z].distance(punto))
        grupos[indice].append(i)

    if len(grupos) == 1:
        return grupos

    votos = [0, 0]   # positivo: planta alta
    for x, y, texto in textos:
        planta = planta_de_texto(texto)
        if planta:
            cerca = min((0, 1), key=lambda z: zonas[z].distance(Point(x, y)))
            votos[cerca] += 1 if planta == "alta" else -1

    if votos[0] != votos[1]:
        alta = 0 if votos[0] > votos[1] else 1
    else:
        sociales = [
            any(tipos[i] in ("sala", "cocina") for i in grupo) for grupo in grupos
        ]
        if sociales[0] != sociales[1]:
            alta = 0 if sociales[1] else 1
        else:
            (ax0, ay0, ax1, ay1), (bx0, by0, bx1, by1) = (
                z.bounds for z in zonas
            )
            if max(bx0 - ax1, ax0 - bx1) >= max(by0 - ay1, ay0 - by1):
                alta = 0 if ax0 > bx0 else 1     # lado a lado: derecha arriba
            else:
                alta = 0 if ay0 > by0 else 1     # una sobre otra
    return [grupos[1 - alta], grupos[alta]]


def _alinear(cajas, tipos, baja, alta):
    """Mueve la planta alta para que su escalera coincida con la de abajo."""
    def escalera(grupo):
        return next((i for i in grupo if tipos[i] == "escalera"), None)

    abajo, arriba = escalera(baja), escalera(alta)
    if abajo is not None and arriba is not None:
        dx = cajas[abajo][0] - cajas[arriba][0]
        dy = cajas[abajo][1] - cajas[arriba][1]
    else:
        dx = min(cajas[i][0] for i in baja) - min(cajas[i][0] for i in alta)
        dy = min(cajas[i][1] for i in baja) - min(cajas[i][1] for i in alta)

    for i in alta:
        cajas[i] = [
            round(v + (dx if k % 2 == 0 else dy), 2)
            for k, v in enumerate(cajas[i])
        ]

    if abajo is not None and arriba is not None and all(
        abs(
            (cajas[abajo][k + 2] - cajas[abajo][k])
            - (cajas[arriba][k + 2] - cajas[arriba][k])
        ) < 0.6
        for k in (0, 1)
    ):
        cajas[arriba] = list(cajas[abajo])
        _quitar_solapes([cajas[i] for i in alta])


# ==========================================
# FUNCIÓN PRINCIPAL
# ==========================================

def importar_documento(documento):
    """
    Distribuciones (una por planta, la baja primero), ancho y largo del
    terreno, y notas para el usuario.
    """
    segmentos, contornos, textos = _extraer(documento)
    if not segmentos and not contornos:
        raise ValueError(SIN_HABITACIONES)

    factor, nota_unidades = _escala(documento, segmentos)
    giro = _giro([
        (x1 * factor, y1 * factor, x2 * factor, y2 * factor, *resto)
        for x1, y1, x2, y2, *resto in segmentos
    ])
    transformar = _transformador(factor, giro)

    segmentos = [
        (*transformar(x1, y1), *transformar(x2, y2), *resto)
        for x1, y1, x2, y2, *resto in segmentos
    ]
    contornos = [
        ([transformar(x, y) for x, y in puntos], capa, en_bloque)
        for puntos, capa, en_bloque in contornos
    ]
    textos = [(*transformar(x, y), texto) for x, y, texto in textos]

    contornos_ok, terreno = _por_contornos(contornos)
    por_contornos = [(p, p) for p in contornos_ok]
    por_muros = _por_muros(segmentos)

    def puntuacion(pares):
        tipos, _ = _nombrar([p for p, _ in pares], textos)
        nombrados = sum(t != "ambiente" for t in tipos)
        return nombrados, sum(p.area for p, _ in pares)

    usar_contornos = len(por_contornos) >= 2 or not por_muros
    if len(por_contornos) >= 2 and len(por_muros) >= 2:
        (n_c, a_c), (n_m, a_m) = puntuacion(por_contornos), puntuacion(por_muros)
        usar_contornos = n_c > n_m or (n_c == n_m and a_c >= 0.8 * a_m)

    pares = por_contornos if usar_contornos else por_muros
    if not pares:
        raise ValueError(SIN_HABITACIONES)

    tipos, desconocidos = _nombrar([p for p, _ in pares], textos)
    margen = 0.0 if usar_contornos else CIERRE_VANOS_M

    cajas, perdidas = [], []
    for _, forma in pares:
        caja, perdida = _rectangulo(forma, margen)
        cajas.append(caja)
        perdidas.append(perdida)

    _cerrar_juntas(cajas)

    plantas = _separar_plantas(cajas, tipos, textos)
    if len(plantas) == 2:
        _alinear(cajas, tipos, *plantas)

    # Terreno: el dibujado si contiene la casa; si no, la casa más un margen.
    x0 = min(c[0] for c in cajas)
    y0 = min(c[1] for c in cajas)
    x1 = max(c[2] for c in cajas)
    y1 = max(c[3] for c in cajas)
    notas = []
    if terreno is not None and len(plantas) == 1 and terreno.buffer(0.05).covers(
        box(x0, y0, x1, y1)
    ):
        tx0, ty0, tx1, ty1 = terreno.bounds
    else:
        m = MARGEN_TERRENO_M
        tx0, ty0, tx1, ty1 = x0 - m, y0 - m, x1 + m, y1 + m
        notas.append(
            "No encontré el terreno en el dibujo: usé el contorno de la casa "
            f"más {m:g} m por lado."
        )

    # Ids únicos en toda la casa; la escalera es común a las dos plantas.
    contadores = defaultdict(int)
    distribuciones = []
    ids = {}
    for numero_planta, grupo in enumerate(plantas):
        escaleras = 0
        distribucion = []
        for i in sorted(grupo, key=lambda i: (-cajas[i][3], cajas[i][0])):
            base = normalizar_nombre(tipos[i])
            if base == "escalera":
                escaleras += 1
                identificador = f"escalera_{escaleras}"
            else:
                contadores[base] += 1
                identificador = f"{base}_{contadores[base]}"
            ids[i] = identificador
            cx0, cy0, cx1, cy1 = cajas[i]
            distribucion.append({
                "id": identificador,
                "nombre": tipos[i],
                "x": round(cx0 - tx0, 3),
                "y": round(cy0 - ty0, 3),
                "ancho": round(cx1 - cx0, 3),
                "largo": round(cy1 - cy0, 3),
            })
        distribuciones.append(distribucion)

    metodo = "sus contornos" if usar_contornos else "los muros"
    notas.insert(0, (
        f"Importé el plano de otro programa: {len(cajas)} habitaciones, "
        f"detectadas por {metodo}"
        + (" en dos plantas" if len(plantas) == 2 else "")
        + ". Los muros, puertas, ventanas y muebles se dibujaron de nuevo."
    ))
    if nota_unidades:
        notas.insert(1, nota_unidades)
    if giro:
        notas.append(f"El dibujo estaba girado {abs(giro):.0f}°; lo enderecé.")

    for i, perdida in enumerate(perdidas):
        if perdida >= 0.3:
            notas.append(
                f"{_legible(ids[i])} tenía forma irregular; la aproximé a un "
                f"rectángulo ({perdida:.1f} m² menos)."
            )

    sin_nombre = [_legible(ids[i]) for i in range(len(cajas)) if tipos[i] == "ambiente"]
    if sin_nombre:
        notas.append(
            "No reconocí el uso de " + ", ".join(sin_nombre) + ". Puedes "
            "renombrarlos, por ejemplo «llama cocina al ambiente 1»."
        )
    if desconocidos:
        notas.append(
            "Textos que no reconocí como ambientes: "
            + ", ".join(f"«{t}»" for t in desconocidos[:6]) + "."
        )

    return (
        distribuciones,
        round(tx1 - tx0, 3),
        round(ty1 - ty0, 3),
        notas,
    )


def importar_dxf(ruta):
    """Como `importar_documento`, a partir de la ruta del archivo."""
    return importar_documento(leer_dxf(ruta))
