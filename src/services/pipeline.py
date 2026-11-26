"""
Orquestación del flujo de generación de planos, independiente de la UI.

requerimientos -> optimización -> validación -> geometrías -> muros
-> puertas -> aberturas -> DXF.
"""

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
from src.models.distribucion import validar_esquema_distribucion
from src.planning.layout_optimizer import optimizar_distribucion, optimizar_por_pisos
from src.planning.reglas_acceso import evaluar_reglas, nombres_legibles, tipo_base

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

    ancho = requerimientos.ancho_terreno_m
    largo = requerimientos.largo_terreno_m

    if not ancho or not largo:
        raise ValueError("Faltan las dimensiones del terreno.")

    n_pisos = requerimientos.numero_pisos or 1
    if n_pisos > 1:
        avisar("Optimizando la distribución por pisos...")
        return generar_plano_multipisos(requerimientos, ancho, largo, ruta_dxf, progreso)

    avisar("Optimizando la distribución espacial...")
    distribucion = optimizar_distribucion(requerimientos)

    plano = construir_plano(distribucion, ancho, largo, ruta_dxf, progreso)
    plano.notas = _notas(requerimientos, distribucion)
    return plano


def _notas(requerimientos, distribucion) -> list[str]:
    """Lo que el sistema añadió sin que el usuario lo pidiera."""
    pidio = any(tipo_base(a.nombre) == "pasillo" for a in requerimientos.ambientes)
    hay = any(tipo_base(a["id"]) == "pasillo" for a in distribucion)
    return [NOTA_PASILLO] if hay and not pidio else []


def _avisos(distribucion, puertas, validacion, ventanas, planta_baja=True) -> list[str]:
    avisos = evaluar_reglas(
        distribucion, puertas["puertas"], validacion["adyacencias"], planta_baja
    )
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

    avisar("Construyendo el plano DXF...")
    ruta = Path(ruta_dxf)
    ruta.parent.mkdir(parents=True, exist_ok=True)

    generar_dxf_desde_geometrias(
        resultado_geometrias=geometrias,
        ancho_terreno_m=ancho,
        largo_terreno_m=largo,
        ruta_salida=str(ruta),
        resultado_muros=muros,
        resultado_aberturas=aberturas,
        resultado_mobiliario=mobiliario,
    )

    return ResultadoPlano(
        distribucion=distribucion,
        validacion=validacion,
        geometrias=geometrias,
        muros=muros,
        puertas=puertas,
        aberturas=aberturas,
        ruta_dxf=ruta,
        mobiliario=mobiliario,
        ventanas=ventanas,
        avisos=_avisos(distribucion, puertas, validacion, ventanas),
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
    Optimiza cada piso por separado y genera un único DXF con los pisos
    apilados verticalmente.
    """

    def avisar(mensaje: str):
        if progreso:
            progreso(mensaje)

    distribuciones = optimizar_por_pisos(requerimientos)
    pisos_resultados = []
    pisos_datos_dxf = []

    for i, distribucion in enumerate(distribuciones):
        avisar(f"Construyendo piso {i + 1} de {len(distribuciones)}...")

        validar_esquema_distribucion(distribucion)
        validacion = validar_distribucion(distribucion)
        geometrias = generar_geometrias(distribucion, ancho, largo)

        if not geometrias["valido"]:
            raise ValueError(
                f"Piso {i + 1}: geometría inválida: " + "; ".join(geometrias["errores"])
            )

        muros = generar_muros(
            ambientes_geometricos=geometrias["ambientes"],
            espesor_exterior_m=ESPESOR_EXTERIOR_M,
            espesor_interior_m=ESPESOR_INTERIOR_M,
        )

        puertas = generar_puertas_automaticas(
            distribucion=distribucion,
            ancho_puerta_m=ANCHO_PUERTA_M,
            espesor_muro_m=ESPESOR_INTERIOR_M,
            puerta_exterior=i == 0,
            espesor_exterior_m=ESPESOR_EXTERIOR_M,
        )

        ventanas = generar_ventanas_automaticas(
            geometrias,
            espesor_muro_m=ESPESOR_EXTERIOR_M,
            puertas=puertas,
        )

        aberturas = generar_aberturas(
            resultado_muros=muros,
            aberturas=puertas["puertas"] + ventanas["ventanas"],
        )

        mobiliario = None
        if amueblar:
            mobiliario = amueblar_automaticamente(geometrias, puertas)

        pisos_resultados.append(ResultadoPlano(
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
                distribucion, puertas, validacion, ventanas, planta_baja=i == 0
            ),
            notas=_notas(requerimientos, distribucion),
        ))

        pisos_datos_dxf.append({
            "geometrias": geometrias,
            "resultado_muros": muros,
            "resultado_aberturas": aberturas,
            "resultado_mobiliario": mobiliario,
        })

    avisar("Construyendo el plano DXF multipiso...")
    ruta = Path(ruta_dxf)
    ruta.parent.mkdir(parents=True, exist_ok=True)

    generar_dxf_multipisos(
        pisos=pisos_datos_dxf,
        ancho_terreno_m=ancho,
        largo_terreno_m=largo,
        ruta_salida=str(ruta),
    )

    for plano in pisos_resultados:
        plano.ruta_dxf = ruta

    return ResultadoPlanoMultipisos(
        pisos=pisos_resultados,
        ruta_dxf=ruta,
        numero_pisos=len(distribuciones),
    )


def abrir_plano(
    ruta_entrada,
    ruta_salida,
    progreso: Callable[[str], None] | None = None,
) -> ResultadoPlano:
    """
    Carga un DXF generado por este proyecto y reconstruye su plano completo
    (muros, puertas, ventanas, mobiliario) sin modificar la distribución.
    """

    from src.cad.dxf_editor import (
        cargar_y_editar,
        distribucion_desde_ambientes,
    )

    _, ambientes, terreno, _ = cargar_y_editar(ruta_entrada, None)

    xmin, ymin, xmax, ymax = terreno.bounds

    return construir_plano(
        distribucion_desde_ambientes(ambientes),
        round(xmax - xmin, 3),
        round(ymax - ymin, 3),
        ruta_salida,
        progreso,
    )


def editar_plano(
    ruta_entrada,
    ruta_salida,
    solicitud,
    progreso: Callable[[str], None] | None = None,
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

    _, ambientes, terreno, resultados = cargar_y_editar(entrada, solicitud)

    xmin, ymin, xmax, ymax = terreno.bounds
    distribucion = distribucion_desde_ambientes(ambientes)

    plano = construir_plano(
        distribucion,
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
