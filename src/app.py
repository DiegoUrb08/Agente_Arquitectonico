
import sys
import traceback
from pathlib import Path

import streamlit as st


# ============================================================
# 1. CONFIGURACION DEL PROYECTO
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ============================================================
# 2. IMPORTACION DE MODULOS
# ============================================================

# Inteligencia artificial
from src.ai.interpreter import interpretar_instruccion
from src.ai.edit_interpreter import interpretar_edicion

# Planificacion espacial
from src.planning.layout_optimizer import optimizar_distribucion

# Geometria
from src.geometry.geometry_generator import generar_geometrias
from src.geometry.adjacency_validator import validar_distribucion
from src.geometry.wall_generator import generar_muros
from src.geometry.door_generator import generar_puertas_automaticas
from src.geometry.opening_generator import generar_aberturas

# CAD
from src.cad.dxf_generator import generar_dxf_desde_geometrias
from src.cad.dxf_reader import analizar_dxf
from src.cad.dxf_editor import editar_dxf


# ============================================================
# 3. CONFIGURACION DE STREAMLIT
# ============================================================

st.set_page_config(
    page_title="Agente Arquitectonico",
    page_icon="🏠",
    layout="wide"
)

st.title("Agente Arquitectonico")

st.write(
    "Sistema de generacion y edicion de planos arquitectonicos "
    "mediante inteligencia artificial."
)


# ============================================================
# 4. FUNCIONES AUXILIARES
# ============================================================

def mostrar_error_tecnico(error):
    """
    Muestra un mensaje de error y su traza tecnica.
    """

    st.error(str(error))

    with st.expander("Consultar detalle tecnico del error"):

        st.code(
            traceback.format_exc(),
            language="python"
        )


def preparar_carpeta_salida():
    """
    Crea la carpeta de salida si no existe.
    """

    carpeta_salida = PROJECT_ROOT / "output"

    carpeta_salida.mkdir(
        parents=True,
        exist_ok=True
    )

    return carpeta_salida


def mostrar_distribucion(distribucion):
    """
    Muestra las dimensiones y posiciones de los ambientes.
    """

    st.subheader("Distribucion de ambientes")

    for i, ambiente in enumerate(distribucion, start=1):

        st.write(f"**Ambiente {i}: {ambiente['nombre']}**")

        col1, col2, col3 = st.columns(3)

        with col1:
            st.write(
                f"Posicion: "
                f"({ambiente['x']}, {ambiente['y']}) m"
            )

        with col2:
            st.write(
                f"Dimensiones: "
                f"{ambiente['ancho']} x {ambiente['largo']} m"
            )

        with col3:
            st.write(
                f"Area: {ambiente['area_m2']} m²"
            )

        st.divider()


def mostrar_validacion_adyacencias(resultado):
    """
    Presenta los resultados de la validacion espacial.
    """

    st.subheader("Validacion de conectividad espacial")

    col1, col2, col3 = st.columns(3)

    with col1:

        st.metric(
            "Adyacencias detectadas",
            resultado["cantidad_adyacencias"]
        )

    with col2:

        st.metric(
            "Grupos conectados",
            resultado["cantidad_componentes"]
        )

    with col3:

        st.metric(
            "Ambientes aislados",
            len(resultado["ambientes_aislados"])
        )

    if resultado["distribucion_conectada"]:

        st.success(
            "Todos los ambientes forman una unica red "
            "de conexiones geometricas."
        )

    else:

        st.warning(
            "La distribucion contiene grupos de ambientes "
            "desconectados."
        )

    # --------------------------------------------------------
    # TABLA DE ADYACENCIAS
    # --------------------------------------------------------

    with st.expander("Consultar adyacencias detectadas"):

        if resultado["adyacencias"]:

            datos = [
                {
                    "Ambiente A": a["ambiente_a"],
                    "Ambiente B": a["ambiente_b"],
                    "Orientacion": a["orientacion"],
                    "Longitud compartida (m)": a["longitud_m"]
                }
                for a in resultado["adyacencias"]
            ]

            st.dataframe(
                datos,
                use_container_width=True
            )

        else:

            st.info("No se detectaron adyacencias.")

    # --------------------------------------------------------
    # COMPONENTES CONECTADOS
    # --------------------------------------------------------

    with st.expander("Consultar grupos de ambientes"):

        for i, componente in enumerate(
            resultado["componentes"],
            start=1
        ):

            st.write(
                f"**Grupo {i}:** {', '.join(componente)}"
            )

    # --------------------------------------------------------
    # AMBIENTES AISLADOS
    # --------------------------------------------------------

    if resultado["ambientes_aislados"]:

        st.error(
            "Ambientes sin conexiones: "
            + ", ".join(resultado["ambientes_aislados"])
        )


def mostrar_puertas(resultado_puertas):
    """
    Presenta las puertas propuestas por el generador.
    """

    puertas = resultado_puertas["puertas"]

    st.subheader("Generacion automatica de puertas")

    st.metric(
        "Puertas propuestas",
        len(puertas)
    )

    if puertas:

        datos = []

        for i, puerta in enumerate(puertas, start=1):

            datos.append({
                "Puerta": i,
                "Ambiente A": puerta.get("ambiente_a", ""),
                "Ambiente B": puerta.get("ambiente_b", ""),
                "Orientacion": puerta["orientacion"],
                "Ancho (m)": puerta["ancho"],
                "Longitud de pared (m)": puerta.get(
                    "longitud_pared_m", 0
                ),
                "Centro": puerta["centro"]
            })

        st.dataframe(
            datos,
            use_container_width=True
        )

    else:

        st.warning(
            "No se pudieron proponer puertas para las "
            "adyacencias detectadas."
        )


# ============================================================
# 5. GENERACION DE UN NUEVO PLANO
# ============================================================

st.header("1. Generar un nuevo plano")

instruccion = st.text_area(
    "Describe el proyecto arquitectonico:",
    height=150,
    placeholder=(
        "Ejemplo: Diseña una vivienda de 150 m² de terreno "
        "con dos dormitorios, sala, comedor, cocina y dos baños."
    )
)


if st.button("Generar plano", type="primary"):

    if not instruccion.strip():

        st.warning(
            "Primero debes escribir una descripcion del proyecto."
        )

    else:

        try:

            # =================================================
            # 5.1 INTERPRETACION DE REQUERIMIENTOS
            # =================================================

            with st.spinner(
                "Interpretando los requerimientos arquitectonicos..."
            ):

                requerimientos = interpretar_instruccion(
                    instruccion
                )

            st.subheader("Requerimientos interpretados")

            st.json(
                requerimientos.model_dump()
            )

            # =================================================
            # 5.2 VALIDACION DE DATOS
            # =================================================

            if requerimientos.datos_faltantes:

                st.warning(
                    "Se necesitan algunos datos adicionales "
                    "antes de generar el plano."
                )

                for dato in requerimientos.datos_faltantes:

                    st.write(f"- {dato}")

            else:

                # =================================================
                # 5.3 OPTIMIZACION DE DISTRIBUCION
                # =================================================

                with st.spinner(
                    "Optimizando la distribucion espacial..."
                ):

                    distribucion = optimizar_distribucion(
                        requerimientos
                    )

                mostrar_distribucion(distribucion)

                # =================================================
                # 5.4 VALIDACION DE ADYACENCIAS
                # =================================================

                with st.spinner(
                    "Validando las conexiones entre ambientes..."
                ):

                    resultado_validacion = validar_distribucion(
                        distribucion
                    )

                mostrar_validacion_adyacencias(
                    resultado_validacion
                )

                # =================================================
                # 5.5 GENERACION DE GEOMETRIAS
                # =================================================

                with st.spinner(
                    "Generando las geometrias de los ambientes..."
                ):

                    resultado_geometrias = generar_geometrias(
                        distribucion,
                        requerimientos.ancho_terreno_m,
                        requerimientos.largo_terreno_m
                    )

                if not resultado_geometrias["valido"]:

                    raise ValueError(
                        "La geometria contiene errores: "
                        + "; ".join(
                            resultado_geometrias["errores"]
                        )
                    )

                st.success(
                    "Geometrias de los ambientes generadas correctamente."
                )

                # =================================================
                # 5.6 GENERACION DE MUROS
                # =================================================

                with st.spinner(
                    "Generando muros exteriores e interiores..."
                ):

                    resultado_muros = generar_muros(
                        ambientes_geometricos=(
                            resultado_geometrias["ambientes"]
                        ),
                        espesor_exterior_m=0.20,
                        espesor_interior_m=0.15
                    )

                st.subheader("Generacion de muros")

                col1, col2, col3 = st.columns(3)

                with col1:

                    st.metric(
                        "Espesor exterior",
                        "0.20 m"
                    )

                with col2:

                    st.metric(
                        "Espesor interior",
                        "0.15 m"
                    )

                with col3:

                    st.metric(
                        "Area de muros",
                        f"{resultado_muros['area_muros_m2']:.2f} m²"
                    )

                st.success(
                    "Muros generados correctamente."
                )

                # =================================================
                # 5.7 GENERACION AUTOMATICA DE PUERTAS
                # =================================================

                with st.spinner(
                    "Calculando las posiciones de las puertas..."
                ):

                    resultado_puertas = generar_puertas_automaticas(
                        distribucion=distribucion,
                        ancho_puerta_m=0.90,
                        espesor_muro_m=0.15
                    )

                mostrar_puertas(resultado_puertas)

                # =================================================
                # 5.8 GENERACION DE ABERTURAS
                # =================================================

                with st.spinner(
                    "Generando aberturas en los muros..."
                ):

                    resultado_aberturas = generar_aberturas(
                        resultado_muros=resultado_muros,
                        aberturas=resultado_puertas["puertas"]
                    )

                st.subheader("Validacion de aberturas")

                col1, col2, col3 = st.columns(3)

                with col1:

                    st.metric(
                        "Puertas procesadas",
                        len(resultado_aberturas["puertas"])
                    )

                with col2:

                    st.metric(
                        "Ventanas procesadas",
                        len(resultado_aberturas["ventanas"])
                    )

                with col3:

                    st.metric(
                        "Area de muros original",
                        f"{resultado_muros['area_muros_m2']:.2f} m²"
                    )

                area_final = resultado_aberturas[
                    "muros_con_aberturas"
                ].area

                st.metric(
                    "Area de muros con aberturas",
                    f"{area_final:.2f} m²"
                )

                st.success(
                    "Las aberturas fueron procesadas y sustraidas "
                    "de la geometria de los muros."
                )

                # =================================================
                # 5.9 GENERACION DEL ARCHIVO DXF
                # =================================================

                with st.spinner(
                    "Construyendo el plano arquitectonico DXF..."
                ):

                    carpeta_salida = preparar_carpeta_salida()

                    ruta_salida = (
                        carpeta_salida / "plano_generado.dxf"
                    )

                    generar_dxf_desde_geometrias(
                        resultado_geometrias=resultado_geometrias,
                        ancho_terreno_m=(
                            requerimientos.ancho_terreno_m
                        ),
                        largo_terreno_m=(
                            requerimientos.largo_terreno_m
                        ),
                        ruta_salida=str(ruta_salida),
                        resultado_muros=resultado_muros,
                        resultado_aberturas=resultado_aberturas
                    )

                # =================================================
                # 5.10 RESULTADO FINAL
                # =================================================

                st.success(
                    "El plano arquitectonico se genero correctamente."
                )

                st.info(
                    "El archivo incluye los ambientes, los muros "
                    "y las puertas generadas automaticamente."
                )

                # -------------------------------------------------
                # DESCARGA DEL DXF
                # -------------------------------------------------

                with open(ruta_salida, "rb") as archivo:

                    contenido_dxf = archivo.read()

                st.download_button(
                    label="Descargar plano DXF",
                    data=contenido_dxf,
                    file_name="plano_generado.dxf",
                    mime="application/dxf"
                )

        except Exception as error:

            st.error(
                f"No se pudo generar el plano: {error}"
            )

            st.subheader(
                "Detalle tecnico del error"
            )

            st.code(
                traceback.format_exc(),
                language="python"
            )


# ============================================================
# 6. EDICION DE UN PLANO EXISTENTE
# ============================================================

st.divider()

st.header("2. Editar un plano existente")

archivo_dxf = st.file_uploader(
    "Subir plano arquitectonico",
    type=["dxf"],
    key="archivo_dxf"
)


if archivo_dxf is not None:

    try:

        # =====================================================
        # 6.1 GUARDAR ARCHIVO ORIGINAL
        # =====================================================

        carpeta_salida = preparar_carpeta_salida()

        ruta_entrada = (
            carpeta_salida / "plano_subido.dxf"
        )

        with open(ruta_entrada, "wb") as archivo:

            archivo.write(
                archivo_dxf.getvalue()
            )

        st.success(
            "Archivo DXF cargado correctamente."
        )

        # =====================================================
        # 6.2 ANALIZAR PLANO
        # =====================================================

        with st.spinner(
            "Analizando el plano arquitectonico..."
        ):

            analisis = analizar_dxf(
                str(ruta_entrada)
            )

        st.subheader(
            "Informacion del plano"
        )

        st.json(analisis)

        # =====================================================
        # 6.3 INTERPRETAR MODIFICACIONES
        # =====================================================

        instruccion_edicion = st.text_area(
            "¿Que modificaciones deseas realizar?",
            height=120,
            placeholder=(
                "Ejemplo: Cambia las dimensiones del dormitorio "
                "principal y agrega una ventana."
            ),
            key="instruccion_edicion"
        )

        if st.button("Aplicar modificaciones"):

            if not instruccion_edicion.strip():

                st.warning(
                    "Primero debes describir las modificaciones."
                )

            else:

                try:

                    # -----------------------------------------
                    # INTERPRETACION
                    # -----------------------------------------

                    with st.spinner(
                        "Interpretando las modificaciones..."
                    ):

                        solicitud = interpretar_edicion(
                            instruccion_edicion
                        )

                    # -----------------------------------------
                    # MODIFICACION DEL DXF
                    # -----------------------------------------

                    ruta_modificada = (
                        carpeta_salida / "plano_modificado.dxf"
                    )

                    with st.spinner(
                        "Aplicando modificaciones al plano..."
                    ):

                        editar_dxf(
                            str(ruta_entrada),
                            str(ruta_modificada),
                            solicitud
                        )

                    st.success(
                        "El plano fue modificado correctamente."
                    )

                    # -----------------------------------------
                    # DESCARGA
                    # -----------------------------------------

                    with open(
                        ruta_modificada,
                        "rb"
                    ) as archivo:

                        contenido_modificado = archivo.read()

                    st.download_button(
                        label="Descargar plano modificado",
                        data=contenido_modificado,
                        file_name="plano_modificado.dxf",
                        mime="application/dxf"
                    )

                except Exception as error:

                    mostrar_error_tecnico(error)

    except Exception as error:

        mostrar_error_tecnico(error)
