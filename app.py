"""Punto de entrada de Streamlit:  streamlit run app.py"""

import os
from pathlib import Path

import streamlit as st

# Cargar variables de ambiente desde .env (si existe)
try:
    from dotenv import load_dotenv
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        load_dotenv(env_file)
except ImportError:
    pass  # python-dotenv no instalado, usa variables de ambiente del sistema

# Validar configuración de LLM provider; si falta, mostrar la pantalla de bienvenida
from src.ai.config import LLMConfig

try:
    LLMConfig.validar_provider()
except ValueError as e:
    from src.ui.bienvenida import mostrar_bienvenida
    mostrar_bienvenida(str(e))
    st.stop()

# Solo decorativo: con la salida redirigida (sin UTF-8) los emojis no se pueden
# imprimir, y eso no debe confundirse con un error de configuración.
try:
    print(LLMConfig.mensaje_bienvenida())
except UnicodeEncodeError:
    pass

from src.ui.interfaz import main

main()
