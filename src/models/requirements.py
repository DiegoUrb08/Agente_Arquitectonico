
from pydantic import BaseModel, Field


class Ambiente(BaseModel):
    nombre: str

    cantidad: int = 1

    # Superficie mínima solicitada por el usuario.
    area_minima_m2: float | None = None

    # Superficie objetivo calculada por el sistema.
    area_objetivo_m2: float | None = None


class RequerimientosArquitectonicos(BaseModel):

    tipo_proyecto: str = "vivienda"

    numero_pisos: int | None = None

    # Dimensiones del terreno.
    ancho_terreno_m: float | None = None
    largo_terreno_m: float | None = None
    area_terreno_m2: float | None = None

    # Superficie total deseada para la vivienda.
    area_total_vivienda_m2: float | None = None

    ambientes: list[Ambiente] = Field(default_factory=list)

    relaciones_adyacencia: list[list[str] | dict] = Field(default_factory=list)

    observaciones: list[str] = Field(
        default_factory=list
    )

    datos_faltantes: list[str] = Field(
        default_factory=list
    )
