
from src.geometry.adjacency_validator import (
    validar_distribucion,
    imprimir_validacion
)


distribucion = [
    {
        "id": "sala_1",
        "nombre": "sala",
        "x": 0.0,
        "y": 16.6,
        "ancho": 5.4,
        "largo": 3.3
    },
    {
        "id": "comedor_1",
        "nombre": "comedor",
        "x": 0.5,
        "y": 13.9,
        "ancho": 4.4,
        "largo": 2.7
    },
    {
        "id": "cocina_1",
        "nombre": "cocina",
        "x": 0.5,
        "y": 11.2,
        "ancho": 4.4,
        "largo": 2.7
    },
    {
        "id": "dormitorio_1",
        "nombre": "dormitorio",
        "x": 5.4,
        "y": 2.7,
        "ancho": 3.9,
        "largo": 3.8
    },
    {
        "id": "dormitorio_2",
        "nombre": "dormitorio",
        "x": 5.4,
        "y": 13.5,
        "ancho": 3.8,
        "largo": 3.9
    },
    {
        "id": "bano_1",
        "nombre": "baño",
        "x": 5.6,
        "y": 0.0,
        "ancho": 2.2,
        "largo": 2.7
    },
    {
        "id": "bano_2",
        "nombre": "baño",
        "x": 7.8,
        "y": 0.0,
        "ancho": 2.2,
        "largo": 2.7
    },
    {
        "id": "lavanderia_1",
        "nombre": "lavandería",
        "x": 0.0,
        "y": 6.5,
        "ancho": 1.9,
        "largo": 2.6
    }
]


resultado = validar_distribucion(distribucion)

imprimir_validacion(resultado)
