"""
Guardar y retomar un proyecto como archivo JSON (sin Streamlit).

Solo se guarda lo que no se puede recalcular: requerimientos, conversación y,
por cada versión, la distribución de sus ambientes. Muros, puertas, ventanas,
muebles, DXF y CSV se reconstruyen al abrirlo.
"""

import json
import tempfile
from pathlib import Path
from typing import Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.models.requirements import RequerimientosArquitectonicos
from src.services.pipeline import construir_multipisos, construir_plano
from src.ui import proyecto as pry

FORMATO = "agente-arquitectonico/proyecto"
VERSION = 1
EXTENSION = ".proyecto.json"

TAMANO_MAXIMO = 5 * 1024 * 1024
VERSIONES_MAXIMAS = 500
AMBIENTES_MAXIMOS = 200
TERRENO_MAXIMO_M = 1000

NO_VALIDO = "El archivo no es un proyecto válido del agente."


class _Modelo(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)


class _Ambiente(_Modelo):
    # El editor de dos plantas depende de que el id termine en un número.
    id: str = Field(max_length=80, pattern=r"^.+_\d{1,6}$")
    nombre: str = Field(min_length=1, max_length=80)
    x: float = Field(ge=0, le=TERRENO_MAXIMO_M)
    y: float = Field(ge=0, le=TERRENO_MAXIMO_M)
    ancho: float = Field(gt=0, le=TERRENO_MAXIMO_M)
    largo: float = Field(gt=0, le=TERRENO_MAXIMO_M)
    area_m2: float | None = None
    area_objetivo_m2: float | None = None


class _Piso(_Modelo):
    distribucion: list[_Ambiente] = Field(
        min_length=1, max_length=AMBIENTES_MAXIMOS
    )
    notas: list[str] = Field(default_factory=list, max_length=500)
    avisos: list[str] = Field(default_factory=list, max_length=500)


class _Terreno(_Modelo):
    ancho: float = Field(gt=0, le=TERRENO_MAXIMO_M)
    largo: float = Field(gt=0, le=TERRENO_MAXIMO_M)


class _Version(_Modelo):
    etiqueta: str = Field(max_length=20_000)
    cambiados: list[str] = Field(default_factory=list, max_length=1000)
    terreno: _Terreno
    multipisos: bool = False
    pisos: list[_Piso] = Field(min_length=1, max_length=2)


class _Mensaje(_Modelo):
    rol: Literal["usuario", "agente", "error"]
    texto: str = Field(max_length=100_000)


class Guardado(_Modelo):
    """Contenido de un archivo de proyecto ya validado."""

    formato: str
    version: int
    id: str | None = None
    nombre: str = Field(max_length=200)
    creado: str = Field(default="", max_length=40)
    modificado: str = Field(default="", max_length=40)
    requerimientos: RequerimientosArquitectonicos | None = None
    mensajes: list[_Mensaje] = Field(max_length=5000)
    versiones: list[_Version] = Field(
        min_length=1, max_length=VERSIONES_MAXIMAS
    )


def _version_a_datos(version: dict) -> dict:
    resultado = version["resultado"]
    pisos = pry.pisos_de(resultado)
    ancho, largo = pry.dimensiones_terreno(pisos[0])
    return {
        "etiqueta": version["etiqueta"],
        "cambiados": sorted(version["cambiados"]),
        "terreno": {"ancho": round(ancho, 3), "largo": round(largo, 3)},
        "multipisos": pisos[0] is not resultado,
        "pisos": [
            {
                "distribucion": p.distribucion,
                "notas": p.notas,
                "avisos": p.avisos,
            }
            for p in pisos
        ],
    }


def exportar(proyecto: dict) -> bytes:
    """El proyecto como archivo. Las trazas de error no se incluyen."""

    datos = Guardado.model_validate({
        "formato": FORMATO,
        "version": VERSION,
        "id": proyecto.get("id"),
        "nombre": proyecto.get("nombre") or "Proyecto",
        "creado": proyecto.get("creado", ""),
        "modificado": proyecto.get("modificado", ""),
        "requerimientos": proyecto["requerimientos"],
        "mensajes": [
            {"rol": m["rol"], "texto": m["texto"]}
            for m in proyecto["mensajes"]
        ],
        "versiones": [
            _version_a_datos(v)
            for v in proyecto["versiones"][-VERSIONES_MAXIMAS:]
        ],
    })
    return json.dumps(
        datos.model_dump(exclude_none=True), ensure_ascii=False, indent=1
    ).encode("utf-8")


def leer(contenido: bytes) -> Guardado:
    """Valida el archivo sin reconstruir los planos."""

    if len(contenido) > TAMANO_MAXIMO:
        raise ValueError("El archivo es demasiado grande para ser un proyecto.")
    try:
        datos = json.loads(contenido.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError(NO_VALIDO) from error

    if not isinstance(datos, dict) or datos.get("formato") != FORMATO:
        raise ValueError(NO_VALIDO)

    version = datos.get("version")
    if isinstance(version, int) and version > VERSION:
        raise ValueError(
            "El proyecto lo creó una versión más nueva del agente: actualízalo."
        )
    try:
        return Guardado.model_validate(datos)
    except ValidationError as error:
        campo = ".".join(str(p) for p in error.errors()[0]["loc"])
        raise ValueError(f"{NO_VALIDO} Revisa el campo «{campo}».") from error


def _reconstruir(version: _Version, ruta: Path) -> dict:
    distribuciones = [
        [a.model_dump(exclude_none=True) for a in p.distribucion]
        for p in version.pisos
    ]
    terreno = version.terreno.ancho, version.terreno.largo

    if version.multipisos:
        resultado = construir_multipisos(distribuciones, *terreno, ruta)
    elif len(distribuciones) == 1:
        resultado = construir_plano(distribuciones[0], *terreno, ruta)
    else:
        raise ValueError("una versión de una planta tiene dos distribuciones")

    for plano, piso in zip(pry.pisos_de(resultado), version.pisos):
        plano.notas = list(piso.notas)
        plano.avisos = list(piso.avisos)

    return pry._version(
        resultado, ruta.read_bytes(), version.etiqueta, version.cambiados
    )


def importar(
    contenido: bytes,
    progreso: Callable[[str], None] | None = None,
) -> dict:
    """
    Reconstruye el proyecto de un archivo. No conserva el `id`: de eso se
    encarga el almacén, para que importar no pise un proyecto guardado.
    """

    datos = leer(contenido)
    versiones = []

    with tempfile.TemporaryDirectory() as carpeta:
        for numero, version in enumerate(datos.versiones, start=1):
            if progreso:
                progreso(
                    f"Reconstruyendo versión {numero} de "
                    f"{len(datos.versiones)}..."
                )
            try:
                versiones.append(
                    _reconstruir(version, Path(carpeta) / "plano.dxf")
                )
            except ValueError as error:
                raise ValueError(
                    f"El proyecto está dañado (versión {numero}): {error}"
                ) from error

    return {
        "nombre": datos.nombre,
        "requerimientos": datos.requerimientos,
        "versiones": versiones,
        "mensajes": [pry._mensaje(m.rol, m.texto) for m in datos.mensajes],
    }
