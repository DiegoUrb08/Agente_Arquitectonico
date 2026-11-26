"""Exportación BIM a IFC4."""

import numpy as np
import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.element as util_elemento
import ifcopenshell.util.unit as util_unidad
import ifcopenshell.validate
import pytest
from shapely.geometry import box
from shapely.ops import unary_union

from src.bim.ifc import ALTURA_ENTREPISO, generar_ifc, tramos_de_muro
from src.services.pipeline import (
    ESPESOR_EXTERIOR_M,
    ESPESOR_INTERIOR_M,
    ResultadoPlanoMultipisos,
)
from tests.plano_fijo import DISTRIBUCION_FIJA, generar_plano_fijo

AJUSTES = ifcopenshell.geom.settings()
AJUSTES.set("use-world-coords", True)


def _abrir(datos, carpeta):
    ruta = carpeta / "modelo.ifc"
    ruta.write_bytes(datos)
    return ifcopenshell.open(str(ruta))


@pytest.fixture(scope="module")
def plano(tmp_path_factory):
    return generar_plano_fijo(None, tmp_path_factory.mktemp("ifc") / "p.dxf")


@pytest.fixture(scope="module")
def modelo(plano, tmp_path_factory):
    return _abrir(generar_ifc(plano), tmp_path_factory.mktemp("ifc"))


def _caja(elemento):
    vertices = np.array(
        ifcopenshell.geom.create_shape(AJUSTES, elemento).geometry.verts
    ).reshape(-1, 3)
    return vertices.min(0), vertices.max(0)


def test_ifc4_en_metros_con_una_planta(modelo):
    assert modelo.schema == "IFC4"
    assert util_unidad.calculate_unit_scale(modelo) == 1.0
    plantas = modelo.by_type("IfcBuildingStorey")
    assert [p.Name for p in plantas] == ["Planta baja"]
    assert len(modelo.by_type("IfcProject")) == 1


def test_el_archivo_es_valido(modelo):
    registro = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(modelo, registro, express_rules=True)
    assert registro.statements == []


def test_un_espacio_por_ambiente_con_su_area(modelo, plano):
    espacios = {e.Name: e for e in modelo.by_type("IfcSpace")}

    assert set(espacios) == {"Sala", "Cocina", "Dormitorio 1", "Baño", "Dormitorio 2"}
    for ambiente in plano.geometrias["ambientes"]:
        if ambiente["id"] != "dormitorio_2":
            continue
        cantidades = util_elemento.get_psets(espacios["Dormitorio 2"])
        assert cantidades["Qto_SpaceBaseQuantities"]["NetFloorArea"] == pytest.approx(
            ambiente["poligono"].area
        )


def test_tramos_exteriores_e_interiores(plano):
    tramos = tramos_de_muro(plano.geometrias["ambientes"])
    largo = sum(t[3] - t[2] for t in tramos["exterior"])

    contorno = unary_union([
        box(a["x"], a["y"], a["x"] + a["ancho"], a["y"] + a["largo"])
        for a in DISTRIBUCION_FIJA
    ]).length
    assert largo == pytest.approx(contorno)
    # Muro entre sala y cocina (x = 5), de y = 0 a 4.
    assert ("v", 5.0, 0.0, 4.0) in tramos["interior"]


def test_muros_con_el_espesor_de_su_clase(modelo):
    for muro in modelo.by_type("IfcWall"):
        exterior = util_elemento.get_psets(muro)["Pset_WallCommon"]["IsExternal"]
        minimo, maximo = _caja(muro)
        espesor = min(maximo[0] - minimo[0], maximo[1] - minimo[1])
        esperado = ESPESOR_EXTERIOR_M if exterior else ESPESOR_INTERIOR_M
        assert espesor == pytest.approx(esperado, abs=1e-3), muro.Name
        assert maximo[2] - minimo[2] == pytest.approx(2.6)


def test_los_muros_cubren_los_del_plano(modelo, plano):
    huellas = []
    for muro in modelo.by_type("IfcWall"):
        (x0, y0, _), (x1, y1, _) = _caja(muro)
        huellas.append(box(x0, y0, x1, y1))
    muros_plano = plano.muros["todos_los_muros"]

    assert unary_union(huellas).intersection(muros_plano).area == pytest.approx(
        muros_plano.area, rel=0.01
    )


def test_puertas_y_ventanas_rellenan_un_vano_de_muro(modelo, plano):
    puertas = modelo.by_type("IfcDoor")
    ventanas = modelo.by_type("IfcWindow")

    assert len(puertas) == len(plano.puertas["puertas"])
    assert len(ventanas) == len(plano.ventanas["ventanas"])
    for elemento in puertas + ventanas:
        (relleno,) = elemento.FillsVoids
        vano = relleno.RelatingOpeningElement
        assert vano.VoidsElements[0].RelatingBuildingElement.is_a("IfcWall")
        (a0, a1), (b0, b1) = _caja(vano), _caja(elemento)
        assert np.all(b0 >= a0 - 0.06) and np.all(b1 <= a1 + 0.06), elemento.Name
        # Y lo llena: mismo ancho y alto que el vano (no una pieza diminuta).
        tamano, hueco = b1 - b0, a1 - a0
        assert max(tamano[:2]) == pytest.approx(max(hueco[:2]), abs=0.06), elemento.Name
        assert tamano[2] == pytest.approx(hueco[2], abs=0.06), elemento.Name


def test_solo_la_puerta_de_entrada_es_exterior(modelo):
    exteriores = [
        p for p in modelo.by_type("IfcDoor")
        if util_elemento.get_psets(p)["Pset_DoorCommon"]["IsExternal"]
    ]
    (entrada,) = exteriores
    (_, y0, _), _ = _caja(entrada)
    assert y0 < 0.05, "la entrada está en el frente (y = 0)"


def test_sanitarios_muebles_y_losa(modelo, plano):
    sanitarios = {s.PredefinedType for s in modelo.by_type("IfcSanitaryTerminal")}
    assert {"TOILETPAN", "WASHHANDBASIN", "SHOWER"} <= sanitarios
    muebles = len(modelo.by_type("IfcFurniture")) + len(modelo.by_type("IfcSanitaryTerminal"))
    assert muebles == len(plano.mobiliario["mobiliario"])
    (losa,) = modelo.by_type("IfcSlab")
    (_, _, z0), (_, _, z1) = _caja(losa)
    assert (z0, z1) == (pytest.approx(-0.15), pytest.approx(0))


def test_todo_esta_en_su_planta(modelo):
    planta = modelo.by_type("IfcBuildingStorey")[0]
    contenidos = {e for rel in planta.ContainsElements for e in rel.RelatedElements}
    espacios = {e for rel in planta.IsDecomposedBy for e in rel.RelatedObjects}

    for clase in ("IfcWall", "IfcDoor", "IfcWindow", "IfcSlab", "IfcFurniture"):
        assert set(modelo.by_type(clase)) <= contenidos, clase
    assert set(modelo.by_type("IfcSpace")) == espacios


def test_dos_plantas_apiladas(plano, tmp_path):
    multipisos = ResultadoPlanoMultipisos(pisos=[plano, plano], ruta_dxf=plano.ruta_dxf,
                                          numero_pisos=2)

    modelo = _abrir(generar_ifc(multipisos), tmp_path)

    plantas = modelo.by_type("IfcBuildingStorey")
    assert [(p.Name, p.Elevation) for p in plantas] == [
        ("Planta baja", 0.0), ("Planta alta 1", ALTURA_ENTREPISO),
    ]
    alta = plantas[1]
    espacios = [e for rel in alta.IsDecomposedBy for e in rel.RelatedObjects]
    (_, _, z0), _ = _caja(espacios[0])
    assert z0 == pytest.approx(ALTURA_ENTREPISO)
    exteriores = [
        p for p in modelo.by_type("IfcDoor")
        if util_elemento.get_psets(p)["Pset_DoorCommon"]["IsExternal"]
    ]
    assert len(exteriores) == 2  # el plano fijo se repite tal cual en cada planta
