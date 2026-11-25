"""Plano fijo (no optimizado) para tests que editan o muestran un plano.

El optimizador no es determinista y el editor rechaza cambios según la
distribución, así que estos tests necesitan siempre el mismo plano.
Deja espacio libre sobre y a la derecha de las habitaciones.
"""

from src.services.pipeline import construir_plano

DISTRIBUCION_FIJA = [
    {"id": "sala_1", "nombre": "sala", "x": 0.0, "y": 0.0, "ancho": 5.0, "largo": 4.0},
    {"id": "cocina_1", "nombre": "cocina", "x": 5.0, "y": 0.0, "ancho": 4.0, "largo": 4.0},
    {"id": "dormitorio_1", "nombre": "dormitorio", "x": 0.0, "y": 4.0, "ancho": 4.0, "largo": 3.0},
    {"id": "bano_1", "nombre": "baño", "x": 4.0, "y": 4.0, "ancho": 2.0, "largo": 3.0},
    {"id": "dormitorio_2", "nombre": "dormitorio", "x": 6.0, "y": 4.0, "ancho": 4.0, "largo": 3.0},
]


def generar_plano_fijo(requerimientos, ruta, progreso=None):
    """Sustituye a `generar_plano`: mismo contrato, distribución fija."""
    return construir_plano(DISTRIBUCION_FIJA, 10, 20, ruta, progreso)
