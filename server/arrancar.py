"""
Arranca el servidor proxy y lo expone por un túnel de Cloudflare.

Uso (desde la raíz del proyecto):
    python server/arrancar.py

Lee GROQ_API_KEY del .env de la raíz. Si no existe PROXY_ACCESS_TOKEN, lo
genera y lo guarda en ese mismo .env. Al final imprime la PROXY_URL y el
token que hay que compartir con los usuarios.
"""

import os
import re
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv, set_key

RAIZ = Path(__file__).resolve().parent.parent
ENV_FILE = RAIZ / ".env"
SERVIDOR = RAIZ / "server" / "proxy_server.py"
PUERTO = os.getenv("PORT", "8000")
PATRON_URL = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def preparar_configuracion() -> None:
    if not ENV_FILE.exists():
        sys.exit("No existe .env en la raíz del proyecto. Crea uno con GROQ_API_KEY.")

    load_dotenv(ENV_FILE)

    if not os.getenv("GROQ_API_KEY"):
        sys.exit("Falta GROQ_API_KEY en .env.")

    if not os.getenv("PROXY_ACCESS_TOKEN"):
        token = secrets.token_urlsafe(32)
        set_key(str(ENV_FILE), "PROXY_ACCESS_TOKEN", token)
        os.environ["PROXY_ACCESS_TOKEN"] = token
        print("Token de acceso generado y guardado en .env")


RUTAS_CLOUDFLARED = [
    Path(os.getenv("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "cloudflared" / "cloudflared.exe",
    Path(os.getenv("ProgramFiles", r"C:\Program Files")) / "cloudflared" / "cloudflared.exe",
]


def comprobar_cloudflared() -> str:
    ruta = shutil.which("cloudflared") or next(
        (str(r) for r in RUTAS_CLOUDFLARED if r.exists()), None
    )
    if not ruta:
        sys.exit(
            "No se encontró cloudflared. Instálalo una vez con:\n"
            "    winget install --id Cloudflare.cloudflared\n"
            "Luego abre una terminal nueva y vuelve a ejecutar este script."
        )
    return ruta


def main() -> None:
    preparar_configuracion()
    cloudflared = comprobar_cloudflared()

    servidor = subprocess.Popen(
        [sys.executable, str(SERVIDOR)],
        env={**os.environ, "PORT": PUERTO},
    )

    tunel = subprocess.Popen(
        [cloudflared, "tunnel", "--url", f"http://127.0.0.1:{PUERTO}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    url_publica = None
    try:
        for linea in tunel.stdout:
            if url_publica is None:
                coincidencia = PATRON_URL.search(linea)
                if coincidencia:
                    url_publica = coincidencia.group(0)
                    token = os.getenv("PROXY_ACCESS_TOKEN")
                    print("\n" + "=" * 60)
                    print("Servidor listo. Comparte esto con los usuarios:")
                    print(f"  PROXY_URL={url_publica}")
                    print(f"  PROXY_ACCESS_TOKEN={token}")
                    print("=" * 60)
                    print("Mantén esta ventana abierta. Ctrl+C para detener.\n")
        tunel.wait()
    except KeyboardInterrupt:
        pass
    finally:
        for proceso in (tunel, servidor):
            if proceso.poll() is None:
                proceso.terminate()


if __name__ == "__main__":
    main()
