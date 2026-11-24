"""Proveedor LLM: Mock (para tests, sin dependencias externas)."""

from .base import LLMProvider


class MockProvider(LLMProvider):
    """Proveedor simulado que devuelve respuestas hardcoded."""

    def __init__(self):
        pass

    @property
    def nombre(self) -> str:
        return "mock"

    @property
    def modelo(self) -> str:
        return "mock-model"

    def chat(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs,
    ) -> dict:
        """Devuelve una respuesta simulada."""
        # Simula un interprete de requerimientos arquitectónicos básico
        last_message = messages[-1]["content"].lower() if messages else ""

        if "terreno" in last_message:
            response = """{
    "ancho_terreno_m": 10,
    "largo_terreno_m": 20,
    "area_total_vivienda_m2": 100,
    "numero_pisos": 1,
    "ambientes": [
        {"nombre": "sala", "cantidad": 1},
        {"nombre": "cocina", "cantidad": 1},
        {"nombre": "dormitorio", "cantidad": 2},
        {"nombre": "baño", "cantidad": 1}
    ]
}"""
        else:
            response = "Respuesta simulada del mock provider"

        return {
            "message": {
                "content": response,
                "role": "assistant",
            }
        }
