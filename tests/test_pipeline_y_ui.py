from pathlib import Path

import pytest

from src.models.defaults import (
    calcular_areas_predeterminadas,
    obtener_area_referencia,
    obtener_peso,
)
from src.models.distribucion import validar_esquema_distribucion
from src.models.requirements import Ambiente, RequerimientosArquitectonicos
from src.services.pipeline import (
    generar_plano,
    generar_plano_multipisos,
    ResultadoPlanoMultipisos,
)
from src.planning.layout_optimizer import optimizar_por_pisos
from src.utils.texto import normalizar_nombre


def test_normalizar_nombre_es_unico_en_todo_el_proyecto():
    from src.models import defaults
    from src.planning import layout_optimizer, space_graph

    assert defaults.normalizar_nombre is normalizar_nombre
    assert space_graph.normalizar_nombre is normalizar_nombre
    assert layout_optimizer.normalizar_nombre is normalizar_nombre


@pytest.mark.parametrize("a, b", [("baño", "bano"), ("Baño 2", "bano 2"), ("lavandería", "lavanderia")])
def test_defaults_tratan_igual_con_y_sin_tilde(a, b):
    assert obtener_peso(a) == obtener_peso(b)
    assert obtener_area_referencia(a) == obtener_area_referencia(b)


def test_baño_usa_su_area_de_referencia_y_no_el_valor_generico():
    assert obtener_area_referencia("bano") == 6
    assert obtener_area_referencia("Baño principal") == 6


# ---------------- esquema de distribución ----------------

def test_esquema_valido(distribucion_simple):
    validar_esquema_distribucion(distribucion_simple)


@pytest.mark.parametrize("cambio", [
    {"ancho": 0},
    {"x": -1},
    {"x": "1"},
    {"id": "sala_1"},  # duplicado (se aplica al segundo)
])
def test_esquema_invalido(distribucion_simple, cambio):
    distribucion_simple[1].update(cambio)
    with pytest.raises(ValueError):
        validar_esquema_distribucion(distribucion_simple)


def test_esquema_falta_clave_y_vacio(distribucion_simple):
    del distribucion_simple[0]["largo"]
    with pytest.raises(ValueError, match="largo"):
        validar_esquema_distribucion(distribucion_simple)
    with pytest.raises(ValueError):
        validar_esquema_distribucion([])


# ---------------- pipeline ----------------

def _requerimientos():
    req = RequerimientosArquitectonicos(
        area_total_vivienda_m2=100,
        ancho_terreno_m=10,
        largo_terreno_m=20,
        ambientes=[
            Ambiente(nombre="sala"),
            Ambiente(nombre="cocina"),
            Ambiente(nombre="dormitorio"),
            Ambiente(nombre="baño"),
        ],
        relaciones_adyacencia=[["sala", "cocina"]],
    )
    return calcular_areas_predeterminadas(req)


def test_pipeline_genera_dxf_y_reporta_etapas(tmp_path):
    etapas = []
    r = generar_plano(_requerimientos(), tmp_path / "salida" / "plano.dxf", progreso=etapas.append)

    assert r.ruta_dxf.exists()
    assert len(r.distribucion) == 4
    assert r.validacion["distribucion_conectada"] is True
    assert len(etapas) == 9


def test_pipeline_sin_dimensiones_de_terreno(tmp_path):
    req = _requerimientos()
    req.ancho_terreno_m = None
    with pytest.raises(ValueError, match="terreno"):
        generar_plano(req, tmp_path / "p.dxf")


# ---------------- UI (Streamlit AppTest, sin Ollama) ----------------

def _requerimientos_dos_pisos():
    req = RequerimientosArquitectonicos(
        ancho_terreno_m=10,
        largo_terreno_m=20,
        area_total_vivienda_m2=120,
        numero_pisos=2,
        ambientes=[
            Ambiente(nombre="sala"),
            Ambiente(nombre="cocina"),
            Ambiente(nombre="dormitorio", cantidad=2),
            Ambiente(nombre="baño"),
        ],
    )
    return calcular_areas_predeterminadas(req)


def test_optimizar_por_pisos_devuelve_dos_distribuciones():
    req = _requerimientos_dos_pisos()
    distribuciones = optimizar_por_pisos(req)
    assert len(distribuciones) == 2
    # Planta baja: sala + cocina + escalera
    nombres_baja = {normalizar_nombre(a["nombre"]) for a in distribuciones[0]}
    assert "sala" in nombres_baja
    assert "cocina" in nombres_baja
    assert "escalera" in nombres_baja
    # Planta alta: dormitorios + baño + escalera
    nombres_alta = {normalizar_nombre(a["nombre"]) for a in distribuciones[1]}
    assert "dormitorio" in nombres_alta
    assert "bano" in nombres_alta
    assert "escalera" in nombres_alta


def test_optimizar_por_pisos_solo_sociales_cae_a_un_piso():
    req = RequerimientosArquitectonicos(
        ancho_terreno_m=10,
        largo_terreno_m=20,
        area_total_vivienda_m2=80,
        numero_pisos=2,
        ambientes=[Ambiente(nombre="sala"), Ambiente(nombre="cocina")],
    )
    req = calcular_areas_predeterminadas(req)
    distribuciones = optimizar_por_pisos(req)
    assert len(distribuciones) == 1


def test_pipeline_multipisos_genera_dxf(tmp_path):
    req = _requerimientos_dos_pisos()
    r = generar_plano_multipisos(req, 10, 20, tmp_path / "multipisos.dxf")
    assert isinstance(r, ResultadoPlanoMultipisos)
    assert r.ruta_dxf.exists()
    assert r.numero_pisos == 2
    assert len(r.pisos) == 2


def test_generar_plano_despacha_a_multipisos_si_numero_pisos_es_2(tmp_path):
    req = _requerimientos_dos_pisos()
    r = generar_plano(req, tmp_path / "p.dxf")
    assert isinstance(r, ResultadoPlanoMultipisos)
    assert r.ruta_dxf.exists()


def test_escalera_esta_en_catalogo():
    from src.planning.reglas_ambientes import AMBIENTES_VALIDOS
    assert "escalera" in AMBIENTES_VALIDOS


def test_la_interfaz_arranca_sin_excepciones():
    from streamlit.testing.v1 import AppTest

    raiz = Path(__file__).resolve().parent.parent
    at = AppTest.from_file(str(raiz / "app.py"), default_timeout=30).run()

    assert not at.exception
    assert at.title[0].value == "Agente Arquitectónico"
    assert [h.value for h in at.header] == [
        "1. Generar un nuevo plano",
        "2. Editar un plano existente",
    ]
