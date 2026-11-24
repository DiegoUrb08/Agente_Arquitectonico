
def detectar_adyacencias(
    distribucion: list[dict],
    longitud_minima_m: float = 0.8,
    tolerancia_m: float = 0.01
) -> list[dict]:
    """
    Detecta los ambientes que comparten un segmento de pared.

    La distribución debe contener:
    id, nombre, x, y, ancho y largo.

    Las coordenadas y dimensiones están expresadas en metros.
    """

    adyacencias = []

    for i in range(len(distribucion)):
        ambiente_a = distribucion[i]

        ax1 = float(ambiente_a["x"])
        ay1 = float(ambiente_a["y"])
        ax2 = ax1 + float(ambiente_a["ancho"])
        ay2 = ay1 + float(ambiente_a["largo"])

        for j in range(i + 1, len(distribucion)):
            ambiente_b = distribucion[j]

            bx1 = float(ambiente_b["x"])
            by1 = float(ambiente_b["y"])
            bx2 = bx1 + float(ambiente_b["ancho"])
            by2 = by1 + float(ambiente_b["largo"])

            longitud = 0
            orientacion = None
            segmento = None

            # ==========================================
            # 1. COMPROBAR PARED VERTICAL COMPARTIDA
            # ==========================================

            if abs(ax2 - bx1) <= tolerancia_m:
                inicio = max(ay1, by1)
                fin = min(ay2, by2)

                longitud = max(0, fin - inicio)

                if longitud >= longitud_minima_m - tolerancia_m:
                    orientacion = "vertical"
                    segmento = {
                        "inicio": (ax2, inicio),
                        "fin": (ax2, fin)
                    }

            elif abs(bx2 - ax1) <= tolerancia_m:
                inicio = max(ay1, by1)
                fin = min(ay2, by2)

                longitud = max(0, fin - inicio)

                if longitud >= longitud_minima_m - tolerancia_m:
                    orientacion = "vertical"
                    segmento = {
                        "inicio": (ax1, inicio),
                        "fin": (ax1, fin)
                    }

            # ==========================================
            # 2. COMPROBAR PARED HORIZONTAL COMPARTIDA
            # ==========================================

            if orientacion is None:

                if abs(ay2 - by1) <= tolerancia_m:
                    inicio = max(ax1, bx1)
                    fin = min(ax2, bx2)

                    longitud = max(0, fin - inicio)

                    if longitud >= longitud_minima_m - tolerancia_m:
                        orientacion = "horizontal"
                        segmento = {
                            "inicio": (inicio, ay2),
                            "fin": (fin, ay2)
                        }

                elif abs(by2 - ay1) <= tolerancia_m:
                    inicio = max(ax1, bx1)
                    fin = min(ax2, bx2)

                    longitud = max(0, fin - inicio)

                    if longitud >= longitud_minima_m - tolerancia_m:
                        orientacion = "horizontal"
                        segmento = {
                            "inicio": (inicio, ay1),
                            "fin": (fin, ay1)
                        }

            # ==========================================
            # 3. REGISTRAR ADYACENCIA
            # ==========================================

            if orientacion is not None:
                adyacencias.append({
                    "ambiente_a": ambiente_a["id"],
                    "nombre_a": ambiente_a["nombre"],
                    "ambiente_b": ambiente_b["id"],
                    "nombre_b": ambiente_b["nombre"],
                    "orientacion": orientacion,
                    "longitud_m": round(longitud, 3),
                    "segmento": segmento
                })

    return adyacencias


def encontrar_componentes(
    distribucion: list[dict],
    adyacencias: list[dict]
) -> list[list[str]]:
    """
    Identifica los grupos de ambientes conectados físicamente.

    Dos ambientes pertenecen al mismo grupo si existe
    una cadena de adyacencias entre ellos.
    """

    grafo = {
        ambiente["id"]: set()
        for ambiente in distribucion
    }

    for adyacencia in adyacencias:
        a = adyacencia["ambiente_a"]
        b = adyacencia["ambiente_b"]

        grafo[a].add(b)
        grafo[b].add(a)

    visitados = set()
    componentes = []

    for identificador in grafo:

        if identificador in visitados:
            continue

        componente = []
        pendientes = [identificador]

        while pendientes:
            actual = pendientes.pop()

            if actual in visitados:
                continue

            visitados.add(actual)
            componente.append(actual)

            pendientes.extend(
                vecino
                for vecino in grafo[actual]
                if vecino not in visitados
            )

        componentes.append(componente)

    return componentes


def validar_distribucion(
    distribucion: list[dict],
    longitud_minima_m: float = 0.8,
    tolerancia_m: float = 0.01
) -> dict:
    """
    Ejecuta la validación geométrica de adyacencias
    y conectividad de toda la distribución.
    """

    if not distribucion:
        raise ValueError(
            "La distribución no contiene ambientes."
        )

    identificadores = [
        ambiente["id"]
        for ambiente in distribucion
    ]

    if len(identificadores) != len(set(identificadores)):
        raise ValueError(
            "Existen identificadores de ambientes duplicados."
        )

    for ambiente in distribucion:
        if (
            float(ambiente["ancho"]) <= 0
            or float(ambiente["largo"]) <= 0
        ):
            raise ValueError(
                f"Dimensiones inválidas en {ambiente['id']}."
            )

    adyacencias = detectar_adyacencias(
        distribucion,
        longitud_minima_m,
        tolerancia_m
    )

    componentes = encontrar_componentes(
        distribucion,
        adyacencias
    )

    ambientes_conexion = set()

    for adyacencia in adyacencias:
        ambientes_conexion.add(adyacencia["ambiente_a"])
        ambientes_conexion.add(adyacencia["ambiente_b"])

    ambientes_aislados = [
        ambiente["id"]
        for ambiente in distribucion
        if ambiente["id"] not in ambientes_conexion
    ]

    return {
        "adyacencias": adyacencias,
        "cantidad_adyacencias": len(adyacencias),
        "componentes": componentes,
        "cantidad_componentes": len(componentes),
        "ambientes_aislados": ambientes_aislados,
        "distribucion_conectada": len(componentes) == 1
    }


def imprimir_validacion(resultado: dict):
    """
    Imprime un informe legible de la validación.
    """

    print("\nVALIDACIÓN DE ADYACENCIAS")
    print("=" * 55)

    print(
        f"\nAdyacencias detectadas: "
        f"{resultado['cantidad_adyacencias']}"
    )

    for adyacencia in resultado["adyacencias"]:
        print(
            f"\n{adyacencia['ambiente_a']} <-> "
            f"{adyacencia['ambiente_b']}"
        )

        print(
            f"  Orientación: {adyacencia['orientacion']}"
        )

        print(
            f"  Longitud compartida: "
            f"{adyacencia['longitud_m']} m"
        )

        print(
            f"  Segmento: {adyacencia['segmento']}"
        )

    print("\nCOMPONENTES CONECTADOS")
    print("-" * 55)

    for i, componente in enumerate(
        resultado["componentes"],
        start=1
    ):
        print(f"Grupo {i}: {', '.join(componente)}")

    print("\nAMBIENTES AISLADOS")
    print("-" * 55)

    if resultado["ambientes_aislados"]:
        for ambiente in resultado["ambientes_aislados"]:
            print(f"- {ambiente}")
    else:
        print("No existen ambientes aislados.")

    print("\nRESULTADO GENERAL")
    print("-" * 55)

    if resultado["distribucion_conectada"]:
        print("La distribución forma una única red de ambientes.")
    else:
        print(
            "La distribución contiene grupos "
            "de ambientes desconectados."
        )
