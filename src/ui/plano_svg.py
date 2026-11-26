"""Vista previa del plano como SVG (función pura: no depende de Streamlit)."""

from html import escape

from src.geometry.medidas import medidas_de_ambiente
from src.utils.texto import normalizar_nombre

CAPAS_POR_DEFECTO = frozenset(
    {"etiquetas", "puertas", "ventanas", "muebles", "medidas", "cotas", "cambios"}
)

FONDO = "#0F2740"
MALLA = "#1B4166"
LIMITE_TERRENO = "#5B86AB"
MURO = "#C9E6FF"
PUERTA = "#FBBF24"
VENTANA = "#7DD3FC"
MUEBLE = "#9CC9EA"
TEXTO = "#E6F1FF"
TEXTO_SUAVE = "#8FB3D1"
MEDIDA = "#FDE68A"
COLOR_POR_DEFECTO = "#7DD3FC"

# Prefijo del nombre normalizado (sin tildes) -> color de la habitación.
COLORES = {
    "sala": "#38BDF8",
    "comedor": "#22D3EE",
    "cocina": "#FBBF24",
    "dormitorio": "#A78BFA",
    "bano": "#34D399",
    "estudio": "#F472B6",
    "oficina": "#F472B6",
    "lavanderia": "#60A5FA",
    "garaje": "#94A3B8",
    "deposito": "#94A3B8",
    "terraza": "#86EFAC",
    "jardin": "#86EFAC",
    "pasillo": "#64748B",
    "escalera": "#64748B",
    "closet": "#64748B",
}

FUENTE = "Segoe UI, Inter, system-ui, sans-serif"


def color_de_ambiente(nombre: str) -> str:
    normalizado = normalizar_nombre(nombre)
    for prefijo, color in COLORES.items():
        if normalizado.startswith(prefijo):
            return color
    return COLOR_POR_DEFECTO


def _n(valor: float) -> str:
    return f"{valor:.3f}".rstrip("0").rstrip(".")


def _limites(resultado) -> tuple[float, float, float, float]:
    terreno = resultado.geometrias.get("terreno")
    if terreno is not None and hasattr(terreno, "bounds"):
        return terreno.bounds
    ambientes = resultado.distribucion
    return (
        min(a["x"] for a in ambientes),
        min(a["y"] for a in ambientes),
        max(a["x"] + a["ancho"] for a in ambientes),
        max(a["y"] + a["largo"] for a in ambientes),
    )


def etiquetas_ambientes(distribucion: list) -> dict:
    """
    Id -> texto visible; numera los tipos que se repiten y los que no son el
    primero (en dos plantas, "Baño 2" puede ser el único de la suya).
    """
    repetidos: dict[str, int] = {}
    for a in distribucion:
        repetidos[a["nombre"]] = repetidos.get(a["nombre"], 0) + 1

    etiquetas = {}
    for a in distribucion:
        base = a["nombre"].capitalize()
        numero = str(a["id"]).rsplit("_", 1)[-1]
        if repetidos[a["nombre"]] > 1 or (numero.isdigit() and numero != "1"):
            base = f"{base} {numero}"
        etiquetas[a["id"]] = base
    return etiquetas


def _path_de_geometria(geometria, convertir) -> str:
    """Convierte polígonos de Shapely en un path SVG (con huecos)."""
    partes = []
    poligonos = getattr(geometria, "geoms", [geometria])
    for poligono in poligonos:
        if getattr(poligono, "geom_type", "") != "Polygon" or poligono.is_empty:
            continue
        for anillo in [poligono.exterior, *poligono.interiors]:
            puntos = [convertir(x, y) for x, y in anillo.coords]
            partes.append("M" + " L".join(puntos) + " Z")
    return " ".join(partes)


MARGEN_IZQ, MARGEN_SUP, MARGEN_DER, MARGEN_INF = 1.7, 0.6, 0.6, 1.7
FONDO_PAGINA = "#0A1A2F"
CAMBIO = "#FBBF24"


def _limites_vivienda(resultado) -> tuple[float, float, float, float]:
    ambientes = resultado.distribucion
    return (
        min(a["x"] for a in ambientes),
        min(a["y"] for a in ambientes),
        max(a["x"] + a["ancho"] for a in ambientes),
        max(a["y"] + a["largo"] for a in ambientes),
    )


def _marco(resultado, enfocar: bool) -> tuple[float, float, float, float]:
    """Zona que se muestra: el terreno completo o solo la vivienda."""
    return _limites_vivienda(resultado) if enfocar else _limites(resultado)


def proporcion_vista(resultado, enfocar: bool = False) -> float:
    """Alto / ancho de la vista (incluye los márgenes de las cotas)."""
    minx, miny, maxx, maxy = _marco(resultado, enfocar)
    return ((maxy - miny) + MARGEN_SUP + MARGEN_INF) / (
        (maxx - minx) + MARGEN_IZQ + MARGEN_DER
    )


def fraccion_ocupada(resultado) -> float:
    """Qué parte del terreno ocupa la vivienda (0 a 1, por su rectángulo envolvente)."""
    tx0, ty0, tx1, ty1 = _limites(resultado)
    vx0, vy0, vx1, vy1 = _limites_vivienda(resultado)
    return ((vx1 - vx0) * (vy1 - vy0)) / ((tx1 - tx0) * (ty1 - ty0))


def _flecha_de_norte(norte: str) -> str:
    """Rosa mínima en el margen superior izquierdo."""
    giro = {"fondo": 0, "derecha": 90, "frente": 180, "izquierda": 270}[norte]
    dx, dy = {0: (0, -1), 90: (1, 0), 180: (0, 1), 270: (-1, 0)}[giro]
    return (
        '<g class="norte" transform="translate(-1.1 0.15)">'
        "<title>Norte</title>"
        f'<circle r="0.34" fill="none" stroke="{TEXTO_SUAVE}" stroke-width="0.03"/>'
        f'<path d="M0 -0.3L0.12 0.14L0 0.06L-0.12 0.14Z" fill="{CAMBIO}" '
        f'transform="rotate({giro})"/>'
        f'<text x="{_n(dx * 0.5)}" y="{_n(dy * 0.5 + 0.09)}" text-anchor="middle" '
        f'font-size="0.26" font-weight="bold" fill="{TEXTO}">N</text></g>'
    )


def generar_svg_plano(
    resultado,
    capas=CAPAS_POR_DEFECTO,
    uid: str = "plano",
    ocupar_contenedor: bool = False,
    enfocar: bool = False,
    resaltar=frozenset(),
    fondo_pagina: bool = False,
    norte: str | None = None,
    retiros: dict | None = None,
) -> str:
    """SVG del plano de un piso (`ResultadoPlano`).

    El eje Y se invierte (como en el DXF, el origen queda abajo a la izquierda).
    `capas` admite: etiquetas, puertas, ventanas, muebles, medidas (ancho y
    largo de cada ambiente), cotas (de todo el plano) y cambios.
    Con `ocupar_contenedor` el SVG llena su contenedor (p. ej. un iframe de
    alto fijo) en lugar de calcular su alto por proporción.
    Con `enfocar` solo se muestra la vivienda (y las cotas miden la vivienda).
    `resaltar` son los ids de ambientes que cambiaron (capa "cambios").
    `fondo_pagina` añade un fondo sólido, para guardar el SVG como archivo.
    `norte` (lado del terreno donde está) dibuja la flecha de norte.
    `retiros` ({frontal, posterior, izquierdo, derecho}) marca el área edificable.
    """
    minx, miny, maxx, maxy = _marco(resultado, enfocar)
    ancho = maxx - minx
    largo = maxy - miny
    tx0, ty0, tx1, ty1 = _limites(resultado)

    def px(x: float) -> float:
        return x - minx

    def py(y: float) -> float:
        return maxy - y

    def punto(x: float, y: float) -> str:
        return f"{_n(px(x))} {_n(py(y))}"

    vb_ancho = ancho + MARGEN_IZQ + MARGEN_DER
    vb_alto = largo + MARGEN_SUP + MARGEN_INF

    if ocupar_contenedor:
        dimension = 'width="100%" height="100%" style="display:block"'
    else:
        dimension = 'width="100%" style="display:block;max-width:100%;height:auto"'

    malla = f"malla-{uid}"
    recorte = f"recorte-{uid}"
    terreno = (
        f'x="{_n(px(tx0))}" y="{_n(py(ty1))}" '
        f'width="{_n(tx1 - tx0)}" height="{_n(ty1 - ty0)}"'
    )
    s: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" role="img" '
        f'aria-label="Vista previa del plano" '
        f'viewBox="{_n(-MARGEN_IZQ)} {_n(-MARGEN_SUP)} {_n(vb_ancho)} {_n(vb_alto)}" '
        f'{dimension} font-family="{FUENTE}">',
        "<style>.amb rect{transition:fill-opacity .25s}"
        ".amb:hover rect{fill-opacity:.5}"
        ".cambio{animation:pulso 1.8s ease-in-out infinite}"
        "@keyframes pulso{0%,100%{stroke-opacity:1}50%{stroke-opacity:.25}}</style>",
        f'<defs><pattern id="{malla}" width="1" height="1" patternUnits="userSpaceOnUse">'
        f'<path d="M1 0H0V1" fill="none" stroke="{MALLA}" stroke-width="0.02"/>'
        f"</pattern>"
        f'<clipPath id="{recorte}"><rect x="{_n(-MARGEN_IZQ)}" y="{_n(-MARGEN_SUP)}" '
        f'width="{_n(vb_ancho)}" height="{_n(vb_alto)}"/></clipPath></defs>',
    ]

    if fondo_pagina:
        s.append(
            f'<rect x="{_n(-MARGEN_IZQ)}" y="{_n(-MARGEN_SUP)}" '
            f'width="{_n(vb_ancho)}" height="{_n(vb_alto)}" fill="{FONDO_PAGINA}"/>'
        )

    s += [
        f'<g clip-path="url(#{recorte})">',
        f'<rect {terreno} fill="{FONDO}"/>',
        f'<rect {terreno} fill="url(#{malla})"/>',
        f'<rect {terreno} fill="none" '
        f'stroke="{LIMITE_TERRENO}" stroke-width="0.05" stroke-dasharray="0.3 0.2"/>',
    ]

    if retiros and any(retiros.values()):
        s.append(
            f'<rect class="retiros" x="{_n(px(tx0 + retiros["izquierdo"]))}" '
            f'y="{_n(py(ty1 - retiros["posterior"]))}" '
            f'width="{_n(tx1 - tx0 - retiros["izquierdo"] - retiros["derecho"])}" '
            f'height="{_n(ty1 - ty0 - retiros["frontal"] - retiros["posterior"])}" '
            f'fill="none" stroke="{CAMBIO}" stroke-width="0.035" '
            f'stroke-dasharray="0.15 0.15" stroke-opacity="0.8">'
            f"<title>Límite de retiros</title></rect>"
        )

    etiquetas = etiquetas_ambientes(resultado.distribucion)

    for a in resultado.distribucion:
        color = color_de_ambiente(a["nombre"])
        area = a.get("area_m2", a["ancho"] * a["largo"])
        s.append(
            f'<g class="amb"><title>{escape(etiquetas[a["id"]])}: {area:.1f} m² '
            f'({a["ancho"]:.1f} × {a["largo"]:.1f} m)</title>'
            f'<rect x="{_n(px(a["x"]))}" y="{_n(py(a["y"] + a["largo"]))}" '
            f'width="{_n(a["ancho"])}" height="{_n(a["largo"])}" '
            f'fill="{color}" fill-opacity="0.22"/></g>'
        )

    muros = (resultado.aberturas or {}).get("muros_con_aberturas")
    if muros is None:
        muros = (resultado.muros or {}).get("todos_los_muros")
    if muros is not None:
        trazo = _path_de_geometria(muros, punto)
        if trazo:
            s.append(f'<path d="{trazo}" fill="{MURO}" fill-rule="evenodd"/>')

    if "cambios" in capas:
        for a in resultado.distribucion:
            if a["id"] in resaltar:
                s.append(
                    f'<rect class="cambio" x="{_n(px(a["x"]))}" '
                    f'y="{_n(py(a["y"] + a["largo"]))}" width="{_n(a["ancho"])}" '
                    f'height="{_n(a["largo"])}" fill="{CAMBIO}" fill-opacity="0.12" '
                    f'stroke="{CAMBIO}" stroke-width="0.1">'
                    f"<title>Modificado</title></rect>"
                )

    if "muebles" in capas and resultado.mobiliario:
        for m in resultado.mobiliario.get("mobiliario", []):
            s.append(
                f'<rect x="{_n(px(m["x"]))}" y="{_n(py(m["y"] + m["largo"]))}" '
                f'width="{_n(m["ancho"])}" height="{_n(m["largo"])}" '
                f'fill="{MUEBLE}" fill-opacity="0.08" stroke="{MUEBLE}" '
                f'stroke-opacity="0.6" stroke-width="0.025" class="mueble">'
                f'<title>{escape(str(m["tipo"]).replace("_", " ").capitalize())}</title></rect>'
            )

    def abertura(a: dict, color: str, clase: str, doble: bool) -> str:
        cx, cy = a["centro"]
        largo_a, grosor = a["ancho"], a["espesor_muro"]
        if a["orientacion"] == "vertical":
            x, y, w, h = cx - grosor / 2, cy - largo_a / 2, grosor, largo_a
        else:
            x, y, w, h = cx - largo_a / 2, cy - grosor / 2, largo_a, grosor
        figura = (
            f'<rect x="{_n(px(x))}" y="{_n(py(y + h))}" width="{_n(w)}" '
            f'height="{_n(h)}" fill="{color}" class="{clase}"/>'
        )
        if doble:
            if a["orientacion"] == "vertical":
                linea = (
                    f'<line x1="{_n(px(cx))}" y1="{_n(py(y + h))}" '
                    f'x2="{_n(px(cx))}" y2="{_n(py(y))}"'
                )
            else:
                linea = (
                    f'<line x1="{_n(px(x))}" y1="{_n(py(cy))}" '
                    f'x2="{_n(px(x + w))}" y2="{_n(py(cy))}"'
                )
            figura += f'{linea} stroke="{FONDO}" stroke-width="0.03"/>'
        return figura

    if "puertas" in capas:
        for p in (resultado.puertas or {}).get("puertas", []):
            s.append(abertura(p, PUERTA, "puerta", doble=False))

    if "ventanas" in capas:
        for v in (resultado.ventanas or {}).get("ventanas", []):
            s.append(abertura(v, VENTANA, "ventana", doble=True))

    if "medidas" in capas:
        for a in resultado.distribucion:
            medidas = medidas_de_ambiente(
                a["x"], a["y"], a["x"] + a["ancho"], a["y"] + a["largo"]
            )
            tamano = max(0.2, min(0.28, min(a["ancho"], a["largo"]) / 11))
            halo = f'paint-order="stroke" stroke="{FONDO}" stroke-width="0.09"'
            s.append('<g class="medida">')
            for eje, m in medidas.items():
                (x1, y1), (x2, y2) = m["inicio"], m["fin"]
                # Remates perpendiculares en los dos extremos.
                dx, dy = (0, 0.1) if eje == "ancho" else (0.1, 0)
                trazos = [((x1, y1), (x2, y2))] + [
                    ((x - dx, y - dy), (x + dx, y + dy))
                    for x, y in (m["inicio"], m["fin"])
                ]
                d = " ".join(f"M{punto(*p)} L{punto(*q)}" for p, q in trazos)
                # El borde oscuro hace visibles los remates sobre los muros.
                for color, grosor in ((FONDO, 0.07), (MEDIDA, 0.022)):
                    s.append(
                        f'<path d="{d}" fill="none" stroke="{color}" '
                        f'stroke-width="{grosor}" stroke-linecap="round"/>'
                    )
                tx, ty = px(m["texto"][0]), py(m["texto"][1])
                giro = "" if eje == "ancho" else f' transform="rotate(-90 {_n(tx)} {_n(ty)})"'
                s.append(
                    f'<text x="{_n(tx)}" y="{_n(ty + tamano * 0.35)}" '
                    f'text-anchor="middle" font-size="{_n(tamano)}" fill="{MEDIDA}" '
                    f'{halo}{giro}>{m["valor"]:.2f} m</text>'
                )
            s.append("</g>")

    if "etiquetas" in capas:
        for a in resultado.distribucion:
            menor = min(a["ancho"], a["largo"])
            tamano = max(0.26, min(0.44, menor / 9))
            cx = px(a["x"] + a["ancho"] / 2)
            cy = py(a["y"] + a["largo"] / 2)
            area = a.get("area_m2", a["ancho"] * a["largo"])
            mostrar_area = menor >= 1.8
            dy = -tamano * 0.15 if mostrar_area else tamano * 0.35
            halo = f'paint-order="stroke" stroke="{FONDO}" stroke-width="0.1"'
            s.append(
                f'<text x="{_n(cx)}" y="{_n(cy + dy)}" text-anchor="middle" '
                f'font-size="{_n(tamano)}" font-weight="600" fill="{TEXTO}" {halo}>'
                f"{escape(etiquetas[a['id']])}</text>"
            )
            if mostrar_area:
                s.append(
                    f'<text x="{_n(cx)}" y="{_n(cy + tamano * 1.0)}" '
                    f'text-anchor="middle" font-size="{_n(tamano * 0.8)}" '
                    f'fill="{TEXTO_SUAVE}" {halo}>{area:.1f} m²</text>'
                )

    if "cotas" in capas:
        yc = largo + 0.75
        xc = -0.75
        trazo_cota = f'stroke="{TEXTO_SUAVE}" stroke-width="0.04"'
        s.append(
            f'<g {trazo_cota} fill="none">'
            f'<line x1="0" y1="{_n(yc)}" x2="{_n(ancho)}" y2="{_n(yc)}"/>'
            f'<line x1="0" y1="{_n(yc - 0.18)}" x2="0" y2="{_n(yc + 0.18)}"/>'
            f'<line x1="{_n(ancho)}" y1="{_n(yc - 0.18)}" x2="{_n(ancho)}" y2="{_n(yc + 0.18)}"/>'
            f'<line x1="{_n(xc)}" y1="0" x2="{_n(xc)}" y2="{_n(largo)}"/>'
            f'<line x1="{_n(xc - 0.18)}" y1="0" x2="{_n(xc + 0.18)}" y2="0"/>'
            f'<line x1="{_n(xc - 0.18)}" y1="{_n(largo)}" x2="{_n(xc + 0.18)}" y2="{_n(largo)}"/>'
            f"</g>"
        )
        s.append(
            f'<text x="{_n(ancho / 2)}" y="{_n(yc + 0.62)}" text-anchor="middle" '
            f'font-size="0.42" fill="{TEXTO_SUAVE}">{ancho:.2f} m</text>'
        )
        s.append(
            f'<text transform="translate({_n(xc - 0.28)} {_n(largo / 2)}) rotate(-90)" '
            f'text-anchor="middle" font-size="0.42" fill="{TEXTO_SUAVE}">{largo:.2f} m</text>'
        )

    s.append("</g>")
    if norte:
        s.append(_flecha_de_norte(norte))
    s.append("</svg>")
    return "".join(s)
