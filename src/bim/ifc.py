"""
Exportación del plano a IFC4 (BIM) con IfcOpenShell. Función pura: no
depende de Streamlit.

Proyecto → sitio → edificio → una planta por piso, con espacios, muros
(exteriores e interiores por tramos rectos), aberturas con puertas y
ventanas, losa de piso y mobiliario (sanitarios como IfcSanitaryTerminal).
"""

import math

import numpy as np
import ifcopenshell
import ifcopenshell.api
from shapely.geometry import LineString, Point, box
from shapely.ops import unary_union

from src.planning.reglas_acceso import EXTERIOR, tipo_base
from src.services.pipeline import (
    ESPESOR_EXTERIOR_M,
    ESPESOR_INTERIOR_M,
    ResultadoPlanoMultipisos,
)
from src.ui.escena_3d import (
    ALTURA_MURO,
    ALTURA_PUERTA,
    ALTURA_VENTANA,
    _antepecho,
    piezas_de_mueble,
)
from src.ui.plano_svg import etiquetas_ambientes

ALTURA_ENTREPISO = 2.80
ESPESOR_LOSA = 0.15
TOLERANCIA = 1e-6

SANITARIOS = {
    "inodoro": "TOILETPAN",
    "lavatorio": "WASHHANDBASIN",
    "ducha": "SHOWER",
    "tina": "BATH",
}


def _api(modelo, nombre, **kwargs):
    return ifcopenshell.api.run(nombre, modelo, **kwargs)


def _colocacion(x, y, z=0.0, angulo=0.0):
    """Matriz 4x4: traslación y giro alrededor del eje Z."""
    c, s = math.cos(angulo), math.sin(angulo)
    matriz = np.eye(4)
    matriz[:3, :3] = [[c, -s, 0], [s, c, 0], [0, 0, 1]]
    matriz[:3, 3] = (x, y, z)
    return matriz


def _colocar(modelo, producto, matriz):
    _api(modelo, "geometry.edit_object_placement", product=producto, matrix=matriz)


# ------------------------------------------------------------
# Tramos de muro
# ------------------------------------------------------------

def _fusionar(segmentos):
    """Une tramos colineales contiguos. Devuelve [(orientación, valor, lo, hi)]."""
    por_recta = {}
    for (x1, y1), (x2, y2) in segmentos:
        if abs(y1 - y2) < TOLERANCIA:
            clave, lo, hi = ("h", round(y1, 4)), *sorted((x1, x2))
        elif abs(x1 - x2) < TOLERANCIA:
            clave, lo, hi = ("v", round(x1, 4)), *sorted((y1, y2))
        else:
            continue  # el plano solo tiene ambientes rectangulares
        por_recta.setdefault(clave, []).append((lo, hi))

    tramos = []
    for (orientacion, valor), intervalos in sorted(por_recta.items()):
        intervalos.sort()
        actual = list(intervalos[0])
        for lo, hi in intervalos[1:]:
            if lo <= actual[1] + 1e-4:
                actual[1] = max(actual[1], hi)
            else:
                tramos.append((orientacion, valor, *actual))
                actual = [lo, hi]
        tramos.append((orientacion, valor, *actual))
    return tramos


def tramos_de_muro(ambientes):
    """
    Tramos rectos de muro de una planta: {"exterior": [...], "interior": [...]},
    cada uno como (orientación, valor, inicio, fin) en metros.
    """
    poligonos = [a["poligono"] for a in ambientes]
    contorno = unary_union(poligonos).boundary
    lineas = unary_union([p.exterior for p in poligonos])

    clases = {"exterior": [], "interior": []}
    for linea in getattr(lineas, "geoms", [lineas]):
        puntos = list(linea.coords)
        for a, b in zip(puntos, puntos[1:]):
            medio = Point((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            clase = "exterior" if contorno.distance(medio) < 1e-6 else "interior"
            clases[clase].append((a, b))

    return {clase: _fusionar(segs) for clase, segs in clases.items()}


def _eje(tramo):
    orientacion, valor, lo, hi = tramo
    if orientacion == "h":
        return (lo, valor), (hi, valor)
    return (valor, lo), (valor, hi)


# ------------------------------------------------------------
# Exportación
# ------------------------------------------------------------

class _Exportador:

    def __init__(self):
        self.modelo = ifcopenshell.api.run("project.create_file", version="IFC4")
        m = self.modelo
        self.proyecto = _api(m, "root.create_entity", ifc_class="IfcProject",
                             name="Agente Arquitectónico")
        _api(m, "unit.assign_unit", length={"is_metric": True, "raw": "METERS"})
        contexto = _api(m, "context.add_context", context_type="Model")
        self.cuerpo = _api(m, "context.add_context", context_type="Model",
                           context_identifier="Body", target_view="MODEL_VIEW",
                           parent=contexto)
        self.sitio = _api(m, "root.create_entity", ifc_class="IfcSite", name="Terreno")
        self.edificio = _api(m, "root.create_entity", ifc_class="IfcBuilding",
                             name="Vivienda")
        _api(m, "aggregate.assign_object", products=[self.sitio], relating_object=self.proyecto)
        _api(m, "aggregate.assign_object", products=[self.edificio], relating_object=self.sitio)

    # -- utilidades ------------------------------------------------

    def _entidad(self, clase, nombre, planta, **atributos):
        entidad = _api(self.modelo, "root.create_entity", ifc_class=clase, name=nombre)
        for clave, valor in atributos.items():
            setattr(entidad, clave, valor)
        _api(self.modelo, "spatial.assign_container", products=[entidad],
             relating_structure=planta)
        return entidad

    def _prisma(self, entidad, puntos, alto, matriz):
        """Extrusión vertical de un polígono (coordenadas locales)."""
        representacion = _api(
            self.modelo, "geometry.add_slab_representation",
            context=self.cuerpo, depth=alto, polyline=[tuple(p) for p in puntos],
        )
        _api(self.modelo, "geometry.assign_representation", product=entidad,
             representation=representacion)
        _colocar(self.modelo, entidad, matriz)

    def _caja(self, entidad, x0, y0, x1, y1, z0, z1):
        self._prisma(
            entidad, [(0, 0), (x1 - x0, 0), (x1 - x0, y1 - y0), (0, y1 - y0)],
            z1 - z0, _colocacion(x0, y0, z0),
        )

    # -- planta -------------------------------------------------------

    def planta(self, piso, indice, nombre):
        m = self.modelo
        cota = indice * ALTURA_ENTREPISO
        planta = _api(m, "root.create_entity", ifc_class="IfcBuildingStorey", name=nombre)
        planta.Elevation = cota
        _api(m, "aggregate.assign_object", products=[planta], relating_object=self.edificio)
        _colocar(m, planta, _colocacion(0, 0, cota))

        ambientes = piso.geometrias["ambientes"]
        self._espacios(piso, ambientes, planta, cota)
        muros = self._muros(ambientes, planta, cota)
        self._aberturas(piso, ambientes, muros, planta, cota)
        self._losa(ambientes, planta, cota)
        self._mobiliario(piso, ambientes, planta, cota)

    def _espacios(self, piso, ambientes, planta, cota):
        m = self.modelo
        etiquetas = etiquetas_ambientes(piso.distribucion)
        for ambiente in ambientes:
            x0, y0, x1, y1 = ambiente["poligono"].bounds
            espacio = _api(m, "root.create_entity", ifc_class="IfcSpace",
                           name=etiquetas.get(ambiente["id"], ambiente["nombre"]))
            espacio.LongName = str(ambiente["nombre"]).capitalize()
            _api(m, "aggregate.assign_object", products=[espacio], relating_object=planta)
            self._caja(espacio, x0, y0, x1, y1, cota, cota + ALTURA_MURO)
            qto = _api(m, "pset.add_qto", product=espacio, name="Qto_SpaceBaseQuantities")
            _api(m, "pset.edit_qto", qto=qto, properties={
                "NetFloorArea": round(ambiente["poligono"].area, 3),
                "Height": ALTURA_MURO,
            })

    def _muros(self, ambientes, planta, cota):
        muros = []
        tramos = tramos_de_muro(ambientes)
        for clase, espesor in (("exterior", ESPESOR_EXTERIOR_M),
                               ("interior", ESPESOR_INTERIOR_M)):
            for i, tramo in enumerate(tramos[clase], start=1):
                (ax, ay), (bx, by) = _eje(tramo)
                largo = math.hypot(bx - ax, by - ay)
                angulo = math.atan2(by - ay, bx - ax)
                muro = self._entidad(
                    "IfcWall", f"Muro {clase} {i}", planta,
                    PredefinedType="SOLIDWALL",
                )
                # Se alarga medio espesor por cada extremo para cerrar esquinas.
                extra = espesor / 2
                representacion = _api(
                    self.modelo, "geometry.add_wall_representation",
                    context=self.cuerpo, length=largo + 2 * extra,
                    height=ALTURA_MURO, thickness=espesor, offset=-espesor / 2,
                )
                _api(self.modelo, "geometry.assign_representation",
                     product=muro, representation=representacion)
                c, s = math.cos(angulo), math.sin(angulo)
                _colocar(self.modelo, muro,
                         _colocacion(ax - c * extra, ay - s * extra, cota, angulo))
                pset = _api(self.modelo, "pset.add_pset", product=muro, name="Pset_WallCommon")
                _api(self.modelo, "pset.edit_pset", pset=pset,
                     properties={"IsExternal": clase == "exterior"})
                muros.append({"muro": muro, "tramo": tramo, "espesor": espesor,
                              "exterior": clase == "exterior"})
        return muros

    def _anfitrion(self, muros, abertura):
        cx, cy = abertura["centro"]
        orientacion = "h" if abertura["orientacion"] == "horizontal" else "v"
        valor, posicion = (cy, cx) if orientacion == "h" else (cx, cy)
        candidatos = [
            m for m in muros
            if m["tramo"][0] == orientacion
            and abs(m["tramo"][1] - valor) < 1e-3
            and m["tramo"][2] - 1e-3 <= posicion <= m["tramo"][3] + 1e-3
        ]
        return candidatos[0] if candidatos else None

    def _aberturas(self, piso, ambientes, muros, planta, cota):
        m = self.modelo
        puertas = (piso.puertas or {}).get("puertas", [])
        ventanas = (piso.ventanas or {}).get("ventanas", [])
        for numero, (tipo, abertura) in enumerate(
            [("puerta", p) for p in puertas] + [("ventana", v) for v in ventanas], 1
        ):
            anfitrion = self._anfitrion(muros, abertura)
            if anfitrion is None:
                continue
            espesor = anfitrion["espesor"]
            ancho = abertura["ancho"]
            if tipo == "puerta":
                z0, alto = 0.0, ALTURA_PUERTA
            else:
                z0 = _antepecho(abertura)
                alto = ALTURA_VENTANA - z0

            cx, cy = abertura["centro"]
            horizontal = abertura["orientacion"] == "horizontal"
            angulo = 0.0 if horizontal else math.pi / 2
            # Origen en el extremo inicial del vano, sobre el eje del muro.
            ox, oy = (cx - ancho / 2, cy) if horizontal else (cx, cy - ancho / 2)

            hueco = _api(m, "root.create_entity", ifc_class="IfcOpeningElement",
                         name=f"Vano {numero}")
            representacion = _api(
                m, "geometry.add_wall_representation", context=self.cuerpo,
                length=ancho, height=alto, thickness=espesor + 0.1,
                offset=-(espesor + 0.1) / 2,
            )
            _api(m, "geometry.assign_representation", product=hueco,
                 representation=representacion)
            _colocar(m, hueco, _colocacion(ox, oy, cota + z0, angulo))
            _api(m, "feature.add_feature", feature=hueco, element=anfitrion["muro"])

            # La carpintería se apoya en la cara del muro (su eje local Y
            # va de 0 hacia el lado positivo).
            c, s = math.cos(angulo), math.sin(angulo)
            fx, fy = ox + s * espesor / 2, oy - c * espesor / 2
            if tipo == "puerta":
                exterior = abertura.get("ambiente_b") == EXTERIOR
                elemento = self._entidad("IfcDoor", f"Puerta {numero}", planta,
                                         PredefinedType="DOOR")
                elemento.OverallWidth, elemento.OverallHeight = ancho, alto
                rep = _api(m, "geometry.add_door_representation", context=self.cuerpo,
                           overall_width=ancho, overall_height=alto,
                           lining_properties={"LiningDepth": espesor})
                pset = _api(m, "pset.add_pset", product=elemento, name="Pset_DoorCommon")
                _api(m, "pset.edit_pset", pset=pset, properties={"IsExternal": exterior})
            else:
                elemento = self._entidad("IfcWindow", f"Ventana {numero}", planta,
                                         PredefinedType="WINDOW")
                elemento.OverallWidth, elemento.OverallHeight = ancho, alto
                rep = _api(m, "geometry.add_window_representation", context=self.cuerpo,
                           overall_width=ancho, overall_height=alto,
                           lining_properties={"LiningDepth": espesor})
                pset = _api(m, "pset.add_pset", product=elemento, name="Pset_WindowCommon")
                _api(m, "pset.edit_pset", pset=pset,
                     properties={"IsExternal": anfitrion["exterior"]})
            _api(m, "geometry.assign_representation", product=elemento, representation=rep)
            _colocar(m, elemento, _colocacion(fx, fy, cota + z0, angulo))
            _api(m, "feature.add_filling", opening=hueco, element=elemento)

    def _losa(self, ambientes, planta, cota):
        union = unary_union([a["poligono"] for a in ambientes])
        for i, parte in enumerate(getattr(union, "geoms", [union]), start=1):
            losa = self._entidad("IfcSlab", f"Losa de piso {i}", planta,
                                 PredefinedType="FLOOR")
            puntos = [(x, y) for x, y in list(parte.exterior.coords)[:-1]]
            self._prisma(losa, puntos, ESPESOR_LOSA,
                         _colocacion(0, 0, cota - ESPESOR_LOSA))

    def _mobiliario(self, piso, ambientes, planta, cota):
        for mueble in (piso.mobiliario or {}).get("mobiliario", []):
            piezas = piezas_de_mueble(mueble, ambientes)
            alto = max((p["h1"] for p in piezas), default=0.75)
            tipo = mueble["tipo"]
            if tipo == "auto":  # no es parte del edificio
                continue
            nombre = tipo.replace("_", " ").capitalize()
            if tipo in SANITARIOS:
                entidad = self._entidad("IfcSanitaryTerminal", nombre, planta,
                                        PredefinedType=SANITARIOS[tipo])
            else:
                entidad = self._entidad("IfcFurniture", nombre, planta)
            x0, y0 = mueble["x"], mueble["y"]
            self._caja(entidad, x0, y0, x0 + mueble["ancho"], y0 + mueble["largo"],
                       cota, cota + alto)


def nombres_de_plantas(cantidad: int) -> list[str]:
    return ["Planta baja"] + [f"Planta alta {i}" for i in range(1, cantidad)]


def generar_ifc(resultado) -> bytes:
    """Archivo IFC4 (texto STEP en UTF-8) de un plano de una o varias plantas."""
    pisos = (
        list(resultado.pisos)
        if isinstance(resultado, ResultadoPlanoMultipisos)
        else [resultado]
    )
    exportador = _Exportador()
    for indice, (piso, nombre) in enumerate(zip(pisos, nombres_de_plantas(len(pisos)))):
        exportador.planta(piso, indice, nombre)
    return exportador.modelo.to_string().encode("utf-8")
