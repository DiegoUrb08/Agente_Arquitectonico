
import json

from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator

from src.ai.errores import mensaje_amigable
from src.ai.ollama_client import MODEL_NAME, chat_con_reintentos


# ==========================================
# 1. MODELO DE UNA OPERACION DE EDICION
# ==========================================

class EditOperation(BaseModel):

    model_config = ConfigDict(extra="forbid")

    tipo: Literal[
        "modificar_area",
        "mover_ambiente"
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
    6. Si faltan datos indispensables, no inventes valores.
    7. Si una instruccion no se puede representar con las operaciones
       disponibles, explica la limitacion en observaciones.
    8. No generes codigo Python ni comandos DXF.
    9. Devuelve una estructura compatible con el esquema proporcionado.
    """

    respuesta = chat_con_reintentos(
        model=MODEL_NAME,
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
        format=EditRequest.model_json_schema(),
        options={
            "temperature": 0
        }
    )

    contenido = respuesta["message"]["content"]

    try:
        resultado = EditRequest.model_validate_json(contenido)

    except ValueError as error:  # incluye pydantic.ValidationError
        raise ValueError(
            mensaje_amigable(error, "la edición solicitada")
        ) from error

    return resultado
