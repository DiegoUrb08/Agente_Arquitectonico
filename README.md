# Agente Arquitectónico

Convierte descripciones en lenguaje natural en planos arquitectónicos DXF.  
Escribe "vivienda de 10×20 m con 2 dormitorios, sala y cocina" y obtén el plano listo para abrir en AutoCAD o LibreCAD.

---

## Inicio rápido (3 pasos)

```bash
# 1. Clona el repositorio
git clone https://github.com/DiegoUrb08/Agente_Arquitectonico.git
cd Agente_Arquitectonico

# 2. Instala las dependencias (Python 3.10 a 3.14, de 64 bits)
pip install -r requirements.txt

# 3. Arranca (la primera vez te guía para elegir un proveedor)
streamlit run app.py
```

Si aún no has configurado un proveedor LLM, la app muestra una pantalla de
bienvenida con los pasos. También puedes ejecutar `python setup_llm.py`, un
asistente que crea el archivo `.env` por ti.

## Cómo se usa

1. **Describe el proyecto** ("Vivienda de 10 x 20 m con sala, comedor, cocina,
   2 dormitorios y 2 baños"), elige uno de los ejemplos o abre un plano `.dxf`
   que ya tengas.
2. **Mira el plano** en pantalla: habitaciones, muros, puertas, ventanas,
   mobiliario y cotas, con capas que puedes activar y desactivar. Puedes ver
   el terreno completo o ajustar la vista a la vivienda. La capa **Medidas**
   traza el ancho y el largo de cada ambiente (entre ejes de muro, como las
   áreas); en el DXF van como cotas en la capa `MEDIDAS`.
   Con **Vista 3D** lo ves como maqueta, con los techos abiertos: arrastra
   para girar la cámara y usa la rueda para acercarte. Activa **Detalle alto**
   para añadir decoración (sillas, veladores, alfombras, TV, plantas…), suelos
   de madera y cerámica, marcos, zócalos e iluminación realista; puede ir más
   lento en equipos modestos. Funciona sin internet.
   El botón **Pantalla completa** de cada visor (2D o 3D) lo amplía a toda la
   pantalla; sales con el mismo botón o con Esc.
3. **Pídele cambios en la conversación**: *«reduce el comedor a 8 m²»* o
   *«pon la cocina al lado del dormitorio»*. Cada cambio crea una
   versión nueva, resalta en el plano lo que cambió y puedes **deshacerlo**.
4. **Descarga** el plano en DXF (AutoCAD, LibreCAD...), una imagen en SVG, el
   cuadro de áreas en CSV y el **modelo BIM en IFC4** (espacios, muros, puertas,
   ventanas, losa y mobiliario), que se abre en Revit 2020+, ArchiCAD 23+,
   BlenderBIM o visores gratuitos como BIM Vision.

### Qué puedes pedir en la conversación

| Cambio | Ejemplo |
|---|---|
| Cambiar un área | «amplía la sala a 24 m²» |
| Reubicar | «pon la cocina al lado del dormitorio» |
| Agregar | «agrega un estudio de 9 m² junto a la sala» |
| Quitar | «quita un baño» |
| Renombrar | «llama cocina al ambiente 1» |
| En dos plantas | «agrega un baño abajo», «pasa el estudio a la planta baja» |

Si no hay sitio, se reorganiza la planta alterándola lo menos posible y el chat
dice qué más cambió. Si dices «el dormitorio» y hay varios, al reubicar vale
cualquiera y al quitar se elimina el último.

### Casas de dos plantas

La planta alta lleva dormitorios y baños (uno baja si arriba hay dos o más),
la escalera queda en la misma posición en ambas y se busca que compartan
contorno. Si tras un cambio la planta alta sobresale, el plano lo avisa. La
escalera no se puede editar. El `.dxf` descargado, de una o dos plantas, se
puede volver a abrir en la app para seguir editándolo.

### Abrir un DXF de otro programa

«¿Ya tienes un plano?» acepta DXF de AutoCAD, LibreCAD u otros programas. Las
habitaciones se detectan por sus contornos cerrados o, si no los hay, por los
espacios que encierran los muros (los vanos de puerta de hasta 0,9 m se
cierran). Se deducen las unidades, se endereza un plano girado y los nombres
se traducen («LIVING» → sala, «SS.HH.» → baño, «Dorm. 2» → dormitorio). Las
habitaciones sin nombre reconocible se llaman «ambiente N» y se pueden
renombrar por chat. Las formas irregulares se aproximan a rectángulos, y
muros, puertas, ventanas y muebles se dibujan de nuevo. Dos grupos de
habitaciones separados se toman como planta baja y alta. No admite DWG.

### Guardar y retomar un proyecto

Con el autoguardado activado (`AUTOGUARDADO=1` en `.env`), cada proyecto se
guarda solo, tras cada cambio, en la carpeta `proyectos/` de tu equipo. La
pantalla de inicio los lista en **Mis proyectos** para abrirlos
(con la conversación y todas las versiones, así «Deshacer» sigue funcionando)
o borrarlos. **Guardar en archivo** descarga un `.proyecto.json` para llevarlo
a otro equipo y se abre con «Importar un proyecto guardado».

El archivo guarda los ambientes de cada versión; muros, puertas, ventanas y
muebles se vuelven a calcular al abrirlo, así que reabrir tarda más cuantas más
versiones tenga (unos 3 s con 30).

> El autoguardado viene **desactivado**: quien pueda abrir la app vería y
> podría borrar los proyectos de «Mis proyectos». Actívalo con
> `AUTOGUARDADO=1` solo en tu equipo. «Guardar en archivo» siempre está
> disponible.

## Reglas de distribución

Se aplican aunque no las pidas; lo que pidas expresamente (p. ej. qué ambientes
van juntos) tiene prioridad.

- Puerta a la calle en la sala (o el ambiente de entrada), en el frente.
- A cada ambiente se llega sin cruzar dormitorios ni baños. A dormitorios y
  baños se entra desde el pasillo, la sala o la escalera.
- Si hay varios dormitorios y baños, se añade un pasillo.
- Los baños no comparten pared y, si hay dos o más, uno es privado de un
  dormitorio.
- La cocina va junto al comedor (o a la sala).
- La vivienda sale compacta, sin huecos, y procurando que cada ambiente toque
  el exterior para tener ventana. Para lograrlo las áreas pueden variar
  alrededor de un 12 % y generar cada planta tarda unos segundos más.

- Las ventanas van centradas en las paredes exteriores o junto a la puerta; en
  una fachada angosta la entrada se corre a un lado para que quepan ambas. A un
  hueco entre ambientes solo dan si es un patio (4 m² y 1,5 m de ancho).

### Orientación al sol

Indica dónde está el norte, visto desde la calle, con la opción **¿Dónde está
el norte?** o en la descripción («el norte está a la derecha», «la fachada mira
al este»). La sala busca el norte (luego el este) y los dormitorios el este
(sol de la mañana, luego el norte); el oeste queda último por el calor de la
tarde. El criterio está pensado para Perú. Es una preferencia: no siempre se
puede cumplir en todos los ambientes. El plano muestra la flecha de norte, la
tabla de ambientes indica hacia dónde miran las ventanas y el chat lo resume.

Si el terreno no permite cumplirlas todas, el plano se genera igualmente y
muestra cuáles no se cumplen. La ventana no está garantizada: un ambiente que
quede sin pared exterior se avisa.

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
| `AUTOGUARDADO` | `1` activa el guardado automático y «Mis proyectos» | `0` |
| `AGENTE_PROYECTOS_DIR` | Carpeta de los proyectos guardados | `proyectos/` |

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
  bim/                  # Exportación a IFC4 (IfcOpenShell)
  ui/                   # Interfaz Streamlit: tema blueprint, vista previa SVG del plano
server/
  proxy_server.py       # Servidor Flask (guarda GROQ_API_KEY server-side)
  arrancar.py           # Lanzador: proxy + túnel Cloudflare
static/three/           # Copia fija de Three.js 0.160.0 (MIT) para la vista 3D sin internet
tests/                  # 530 tests pytest
```

---

## Licencia

[MIT](LICENSE). Incluye una copia de [Three.js](https://threejs.org) (MIT, ver `static/three/LICENSE`).
