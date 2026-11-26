
import json
import re

from src.planning.orientacion import detectar_norte
from src.planning.retiros import detectar_retiros
from src.models.requirements import RequerimientosArquitectonicos

from src.models.defaults import (
    calcular_areas_predeterminadas,
    estimar_area_total_vivienda,
    completar_dimensiones_terreno
)

from src.ai.errores import mensaje_amigable
from src.ai.providers import get_provider


# ============================================================
# 0. EXTRACCION DE TERRENO POR REGEX (FALLBACK)
# ============================================================

# Separadores entre las dos dimensiones: "x", "×", "por", "by".
_SEP = r"(?:[xX×]|por|by)"

# Número entero o decimal (coma o punto como separador).
_NUM = r"(\d+(?:[.,]\d+)?)"

# Unidades opcionales: m, metros, metro, mts, meter, meters.
_UNIDAD = r"(?:\s*(?:m(?:etro[s]?|ts?|eter[s]?)?)?)?"

# Patrón principal: "6 x 10 metros", "10x20", "10 by 20 meter lot".
_RE_DIM = re.compile(
    rf"{_NUM}\s*{_SEP}\s*{_NUM}{_UNIDAD}",
    re.IGNORECASE,
)

# Patrón área: "200 m2", "150 m²", "80 metros cuadrados"
# Solo se usa cuando no hay patrón NxM y el texto menciona "terreno".
_RE_AREA = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(?:m[²2]|metros?\s+cuadrados?)",
    re.IGNORECASE,
)

# Dimensión mínima razonable para un terreno (m).
_MIN_DIM_M = 3.0


def _extraer_terreno_por_regex(texto: str) -> dict:
    """
    Fallback determinista: busca dimensiones del terreno en el prompt
    cuando el modelo devolvió ancho/largo/area_terreno todos nulos.

    Devuelve un dict con las claves que pudo extraer (puede ser vacío).
    """
    texto_n = texto.replace(",", ".")

    # 1. Buscar patrón NxM (prioridad sobre área sola).
    for m in _RE_DIM.finditer(texto_n):
        a, b = float(m.group(1)), float(m.group(2))
        if a >= _MIN_DIM_M and b >= _MIN_DIM_M:
            return {"ancho_terreno_m": a, "largo_terreno_m": b}

    # 2. Área total del terreno (solo si aparece la palabra "terreno").
    texto_lower = texto_n.lower()
    if "terreno" in texto_lower or "lote" in texto_lower or "lot" in texto_lower:
        m = _RE_AREA.search(texto_n)
        if m:
            return {"area_terreno_m2": float(m.group(1))}

    return {}


def _reconciliar_datos_faltantes(requerimientos) -> None:
    """
    Vacía `datos_faltantes`, dejando constancia en las observaciones.

    Al llegar aquí el sistema ya completó todo lo necesario con valores por
    defecto (pisos, área total, áreas por ambiente), y lo imprescindible (las
    dimensiones del terreno y los ambientes) lo rechaza antes con un error
    claro. Lo que el modelo siga marcando como faltante, p. ej. gpt-oss, no
    debe impedir generar el plano.
    """

    if requerimientos.datos_faltantes:
        requerimientos.observaciones.append(
            "Se usaron valores por defecto para: "
            + ", ".join(requerimientos.datos_faltantes)
        )
        requerimientos.datos_faltantes = []


# ============================================================
# 1. INTERPRETACION DE INSTRUCCIONES
# ============================================================

def interpretar_instruccion(instruccion: str) -> RequerimientosArquitectonicos:

    """
    Interpreta una descripcion arquitectonica en lenguaje natural
    y la transforma en un objeto estructurado de requerimientos.

    Posteriormente completa automaticamente los datos que
    puedan estimarse mediante las funciones predeterminadas.
    """

    if not instruccion or not instruccion.strip():
        raise ValueError(
            "La instruccion arquitectonica no puede estar vacia."
        )

    # --------------------------------------------------------
    # 1.1 PROMPT PARA EL MODELO
    # --------------------------------------------------------

    prompt = f"""
Eres un asistente especializado en interpretacion de
requerimientos arquitectonicos.

Tu tarea es analizar la descripcion de un usuario y
transformarla en un objeto JSON estructurado.

DESCRIPCION DEL USUARIO:

{instruccion}

INSTRUCCIONES:

1. Identifica el tipo de proyecto.
2. Identifica el numero de pisos si se menciona.
3. Identifica las dimensiones del terreno si se proporcionan.
4. Identifica el area total del terreno si se proporciona.
5. Identifica el area total deseada de la vivienda si se proporciona.
6. Identifica todos los ambientes solicitados.
7. Identifica la cantidad de cada ambiente.
8. Identifica las areas minimas u objetivo si el usuario las especifica.
9. Identifica las relaciones de adyacencia solicitadas.
10. Registra observaciones arquitectonicas relevantes.
11. Identifica datos importantes que realmente falten.

REGLAS IMPORTANTES:

- No confundas el area del terreno con el area construida.
- Si el usuario proporciona solamente el area del terreno,
  registra ese valor en area_terreno_m2.
- Si proporciona ancho y largo, registra ambas dimensiones.
- No inventes dimensiones del terreno.
- No inventes areas de ambientes que el usuario no haya especificado.
- No inventes relaciones de adyacencia.
- Si un dato no esta disponible, utiliza null.
- Si el usuario no especifica el numero de pisos, utiliza null.
- Si el usuario no proporciona cantidades, utiliza una cantidad razonable
  segun su descripcion y el tipo de proyecto.
- Extrae todos los ambientes mencionados, incluso si aparecen
  dentro de una descripcion general.
- No confundas el numero de habitantes con el numero de dormitorios.

RELACIONES DE ADYACENCIA:

Cuando el usuario indique que dos ambientes deben estar conectados,
representa la relacion de esta manera:

{{
    "ambiente_a": "sala",
    "ambiente_b": "comedor",
    "modo": "todos"
}}

Los modos permitidos son:

- todos
- al_menos_uno
- correspondiente

Utiliza estas relaciones solamente cuando exista una indicacion
suficiente en la descripcion del usuario.

FORMATO JSON OBLIGATORIO:

{{
    "tipo_proyecto": "vivienda",
    "numero_pisos": null,
    "ancho_terreno_m": null,
    "largo_terreno_m": null,
    "area_terreno_m2": null,
    "area_total_vivienda_m2": null,
    "ambientes": [
        {{
            "nombre": "sala",
            "cantidad": 1,
            "area_minima_m2": null,
            "area_objetivo_m2": null
        }}
    ],
    "relaciones_adyacencia": [],
    "observaciones": [],
    "datos_faltantes": []
}}

Devuelve exclusivamente el JSON.
No agregues explicaciones antes ni despues.
"""

    # --------------------------------------------------------
    # 1.2 CONSULTA AL PROVEEDOR LLM
    # --------------------------------------------------------

    provider = get_provider()
    respuesta = provider.chat(
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.1,
    )

    contenido = respuesta["message"]["content"]

    # --------------------------------------------------------
    # 1.3 CONVERSION DEL JSON
    # --------------------------------------------------------

    try:

        datos = json.loads(contenido)

    except json.JSONDecodeError as error:

        raise ValueError(
            f"El modelo devolvio un JSON invalido: {error}"
        ) from error

    # --------------------------------------------------------
    # 1.4 VALIDACION CON PYDANTIC
    # --------------------------------------------------------

    # El norte y los retiros no se piden al modelo: se leen del texto.
    if isinstance(datos, dict):
        datos.pop("norte", None)
        datos.pop("retiros", None)

    try:

        requerimientos = RequerimientosArquitectonicos(
            **datos
        )

    except (TypeError, ValueError) as error:

        raise ValueError(
            mensaje_amigable(error, "los requerimientos")
        ) from error

    # --------------------------------------------------------
    # 1.5 NOTA: REINTENTOS MANEJADOS INTERNAMENTE POR PROVIDER
    # --------------------------------------------------------
    # Los reintentos ahora se manejan dentro del provider.
    # El registro de reintentos se puede agregar aquí si es necesario.

    # --------------------------------------------------------
    # 1.6 FALLBACK: EXTRAER TERRENO POR REGEX SI EL MODELO LO OMITIÓ
    # --------------------------------------------------------

    if (requerimientos.ancho_terreno_m is None
            and requerimientos.largo_terreno_m is None
            and requerimientos.area_terreno_m2 is None):
        for clave, valor in _extraer_terreno_por_regex(instruccion).items():
            setattr(requerimientos, clave, valor)

    requerimientos.norte = detectar_norte(instruccion)
    requerimientos.retiros = detectar_retiros(instruccion)

    # --------------------------------------------------------
    # 2. COMPLETAR DIMENSIONES DEL TERRENO
    # --------------------------------------------------------

    requerimientos = completar_dimensiones_terreno(
        requerimientos
    )

    # --------------------------------------------------------
    # 3. ESTIMAR AREA TOTAL DE LA VIVIENDA
    # --------------------------------------------------------

    if requerimientos.area_total_vivienda_m2 is None:

        requerimientos = estimar_area_total_vivienda(
            requerimientos
        )

    # --------------------------------------------------------
    # 4. DISTRIBUIR AREAS PREDETERMINADAS
    # --------------------------------------------------------

    requerimientos = calcular_areas_predeterminadas(
        requerimientos
    )

    # --------------------------------------------------------
    # 5. RECONCILIAR LOS DATOS FALTANTES
    # --------------------------------------------------------

    _reconciliar_datos_faltantes(requerimientos)

    # --------------------------------------------------------
    # 6. DEVOLVER REQUERIMIENTOS COMPLETOS
    # --------------------------------------------------------

    return requerimientos


# ============================================================
# 6. PRUEBA INDEPENDIENTE
# ============================================================

if __name__ == "__main__":

    instruccion_prueba = """
    Quiero construir una casa familiar de un piso
    en un terreno de 200 m2.

    Viviremos cuatro personas, asi que necesito
    tres dormitorios, dos baños, una sala comoda,
    comedor, cocina y lavanderia.

    Me gustaria que los dormitorios sean tranquilos
    y esten separados de las areas comunes, y que
    la casa tenga una distribucion espaciosa y bien organizada.
    """

    print("\nINTERPRETANDO INSTRUCCION...\n")

    try:

        resultado = interpretar_instruccion(
            instruccion_prueba
        )

        print("REQUERIMIENTOS ARQUITECTONICOS")
        print("=" * 55)

        print(
            json.dumps(
                resultado.model_dump(),
                indent=4,
                ensure_ascii=False
            )
        )

    except Exception as error:

        print("\nERROR:")
        print(error)
