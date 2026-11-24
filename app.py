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

# Validar configuración de LLM provider
try:
    from src.ai.config import LLMConfig
    provider_name, config = LLMConfig.validar_provider()
    print(LLMConfig.mensaje_bienvenida())
except ValueError as e:
    print(f"\n❌ Error de configuración:\n{e}")
    print(
        "\n💡 Solución rápida para Groq (gratis):\n"
        "  1. Visita https://console.groq.com/keys\n"
        "  2. Copia tu API key\n"
        "  3. Edita .env: GROQ_API_KEY=gsk_...\n"
        "  4. Reinicia la app\n"
    )
    raise

from src.ui.interfaz import main

main()
