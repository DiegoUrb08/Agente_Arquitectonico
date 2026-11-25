"""Presentación de un plano generado: tarjetas, pestañas y vista previa."""

from html import escape

import streamlit as st

from src.services.pipeline import ResultadoPlanoMultipisos
from src.ui.plano_svg import (
    color_de_ambiente,
    etiquetas_ambientes,
    generar_svg_plano,
    proporcion_vista,
)

CAPAS = {
    "Etiquetas": "etiquetas",
    "Puertas": "puertas",
    "Ventanas": "ventanas",
    "Muebles": "muebles",
    "Cotas": "cotas",
}


def pisos_de(resultado) -> list:
    if isinstance(resultado, ResultadoPlanoMultipisos):
        return list(resultado.pisos)
    return [resultado]


def etiquetas_de_pisos(cantidad: int) -> list[str]:
    return (["Planta Baja"] + [f"Planta Alta {i}" for i in range(1, cantidad)])[:cantidad]


def _dimensiones_terreno(piso) -> tuple[float, float]:
    minx, miny, maxx, maxy = piso.geometrias["terreno"].bounds
    return maxx - minx, maxy - miny


def tarjetas_resumen(piso) -> None:
    ancho, largo = _dimensiones_terreno(piso)
    superficie = sum(
        a.get("area_m2", a["ancho"] * a["largo"]) for a in piso.distribucion
    )
    puertas = len(piso.puertas["puertas"])
    ventanas = len((piso.ventanas or {}).get("ventanas", []))
    conectado = piso.validacion["distribucion_conectada"]

    columnas = st.columns(5)
    columnas[0].metric("Terreno", f"{ancho:g} × {largo:g} m", border=True)
    columnas[1].metric("Ambientes", len(piso.distribucion), border=True)
    columnas[2].metric("Superficie construida", f"{superficie:.1f} m²", border=True)
    columnas[3].metric("Puertas · ventanas", f"{puertas} · {ventanas}", border=True)
    columnas[4].metric(
        "Ambientes conectados", "Sí" if conectado else "No", border=True
    )


def _leyenda_html(piso) -> str:
    totales: dict[str, float] = {}
    for a in piso.distribucion:
        area = a.get("area_m2", a["ancho"] * a["largo"])
        totales[a["nombre"]] = totales.get(a["nombre"], 0.0) + area

    filas = "".join(
        f'<div style="display:flex;align-items:center;gap:8px;margin:4px 0">'
        f'<span style="width:12px;height:12px;border-radius:3px;'
        f'background:{color_de_ambiente(nombre)}"></span>'
        f'<span style="flex:1">{escape(nombre.capitalize())}</span>'
        f'<span style="color:#8FB3D1;font-variant-numeric:tabular-nums">'
        f"{area:.1f} m²</span></div>"
        for nombre, area in totales.items()
    )
    return f'<div style="font-size:0.9rem">{filas}</div>'


def _mostrar_svg(piso, capas, clave: str) -> None:
    """El SVG va en un iframe: st.html descarta las etiquetas <svg>."""
    svg = generar_svg_plano(piso, capas, uid=clave, ocupar_contenedor=True)
    documento = (
        '<!doctype html><html><head><meta charset="utf-8">'
        "<style>html,body{height:100%;margin:0;overflow:hidden;"
        "background:transparent}</style></head>"
        f"<body>{svg}</body></html>"
    )
    altura = int(max(360, min(780, 640 * proporcion_vista(piso))))
    st.iframe(documento, height=altura)


@st.fragment
def visor_plano(piso, clave: str) -> None:
    """Vista previa con capas conmutables; solo se vuelve a ejecutar este bloque."""

    elegidas = st.pills(
        "Capas",
        list(CAPAS),
        selection_mode="multi",
        default=list(CAPAS),
        key=f"capas_{clave}",
    )
    capas = frozenset(CAPAS[e] for e in (elegidas or []))

    izquierda, derecha = st.columns([3, 2])

    with izquierda:
        _mostrar_svg(piso, capas, clave)

    with derecha:
        st.markdown("**Leyenda**")
        st.html(_leyenda_html(piso))
        st.caption("Pasa el cursor sobre una habitación para ver sus medidas.")


def tabla_ambientes(piso) -> None:
    etiquetas = etiquetas_ambientes(piso.distribucion)
    st.dataframe(
        [
            {
                "Ambiente": etiquetas[a["id"]],
                "Posición (m)": f"({a['x']:g}, {a['y']:g})",
                "Dimensiones (m)": f"{a['ancho']:g} × {a['largo']:g}",
                "Área (m²)": round(a.get("area_m2", a["ancho"] * a["largo"]), 2),
            }
            for a in piso.distribucion
        ],
        hide_index=True,
        width="stretch",
    )


def mostrar_validacion_adyacencias(resultado) -> None:
    c1, c2, c3 = st.columns(3)
    c1.metric("Adyacencias detectadas", resultado["cantidad_adyacencias"], border=True)
    c2.metric("Grupos conectados", resultado["cantidad_componentes"], border=True)
    c3.metric("Ambientes aislados", len(resultado["ambientes_aislados"]), border=True)

    if resultado["distribucion_conectada"]:
        st.success("Todos los ambientes forman una única red de conexiones.")
    else:
        st.warning("La distribución contiene grupos de ambientes desconectados.")

    with st.expander("Adyacencias detectadas"):
        if resultado["adyacencias"]:
            st.dataframe(
                [
                    {
                        "Ambiente A": a["ambiente_a"],
                        "Ambiente B": a["ambiente_b"],
                        "Orientación": a["orientacion"],
                        "Longitud compartida (m)": a["longitud_m"],
                    }
                    for a in resultado["adyacencias"]
                ],
                hide_index=True,
                width="stretch",
            )
        else:
            st.info("No se detectaron adyacencias.")

    with st.expander("Grupos de ambientes"):
        for i, componente in enumerate(resultado["componentes"], start=1):
            st.write(f"**Grupo {i}:** {', '.join(componente)}")

    if resultado["ambientes_aislados"]:
        st.error(
            "Ambientes sin conexiones: "
            + ", ".join(resultado["ambientes_aislados"])
        )


def mostrar_puertas(resultado_puertas) -> None:
    puertas = resultado_puertas["puertas"]

    if not puertas:
        st.warning("No se pudieron proponer puertas para las adyacencias.")
        return

    st.dataframe(
        [
            {
                "Puerta": i,
                "Ambiente A": p.get("ambiente_a", ""),
                "Ambiente B": p.get("ambiente_b", ""),
                "Orientación": p["orientacion"],
                "Ancho (m)": p["ancho"],
                "Longitud de pared (m)": p.get("longitud_pared_m", 0),
                "Centro": str(p["centro"]),
            }
            for i, p in enumerate(puertas, start=1)
        ],
        hide_index=True,
        width="stretch",
    )


def mostrar_resultado(resultado, requerimientos=None, clave: str = "gen") -> None:
    """Tarjetas + pestañas de un resultado (un piso o varios)."""

    pisos = pisos_de(resultado)
    etiquetas = etiquetas_de_pisos(len(pisos))

    indice = 0
    if len(pisos) > 1:
        elegido = st.segmented_control(
            "Planta", etiquetas, default=etiquetas[0], key=f"planta_{clave}"
        )
        indice = etiquetas.index(elegido) if elegido in etiquetas else 0

    piso = pisos[indice]
    tarjetas_resumen(piso)

    nombres = ["Plano", "Ambientes", "Conectividad", "Puertas"]
    if requerimientos is not None:
        nombres.append("Requerimientos")
    pestanas = st.tabs(nombres)

    with pestanas[0]:
        visor_plano(piso, f"{clave}-{indice}")
    with pestanas[1]:
        tabla_ambientes(piso)
    with pestanas[2]:
        mostrar_validacion_adyacencias(piso.validacion)
    with pestanas[3]:
        mostrar_puertas(piso.puertas)
    if requerimientos is not None:
        with pestanas[4]:
            st.json(requerimientos.model_dump())
