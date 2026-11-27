"""
Lámina en PDF para presentar o imprimir el plano: una hoja A3 por planta, a
escala, con cuadro de áreas, norte, escala gráfica y membrete.

Los símbolos de puertas, ventanas y muebles son los mismos del DXF.
"""

import io
import math
from datetime import date

import ezdxf
from ezdxf import path as ezpath
from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from src.cad.dxf_aberturas import dibujar_puerta, dibujar_ventana
from src.cad.dxf_base import APP_ID
from src.cad.dxf_generator import (
    dibujar_escalera,
    dibujar_etiqueta_ambiente,
    obtener_poligonos,
)
from src.cad.dxf_mobiliario import dibujar_mobiliario
from src.ui.plano_svg import etiquetas_ambientes
from src.utils.texto import normalizar_nombre

PAGINA = landscape(A3)
MARGEN = 10 * mm
ANCHO_PANEL = 105 * mm
# Espacio alrededor del dibujo para las cotas y el rótulo de la calle.
BORDE_LATERAL = 13 * mm
BORDE_INFERIOR = 15 * mm
BORDE_SUPERIOR = 3 * mm
ALTO_MEMBRETE = 66 * mm
ALTO_REFERENCIAS = 34 * mm
ALTO_FILA = 6 * mm
ALTO_FILA_MINIMO = 3.4 * mm
ESCALAS = (50, 75, 100, 125, 150, 200, 250, 300, 400, 500, 750, 1000)

NEGRO = (0.08, 0.08, 0.08)
GRIS = (0.45, 0.45, 0.45)
GRIS_CLARO = (0.78, 0.78, 0.78)
NORMAL, NEGRITA = "Helvetica", "Helvetica-Bold"

AVISO = (
    "Anteproyecto generado automáticamente. Medidas y áreas entre ejes de "
    "muro. No reemplaza el expediente firmado por un profesional."
)
# Giro (antihorario) de la flecha; el frente (calle) queda abajo.
GIRO_NORTE = {"fondo": 0, "izquierda": 90, "frente": 180, "derecha": 270}


def titulos_de_plantas(cantidad: int) -> list[str]:
    if cantidad == 1:
        return ["PLANTA ÚNICA"]
    altas = (
        ["PLANTA ALTA"] if cantidad == 2
        else [f"PLANTA ALTA {i}" for i in range(1, cantidad)]
    )
    return ["PLANTA BAJA", *altas]


def elegir_escala(ancho_m: float, largo_m: float, ancho_pt: float, alto_pt: float) -> int:
    """La escala normalizada más grande con la que el terreno entra en la hoja."""
    necesaria = max(ancho_m * 1000 * mm / ancho_pt, largo_m * 1000 * mm / alto_pt)
    for escala in ESCALAS:
        if escala >= necesaria - 1e-9:
            return escala
    return int(math.ceil(necesaria / 500) * 500)


def _terreno(piso) -> tuple[float, float, float, float]:
    terreno = piso.geometrias.get("terreno")
    if terreno is not None and hasattr(terreno, "bounds"):
        return terreno.bounds
    cajas = [a["poligono"].bounds for a in piso.geometrias["ambientes"]]
    return (
        min(0, *(c[0] for c in cajas)), min(0, *(c[1] for c in cajas)),
        max(c[2] for c in cajas), max(c[3] for c in cajas),
    )


def _area(ambiente) -> float:
    return ambiente.get("area_m2", ambiente["poligono"].area)


def _recortar(texto: str, fuente: str, tamano: float, ancho: float) -> str:
    if stringWidth(texto, fuente, tamano) <= ancho:
        return texto
    while texto and stringWidth(texto + "…", fuente, tamano) > ancho:
        texto = texto[:-1]
    return texto.rstrip() + "…"


def _en_lineas(texto: str, fuente: str, tamano: float, ancho: float, maximo: int) -> list[str]:
    """Parte el texto en hasta `maximo` líneas; lo que sobre se recorta."""
    lineas: list[str] = []
    actual = ""
    palabras = texto.split()
    for i, palabra in enumerate(palabras):
        candidata = f"{actual} {palabra}".strip()
        if actual and stringWidth(candidata, fuente, tamano) > ancho:
            if len(lineas) == maximo - 1:
                actual = " ".join([actual, *palabras[i:]])
                break
            lineas.append(actual)
            candidata = palabra
        actual = candidata
    if actual:
        lineas.append(actual)
    return [_recortar(linea, fuente, tamano, ancho) for linea in lineas]


class _Dibujo:
    """Lienzo en metros: convierte coordenadas del plano a puntos de la hoja."""

    def __init__(self, c, escala: int, x0: float, y0: float, minx: float, miny: float):
        self.c = c
        self.pt_por_m = 1000 * mm / escala
        self.x0, self.y0, self.minx, self.miny = x0, y0, minx, miny

    def punto(self, x: float, y: float) -> tuple[float, float]:
        return (
            self.x0 + (x - self.minx) * self.pt_por_m,
            self.y0 + (y - self.miny) * self.pt_por_m,
        )

    def trazo(self, puntos, cerrar: bool = False) -> None:
        camino = self.c.beginPath()
        camino.moveTo(*self.punto(*puntos[0]))
        for p in puntos[1:]:
            camino.lineTo(*self.punto(*p))
        if cerrar:
            camino.close()
        self.c.drawPath(camino, stroke=1, fill=0)

    def relleno(self, geometria) -> None:
        camino = self.c.beginPath()
        for poligono in obtener_poligonos(geometria):
            for anillo in (poligono.exterior, *poligono.interiors):
                puntos = list(anillo.coords)
                camino.moveTo(*self.punto(*puntos[0][:2]))
                for p in puntos[1:]:
                    camino.lineTo(*self.punto(*p[:2]))
                camino.close()
        # Par-impar: los huecos quedan vacíos.
        self.c.drawPath(camino, stroke=0, fill=1, fillMode=0)

    def entidades(self, entidades, grosor: float, color) -> None:
        """Entidades DXF (líneas, polilíneas, arcos, elipses y bloques)."""
        for e in entidades:
            if e.dxftype() == "INSERT":
                self.entidades(e.virtual_entities(), grosor, color)
                continue
            if e.dxftype() == "TEXT":
                continue
            puntos = [(v.x, v.y) for v in ezpath.make_path(e).flattening(0.005)]
            if len(puntos) > 1:
                self.c.setStrokeColorRGB(*color)
                self.c.setLineWidth(grosor)
                self.trazo(puntos)


def _borrador():
    """Documento DXF temporal donde se generan los símbolos."""
    doc = ezdxf.new("R2010")
    doc.appids.new(APP_ID)
    return doc.modelspace()


def _dibujar_simbolos(dibujo: _Dibujo, piso) -> None:
    if (piso.mobiliario or {}).get("mobiliario"):
        msp = _borrador()
        dibujar_mobiliario(msp, piso.mobiliario)
        dibujo.entidades(msp, 0.35, GRIS)

    msp = _borrador()
    for ambiente in piso.geometrias["ambientes"]:
        if normalizar_nombre(ambiente["nombre"]).startswith("escalera"):
            dibujar_escalera(msp, ambiente["poligono"])
    dibujo.entidades(msp, 0.4, GRIS)

    muros = (piso.aberturas or {}).get("muros_con_aberturas")
    if muros is None:
        muros = (piso.muros or {}).get("todos_los_muros")
    if muros is not None:
        dibujo.c.setFillColorRGB(*NEGRO)
        dibujo.relleno(muros)

    aberturas = piso.aberturas or {}
    msp = _borrador()
    for ventana in aberturas.get("ventanas", []):
        dibujar_ventana(msp, ventana)
    for puerta in aberturas.get("puertas", []):
        dibujar_puerta(msp, puerta)
    dibujo.entidades(msp, 0.5, NEGRO)


def _dibujar_etiquetas(dibujo: _Dibujo, piso) -> None:
    c = dibujo.c
    nombres = etiquetas_ambientes(piso.distribucion)
    muebles = (piso.mobiliario or {}).get("mobiliario", [])

    for ambiente in piso.geometrias["ambientes"]:
        nombre = nombres.get(ambiente["id"], ambiente["nombre"])
        poligono = ambiente["poligono"]
        propios = [
            {**m, "ambiente": nombre} for m in muebles
            if poligono.buffer(0.01).covers(m["geometria"])
        ]
        # Misma búsqueda de hueco libre que en el DXF.
        msp = _borrador()
        dibujar_etiqueta_ambiente(
            msp, {**ambiente, "nombre": nombre}, {"mobiliario": propios}
        )
        arriba, abajo = [t.get_placement()[1] for t in msp.query("TEXT")]
        x, y = dibujo.punto(arriba.x, (arriba.y + abajo.y) / 2)

        minx, miny, maxx, maxy = poligono.bounds
        disponible = (maxx - minx) * dibujo.pt_por_m * 0.85
        texto = nombre.upper()
        tamano = 8.0
        while tamano > 4.5 and stringWidth(texto, NEGRITA, tamano) > disponible:
            tamano -= 0.25
        menor = tamano * 0.85
        lineas = [(texto, NEGRITA, tamano), (f"{_area(ambiente):.2f} m²", NORMAL, menor)]
        # Las medidas solo si el ambiente da para tres líneas.
        medidas = f"{maxx - minx:.2f} × {maxy - miny:.2f} m"
        if (stringWidth(medidas, NORMAL, menor) <= disponible
                and (maxy - miny) * dibujo.pt_por_m > tamano * 4):
            lineas.append((medidas, NORMAL, menor))

        ancho = max(stringWidth(*linea) for linea in lineas)
        alto = tamano * len(lineas)
        # Fondo blanco para que se lea sobre muebles y líneas.
        c.setFillColorRGB(1, 1, 1)
        c.rect(x - ancho / 2 - 1, y - alto / 2, ancho + 2, alto, stroke=0, fill=1)
        c.setFillColorRGB(*NEGRO)
        base = y + alto / 2 - tamano * 0.8
        for contenido, fuente, cuerpo in lineas:
            c.setFont(fuente, cuerpo)
            c.drawCentredString(x, base, contenido)
            base -= tamano


def _cota(c, p, q, texto: str) -> None:
    """Cota exterior entre dos puntos de la hoja (horizontal o vertical)."""
    c.setStrokeColorRGB(*NEGRO)
    c.setLineWidth(0.4)
    c.line(*p, *q)
    for x, y in (p, q):
        c.line(x - 2.2, y - 2.2, x + 2.2, y + 2.2)
    c.saveState()
    c.translate((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
    if abs(p[0] - q[0]) < 1e-6:
        c.rotate(90)
    c.setFillColorRGB(*NEGRO)
    c.setFont(NORMAL, 7.5)
    c.drawCentredString(0, 2.5, texto)
    c.restoreState()


def _dibujar_planta(c, piso, escala: int, area, retiros, con_calle: bool) -> None:
    x_area, y_area, ancho_area, alto_area = area
    minx, miny, maxx, maxy = _terreno(piso)
    pt_por_m = 1000 * mm / escala
    ancho, alto = (maxx - minx) * pt_por_m, (maxy - miny) * pt_por_m
    x0 = x_area + (ancho_area - ancho) / 2
    y0 = y_area + (alto_area - alto) / 2
    dibujo = _Dibujo(c, escala, x0, y0, minx, miny)

    # Límite del terreno (raya y punto) y retiros (trazos).
    c.saveState()
    c.setStrokeColorRGB(*GRIS)
    c.setLineWidth(0.6)
    c.setDash([8, 2, 1.5, 2])
    c.rect(x0, y0, ancho, alto, stroke=1, fill=0)
    if retiros and any(retiros.values()):
        c.setDash([3, 3])
        c.setLineWidth(0.4)
        dibujo.trazo([
            (minx + retiros["izquierdo"], miny + retiros["frontal"]),
            (maxx - retiros["derecho"], miny + retiros["frontal"]),
            (maxx - retiros["derecho"], maxy - retiros["posterior"]),
            (minx + retiros["izquierdo"], maxy - retiros["posterior"]),
        ], cerrar=True)
        c.setFillColorRGB(*GRIS)
        c.setFont(NORMAL, 6)
        rx, ry = dibujo.punto(
            minx + retiros["izquierdo"], miny + retiros["frontal"]
        )
        c.drawString(rx + 2, ry - 8, "Límite de retiros")
    c.restoreState()

    _dibujar_simbolos(dibujo, piso)
    _dibujar_etiquetas(dibujo, piso)

    _cota(c, (x0, y0 - 5 * mm), (x0 + ancho, y0 - 5 * mm), f"{maxx - minx:.2f} m")
    _cota(c, (x0 - 5 * mm, y0), (x0 - 5 * mm, y0 + alto), f"{maxy - miny:.2f} m")
    if con_calle:
        c.setFillColorRGB(*GRIS)
        c.setFont(NEGRITA, 8)
        c.drawCentredString(x0 + ancho / 2, y0 - 11 * mm, "CALLE")


def _cuadro_de_areas(c, piso, pisos, x, y_superior, ancho, alto) -> None:
    """Ambientes de la planta con sus medidas; totales al final."""
    nombres = etiquetas_ambientes(piso.distribucion)
    ambientes = piso.geometrias["ambientes"]

    totales = [("Total de esta planta", sum(map(_area, ambientes)))]
    if len(pisos) > 1:
        totales.append((
            f"Total de las {len(pisos)} plantas",
            sum(_area(a) for p in pisos for a in p.geometrias["ambientes"]),
        ))

    libre = alto - 17 * mm
    filas = len(ambientes) + len(totales)
    alto_fila = max(ALTO_FILA_MINIMO, min(ALTO_FILA, libre / filas))
    caben = int(libre / alto_fila + 1e-6) - len(totales)
    # Si no entran todos, la última fila resume los que faltan.
    visibles = ambientes if len(ambientes) <= caben else ambientes[:caben - 1]
    tamano = min(8.5, alto_fila * 0.55)

    col_area = x + ancho - 3 * mm
    col_medidas = x + ancho - 24 * mm

    c.setFillColorRGB(*NEGRO)
    c.setFont(NEGRITA, 11)
    c.drawString(x + 3 * mm, y_superior - 6 * mm, "CUADRO DE ÁREAS")
    y = y_superior - 12 * mm
    c.setFont(NEGRITA, 7.5)
    c.drawString(x + 3 * mm, y, "Ambiente")
    c.drawRightString(col_medidas, y, "Medidas (m)")
    c.drawRightString(col_area, y, "Área (m²)")
    y -= 2 * mm

    def linea(y, grosor, color):
        c.setStrokeColorRGB(*color)
        c.setLineWidth(grosor)
        c.line(x, y, x + ancho, y)

    def fila(y, nombre, medidas, area, fuente=NORMAL):
        base = y - alto_fila * 0.7
        c.setFillColorRGB(*NEGRO)
        c.setFont(fuente, tamano)
        c.drawString(x + 3 * mm, base, _recortar(nombre, fuente, tamano, 52 * mm))
        c.drawRightString(col_medidas, base, medidas)
        c.drawRightString(col_area, base, area)

    linea(y, 0.6, NEGRO)
    for a in visibles:
        minx, miny, maxx, maxy = a["poligono"].bounds
        fila(
            y, nombres.get(a["id"], a["nombre"]),
            f"{maxx - minx:.2f} × {maxy - miny:.2f}", f"{_area(a):.2f}",
        )
        y -= alto_fila
        linea(y, 0.25, GRIS_CLARO)

    if len(visibles) < len(ambientes):
        resto = ambientes[len(visibles):]
        fila(y, f"Otros {len(resto)} ambientes", "", f"{sum(map(_area, resto)):.2f}")
        y -= alto_fila

    linea(y, 0.6, NEGRO)
    for nombre, total in totales:
        fila(y, nombre, "", f"{total:.2f}", NEGRITA)
        y -= alto_fila


def _norte_y_escala(c, escala: int, norte, x, y, ancho) -> None:
    if norte in GIRO_NORTE:
        cx, cy, r = x + ancho - 17 * mm, y + 17 * mm, 9 * mm
        c.saveState()
        c.translate(cx, cy)
        c.rotate(GIRO_NORTE[norte])
        c.setStrokeColorRGB(*NEGRO)
        c.setLineWidth(0.6)
        c.circle(0, 0, r, stroke=1, fill=0)
        c.setFillColorRGB(*NEGRO)
        flecha = c.beginPath()
        flecha.moveTo(0, r * 0.92)
        flecha.lineTo(r * 0.35, -r * 0.45)
        flecha.lineTo(0, -r * 0.2)
        flecha.lineTo(-r * 0.35, -r * 0.45)
        flecha.close()
        c.drawPath(flecha, stroke=0, fill=1)
        c.restoreState()
        # La letra va en la punta, siempre derecha.
        angulo = math.radians(GIRO_NORTE[norte] + 90)
        c.setFillColorRGB(*NEGRO)
        c.setFont(NEGRITA, 9)
        c.drawCentredString(
            cx + math.cos(angulo) * (r + 4 * mm),
            cy + math.sin(angulo) * (r + 4 * mm) - 3, "N",
        )

    # Escala gráfica: cinco tramos de 1, 2, 5… metros en menos de 58 mm.
    mm_por_m = 1000 / escala
    tramo = next((t for t in (50, 20, 10, 5, 2, 1) if 5 * t * mm_por_m <= 58), 1)
    paso = tramo * mm_por_m * mm
    bx, by = x + 4 * mm, y + 13 * mm
    c.setStrokeColorRGB(*NEGRO)
    c.setLineWidth(0.5)
    for i in range(5):
        c.setFillColorRGB(*(NEGRO if i % 2 == 0 else (1, 1, 1)))
        c.rect(bx + i * paso, by, paso, 2 * mm, stroke=1, fill=1)
    c.setFillColorRGB(*NEGRO)
    c.setFont(NORMAL, 7)
    for i in range(6):
        c.drawCentredString(bx + i * paso, by - 3.5 * mm, str(i * tramo))
    c.drawString(bx + 5 * paso + 2.5 * mm, by - 3.5 * mm, "m")
    c.setFont(NEGRITA, 8)
    c.drawString(bx, by + 5 * mm, "ESCALA GRÁFICA")


def _membrete(c, x, y, ancho, nombre, titulo, escala, terreno, fecha, hoja, hojas) -> None:
    interior = ancho - 6 * mm
    c.setFillColorRGB(*GRIS)
    c.setFont(NORMAL, 7)
    c.drawString(x + 3 * mm, y + ALTO_MEMBRETE - 5 * mm, "PROYECTO")
    c.setFillColorRGB(*NEGRO)
    c.setFont(NEGRITA, 10.5)
    base = y + ALTO_MEMBRETE - 10.5 * mm
    for linea in _en_lineas(nombre, NEGRITA, 10.5, interior, 3):
        c.drawString(x + 3 * mm, base, linea)
        base -= 4.6 * mm

    c.setFont(NEGRITA, 15)
    c.drawString(x + 3 * mm, y + 36 * mm, titulo)

    c.setStrokeColorRGB(*NEGRO)
    c.setLineWidth(0.6)
    for altura in (33 * mm, 22 * mm, 11 * mm):
        c.line(x, y + altura, x + ancho, y + altura)
    c.line(x + ancho / 2, y + 11 * mm, x + ancho / 2, y + 33 * mm)

    minx, miny, maxx, maxy = terreno
    datos = (
        (0, 22, "ESCALA (impresa en A3 al 100 %)", f"1:{escala}"),
        (0.5, 22, "TERRENO", f"{maxx - minx:.2f} × {maxy - miny:.2f} m"),
        (0, 11, "FECHA", fecha.strftime("%d/%m/%Y")),
        (0.5, 11, "LÁMINA", f"A-{hoja:02d}  ({hoja} de {hojas})"),
    )
    for columna, altura, rotulo, valor in datos:
        cx = x + columna * ancho + 3 * mm
        c.setFillColorRGB(*GRIS)
        c.setFont(NORMAL, 7)
        c.drawString(cx, y + (altura + 7) * mm, rotulo)
        c.setFillColorRGB(*NEGRO)
        c.setFont(NEGRITA, 10)
        c.drawString(cx, y + (altura + 2.5) * mm, valor)

    c.setFillColorRGB(*GRIS)
    c.setFont(NORMAL, 6.5)
    base = y + 7 * mm
    for linea in _en_lineas(AVISO, NORMAL, 6.5, interior, 3):
        c.drawString(x + 3 * mm, base, linea)
        base -= 3 * mm


def generar_lamina(resultado, nombre: str = "Proyecto", requerimientos=None,
                   fecha: date | None = None) -> bytes:
    """
    PDF con una hoja A3 por planta de `resultado` (de una o varias plantas).
    Con `requerimientos` se añaden el norte, los retiros y la calle.
    """
    pisos = getattr(resultado, "pisos", [resultado])
    fecha = fecha or date.today()
    norte = getattr(requerimientos, "norte", None)
    retiros = getattr(requerimientos, "retiros", None)
    retiros = retiros.model_dump() if retiros else None

    ancho_hoja, alto_hoja = PAGINA
    x_panel = ancho_hoja - MARGEN - ANCHO_PANEL
    area = (
        MARGEN + BORDE_LATERAL,
        MARGEN + BORDE_INFERIOR,
        x_panel - MARGEN - 2 * BORDE_LATERAL,
        alto_hoja - 2 * MARGEN - BORDE_INFERIOR - BORDE_SUPERIOR,
    )
    # La misma escala en todas las plantas.
    cajas = [_terreno(p) for p in pisos]
    escala = elegir_escala(
        max(c[2] - c[0] for c in cajas), max(c[3] - c[1] for c in cajas),
        area[2], area[3],
    )

    salida = io.BytesIO()
    c = canvas.Canvas(salida, pagesize=PAGINA)
    c.setTitle(nombre)
    c.setCreator("Agente Arquitectónico")

    titulos = titulos_de_plantas(len(pisos))
    for hoja, (piso, titulo) in enumerate(zip(pisos, titulos), start=1):
        _dibujar_planta(
            c, piso, escala, area,
            # Los retiros se miden en la planta baja.
            retiros if hoja == 1 else None,
            requerimientos is not None,
        )

        y_referencias = MARGEN + ALTO_MEMBRETE
        y_cuadro = y_referencias + ALTO_REFERENCIAS
        _cuadro_de_areas(
            c, piso, pisos, x_panel, alto_hoja - MARGEN, ANCHO_PANEL,
            alto_hoja - MARGEN - y_cuadro,
        )
        _norte_y_escala(c, escala, norte, x_panel, y_referencias, ANCHO_PANEL)
        _membrete(
            c, x_panel, MARGEN, ANCHO_PANEL, nombre, titulo, escala,
            _terreno(piso), fecha, hoja, len(pisos),
        )

        c.setStrokeColorRGB(*NEGRO)
        c.setLineWidth(1.2)
        c.rect(MARGEN, MARGEN, ancho_hoja - 2 * MARGEN, alto_hoja - 2 * MARGEN)
        c.line(x_panel, MARGEN, x_panel, alto_hoja - MARGEN)
        c.setLineWidth(0.6)
        for altura in (y_referencias, y_cuadro):
            c.line(x_panel, altura, ancho_hoja - MARGEN, altura)
        c.showPage()

    c.save()
    return salida.getvalue()
