"""Punto de entrada de Streamlit:  streamlit run app.py"""

import os
from pathlib import Path

# Cargar variables de ambiente desde .env (si existe)
try:
    from dotenv import load_dotenv
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        load_dotenv(env_file)
except ImportError:
    pass  # python-dotenv no instalado, usa variables de ambiente del sistema

from src.ui.interfaz import main

main()
