#!/usr/bin/env python3
"""Script interactivo para configurar el proveedor LLM."""

import os
from pathlib import Path


def setup_groq():
    """Configurar Groq (gratis)."""
    print("\n🚀 Configuración de Groq (Gratis, sin tarjeta)\n" + "=" * 50)
    print("Pasos:")
    print("  1. Abre: https://console.groq.com/keys")
    print("  2. Haz login o crea cuenta (con email o GitHub)")
    print("  3. Genera una API key (copia al portapapeles)")
    print()
    api_key = input("Pega tu GROQ_API_KEY: ").strip()

    if not api_key:
        print("❌ API key vacía")
        return False

    env_content = f"LLM_PROVIDER=groq\nGROQ_API_KEY={api_key}\n"
    Path(".env").write_text(env_content)
    print(f"\n✅ Groq configurado en .env")
    print(f"   Modelo: Mixtral 8x7B")
    print(f"   Precio: Gratis")
    return True


def setup_ollama():
    """Configurar Ollama (local)."""
    print("\n🚀 Configuración de Ollama (Local)\n" + "=" * 50)
    print("Pasos:")
    print("  1. Descarga: https://ollama.ai")
    print("  2. Instala y abre: ollama pull qwen3:8b")
    print("  3. Ollama se ejecuta en http://localhost:11434")
    print()
    host = input("Host de Ollama [http://localhost:11434]: ").strip()
    if not host:
        host = "http://localhost:11434"

    env_content = f"LLM_PROVIDER=ollama\nOLLAMA_HOST={host}\n"
    Path(".env").write_text(env_content)
    print(f"\n✅ Ollama configurado en .env")
    print(f"   Host: {host}")
    return True


def setup_claude():
    """Configurar Claude API."""
    print("\n🚀 Configuración de Claude\n" + "=" * 50)
    print("Pasos:")
    print("  1. Abre: https://console.anthropic.com/keys")
    print("  2. Genera una API key")
    print("  3. Pega aquí")
    print()
    api_key = input("Pega tu ANTHROPIC_API_KEY: ").strip()

    if not api_key:
        print("❌ API key vacía")
        return False

    env_content = f"LLM_PROVIDER=claude\nANTHROPIC_API_KEY={api_key}\n"
    Path(".env").write_text(env_content)
    print(f"\n✅ Claude configurado en .env")
    return True


def main():
    """Menu principal."""
    print("\n" + "=" * 60)
    print(" 🏗️  AGENTE ARQUITECTÓNICO - Setup de LLM Provider")
    print("=" * 60)
    print("\nOpciones de proveedor:")
    print("  1️⃣  Groq (Recomendado - Gratis, sin tarjeta)")
    print("  2️⃣  Ollama (Local - Requiere instalación)")
    print("  3️⃣  Claude (API - Requiere clave)")
    print("  4️⃣  Salir")
    print()

    choice = input("Elige una opción (1-4): ").strip()

    if choice == "1":
        if setup_groq():
            print("\n🎉 Setup completo. Ejecuta: streamlit run app.py")
    elif choice == "2":
        if setup_ollama():
            print("\n🎉 Setup completo. Ejecuta: streamlit run app.py")
    elif choice == "3":
        if setup_claude():
            print("\n🎉 Setup completo. Ejecuta: streamlit run app.py")
    elif choice == "4":
        print("👋 Adiós")
    else:
        print("❌ Opción no válida")
        main()


if __name__ == "__main__":
    main()
