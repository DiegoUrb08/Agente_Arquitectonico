
from pathlib import Path
from collections import Counter
import tempfile
import os

import ezdxf
from ezdxf import bbox


def analizar_dxf(archivo_bytes):

    """
    Lee un archivo DXF y devuelve información
    sobre sus entidades, capas y dimensiones.
    """

    archivo_temporal = None

    try:
        # Crear un archivo temporal para leer el DXF
        with tempfile.NamedTemporaryFile(
            suffix=".dxf",
            delete=False
        ) as temporal:

            temporal.write(archivo_bytes)
            archivo_temporal = temporal.name

        # Abrir el documento DXF
        documento = ezdxf.readfile(archivo_temporal)

        # Obtener el espacio modelo
        espacio_modelo = documento.modelspace()

        # Contabilizar entidades y capas
        tipos = Counter()
        capas = Counter()

        for entidad in espacio_modelo:

            tipo = entidad.dxftype()
            capa = entidad.dxf.layer

            tipos[tipo] += 1
            capas[capa] += 1

        # Calcular límites geométricos
        limites = bbox.extents(espacio_modelo)

        if limites.has_data:
            dimensiones = {
                "xmin": round(limites.extmin.x, 3),
                "ymin": round(limites.extmin.y, 3),
                "xmax": round(limites.extmax.x, 3),
                "ymax": round(limites.extmax.y, 3),
                "ancho": round(
                    limites.extmax.x - limites.extmin.x, 3
                ),
                "alto": round(
                    limites.extmax.y - limites.extmin.y, 3
                )
            }
        else:
            dimensiones = None

        return {
            "version": documento.dxfversion,
            "total_entidades": sum(tipos.values()),
            "tipos_entidades": dict(tipos),
            "capas": dict(capas),
            "dimensiones": dimensiones
        }

    finally:

        # Eliminar el archivo temporal
        if archivo_temporal and os.path.exists(archivo_temporal):
            os.remove(archivo_temporal)
