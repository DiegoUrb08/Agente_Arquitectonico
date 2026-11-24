"""Diagnóstico del grafo espacial (API actual: construir_grafo)."""

import json

from src.models.requirements import Ambiente, RequerimientosArquitectonicos
from src.planning.space_graph import construir_grafo


requerimientos = RequerimientosArquitectonicos(
    ambientes=[
        Ambiente(nombre="Sala"),
        Ambiente(nombre="Baño", cantidad=2),
    ],
    relaciones_adyacencia=[
        {"ambiente_a": "baño", "ambiente_b": "baño", "modo": "todos"},
        {"ambiente_a": "sala", "ambiente_b": "baño", "modo": "al_menos_uno"},
    ],
)

grafo = construir_grafo(requerimientos)

print("GRAFO ESPACIAL CREADO CORRECTAMENTE")
print(json.dumps(grafo, indent=2, ensure_ascii=False))
