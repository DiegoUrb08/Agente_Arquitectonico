"""
Garaje con acceso desde la calle: medidas mínimas, frente libre y portón.

La calle está abajo en el plano (y = 0), así que el auto entra por el borde
inferior del garaje.
"""

from src.planning.reglas_acceso import EXTERIOR, nombres_legibles, tipo_base

# Un auto: 2,70 × 5,00 m (estacionamiento individual del RNE peruano, A.010).
ANCHO_MINIMO_M = 2.70
LARGO_MINIMO_M = 5.00
AREA_OBJETIVO_MINIMA_M2 = 15.0

ANCHO_PORTON_M = 2.40
SEPARACION_EXTREMOS_M = 0.10
TOLERANCIA = 0.01


_SINONIMOS = {"garaje": "cochera", "cochera": "garaje"}


def como_se_llama(texto: str, nombres: list[str]) -> str:
    """
    Quien creó «cochera» puede pedir después «el garaje»: devuelve `texto`
    con la palabra que usan los `nombres` (ya normalizados) del plano.
    """
    palabra = texto.replace("_", " ").split(" ")[0]
    otra = _SINONIMOS.get(palabra)
    if not otra:
        return texto
    usa = lambda p: any(n.replace("_", " ").split(" ")[0] == p for n in nombres)
    if usa(palabra) or not usa(otra):
        return texto
    return otra + texto[len(palabra):]


def es_garaje(identificador: str) -> bool:
    return tipo_base(identificador) == "garaje"


def tiene_frente_libre(distribucion: list[dict], garaje: dict) -> bool:
    """True si ningún ambiente queda entre el garaje y la calle."""
    return not any(
        otro["y"] < garaje["y"] - TOLERANCIA
        and otro["x"] < garaje["x"] + garaje["ancho"] - TOLERANCIA
        and otro["x"] + otro["ancho"] > garaje["x"] + TOLERANCIA
        for otro in distribucion
        if otro["id"] != garaje["id"]
    )


def portones(distribucion: list[dict], espesor_muro_m: float) -> list[dict]:
    """El portón de cada garaje con frente a la calle y ancho suficiente."""
    resultado = []

    for a in distribucion:
        if not es_garaje(a["id"]):
            continue
        if a["ancho"] < ANCHO_PORTON_M + 2 * SEPARACION_EXTREMOS_M - TOLERANCIA:
            continue
        if not tiene_frente_libre(distribucion, a):
            continue
        resultado.append({
            "tipo": "puerta",
            "vehicular": True,
            "centro": (round(a["x"] + a["ancho"] / 2, 4), round(a["y"], 4)),
            "ancho": ANCHO_PORTON_M,
            "espesor_muro": float(espesor_muro_m),
            "orientacion": "horizontal",
            "ambiente_a": a["id"],
            "ambiente_b": EXTERIOR,
            "longitud_pared_m": round(a["ancho"], 3),
        })

    return resultado


def avisos_de_garaje(distribucion: list[dict]) -> list[str]:
    """Garajes de la planta baja por los que no puede entrar un auto."""
    nombre = nombres_legibles(distribucion)
    avisos = []

    for a in distribucion:
        if not es_garaje(a["id"]):
            continue
        if not tiene_frente_libre(distribucion, a):
            avisos.append(f"{nombre[a['id']]} no tiene acceso desde la calle.")
        if (
            a["ancho"] < ANCHO_MINIMO_M - TOLERANCIA
            or a["largo"] < LARGO_MINIMO_M - TOLERANCIA
        ):
            avisos.append(
                f"{nombre[a['id']]} mide {a['ancho']:g} × {a['largo']:g} m: "
                f"para un auto se necesitan {ANCHO_MINIMO_M:g} × "
                f"{LARGO_MINIMO_M:g} m (ancho por fondo)."
            )

    return avisos
