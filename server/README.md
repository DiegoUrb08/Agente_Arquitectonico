# Servidor proxy (modo demo)

Permite que otros usuarios del Agente Arquitectónico generen planos
**sin crear su propia cuenta de Groq**, usando tu clave en el servidor.

⚠️ **Responsabilidad del operador**: tú controlas esta clave y consumes
tu cuota por cada petición. El rate limiting (10 peticiones/hora por IP
por defecto) protege contra abuso, pero no lo elimina. Úsalo solo
como demo para un grupo controlado (amigos, equipo, portafolio).

---

## Opción recomendada — Lanzador local + túnel Cloudflare

No necesitas cuenta en ningún servicio de hosting. Solo necesitas
[cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/) instalado una vez:

```bash
winget install --id Cloudflare.cloudflared   # Windows
brew install cloudflared                      # macOS
```

Pon tu `GROQ_API_KEY` en el `.env` de la raíz del proyecto y ejecuta:

```bash
python server/arrancar.py
```

El script:
1. Lee `GROQ_API_KEY` del `.env`.
2. Genera `PROXY_ACCESS_TOKEN` automáticamente si no existe (lo guarda en `.env`).
3. Arranca `proxy_server.py` con waitress en `127.0.0.1:8000`.
4. Abre un túnel Cloudflare y muestra la URL pública:

```
============================================================
Servidor listo. Comparte esto con los usuarios:
  PROXY_URL=https://xxxx.trycloudflare.com
  PROXY_ACCESS_TOKEN=<token generado>
============================================================
Mantén esta ventana abierta. Ctrl+C para detener.
```

**Limitaciones del túnel rápido:**
- La URL cambia cada vez que reinicias el lanzador.
- El servidor se cae si cierras el PC o la ventana.
- Para una URL fija necesitas un [named tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/get-started/) de Cloudflare (requiere dominio propio).

---

## Opción alternativa — Deploy en Render (gratis, siempre activo)

1. Crea cuenta en [render.com](https://render.com).
2. **New Web Service** → conecta tu repo de GitHub.
3. Configuración:
   - **Root directory**: `server`
   - **Build command**: `pip install -r requirements.txt`
   - **Start command**: `python proxy_server.py`
4. Variables de ambiente:
   - `GROQ_API_KEY=gsk_...`
   - `RATE_LIMIT_REQUESTS=10` (opcional)
   - `RATE_LIMIT_WINDOW_S=3600` (opcional)
   - `PROXY_ACCESS_TOKEN=...` (recomendado si vas a compartir la URL)
5. Deploy. Copia la URL del servicio.

**Nota:** el free tier de Render "duerme" tras 15 min de inactividad; la primera petición tarda ~30 s en despertar.

---

## Cómo lo usan tus usuarios

En su `.env`:

```
LLM_PROVIDER=proxy
PROXY_URL=https://xxxx.trycloudflare.com
PROXY_ACCESS_TOKEN=<el token que mostraste>
```

---

## Verificar que funciona

```bash
curl https://xxxx.trycloudflare.com/health
# {"status": "ok", "groq_configurado": true, "rate_limit": "10 req / 3600s"}
```

---

## Ajustar el límite de peticiones

| Variable | Descripción | Default |
|---|---|---|
| `RATE_LIMIT_REQUESTS` | Peticiones permitidas por IP | `10` |
| `RATE_LIMIT_WINDOW_S` | Ventana de tiempo (segundos) | `3600` (1 hora) |
| `PROXY_ACCESS_TOKEN` | Token que deben enviar los clientes | vacío (sin restricción) |

Para revocar el acceso: cambia `PROXY_ACCESS_TOKEN` o apaga el servidor.
