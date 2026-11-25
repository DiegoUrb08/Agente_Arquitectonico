"""Interfaz Streamlit. Se lanza con:  streamlit run app.py"""

import logging
import os
import traceback
from pathlib import Path

import streamlit as st

from src.ai.edit_interpreter import interpretar_edicion
from src.ai.interpreter import interpretar_instruccion
from src.ai.ollama_client import OllamaError
from src.ai.providers import LLMProviderError
from src.cad.dxf_reader import analizar_dxf
from src.services.pipeline import editar_plano, generar_csv_areas, generar_plano
from src.ui.resultados import mostrar_resultado
from src.ui.tema import aplicar_tema

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CARPETA_SALIDA = PROJECT_ROOT / "output"

# Errores esperables: se muestran como mensaje claro, sin traza.
ERRORES_CONTROLADOS = (
    ValueError,
    OllamaError,
    LLMProviderError,
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


# ============================================================
# SECCIONES
# ============================================================

def _generar(instruccion: str) -> None:
    """Interpreta, genera y guarda el resultado en session_state."""

    st.session_state.pop("generado", None)

    if not instruccion.strip():
        st.warning("Primero debes escribir una descripción del proyecto.")
        return

    try:
        with st.spinner("Interpretando los requerimientos..."):
            requerimientos = interpretar_instruccion(instruccion)

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

        st.session_state["generado"] = {
            "requerimientos": requerimientos,
            "resultado": resultado,
            "dxf": resultado.ruta_dxf.read_bytes(),
            "csv": generar_csv_areas(resultado),
        }
        st.toast("Plano generado", icon="✅")

    except Exception as error:  # límite de la UI: nunca romper la página
        mostrar_error(error)


def _mostrar_generado(generado: dict) -> None:

    st.success("El plano arquitectónico se generó correctamente.")

    descarga_dxf, descarga_csv, _ = st.columns([1, 1, 2])
    descarga_dxf.download_button(
        "Descargar plano DXF",
        data=generado["dxf"],
        file_name="plano_generado.dxf",
        mime="application/dxf",
        type="primary",
        on_click="ignore",
        width="stretch",
    )
    descarga_csv.download_button(
        "Cuadro de áreas (CSV)",
        data=generado["csv"],
        file_name="cuadro_areas.csv",
        mime="text/csv",
        on_click="ignore",
        width="stretch",
    )

    mostrar_resultado(
        generado["resultado"], generado["requerimientos"], clave="gen"
    )


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

    if st.button("Generar plano", type="primary"):
        _generar(instruccion)

    generado = st.session_state.get("generado")
    if generado:
        _mostrar_generado(generado)


def _aplicar_edicion(instruccion: str, ruta_entrada: Path, id_archivo: str) -> None:
    """Interpreta y aplica la edición; guarda el resultado en session_state."""

    st.session_state.pop("editado", None)

    if not instruccion.strip():
        st.warning("Primero debes describir las modificaciones.")
        return

    with st.spinner("Interpretando las modificaciones..."):
        solicitud = interpretar_edicion(instruccion)

    ruta_modificada = CARPETA_SALIDA / "plano_modificado.dxf"

    with st.spinner("Aplicando modificaciones y regenerando el plano..."):
        resultado = editar_plano(
            str(ruta_entrada), str(ruta_modificada), solicitud
        )

    st.session_state["editado"] = {
        "archivo": id_archivo,
        "modificaciones": resultado["modificaciones"],
        "observaciones": resultado["observaciones"],
        "plano": resultado["plano"],
        "dxf": ruta_modificada.read_bytes(),
    }
    st.toast("Plano modificado", icon="✅")


def _mostrar_editado(editado: dict) -> None:

    st.success("El plano fue modificado correctamente.")

    for aviso in editado["observaciones"]:
        st.info(aviso)

    with st.expander("Modificaciones aplicadas"):
        st.json(editado["modificaciones"])

    st.download_button(
        "Descargar plano modificado",
        data=editado["dxf"],
        file_name="plano_modificado.dxf",
        mime="application/dxf",
        type="primary",
        on_click="ignore",
    )

    mostrar_resultado(editado["plano"], clave="edit")


def seccion_editar():

    st.divider()
    st.header("2. Editar un plano existente")

    archivo_dxf = st.file_uploader(
        "Subir plano arquitectónico", type=["dxf"], key="archivo_dxf"
    )

    if archivo_dxf is None:
        st.session_state.pop("editado", None)
        return

    try:
        CARPETA_SALIDA.mkdir(parents=True, exist_ok=True)
        ruta_entrada = CARPETA_SALIDA / "plano_subido.dxf"
        ruta_entrada.write_bytes(archivo_dxf.getvalue())

        st.success("Archivo DXF cargado correctamente.")

        with st.spinner("Analizando el plano..."):
            analisis = analizar_dxf(archivo_dxf.getvalue())

        with st.expander("Información del plano"):
            st.json(analisis)

        instruccion_edicion = st.text_area(
            "¿Qué modificaciones deseas realizar?",
            height=120,
            placeholder=(
                "Ejemplo: Cambia el área del dormitorio principal a 20 m²."
            ),
            key="instruccion_edicion",
        )

        if st.button("Aplicar modificaciones"):
            _aplicar_edicion(
                instruccion_edicion, ruta_entrada, archivo_dxf.file_id
            )

        editado = st.session_state.get("editado")
        if editado and editado["archivo"] == archivo_dxf.file_id:
            _mostrar_editado(editado)

    except Exception as error:  # límite de la UI
        mostrar_error(error)


# ============================================================
# PUNTO DE ENTRADA
# ============================================================

def _sidebar_proveedor():
    """Muestra información del proveedor LLM activo en la barra lateral."""
    provider = os.getenv("LLM_PROVIDER", "groq").lower()

    iconos = {
        "groq": "⚡",
        "ollama": "🖥️",
        "proxy": "🌐",
        "claude": "🤖",
        "mock": "🧪",
    }
    icono = iconos.get(provider, "🤖")

    with st.sidebar:
        st.markdown("### Proveedor LLM")

        if provider == "groq":
            modelo = os.getenv("LLM_GROQ_MODEL", "openai/gpt-oss-20b")
            st.success(f"{icono} **Groq** (gratis)")
            st.caption(f"Modelo: `{modelo}`")
            st.caption("Sin tarjeta de crédito · 100+ tokens/s")

        elif provider == "ollama":
            host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
            modelo = os.getenv("LLM_OLLAMA_MODEL", "qwen3:8b")
            st.info(f"{icono} **Ollama** (local)")
            st.caption(f"Host: `{host}`")
            st.caption(f"Modelo: `{modelo}`")

        elif provider == "proxy":
            proxy_url = os.getenv("PROXY_URL", "")
            url_corta = proxy_url[:40] + "…" if len(proxy_url) > 40 else proxy_url
            st.info(f"{icono} **Modo proxy** (demo)")
            st.caption(f"Servidor: `{url_corta}`")
            st.warning(
                "Sujeto al límite del operador.  \n"
                "Para uso ilimitado: [obtén tu clave Groq gratis]"
                "(https://console.groq.com/keys)"
            )

        elif provider == "claude":
            modelo = os.getenv("LLM_CLAUDE_MODEL", "claude-opus-5-5")
            st.info(f"{icono} **Claude** (Anthropic)")
            st.caption(f"Modelo: `{modelo}`")
            st.caption("De pago, según el uso de tu cuenta de Anthropic.")

        elif provider == "mock":
            st.warning(f"{icono} **Mock** (solo tests)")
            st.caption("Las respuestas son simuladas.")

        else:
            modelo_env = os.getenv(f"LLM_{provider.upper()}_MODEL", "")
            st.info(f"{icono} **{provider.upper()}**")
            if modelo_env:
                st.caption(f"Modelo: `{modelo_env}`")

        st.divider()

        with st.expander("¿Cómo cambiar de proveedor?"):
            st.markdown(
                "Edita el archivo `.env` en la raíz del proyecto:\n\n"
                "```\n"
                "# Groq (gratis, recomendado)\n"
                "LLM_PROVIDER=groq\n"
                "GROQ_API_KEY=gsk_...\n\n"
                "# Ollama (local)\n"
                "LLM_PROVIDER=ollama\n\n"
                "# Claude (de pago)\n"
                "LLM_PROVIDER=claude\n"
                "ANTHROPIC_API_KEY=sk-ant-...\n\n"
                "# Proxy (demo)\n"
                "LLM_PROVIDER=proxy\n"
                "PROXY_URL=https://...\n"
                "```\n\n"
                "Luego reinicia la app."
            )


def main():

    st.set_page_config(
        page_title="Agente Arquitectónico",
        page_icon="🏠",
        layout="wide",
    )

    aplicar_tema()
    _sidebar_proveedor()

    st.title("Agente Arquitectónico")
    st.write(
        "Sistema de generación y edición de planos arquitectónicos "
        "mediante inteligencia artificial."
    )

    seccion_generar()
    seccion_editar()
