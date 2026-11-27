"""Reglas de funcionamiento: accesos, puertas, pasillo, baños y avisos."""

import itertools

import pytest

from src.ai.edit_interpreter import EditOperation, EditRequest
from src.geometry.adjacency_validator import detectar_adyacencias
from src.geometry.door_generator import generar_puertas_automaticas
from src.models.defaults import calcular_areas_predeterminadas
from src.models.requirements import Ambiente, RequerimientosArquitectonicos
from src.planning import layout_optimizer
from src.planning.reglas_acceso import (
    asignar_en_suite,
    completar_programa,
    elegir_entrada,
    evaluar_reglas,
    puede_dar_acceso,
)
from src.services.pipeline import (
    NOTA_PASILLO,
    construir_plano,
    editar_plano,
    generar_plano,
)
from src.ui.proyecto import observaciones_del_plano, resumen_modificaciones


def _req(ancho=10, largo=20, pisos=1, relaciones=(), **ambientes):
    req = RequerimientosArquitectonicos(
        area_total_vivienda_m2=100,
        ancho_terreno_m=ancho,
        largo_terreno_m=largo,
        numero_pisos=pisos,
        ambientes=[Ambiente(nombre=n, cantidad=c) for n, c in ambientes.items()],
        relaciones_adyacencia=list(relaciones),
    )
    return calcular_areas_predeterminadas(req)


def _amb(identificador, x, y, ancho, largo):
    return {
        "id": identificador, "nombre": identificador.rsplit("_", 1)[0],
        "x": x, "y": y, "ancho": ancho, "largo": largo,
    }


def _conexiones(puertas):
    return {
        frozenset((p["ambiente_a"], p["ambiente_b"])) for p in puertas["puertas"]
    }


def _par(a, b):
    return frozenset((a, b))


# ---------------- Reglas puras ----------------

@pytest.mark.parametrize("desde, hacia, permitido", [
    ("sala_1", "dormitorio_1", True),
    ("pasillo_1", "bano_1", True),
    ("sala_1", "bano_1", True),
    ("comedor_1", "bano_1", False),
    ("comedor_1", "dormitorio_1", False),
    ("pasillo_1", "dormitorio_1", True),
    ("cocina_1", "bano_1", False),
    ("bano_1", "bano_2", False),
    ("dormitorio_1", "dormitorio_2", False),
    ("dormitorio_1", "sala_1", False),
    ("cocina_1", "lavanderia_1", True),
    ("cocina_1", "dormitorio_1", False),
    ("dormitorio principal_1", "closet_1", True),
])
def test_puede_dar_acceso(desde, hacia, permitido):
    assert puede_dar_acceso(desde, hacia) is permitido


@pytest.mark.parametrize("desde, permitido", [
    ("sala_1", True),
    ("comedor_1", True),
    ("dormitorio_1", True),
    ("dormitorio principal_1", True),
    ("escalera_1", False),
    ("pasillo_1", False),
    ("cocina_1", False),
])
def test_a_la_terraza_se_sale_desde_un_ambiente_amplio_o_dormitorio(desde, permitido):
    assert puede_dar_acceso(desde, "terraza_1") is permitido
    # Aunque la escalera sea la entrada de la planta alta.
    assert puede_dar_acceso(desde, "terraza_1", entrada=desde) is permitido


@pytest.mark.parametrize("hacia, arriba, permitido", [
    ("pasillo_1", True, True),
    ("sala_1", True, True),
    ("dormitorio_1", True, False),
    ("bano_1", True, False),
    # Abajo la escalera es un final de recorrido, no un paso entre ambientes.
    ("pasillo_1", False, False),
    ("comedor_1", False, False),
    ("garaje_1", False, False),
])
def test_la_escalera_solo_desemboca_en_la_circulacion(hacia, arriba, permitido):
    entrada = "escalera_1" if arriba else "sala_1"
    assert puede_dar_acceso("escalera_1", hacia, entrada=entrada) is permitido


def test_a_la_escalera_se_llega_desde_la_circulacion():
    assert puede_dar_acceso("sala_1", "escalera_1")
    assert puede_dar_acceso("pasillo_1", "escalera_1")
    assert not puede_dar_acceso("dormitorio_1", "escalera_1")


def test_el_bano_en_suite_solo_se_abre_a_su_dormitorio():
    en_suite = {"bano_2": "dormitorio_1"}

    assert puede_dar_acceso("dormitorio_1", "bano_2", en_suite)
    assert not puede_dar_acceso("pasillo_1", "bano_2", en_suite)
    assert not puede_dar_acceso("dormitorio_2", "bano_2", en_suite)


@pytest.mark.parametrize("ids, planta_baja, esperado", [
    (["bano_1", "dormitorio_1", "sala_1"], True, "sala_1"),
    (["dormitorio_1", "comedor_1"], True, "comedor_1"),
    (["bano_1", "dormitorio_1"], True, "dormitorio_1"),
    (["dormitorio_1", "pasillo_1", "escalera_1"], False, "escalera_1"),
])
def test_elegir_entrada(ids, planta_baja, esperado):
    assert elegir_entrada(ids, planta_baja) == esperado


def test_en_suite_va_al_dormitorio_principal():
    ids = ["dormitorio_1", "dormitorio principal_1", "bano_1", "bano_2"]

    assert asignar_en_suite(ids) == {"bano_2": "dormitorio principal_1"}


def test_con_un_solo_bano_no_hay_en_suite():
    assert asignar_en_suite(["dormitorio_1", "bano_1"]) == {}


def test_en_suite_respeta_lo_pedido_por_el_usuario():
    relaciones = [{
        "modo": "correspondiente",
        "pares": [["dormitorio_1", "bano_1"], ["dormitorio_2", "bano_2"]],
    }]

    assert asignar_en_suite(
        ["dormitorio_1", "dormitorio_2", "bano_1", "bano_2"], relaciones
    ) == {"bano_1": "dormitorio_1", "bano_2": "dormitorio_2"}


# ---------------- Pasillo automático ----------------

def test_se_agrega_pasillo_con_varios_dormitorios_y_banos():
    req = _req(sala=1, dormitorio=2, **{"baño": 2})

    completo = completar_programa(req)

    assert completo.ambientes[-1].nombre == "pasillo"
    assert completo.ambientes[-1].area_objetivo_m2 >= 4
    assert len(req.ambientes) == 3, "no modifica los requerimientos originales"


@pytest.mark.parametrize("ambientes", [
    {"sala": 1},
    {"sala": 1, "dormitorio": 1},
    {"sala": 1, "dormitorio": 3, "pasillo": 1},
])
def test_no_se_agrega_pasillo_si_no_hace_falta_o_ya_existe(ambientes):
    req = _req(**ambientes)

    assert completar_programa(req) is req


# ---------------- Puertas ----------------

# Baños y dormitorios contiguos entre sí, todos bajo un pasillo y una sala.
PLANTA = [
    _amb("sala_1", 0, 0, 8, 3),
    _amb("pasillo_1", 0, 3, 8, 1.5),
    _amb("dormitorio_1", 0, 4.5, 3, 3),
    _amb("bano_1", 3, 4.5, 2, 3),
    _amb("bano_2", 5, 4.5, 1.5, 3),
    _amb("dormitorio_2", 6.5, 4.5, 3, 3),
]


# Rectángulo sin huecos de 8 x 7 m que cumple las reglas.
PLANTA_COMPACTA = [
    _amb("sala_1", 0, 0, 5, 3.5),
    _amb("cocina_1", 5, 0, 3, 3.5),
    _amb("pasillo_1", 0, 3.5, 8, 1.2),
    _amb("dormitorio_1", 0, 4.7, 3.5, 2.8),
    _amb("bano_1", 3.5, 4.7, 2, 2.8),
    _amb("dormitorio_2", 5.5, 4.7, 2.5, 2.8),
]


def test_una_sola_puerta_por_ambiente_privado():
    conexiones = _conexiones(generar_puertas_automaticas(PLANTA))

    assert _par("sala_1", "pasillo_1") in conexiones
    assert _par("pasillo_1", "dormitorio_1") in conexiones
    assert _par("pasillo_1", "dormitorio_2") in conexiones
    assert _par("pasillo_1", "bano_1") in conexiones
    assert _par("bano_1", "bano_2") not in conexiones
    for privado in ("dormitorio_1", "dormitorio_2", "bano_1"):
        assert sum(privado in par for par in conexiones) == 1, privado


def test_a_la_cocina_se_entra_desde_el_comedor_y_no_desde_el_pasillo():
    planta = [
        _amb("sala_1", 0, 0, 4, 3),
        _amb("comedor_1", 4, 0, 4, 3),
        _amb("pasillo_1", 0, 3, 4, 1.5),
        _amb("cocina_1", 4, 3, 4, 3),
        _amb("dormitorio_1", 0, 4.5, 4, 3),
    ]

    conexiones = _conexiones(generar_puertas_automaticas(planta))

    assert _par("comedor_1", "cocina_1") in conexiones
    assert _par("pasillo_1", "cocina_1") not in conexiones


def test_hay_puerta_exterior_en_el_frente_de_la_sala():
    puertas = generar_puertas_automaticas(PLANTA)["puertas"]

    (exterior,) = [p for p in puertas if p["ambiente_b"] == "exterior"]
    assert exterior["ambiente_a"] == "sala_1"
    assert exterior["orientacion"] == "horizontal"
    assert exterior["centro"][1] == 0


def test_planta_alta_sin_puerta_exterior():
    puertas = generar_puertas_automaticas(PLANTA, puerta_exterior=False)["puertas"]

    assert all(p["ambiente_b"] != "exterior" for p in puertas)


def test_el_plano_con_puerta_exterior_se_construye(tmp_path):
    plano = construir_plano(PLANTA, 10, 10, tmp_path / "p.dxf")

    assert plano.aberturas["cantidad_puertas"] == len(plano.puertas["puertas"])
    assert plano.ruta_dxf.exists()


def test_bano_sin_otro_acceso_usa_el_dormitorio_sin_aviso():
    planta = [
        _amb("sala_1", 0, 0, 4, 3),
        _amb("dormitorio_1", 0, 3, 4, 3),
        _amb("bano_1", 0, 6, 2, 2),
    ]

    puertas = generar_puertas_automaticas(planta)
    avisos = evaluar_reglas(planta, puertas["puertas"], detectar_adyacencias(planta))

    assert _par("dormitorio_1", "bano_1") in _conexiones(puertas)
    assert avisos == []


def test_acceso_de_respaldo_y_aviso_si_hay_que_cruzar_un_bano():
    planta = [
        _amb("sala_1", 0, 0, 4, 3),
        _amb("bano_1", 0, 3, 4, 2),
        _amb("dormitorio_1", 0, 5, 4, 3),
    ]

    puertas = generar_puertas_automaticas(planta)
    avisos = evaluar_reglas(planta, puertas["puertas"], detectar_adyacencias(planta))

    assert _par("bano_1", "dormitorio_1") in _conexiones(puertas)
    assert any("Dormitorio" in a and "cruzar" in a for a in avisos)


def test_avisos_por_banos_juntos_cocina_lejos_y_ambiente_aislado():
    planta = [
        _amb("sala_1", 0, 0, 6, 3),
        _amb("comedor_1", 6, 0, 3, 3),
        _amb("bano_1", 0, 3, 2, 2),
        _amb("bano_2", 2, 3, 2, 2),
        _amb("cocina_1", 20, 20, 3, 3),
    ]

    puertas = generar_puertas_automaticas(planta)
    avisos = " ".join(
        evaluar_reglas(planta, puertas["puertas"], detectar_adyacencias(planta))
    )

    assert "Bano 1 y Bano 2 comparten pared." in avisos
    assert "La cocina no está junto al comedor." in avisos
    assert "Cocina no tiene ninguna puerta" in avisos


# ---------------- Plano generado de extremo a extremo ----------------

def _comparten_pared(distribucion, tipo):
    return [
        a for a in detectar_adyacencias(distribucion)
        if a["ambiente_a"].startswith(tipo) and a["ambiente_b"].startswith(tipo)
    ]


def test_plano_tipico_cumple_las_reglas(tmp_path):
    req = _req(sala=1, comedor=1, cocina=1, dormitorio=2, **{"baño": 2})

    plano = generar_plano(req, tmp_path / "p.dxf")

    assert [a for a in plano.avisos if "ventana" not in a] == []
    assert plano.notas == [NOTA_PASILLO]
    assert not _comparten_pared(plano.distribucion, "bano")

    exteriores = [p for p in plano.puertas["puertas"] if p["ambiente_b"] == "exterior"]
    assert [p["ambiente_a"] for p in exteriores] == ["sala_1"]

    sala = next(a for a in plano.distribucion if a["id"] == "sala_1")
    assert sala["y"] == min(a["y"] for a in plano.distribucion)

    conexiones = _conexiones(plano.puertas)
    privados = ("bano", "dormitorio")
    for a, b in itertools.combinations([x["id"] for x in plano.distribucion], 2):
        if a.startswith(b.rsplit("_", 1)[0]) and a.startswith(privados):
            assert _par(a, b) not in conexiones
    assert sum("bano_2" in par for par in conexiones) == 1
    assert _par("bano_2", "dormitorio_1") in conexiones, "baño en suite"


def test_la_vivienda_sale_compacta(monkeypatch):
    monkeypatch.setattr(layout_optimizer, "TIEMPO_COMPACTACION_SEGUNDOS", 6)

    dist = layout_optimizer.optimizar_distribucion(
        _req(sala=1, cocina=1, dormitorio=2, **{"baño": 1})
    )

    envolvente = (
        max(a["x"] + a["ancho"] for a in dist) - min(a["x"] for a in dist)
    ) * (
        max(a["y"] + a["largo"] for a in dist) - min(a["y"] for a in dist)
    )
    assert sum(a["area_m2"] for a in dist) / envolvente >= 0.9


def test_dos_pisos_solo_la_planta_baja_tiene_puerta_exterior(tmp_path):
    req = _req(pisos=2, sala=1, cocina=1, dormitorio=2, **{"baño": 1})

    plano = generar_plano(req, tmp_path / "p.dxf")

    exteriores = [
        [p for p in piso.puertas["puertas"] if p["ambiente_b"] == "exterior"]
        for piso in plano.pisos
    ]
    assert [len(e) for e in exteriores] == [1, 0]


def test_las_relaciones_del_usuario_mandan_sobre_las_reglas(tmp_path):
    req = _req(
        sala=1, dormitorio=1, relaciones=[{
            "ambiente_a": "baño", "ambiente_b": "baño", "modo": "todos",
        }], **{"baño": 2},
    )

    plano = generar_plano(req, tmp_path / "p.dxf")

    assert _comparten_pared(plano.distribucion, "bano")


def test_si_no_caben_las_reglas_se_relajan(monkeypatch):
    intentos = []
    original = layout_optimizer._resolver_nivel

    def solo_el_basico(grafo, nivel, *resto):
        intentos.append(nivel.nombre)
        return original(grafo, nivel, *resto) if not nivel.acceso else None

    monkeypatch.setattr(layout_optimizer, "_resolver_nivel", solo_el_basico)

    distribucion = layout_optimizer.optimizar_distribucion(
        _req(sala=1, dormitorio=2, **{"baño": 2})
    )

    assert intentos == ["completo", "sin_preferencias", "sin_separacion", "basico"]
    assert not any(a["id"].startswith("pasillo") for a in distribucion)


def test_el_pasillo_no_impide_usar_un_terreno_justo(tmp_path):
    """Si el pasillo no cabe, se genera sin él."""
    req = _req(ancho=5, largo=6, dormitorio=2)
    for ambiente in req.ambientes:
        ambiente.area_minima_m2 = ambiente.area_objetivo_m2 = 14
    req.area_total_vivienda_m2 = 28

    plano = generar_plano(req, tmp_path / "p.dxf")

    assert len(plano.distribucion) == 2
    assert plano.notas == []


def test_el_chat_informa_el_pasillo_y_los_avisos(tmp_path):
    plano = construir_plano(PLANTA, 10, 10, tmp_path / "p.dxf")
    plano.notas = [NOTA_PASILLO]

    texto = observaciones_del_plano(plano)

    assert NOTA_PASILLO in texto
    assert "⚠️ Bano 1 y Bano 2 comparten pared." in texto


# ---------------- Ampliar reacomodando la planta ----------------

def test_ampliar_un_plano_compacto_mantiene_las_reglas(tmp_path):
    base = tmp_path / "base.dxf"
    construir_plano(PLANTA_COMPACTA, 12, 12, base)
    solicitud = EditRequest(operaciones=[EditOperation(
        tipo="modificar_area", ambiente="dormitorio 1", area_objetivo=14,
    )])

    r = editar_plano(str(base), str(tmp_path / "e.dxf"), solicitud)

    modificacion = r["modificaciones"][0]
    assert modificacion["area_nueva"] == pytest.approx(14, rel=0.04)
    plano = r["plano"]
    assert [a for a in plano.avisos if "ventana" not in a] == []
    areas = {a["id"]: a["ancho"] * a["largo"] for a in plano.distribucion}
    for original in PLANTA_COMPACTA:
        if original["id"] != "dormitorio_1":
            area = original["ancho"] * original["largo"]
            assert areas[original["id"]] >= area * 0.85 - 0.1, original["id"]


def test_el_resumen_explica_el_reacomodo():
    lineas = resumen_modificaciones([{
        "id": "sala_1", "ambiente": "Sala",
        "area_anterior": 18, "area_nueva": 22,
        "ajustes": [{"id": "cocina_1", "area_anterior": 12, "area_nueva": 11}],
    }])

    assert lineas[1] == (
        "Para hacer sitio reacomodé la planta: Cocina 1 12.0 → 11.0 m²"
    )
