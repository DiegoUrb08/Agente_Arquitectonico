# Estado del proyecto – Agente Arquitectónico

Última actualización: 2026-11-24 (tras ampliaciones funcionales C–D: UI multi-piso, escalera DXF, closet).

## Entorno y herramientas
- `.venv` funcional: Python 3.14.7, streamlit 1.67, ollama 0.6.3, ortools 9.15, shapely 2.2, ezdxf 1.4.5, pydantic 2.14, pytest 9.2.
- Git 2.56.1 instalado; rama `main` publicada en https://github.com/DiegoUrb08/Agente_Arquitectonico (público, licencia MIT; publicado el 2026-11-24). `.gitignore` excluye `.venv`, cachés, `.env`, credenciales y `output/`.
- `requirements.txt` (dependencias directas + pytest) y `pytest.ini`.
- Proveedor LLM por defecto: Groq (`openai/gpt-oss-20b`). Alternativa local: Ollama con `qwen3:8b`. Arranque: `streamlit run app.py`.

## Arquitectura actual
| Paquete | Archivos | Función |
|---|---|---|
| `app.py` | launcher | Punto de entrada Streamlit (sin manipular `sys.path`). |
| `src/ui` | `interfaz.py` | UI por secciones; errores esperables con mensaje claro, inesperados con traza. |
| `src/services` | `pipeline.py` | `generar_plano(requerimientos, ruta_dxf, progreso)`: optimización → DXF, sin dependencia de Streamlit. |
| `src/ai` | `interpreter`, `edit_interpreter`, `ollama_client` | Qwen3. `chat_con_reintentos`: timeout 180 s, 2 reintentos, `OllamaError`; no reintenta errores 4xx. |
| `src/models` | `requirements`, `defaults`, `distribucion` | Modelos pydantic, áreas por defecto, contrato tipado de la distribución (`AmbienteDistribuido`, `validar_esquema_distribucion`). |
| `src/utils` | `texto.py` | `normalizar_nombre` único (sin tildes). |
| `src/planning` | `space_graph`, `reglas_ambientes`, `restricciones`, `layout_optimizer` | Grafo; configuración por ambiente; restricción de adyacencia CP-SAT; función `optimizar_distribucion`. |
| `src/geometry` | `geometry_generator`, `adjacency_validator`, `wall_generator`, `door_generator`, `opening_generator`, `furniture_generator` | Geometría Shapely. |
| `src/cad` | `dxf_base`, `dxf_generator`, `dxf_aberturas`, `dxf_mobiliario`, `furniture_symbols`, `dxf_reader`, `dxf_editor` | `dxf_base` define el contrato generador↔editor (capas, XDATA, unidades). |

## Pruebas
- **219 pruebas pytest pasan, 0 skipped** (~35 s; CI en `.github/workflows/tests.yml`): modelos, grafo, defaults, esquema de distribución, geometría, adyacencias, puertas, muros, aberturas, DXF (con y sin mobiliario, escalera con peldaños, multipisos), lector, editor (ida y vuelta con el generador), capa `ai` con Ollama simulado (incluye reintentos, historial y fallback regex), pipeline completo (un piso y múltiples pisos), mobiliario automático (nuevas plantillas) y arranque de la UI con `streamlit.testing.AppTest`.
- Los 12 scripts de `scripts/diagnostico/` se conservan y **todos se ejecutan sin error** (`PYTHONPATH` en la raíz). `diag_space_graph.py` se reescribió para la API actual; `diag_optimizador.py` es el bloque de prueba extraído de `layout_optimizer.py`.
- Las pruebas de `ai` simulan Ollama; el flujo real se verificó aparte (ver más abajo).

## Problemas resueltos
1. **Git:** instalado, repositorio inicializado y commits creados.
2. **`normalizar_nombre` duplicada:** ahora una sola en `src/utils/texto.py`. Corrige un fallo real: `defaults.py` no quitaba tildes, así que "bano" (sin tilde) recibía área/peso genéricos en vez de los de baño. Las tablas de `defaults` usan claves sin tilde.
3. **Cobertura:** nuevas pruebas para `ai`, `dxf_editor`, `dxf_reader`, `furniture_generator`, mobiliario DXF, pipeline y UI.
4. **Archivos grandes:** `dxf_generator.py` (1384 → 594 líneas; `dxf_aberturas`, `dxf_mobiliario`, `dxf_base`), `layout_optimizer.py` (962 → unas 750 líneas; `reglas_ambientes`, `restricciones`), `app.py` (515 líneas de script → launcher + `ui/interfaz.py` + `services/pipeline.py`). Los nombres públicos se siguen exportando desde los módulos originales.
5. **Distribución tipada:** `AmbienteDistribuido` + validación de esquema, aplicada en el pipeline tras el optimizador.
6. **`sys.path`, `except Exception` y Ollama:** eliminado el hack de `sys.path`; los `except Exception` solo quedan en el límite de la UI; excepciones específicas en los intérpretes con `from error`; timeout y reintentos en Ollama.
7. **Acoplamiento editor↔generador:** constantes compartidas en `dxf_base`, y la prueba de ida y vuelta lo vigila.
8. **Script obsoleto** `diag_space_graph`: actualizado.

### Errores reales descubiertos y corregidos al escribir las pruebas
- `dxf_editor.obtener_nombre` leía el **identificador** (`sala_1`) en lugar del nombre ("Sala"), por lo que la edición de áreas nunca encontraba el ambiente en un DXF generado por el propio proyecto.
- `dxf_editor.buscar_texto` encontraba dos etiquetas por ambiente (nombre y área, mismos metadatos) y lanzaba "varias etiquetas"; además movía el texto al centro. Ahora actualiza solo la etiqueta de área.
- La UI llamaba a `analizar_dxf` con una **ruta** cuando esperaba **bytes** (`TypeError` al subir un DXF). `analizar_dxf` ahora acepta bytes o ruta, y la UI pasa los bytes.

## Etapas completadas tras la auditoría
1. **Prueba con Ollama + qwen3:8b reales** (script manual, no automatizado): interpretar una vivienda de 10x20 m (≈50 s), optimizar y generar el DXF (≈4 s, 8 ambientes, conectada), e interpretar ediciones en lenguaje natural. Funciona de extremo a extremo.
   - Hallazgo: una petición fuera del catálogo ("agrega una piscina") hace que el modelo devuelva `area_objetivo: 0`; se rechaza con `ValueError` de validación (correcto, pero el mensaje es técnico).
2. **`mover_ambiente` implementado** en `dxf_editor.py` (`izquierda_de`, `derecha_de`, `arriba_de`, `abajo_de`, `junto_a`, `cerca_de`): coloca el ambiente pegado al de referencia, conserva sus dimensiones, elige la posición válida más cercana a la actual y rechaza posiciones fuera del terreno o con superposición. `lejos_de` se añadió después (ver ampliaciones).
   - Los ambientes se localizan por id (`dormitorio_2`), nombre único o "dormitorio 2", sin importar tildes ni mayúsculas. Antes, nombres repetidos ("dormitorio" ×2) hacían imposible editar.
   - Las etiquetas se desplazan con el ambiente; la UI muestra las modificaciones y los avisos.
3. **`optimizar_distribucion` dividida** en 14 funciones (validación, variables, adyacencias, conectividad por flujo, relaciones, desviaciones, distancias, extracción) con el mismo modelo CP-SAT y el mismo orden de construcción. El solver es multihilo y no determinista, así que la regresión se verificó por el objetivo: la desviación de áreas óptima es idéntica antes y después (0.00 y 0.09 m² en los dos casos de referencia). Se añadieron pruebas de invariantes (sin solapes, dentro del terreno, relaciones cumplidas, conectividad) y de errores.

4. **Validación de capacidad del terreno** (`_validar_capacidad_terreno` en `layout_optimizer.py`): error claro si la suma de áreas mínimas supera el terreno, si el área por piso (`area_total / pisos`) lo supera o si `numero_pisos < 1`.
5. **Mensajes amigables** (`src/ai/errores.py`, `mensaje_amigable`): las respuestas inválidas del modelo (p. ej. "agrega una piscina" → `area_objetivo: 0`) producen una explicación en lenguaje llano con el detalle técnico al final.
6. **Regeneración tras editar** (`pipeline.editar_plano`): la UI aplica la edición sobre la distribución leída del DXF y regenera todo (muros, puertas, aberturas) con `construir_plano`, extraída de `generar_plano`. `dxf_editor` se dividió en `cargar_y_editar` (en memoria) + `distribucion_desde_ambientes`; `editar_dxf` se conserva (edición directa, avisa que no recalcula). Si la edición deja ambientes sin pared compartida, la salida lo avisa.
7. **`modificar_area` conserva el contacto con los vecinos**: prueba el nuevo tamaño centrado y anclado a cada esquina, descarta los que se salen o se superponen y elige el que mantiene más pared compartida (el centrado gana los empates). Las etiquetas se desplazan con el ambiente. Si ningún candidato cabe, se rechaza como antes.

## Ampliaciones funcionales
8. **Amueblado automático** (`src/geometry/mobiliario_automatico.py`): plantillas por tipo de ambiente (sala, comedor, cocina, dormitorio, baño, estudio/oficina). Los muebles se pegan a las paredes (esquinas primero, luego a lo largo de los muros; prueba ambas orientaciones), sin salirse, sin solaparse y sin tapar el radio de cada puerta. Lo que no cabe se informa en `omitidos`. `construir_plano` lo incluye por defecto (`amueblar=False` lo desactiva) y `ResultadoPlano.mobiliario` lo expone; como `editar_plano` usa `construir_plano`, el mobiliario también se regenera al editar.
9. **`lejos_de`** en `mover_ambiente`: recorre una malla de 0,5 m sobre el terreno y elige la posición válida más alejada de la referencia (empate: la más cercana a la actual).
10. **Error latente corregido**: `generar_aberturas` fallaba en ~15 % de las distribuciones ("puerta no está dentro de un muro") porque sumas como 11.4 + 3.7 = 15.100000000000001 desalineaban el borde compartido y el muro interior desaparecía. `construir_poligono_ambiente` redondea ahora a 4 decimales. Antes fallaba en menos de 40 generaciones seguidas; tras la corrección, 120 sin fallos.
11. **Ventanas automáticas** (`src/geometry/window_generator.py`): una pared es exterior si pertenece al perímetro del conjunto de ambientes. Por ambiente se toman hasta 2 de sus tramos exteriores más largos (tramos colineales fusionados), con la ventana centrada en el tramo, margen de 0,40 m a los extremos y ancho según el tipo (sala 1,8 m, comedor 1,5 m, dormitorio/cocina 1,2 m, baño 0,6 m; se reduce si el tramo es corto y se descarta si queda por debajo de 0,5 m). No se colocan en pasillo/clóset/depósito ni donde su hueco (con 5 cm de holgura) toque el de una puerta u otra ventana. Los ambientes que se quedan sin ventana se informan en `ResultadoPlano.ventanas["omitidos"]`. Verificado con 120 planos reales del optimizador sin fallos (una primera versión fallaba en 4 de 45: `linemerge` con tramos sueltos y huecos solapados). Se abren en el muro con `generar_aberturas` y se dibujan en la capa VENTANAS.

## Benchmark LLM (Qwen3:8b) – 2026-11-24

20 casos de petición real ejecutados con `scripts/benchmark_llm.py` (resultados en `docs/benchmark_llm.json`).

| Resultado | Casos |
|---|---|
| Interpretación OK + plano OK + conectado | 15 / 20 |
| Error: terreno no extraído | 4 / 20 |
| Error esperado (prompt ambiguo) | 1 / 20 |

**Hallazgos registrados para corrección futura:**

1. **Ambientes fuera de catálogo se aceptan** – "piscina" en el prompt produjo `area_objetivo: 8 m²` (valor válido para Pydantic) y el plano se generó con ese ambiente. *Resuelto: ver "Correcciones del benchmark", punto 1.*

2. **Extracción intermitente del terreno** – 3 prompts con dimensiones explícitas fallaron (`minimo` "6 x 10 metros", `habitantes` "11 x 20 m", `ingles_mezclado` "10 x 20 meter lot"). El mismo texto en otros casos sí funciona. Causa probable: el modelo omite las dimensiones cuando el texto tiene información que distrae (familia de 5 personas, departamento pequeño, inglés). *Resuelto: ver "Correcciones del benchmark", punto 2.*

3. **Tiempos extremos** – el caso "ambiguo" tardó 452 s (≈ 8 min). *Resuelto: ver "Correcciones del benchmark", punto 3.*

## Limitaciones conocidas
- `editar_plano` regenera muros, puertas, aberturas y mobiliario (se recoloca con las plantillas, no se conservan posiciones previas) y, si un ambiente que actúa de «nudo» cambia mucho de tamaño, puede quedar sin pared compartida con algún vecino (se avisa; no se reubican los vecinos).
- `editar_dxf` (edición directa) sigue sin recalcular muros ni puertas.
- Las ventanas tienen ancho fijo por tipo de ambiente (sin altura de alféizar ni orientación solar) y se colocan en cualquier pared exterior, incluso la que da a un hueco interior entre ambientes.
- El editor solo opera con habitaciones rectangulares y DXF en metros.
- En distribuciones muy compactas, `modificar_area` y `mover_ambiente` suelen rechazar el cambio por falta de espacio (comportamiento correcto, pero limitante).
- El CI de GitHub Actions pasó en su primer run (2026-11-24, 1 min 11 s). Aviso pendiente: `actions/checkout@v4` y `actions/setup-python@v5` usan Node.js 20, que GitHub está retirando (hoy se fuerza Node 24); conviene subir sus versiones.

## Correcciones del benchmark implementadas
1. ~~**Lista blanca de ambientes**~~ **Implementado:** `AMBIENTES_VALIDOS` en `reglas_ambientes.py` (15 tipos); `_validar_ambientes` en `layout_optimizer.py` rechaza tipos fuera de catálogo antes de CP-SAT con mensaje claro. "piscina" se rechaza ahora.
2. ~~**Extracción del terreno**~~ **Implementado:** fallback regex (`_extraer_terreno_por_regex`) en `interpreter.py`; se activa solo cuando el LLM devuelve ancho/largo/area_terreno todos nulos. Busca patrones `NxM` ("6 x 10 metros") y área ("200 m2"). Resuelve los 3 casos fallidos del benchmark (`minimo`, `habitantes`, `ingles_mezclado`).
3. ~~**Reintentos y tiempos**~~ **Implementado:** `chat_con_reintentos` acepta `historial: list` opcional; apenda `{intento, tiempo_s, ok, error}` por cada llamada. `interpretar_instruccion` pasa el historial y, si hubo más de un intento, añade `"[LLM] N intentos: Xs + Ys"` a `requerimientos.observaciones`. El benchmark imprime esta nota en la línea de cada caso.

## Ampliaciones funcionales implementadas
12. **Más plantillas de mobiliario** (`furniture_generator.py`, `furniture_symbols.py`, `dxf_mobiliario.py`, `mobiliario_automatico.py`): tres nuevos tipos (`lavadora` 0,60×0,65 m, `secadora` 0,60×0,65 m, `tina` 1,70×0,75 m) con símbolo DXF propio. Nuevas plantillas en `PLANTILLAS`: `"lavanderia"` → lavadora + secadora; `"terraza"` → mesa_comedor centrada; `"dormitorio principal"` → cama_queen + armario.

13. **Pisos múltiples** (`reglas_ambientes.py`, `layout_optimizer.py`, `dxf_generator.py`, `pipeline.py`): `escalera` añadida al catálogo (`AMBIENTES_VALIDOS`, `DIMENSIONES_REFERENCIA`); nuevos conjuntos `AMBIENTES_PLANTA_BAJA` y `AMBIENTES_PLANTA_ALTA`; `optimizar_por_pisos(req)` divide ambientes por zona, añade escalera a cada piso y los optimiza independientemente; `generar_dxf_multipisos(pisos, …)` apila los pisos verticalmente (separación 3 m) con etiquetas "PLANTA BAJA"/"PLANTA ALTA"; `generar_plano` despacha automáticamente al flujo multipisos cuando `numero_pisos > 1`; nuevo dataclass `ResultadoPlanoMultipisos`. Si todos los ambientes son sociales (planta alta vacía), cae en distribución de un piso.

14. **UI multi-piso** (`interfaz.py`): `generar_plano` puede devolver `ResultadoPlano` o `ResultadoPlanoMultipisos`; la UI detecta el tipo y muestra las plantas en pestañas separadas (`_mostrar_cualquier_resultado`, `mostrar_resultado_multipisos`).

15. **Escalera en el DXF + proporción** (`reglas_ambientes.py`, `dxf_generator.py`): `"escalera"` añadida a `PROPORCIONES_AMBIENTES` (2.5); `dibujar_escalera` dibuja las líneas de peldaños y una flecha de sentido dentro del polígono, llamada automáticamente para cualquier ambiente cuyo nombre empiece por "escalera". El símbolo se aplica tanto en planos de un piso como en `_dibujar_piso` para multipisos.

16. **Closet en plantillas de mobiliario** (`mobiliario_automatico.py`): `"closet"` → armario.

## Plan de acción: soporte multi-LLM con Groq gratis (para publicación en GitHub)

**Objetivo:** permitir que usuarios sin Ollama usen el agente **completamente gratis** (Groq) o con sus propias claves (Claude, OpenAI) o servidor local.

### Fase 1: Abstracción de proveedores LLM (2 horas) — ✅ COMPLETO
- Crear `src/ai/providers/__init__.py` y base class `LLMProvider` (métodos `chat()`, propiedades `nombre`, `modelo`).
- Implementar `GroqProvider` (Groq API, **default gratis, sin tarjeta**).
- Implementar `OllamaProvider` (actual `ollama_client.py`, reutilizar lógica).
- Factory `get_provider()` en `src/ai/interpreter.py` elige según `LLM_PROVIDER` env var.
- Mantener `src/ai/ollama_client.py` para compatibilidad (wrapper a `OllamaProvider`).

### Fase 2: Configuración y dependencias (1 hora) — ✅ COMPLETO
- Crear `.env.example` ✅
- `requirements.txt`: agregar `groq>=0.9`, `python-dotenv>=1.0` ✅
- `app.py`: leer `.env` y validar configuración ✅
- `src/ai/config.py`: LLMConfig con validación clara ✅
- `setup_llm.py`: script interactivo de primer setup ✅
- `.gitignore` ya excluye `.env` ✅

### Fase 3: Tests multi-proveedor (1.5 horas) — ✅ COMPLETO
- `tests/test_ai_providers.py` ampliado con `TestContratosProveedores` (24 tests parametrizados sobre mock, groq, ollama y proxy mockeados) y `TestFactoryEnv` (2 tests). ✅
- Backends simulados sin red ni credenciales reales (todos pasan en CI). ✅
- `.github/workflows/tests.yml`: corre en push/PR a `main`, Python 3.12, `LLM_PROVIDER=mock`. ✅
- Bugs de test corregidos: patch apuntaba a `src.ai.providers.get_provider` en lugar de `src.ai.interpreter.get_provider` (2 tests); fixture del proxy server no limpiaba `PROXY_ACCESS_TOKEN` del entorno (5 tests); UI test no forzaba `LLM_PROVIDER=mock` (1 test). ✅

### Fase 4: Documentación y UI (1 hora) — ✅ COMPLETO (ver "Fase 4 implementada")
- `README.md`: tabla de setup (Groq gratis, Ollama local, Claude/OpenAI con clave). ✅
- Instrucciones de signup Groq (1 min, sin tarjeta). ✅
- `src/ui/interfaz.py`: mostrar provider actual y mensaje si falta configuración. ✅

### Tabla comparativa de proveedores
| Proveedor | Costo | Setup | Velocidad | Modelos |
|-----------|-------|-------|-----------|---------|
| **Groq** (default) | 🟢 Gratis | 2 min signup | 🚀 Ultra rápido | openai/gpt-oss-20b (default), openai/gpt-oss-120b |
| **Ollama** (local) | 🟢 Gratis | 10 min + 2 GB | ⚠️ Según PC | qwen3:8b, otros |
| **Claude** | 🟡 $5 créditos | Clave API | ⚡ Rápido | Opus, Sonnet, Haiku |
| **OpenAI** | 🟡 $5 créditos | Clave API | ⚡ Rápido | GPT-4, 3.5 |

### Por qué Groq como default
- Completamente **gratis, sin tarjeta de crédito** (solo email).
- **Sin descargas** (API remoto).
- Velocidad: 100+ tokens/s (más rápido que OpenAI).
- Rate limits generosos: 8,000 req/min.
- Modelos vigentes: `openai/gpt-oss-20b` (default). Mixtral 8x7B y LLaMA 2 fueron retirados del catálogo de Groq (ver punto 24).

## Ampliaciones implementadas (Fase 1: Multi-LLM)

17. **Abstracción de proveedores LLM** (`src/ai/providers/`):
    - Base class `LLMProvider` con interfaz `chat(messages, temperature, ...)`
    - `GroqProvider` → Groq API (gratis, sin tarjeta, sin descargas)
    - `OllamaProvider` → Ollama local o remoto
    - `MockProvider` → tests sin dependencias externas
    - Factory `get_provider()` lee `LLM_PROVIDER` env var (default: groq)

18. **Configuración por ambiente** (`.env.example`, `python-dotenv`):
    - `LLM_PROVIDER=groq|ollama|claude|openai|mock`
    - `GROQ_API_KEY=gsk_...` (gratis signup en https://console.groq.com)
    - `OLLAMA_HOST=http://localhost:11434` (opcional, fallback local)
    - `app.py` carga `.env` al inicio

19. **Tests multi-proveedor** (`tests/test_ai_providers.py`, 9 tests):
    - MockProvider funciona sin API keys
    - GroqProvider maneja falta de key con mensaje claro
    - OllamaProvider se configura por host
    - Factory devuelve el proveedor correcto

20. **Configuración y validación de ambiente** (`src/ai/config.py`):
    - `LLMConfig.validar_provider()`: valida cada proveedor
    - Mensajes de error amigables con instrucciones (ej: "Visita https://console.groq.com/keys")
    - `LLMConfig.mensaje_bienvenida()`: muestra info del proveedor en uso
    - `app.py` valida config antes de iniciar UI

21. **Script de setup interactivo** (`setup_llm.py`):
    - Menu: 1=Groq, 2=Ollama, 3=Proxy, 4=Salir (Claude se retiró del menú: `get_provider` no lo soporta)
    - Instrucciones paso a paso para cada proveedor
    - Genera `.env` automáticamente con configuración

22. **Tests de configuración** (`tests/test_llm_config.py`, 9 tests):
    - Validación de API keys requeridas
    - Mensajes de bienvenida por proveedor
    - Hosts por defecto (Ollama)
    - Proveedores desconocidos

23. **Servidor proxy (modo demo, sin clave propia)** (`server/proxy_server.py`, `src/ai/providers/proxy_provider.py`):
    - Flask app que guarda `GROQ_API_KEY` server-side (nunca expuesta al cliente)
    - Rate limiting por IP: ventana deslizante en memoria, 10 peticiones/hora por defecto (`RATE_LIMIT_REQUESTS`, `RATE_LIMIT_WINDOW_S`)
    - Token de acceso opcional (`PROXY_ACCESS_TOKEN`) para restringir quién usa el proxy
    - Endpoint `/health` para verificar estado y configuración
    - `ProxyProvider`: cliente que habla con el servidor, maneja 429 (rate limit) y errores de conexión con mensajes claros
    - `LLM_PROVIDER=proxy` + `PROXY_URL=...` en `.env`
    - `setup_llm.py` opción 3: configura el proxy interactivamente
    - `server/README.md`: guía de deploy en Render (free tier) con advertencia explícita de responsabilidad del operador
    - `tests/test_proxy_provider.py` (14 tests): cliente, servidor Flask vía test_client, rate limiting, token inválido

    **Decisión de diseño:** se evaluó embeber una clave compartida en el repo público y se descartó — una sola clave compartida entre todos los clones de GitHub viola los TOS de Groq, es extraíble del historial de git, y cualquier abuso la revoca para todos. El proxy resuelve esto moviendo la clave a un servidor que el operador controla y limita, sin exponerla nunca al cliente.

24. **Prueba end-to-end con clave real de Groq** (servidor local, clave descartada tras la prueba, nunca commiteada — verificado en el historial de git): confirmó rate limiting (ventana deslizante, N peticiones exactas permitidas, N+1 bloqueada con 429), y el pipeline completo (`interpretar_instruccion` → `optimizar_distribucion` → DXF) funcionando en ~6.5 s de punta a punta vía `LLM_PROVIDER=proxy`.
    - **Hallazgo:** el modelo default `mixtral-8x7b-32768` está descontinuado en Groq (`model_decommissioned`, HTTP 400). Confirmado contra `/v1/models` con la clave real: el catálogo vigente no incluye mixtral ni llama2/3 clásicos. Nuevo default: `openai/gpt-oss-20b` (responde JSON limpio, rápido).
    - **Bug encontrado en `.gitignore`:** el patrón `.env.*` excluía también `.env.example` (la plantilla pública sin secretos), por lo que nunca se había versionado pese a crearse en la Fase 2. Corregido con `!.env.example`.

## Fase 3 implementada (2026-11-24)

25. **Tests de contratos multi-proveedor** (`tests/test_ai_providers.py`): clase `TestContratosProveedores` con 6 × 4 tests parametrizados (`mock`, `groq`, `ollama`, `proxy`) que verifican la interfaz `LLMProvider` (nombre, modelo, chat, estructura de respuesta) usando backends simulados sin red. `TestFactoryEnv` verifica que la factory lee `LLM_PROVIDER` del entorno.

26. **GitHub Actions CI** (`.github/workflows/tests.yml`): disparado en push y PR a `main`; Python 3.12; instala `requirements.txt` + `server/requirements.txt`; corre `pytest tests/` con `LLM_PROVIDER=mock`. No requiere credenciales.

27. **Corrección de 8 tests pre-existentes rotos** (descubiertos al correr la suite completa):
    - 2 tests en `test_ai.py` usaban `src.ai.providers.get_provider` como target del patch, pero `interpreter.py` importa con `from ... import`, así que el patch no tenía efecto; corregido a `src.ai.interpreter.get_provider`.
    - 5 tests de `TestProxyServerIntegration` fallaban cuando se corrían después de otros tests que cargaban `.env` y dejaban `PROXY_ACCESS_TOKEN` en `os.environ`; corregido añadiendo `monkeypatch.delenv("PROXY_ACCESS_TOKEN", raising=False)` al fixture.
    - 1 test de UI (`test_la_interfaz_arranca_sin_excepciones`) fallaba con `.env` real que tiene `LLM_PROVIDER=proxy` sin `PROXY_URL`; corregido forzando `LLM_PROVIDER=mock` en el test.

**Resultado: 168 tests pasan, 4 skipped (pre-existentes), 0 fallos.**

## Fase 4 implementada (2026-11-24)

28. **Sidebar de proveedor en la UI** (`src/ui/interfaz.py`, función `_sidebar_proveedor`): muestra en la barra lateral el proveedor activo (Groq, Ollama, Proxy, mock) con nombre, modelo e info relevante. Para proxy incluye advertencia de límite y enlace a Groq. Incluye un expander con instrucciones de `.env` para cambiar de proveedor sin salir de la app.

29. **README.md** (raíz del proyecto): inicio rápido en 3 pasos, tabla comparativa de proveedores, guías paso a paso para Groq (recomendado), Ollama y Proxy; documentación del lanzador `server/arrancar.py`; tabla de variables de entorno; instrucciones para correr tests; mapa de la estructura del proyecto.

30. **server/README.md** actualizado: documenta el lanzador `arrancar.py` con túnel Cloudflare como opción principal (sin cuenta de hosting), sus limitaciones (URL efímera, PC encendido), y mantiene la opción de Render como alternativa siempre activa.

## Preparación para publicar (2026-11-24)

31. **`edit_interpreter` migrado a los proveedores** (`src/ai/edit_interpreter.py`): seguía llamando a Ollama directamente (`chat_con_reintentos`), así que la sección "Editar un plano" no funcionaba con Groq ni con el proxy; la Fase 1 solo había migrado `interpreter.py`. Ahora usa `get_provider()`. Como Groq y el proxy no tienen salida estructurada nativa, el esquema de `EditRequest` se incluye en el prompt de sistema; `format=` se envía solo a Ollama. Verificado con una llamada real a Groq (modificar área y mover ambiente).
32. **`OllamaProvider` ignoraba `temperature`**: el parámetro se aceptaba pero no se enviaba a Ollama. Ahora se reenvía en `options` (el intérprete usa 0,1 y la edición 0).
33. **Tests rehabilitados** (`tests/test_ai.py`): los 3 tests de validación de errores y el de reintentos estaban en `skip` por el mismo patch erróneo de la Fase 3 (apuntaban a `src.ai.providers.get_provider`); además `test_interpretar_edicion_valida` llamaba al Ollama real (20 s y fallaría en CI). Corregido el target del patch. Se eliminaron los 2 tests de "[LLM] N intentos" (esa nota ya no existe), se repusieron los de fallback regex del terreno (4 casos, verificados: fallan sin el fallback) y se añadieron tests de reintentos y temperatura de `OllamaProvider`, que no tenía ninguno.
34. **`setup_llm.py`**: mostraba un modelo retirado; sobrescribía el `.env` completo (habría borrado `GROQ_API_KEY` y `PROXY_ACCESS_TOKEN`) y escribía en el directorio actual. Ahora actualiza solo las claves indicadas, en el `.env` de la raíz. Se retiró la opción Claude, que `get_provider` no soporta. Nuevo `tests/test_setup_llm.py` (5 tests, sobre un `.env` temporal).
35. **Documentación alineada**: README y `.env.example` dejaron de anunciar proveedores inexistentes (ver punto 37 para el estado final de Claude).

36. **`LLMProviderError`** (`providers/base.py`, subclase de `RuntimeError`): Groq, Ollama, el proxy y Claude la lanzan ante fallos esperables (red, cuota, clave, rechazo) y la UI la incluye en `ERRORES_CONTROLADOS`. Antes eran `RuntimeError` genéricos, así que al llegar al límite del proxy (429) el usuario veía "Error inesperado" con traza en lugar del mensaje claro.
37. **`ClaudeProvider`** (`providers/claude_provider.py`, SDK `anthropic>=2,<3`): `LLM_PROVIDER=claude` + `ANTHROPIC_API_KEY`; modelo por defecto `claude-opus-5-5` (`LLM_CLAUDE_MODEL` lo cambia). Detalles no obvios: los mensajes `system` se pasan en el campo `system` de la API; no se envía `temperature` (los modelos Claude 5 la rechazan con 400) ni kwargs de otros proveedores; se usa `output_config.effort="low"` porque la tarea es extraer JSON; un `stop_reason` de rechazo se convierte en `LLMProviderError`. Integrado en la factory, `config.py`, `setup_llm.py` (opción 4), la barra lateral, README y `.env.example`. OpenAI se retiró de `config.py` y de la documentación (nunca se implementó). **Verificado solo con mocks: no hay clave de Anthropic en este entorno, así que falta una prueba real.**

**Resultado: 213 tests pasan, 0 skipped.**

## Publicación y primer arranque (2026-11-24)

38. **Pantalla de bienvenida** (`src/ui/bienvenida.py`, `app.py`): cuando falta configurar el proveedor LLM (sin `.env`, clave ausente, `PROXY_URL` vacío o proveedor desconocido), la app ya no lanza una traza de Python: muestra una pantalla con pestañas para Groq, servidor demo, Ollama y Claude, recomienda `python setup_llm.py`, ofrece "reintentar" y deja el error exacto en un desplegable. `tests/test_bienvenida.py` (6 tests, con el `.env` real anulado). Verificado con `streamlit.testing.AppTest`; **no se revisó visualmente en un navegador**.
39. **Publicación**: repo público con licencia MIT; el README usa ya la URL real del repo y explica el primer arranque.

**Resultado: 219 tests pasan, 0 skipped.**

## Acciones pendientes (priorizadas) — revisión 2026-11-24

### Prioridad alta: antes de publicar en GitHub
- **Probar `ClaudeProvider` con una clave real** de Anthropic (una llamada de interpretación y una de edición). Sin probar a 2026-11-24: el dueño del proyecto no tiene saldo de API y decidió no gastar. Comprobado sin red: el SDK acepta los parámetros enviados y el cuerpo de la petición coincide con la documentación; README y `.env.example` avisan de que no está probado. Coste estimado de una prueba: ~2-3 centavos con `claude-opus-5-5` por plano generado, ~0,1 centavos con `claude-haiku-5-5`.
- **Refusal fallbacks de Claude**: la API admite reintentar automáticamente en otro modelo cuando un clasificador de seguridad rechaza la petición (parámetro `fallbacks` en el endpoint beta). No se activó porque no se pudo probar; hoy un rechazo se muestra como error claro.

### Prioridad media: calidad y robustez
- **Proxy con URL fija**: named tunnel de Cloudflare con dominio propio, o despliegue en Render. Con el túnel rápido la URL cambia en cada reinicio.
- **Rate limit en memoria**: se reinicia con el proceso y es válido solo para un proceso. Suficiente para la demo; no escala a varios workers.
- **Re-ejecutar el benchmark con Groq** (`scripts/benchmark_llm.py`) para comparar calidad y tiempos frente a Qwen3:8b local. Es una sugerencia, no un hallazgo previo.

### Funcionalidad del plano (de "Limitaciones conocidas")
- `editar_dxf` (edición directa) no recalcula muros ni puertas.
- `editar_plano` no reubica los vecinos cuando un ambiente "nudo" cambia mucho de tamaño.
- Ventanas: sin altura de alféizar ni orientación solar; se colocan incluso en un muro que da a un hueco interior.
- El editor solo opera con habitaciones rectangulares y DXF en metros.
- En distribuciones compactas, `modificar_area` y `mover_ambiente` rechazan cambios por falta de espacio.

### Nuevas funciones
- **Exportación BIM** (IfcOpenShell o gbXML). Etapa planeada desde el inicio del proyecto; sin iniciar.
