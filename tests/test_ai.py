import json

import ollama
import pytest

from src.ai import edit_interpreter, interpreter, ollama_client
from src.ai.ollama_client import OllamaError, chat_con_reintentos


def _respuesta(datos):
    return {"message": {"content": json.dumps(datos)}}


# ---------------- interpretar_instruccion ----------------

def test_interpretar_instruccion_completa_areas_y_terreno(monkeypatch):
    datos = {
        "tipo_proyecto": "vivienda",
        "area_terreno_m2": 200,
        "ambientes": [
            {"nombre": "sala", "cantidad": 1},
            {"nombre": "baño", "cantidad": 2},
        ],
    }
    monkeypatch.setattr(
        interpreter, "chat_con_reintentos", lambda **kw: _respuesta(datos)
    )

    req = interpreter.interpretar_instruccion("casa de 200 m2")

    assert req.ancho_terreno_m and req.largo_terreno_m
    assert req.area_total_vivienda_m2 > 0
    assert all(a.area_objetivo_m2 > 0 for a in req.ambientes)


def test_interpretar_instruccion_vacia():
    with pytest.raises(ValueError):
        interpreter.interpretar_instruccion("   ")


def test_interpretar_instruccion_json_invalido(monkeypatch):
    monkeypatch.setattr(
        interpreter,
        "chat_con_reintentos",
        lambda **kw: {"message": {"content": "no es json"}},
    )
    with pytest.raises(ValueError, match="JSON invalido"):
        interpreter.interpretar_instruccion("casa")


def test_interpretar_instruccion_esquema_invalido(monkeypatch):
    monkeypatch.setattr(
        interpreter,
        "chat_con_reintentos",
        lambda **kw: _respuesta({"ambientes": "no es lista"}),
    )
    with pytest.raises(ValueError, match="validar"):
        interpreter.interpretar_instruccion("casa")


# ---------------- interpretar_edicion ----------------

def test_interpretar_edicion_valida(monkeypatch):
    datos = {"operaciones": [
        {"tipo": "modificar_area", "ambiente": "Sala", "area_objetivo": 16}
    ]}
    monkeypatch.setattr(
        edit_interpreter, "chat_con_reintentos", lambda **kw: _respuesta(datos)
    )
    solicitud = edit_interpreter.interpretar_edicion("sala a 16 m2")
    assert solicitud.operaciones[0].area_objetivo == 16


def test_interpretar_edicion_rechaza_operacion_incompleta(monkeypatch):
    datos = {"operaciones": [{"tipo": "modificar_area", "ambiente": "Sala"}]}
    monkeypatch.setattr(
        edit_interpreter, "chat_con_reintentos", lambda **kw: _respuesta(datos)
    )
    with pytest.raises(ValueError):
        edit_interpreter.interpretar_edicion("cambia la sala")


# ---------------- chat_con_reintentos ----------------

class _ClienteFalso:
    def __init__(self, fallos, error):
        self.fallos = fallos
        self.error = error
        self.llamadas = 0

    def chat(self, **kwargs):
        self.llamadas += 1
        if self.llamadas <= self.fallos:
            raise self.error
        return {"message": {"content": "ok"}}


def _parchear_cliente(monkeypatch, cliente):
    monkeypatch.setattr(ollama, "Client", lambda **kw: cliente)


def test_reintenta_y_se_recupera(monkeypatch):
    cliente = _ClienteFalso(fallos=2, error=ConnectionError("caído"))
    _parchear_cliente(monkeypatch, cliente)

    r = chat_con_reintentos(messages=[], reintentos=2, espera=0)

    assert r["message"]["content"] == "ok"
    assert cliente.llamadas == 3


def test_agota_reintentos_y_lanza_ollama_error(monkeypatch):
    cliente = _ClienteFalso(fallos=99, error=ConnectionError("caído"))
    _parchear_cliente(monkeypatch, cliente)

    with pytest.raises(OllamaError):
        chat_con_reintentos(messages=[], reintentos=1, espera=0)

    assert cliente.llamadas == 2


def test_no_reintenta_errores_4xx(monkeypatch):
    cliente = _ClienteFalso(
        fallos=99, error=ollama.ResponseError("modelo no existe", 404)
    )
    _parchear_cliente(monkeypatch, cliente)

    with pytest.raises(OllamaError):
        chat_con_reintentos(messages=[], reintentos=3, espera=0)

    assert cliente.llamadas == 1


def test_consultar_modelo_devuelve_mensaje_de_error(monkeypatch):
    def falla(**kw):
        raise OllamaError("sin servidor")

    monkeypatch.setattr(ollama_client, "chat_con_reintentos", falla)
    assert "Error al comunicarse" in ollama_client.consultar_modelo("hola")
