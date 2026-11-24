# Estado del proyecto – Agente Arquitectónico

Última actualización: 2026-11-24 (tras ampliaciones funcionales C–D: UI multi-piso, escalera DXF, closet).

## Entorno y herramientas
- `.venv` funcional: Python 3.14.7, streamlit 1.67, ollama 0.6.3, ortools 9.15, shapely 2.2, ezdxf 1.4.5, pydantic 2.14, pytest 9.2.
- Git 2.56.1 instalado; repositorio local en rama `main` (sin remoto; nada publicado). `.gitignore` excluye `.venv`, cachés, `.env`, credenciales y `output/`.
- `requirements.txt` (dependencias directas + pytest) y `pytest.ini`.
- Modelo LLM: `qwen3:8b`. Arranque: `streamlit run app.py`.

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
- **114 pruebas pytest, todas pasan** (~13 s): modelos, grafo, defaults, esquema de distribución, geometría, adyacencias, puertas, muros, aberturas, DXF (con y sin mobiliario, escalera con peldaños, multipisos), lector, editor (ida y vuelta con el generador), capa `ai` con Ollama simulado (incluye reintentos, historial y fallback regex), pipeline completo (un piso y múltiples pisos), mobiliario automático (nuevas plantillas) y arranque de la UI con `streamlit.testing.AppTest`.
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

1. **Ambientes fuera de catálogo se aceptan** – "piscina" en el prompt produjo `area_objetivo: 8 m²` (valor válido para Pydantic) y el plano se generó con ese ambiente. El mecanismo `mensaje_amigable` solo actúa sobre `ValidationError`; no hay rechazo cuando el modelo asigna un área válida a un ambiente no soportado. Solución pendiente: lista blanca de ambientes válidos que el `layout_optimizer` o el intérprete compruebe antes de optimizar.

2. **Extracción intermitente del terreno** – 3 prompts con dimensiones explícitas fallaron (`minimo` "6 x 10 metros", `habitantes` "11 x 20 m", `ingles_mezclado` "10 x 20 meter lot"). El mismo texto en otros casos sí funciona. Causa probable: el modelo omite las dimensiones cuando el texto tiene información que distrae (familia de 5 personas, departamento pequeño, inglés). Solución pendiente: reintentar la extracción si `ancho_terreno_m` o `largo_terreno_m` llegan nulos pero el prompt contiene patrones numéricos; o añadir una segunda pasada de extracción centrada solo en el terreno.

3. **Tiempos extremos** – el caso "ambiguo" tardó 452 s (≈ 8 min). Los reintentos internos de Ollama no quedan registrados en el benchmark. Solución pendiente: registrar número de reintentos y tiempo por intento en la respuesta del intérprete.

## Limitaciones conocidas
- `editar_plano` regenera muros, puertas, aberturas y mobiliario (se recoloca con las plantillas, no se conservan posiciones previas) y, si un ambiente que actúa de «nudo» cambia mucho de tamaño, puede quedar sin pared compartida con algún vecino (se avisa; no se reubican los vecinos).
- `editar_dxf` (edición directa) sigue sin recalcular muros ni puertas.
- Las ventanas tienen ancho fijo por tipo de ambiente (sin altura de alféizar ni orientación solar) y se colocan en cualquier pared exterior, incluso la que da a un hueco interior entre ambientes.
- El editor solo opera con habitaciones rectangulares y DXF en metros.
- En distribuciones muy compactas, `modificar_area` y `mover_ambiente` suelen rechazar el cambio por falta de espacio (comportamiento correcto, pero limitante).
- Sin remoto Git ni CI.

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

### Fase 3: Tests multi-proveedor (1.5 horas)
- Crear `tests/test_ai_providers.py` con tests para Groq, Ollama, mock (simulado siempre disponible).
- Parametrizar tests: `@pytest.mark.parametrize("provider", ["mock", "groq"])`.
- Mock provider devuelve respuestas hardcoded (sin red).
- CI/GitHub Actions: correr tests con `LLM_PROVIDER=mock` (sin credenciales).

### Fase 4: Documentación y UI (1 hora)
- `README.md`: tabla de setup (Groq gratis, Ollama local, Claude/OpenAI con clave).
- Instrucciones de signup Groq (1 min, sin tarjeta).
- `src/ui/interfaz.py`: mostrar provider actual y mensaje si falta configuración.

### Tabla comparativa de proveedores
| Proveedor | Costo | Setup | Velocidad | Modelos |
|-----------|-------|-------|-----------|---------|
| **Groq** (default) | 🟢 Gratis | 2 min signup | 🚀 Ultra rápido | Mixtral, LLaMA 2 |
| **Ollama** (local) | 🟢 Gratis | 10 min + 2 GB | ⚠️ Según PC | qwen3:8b, otros |
| **Claude** | 🟡 $5 créditos | Clave API | ⚡ Rápido | Opus, Sonnet, Haiku |
| **OpenAI** | 🟡 $5 créditos | Clave API | ⚡ Rápido | GPT-4, 3.5 |

### Por qué Groq como default
- Completamente **gratis, sin tarjeta de crédito** (solo email).
- **Sin descargas** (API remoto).
- Velocidad: 100+ tokens/s (más rápido que OpenAI).
- Rate limits generosos: 8,000 req/min.
- Modelos open: Mixtral 8x7B (comparable a GPT-3.5), LLaMA 2 70B.

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
    - Menu: 1=Groq, 2=Ollama, 3=Claude, 4=Salir
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

## Siguientes etapas
1. Fase 3: Tests y CI multiproveedor.
2. Fase 4: UI mejorada con selector de proveedor.
3. BIM export (IfcOpenShell o gbXML).
