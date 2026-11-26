"""
Autoguardado de proyectos en una carpeta local (sin Streamlit).

La carpeta es `proyectos/` en la raíz (o `AGENTE_PROYECTOS_DIR`). Con
`AUTOGUARDADO=1` lo activa; por defecto está desactivado, porque quien pueda
abrir la app vería la lista de proyectos.
"""

import os
import re
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path

from src.ui import guardado

CARPETA_POR_DEFECTO = Path(__file__).resolve().parents[2] / "proyectos"
ACTIVADO = {"1", "true", "si", "sí", "on"}
INTENTOS = 5
ESPERA_S = 0.1


def activo() -> bool:
    return os.getenv("AUTOGUARDADO", "0").strip().lower() in ACTIVADO


def carpeta() -> Path:
    return Path(os.getenv("AGENTE_PROYECTOS_DIR") or CARPETA_POR_DEFECTO)


def _ruta(identificador: str) -> Path:
    # Solo ids propios: impide salir de la carpeta.
    if not re.fullmatch(r"[0-9a-f]{32}", identificador):
        raise ValueError("Identificador de proyecto no válido.")
    return carpeta() / f"{identificador}{guardado.EXTENSION}"


def _reemplazar(origen: Path, destino: Path) -> None:
    """`os.replace` con reintentos: OneDrive o un antivirus pueden bloquear."""
    for intento in range(INTENTOS):
        try:
            os.replace(origen, destino)
            return
        except PermissionError:
            if intento == INTENTOS - 1:
                raise
            time.sleep(ESPERA_S)


def guardar(proyecto: dict) -> Path | None:
    """Escribe el proyecto; le asigna `id` y fechas. None si está desactivado."""

    if not activo():
        return None

    ahora = datetime.now().isoformat(timespec="microseconds")
    proyecto.setdefault("id", uuid.uuid4().hex)
    proyecto.setdefault("creado", ahora)
    proyecto["modificado"] = ahora

    destino = _ruta(proyecto["id"])
    contenido = guardado.exportar(proyecto)
    destino.parent.mkdir(parents=True, exist_ok=True)

    # Se escribe aparte y se sustituye: un corte no deja el archivo a medias.
    descriptor, temporal = tempfile.mkstemp(dir=destino.parent, suffix=".tmp")
    temporal = Path(temporal)
    try:
        with os.fdopen(descriptor, "wb") as archivo:
            archivo.write(contenido)
        _reemplazar(temporal, destino)
    finally:
        temporal.unlink(missing_ok=True)

    return destino


def listar() -> tuple[list[dict], int]:
    """(proyectos, del más reciente al más antiguo; archivos dañados)."""

    if not activo():
        return [], 0

    proyectos, danados = [], 0

    for ruta in carpeta().glob(f"*{guardado.EXTENSION}"):
        identificador = ruta.name.removesuffix(guardado.EXTENSION)
        try:
            _ruta(identificador)
            datos = guardado.leer(ruta.read_bytes())
        except (OSError, ValueError):
            danados += 1
            continue
        proyectos.append({
            "id": identificador,
            "nombre": datos.nombre,
            "modificado": datos.modificado,
            "versiones": len(datos.versiones),
        })

    proyectos.sort(key=lambda p: p["modificado"], reverse=True)
    return proyectos, danados


def abrir(identificador: str, progreso=None) -> dict:
    ruta = _ruta(identificador)
    try:
        contenido = ruta.read_bytes()
    except FileNotFoundError as error:
        raise ValueError("Ese proyecto ya no existe.") from error

    datos = guardado.leer(contenido)
    proyecto = guardado.importar(contenido, progreso)
    proyecto.update(
        id=identificador, creado=datos.creado, modificado=datos.modificado
    )
    return proyecto


def borrar(identificador: str) -> None:
    _ruta(identificador).unlink(missing_ok=True)
