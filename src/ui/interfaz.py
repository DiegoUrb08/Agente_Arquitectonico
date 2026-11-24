"""Interfaz Streamlit. Se lanza con:  streamlit run app.py"""

import logging
import traceback
from pathlib import Path

import streamlit as st

from src.ai.edit_interpreter import interpretar_edicion
from src.ai.interpreter import interpretar_instruccion
from src.ai.ollama_client import OllamaError
from src.cad.dxf_reader import analizar_dxf
from src.services.pipeline import editar_plano, generar_plano

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CARPETA_SALIDA = PROJECT_ROOT / "output"

# Errores esperables: se muestran como mensaje claro, sin traza.
ERRORES_CONTROLADOS = (
    ValueError,
    OllamaError,
    FileNotFoundError,
    NotImplementedError,
)


# ============================================================
# AUXILIARES DE PRESENTACIÓN
# ============================================================

def mostrar_error(error: Exception):
    """Mensaje claro para errores esperables; traza para los inesperados."""

    if isinstance(error, ERRORES_CONTROLADOS):
        st.error(str(error))
        return

    logger.exception("Error inesperado", exc_info=error)
    st.error(f"Error inesperado: {error}")

    with st.expander("Detalle técnico del error"):
        st.code(
            "".join(traceback.format_exception(error)),
            language="python",
        )


def mostrar_distribucion(distribucion):

    st.subheader("Distribución de ambientes")

    for i, a in enumerate(distribucion, start=1):

        st.write(f"**Ambiente {i}: {a['nombre']}**")
        c1, c2, c3 = st.columns(3)
        c1.write(f"Posición: ({a['x']}, {a['y']}) m")
        c2.write(f"Dimensiones: {a['ancho']} x {a['largo']} m")
        c3.write(f"Área: {a.get('area_m2', a['ancho'] * a['largo'])} m²")
        st.divider()


def mostrar_validacion_adyacencias(resultado):

    st.subheader("Validación de conectividad espacial")

    c1, c2, c3 = st.columns(3)
    c1.metric("Adyacencias detectadas", resultado["cantidad_adyacencias"])
    c2.metric("Grupos conectados", resultado["cantidad_componentes"])
    c3.metric("Ambientes aislados", len(resultado["ambientes_aislados"]))

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
                use_container_width=True,
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


def mostrar_puertas(resultado_puertas):

    puertas = resultado_puertas["puertas"]

    st.subheader("Generación automática de puertas")
    st.metric("Puertas propuestas", len(puertas))

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
                "Centro": p["centro"],
            }
            for i, p in enumerate(puertas, start=1)
        ],
        use_container_width=True,
    )


def mostrar_resultado_plano(resultado):

    mostrar_distribucion(resultado.distribucion)
    mostrar_validacion_adyacencias(resultado.validacion)
    mostrar_puertas(resultado.puertas)

    st.subheader("Muros y aberturas")
    c1, c2, c3 = st.columns(3)
    c1.metric("Área de muros", f"{resultado.muros['area_muros_m2']:.2f} m²")
    c2.metric(
        "Área con aberturas",
        f"{resultado.aberturas['muros_con_aberturas'].area:.2f} m²",
    )
    c3.metric("Puertas procesadas", len(resultado.aberturas["puertas"]))


# ============================================================
# SECCIONES
# ============================================================

def seccion_generar():

    st.header("1. Generar un nuevo plano")

    instruccion = st.text_area(
        "Describe el proyecto arquitectónico:",
        height=150,
        placeholder=(
            "Ejemplo: Diseña una vivienda de 150 m² de terreno "
            "con dos dormitorios, sala, comedor, cocina y dos baños."
        ),
    )

    if not st.button("Generar plano", type="primary"):
        return

    if not instruccion.strip():
        st.warning("Primero debes escribir una descripción del proyecto.")
        return

    try:
        with st.spinner("Interpretando los requerimientos..."):
            requerimientos = interpretar_instruccion(instruccion)

        st.subheader("Requerimientos interpretados")
        st.json(requerimientos.model_dump())

        if requerimientos.datos_faltantes:
            st.warning(
                "Se necesitan algunos datos adicionales "
                "antes de generar el plano."
            )
            for dato in requerimientos.datos_faltantes:
                st.write(f"- {dato}")
            return

        CARPETA_SALIDA.mkdir(parents=True, exist_ok=True)

        with st.status("Generando el plano...", expanded=False) as estado:
            resultado = generar_plano(
                requerimientos,
                CARPETA_SALIDA / "plano_generado.dxf",
                progreso=lambda m: estado.update(label=m),
            )
            estado.update(label="Plano generado", state="complete")

        mostrar_resultado_plano(resultado)

        st.success("El plano arquitectónico se generó correctamente.")

        st.download_button(
            label="Descargar plano DXF",
            data=resultado.ruta_dxf.read_bytes(),
            file_name="plano_generado.dxf",
            mime="application/dxf",
        )

    except Exception as error:  # límite de la UI: nunca romper la página
        mostrar_error(error)


def seccion_editar():

    st.divider()
    st.header("2. Editar un plano existente")

    archivo_dxf = st.file_uploader(
        "Subir plano arquitectónico", type=["dxf"], key="archivo_dxf"
    )

    if archivo_dxf is None:
        return

    try:
        CARPETA_SALIDA.mkdir(parents=True, exist_ok=True)
        ruta_entrada = CARPETA_SALIDA / "plano_subido.dxf"
        ruta_entrada.write_bytes(archivo_dxf.getvalue())

        st.success("Archivo DXF cargado correctamente.")

        with st.spinner("Analizando el plano..."):
            analisis = analizar_dxf(archivo_dxf.getvalue())

        st.subheader("Información del plano")
        st.json(analisis)

        instruccion_edicion = st.text_area(
            "¿Qué modificaciones deseas realizar?",
            height=120,
            placeholder=(
                "Ejemplo: Cambia el área del dormitorio principal a 20 m²."
            ),
            key="instruccion_edicion",
        )

        if not st.button("Aplicar modificaciones"):
            return

        if not instruccion_edicion.strip():
            st.warning("Primero debes describir las modificaciones.")
            return

        with st.spinner("Interpretando las modificaciones..."):
            solicitud = interpretar_edicion(instruccion_edicion)

        ruta_modificada = CARPETA_SALIDA / "plano_modificado.dxf"

        with st.spinner("Aplicando modificaciones y regenerando el plano..."):
            resultado = editar_plano(
                str(ruta_entrada), str(ruta_modificada), solicitud
            )

        st.success("El plano fue modificado correctamente.")

        st.json(resultado["modificaciones"])

        for aviso in resultado["observaciones"]:
            st.info(aviso)

        st.download_button(
            label="Descargar plano modificado",
            data=ruta_modificada.read_bytes(),
            file_name="plano_modificado.dxf",
            mime="application/dxf",
        )

    except Exception as error:  # límite de la UI
        mostrar_error(error)


# ============================================================
# PUNTO DE ENTRADA
# ============================================================

def main():

    st.set_page_config(
        page_title="Agente Arquitectónico",
        page_icon="🏠",
        layout="wide",
    )

    st.title("Agente Arquitectónico")
    st.write(
        "Sistema de generación y edición de planos arquitectónicos "
        "mediante inteligencia artificial."
    )

    seccion_generar()
    seccion_editar()
