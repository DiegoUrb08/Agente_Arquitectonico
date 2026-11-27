"""
Reglas de funcionamiento de la vivienda: por dónde se entra a cada ambiente.

Funciones puras compartidas por el optimizador, el generador de puertas y los
avisos del plano. Los ambientes se identifican como en el grafo espacial:
"<nombre normalizado>_<número>".
"""

from src.models.requirements import Ambiente, RequerimientosArquitectonicos
from src.utils.texto import normalizar_nombre

EXTERIOR = "exterior"

CIRCULACION = {"sala", "comedor", "pasillo", "escalera"}
SOCIALES = {"sala", "comedor", "cocina"}
# Ambientes de servicio a los que también se puede entrar desde la cocina.
DESDE_COCINA = {"lavanderia", "deposito", "garaje"}
# A la terraza se sale desde un ambiente amplio o un dormitorio, nunca desde
# la escalera ni un pasillo.
DESDE_TERRAZA = {"sala", "comedor", "dormitorio"}
# Desde la escalera solo se pasa a la circulación.
DESDE_ESCALERA = {"sala", "comedor", "pasillo"}

ORDEN_ENTRADA = ("sala", "comedor", "pasillo", "escalera", "cocina", "estudio")
ORDEN_ENTRADA_PLANTA_ALTA = ("escalera", "pasillo", "sala", "comedor")

PORCENTAJE_PASILLO = 0.10
AREA_MINIMA_PASILLO_M2 = 3.0
AREA_OBJETIVO_MINIMA_PASILLO_M2 = 4.0

ANCHO_MINIMO_PUERTA_PARED_M = 1.10


def tipo_base(identificador: str) -> str:
    """'dormitorio principal_1' -> 'dormitorio'; 'cochera_1' -> 'garaje'."""
    nombre = normalizar_nombre(str(identificador).rsplit("_", 1)[0])
    for prefijo in ("dormitorio", "bano"):
        if nombre.startswith(prefijo):
            return prefijo
    return {"cochera": "garaje", "oficina": "estudio"}.get(nombre, nombre)


def elegir_entrada(ids: list[str], planta_baja: bool = True) -> str:
    """Ambiente por el que se llega a la planta (puerta exterior o escalera)."""
    orden = ORDEN_ENTRADA if planta_baja else ORDEN_ENTRADA_PLANTA_ALTA

    def prioridad(identificador):
        tipo = tipo_base(identificador)
        if tipo in orden:
            return orden.index(tipo)
        return len(orden) + {"dormitorio": 1, "bano": 2}.get(tipo, 0)

    return min(ids, key=prioridad)


def asignar_en_suite(ids: list[str], relaciones: list[dict] | None = None) -> dict:
    """
    Baños privados como {baño: dormitorio}.

    Mandan las relaciones que obliguen a juntar dormitorios y baños; si no
    hay, con dos o más baños uno es del dormitorio principal (o del primero).
    """
    pedidos = {}
    for relacion in relaciones or []:
        if relacion["modo"] == "al_menos_uno":
            continue
        for a, b in relacion["pares"]:
            par = {tipo_base(a): a, tipo_base(b): b}
            if set(par) == {"dormitorio", "bano"}:
                pedidos.setdefault(par["bano"], par["dormitorio"])
    if pedidos:
        return pedidos

    banos = [i for i in ids if tipo_base(i) == "bano"]
    dormitorios = [i for i in ids if tipo_base(i) == "dormitorio"]
    if len(banos) < 2 or not dormitorios:
        return {}

    principal = next((d for d in dormitorios if "principal" in d), dormitorios[0])
    return {banos[-1]: principal}


def puede_dar_acceso(
    desde: str, hacia: str, en_suite: dict | None = None, entrada: str | None = None
) -> bool:
    """True si es correcto entrar a `hacia` por una puerta desde `desde`."""
    en_suite = en_suite or {}

    if desde == hacia:
        return False
    if hacia in en_suite:
        return en_suite[hacia] == desde

    origen, destino = tipo_base(desde), tipo_base(hacia)

    # Van antes que la entrada: en la planta alta la entrada es la escalera.
    if destino == "terraza":
        return origen in DESDE_TERRAZA
    # La escalera no es un pasillo: abajo se llega a ella y nada más; arriba,
    # donde es la entrada, desemboca en la circulación, no en un cuarto. Así
    # queda paso libre al subir y bajar.
    if origen == "escalera":
        return desde == entrada and destino in DESDE_ESCALERA

    # La entrada reparte hacia cualquier ambiente (p. ej. si no hay sala).
    if desde == entrada:
        return True
    if destino in {"dormitorio", "bano"}:
        return origen in {"pasillo", "sala", "escalera"}
    if destino == "closet":
        return origen in {"dormitorio", "pasillo"}
    if destino in DESDE_COCINA:
        return origen in CIRCULACION or origen == "cocina"
    return origen in CIRCULACION


def completar_programa(
    requerimientos: RequerimientosArquitectonicos,
) -> RequerimientosArquitectonicos:
    """
    Añade un pasillo cuando hay dos o más dormitorios y baños de acceso común
    y el usuario no pidió uno. Devuelve el mismo objeto si no hace falta.
    """
    cantidades = {
        "dormitorio": 0, "bano": 0, "pasillo": 0, "escalera": 0, "sala": 0,
        "comedor": 0,
    }
    for ambiente in requerimientos.ambientes:
        tipo = tipo_base(normalizar_nombre(ambiente.nombre))
        if tipo in cantidades:
            cantidades[tipo] += ambiente.cantidad

    if cantidades["pasillo"]:
        return requerimientos

    # En la casa básica la sala reparte al dormitorio y al baño.
    if (
        requerimientos.programa_basico
        and cantidades["dormitorio"] <= 1 and cantidades["bano"] <= 1
    ):
        return requerimientos

    dormitorios, banos = cantidades["dormitorio"], cantidades["bano"]
    privados = 1 if banos >= 2 and dormitorios else 0
    # Una planta de cuartos con escalera y sin sala necesita un hall donde
    # desembarcar (de la escalera solo se pasa a la circulación).
    desembarco = (
        cantidades["escalera"] and dormitorios + banos
        and not cantidades["sala"] + cantidades["comedor"]
    )
    if dormitorios + banos - privados < 2 and not desembarco:
        return requerimientos

    superficie = sum(
        (a.area_objetivo_m2 or a.area_minima_m2 or 8) * a.cantidad
        for a in requerimientos.ambientes
    )
    pasillo = Ambiente(
        nombre="pasillo",
        area_minima_m2=AREA_MINIMA_PASILLO_M2,
        area_objetivo_m2=round(
            max(AREA_OBJETIVO_MINIMA_PASILLO_M2, superficie * PORCENTAJE_PASILLO), 2
        ),
    )
    return requerimientos.model_copy(
        update={"ambientes": [*requerimientos.ambientes, pasillo]}
    )


def nombres_legibles(distribucion: list[dict]) -> dict:
    """{id: "Baño 2"}; el número solo aparece si el nombre se repite."""
    nombres = [str(a["nombre"]).capitalize() for a in distribucion]
    legibles = {}
    vistos: dict[str, int] = {}
    for ambiente, nombre in zip(distribucion, nombres):
        vistos[nombre] = vistos.get(nombre, 0) + 1
        sufijo = f" {vistos[nombre]}" if nombres.count(nombre) > 1 else ""
        legibles[ambiente["id"]] = nombre + sufijo
    return legibles


def evaluar_reglas(
    distribucion: list[dict],
    puertas: list[dict],
    adyacencias: list[dict],
    planta_baja: bool = True,
) -> list[str]:
    """Avisos en español sobre las reglas que el plano no cumple."""
    ids = [a["id"] for a in distribucion]
    if not ids:
        return []

    nombre = nombres_legibles(distribucion)
    avisos = []

    conexiones = [
        (p["ambiente_a"], p["ambiente_b"])
        for p in puertas
        if p.get("ambiente_b") != EXTERIOR
    ]
    entradas = [
        p["ambiente_a"] for p in puertas
        if p.get("ambiente_b") == EXTERIOR and not p.get("vehicular")
    ]

    if planta_baja and not entradas:
        avisos.append("La vivienda no tiene puerta al exterior.")

    entrada = entradas[0] if entradas else elegir_entrada(ids, planta_baja)

    # Baño privado: el que solo tiene puerta a un dormitorio.
    en_suite = {}
    for bano in (i for i in ids if tipo_base(i) == "bano"):
        vecinos = [b if a == bano else a for a, b in conexiones if bano in (a, b)]
        if len(vecinos) == 1 and tipo_base(vecinos[0]) == "dormitorio":
            en_suite[bano] = vecinos[0]

    alcanzados = {entrada}
    pendientes = [entrada]
    while pendientes:
        actual = pendientes.pop()
        for a, b in conexiones:
            if actual not in (a, b):
                continue
            otro = b if actual == a else a
            if otro not in alcanzados and puede_dar_acceso(
                actual, otro, en_suite, entrada
            ):
                alcanzados.add(otro)
                pendientes.append(otro)

    sin_puerta = {i for i in ids if not any(i in par for par in conexiones)}
    for identificador in ids:
        if identificador in alcanzados:
            continue
        if identificador in sin_puerta:
            avisos.append(f"{nombre[identificador]} no tiene ninguna puerta de acceso.")
        else:
            avisos.append(
                f"Para llegar a {nombre[identificador]} hay que cruzar un "
                "ambiente que no es de paso."
            )

    banos_juntos = sorted(
        (a["ambiente_a"], a["ambiente_b"])
        for a in adyacencias
        if tipo_base(a["ambiente_a"]) == tipo_base(a["ambiente_b"]) == "bano"
    )
    for a, b in banos_juntos:
        avisos.append(f"{nombre[a]} y {nombre[b]} comparten pared.")

    cocinas = [i for i in ids if tipo_base(i) == "cocina"]
    destino = next(
        (t for t in ("comedor", "sala") if any(tipo_base(i) == t for i in ids)), None
    )
    if cocinas and destino:
        junto = any(
            {tipo_base(a["ambiente_a"]), tipo_base(a["ambiente_b"])}
            == {"cocina", destino}
            for a in adyacencias
        )
        if not junto:
            lugar = "al comedor" if destino == "comedor" else "a la sala"
            avisos.append(f"La cocina no está junto {lugar}.")

    return avisos
