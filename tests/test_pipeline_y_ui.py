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
    generar_csv_areas,
    exportar_csv_areas,
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
    from src.planning.reglas_ambientes import AMBIENTES_VALIDOS, PROPORCIONES_AMBIENTES
    assert "escalera" in AMBIENTES_VALIDOS
    assert "escalera" in PROPORCIONES_AMBIENTES


def test_dxf_multipisos_contiene_ambas_plantas(tmp_path):
    import ezdxf
    req = _requerimientos_dos_pisos()
    r = generar_plano_multipisos(req, 10, 20, tmp_path / "mp.dxf")
    doc = ezdxf.readfile(str(r.ruta_dxf))
    msp = doc.modelspace()
    textos = [e.dxf.text for e in msp if e.dxftype() == "TEXT"]
    etiquetas = [t for t in textos if "PLANTA" in t.upper()]
    assert len(etiquetas) >= 2


def test_escalera_peldanos_dibujados_en_dxf(tmp_path):
    import ezdxf
    from src.geometry.geometry_generator import generar_geometrias
    from src.cad.dxf_generator import generar_dxf_desde_geometrias

    dist = [
        {"id": "sala_1", "nombre": "sala", "x": 0, "y": 0, "ancho": 7, "largo": 5},
        {"id": "escalera_1", "nombre": "escalera", "x": 7, "y": 0, "ancho": 3, "largo": 5},
    ]
    geo = generar_geometrias(dist, 10, 5)
    generar_dxf_desde_geometrias(geo, 10, 5, str(tmp_path / "esc.dxf"))
    doc = ezdxf.readfile(str(tmp_path / "esc.dxf"))
    msp = doc.modelspace()
    # La escalera debe tener al menos 3 líneas de peldaños horizontales.
    lineas = [e for e in msp if e.dxftype() == "LINE" and e.dxf.layer == "AMBIENTES"]
    assert len(lineas) >= 3


def test_dxf_monopiso_contiene_cotas(tmp_path):
    """El DXF de un plano simple debe tener líneas en la capa TEXTOS (cotas)."""
    import ezdxf
    r = generar_plano(_requerimientos(), tmp_path / "cotas.dxf")
    doc = ezdxf.readfile(str(r.ruta_dxf))
    msp = doc.modelspace()
    lineas_textos = [e for e in msp if e.dxftype() == "LINE" and e.dxf.layer == "TEXTOS"]
    assert len(lineas_textos) >= 4   # 2 extensiones + 1 cota h + 1 cota v como mínimo


def test_dxf_monopiso_contiene_cuadro_areas(tmp_path):
    """El DXF debe tener texto 'CUADRO DE ÁREAS' en la capa TEXTOS."""
    import ezdxf
    r = generar_plano(_requerimientos(), tmp_path / "cuadro.dxf")
    doc = ezdxf.readfile(str(r.ruta_dxf))
    msp = doc.modelspace()
    textos = [e.dxf.text for e in msp if e.dxftype() == "TEXT"]
    assert any("CUADRO" in t.upper() for t in textos)
    assert any("TOTAL" in t.upper() for t in textos)


def test_csv_areas_monopiso(tmp_path):
    """generar_csv_areas produce CSV con cabecera y una fila por ambiente."""
    r = generar_plano(_requerimientos(), tmp_path / "p.dxf")
    csv_text = generar_csv_areas(r)
    lineas = csv_text.strip().splitlines()
    assert lineas[0] == "piso,ambiente,area_m2,ancho_m,largo_m"
    assert len(lineas) == 5   # cabecera + 4 ambientes


def test_csv_areas_multipisos(tmp_path):
    """generar_csv_areas para multipiso incluye columna piso con dos valores distintos."""
    r = generar_plano_multipisos(_requerimientos_dos_pisos(), 10, 20, tmp_path / "mp.dxf")
    csv_text = generar_csv_areas(r)
    lineas = csv_text.strip().splitlines()
    pisos_col = {l.split(",")[0] for l in lineas[1:]}
    assert "PLANTA BAJA" in pisos_col
    assert any("ALTA" in p for p in pisos_col)


def test_exportar_csv_areas_escribe_archivo(tmp_path):
    r = generar_plano(_requerimientos(), tmp_path / "p.dxf")
    ruta_csv = exportar_csv_areas(r, tmp_path / "areas.csv")
    assert ruta_csv.exists()
    contenido = ruta_csv.read_text(encoding="utf-8")
    assert "piso" in contenido
    assert "area_m2" in contenido


def test_la_interfaz_arranca_sin_excepciones(monkeypatch):
    from streamlit.testing.v1 import AppTest

    # Forzar mock provider para que el test no dependa del .env del operador
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.delenv("PROXY_URL", raising=False)

    raiz = Path(__file__).resolve().parent.parent
    at = AppTest.from_file(str(raiz / "app.py"), default_timeout=30).run()

    assert not at.exception
    assert at.title[0].value == "Agente Arquitectónico"
    assert [h.value for h in at.header] == [
        "1. Generar un nuevo plano",
        "2. Editar un plano existente",
    ]
