"""Estado de un proyecto: versiones del plano y conversación (sin Streamlit)."""

import re
import tempfile
from pathlib import Path

import ezdxf

from src.services.edicion_multipisos import editar_plano_multipisos
from src.services.pipeline import (
    ResultadoPlanoMultipisos,
    abrir_plano,
    editar_plano,
    generar_csv_areas,
    generar_plano,
)

RELACIONES = {
    "junto_a": "junto a",
    "cerca_de": "cerca de",
    "lejos_de": "lejos de",
    "izquierda_de": "a la izquierda de",
    "derecha_de": "a la derecha de",
    "arriba_de": "arriba de",
    "abajo_de": "abajo de",
}

AYUDA = (
    "Puedo **cambiar el área** de un ambiente (*«reduce el comedor a 8 m²»*), "
    "**reubicarlo** (*«pon la cocina al lado del dormitorio»*), **agregar** "
    "(*«agrega un estudio»*), **quitar** (*«quita un baño»*) o "
    "**renombrar** ambientes (*«llama cocina al ambiente 1»*)."
)

AYUDA_PLANTAS = " En esta casa puedes decir «arriba» o «abajo»."


def pisos_de(resultado) -> list:
    if isinstance(resultado, ResultadoPlanoMultipisos):
        return list(resultado.pisos)
    return [resultado]


def dimensiones_terreno(piso) -> tuple[float, float]:
    minx, miny, maxx, maxy = piso.geometrias["terreno"].bounds
    return maxx - minx, maxy - miny


def _legible(identificador: str) -> str:
    return str(identificador).replace("_", " ").capitalize()


def resumen_modificaciones(modificaciones: list) -> list[str]:
    """Una línea legible por cada modificación aplicada por el editor."""
    lineas = []
    for m in modificaciones:
        nombre = _legible(m.get("id") or m["ambiente"])
        planta = f" (planta {m['planta']})" if m.get("planta") else ""
        accion = m.get("accion")
        if accion == "agregado":
            lineas.append(
                f"Agregué {nombre}, de {m['area_nueva']:.1f} m²{planta}"
            )
        elif accion == "quitado":
            lineas.append(f"Quité {nombre}{planta}")
        elif accion == "renombrado":
            lineas.append(
                f"{_legible(m['id_anterior'])} ahora es {nombre}{planta}"
            )
        elif accion == "cambiado_de_planta":
            cambio = f" como {nombre}" if m["id"] != m["id_anterior"] else ""
            lineas.append(
                f"{_legible(m['id_anterior'])} pasó a la planta "
                f"{m['planta']}{cambio}"
            )
        elif "area_nueva" in m:
            lineas.append(
                f"{nombre}: {m['area_anterior']:.1f} → {m['area_nueva']:.1f} m²"
            )
        else:
            relacion = RELACIONES.get(m["relacion"], m["relacion"])
            referencia = str(m["referencia"]).replace("_", " ")
            lineas.append(f"{nombre} movido {relacion} {referencia}{planta}")
        if m.get("tambien"):
            verbo = "quité" if accion == "quitado" else "agregué"
            extra = ", ".join(_legible(i) for i in m["tambien"])
            lineas.append(f"También {verbo}: {extra}")
        if m.get("ajustes"):
            cedidos = ", ".join(
                f"{_legible(a['id'])} {a['area_anterior']:.1f} → "
                f"{a['area_nueva']:.1f} m²"
                for a in m["ajustes"]
            )
            lineas.append(f"Para hacer sitio reacomodé la planta: {cedidos}")
    return lineas


def describir_plano(resultado) -> str:
    pisos = pisos_de(resultado)
    ambientes = sum(len(p.distribucion) for p in pisos)
    superficie = sum(
        a.get("area_m2", a["ancho"] * a["largo"])
        for p in pisos
        for a in p.distribucion
    )
    ancho, largo = dimensiones_terreno(pisos[0])
    texto = (
        f"{ambientes} ambientes, {superficie:.1f} m² construidos en un "
        f"terreno de {ancho:g} × {largo:g} m"
    )
    if len(pisos) > 1:
        texto += f" ({len(pisos)} plantas)"
    return texto


def _mensaje(rol: str, texto: str, detalle: str | None = None) -> dict:
    return {"rol": rol, "texto": texto, "detalle": detalle}


def _por_piso(resultado, atributo: str) -> list[str]:
    """Notas o avisos de todas las plantas, indicando cuál si hay varias."""
    pisos = pisos_de(resultado)
    textos = []
    for i, piso in enumerate(pisos):
        planta = "" if len(pisos) == 1 else (
            "Planta baja: " if i == 0 else f"Planta alta {i}: "
        )
        textos += [planta + t for t in getattr(piso, atributo)]
    return textos


def observaciones_del_plano(resultado) -> str:
    """Texto para el chat con lo añadido y las reglas no cumplidas."""
    lineas = list(dict.fromkeys(
        re.sub(r"^Planta (baja|alta \d+): ", "", t)
        for t in _por_piso(resultado, "notas")
    ))
    lineas += [f"⚠️ {t}" for t in _por_piso(resultado, "avisos")]
    return "".join(f"\n\n{linea}" for linea in lineas)


def _geometria(ambiente: dict) -> tuple:
    return tuple(round(ambiente[k], 3) for k in ("x", "y", "ancho", "largo"))


def ambientes_cambiados(antes, despues) -> frozenset:
    """Ids de los ambientes cuya posición o tamaño difiere entre dos planos."""
    previos = {
        a["id"]: _geometria(a) for p in pisos_de(antes) for a in p.distribucion
    }
    return frozenset(
        a["id"]
        for p in pisos_de(despues)
        for a in p.distribucion
        if previos.get(a["id"]) != _geometria(a)
    )


def _version(resultado, dxf: bytes, etiqueta: str, cambiados=frozenset()) -> dict:
    return {
        "resultado": resultado,
        "dxf": dxf,
        "csv": generar_csv_areas(resultado),
        "etiqueta": etiqueta,
        "cambiados": frozenset(cambiados),
    }


def _invitacion(resultado) -> str:
    return AYUDA + (AYUDA_PLANTAS if len(pisos_de(resultado)) > 1 else "")


def proyecto_inicial(requerimientos, texto: str, resultado, dxf: bytes) -> dict:
    """Proyecto con un plano ya generado como versión 1."""

    return {
        "requerimientos": requerimientos,
        "versiones": [_version(resultado, dxf, "Plano inicial")],
        "mensajes": [
            _mensaje("usuario", texto),
            _mensaje(
                "agente",
                f"Plano generado: {describir_plano(resultado)}."
                + observaciones_del_plano(resultado)
                + "\n\n" + _invitacion(resultado),
            ),
        ],
    }


def crear_proyecto(requerimientos, texto: str, progreso=None) -> dict:
    """Genera el plano inicial a partir de requerimientos ya interpretados."""

    with tempfile.TemporaryDirectory() as carpeta:
        ruta = Path(carpeta) / "plano.dxf"
        resultado = generar_plano(requerimientos, ruta, progreso=progreso)
        dxf = ruta.read_bytes()

    return proyecto_inicial(requerimientos, texto, resultado, dxf)


def abrir_proyecto(dxf: bytes, nombre_archivo: str, progreso=None) -> dict:
    """Abre un DXF existente como versión inicial de un proyecto."""

    with tempfile.TemporaryDirectory() as carpeta:
        entrada = Path(carpeta) / "entrada.dxf"
        salida = Path(carpeta) / "salida.dxf"
        entrada.write_bytes(dxf)
        try:
            resultado = abrir_plano(entrada, salida, progreso=progreso)
        except (OSError, ezdxf.DXFError) as error:
            raise ValueError(
                f"«{nombre_archivo}» no es un archivo DXF válido."
            ) from error
        regenerado = salida.read_bytes()

    return {
        "requerimientos": None,
        "versiones": [_version(resultado, regenerado, "Plano abierto")],
        "mensajes": [
            _mensaje(
                "agente",
                f"Abrí «{nombre_archivo}»: {describir_plano(resultado)}."
                + observaciones_del_plano(resultado)
                + "\n\n" + _invitacion(resultado),
            ),
        ],
    }


def version_actual(proyecto: dict) -> dict:
    return proyecto["versiones"][-1]


def aplicar_edicion(proyecto: dict, texto: str, solicitud) -> None:
    """Aplica la edición al plano actual y añade una versión nueva."""

    actual = version_actual(proyecto)

    with tempfile.TemporaryDirectory() as carpeta:
        entrada = Path(carpeta) / "entrada.dxf"
        salida = Path(carpeta) / "salida.dxf"
        entrada.write_bytes(actual["dxf"])
        if isinstance(actual["resultado"], ResultadoPlanoMultipisos):
            resultado = editar_plano_multipisos(
                actual["resultado"], str(salida), solicitud
            )
        else:
            resultado = editar_plano(str(entrada), str(salida), solicitud)
        dxf = salida.read_bytes()

    lineas = resumen_modificaciones(resultado["modificaciones"])
    numero = len(proyecto["versiones"]) + 1
    cambiados = ambientes_cambiados(actual["resultado"], resultado["plano"])

    proyecto["versiones"].append(
        _version(resultado["plano"], dxf, "; ".join(lineas), cambiados)
    )

    respuesta = f"Listo, versión {numero}:\n" + "\n".join(f"- {l}" for l in lineas)
    if cambiados:
        respuesta += "\n\nLo modificado aparece resaltado en el plano."
    previos = set(_por_piso(actual["resultado"], "avisos"))
    nuevos = [
        a for a in _por_piso(resultado["plano"], "avisos") if a not in previos
    ]
    for aviso in [*resultado["observaciones"], *nuevos]:
        respuesta += f"\n\n⚠️ {aviso}"
    proyecto["mensajes"].append(_mensaje("agente", respuesta))


def registrar_error(proyecto: dict, texto: str, detalle: str | None = None) -> None:
    proyecto["mensajes"].append(_mensaje("error", texto, detalle))


def registrar_usuario(proyecto: dict, texto: str) -> None:
    proyecto["mensajes"].append(_mensaje("usuario", texto))


def deshacer(proyecto: dict) -> bool:
    """Vuelve a la versión anterior; False si ya no hay nada que deshacer."""

    if len(proyecto["versiones"]) < 2:
        return False

    quitada = proyecto["versiones"].pop()
    proyecto["mensajes"].append(
        _mensaje(
            "agente",
            f"Deshice el último cambio ({quitada['etiqueta']}). "
            f"Vuelves a la versión {len(proyecto['versiones'])}.",
        )
    )
    return True
