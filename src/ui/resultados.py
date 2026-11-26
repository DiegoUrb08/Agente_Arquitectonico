"""Presentación de un plano generado: tarjetas, pestañas y vista previa."""

from html import escape

import streamlit as st

from src.ui.proyecto import dimensiones_terreno, pisos_de
from src.ui.plano_svg import (
    color_de_ambiente,
    etiquetas_ambientes,
    fraccion_ocupada,
    generar_svg_plano,
    proporcion_vista,
)

CAPAS = {
    "Etiquetas": "etiquetas",
    "Puertas": "puertas",
    "Ventanas": "ventanas",
    "Muebles": "muebles",
    "Cotas": "cotas",
    "Cambios": "cambios",
}

VISTA_TERRENO = "Terreno completo"
VISTA_VIVIENDA = "Ajustar a la vivienda"


def etiquetas_de_pisos(cantidad: int) -> list[str]:
    return (["Planta Baja"] + [f"Planta Alta {i}" for i in range(1, cantidad)])[:cantidad]


def tarjetas_resumen(piso) -> None:
    ancho, largo = dimensiones_terreno(piso)
    superficie = sum(
        a.get("area_m2", a["ancho"] * a["largo"]) for a in piso.distribucion
    )
    puertas = len(piso.puertas["puertas"])
    ventanas = len((piso.ventanas or {}).get("ventanas", []))
    conectado = piso.validacion["distribucion_conectada"]

    arriba = st.columns(3)
    arriba[0].metric("Terreno", f"{ancho:g} × {largo:g} m", border=True)
    arriba[1].metric("Ambientes", len(piso.distribucion), border=True)
    arriba[2].metric("Superficie construida", f"{superficie:.1f} m²", border=True)

    abajo = st.columns(3)
    abajo[0].metric("Puertas", puertas, border=True)
    abajo[1].metric("Ventanas", ventanas, border=True)
    abajo[2].metric("Ambientes conectados", "Sí" if conectado else "No", border=True)


def _leyenda_html(piso) -> str:
    totales: dict[str, float] = {}
    for a in piso.distribucion:
        area = a.get("area_m2", a["ancho"] * a["largo"])
        totales[a["nombre"]] = totales.get(a["nombre"], 0.0) + area

    etiquetas = "".join(
        f'<span style="display:inline-flex;align-items:center;gap:6px;'
        f'margin:0 16px 6px 0;white-space:nowrap">'
        f'<span style="width:10px;height:10px;border-radius:3px;'
        f'background:{color_de_ambiente(nombre)}"></span>'
        f"{escape(nombre.capitalize())} "
        f'<span style="color:#8FB3D1;font-variant-numeric:tabular-nums">'
        f"{area:.1f} m²</span></span>"
        for nombre, area in totales.items()
    )
    return (
        f'<div style="display:flex;flex-wrap:wrap;font-size:0.85rem">'
        f"{etiquetas}</div>"
    )


def _mostrar_svg(piso, capas, clave: str, enfocar: bool, cambiados) -> None:
    """El SVG va en un iframe: st.html descarta las etiquetas <svg>."""
    svg = generar_svg_plano(
        piso,
        capas,
        uid=clave,
        ocupar_contenedor=True,
        enfocar=enfocar,
        resaltar=cambiados,
    )
    documento = (
        '<!doctype html><html><head><meta charset="utf-8">'
        "<style>html,body{height:100%;margin:0;overflow:hidden;"
        "background:transparent}</style></head>"
        f"<body>{svg}</body></html>"
    )
    altura = int(max(360, min(780, 640 * proporcion_vista(piso, enfocar))))
    st.iframe(documento, height=altura)


@st.fragment
def visor_plano(piso, clave: str, cambiados=frozenset(), archivo: str = "plano.svg") -> None:
    """Vista previa con capas conmutables; solo se vuelve a ejecutar este bloque."""

    elegidas = st.pills(
        "Capas",
        list(CAPAS),
        selection_mode="multi",
        default=list(CAPAS),
        key=f"capas_{clave}",
    )
    capas = frozenset(CAPAS[e] for e in (elegidas or []))

    por_defecto = VISTA_VIVIENDA if fraccion_ocupada(piso) < 0.5 else VISTA_TERRENO
    vista = st.segmented_control(
        "Vista",
        [VISTA_TERRENO, VISTA_VIVIENDA],
        default=por_defecto,
        key=f"vista_{clave}",
    )
    enfocar = vista == VISTA_VIVIENDA

    st.html(_leyenda_html(piso))
    _mostrar_svg(piso, capas, clave, enfocar, cambiados)

    if cambiados and "cambios" in capas:
        st.caption("En ámbar parpadeante: lo que cambió en esta versión.")
    else:
        st.caption("Pasa el cursor sobre una habitación para ver sus medidas.")

    st.download_button(
        "Descargar imagen (SVG)",
        data=generar_svg_plano(
            piso,
            capas - {"cambios"},
            uid=f"{clave}-archivo",
            enfocar=enfocar,
            fondo_pagina=True,
        ),
        file_name=archivo,
        mime="image/svg+xml",
        on_click="ignore",
    )


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
                "Ambiente B": (
                    "Exterior" if p.get("ambiente_b") == "exterior"
                    else p.get("ambiente_b", "")
                ),
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


def mostrar_resultado(
    resultado, requerimientos=None, clave: str = "gen", cambiados=frozenset()
) -> None:
    """Tarjetas + pestañas de un resultado (un piso o varios).

    `cambiados` son los ids de ambientes a resaltar en el plano.
    """

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

    if piso.avisos:
        st.warning(
            "Reglas que este plano no cumple:\n"
            + "\n".join(f"- {aviso}" for aviso in piso.avisos)
        )

    nombres = ["Plano", "Ambientes", "Conectividad", "Puertas"]
    if requerimientos is not None:
        nombres.append("Requerimientos")
    pestanas = st.tabs(nombres)

    archivo = "plano.svg" if len(pisos) == 1 else f"plano_planta_{indice + 1}.svg"

    with pestanas[0]:
        visor_plano(piso, f"{clave}-{indice}", cambiados, archivo)
    with pestanas[1]:
        tabla_ambientes(piso)
    with pestanas[2]:
        mostrar_validacion_adyacencias(piso.validacion)
    with pestanas[3]:
        mostrar_puertas(piso.puertas)
    if requerimientos is not None:
        with pestanas[4]:
            st.json(requerimientos.model_dump())
