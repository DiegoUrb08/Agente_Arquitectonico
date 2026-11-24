import pytest


@pytest.fixture
def distribucion_simple():
    """Dos ambientes contiguos de 5x4 y 3x4 m dentro de un terreno de 10x10."""
    return [
        {"id": "sala_1", "nombre": "Sala", "x": 0, "y": 0, "ancho": 5, "largo": 4},
        {"id": "cocina_1", "nombre": "Cocina", "x": 5, "y": 0, "ancho": 3, "largo": 4},
    ]
