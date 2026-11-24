# Estado del proyecto – Agente Arquitectónico

Última actualización: 2026-11-23 (tras la preparación para modificar con seguridad). No se han tocado algoritmos, interpretación Qwen3, generación DXF ni BIM.

## Entorno y herramientas
- `.venv` funcional: Python 3.14.7, streamlit 1.67, ollama 0.6.3, ortools 9.15, shapely 2.2, ezdxf 1.4.5, pydantic 2.14, pytest 9.2.
- Modelo LLM: `qwen3:8b` (`src/ai/ollama_client.py`).
- **Git NO está instalado** en el equipo (no está en el PATH ni en las rutas habituales), por lo que el repositorio **no se pudo inicializar**. Sí existe `.gitignore`. Pendiente: instalar Git (p. ej. `winget install Git.Git`) y ejecutar `git init`.
- `requirements.txt` creado (rangos compatibles con el entorno actual; solo dependencias directas + pytest). `requests` no se incluye porque el código no lo importa.
- `pytest.ini` creado (`testpaths = tests`, `pythonpath = .`).

## Módulos
| Paquete | Archivo | Función |
|---|---|---|
| `src/app.py` | UI Streamlit (515 líneas) | Orquesta: interpretar → optimizar → geometría → validar → muros/puertas/ventanas → DXF; edición y análisis de DXF. |
| `ai` | `interpreter.py`, `edit_interpreter.py`, `ollama_client.py` | Interpretación de instrucciones y ediciones con Ollama/Qwen3. |
| `models` | `requirements.py`, `defaults.py` | Modelos pydantic; áreas/pesos por defecto; dimensiones de terreno. |
| `planning` | `space_graph.py`, `layout_optimizer.py` | Grafo de relaciones; optimización CP-SAT (OR-Tools). |
| `geometry` | `geometry_generator`, `adjacency_validator`, `wall_generator`, `door_generator`, `opening_generator`, `furniture_generator` | Polígonos Shapely, adyacencias, muros, puertas, ventanas, mobiliario. |
| `cad` | `dxf_generator`, `furniture_symbols`, `dxf_reader`, `dxf_editor` | Exportación, símbolos, lectura y edición DXF. |

## Pruebas
**Causa del fallo anterior:** los archivos `tests/test_*.py` eran scripts de diagnóstico (código a nivel de módulo, sin funciones `test_*`), por lo que pytest no recolectaba nada y además los ejecutaba al importarlos.

**Cambios:** los 11 scripts se **movieron sin modificar** a `scripts/diagnostico/` con prefijo `diag_` (se conservan). Se crearon pruebas pytest reales:
- `tests/conftest.py` – fixture de distribución simple.
- `tests/test_modelos_y_grafo.py` – normalización, relaciones, `construir_grafo` (incl. errores), áreas predeterminadas.
- `tests/test_geometria_y_cad.py` – geometrías, fuera de terreno, adyacencias, aislamiento, puertas, pipeline completo muros→aberturas→DXF→lectura.
- `tests/test_optimizador.py` – prueba de humo del optimizador (vivienda de 5 ambientes, límites del terreno, conectividad).

**Resultado:** `pytest` → **13 passed** (≈2.6 s). No se usaron skips ni xfail.

**Importaciones:** los 17 módulos de `src/` (excepto `app.py`, que ejecuta la UI Streamlit y no se importó) cargan sin error.

**Scripts de diagnóstico** (se ejecutan con `PYTHONPATH` en la raíz: `python scripts\diagnostico\diag_x.py`):
- `diag_defaults`, `diag_geometry`: funcionan.
- `diag_space_graph`: **falla** (`ImportError: Ambiente`); usa una API `GrafoEspacial` que ya no existe. Se conserva como referencia histórica y no se reescribió; su equivalente actual está en `test_modelos_y_grafo.py`.
- Los demás (`adjacency_validator`, `doors`, `door_geometry`, `dxf_generator`, `furniture`, `opening_generator`, `plano_completo`, `wall_generator`) no se re-ejecutaron porque algunos escriben en `output/`; su estado no está verificado.

## Problemas pendientes
1. **Git no instalado** → sin control de versiones todavía.
2. `normalizar_nombre` está duplicada **con comportamiento distinto**: `defaults.py` solo hace `strip().lower()` (conserva tildes) mientras `space_graph.py` y `layout_optimizer.py` quitan tildes. Riesgo de que "baño" y "bano" se traten distinto según el módulo.
3. Sin pruebas para `ai/` (requiere simular Ollama), `dxf_editor`, `furniture_generator`, `app.py`; el optimizador solo tiene una prueba de humo.
4. Archivos grandes y multipropósito: `layout_optimizer.py` (36 KB), `dxf_generator.py` (31 KB), `app.py` (515 líneas).
5. Distribución como `list[dict]` sin esquema tipado.
6. `app.py` modifica `sys.path`; `except Exception` genéricos; llamadas a Ollama sin timeout/reintentos visibles.
7. `dxf_editor` depende del formato exacto que emite `dxf_generator`.
8. `scripts/diagnostico/diag_space_graph.py` obsoleto.

## Etapas siguientes (propuesta)
1. Instalar Git, `git init` y primer commit (el `.gitignore` ya excluye `.venv`, cachés, `.env` y `output/`).
2. Ampliar pruebas: `dxf_editor`, `furniture_generator`, capa `ai` con LLM simulado.
3. Unificar `normalizar_nombre` (decidir criterio con tildes).
4. Tipar la distribución; separar lógica de `app.py`; dividir optimizador y generador DXF.
5. Robustecer la capa LLM.
6. Ampliaciones funcionales y, después, BIM.
