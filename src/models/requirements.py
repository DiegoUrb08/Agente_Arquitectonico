
from typing import Literal

from pydantic import BaseModel, Field


class Ambiente(BaseModel):
    nombre: str

    cantidad: int = 1

    # Superficie mínima solicitada por el usuario.
    area_minima_m2: float | None = None

    # Superficie objetivo calculada por el sistema.
    area_objetivo_m2: float | None = None


class Retiros(BaseModel):
    """Franjas libres entre la casa y los límites del terreno (m)."""

    frontal: float = Field(default=0, ge=0, le=100)
    posterior: float = Field(default=0, ge=0, le=100)
    izquierdo: float = Field(default=0, ge=0, le=100)
    derecho: float = Field(default=0, ge=0, le=100)


class RequerimientosArquitectonicos(BaseModel):

    tipo_proyecto: str = "vivienda"

    numero_pisos: int | None = None

    # Dimensiones del terreno.
    ancho_terreno_m: float | None = None
    largo_terreno_m: float | None = None
    area_terreno_m2: float | None = None
    # True cuando el terreno no lo dio el usuario y se calculó desde el área
    # de la vivienda: entonces la casa se centra en el lote.
    terreno_estimado: bool = False

    # Casa mínima (un piso, hasta 30 m²): sin reserva de circulación ni pasillo.
    programa_basico: bool = False
    # Ambientes que el sistema añadió porque toda casa básica los lleva.
    ambientes_agregados: list[str] = Field(default_factory=list)

    # Superficie total deseada para la vivienda.
    area_total_vivienda_m2: float | None = None

    # Lado del terreno donde está el norte (el frente es la calle).
    norte: Literal["frente", "fondo", "derecha", "izquierda"] | None = None

    retiros: Retiros | None = None

    ambientes: list[Ambiente] = Field(default_factory=list)

    relaciones_adyacencia: list[list[str] | dict] = Field(default_factory=list)

    observaciones: list[str] = Field(
        default_factory=list
    )

    datos_faltantes: list[str] = Field(
        default_factory=list
    )
