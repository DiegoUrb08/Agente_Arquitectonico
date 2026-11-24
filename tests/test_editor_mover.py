import ezdxf
import pytest

from src.ai.edit_interpreter import EditOperation, EditRequest
from src.cad.dxf_editor import editar_dxf, obtener_ambientes, resolver_ambiente
from src.cad.dxf_generator import generar_dxf_desde_geometrias
from src.geometry.geometry_generator import generar_geometrias

DISTRIBUCION = [
    {"id": "sala_1", "nombre": "Sala", "x": 0, "y": 0, "ancho": 5, "largo": 4},
    {"id": "cocina_1", "nombre": "Cocina", "x": 5, "y": 0, "ancho": 3, "largo": 4},
    {"id": "dormitorio_1", "nombre": "Dormitorio", "x": 0, "y": 6, "ancho": 4, "largo": 3},
    {"id": "dormitorio_2", "nombre": "Dormitorio", "x": 8, "y": 6, "ancho": 4, "largo": 3},
]


@pytest.fixture
def dxf(tmp_path):
    geo = generar_geometrias(DISTRIBUCION, 12, 10)
    ruta = tmp_path / "base.dxf"
    generar_dxf_desde_geometrias(geo, 12, 10, str(ruta))
    return ruta


def _mover(ambiente, referencia, relacion):
    return EditRequest(operaciones=[
        EditOperation(
            tipo="mover_ambiente", ambiente=ambiente,
            referencia=referencia, relacion=relacion,
        )
    ])


def _ambientes(ruta):
    doc = ezdxf.readfile(str(ruta))
    return {a["id"]: a for a in obtener_ambientes(doc.modelspace())}, doc


def test_resolver_por_id_nombre_y_numero(dxf):
    amb, _ = _ambientes(dxf)
    lista = list(amb.values())

    assert resolver_ambiente(lista, "SALA")["id"] == "sala_1"
    assert resolver_ambiente(lista, "dormitorio 2")["id"] == "dormitorio_2"
    assert resolver_ambiente(lista, "dormitorio_1")["id"] == "dormitorio_1"

    with pytest.raises(ValueError, match="ambiguo"):
        resolver_ambiente(lista, "dormitorio")
    with pytest.raises(ValueError, match="No se encontro"):
        resolver_ambiente(lista, "garaje")


def test_mover_arriba_de_deja_los_ambientes_pegados(dxf, tmp_path):
    salida = tmp_path / "mov.dxf"
    r = editar_dxf(str(dxf), str(salida), _mover("dormitorio 1", "sala", "arriba_de"))

    assert r["modificaciones"][0]["id"] == "dormitorio_1"
    assert any("no se recalculan" in o for o in r["observaciones"])

    amb, doc = _ambientes(salida)
    dorm = amb["dormitorio_1"]["poligono"]
    sala = amb["sala_1"]["poligono"]

    assert dorm.bounds[1] == pytest.approx(4.0)             # apoyado sobre la sala
    assert dorm.area == pytest.approx(12.0)                 # conserva dimensiones
    assert dorm.intersection(sala).area == pytest.approx(0)
    assert dorm.intersection(sala.buffer(1e-6)).length > 0.5  # comparten arista

    # Las etiquetas se movieron con el ambiente.
    etiquetas = [
        t for t in doc.modelspace().query("TEXT")
        if t.get_xdata("AGENTE_ARQ")[0].value == "dormitorio_1"
    ]
    assert len(etiquetas) == 2
    for t in etiquetas:
        x, y = t.dxf.align_point.x, t.dxf.align_point.y
        assert dorm.buffer(0.01).covers(__import__("shapely.geometry").geometry.Point(x, y))


def test_mover_junto_a_elige_posicion_valida_cercana(dxf, tmp_path):
    salida = tmp_path / "mov.dxf"
    editar_dxf(str(dxf), str(salida), _mover("dormitorio_2", "cocina", "junto_a"))

    amb, _ = _ambientes(salida)
    dorm = amb["dormitorio_2"]["poligono"]
    cocina = amb["cocina_1"]["poligono"]

    assert dorm.intersection(cocina).area == pytest.approx(0)
    assert dorm.distance(cocina) == pytest.approx(0)
    for otro in ("sala_1", "dormitorio_1"):
        assert dorm.intersection(amb[otro]["poligono"]).area == pytest.approx(0)


def test_mover_sin_espacio_libre(dxf, tmp_path):
    # A la derecha de la sala está la cocina, y no cabe un dormitorio sobre ella.
    with pytest.raises(ValueError, match="No hay espacio"):
        editar_dxf(str(dxf), str(tmp_path / "x.dxf"), _mover("dormitorio 1", "sala", "derecha_de"))


def test_mover_errores_de_uso(dxf, tmp_path):
    salida = str(tmp_path / "x.dxf")
    with pytest.raises(ValueError, match="si mismo"):
        editar_dxf(str(dxf), salida, _mover("sala", "sala", "junto_a"))
    with pytest.raises(NotImplementedError):
        editar_dxf(str(dxf), salida, _mover("sala", "cocina", "lejos_de"))
    with pytest.raises(ValueError, match="No se encontro"):
        editar_dxf(str(dxf), salida, _mover("sala", "garaje", "junto_a"))


def test_editar_plano_regenera_muros_y_puertas(dxf, tmp_path):
    from src.services.pipeline import editar_plano

    salida = tmp_path / "regen.dxf"
    r = editar_plano(
        str(dxf), str(salida), _mover("dormitorio 1", "sala", "arriba_de")
    )

    assert salida.exists()
    assert not any("no se recalculan" in o for o in r["observaciones"])

    plano = r["plano"]
    nuevos = {a["id"]: a for a in plano.distribucion}
    assert nuevos["dormitorio_1"]["y"] == pytest.approx(4.0)
    # Los muros se calcularon sobre la nueva posicion.
    assert plano.muros and plano.puertas["puertas"]

    amb, _ = _ambientes(salida)
    assert amb["dormitorio_1"]["poligono"].bounds[1] == pytest.approx(4.0)


def test_editar_plano_avisa_si_queda_desconectado(dxf, tmp_path):
    from src.services.pipeline import editar_plano

    # Los dormitorios del fixture ya estan aislados de sala/cocina.
    r = editar_plano(str(dxf), str(tmp_path / "r.dxf"), _mover("cocina", "sala", "derecha_de"))
    assert any("sin pared compartida" in o for o in r["observaciones"])


def test_editar_plano_rechaza_misma_ruta(dxf):
    from src.services.pipeline import editar_plano

    with pytest.raises(ValueError, match="diferente"):
        editar_plano(str(dxf), str(dxf), _mover("cocina", "sala", "derecha_de"))


def _modificar(ambiente, area):
    return EditRequest(operaciones=[
        EditOperation(tipo="modificar_area", ambiente=ambiente, area_objetivo=area)
    ])


def test_reducir_area_conserva_contacto_con_vecinos(dxf, tmp_path):
    # Cocina (5..8 x 0..4) toca a la sala por x=5; al reducirla debe seguir pegada.
    salida = tmp_path / "red.dxf"
    editar_dxf(str(dxf), str(salida), _modificar("cocina", 6))

    amb, doc = _ambientes(salida)
    cocina, sala = amb["cocina_1"]["poligono"], amb["sala_1"]["poligono"]

    assert cocina.area == pytest.approx(6.0)
    assert cocina.bounds[0] == pytest.approx(5.0)
    assert cocina.boundary.intersection(sala.boundary).length > 1.0


def test_reducir_area_mueve_las_etiquetas_con_el_ambiente(dxf, tmp_path):
    salida = tmp_path / "et.dxf"
    editar_dxf(str(dxf), str(salida), _modificar("cocina", 6))

    amb, doc = _ambientes(salida)
    xmin, ymin, xmax, ymax = amb["cocina_1"]["poligono"].bounds

    from src.cad.dxf_editor import buscar_textos
    etiquetas = buscar_textos(doc.modelspace(), amb["cocina_1"])
    assert etiquetas
    for t in etiquetas:
        x, y, _ = t.dxf.insert
        assert xmin - 0.01 <= x <= xmax + 0.01
        assert ymin - 0.01 <= y <= ymax + 0.01
    assert any(t.dxf.text.strip() == "6.00 m2" for t in etiquetas)


def test_editar_plano_tras_reducir_area_sigue_conectado(dxf, tmp_path):
    from src.services.pipeline import editar_plano

    r = editar_plano(str(dxf), str(tmp_path / "c.dxf"), _modificar("cocina", 6))
    ady = {(a["ambiente_a"], a["ambiente_b"]) for a in r["plano"].validacion["adyacencias"]}
    assert ("sala_1", "cocina_1") in ady
