"""
Edición por conversación de casas de dos plantas.

Cada operación se aplica a la planta que corresponde con el mismo editor de
una planta; la escalera no se mueve y la planta alta procura no sobresalir.
"""

import tempfile
from pathlib import Path

from src.ai.edit_interpreter import EditOperation, EditRequest
from src.cad.dxf_editor import cargar_y_editar, distribucion_desde_ambientes
from src.cad.dxf_generator import generar_dxf_desde_geometrias
from src.geometry.geometry_generator import generar_geometrias
from src.models.requirements import Retiros
from src.planning.garaje import como_se_llama
from src.planning.layout_optimizer import ESCALERA, contorno
from src.planning.reglas_acceso import tipo_base
from src.planning.retiros import area_edificable, trasladar
from src.services.pipeline import construir_multipisos
from src.utils.texto import normalizar_nombre

PLANTAS = ("baja", "alta")


def _coincidentes(distribucion, texto) -> list[dict]:
    """Ambientes de una planta que responden a "dormitorio 2" o "baño"."""
    clave = como_se_llama(
        normalizar_nombre(texto),
        [normalizar_nombre(a["nombre"]) for a in distribucion],
    )
    por_id = [
        a for a in distribucion
        if normalizar_nombre(a["id"]) == clave.replace(" ", "_")
    ]
    return por_id or [
        a for a in distribucion if normalizar_nombre(a["nombre"]) == clave
    ]


def _plantas_con(distribuciones, texto, planta=None) -> list[int]:
    clave = como_se_llama(
        normalizar_nombre(texto),
        [normalizar_nombre(a["nombre"]) for d in distribuciones for a in d],
    ).replace(" ", "_")
    exactas = [
        i for i, d in enumerate(distribuciones)
        if any(normalizar_nombre(a["id"]) == clave for a in d)
    ]
    indices = exactas or [
        i for i, d in enumerate(distribuciones) if _coincidentes(d, texto)
    ]
    if planta is not None:
        indices = [i for i in indices if i == PLANTAS.index(planta)]
    if not indices:
        lugar = f" en la planta {planta}" if planta else ""
        raise ValueError(f"No se encontro el ambiente: {texto}{lugar}.")
    return indices


def _planta_para_agregar(distribuciones, operacion) -> int:
    if operacion.planta:
        return PLANTAS.index(operacion.planta)

    privado = normalizar_nombre(operacion.ambiente).startswith(
        ("dormitorio", "bano", "closet")
    )
    habitual = 1 if privado else 0

    if operacion.referencia:
        con_referencia = _plantas_con(distribuciones, operacion.referencia)
        if habitual not in con_referencia:
            return con_referencia[0]

    return habitual


def _editar_piso(distribuciones, indice, operacion, terreno, norte=None):
    """Aplica la operación a una planta y devuelve (distribución, resultado)."""
    ancho, largo = terreno
    numeros: dict[str, int] = {}
    for distribucion in distribuciones:
        for a in distribucion:
            base, numero = a["id"].rsplit("_", 1)
            base = normalizar_nombre(base)
            numeros[base] = max(numeros.get(base, 0), int(numero))

    planta = {
        "fijos": frozenset({ESCALERA}),
        "planta_baja": indice == 0,
        "norte": norte,
        "limites": contorno(distribuciones[0]) if indice else None,
    }
    if indice == 0 and len(distribuciones) > 1:
        arriba = contorno(distribuciones[1])
        abajo = contorno(distribuciones[0])
        # Solo lo que hoy ya está cubierto: no se exige corregir lo anterior.
        planta["cubrir"] = (
            max(arriba[0], abajo[0]), max(arriba[1], abajo[1]),
            min(arriba[2], abajo[2]), min(arriba[3], abajo[3]),
        )

    with tempfile.TemporaryDirectory() as carpeta:
        ruta = Path(carpeta) / "planta.dxf"
        geometrias = generar_geometrias(distribuciones[indice], ancho, largo)
        generar_dxf_desde_geometrias(geometrias, ancho, largo, str(ruta))
        _, ambientes, _, resultados = cargar_y_editar(
            ruta, EditRequest(operaciones=[operacion]), planta, numeros
        )
        nueva = distribucion_desde_ambientes(ambientes)

    return nueva, {**resultados[0], "planta": PLANTAS[indice]}


def _cambiar_de_planta(
    distribuciones, operacion, origen, destino, terreno, norte=None
):
    """Mover junto a un ambiente de la otra planta: quitar y volver a poner."""
    candidatos = _coincidentes(distribuciones[origen], operacion.ambiente)
    ambiente = max(candidatos, key=lambda a: int(a["id"].rsplit("_", 1)[1]))
    if tipo_base(ambiente["id"]) == "escalera":
        raise ValueError("La escalera une las dos plantas y no se puede mover.")

    nuevas = list(distribuciones)
    nuevas[origen], quitado = _editar_piso(
        nuevas, origen,
        EditOperation(tipo="quitar_ambiente", ambiente=ambiente["id"]), terreno,
        norte,
    )
    relacion = operacion.relacion
    nuevas[destino], agregado = _editar_piso(
        nuevas, destino,
        EditOperation(
            tipo="agregar_ambiente", ambiente=ambiente["nombre"],
            area_objetivo=round(ambiente["ancho"] * ambiente["largo"], 2),
            referencia=operacion.referencia,
            relacion=None if relacion == "lejos_de" else relacion,
        ),
        terreno, norte,
    )
    resultado = {
        "accion": "cambiado_de_planta",
        "ambiente": ambiente["nombre"],
        "id": agregado["id"],
        "id_anterior": ambiente["id"],
        "planta": PLANTAS[destino],
        "ajustes": quitado.get("ajustes", []) + agregado.get("ajustes", []),
    }
    return nuevas, resultado


def _aplicar(distribuciones, operacion, terreno, norte=None):
    if operacion.tipo == "agregar_ambiente":
        indice = _planta_para_agregar(distribuciones, operacion)

    elif operacion.tipo == "mover_ambiente":
        origenes = _plantas_con(distribuciones, operacion.ambiente)
        destinos = _plantas_con(distribuciones, operacion.referencia)
        comunes = [i for i in origenes if i in destinos]
        if operacion.planta:
            pedida = PLANTAS.index(operacion.planta)
            comunes = [i for i in comunes if i == pedida]
            destinos = [pedida] if pedida in destinos else destinos
        if not comunes:
            return _cambiar_de_planta(
                distribuciones, operacion, origenes[0], destinos[0], terreno,
                norte,
            )
        indice = comunes[0]

    else:
        indices = _plantas_con(
            distribuciones, operacion.ambiente, operacion.planta
        )
        if len(indices) > 1 and operacion.tipo in (
            "modificar_area", "renombrar_ambiente"
        ):
            raise ValueError(
                f"Hay «{operacion.ambiente}» en las dos plantas: indica cuál "
                "(por ejemplo, «el de arriba»)."
            )
        indice = indices[-1]

    nuevas = list(distribuciones)
    nuevas[indice], resultado = _editar_piso(
        nuevas, indice, operacion, terreno, norte
    )
    return nuevas, resultado


def editar_plano_multipisos(
    resultado, ruta_salida, solicitud, progreso=None, norte=None,
    retiros=None,
) -> dict:
    """
    Como `pipeline.editar_plano`, pero sobre un `ResultadoPlanoMultipisos`.
    """
    minx, miny, maxx, maxy = resultado.pisos[0].geometrias["terreno"].bounds
    terreno = (round(maxx - minx, 3), round(maxy - miny, 3))
    # Se edita dentro de los retiros y al final se devuelve a su sitio.
    retiros = retiros or Retiros()
    completo = terreno
    terreno = area_edificable(*completo, retiros)
    distribuciones = [
        trasladar(p.distribucion, -retiros.izquierdo, -retiros.frontal)
        for p in resultado.pisos
    ]
    modificaciones = []

    for operacion in solicitud.operaciones:
        distribuciones, hecho = _aplicar(
            distribuciones, operacion, terreno, norte
        )
        modificaciones.append(hecho)

    distribuciones = [
        trasladar(d, retiros.izquierdo, retiros.frontal) for d in distribuciones
    ]
    plano = construir_multipisos(
        distribuciones, *completo, ruta_salida, progreso
    )

    return {
        "archivo": str(ruta_salida),
        "modificaciones": modificaciones,
        "observaciones": list(solicitud.observaciones),
        "plano": plano,
    }
