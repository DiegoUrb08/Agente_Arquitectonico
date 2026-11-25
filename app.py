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
try:
    from src.ai.config import LLMConfig
    provider_name, config = LLMConfig.validar_provider()
    print(LLMConfig.mensaje_bienvenida())
except ValueError as e:
    from src.ui.bienvenida import mostrar_bienvenida
    mostrar_bienvenida(str(e))
    st.stop()

from src.ui.interfaz import main

main()
