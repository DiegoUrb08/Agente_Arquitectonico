# Estado del proyecto – Agente Arquitectónico

Última actualización: 2026-11-24 (tras completar las siguientes etapas).

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
- **64 pruebas pytest, todas pasan** (~10 s): modelos, grafo, defaults, esquema de distribución, geometría, adyacencias, puertas, muros, aberturas, DXF (con y sin mobiliario), lector, editor (ida y vuelta con el generador), capa `ai` con Ollama simulado (incluye reintentos y errores), pipeline completo y arranque de la UI con `streamlit.testing.AppTest`.
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
2. **`mover_ambiente` implementado** en `dxf_editor.py` (`izquierda_de`, `derecha_de`, `arriba_de`, `abajo_de`, `junto_a`, `cerca_de`): coloca el ambiente pegado al de referencia, conserva sus dimensiones, elige la posición válida más cercana a la actual y rechaza posiciones fuera del terreno o con superposición. `lejos_de` lanza `NotImplementedError`.
   - Los ambientes se localizan por id (`dormitorio_2`), nombre único o "dormitorio 2", sin importar tildes ni mayúsculas. Antes, nombres repetidos ("dormitorio" ×2) hacían imposible editar.
   - Las etiquetas se desplazan con el ambiente; la UI muestra las modificaciones y los avisos.
3. **`optimizar_distribucion` dividida** en 14 funciones (validación, variables, adyacencias, conectividad por flujo, relaciones, desviaciones, distancias, extracción) con el mismo modelo CP-SAT y el mismo orden de construcción. El solver es multihilo y no determinista, así que la regresión se verificó por el objetivo: la desviación de áreas óptima es idéntica antes y después (0.00 y 0.09 m² en los dos casos de referencia). Se añadieron pruebas de invariantes (sin solapes, dentro del terreno, relaciones cumplidas, conectividad) y de errores.

4. **Validación de capacidad del terreno** (`_validar_capacidad_terreno` en `layout_optimizer.py`): error claro si la suma de áreas mínimas supera el terreno, si el área por piso (`area_total / pisos`) lo supera o si `numero_pisos < 1`.
5. **Mensajes amigables** (`src/ai/errores.py`, `mensaje_amigable`): las respuestas inválidas del modelo (p. ej. "agrega una piscina" → `area_objetivo: 0`) producen una explicación en lenguaje llano con el detalle técnico al final.

## Limitaciones conocidas
- Tras editar, los **muros, puertas, ventanas y mobiliario no se recalculan** (la salida lo avisa). Solo se mueven/redimensionan ambientes y sus etiquetas.
- El editor solo opera con habitaciones rectangulares y DXF en metros.
- En distribuciones muy compactas, `modificar_area` y `mover_ambiente` suelen rechazar el cambio por falta de espacio (comportamiento correcto, pero limitante).
- Sin remoto Git ni CI.

## Siguientes etapas
1. Regenerar muros/puertas al editar (o permitir ediciones sobre la distribución y regenerar el plano completo en vez de editar el DXF).
2. Ampliaciones funcionales y, después, BIM.
