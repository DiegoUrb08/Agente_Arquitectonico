"""
Servidor proxy para Groq API.

Permite que usuarios del Agente Arquitectónico generen planos sin
tener su propia clave de Groq, usando la clave del operador de este
servidor (variable de ambiente GROQ_API_KEY en ESTE servidor, nunca
expuesta al cliente).

Incluye rate limiting por IP para proteger la cuota del operador.

Despliegue recomendado: Render, Railway o Fly.io (free tier).
Ejecutar localmente: python server/proxy_server.py
"""

import os
import time
from collections import defaultdict, deque
from threading import Lock

from flask import Flask, request, jsonify

app = Flask(__name__)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "10"))
RATE_LIMIT_WINDOW_S = int(os.getenv("RATE_LIMIT_WINDOW_S", "3600"))  # 1 hora

# Token opcional para restringir el acceso al proxy (si se configura,
# los clientes deben enviarlo en el header X-Proxy-Token).
PROXY_ACCESS_TOKEN = os.getenv("PROXY_ACCESS_TOKEN")

# --------------------------------------------------------------------
# RATE LIMITING POR IP (en memoria, sin dependencias externas)
# --------------------------------------------------------------------

_peticiones_por_ip: dict[str, deque] = defaultdict(deque)
_lock = Lock()


def _limite_excedido(ip: str) -> bool:
    """Ventana deslizante: True si la IP ya hizo RATE_LIMIT_REQUESTS
    peticiones en los últimos RATE_LIMIT_WINDOW_S segundos."""
    ahora = time.time()
    with _lock:
        cola = _peticiones_por_ip[ip]
        while cola and ahora - cola[0] > RATE_LIMIT_WINDOW_S:
            cola.popleft()
        if len(cola) >= RATE_LIMIT_REQUESTS:
            return True
        cola.append(ahora)
        return False


# --------------------------------------------------------------------
# ENDPOINT
# --------------------------------------------------------------------

@app.route("/chat", methods=["POST"])
def chat():
    if not GROQ_API_KEY:
        return jsonify({
            "error": "El servidor proxy no tiene GROQ_API_KEY configurada."
        }), 500

    if PROXY_ACCESS_TOKEN:
        token_recibido = request.headers.get("X-Proxy-Token")
        if token_recibido != PROXY_ACCESS_TOKEN:
            return jsonify({"error": "Token de acceso inválido."}), 401

    # El servidor solo escucha en 127.0.0.1: las únicas conexiones que llegan
    # desde localhost son las del túnel de Cloudflare, que fija CF-Connecting-IP.
    # Cualquier otra cabecera enviada por el cliente se ignora.
    ip_cliente = request.remote_addr
    if ip_cliente in ("127.0.0.1", "::1"):
        ip_cliente = request.headers.get("CF-Connecting-IP", ip_cliente)

    if _limite_excedido(ip_cliente):
        return jsonify({
            "error": (
                f"Límite de uso alcanzado ({RATE_LIMIT_REQUESTS} peticiones/"
                f"{RATE_LIMIT_WINDOW_S // 60} min). Usa tu propia clave de Groq "
                "para uso ilimitado: https://console.groq.com/keys"
            )
        }), 429

    datos = request.get_json(force=True, silent=True) or {}
    messages = datos.get("messages")
    temperature = datos.get("temperature", 0.7)
    max_tokens = datos.get("max_tokens", 2048)
    model = datos.get("model", "openai/gpt-oss-20b")

    if not messages:
        return jsonify({"error": "Falta el campo 'messages'."}), 400

    try:
        from groq import Groq
        cliente = Groq(api_key=GROQ_API_KEY)
        respuesta = cliente.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return jsonify({
            "message": {
                "content": respuesta.choices[0].message.content,
                "role": "assistant",
            }
        })

    except Exception as error:
        return jsonify({"error": f"Error al consultar Groq: {error}"}), 502


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "groq_configurado": bool(GROQ_API_KEY),
        "rate_limit": f"{RATE_LIMIT_REQUESTS} req / {RATE_LIMIT_WINDOW_S}s",
    })


if __name__ == "__main__":
    from waitress import serve
    puerto = int(os.getenv("PORT", "8000"))
    serve(app, host="127.0.0.1", port=puerto)
