
import unicodedata

from src.models.requirements import RequerimientosArquitectonicos


# ============================================================
# 1. NORMALIZAR NOMBRES
# ============================================================

def normalizar_nombre(nombre: str) -> str:
    texto = str(nombre).strip().lower()

    texto = unicodedata.normalize("NFD", texto)

    return "".join(
        caracter
        for caracter in texto
        if unicodedata.category(caracter) != "Mn"
    )


# ============================================================
# 2. NORMALIZAR RELACIONES
# ============================================================

MODOS_VALIDOS = {
    "todos",
    "al_menos_uno",
    "correspondiente",
}


def interpretar_relacion(relacion):
    """
    Admite el formato antiguo:
        ["sala", "comedor"]

    Y el nuevo:
        {
            "ambiente_a": "sala",
            "ambiente_b": "comedor",
            "modo": "todos"
        }
    """

    if isinstance(relacion, (tuple, list)):

        if len(relacion) != 2:
            raise ValueError(
                f"Relación de adyacencia inválida: {relacion}"
            )

        ambiente_a, ambiente_b = relacion
        modo = "todos"

    elif isinstance(relacion, dict):

        ambiente_a = relacion.get("ambiente_a")
        ambiente_b = relacion.get("ambiente_b")
        modo = relacion.get("modo", "todos")

    else:
        raise ValueError(
            f"Formato de relación desconocido: {relacion}"
        )

    if not ambiente_a or not ambiente_b:
        raise ValueError(
            f"La relación debe especificar ambos ambientes: {relacion}"
        )

    modo = str(modo).strip().lower()

    if modo not in MODOS_VALIDOS:
        raise ValueError(
            f"Modo de adyacencia desconocido: {modo}"
        )

    return (
        normalizar_nombre(ambiente_a),
        normalizar_nombre(ambiente_b),
        modo
    )


# ============================================================
# 3. CONSTRUIR GRAFO ESPACIAL
# ============================================================

def construir_grafo(
    requerimientos: RequerimientosArquitectonicos
):
    """
    Construye un grafo espacial con ambientes individuales
    y relaciones de adyacencia configurables.

    Modos:

    todos:
        Todas las combinaciones deben ser adyacentes.

    al_menos_uno:
        Al menos una combinación debe ser adyacente.

    correspondiente:
        Cada instancia se relaciona con la instancia
        del mismo número de la otra categoría.
    """

    nodos = []
    relaciones = []

    ambientes_disponibles = {}

    # --------------------------------------------------------
    # CREAR NODOS
    # --------------------------------------------------------

    for ambiente in requerimientos.ambientes:

        nombre = normalizar_nombre(ambiente.nombre)

        if not nombre:
            raise ValueError(
                "Se encontró un ambiente sin nombre."
            )

        if ambiente.cantidad < 1:
            raise ValueError(
                f"La cantidad de '{ambiente.nombre}' debe ser positiva."
            )

        if nombre in ambientes_disponibles:
            raise ValueError(
                f"El ambiente '{ambiente.nombre}' está duplicado."
            )

        ambientes_disponibles[nombre] = []

        for i in range(1, ambiente.cantidad + 1):

            identificador = f"{nombre}_{i}"

            nodo = {
                "id": identificador,
                "nombre": ambiente.nombre,
                "nombre_base": nombre,
                "numero": i,
                "area_minima_m2": ambiente.area_minima_m2,
                "area_objetivo_m2": ambiente.area_objetivo_m2,
            }

            nodos.append(nodo)

            ambientes_disponibles[nombre].append(
                identificador
            )

    if not nodos:
        raise ValueError(
            "No se han definido ambientes."
        )

    # --------------------------------------------------------
    # INTERPRETAR RELACIONES
    # --------------------------------------------------------

    for relacion_original in requerimientos.relaciones_adyacencia:

        ambiente_a, ambiente_b, modo = interpretar_relacion(
            relacion_original
        )

        if ambiente_a not in ambientes_disponibles:
            raise ValueError(
                f"No existe el ambiente '{ambiente_a}'."
            )

        if ambiente_b not in ambientes_disponibles:
            raise ValueError(
                f"No existe el ambiente '{ambiente_b}'."
            )

        instancias_a = ambientes_disponibles[ambiente_a]
        instancias_b = ambientes_disponibles[ambiente_b]

        # --------------------------------------------
        # GENERAR PARES POSIBLES
        # --------------------------------------------

        if ambiente_a == ambiente_b:

            if len(instancias_a) < 2:
                raise ValueError(
                    f"No existen suficientes unidades de "
                    f"'{ambiente_a}' para establecer adyacencia."
                )

            pares = [
                (instancias_a[i], instancias_a[j])
                for i in range(len(instancias_a))
                for j in range(i + 1, len(instancias_a))
            ]

            if modo == "correspondiente":
                raise ValueError(
                    "El modo 'correspondiente' no puede utilizarse "
                    "entre instancias del mismo tipo."
                )

        elif modo == "correspondiente":

            if len(instancias_a) != len(instancias_b):
                raise ValueError(
                    f"El modo 'correspondiente' requiere la misma "
                    f"cantidad de '{ambiente_a}' y '{ambiente_b}'."
                )

            pares = list(zip(instancias_a, instancias_b))

        else:

            pares = [
                (nodo_a, nodo_b)
                for nodo_a in instancias_a
                for nodo_b in instancias_b
            ]

        # --------------------------------------------
        # GUARDAR RELACIÓN
        # --------------------------------------------

        relaciones.append({
            "ambiente_a": ambiente_a,
            "ambiente_b": ambiente_b,
            "modo": modo,
            "pares": [
                list(par)
                for par in pares
            ]
        })

    # --------------------------------------------------------
    # DEVOLVER RESULTADO
    # --------------------------------------------------------

    return {
        "nodos": nodos,
        "relaciones": relaciones
    }


# ============================================================
# 4. PRUEBA INDEPENDIENTE
# ============================================================

if __name__ == "__main__":

    from src.models.requirements import (
        RequerimientosArquitectonicos
    )

    ejemplo = RequerimientosArquitectonicos(
        tipo_proyecto="vivienda",

        ancho_terreno_m=10,
        largo_terreno_m=20,

        ambientes=[
            {"nombre": "dormitorio", "cantidad": 2},
            {"nombre": "sala", "cantidad": 1},
            {"nombre": "cocina", "cantidad": 1},
            {"nombre": "baño", "cantidad": 2}
        ],

        relaciones_adyacencia=[
            {
                "ambiente_a": "sala",
                "ambiente_b": "cocina",
                "modo": "todos"
            },
            {
                "ambiente_a": "dormitorio",
                "ambiente_b": "baño",
                "modo": "al_menos_uno"
            },
            {
                "ambiente_a": "baño",
                "ambiente_b": "baño",
                "modo": "todos"
            }
        ]
    )

    grafo = construir_grafo(ejemplo)

    print("\nNODOS DEL GRAFO:\n")

    for nodo in grafo["nodos"]:
        print(nodo)

    print("\nRELACIONES ESPACIALES:\n")

    for relacion in grafo["relaciones"]:

        print(
            f"{relacion['ambiente_a']} - "
            f"{relacion['ambiente_b']}"
        )

        print(f"Modo: {relacion['modo']}")
        print(f"Pares: {relacion['pares']}\n")

    print("GRAFO CONSTRUIDO CORRECTAMENTE.")
