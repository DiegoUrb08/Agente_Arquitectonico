# Estado del proyecto – Agente Arquitectónico

Última actualización: 2026-11-24. Todos los problemas detectados en la auditoría inicial están resueltos. Los algoritmos del optimizador, los prompts de Qwen3 y el dibujo DXF no cambiaron de comportamiento (solo se reubicó código).

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
- **48 pruebas pytest, todas pasan** (~6 s): modelos, grafo, defaults, esquema de distribución, geometría, adyacencias, puertas, muros, aberturas, DXF (con y sin mobiliario), lector, editor (ida y vuelta con el generador), capa `ai` con Ollama simulado (incluye reintentos y errores), pipeline completo y arranque de la UI con `streamlit.testing.AppTest`.
- Los 12 scripts de `scripts/diagnostico/` se conservan y **todos se ejecutan sin error** (`PYTHONPATH` en la raíz). `diag_space_graph.py` se reescribió para la API actual; `diag_optimizador.py` es el bloque de prueba extraído de `layout_optimizer.py`.
- No se probó contra un servidor Ollama real (las pruebas de `ai` lo simulan).

## Problemas resueltos
1. **Git:** instalado, repositorio inicializado y commits creados.
2. **`normalizar_nombre` duplicada:** ahora una sola en `src/utils/texto.py`. Corrige un fallo real: `defaults.py` no quitaba tildes, así que "bano" (sin tilde) recibía área/peso genéricos en vez de los de baño. Las tablas de `defaults` usan claves sin tilde.
3. **Cobertura:** nuevas pruebas para `ai`, `dxf_editor`, `dxf_reader`, `furniture_generator`, mobiliario DXF, pipeline y UI.
4. **Archivos grandes:** `dxf_generator.py` (1384 → 594 líneas; `dxf_aberturas`, `dxf_mobiliario`, `dxf_base`), `layout_optimizer.py` (962 → ~630 líneas; `reglas_ambientes`, `restricciones`), `app.py` (515 líneas de script → launcher + `ui/interfaz.py` + `services/pipeline.py`). Los nombres públicos se siguen exportando desde los módulos originales.
5. **Distribución tipada:** `AmbienteDistribuido` + validación de esquema, aplicada en el pipeline tras el optimizador.
6. **`sys.path`, `except Exception` y Ollama:** eliminado el hack de `sys.path`; los `except Exception` solo quedan en el límite de la UI; excepciones específicas en los intérpretes con `from error`; timeout y reintentos en Ollama.
7. **Acoplamiento editor↔generador:** constantes compartidas en `dxf_base`, y la prueba de ida y vuelta lo vigila.
8. **Script obsoleto** `diag_space_graph`: actualizado.

### Errores reales descubiertos y corregidos al escribir las pruebas
- `dxf_editor.obtener_nombre` leía el **identificador** (`sala_1`) en lugar del nombre ("Sala"), por lo que la edición de áreas nunca encontraba el ambiente en un DXF generado por el propio proyecto.
- `dxf_editor.buscar_texto` encontraba dos etiquetas por ambiente (nombre y área, mismos metadatos) y lanzaba "varias etiquetas"; además movía el texto al centro. Ahora actualiza solo la etiqueta de área.
- La UI llamaba a `analizar_dxf` con una **ruta** cuando esperaba **bytes** (`TypeError` al subir un DXF). `analizar_dxf` ahora acepta bytes o ruta, y la UI pasa los bytes.

## Limitaciones conocidas / pendientes
- `optimizar_distribucion` sigue siendo una función larga (~420 líneas) con un único modelo CP-SAT; se dejó íntegra para no alterar el algoritmo.
- La operación `mover_ambiente` del editor sigue sin implementar (lanza `NotImplementedError`, mostrado como mensaje claro en la UI).
- Verificación manual pendiente con Ollama real y `streamlit run app.py` en el navegador.
- Sin remoto Git ni CI.

## Siguientes etapas
1. Probar el flujo completo con Ollama + Qwen3 real.
2. Implementar `mover_ambiente` y más operaciones de edición.
3. Dividir `optimizar_distribucion` en fases (variables, restricciones, objetivo, extracción) con pruebas de regresión del resultado.
4. Ampliaciones funcionales y, después, BIM.
