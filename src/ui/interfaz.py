"""Interfaz Streamlit. Se lanza con:  streamlit run app.py"""

import logging
import os
import re
import traceback
from datetime import datetime

import streamlit as st

from src.ai.edit_interpreter import interpretar_edicion
from src.ai.interpreter import interpretar_instruccion
from src.ai.ollama_client import OllamaError
from src.ai.providers import LLMProviderError
from src.bim.ifc import generar_ifc
from src.lamina.pdf import generar_lamina
from src.models.requirements import Retiros
from src.ui import almacen, guardado
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
# GUARDADO
# ============================================================

def _autoguardar(proyecto: dict) -> None:
    """Guarda en este equipo; un fallo de disco no interrumpe el trabajo."""

    try:
        almacen.guardar(proyecto)
    except (OSError, ValueError) as error:
        logger.warning("No se pudo autoguardar", exc_info=error)
        st.session_state["aviso_guardado"] = (
            f"No se pudo guardar el proyecto en este equipo ({error}). "
            "Usa «Guardar en archivo»."
        )
    else:
        st.session_state.pop("aviso_guardado", None)


def _entrar(proyecto: dict) -> None:
    st.session_state.pop("aviso_guardado", None)
    st.session_state.pop("por_borrar", None)
    st.session_state["proyecto"] = proyecto


def _nombre_de_archivo(proyecto: dict) -> str:
    nombre = re.sub(r"[^\w-]+", "_", proyecto.get("nombre", "")).strip("_")
    return (nombre or "proyecto") + guardado.EXTENSION


def _fecha(texto: str) -> str:
    try:
        return datetime.fromisoformat(texto).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return "sin fecha"


# ============================================================
# INICIO: describir un proyecto o abrir un plano existente
# ============================================================

# El lado del terreno donde está el norte; None = lo que diga la descripción.
OPCIONES_NORTE = {
    "Según la descripción": None,
    "Al fondo": "fondo",
    "Hacia la calle": "frente",
    "A la derecha": "derecha",
    "A la izquierda": "izquierda",
}


# campo -> etiqueta
CAMPOS_RETIRO = {
    "frontal": "Frontal (calle)",
    "posterior": "Posterior",
    "izquierdo": "Izquierdo",
    "derecho": "Derecho",
}


def _pedir_retiros() -> dict:
    """Los retiros escritos en la pantalla; los que quedan en 0 se omiten."""

    with st.expander("Retiros del terreno (opcional)"):
        st.caption(
            "Metros libres entre la casa y cada límite, vistos desde la calle. "
            "Consulta los de tu municipio. En 0 vale lo que diga la descripción."
        )
        valores = {
            campo: columna.number_input(
                etiqueta, min_value=0.0, max_value=100.0, step=0.5,
                key=f"retiro_{campo}",
            )
            for columna, (campo, etiqueta) in zip(
                st.columns(len(CAMPOS_RETIRO)), CAMPOS_RETIRO.items()
            )
        }
    return {campo: v for campo, v in valores.items() if v > 0}


def _generar(
    instruccion: str, norte: str | None = None, retiros: dict | None = None
) -> None:

    if not instruccion.strip():
        st.warning("Primero debes escribir una descripción del proyecto.")
        return

    try:
        with st.spinner("Interpretando los requerimientos..."):
            requerimientos = interpretar_instruccion(instruccion)
            if norte:
                requerimientos.norte = norte
            if retiros:
                leidos = requerimientos.retiros or Retiros()
                requerimientos.retiros = leidos.model_copy(update=retiros)

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

    _entrar(proyecto)
    _autoguardar(proyecto)
    st.rerun()


def _abrir(archivo) -> None:

    try:
        with st.spinner("Abriendo el plano..."):
            proyecto = pry.abrir_proyecto(archivo.getvalue(), archivo.name)

    except Exception as error:  # límite de la UI
        mostrar_error(error)
        return

    _entrar(proyecto)
    _autoguardar(proyecto)
    st.rerun()


def _recuperar(cargar, guardar: bool) -> None:
    """Abre un proyecto guardado (`cargar` recibe el callback de progreso)."""

    try:
        with st.status("Abriendo el proyecto...", expanded=False) as estado:
            proyecto = cargar(lambda m: estado.update(label=m))
            estado.update(label="Proyecto abierto", state="complete")

    except Exception as error:  # límite de la UI
        mostrar_error(error)
        return

    _entrar(proyecto)
    if guardar:
        _autoguardar(proyecto)
    st.rerun()


def _importar_proyecto() -> None:

    with st.expander("Importar un proyecto guardado en un archivo"):
        archivo = st.file_uploader(
            "Subir proyecto (.json)", type=["json"], key="archivo_proyecto"
        )
        if archivo is not None and st.button("Importar proyecto"):
            _recuperar(
                lambda progreso: guardado.importar(archivo.getvalue(), progreso),
                guardar=True,
            )


def _mis_proyectos() -> None:

    proyectos, danados = almacen.listar()

    if not proyectos and not danados:
        return

    st.subheader("Mis proyectos")

    if danados:
        st.caption(
            f"{danados} archivo(s) de `{almacen.carpeta()}` no se pudieron leer."
        )

    if not proyectos:
        return

    por_id = {p["id"]: p for p in proyectos}

    def etiqueta(identificador):
        p = por_id[identificador]
        return (
            f"{p['nombre']} · {_fecha(p['modificado'])} · "
            f"versión {p['versiones']}"
        )

    elegido = st.selectbox(
        "Proyecto guardado en este equipo",
        list(por_id),
        format_func=etiqueta,
        key="proyecto_guardado",
    )

    c_abrir, c_borrar = st.columns(2)

    if c_abrir.button("Abrir proyecto", width="stretch"):
        _recuperar(
            lambda progreso: almacen.abrir(elegido, progreso), guardar=False
        )

    if c_borrar.button("Borrar proyecto", width="stretch"):
        st.session_state["por_borrar"] = elegido

    # La confirmación solo vale para el proyecto que sigue elegido.
    if st.session_state.get("por_borrar") != elegido:
        return

    st.warning(f"¿Borrar «{por_id[elegido]['nombre']}»? No se puede deshacer.")
    c_si, c_no = st.columns(2)

    # Con callbacks, la lista ya sale actualizada en la misma ejecución.
    c_si.button(
        "Sí, borrar", on_click=_borrar, args=(elegido,), width="stretch"
    )
    c_no.button(
        "Cancelar",
        on_click=st.session_state.pop,
        args=("por_borrar", None),
        width="stretch",
    )


def _borrar(identificador: str) -> None:
    st.session_state.pop("por_borrar", None)
    try:
        almacen.borrar(identificador)
    except OSError as error:
        mostrar_error(error)


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
    # Muestra todo a la vez: plantas, garaje, retiros, norte y mobiliario.
    "Proyecto completo": (
        "Casa de dos pisos en un terreno de 12 x 25 metros con retiro frontal "
        "de 3 m. Quiero garaje, sala, comedor, cocina, lavandería, estudio, "
        "3 dormitorios y 3 baños. El norte está a la derecha."
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

    norte = st.radio(
        "¿Dónde está el norte? (opcional)",
        list(OPCIONES_NORTE),
        horizontal=True,
        key="norte",
        help="Visto desde la calle. Con este dato, la sala y los dormitorios "
             "se ubican buscando el mejor sol (criterio para Perú).",
    )

    retiros = _pedir_retiros()

    if st.button("Generar plano", type="primary"):
        _generar(instruccion, OPCIONES_NORTE[norte], retiros)

    with st.expander("¿Ya tienes un plano? Ábrelo para editarlo (DXF de cualquier programa)"):
        archivo = st.file_uploader(
            "Subir plano arquitectónico (.dxf)", type=["dxf"], key="archivo_dxf"
        )
        if archivo is not None and st.button("Abrir plano"):
            _abrir(archivo)

    _importar_proyecto()
    _mis_proyectos()


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
        st.download_button(
            "Guardar en archivo",
            # Se genera al pulsar, con lo que haya en ese momento.
            data=lambda: guardado.exportar(proyecto),
            file_name=_nombre_de_archivo(proyecto),
            mime="application/json",
            on_click="ignore",
            width="stretch",
            help="Proyecto completo (conversación y versiones) para retomarlo "
                 "después o en otro equipo.",
        )
        if "aviso_guardado" in st.session_state:
            st.warning(st.session_state["aviso_guardado"])
        elif almacen.activo():
            st.caption("Se guarda automáticamente en este equipo.")
        else:
            st.caption(
                "Guardado automático desactivado (AUTOGUARDADO=1 en .env lo activa)."
            )

    if nuevo:
        st.session_state.pop("proyecto", None)
        st.rerun()

    if deshacer:
        pry.deshacer(proyecto)
        _autoguardar(proyecto)
        st.rerun()

    if entrada:
        _refinar(proyecto, entrada, caja)
        _autoguardar(proyecto)
        st.rerun()

    with caja:
        _mostrar_mensajes(proyecto["mensajes"])

    with derecha:
        descarga_pdf, descarga_dxf, descarga_csv, descarga_ifc = st.columns(4)
        resultado_actual = actual["resultado"]
        descarga_pdf.download_button(
            "Lámina (PDF)",
            # Se genera al pulsar, igual que el modelo BIM.
            data=lambda: generar_lamina(
                resultado_actual,
                proyecto.get("nombre") or "Proyecto",
                proyecto["requerimientos"],
            ),
            file_name="lamina.pdf",
            mime="application/pdf",
            type="primary",
            on_click="ignore",
            width="stretch",
            help="Una hoja A3 por planta, a escala, con cuadro de áreas, norte "
                 "y membrete. Lista para imprimir.",
        )
        descarga_dxf.download_button(
            "Descargar DXF",
            data=actual["dxf"],
            file_name="plano.dxf",
            mime="application/dxf",
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
