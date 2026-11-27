"""
Orquestación del flujo de generación de planos, independiente de la UI.

requerimientos -> optimización -> validación -> geometrías -> muros
-> puertas -> aberturas -> DXF.
"""

import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from src.cad.dxf_generator import generar_dxf_desde_geometrias, generar_dxf_multipisos
from src.geometry.adjacency_validator import validar_distribucion
from src.geometry.door_generator import generar_puertas_automaticas
from src.geometry.geometry_generator import generar_geometrias
from src.geometry.mobiliario_automatico import amueblar_automaticamente
from src.geometry.opening_generator import generar_aberturas
from src.geometry.wall_generator import generar_muros
from src.geometry.window_generator import generar_ventanas_automaticas
from src.models.defaults import estimar_terreno_para_vivienda
from src.models.distribucion import validar_esquema_distribucion
from src.planning.garaje import avisos_de_garaje
from src.planning.orientacion import nota_de_orientacion
from src.planning.retiros import (
    area_edificable,
    nota_de_retiros,
    reducir_al_area_edificable,
    trasladar,
    ubicar,
)
from src.planning.layout_optimizer import (
    contorno,
    optimizar_distribucion,
    optimizar_por_pisos,
)
from src.planning.reglas_acceso import evaluar_reglas, nombres_legibles, tipo_base
from src.planning.space_graph import interpretar_relacion
from src.utils.texto import normalizar_nombre

ESPESOR_EXTERIOR_M = 0.20
ESPESOR_INTERIOR_M = 0.15
ANCHO_PUERTA_M = 0.90

NOTA_PASILLO = (
    "Agregué un pasillo para entrar a dormitorios y baños sin cruzar otros "
    "ambientes."
)


@dataclass
class ResultadoPlano:
    distribucion: list
    validacion: dict
    geometrias: dict
    muros: dict
    puertas: dict
    aberturas: dict
    ruta_dxf: Path
    mobiliario: dict | None = None
    ventanas: dict | None = None
    avisos: list = field(default_factory=list)  # reglas que no se cumplen
    notas: list = field(default_factory=list)  # decisiones tomadas por el sistema


@dataclass
class ResultadoPlanoMultipisos:
    pisos: list          # list[ResultadoPlano], one per floor
    ruta_dxf: Path
    numero_pisos: int


def generar_plano(
    requerimientos,
    ruta_dxf,
    progreso: Callable[[str], None] | None = None,
) -> ResultadoPlano:
    """
    Ejecuta todo el flujo y guarda el DXF en `ruta_dxf`.

    `progreso` es un callback opcional que recibe el nombre de cada etapa.
    Lanza ValueError si los datos o el resultado intermedio no son válidos.
    """

    def avisar(mensaje: str):
        if progreso:
            progreso(mensaje)

    requerimientos = estimar_terreno_para_vivienda(requerimientos)
    ancho = requerimientos.ancho_terreno_m
    largo = requerimientos.largo_terreno_m

    if not ancho or not largo:
        raise ValueError("Faltan las dimensiones del terreno.")

    n_pisos = requerimientos.numero_pisos or 1
    if n_pisos > 1:
        avisar("Optimizando la distribución por pisos...")
        return generar_plano_multipisos(requerimientos, ancho, largo, ruta_dxf, progreso)

    avisar("Optimizando la distribución espacial...")
    (distribucion,) = _resolver_en_el_lote(
        requerimientos, lambda r: [optimizar_distribucion(r)]
    )

    plano = construir_plano(distribucion, ancho, largo, ruta_dxf, progreso)
    plano.notas = _notas(requerimientos, distribucion)
    _anotar_retiros(plano, requerimientos)
    _anotar_orientacion(plano, requerimientos.norte)
    return plano


def _resolver_en_el_lote(requerimientos, resolver) -> list:
    """
    Resuelve las plantas dentro de los retiros y las coloca al frente y
    centradas en el terreno.
    """
    interior = reducir_al_area_edificable(requerimientos)
    try:
        distribuciones = resolver(interior)
    except ValueError as error:
        if not requerimientos.retiros:
            raise
        raise ValueError(
            f"Dentro de los retiros quedan {interior.ancho_terreno_m:g} × "
            f"{interior.largo_terreno_m:g} m. {error}"
        ) from error

    return ubicar(
        distribuciones, requerimientos.ancho_terreno_m,
        requerimientos.largo_terreno_m, requerimientos.retiros,
        centrar=_centrar_en_lote(requerimientos, distribuciones),
    )


def _centrar_en_lote(requerimientos, distribuciones) -> bool:
    """
    La casa va al centro del lote solo si el terreno se calculó (no lo dio el
    usuario) y no hay garaje: el garaje tiene que dar a la calle.
    """
    if not requerimientos.terreno_estimado:
        return False
    return not any(
        tipo_base(a["id"]) == "garaje"
        for distribucion in distribuciones for a in distribucion
    )


def _anotar_retiros(plano, requerimientos) -> None:
    retiros = requerimientos.retiros
    if retiros and any(retiros.model_dump().values()):
        plano.notas.append(nota_de_retiros(
            requerimientos.ancho_terreno_m, requerimientos.largo_terreno_m,
            retiros,
        ))


def _anotar_orientacion(plano, norte) -> None:
    if not norte:
        return
    nota = nota_de_orientacion(
        plano.distribucion, plano.ventanas["ventanas"], norte,
        nombres_legibles(plano.distribucion),
    )
    if nota:
        plano.notas.append(nota)


def _notas(requerimientos, distribucion) -> list[str]:
    """Lo que el sistema añadió sin que el usuario lo pidiera."""
    pidio = any(tipo_base(a.nombre) == "pasillo" for a in requerimientos.ambientes)
    hay = any(tipo_base(a["id"]) == "pasillo" for a in distribucion)
    notas = [NOTA_PASILLO] if hay and not pidio else []
    if requerimientos.ambientes_agregados:
        notas.append(
            "Toda casa básica lleva sala, comedor, cocina, dormitorio y baño: "
            "añadí " + ", ".join(requerimientos.ambientes_agregados) + "."
        )
    return notas


def _avisos(distribucion, puertas, validacion, ventanas, planta_baja=True) -> list[str]:
    avisos = evaluar_reglas(
        distribucion, puertas["puertas"], validacion["adyacencias"], planta_baja
    )
    if planta_baja:
        avisos += avisos_de_garaje(distribucion)
    sin_ventana = [
        i for i in ventanas.get("omitidos", []) if tipo_base(i) != "escalera"
    ]
    if sin_ventana:
        nombres = nombres_legibles(distribucion)
        avisos.append(
            "Sin ventana al exterior: "
            + ", ".join(nombres[i] for i in sin_ventana) + "."
        )
    return avisos


def construir_plano(
    distribucion,
    ancho,
    largo,
    ruta_dxf,
    progreso: Callable[[str], None] | None = None,
    amueblar: bool = True,
) -> ResultadoPlano:
    """
    Genera validación, geometrías, muros, puertas, aberturas y DXF
    a partir de una distribución ya resuelta (del optimizador o editada).
    """

    plano = _construir_piso(
        distribucion, ancho, largo, ruta_dxf, progreso, amueblar
    )

    if progreso:
        progreso("Construyendo el plano DXF...")

    plano.ruta_dxf.parent.mkdir(parents=True, exist_ok=True)

    generar_dxf_desde_geometrias(
        resultado_geometrias=plano.geometrias,
        ancho_terreno_m=ancho,
        largo_terreno_m=largo,
        ruta_salida=str(plano.ruta_dxf),
        resultado_muros=plano.muros,
        resultado_aberturas=plano.aberturas,
        resultado_mobiliario=plano.mobiliario,
    )

    return plano


def _construir_piso(
    distribucion,
    ancho,
    largo,
    ruta_dxf,
    progreso: Callable[[str], None] | None = None,
    amueblar: bool = True,
    planta_baja: bool = True,
) -> ResultadoPlano:
    """Todo lo de una planta salvo escribir el DXF."""

    def avisar(mensaje: str):
        if progreso:
            progreso(mensaje)

    validar_esquema_distribucion(distribucion)

    avisar("Validando las conexiones entre ambientes...")
    validacion = validar_distribucion(distribucion)

    avisar("Generando las geometrías de los ambientes...")
    geometrias = generar_geometrias(distribucion, ancho, largo)

    if not geometrias["valido"]:
        raise ValueError(
            "La geometría contiene errores: " + "; ".join(geometrias["errores"])
        )

    avisar("Generando muros...")
    muros = generar_muros(
        ambientes_geometricos=geometrias["ambientes"],
        espesor_exterior_m=ESPESOR_EXTERIOR_M,
        espesor_interior_m=ESPESOR_INTERIOR_M,
    )

    avisar("Calculando puertas...")
    puertas = generar_puertas_automaticas(
        distribucion=distribucion,
        ancho_puerta_m=ANCHO_PUERTA_M,
        espesor_muro_m=ESPESOR_INTERIOR_M,
        puerta_exterior=planta_baja,
        espesor_exterior_m=ESPESOR_EXTERIOR_M,
    )

    avisar("Colocando ventanas en los muros exteriores...")
    ventanas = generar_ventanas_automaticas(
        geometrias,
        espesor_muro_m=ESPESOR_EXTERIOR_M,
        puertas=puertas,
    )

    avisar("Generando aberturas en los muros...")
    aberturas = generar_aberturas(
        resultado_muros=muros,
        aberturas=puertas["puertas"] + ventanas["ventanas"],
    )

    mobiliario = None

    if amueblar:
        avisar("Colocando el mobiliario...")
        mobiliario = amueblar_automaticamente(geometrias, puertas)

    return ResultadoPlano(
        distribucion=distribucion,
        validacion=validacion,
        geometrias=geometrias,
        muros=muros,
        puertas=puertas,
        aberturas=aberturas,
        ruta_dxf=Path(ruta_dxf),
        mobiliario=mobiliario,
        ventanas=ventanas,
        avisos=_avisos(
            distribucion, puertas, validacion, ventanas, planta_baja
        ),
    )


def generar_plano_multipisos(
    requerimientos,
    ancho,
    largo,
    ruta_dxf,
    progreso: Callable[[str], None] | None = None,
    amueblar: bool = True,
) -> ResultadoPlanoMultipisos:
    """
    Optimiza las plantas (escalera alineada y contorno parecido) y genera un
    único DXF con ellas apiladas verticalmente.
    """

    distribuciones = _resolver_en_el_lote(requerimientos, optimizar_por_pisos)
    resultado = construir_multipisos(
        distribuciones, ancho, largo, ruta_dxf, progreso, amueblar
    )

    for plano in resultado.pisos:
        plano.notas = _notas(requerimientos, plano.distribucion)
        _anotar_orientacion(plano, requerimientos.norte)

    _anotar_retiros(resultado.pisos[0], requerimientos)

    resultado.pisos[0].avisos += _relaciones_entre_plantas(
        requerimientos, distribuciones
    )

    return resultado


def construir_multipisos(
    distribuciones,
    ancho,
    largo,
    ruta_dxf,
    progreso: Callable[[str], None] | None = None,
    amueblar: bool = True,
) -> ResultadoPlanoMultipisos:
    """Planos y DXF conjunto a partir de distribuciones ya resueltas."""

    pisos = []

    for i, distribucion in enumerate(distribuciones):
        if progreso:
            progreso(f"Construyendo piso {i + 1} de {len(distribuciones)}...")

        plano = _construir_piso(
            distribucion, ancho, largo, ruta_dxf,
            amueblar=amueblar, planta_baja=i == 0,
        )
        if i > 0:
            plano.avisos += _avisos_de_planta_alta(
                distribuciones[0], distribucion
            )
        pisos.append(plano)

    if progreso:
        progreso("Construyendo el plano DXF multipiso...")

    ruta = Path(ruta_dxf)
    ruta.parent.mkdir(parents=True, exist_ok=True)

    generar_dxf_multipisos(
        pisos=[
            {
                "geometrias": p.geometrias,
                "resultado_muros": p.muros,
                "resultado_aberturas": p.aberturas,
                "resultado_mobiliario": p.mobiliario,
            }
            for p in pisos
        ],
        ancho_terreno_m=ancho,
        largo_terreno_m=largo,
        ruta_salida=str(ruta),
    )

    return ResultadoPlanoMultipisos(
        pisos=pisos, ruta_dxf=ruta, numero_pisos=len(pisos),
    )


def _avisos_de_planta_alta(baja, alta) -> list[str]:
    """La escalera debe coincidir y la planta alta no debe sobresalir."""
    avisos = []

    def escalera(distribucion):
        return next(
            (
                tuple(round(a[k], 2) for k in ("x", "y", "ancho", "largo"))
                for a in distribucion if tipo_base(a["id"]) == "escalera"
            ),
            None,
        )

    if escalera(baja) != escalera(alta):
        avisos.append("La escalera no coincide con la de la planta baja.")

    bx0, by0, bx1, by1 = contorno(baja)
    ax0, ay0, ax1, ay1 = contorno(alta)
    saliente = max(bx0 - ax0, by0 - ay0, ax1 - bx1, ay1 - by1)

    if saliente > 0.05:
        avisos.append(
            f"La planta alta sobresale {saliente:.1f} m de la planta baja."
        )

    return avisos


def _relaciones_entre_plantas(requerimientos, distribuciones) -> list[str]:
    """Relaciones pedidas entre ambientes que quedaron en plantas distintas."""
    if len(distribuciones) < 2:
        return []

    en_planta = [
        {normalizar_nombre(a["nombre"]) for a in d} for d in distribuciones
    ]
    avisos = []

    for relacion in requerimientos.relaciones_adyacencia:
        a, b, _ = interpretar_relacion(relacion)
        if not any({a, b} <= nombres for nombres in en_planta):
            avisos.append(
                f"No se puede juntar {a} con {b}: quedan en plantas distintas."
            )

    return list(dict.fromkeys(avisos))


def abrir_plano(
    ruta_entrada,
    ruta_salida,
    progreso: Callable[[str], None] | None = None,
) -> ResultadoPlano | ResultadoPlanoMultipisos:
    """
    Carga un DXF generado por este proyecto (una o dos plantas) y reconstruye
    su plano completo (muros, puertas, ventanas, mobiliario) sin modificar la
    distribución.
    """

    from src.cad.dxf_editor import leer_plantas, tiene_metadatos
    from src.cad.importador_dxf import importar_documento, leer_dxf

    documento = leer_dxf(ruta_entrada)

    if tiene_metadatos(documento):
        distribuciones, ancho, largo = leer_plantas(ruta_entrada)
        notas = []
    else:
        # Dibujado con otro programa: se deducen las habitaciones.
        distribuciones, ancho, largo, notas = importar_documento(documento)

    if len(distribuciones) > 1:
        plano = construir_multipisos(
            distribuciones, ancho, largo, ruta_salida, progreso
        )
        plano.pisos[0].notas = notas
    else:
        plano = construir_plano(
            distribuciones[0], ancho, largo, ruta_salida, progreso
        )
        plano.notas = notas

    return plano


def editar_plano(
    ruta_entrada,
    ruta_salida,
    solicitud,
    progreso: Callable[[str], None] | None = None,
    norte: str | None = None,
    retiros=None,
) -> dict:
    """
    Aplica la edición sobre la distribución del DXF y regenera el plano
    completo (muros, puertas, aberturas) para que quede coherente.

    Devuelve las claves de `editar_dxf` más `plano` (ResultadoPlano).
    """

    from src.cad.dxf_editor import (
        cargar_y_editar,
        distribucion_desde_ambientes,
    )

    entrada = Path(ruta_entrada)
    salida = Path(ruta_salida)

    if entrada.exists() and entrada.resolve() == salida.resolve():
        raise ValueError(
            "El archivo de salida debe ser diferente del archivo original."
        )

    if retiros and any(retiros.model_dump().values()):
        ambientes, terreno, resultados = _editar_dentro_de_retiros(
            entrada, solicitud, norte, retiros
        )
    else:
        _, ambientes, terreno, resultados = cargar_y_editar(
            entrada, solicitud, {"norte": norte}
        )
        ambientes = distribucion_desde_ambientes(ambientes)

    xmin, ymin, xmax, ymax = terreno.bounds
    plano = construir_plano(
        ambientes,
        round(xmax - xmin, 3),
        round(ymax - ymin, 3),
        salida,
        progreso,
    )

    observaciones = list(solicitud.observaciones)

    if not plano.validacion["distribucion_conectada"]:
        observaciones.append(
            "Tras la edición hay ambientes sin pared compartida con el "
            "resto, por lo que no tienen puerta. Prueba a moverlos junto "
            "a otro ambiente."
        )

    return {
        "archivo": str(salida),
        "modificaciones": resultados,
        "observaciones": observaciones,
        "plano": plano,
    }


def _editar_dentro_de_retiros(entrada, solicitud, norte, retiros):
    """
    Edita sobre un terreno recortado a los retiros, para que ningún cambio
    los invada. Devuelve (distribución, terreno completo, resultados).
    """
    from src.cad.dxf_editor import (
        cargar_y_editar,
        distribucion_desde_ambientes,
    )

    _, originales, terreno, _ = cargar_y_editar(entrada, None)
    xmin, ymin, xmax, ymax = terreno.bounds
    ancho, largo = area_edificable(
        round(xmax - xmin, 3), round(ymax - ymin, 3), retiros
    )
    dentro = trasladar(
        distribucion_desde_ambientes(originales),
        -retiros.izquierdo, -retiros.frontal,
    )

    with tempfile.TemporaryDirectory() as carpeta:
        ruta = Path(carpeta) / "edificable.dxf"
        generar_dxf_desde_geometrias(
            generar_geometrias(dentro, ancho, largo), ancho, largo, str(ruta)
        )
        _, ambientes, _, resultados = cargar_y_editar(
            ruta, solicitud, {"norte": norte}
        )
        editada = distribucion_desde_ambientes(ambientes)

    return (
        trasladar(editada, retiros.izquierdo, retiros.frontal),
        terreno,
        resultados,
    )


# ==========================================
# EXPORTACIÓN CSV DEL CUADRO DE ÁREAS
# ==========================================

def _filas_areas(resultado) -> list[dict]:
    """Extrae las filas del cuadro de áreas de un ResultadoPlano o ResultadoPlanoMultipisos."""
    if isinstance(resultado, ResultadoPlanoMultipisos):
        filas = []
        for i, plano in enumerate(resultado.pisos):
            label = f"PLANTA BAJA" if i == 0 else f"PLANTA ALTA {i}"
            for amb in plano.geometrias["ambientes"]:
                xmin, ymin, xmax, ymax = amb["poligono"].bounds
                filas.append({
                    "piso": label,
                    "ambiente": amb["nombre"],
                    "area_m2": round(amb.get("area_m2", amb["poligono"].area), 2),
                    "ancho_m": round(xmax - xmin, 2),
                    "largo_m": round(ymax - ymin, 2),
                })
        return filas
    # ResultadoPlano
    filas = []
    for amb in resultado.geometrias["ambientes"]:
        xmin, ymin, xmax, ymax = amb["poligono"].bounds
        filas.append({
            "piso": "PLANTA ÚNICA",
            "ambiente": amb["nombre"],
            "area_m2": round(amb.get("area_m2", amb["poligono"].area), 2),
            "ancho_m": round(xmax - xmin, 2),
            "largo_m": round(ymax - ymin, 2),
        })
    return filas


def generar_csv_areas(resultado) -> str:
    """Devuelve el cuadro de áreas como texto CSV (separado por comas)."""
    import csv
    import io

    campos = ["piso", "ambiente", "area_m2", "ancho_m", "largo_m"]
    filas = _filas_areas(resultado)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=campos)
    writer.writeheader()
    writer.writerows(filas)
    return buf.getvalue()


def exportar_csv_areas(resultado, ruta_csv) -> Path:
    """Escribe el cuadro de áreas en un archivo CSV y devuelve su Path."""
    ruta = Path(ruta_csv)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(generar_csv_areas(resultado), encoding="utf-8")
    return ruta
