
from src.geometry.door_generator import (
    generar_puertas_automaticas,
    imprimir_puertas
)

# Distribución de prueba
distribucion = [
    {
        "id": "sala_1",
        "nombre": "sala",
        "x": 6.7,
        "y": 5.9,
        "ancho": 3.3,
        "largo": 5.4
    },
    {
        "id": "comedor_1",
        "nombre": "comedor",
        "x": 4.0,
        "y": 6.4,
        "ancho": 2.7,
        "largo": 4.4
    },
    {
        "id": "cocina_1",
        "nombre": "cocina",
        "x": 1.3,
        "y": 6.4,
        "ancho": 2.7,
        "largo": 4.4
    },
    {
        "id": "dormitorio_1",
        "nombre": "dormitorio",
        "x": 2.9,
        "y": 13.5,
        "ancho": 3.9,
        "largo": 3.8
    },
    {
        "id": "dormitorio_2",
        "nombre": "dormitorio",
        "x": 4.4,
        "y": 2.1,
        "ancho": 3.9,
        "largo": 3.8
    },
    {
        "id": "bano_1",
        "nombre": "baño",
        "x": 3.9,
        "y": 10.8,
        "ancho": 2.2,
        "largo": 2.7
    },
    {
        "id": "bano_2",
        "nombre": "baño",
        "x": 1.7,
        "y": 10.8,
        "ancho": 2.2,
        "largo": 2.7
    },
    {
        "id": "lavanderia_1",
        "nombre": "lavandería",
        "x": 1.8,
        "y": 4.5,
        "ancho": 2.6,
        "largo": 1.9
    }
]

resultado = generar_puertas_automaticas(
    distribucion
)

imprimir_puertas(resultado)
