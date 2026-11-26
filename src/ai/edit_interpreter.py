
import json

from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator

from src.ai.errores import mensaje_amigable
from src.ai.providers import get_provider


# ==========================================
# 1. MODELO DE UNA OPERACION DE EDICION
# ==========================================

class EditOperation(BaseModel):

    model_config = ConfigDict(extra="forbid")

    tipo: Literal[
        "modificar_area",
        "mover_ambiente",
        "agregar_ambiente",
        "quitar_ambiente",
        "renombrar_ambiente"
    ] = Field(
        description="Tipo de modificacion solicitada"
    )

    ambiente: str = Field(
        min_length=1,
        description="Nombre del ambiente que se modificara"
    )

    area_objetivo: float | None = Field(
        default=None,
        gt=0,
        description="Area objetivo en metros cuadrados"
    )

    referencia: str | None = Field(
        default=None,
        description="Ambiente que servira como referencia"
    )

    relacion: Literal[
        "junto_a",
        "cerca_de",
        "lejos_de",
        "izquierda_de",
        "derecha_de",
        "arriba_de",
        "abajo_de"
    ] | None = Field(
        default=None,
        description="Relacion espacial deseada"
    )

    nombre_nuevo: str | None = Field(
        default=None,
        description="Nuevo tipo del ambiente, solo para renombrar_ambiente"
    )

    planta: Literal["baja", "alta"] | None = Field(
        default=None,
        description="Planta, solo si el usuario la menciona"
    )

    @model_validator(mode="after")
    def validar_operacion(self):

        if self.tipo == "modificar_area":
            if self.area_objetivo is None:
                raise ValueError(
                    "La modificacion de area necesita un area objetivo."
                )

        if self.tipo == "mover_ambiente":
            if not self.referencia or not self.relacion:
                raise ValueError(
                    "Para mover un ambiente se necesita una referencia "
                    "y una relacion espacial."
                )

        if self.tipo == "renombrar_ambiente" and not self.nombre_nuevo:
            raise ValueError("Para renombrar se necesita el nombre nuevo.")

        return self


# ==========================================
# 2. MODELO DE LA SOLICITUD COMPLETA
# ==========================================

class EditRequest(BaseModel):

    model_config = ConfigDict(extra="forbid")

    operaciones: list[EditOperation] = Field(
        min_length=1,
        max_length=10,
        description="Lista de modificaciones solicitadas"
    )

    observaciones: list[str] = Field(
        default_factory=list,
        description="Advertencias o aclaraciones necesarias"
    )


# ==========================================
# 3. INTERPRETAR EL PROMPT
# ==========================================

def interpretar_edicion(instruccion: str) -> EditRequest:

    if not instruccion or not instruccion.strip():
        raise ValueError("La instruccion no puede estar vacia.")

    mensaje_sistema = """
    Eres un asistente especializado en interpretar modificaciones
    de planos arquitectonicos 2D.

    Tu tarea es convertir las instrucciones del usuario en operaciones
    estructuradas que posteriormente ejecutara un programa.

    REGLAS:

    1. No inventes ambientes que el usuario no haya mencionado.
    2. No inventes dimensiones ni areas.
    3. Utiliza exclusivamente los tipos de operacion permitidos.
    4. Para modificar un area, utiliza modificar_area.
    5. Para cambiar la ubicacion de un ambiente, utiliza mover_ambiente.
       "ambiente" es el que se mueve y "referencia" el que sirve de guia.
       "al lado de", "junto a", "pegado a" o "cerca de" son junto_a; usa
       una direccion solo si el usuario la dice.
       Escribe los nombres como el usuario; no agregues numeros que no dijo.
    6. Si faltan datos indispensables, no inventes valores.
    7. Para anadir un ambiente usa agregar_ambiente: "ambiente" es el tipo
       en singular ("estudio", "bano", "dormitorio"); area_objetivo,
       referencia y relacion solo si el usuario las dice. Si pide varios,
       una operacion por cada uno.
       Para eliminar uno usa quitar_ambiente.
       "planta" es "baja" para abajo o primer piso y "alta" para arriba o
       segundo piso; null si no lo dice.
       Para cambiar el uso o el nombre de un ambiente sin moverlo
       ("llama cocina al ambiente 1", "el ambiente 2 es un baño") usa
       renombrar_ambiente: "ambiente" es el actual y "nombre_nuevo" el
       tipo nuevo en singular.
    8. Si una instruccion no se puede representar con las operaciones
       disponibles, explica la limitacion en observaciones.
    9. No generes codigo Python ni comandos DXF.
    10. Devuelve una estructura compatible con el esquema proporcionado.
    """

    esquema = EditRequest.model_json_schema()
    mensaje_sistema += (
        "\n    Responde exclusivamente con un objeto JSON que cumpla este "
        "esquema, sin texto adicional ni bloques de codigo:\n    "
        + json.dumps(esquema, ensure_ascii=False)
    )

    provider = get_provider()

    # Ollama admite salida estructurada nativa; el resto depende del prompt.
    extra = {"format": esquema} if provider.nombre == "ollama" else {}

    respuesta = provider.chat(
        messages=[
            {
                "role": "system",
                "content": mensaje_sistema
            },
            {
                "role": "user",
                "content": instruccion
            }
        ],
        temperature=0,
        **extra,
    )

    contenido = respuesta["message"]["content"]

    try:
        resultado = EditRequest.model_validate_json(contenido)

    except ValueError as error:  # incluye pydantic.ValidationError
        raise ValueError(
            mensaje_amigable(error, "la edición solicitada")
        ) from error

    return resultado
