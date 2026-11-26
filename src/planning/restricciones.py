"""Restricciones CP-SAT reutilizables del optimizador."""

from src.planning.reglas_ambientes import LONGITUD_MINIMA_ADYACENCIA_DM


# ============================================================
# 3. ADYACENCIA FÍSICA
# ============================================================

def agregar_adyacencia_fisica(
    modelo,
    ambiente_a,
    ambiente_b,
    identificador,
    ancho_terreno_dm,
    largo_terreno_dm,
    minimo=LONGITUD_MINIMA_ADYACENCIA_DM
):
    """
    Obliga a dos ambientes rectangulares a compartir
    una frontera de longitud mínima.

    Se consideran cuatro posibilidades:

    1. A a la izquierda de B.
    2. B a la izquierda de A.
    3. A debajo de B.
    4. B debajo de A.

    Retorna una variable booleana que indica
    si ambos ambientes son adyacentes.
    """

    # --------------------------------------------------------
    # VARIABLES DE POSICIÓN Y DIMENSIONES
    # --------------------------------------------------------

    x_a = ambiente_a["x"]
    y_a = ambiente_a["y"]

    fin_x_a = ambiente_a["fin_x"]
    fin_y_a = ambiente_a["fin_y"]

    x_b = ambiente_b["x"]
    y_b = ambiente_b["y"]

    fin_x_b = ambiente_b["fin_x"]
    fin_y_b = ambiente_b["fin_y"]

    # --------------------------------------------------------
    # SOLAPAMIENTO VERTICAL
    # --------------------------------------------------------

    inicio_vertical = modelo.NewIntVar(
        0,
        largo_terreno_dm,
        f"inicio_vertical_{identificador}"
    )

    fin_vertical = modelo.NewIntVar(
        0,
        largo_terreno_dm,
        f"fin_vertical_{identificador}"
    )

    modelo.AddMaxEquality(
        inicio_vertical,
        [y_a, y_b]
    )

    modelo.AddMinEquality(
        fin_vertical,
        [fin_y_a, fin_y_b]
    )

    solapamiento_vertical = modelo.NewIntVar(
        -largo_terreno_dm,
        largo_terreno_dm,
        f"solapamiento_vertical_{identificador}"
    )

    modelo.Add(
        solapamiento_vertical ==
        fin_vertical - inicio_vertical
    )

    # --------------------------------------------------------
    # SOLAPAMIENTO HORIZONTAL
    # --------------------------------------------------------

    inicio_horizontal = modelo.NewIntVar(
        0,
        ancho_terreno_dm,
        f"inicio_horizontal_{identificador}"
    )

    fin_horizontal = modelo.NewIntVar(
        0,
        ancho_terreno_dm,
        f"fin_horizontal_{identificador}"
    )

    modelo.AddMaxEquality(
        inicio_horizontal,
        [x_a, x_b]
    )

    modelo.AddMinEquality(
        fin_horizontal,
        [fin_x_a, fin_x_b]
    )

    solapamiento_horizontal = modelo.NewIntVar(
        -ancho_terreno_dm,
        ancho_terreno_dm,
        f"solapamiento_horizontal_{identificador}"
    )

    modelo.Add(
        solapamiento_horizontal ==
        fin_horizontal - inicio_horizontal
    )

    # --------------------------------------------------------
    # VARIABLES BOOLEANAS DE ORIENTACIÓN
    # --------------------------------------------------------

    a_izquierda = modelo.NewBoolVar(
        f"a_izquierda_{identificador}"
    )

    b_izquierda = modelo.NewBoolVar(
        f"b_izquierda_{identificador}"
    )

    a_abajo = modelo.NewBoolVar(
        f"a_abajo_{identificador}"
    )

    b_abajo = modelo.NewBoolVar(
        f"b_abajo_{identificador}"
    )

    # --------------------------------------------------------
    # A ESTÁ A LA IZQUIERDA DE B
    # --------------------------------------------------------

    modelo.Add(
        fin_x_a == x_b
    ).OnlyEnforceIf(a_izquierda)

    modelo.Add(
        solapamiento_vertical >= minimo
    ).OnlyEnforceIf(a_izquierda)

    # --------------------------------------------------------
    # B ESTÁ A LA IZQUIERDA DE A
    # --------------------------------------------------------

    modelo.Add(
        fin_x_b == x_a
    ).OnlyEnforceIf(b_izquierda)

    modelo.Add(
        solapamiento_vertical >= minimo
    ).OnlyEnforceIf(b_izquierda)

    # --------------------------------------------------------
    # A ESTÁ DEBAJO DE B
    # --------------------------------------------------------

    modelo.Add(
        fin_y_a == y_b
    ).OnlyEnforceIf(a_abajo)

    modelo.Add(
        solapamiento_horizontal >= minimo
    ).OnlyEnforceIf(a_abajo)

    # --------------------------------------------------------
    # B ESTÁ DEBAJO DE A
    # --------------------------------------------------------

    modelo.Add(
        fin_y_b == y_a
    ).OnlyEnforceIf(b_abajo)

    modelo.Add(
        solapamiento_horizontal >= minimo
    ).OnlyEnforceIf(b_abajo)

    # --------------------------------------------------------
    # AL MENOS UNA ORIENTACIÓN DEBE CUMPLIRSE
    # --------------------------------------------------------

    adyacente = modelo.NewBoolVar(
        f"adyacente_{identificador}"
    )

    orientaciones = [
        a_izquierda,
        b_izquierda,
        a_abajo,
        b_abajo
    ]

    modelo.AddBoolOr(
        orientaciones
    ).OnlyEnforceIf(adyacente)

    modelo.AddBoolAnd(
        [variable.Not() for variable in orientaciones]
    ).OnlyEnforceIf(adyacente.Not())

    return adyacente


def agregar_separacion(modelo, ambiente_a, ambiente_b, identificador, hueco_dm):
    """
    Impide que dos ambientes se toquen: deben distar `hueco_dm` en algún eje.

    Hace falta porque `adyacente == 0` no prohíbe compartir pared.
    """

    opciones = []

    for eje, fin in (("x", "fin_x"), ("y", "fin_y")):
        for orden, (primero, segundo) in enumerate(
            ((ambiente_a, ambiente_b), (ambiente_b, ambiente_a))
        ):
            opcion = modelo.NewBoolVar(f"separado_{eje}{orden}_{identificador}")
            modelo.Add(
                primero[fin] + hueco_dm <= segundo[eje]
            ).OnlyEnforceIf(opcion)
            opciones.append(opcion)

    modelo.AddBoolOr(opciones)
