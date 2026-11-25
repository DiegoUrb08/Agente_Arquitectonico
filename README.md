# Agente Arquitectónico

Convierte descripciones en lenguaje natural en planos arquitectónicos DXF.  
Escribe "vivienda de 10×20 m con 2 dormitorios, sala y cocina" y obtén el plano listo para abrir en AutoCAD o LibreCAD.

---

## Inicio rápido (3 pasos)

```bash
# 1. Clona el repositorio
git clone https://github.com/<tu-usuario>/Agente_Arquitectonico.git
cd Agente_Arquitectonico

# 2. Instala las dependencias
pip install -r requirements.txt

# 3. Configura el proveedor LLM (ver tabla abajo) y arranca
streamlit run app.py
```

---

## Proveedores LLM

| Proveedor | Costo | Setup | Velocidad |
|---|---|---|---|
| **Groq** *(recomendado)* | 🟢 Gratis, sin tarjeta | 2 min · solo email | ⚡ 100+ tokens/s |
| **Ollama** *(local)* | 🟢 Gratis | 10 min · descarga ~5 GB | ⚠️ Según tu PC |
| **Proxy** *(demo)* | 🟢 Gratis* | Pide URL al operador | ⚡ Igual que Groq |
| **Claude** *(sin probar con la API real)* | 🟡 De pago | Clave API de Anthropic | ⚡ Rápido |

\* Sujeto al límite de peticiones que fije el operador del servidor demo.

---

## Opción A — Groq (recomendada)

Groq es gratuito, sin tarjeta de crédito, y es el default.

1. Abre [console.groq.com/keys](https://console.groq.com/keys) (solo necesitas un email).
2. Haz clic en **Create API key** y copia la clave.
3. Crea el archivo `.env` en la raíz del proyecto:

```
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_...
```

4. Arranca: `streamlit run app.py`

---

## Opción B — Ollama (local, sin internet)

1. Instala Ollama desde [ollama.com](https://ollama.com).
2. Descarga el modelo: `ollama pull qwen3:8b`
3. Crea `.env`:

```
LLM_PROVIDER=ollama
# OLLAMA_HOST=http://localhost:11434  ← opcional, este es el default
```

4. Arranca: `streamlit run app.py`

---

## Opción C — Proxy (modo demo, sin cuenta propia)

Alguien más corre el servidor y comparte la URL contigo.  
Solo necesitas `PROXY_URL` y, si lo exige, `PROXY_ACCESS_TOKEN`.

```
LLM_PROVIDER=proxy
PROXY_URL=https://xxxx.trycloudflare.com
PROXY_ACCESS_TOKEN=...
```

### Si tú quieres ser el operador del proxy

Instala [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/) una vez:

```bash
winget install --id Cloudflare.cloudflared   # Windows
# brew install cloudflared                   # macOS
```

Luego, con tu `GROQ_API_KEY` en `.env`, ejecuta el lanzador:

```bash
python server/arrancar.py
```

Imprimirá una `PROXY_URL` y un `PROXY_ACCESS_TOKEN` que puedes compartir.  
Mantén la ventana abierta mientras otros lo usen.

---

## Opción D — Claude (API de Anthropic, de pago)

> **Aún no probado con la API real.** Está implementado y cubierto por tests con un cliente simulado, y se comprobó que la petición que envía coincide con la documentación de la API, pero nadie lo ha ejecutado todavía con una clave real. Si lo pruebas y falla (o funciona), abre un issue. Una suscripción Claude Pro **no** incluye saldo de API: la clave de la consola se factura aparte.

1. Crea una clave en [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys) (la cuenta necesita saldo).
2. Crea `.env`:

```
LLM_PROVIDER=claude
ANTHROPIC_API_KEY=sk-ant-...
# LLM_CLAUDE_MODEL=claude-opus-5-5  ← opcional, debe ser un modelo Claude 5.x
```

3. Arranca: `streamlit run app.py`

---

## Variables de entorno disponibles

Copia `.env.example` a `.env` y edita lo que necesites.

| Variable | Descripción | Default |
|---|---|---|
| `LLM_PROVIDER` | `groq` / `ollama` / `proxy` / `claude` / `mock` | `groq` |
| `GROQ_API_KEY` | Clave de API de Groq | — |
| `LLM_GROQ_MODEL` | Modelo Groq a usar | `openai/gpt-oss-20b` |
| `OLLAMA_HOST` | URL del servidor Ollama | `http://localhost:11434` |
| `PROXY_URL` | URL del servidor proxy | — |
| `PROXY_ACCESS_TOKEN` | Token de acceso al proxy (opcional) | — |
| `ANTHROPIC_API_KEY` | Clave de la API de Anthropic | — |
| `LLM_CLAUDE_MODEL` | Modelo Claude a usar | `claude-opus-5-5` |

---

## Ejecutar los tests

```bash
# Sin credenciales (usa el MockProvider)
LLM_PROVIDER=mock pytest tests/

# O en Windows PowerShell
$env:LLM_PROVIDER="mock"; pytest tests/
```

Los tests también corren automáticamente en GitHub Actions en cada push.

---

## Estructura del proyecto

```
app.py                  # Punto de entrada (streamlit run app.py)
src/
  ai/                   # Interpretación LLM + proveedores
    providers/          # Groq, Ollama, Proxy, Claude, Mock
  planning/             # Optimizador CP-SAT de distribución de ambientes
  geometry/             # Geometría Shapely (muros, puertas, ventanas)
  cad/                  # Generación y edición de DXF (ezdxf)
  services/             # Pipeline completo: LLM → optimizador → DXF
  ui/                   # Interfaz Streamlit
server/
  proxy_server.py       # Servidor Flask (guarda GROQ_API_KEY server-side)
  arrancar.py           # Lanzador: proxy + túnel Cloudflare
tests/                  # 213 tests pytest
```

---

## Licencia

[MIT](LICENSE)
