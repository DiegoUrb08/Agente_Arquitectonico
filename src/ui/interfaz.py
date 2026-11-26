"""Interfaz Streamlit. Se lanza con:  streamlit run app.py"""

import logging
import os
import traceback

import streamlit as st

from src.ai.edit_interpreter import interpretar_edicion
from src.ai.interpreter import interpretar_instruccion
from src.ai.ollama_client import OllamaError
from src.ai.providers import LLMProviderError
from src.bim.ifc import generar_ifc
from src.ui import proyecto as pry
from src.ui.resultados import mostrar_resultado
from src.ui.tema import aplicar_tema

logger = logging.getLogger(__name__)

# Errores esperables: se muestran como mensaje claro, sin traza.
ERRORES_CONTROLADOS = (
    ValueError,
    OllamaError,
    LLMProviderError,
    FileNotFoundError,
    NotImplementedError,
)


# ============================================================
# ERRORES
# ============================================================

def describir_error(error: Exception) -> tuple[str, str | None]:
    """(mensaje, traza); la traza solo existe en errores inesperados."""

    if isinstance(error, ERRORES_CONTROLADOS):
        return str(error), None

    logger.exception("Error inesperado", exc_info=error)
    return (
        f"Error inesperado: {error}",
        "".join(traceback.format_exception(error)),
    )


def mostrar_error(error: Exception):
    """Mensaje claro para errores esperables; traza para los inesperados."""

    texto, detalle = describir_error(error)
    st.error(texto)

    if detalle:
        with st.expander("Detalle técnico del error"):
            st.code(detalle, language="python")


# ============================================================
# INICIO: describir un proyecto o abrir un plano existente
# ============================================================

def _generar(instruccion: str) -> None:

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

        with st.status("Generando el plano...", expanded=False) as estado:
            proyecto = pry.crear_proyecto(
                requerimientos,
                instruccion,
                progreso=lambda m: estado.update(label=m),
            )
            estado.update(label="Plano generado", state="complete")

    except Exception as error:  # límite de la UI: nunca romper la página
        mostrar_error(error)
        return

    st.session_state["proyecto"] = proyecto
    st.rerun()


def _abrir(archivo) -> None:

    try:
        with st.spinner("Abriendo el plano..."):
            proyecto = pry.abrir_proyecto(archivo.getvalue(), archivo.name)

    except Exception as error:  # límite de la UI
        mostrar_error(error)
        return

    st.session_state["proyecto"] = proyecto
    st.rerun()


EJEMPLOS = {
    "Casa pequeña": (
        "Casa de 8 x 15 metros con sala, cocina, 2 dormitorios y 1 baño."
    ),
    "Vivienda familiar": (
        "Vivienda de 10 x 20 metros con sala, comedor, cocina, "
        "2 dormitorios y 2 baños."
    ),
    "Casa de dos pisos": (
        "Casa de dos pisos en un terreno de 12 x 25 metros con sala, comedor, "
        "cocina, estudio, 3 dormitorios y 2 baños."
    ),
    "Solo el área del terreno": (
        "Vivienda en un terreno de 200 m² con 3 dormitorios, sala, cocina "
        "y 2 baños."
    ),
}


def _usar_ejemplo() -> None:
    """Copia el ejemplo elegido al cuadro de texto y deja volver a elegirlo."""
    elegido = st.session_state.get("ejemplo")
    if elegido:
        st.session_state["instruccion"] = EJEMPLOS[elegido]
        st.session_state["ejemplo"] = None


def inicio() -> None:

    st.header("Nuevo proyecto")

    instruccion = st.text_area(
        "Describe el proyecto arquitectónico:",
        height=150,
        placeholder=(
            "Ejemplo: Diseña una vivienda de 150 m² de terreno "
            "con dos dormitorios, sala, comedor, cocina y dos baños."
        ),
        key="instruccion",
    )

    st.pills(
        "O empieza con un ejemplo",
        list(EJEMPLOS),
        key="ejemplo",
        on_change=_usar_ejemplo,
    )

    if st.button("Generar plano", type="primary"):
        _generar(instruccion)

    with st.expander("¿Ya tienes un plano? Ábrelo para editarlo (DXF de cualquier programa)"):
        archivo = st.file_uploader(
            "Subir plano arquitectónico (.dxf)", type=["dxf"], key="archivo_dxf"
        )
        if archivo is not None and st.button("Abrir plano"):
            _abrir(archivo)


# ============================================================
# ESPACIO DE TRABAJO: conversación + plano
# ============================================================

def _mostrar_mensajes(mensajes: list) -> None:

    for m in mensajes:
        with st.chat_message("user" if m["rol"] == "usuario" else "assistant"):
            if m["rol"] == "error":
                st.error(m["texto"])
                if m["detalle"]:
                    with st.expander("Detalle técnico"):
                        st.code(m["detalle"], language="python")
            else:
                st.markdown(m["texto"])


def _refinar(proyecto: dict, texto: str, caja) -> None:
    """Interpreta y aplica un cambio; el resultado queda en el proyecto."""

    pry.registrar_usuario(proyecto, texto)

    with caja:
        _mostrar_mensajes(proyecto["mensajes"])
        with st.spinner("Interpretando y aplicando el cambio..."):
            try:
                solicitud = interpretar_edicion(texto)
                pry.aplicar_edicion(proyecto, texto, solicitud)
            except Exception as error:  # límite de la UI
                mensaje, detalle = describir_error(error)
                pry.registrar_error(proyecto, mensaje, detalle)


def espacio_de_trabajo(proyecto: dict) -> None:

    actual = pry.version_actual(proyecto)
    versiones = len(proyecto["versiones"])

    izquierda, derecha = st.columns([2, 3], gap="large")

    with izquierda:
        st.subheader("Conversación")
        caja = st.container(height=460, border=True)
        entrada = st.chat_input(
            "Pide un cambio al plano…",
            key="entrada_chat",
        )
        c_deshacer, c_nuevo = st.columns(2)
        deshacer = c_deshacer.button(
            "↶ Deshacer",
            disabled=versiones < 2,
            width="stretch",
        )
        nuevo = c_nuevo.button("Nuevo proyecto", width="stretch")
        st.caption(f"Versión {versiones}: {actual['etiqueta']}")

    if nuevo:
        st.session_state.pop("proyecto", None)
        st.rerun()

    if deshacer:
        pry.deshacer(proyecto)
        st.rerun()

    if entrada:
        _refinar(proyecto, entrada, caja)
        st.rerun()

    with caja:
        _mostrar_mensajes(proyecto["mensajes"])

    with derecha:
        descarga_dxf, descarga_csv, descarga_ifc = st.columns([1, 1, 1])
        descarga_dxf.download_button(
            "Descargar DXF",
            data=actual["dxf"],
            file_name="plano.dxf",
            mime="application/dxf",
            type="primary",
            on_click="ignore",
            width="stretch",
        )
        descarga_csv.download_button(
            "Cuadro de áreas (CSV)",
            data=actual["csv"],
            file_name="cuadro_areas.csv",
            mime="text/csv",
            on_click="ignore",
            width="stretch",
        )
        resultado_actual = actual["resultado"]
        descarga_ifc.download_button(
            "Modelo BIM (IFC)",
            # Se genera solo al pulsar: no hace falta para ver el plano.
            data=lambda: generar_ifc(resultado_actual),
            file_name="modelo.ifc",
            mime="application/x-step",
            on_click="ignore",
            width="stretch",
            help="Modelo IFC4 con espacios, muros, puertas, ventanas, losa y "
                 "mobiliario. Se abre en Revit, ArchiCAD, BlenderBIM o un "
                 "visor gratuito como BIM Vision.",
        )

        mostrar_resultado(
            actual["resultado"],
            proyecto["requerimientos"],
            clave="proyecto",
            cambiados=actual["cambiados"],
        )


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

    proyecto = st.session_state.get("proyecto")

    if proyecto is None:
        inicio()
    else:
        espacio_de_trabajo(proyecto)
