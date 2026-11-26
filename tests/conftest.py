import pytest


@pytest.fixture(autouse=True)
def compactacion_breve(monkeypatch):
    """La compactación agota su tiempo; en los tests basta con un segundo."""
    monkeypatch.setattr(
        "src.planning.layout_optimizer.TIEMPO_COMPACTACION_SEGUNDOS", 1
    )
    monkeypatch.setattr(
        "src.planning.reacomodo.TIEMPO_REACOMODO_SEGUNDOS", 3
    )


@pytest.fixture(autouse=True)
def carpeta_de_proyectos(monkeypatch, tmp_path):
    """Los tests nunca escriben en la carpeta real de proyectos."""
    carpeta = tmp_path / "proyectos"
    monkeypatch.setenv("AGENTE_PROYECTOS_DIR", str(carpeta))
    monkeypatch.setenv("AUTOGUARDADO", "1")
    return carpeta


@pytest.fixture
def distribucion_simple():
    """Dos ambientes contiguos de 5x4 y 3x4 m dentro de un terreno de 10x10."""
    return [
        {"id": "sala_1", "nombre": "Sala", "x": 0, "y": 0, "ancho": 5, "largo": 4},
        {"id": "cocina_1", "nombre": "Cocina", "x": 5, "y": 0, "ancho": 3, "largo": 4},
    ]
