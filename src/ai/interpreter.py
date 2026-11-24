
import json

from src.models.requirements import RequerimientosArquitectonicos

from src.models.defaults import (
    calcular_areas_predeterminadas,
    estimar_area_total_vivienda,
    completar_dimensiones_terreno
)

from src.ai.ollama_client import MODEL_NAME, chat_con_reintentos


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
    # 1.2 CONSULTA A OLLAMA
    # --------------------------------------------------------

    respuesta = chat_con_reintentos(
        model=MODEL_NAME,
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],
        format="json",
        options={
            "temperature": 0.1
        }
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

    try:

        requerimientos = RequerimientosArquitectonicos(
            **datos
        )

    except (TypeError, ValueError) as error:

        raise ValueError(
            f"No se pudieron validar los requerimientos: {error}"
        ) from error

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
    # 5. DEVOLVER REQUERIMIENTOS COMPLETOS
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
