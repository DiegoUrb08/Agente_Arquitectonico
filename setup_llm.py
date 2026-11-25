#!/usr/bin/env python3
"""Script interactivo para configurar el proveedor LLM."""

from pathlib import Path

from dotenv import set_key

ENV_FILE = Path(__file__).resolve().parent / ".env"
MODELO_GROQ = "openai/gpt-oss-20b"
MODELO_CLAUDE = "claude-opus-5-5"


def _guardar_env(**valores: str) -> None:
    """Actualiza solo las claves indicadas y conserva el resto del .env."""
    ENV_FILE.touch(exist_ok=True)
    for clave, valor in valores.items():
        set_key(str(ENV_FILE), clave, valor, quote_mode="never")


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

    _guardar_env(LLM_PROVIDER="groq", GROQ_API_KEY=api_key)
    print("\n✅ Groq configurado en .env")
    print(f"   Modelo: {MODELO_GROQ}")
    print("   Precio: Gratis")
    return True


def setup_ollama():
    """Configurar Ollama (local)."""
    print("\n🚀 Configuración de Ollama (Local)\n" + "=" * 50)
    print("Pasos:")
    print("  1. Descarga: https://ollama.com")
    print("  2. Instala y ejecuta: ollama pull qwen3:8b")
    print("  3. Ollama se ejecuta en http://localhost:11434")
    print()
    host = input("Host de Ollama [http://localhost:11434]: ").strip()
    if not host:
        host = "http://localhost:11434"

    _guardar_env(LLM_PROVIDER="ollama", OLLAMA_HOST=host)
    print("\n✅ Ollama configurado en .env")
    print(f"   Host: {host}")
    return True


def setup_proxy():
    """Configurar proxy (servidor demo de un tercero)."""
    print("\n🚀 Configuración de Proxy (Servidor demo, sin clave propia)\n" + "=" * 50)
    print("Necesitas la URL de un servidor proxy ya desplegado")
    print("(ver server/README.md si quieres desplegar el tuyo).")
    print("Sujeto al límite de peticiones que imponga su operador.")
    print()
    proxy_url = input("URL del servidor proxy (ej: https://xxxx.trycloudflare.com): ").strip()

    if not proxy_url:
        print("❌ URL vacía")
        return False

    token = input("Token de acceso (Enter si no te pidieron uno): ").strip()

    valores = {"LLM_PROVIDER": "proxy", "PROXY_URL": proxy_url}
    if token:
        valores["PROXY_ACCESS_TOKEN"] = token
    _guardar_env(**valores)
    print("\n✅ Proxy configurado en .env")
    print(f"   Servidor: {proxy_url}")
    print("   Nota: para uso ilimitado, usa tu propia clave Groq (opción 1)")
    return True


def setup_claude():
    """Configurar Claude (API de Anthropic, de pago)."""
    print("\n🚀 Configuración de Claude (API de Anthropic, de pago)\n" + "=" * 50)
    print("Pasos:")
    print("  1. Abre: https://console.anthropic.com/settings/keys")
    print("  2. Crea una API key (la cuenta necesita saldo)")
    print("  3. Pégala aquí")
    print()
    api_key = input("Pega tu ANTHROPIC_API_KEY: ").strip()

    if not api_key:
        print("❌ API key vacía")
        return False

    _guardar_env(LLM_PROVIDER="claude", ANTHROPIC_API_KEY=api_key)
    print("\n✅ Claude configurado en .env")
    print(f"   Modelo: {MODELO_CLAUDE}")
    print("   Precio: de pago, según uso")
    return True


def main():
    """Menu principal."""
    print("\n" + "=" * 60)
    print(" 🏗️  AGENTE ARQUITECTÓNICO - Setup de LLM Provider")
    print("=" * 60)
    print("\nOpciones de proveedor:")
    print("  1️⃣  Groq (Recomendado - Gratis, sin tarjeta, cuota propia)")
    print("  2️⃣  Ollama (Local - Requiere instalación)")
    print("  3️⃣  Proxy (Demo de un tercero - Sin crear cuenta, con límite)")
    print("  4️⃣  Claude (API de Anthropic - De pago)")
    print("  5️⃣  Salir")
    print()

    choice = input("Elige una opción (1-5): ").strip()

    acciones = {
        "1": setup_groq,
        "2": setup_ollama,
        "3": setup_proxy,
        "4": setup_claude,
    }

    if choice in acciones:
        if acciones[choice]():
            print("\n🎉 Setup completo. Ejecuta: streamlit run app.py")
    elif choice == "5":
        print("👋 Adiós")
    else:
        print("❌ Opción no válida")
        main()


if __name__ == "__main__":
    main()
