# Servidor proxy (modo demo)

Permite que otros usuarios del Agente Arquitectónico generen planos
**sin crear su propia cuenta de Groq**, usando tu clave en el servidor.

⚠️ **Responsabilidad del operador**: tú controlas esta clave y pagas
(o consumes tu cuota gratis) por cada petición que haga cualquier
usuario de tu servidor. El rate limiting (10 peticiones/hora por IP
por defecto) protege contra abuso, pero no lo elimina. Úsalo solo
como demo para un grupo controlado (amigos, equipo, portafolio), no
como backend de producción a escala.

## Deploy en Render (gratis)

1. Crea cuenta en [render.com](https://render.com)
2. **New Web Service** → conecta tu repo de GitHub
3. Configuración:
   - **Root directory**: `server`
   - **Build command**: `pip install -r requirements.txt`
   - **Start command**: `python proxy_server.py`
4. Variables de ambiente (Environment):
   - `GROQ_API_KEY=gsk_...` (tu clave, generada en https://console.groq.com/keys)
   - `RATE_LIMIT_REQUESTS=10` (opcional, default 10)
   - `RATE_LIMIT_WINDOW_S=3600` (opcional, default 1 hora)
   - `PROXY_ACCESS_TOKEN=...` (opcional: si lo pones, solo quien tenga
     este token puede usar tu proxy — recomendado si vas a compartir
     la URL públicamente)
5. Deploy. Copia la URL que te da Render (ej: `https://tu-app.onrender.com`)

**Nota sobre el free tier de Render:** el servicio se "duerme" tras 15
min de inactividad y la primera petición tras dormir tarda ~30s en
despertar. Aceptable para una demo, no para uso constante.

## Deploy local (para pruebas, o LAN de confianza)

```bash
cd server
pip install -r requirements.txt
export GROQ_API_KEY=gsk_...       # Linux/Mac
set GROQ_API_KEY=gsk_...          # Windows cmd
$env:GROQ_API_KEY="gsk_..."       # PowerShell

python proxy_server.py
# Servidor en http://localhost:8000
```

## Cómo lo usan tus usuarios

En su `.env`:

```
LLM_PROVIDER=proxy
PROXY_URL=https://tu-app.onrender.com
PROXY_ACCESS_TOKEN=...   # solo si lo configuraste
```

## Verificar que funciona

```bash
curl https://tu-app.onrender.com/health
# {"status": "ok", "groq_configurado": true, "rate_limit": "10 req / 3600s"}
```

## Ajustar o apagar el límite

- Súbelo si confías en tu círculo de usuarios: `RATE_LIMIT_REQUESTS=50`
- Revoca el acceso en cualquier momento: cambia o elimina `GROQ_API_KEY`
  en Render, o apaga el servicio.
