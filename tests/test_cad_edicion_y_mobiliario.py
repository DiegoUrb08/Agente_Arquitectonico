import ezdxf
import pytest

from src.ai.edit_interpreter import EditOperation, EditRequest
from src.cad.dxf_editor import editar_dxf, obtener_ambientes
from src.cad.dxf_generator import generar_dxf_desde_geometrias
from src.cad.dxf_reader import analizar_dxf
from src.geometry.furniture_generator import (
    construir_mobiliario,
    generar_mobiliario,
    obtener_dimensiones,
)
from src.geometry.geometry_generator import generar_geometrias


@pytest.fixture
def geometrias(distribucion_simple):
    return generar_geometrias(distribucion_simple, 10, 10)


@pytest.fixture
def dxf_base(geometrias, tmp_path):
    ruta = tmp_path / "base.dxf"
    generar_dxf_desde_geometrias(geometrias, 10, 10, str(ruta))
    return ruta


def _solicitud(ambiente, area):
    return EditRequest(operaciones=[
        EditOperation(tipo="modificar_area", ambiente=ambiente, area_objetivo=area)
    ])


# ---------------- mobiliario ----------------

def test_dimensiones_y_tipo_desconocido():
    assert obtener_dimensiones("Sofa") == (2.00, 0.90)
    with pytest.raises(ValueError):
        obtener_dimensiones("nave_espacial")


def test_construir_mobiliario_usa_dimensiones_por_defecto():
    m = construir_mobiliario({"tipo": "sofa", "ambiente": "Sala", "x": 1, "y": 1})
    assert (m["ancho"], m["largo"]) == (2.0, 0.9)
    assert m["geometria"].area == pytest.approx(1.8)


def test_generar_mobiliario_acepta_y_rechaza(geometrias):
    r = generar_mobiliario(geometrias, [
        {"tipo": "sofa", "ambiente": "Sala", "x": 0.5, "y": 0.5},
        {"tipo": "sofa", "ambiente": "Sala", "x": 4.5, "y": 0.5},  # se sale
        {"tipo": "cocina", "ambiente": "Baño", "x": 0, "y": 0},   # no existe
    ])
    assert r["cantidad"] == 1
    assert len(r["errores"]) == 2


def test_dxf_con_mobiliario(geometrias, tmp_path):
    mob = generar_mobiliario(geometrias, [
        {"tipo": "sofa", "ambiente": "Sala", "x": 0.5, "y": 0.5},
        {"tipo": "cama_matrimonial", "ambiente": "Sala", "x": 2.5, "y": 1.5},
    ])
    ruta = tmp_path / "mob.dxf"
    generar_dxf_desde_geometrias(
        geometrias, 10, 10, str(ruta), resultado_mobiliario=mob
    )
    assert "MOBILIARIO" in analizar_dxf(ruta.read_bytes())["capas"]


# ---------------- reader ----------------

def test_analizar_dxf_acepta_ruta_y_bytes(dxf_base):
    por_ruta = analizar_dxf(str(dxf_base))
    por_bytes = analizar_dxf(dxf_base.read_bytes())
    assert por_ruta == por_bytes
    assert por_ruta["total_entidades"] > 0


def test_analizar_dxf_ruta_inexistente(tmp_path):
    with pytest.raises(FileNotFoundError):
        analizar_dxf(tmp_path / "no_existe.dxf")


# ---------------- editor (contrato con el generador) ----------------

def test_generador_deja_metadatos_que_el_editor_lee(dxf_base):
    doc = ezdxf.readfile(str(dxf_base))
    nombres = {a["nombre"] for a in obtener_ambientes(doc.modelspace())}
    assert nombres == {"Sala", "Cocina"}


def test_editar_area_ida_y_vuelta(dxf_base, tmp_path):
    salida = tmp_path / "editado.dxf"
    r = editar_dxf(str(dxf_base), str(salida), _solicitud("sala", 16))

    assert r["modificaciones"][0]["area_anterior"] == 20.0
    assert r["modificaciones"][0]["area_nueva"] == pytest.approx(16.0)

    doc = ezdxf.readfile(str(salida))
    etiquetas = [t.dxf.text for t in doc.modelspace().query("TEXT")]
    assert "16.00 m2" in etiquetas
    assert "20.00 m2" not in etiquetas
    sala = next(a for a in obtener_ambientes(doc.modelspace()) if a["nombre"] == "Sala")
    assert sala["poligono"].area == pytest.approx(16.0)


def test_editar_rechaza_area_que_no_cabe_en_el_terreno(dxf_base, tmp_path):
    with pytest.raises(ValueError, match="reacomodar"):
        editar_dxf(str(dxf_base), str(tmp_path / "x.dxf"), _solicitud("sala", 95))


def test_ampliar_sin_hueco_reacomoda_al_vecino(dxf_base, tmp_path):
    salida = tmp_path / "editado.dxf"
    r = editar_dxf(str(dxf_base), str(salida), _solicitud("sala", 60))

    assert r["modificaciones"][0]["area_nueva"] == pytest.approx(60, rel=0.04)

    doc = ezdxf.readfile(str(salida))
    ambientes = obtener_ambientes(doc.modelspace())
    sala, cocina = (a["poligono"] for a in ambientes)
    assert sala.intersection(cocina).area == pytest.approx(0, abs=1e-6)
    assert sala.boundary.intersection(cocina.boundary).length >= 1.2
    assert cocina.area >= 12 * 0.85 - 0.05


def test_editar_ambiente_inexistente_y_archivo_inexistente(dxf_base, tmp_path):
    with pytest.raises(ValueError, match="No se encontro"):
        editar_dxf(str(dxf_base), str(tmp_path / "x.dxf"), _solicitud("garaje", 10))
    with pytest.raises(FileNotFoundError):
        editar_dxf(str(tmp_path / "no.dxf"), str(tmp_path / "x.dxf"), _solicitud("sala", 10))


def test_editar_no_permite_sobrescribir_el_original(dxf_base):
    with pytest.raises(ValueError):
        editar_dxf(str(dxf_base), str(dxf_base), _solicitud("sala", 16))
