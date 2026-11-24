"""
Tipo y validación de la distribución espacial.

La distribución es la lista de ambientes que produce el optimizador
y consumen los módulos de geometría y CAD. Se mantiene como lista de
diccionarios (por compatibilidad), pero ahora su contrato está
declarado y se puede comprobar con `validar_esquema_distribucion`.
"""

from typing import NotRequired, TypedDict


class AmbienteDistribuido(TypedDict):
    id: str
    nombre: str
    x: float
    y: float
    ancho: float
    largo: float
    area_m2: NotRequired[float]
    area_objetivo_m2: NotRequired[float]


Distribucion = list[AmbienteDistribuido]

CLAVES_NUMERICAS = ("x", "y", "ancho", "largo")


def validar_esquema_distribucion(distribucion) -> None:
    """
    Comprueba que la distribución cumpla el contrato mínimo.
    Lanza ValueError con un mensaje descriptivo si no lo cumple.
    """

    if not isinstance(distribucion, list) or not distribucion:
        raise ValueError("La distribución debe ser una lista no vacía.")

    ids = set()

    for posicion, ambiente in enumerate(distribucion, start=1):

        if not isinstance(ambiente, dict):
            raise ValueError(f"El ambiente {posicion} no es un diccionario.")

        for clave in ("id", "nombre", *CLAVES_NUMERICAS):
            if clave not in ambiente:
                raise ValueError(
                    f"Al ambiente {posicion} le falta la clave '{clave}'."
                )

        identificador = ambiente["id"]

        if identificador in ids:
            raise ValueError(f"Identificador duplicado: '{identificador}'.")

        ids.add(identificador)

        for clave in CLAVES_NUMERICAS:
            valor = ambiente[clave]
            if isinstance(valor, bool) or not isinstance(valor, (int, float)):
                raise ValueError(
                    f"'{clave}' de '{identificador}' debe ser numérico."
                )

        if ambiente["ancho"] <= 0 or ambiente["largo"] <= 0:
            raise ValueError(
                f"'{identificador}' debe tener ancho y largo positivos."
            )

        if ambiente["x"] < 0 or ambiente["y"] < 0:
            raise ValueError(
                f"'{identificador}' tiene coordenadas negativas."
            )
