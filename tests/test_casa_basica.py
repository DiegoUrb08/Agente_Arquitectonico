"""Solo la lista de ambientes, y la casa básica cuando no se detalla el programa."""

import json

import pytest

from src.ai import interpreter
from src.models.defaults import completar_casa_basica
from src.models.requirements import Ambiente, RequerimientosArquitectonicos as Req
from src.services.pipeline import generar_plano

BASICOS = ["sala", "comedor", "cocina", "dormitorio", "baño"]


def _interpretar(monkeypatch, **datos):
    class Proveedor:
        def chat(self, **_):
            return {"message": {"content": json.dumps(datos)}}

    monkeypatch.setattr(interpreter, "get_provider", Proveedor)
    return interpreter.interpretar_instruccion("una casa")


def _ambientes(*nombres):
    return [{"nombre": n, "cantidad": 1} for n in nombres]


def _margenes(plano):
    x0, y0, x1, y1 = plano.geometrias["terreno"].bounds
    cajas = [a["poligono"].bounds for a in plano.geometrias["ambientes"]]
    return (
        min(b[0] for b in cajas) - x0, x1 - max(b[2] for b in cajas),
        min(b[1] for b in cajas) - y0, y1 - max(b[3] for b in cajas),
    )


def test_solo_la_lista_genera_el_plano(monkeypatch, tmp_path):
    req = _interpretar(monkeypatch, ambientes=_ambientes(*BASICOS))

    assert req.area_total_vivienda_m2 == pytest.approx(71.59, abs=0.1)
    assert req.terreno_estimado and not req.programa_basico
    plano = generar_plano(req, tmp_path / "p.dxf")
    assert {a["nombre"] for a in plano.distribucion} >= set(BASICOS)


def test_la_casa_de_25_m2_sale_completa_y_sin_pasillo(monkeypatch, tmp_path):
    req = _interpretar(monkeypatch, area_total_vivienda_m2=25, ambientes=[])

    plano = generar_plano(req, tmp_path / "p.dxf")

    assert sorted(a["nombre"] for a in plano.distribucion) == sorted(BASICOS)
    assert plano.mobiliario["omitidos"] == []
    assert plano.avisos == []
    total = sum(a["ancho"] * a["largo"] for a in plano.distribucion)
    assert total == pytest.approx(25, rel=0.05)
    izquierda, derecha, frente, fondo = _margenes(plano)
    assert min(izquierda, derecha, frente, fondo) > 0.5
    assert abs(izquierda - derecha) <= 0.2 and abs(frente - fondo) <= 0.2
    assert any("añadí sala" in n for n in plano.notas)


def test_se_completan_los_basicos_que_faltan(monkeypatch):
    req = _interpretar(
        monkeypatch, area_total_vivienda_m2=25,
        ambientes=_ambientes("dormitorio principal", "baño", "lavanderia"),
    )

    assert req.ambientes_agregados == ["sala", "comedor", "cocina"]
    assert req.programa_basico
    assert len(req.ambientes) == 6, "los extras del usuario se respetan"


@pytest.mark.parametrize("datos", [
    {"numero_pisos": 2, "area_total_vivienda_m2": 28},
    {"area_total_vivienda_m2": 90},
])
def test_dos_pisos_o_casa_grande_con_lista_no_se_tocan(datos):
    req = Req(ambientes=[Ambiente(nombre="sala")], **datos)

    completar_casa_basica(req)

    assert [a.nombre for a in req.ambientes] == ["sala"]
    assert not req.programa_basico


def test_casa_grande_sin_lista_lleva_los_basicos_sin_ser_compacta():
    req = completar_casa_basica(Req(area_total_vivienda_m2=100))

    assert [a.nombre for a in req.ambientes] == BASICOS
    assert not req.programa_basico


def test_demasiado_pequena_se_explica():
    with pytest.raises(ValueError, match="al menos 22 m²"):
        completar_casa_basica(Req(area_total_vivienda_m2=18))


def test_el_terreno_del_usuario_se_respeta(monkeypatch):
    req = _interpretar(
        monkeypatch, area_total_vivienda_m2=25, ancho_terreno_m=8,
        largo_terreno_m=10, ambientes=[],
    )

    assert not req.terreno_estimado
    assert (req.ancho_terreno_m, req.largo_terreno_m) == (8, 10)


def test_el_modelo_no_decide_las_marcas_internas(monkeypatch):
    req = _interpretar(
        monkeypatch, area_total_vivienda_m2=90, programa_basico=True,
        ambientes=_ambientes("sala"),
    )

    assert not req.programa_basico
