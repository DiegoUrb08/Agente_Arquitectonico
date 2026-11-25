"""Pantalla de bienvenida: se muestra cuando falta configurar el proveedor LLM."""

import streamlit as st

ENV_GROQ = "LLM_PROVIDER=groq\nGROQ_API_KEY=pega_aqui_tu_clave"
ENV_PROXY = "LLM_PROVIDER=proxy\nPROXY_URL=https://...\nPROXY_ACCESS_TOKEN=..."
ENV_OLLAMA = "LLM_PROVIDER=ollama"
ENV_CLAUDE = "LLM_PROVIDER=claude\nANTHROPIC_API_KEY=pega_aqui_tu_clave"


def mostrar_bienvenida(detalle: str) -> None:
    """Explica cómo configurar un proveedor; `detalle` es el error de validación."""

    st.set_page_config(
        page_title="Agente Arquitectónico",
        page_icon="🏠",
        layout="centered",
    )

    st.title("Agente Arquitectónico")
    st.subheader("Falta un paso para empezar")
    st.write(
        "Para interpretar tus descripciones, el agente necesita conectarse "
        "a un modelo de inteligencia artificial. Elige una de estas opciones."
    )

    st.info(
        "**La forma más rápida:** abre una terminal en la carpeta del proyecto "
        "y ejecuta `python setup_llm.py`. Te guía paso a paso y crea el "
        "archivo `.env` por ti."
    )

    tab_groq, tab_proxy, tab_ollama, tab_claude = st.tabs(
        ["Groq (gratis)", "Servidor demo", "Ollama (local)", "Claude (de pago)"]
    )

    with tab_groq:
        st.markdown(
            "**Recomendado.** Gratis y sin tarjeta de crédito; solo necesitas "
            "una cuenta.\n\n"
            "1. Crea una cuenta en [console.groq.com](https://console.groq.com).\n"
            "2. En [console.groq.com/keys](https://console.groq.com/keys) pulsa "
            "**Create API key** y copia la clave.\n"
            "3. En la carpeta del proyecto crea un archivo llamado `.env` con:"
        )
        st.code(ENV_GROQ, language="bash")

    with tab_proxy:
        st.markdown(
            "Si alguien ejecuta un servidor demo, no necesitas cuenta propia.\n\n"
            "1. Pídele la **URL** y el **token** de acceso.\n"
            "2. Crea el archivo `.env` con:"
        )
        st.code(ENV_PROXY, language="bash")
        st.caption(
            "Tiene un límite de peticiones por hora y funciona solo mientras "
            "el operador mantenga su servidor encendido."
        )

    with tab_ollama:
        st.markdown(
            "Funciona sin internet y sin cuenta, pero necesita instalar un "
            "modelo en tu computadora (varios GB).\n\n"
            "1. Instala Ollama desde [ollama.com](https://ollama.com).\n"
            "2. En una terminal ejecuta `ollama pull qwen3:8b`.\n"
            "3. Crea el archivo `.env` con:"
        )
        st.code(ENV_OLLAMA, language="bash")

    with tab_claude:
        st.markdown(
            "Requiere una clave de la API de Anthropic con saldo. Una "
            "suscripción Claude Pro **no** incluye saldo de API.\n\n"
            "1. Crea una clave en "
            "[console.anthropic.com](https://console.anthropic.com/settings/keys).\n"
            "2. Crea el archivo `.env` con:"
        )
        st.code(ENV_CLAUDE, language="bash")
        st.caption("Este proveedor aún no se ha probado con la API real.")

    st.divider()

    if st.button("Ya lo configuré, reintentar", type="primary"):
        st.rerun()
    st.caption(
        "Si sigue mostrando esta pantalla, cierra la app (Ctrl+C) y vuelve a "
        "ejecutar `streamlit run app.py`."
    )

    with st.expander("¿Qué falló exactamente?"):
        st.code(detalle.strip(), language="text")
