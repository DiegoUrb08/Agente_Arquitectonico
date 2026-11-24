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


def test_historial_registra_intentos_fallidos_y_exitoso(monkeypatch):
    cliente = _ClienteFalso(fallos=1, error=ConnectionError("caído"))
    _parchear_cliente(monkeypatch, cliente)

    hist = []
    chat_con_reintentos(messages=[], reintentos=2, espera=0, historial=hist)

    assert len(hist) == 2
    assert hist[0]["ok"] is False
    assert hist[0]["error"] is not None
    assert hist[1]["ok"] is True
    assert hist[1]["error"] is None
    assert all("tiempo_s" in h for h in hist)
    assert all(h["intento"] == i + 1 for i, h in enumerate(hist))


def test_historial_registra_unico_intento_exitoso(monkeypatch):
    cliente = _ClienteFalso(fallos=0, error=None)
    _parchear_cliente(monkeypatch, cliente)

    hist = []
    chat_con_reintentos(messages=[], reintentos=2, espera=0, historial=hist)

    assert len(hist) == 1
    assert hist[0]["ok"] is True


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


# ---------------- diagnóstico de reintentos en interpretar_instruccion ----------------

def test_interpretar_instruccion_anota_reintentos_en_observaciones(monkeypatch):
    """Cuando el LLM necesita más de un intento, aparece una nota [LLM] en observaciones."""
    datos_ok = {
        "tipo_proyecto": "vivienda",
        "ancho_terreno_m": 10.0,
        "largo_terreno_m": 20.0,
        "ambientes": [{"nombre": "sala", "cantidad": 1}],
    }

    def _chat_dos_intentos(**kw):
        # Simula que internamente hubo un reintento: llena historial con 2 entradas.
        hist = kw.get("historial")
        if hist is not None:
            hist.append({"intento": 1, "tiempo_s": 5.0, "ok": False, "error": "timeout"})
            hist.append({"intento": 2, "tiempo_s": 3.0, "ok": True, "error": None})
        return _respuesta(datos_ok)

    monkeypatch.setattr(interpreter, "chat_con_reintentos", _chat_dos_intentos)
    req = interpreter.interpretar_instruccion("casa 10x20 con sala")

    notas_llm = [o for o in req.observaciones if o.startswith("[LLM]")]
    assert notas_llm, "Se esperaba nota de reintentos en observaciones"
    assert "2 intentos" in notas_llm[0]


def test_interpretar_instruccion_sin_reintentos_no_anota(monkeypatch):
    datos = {
        "tipo_proyecto": "vivienda",
        "ancho_terreno_m": 10.0,
        "largo_terreno_m": 20.0,
        "ambientes": [{"nombre": "sala", "cantidad": 1}],
    }
    monkeypatch.setattr(interpreter, "chat_con_reintentos", lambda **kw: _respuesta(datos))
    req = interpreter.interpretar_instruccion("casa 10x20 con sala")

    notas_llm = [o for o in req.observaciones if o.startswith("[LLM]")]
    assert not notas_llm


# ---------------- fallback regex terreno ----------------

def _sin_terreno(monkeypatch, prompt):
    """Mock que devuelve terreno nulo para forzar el fallback."""
    datos = {
        "tipo_proyecto": "vivienda",
        "ambientes": [{"nombre": "sala", "cantidad": 1}],
    }
    monkeypatch.setattr(interpreter, "chat_con_reintentos", lambda **kw: _respuesta(datos))
    return interpreter.interpretar_instruccion(prompt)


def test_fallback_regex_extrae_NxM(monkeypatch):
    req = _sin_terreno(monkeypatch, "Departamento pequeño de 6 x 10 metros con una sala.")
    assert {req.ancho_terreno_m, req.largo_terreno_m} == {6.0, 10.0}


def test_fallback_regex_extrae_NxM_sin_unidad(monkeypatch):
    req = _sin_terreno(monkeypatch, "Casa en un terreno de 11x20 m.")
    assert {req.ancho_terreno_m, req.largo_terreno_m} == {11.0, 20.0}


def test_fallback_regex_extrae_ingles(monkeypatch):
    req = _sin_terreno(monkeypatch, "House on a 10 x 20 meter lot.")
    assert {req.ancho_terreno_m, req.largo_terreno_m} == {10.0, 20.0}


def test_fallback_regex_extrae_area_con_palabra_terreno(monkeypatch):
    req = _sin_terreno(monkeypatch, "Tengo un terreno de 200 m2.")
    assert req.area_terreno_m2 == 200.0 or (req.ancho_terreno_m and req.largo_terreno_m)


def test_fallback_regex_no_actua_si_llm_ya_dio_terreno(monkeypatch):
    datos = {
        "tipo_proyecto": "vivienda",
        "ancho_terreno_m": 8.0,
        "largo_terreno_m": 15.0,
        "ambientes": [{"nombre": "sala", "cantidad": 1}],
    }
    monkeypatch.setattr(interpreter, "chat_con_reintentos", lambda **kw: _respuesta(datos))
    req = interpreter.interpretar_instruccion("Casa de 8x15 con sala.")
    assert req.ancho_terreno_m == 8.0
    assert req.largo_terreno_m == 15.0


def test_fallback_regex_no_actua_sin_patron(monkeypatch):
    with pytest.raises(ValueError, match="dimensiones"):
        _sin_terreno(monkeypatch, "Quiero una casa bonita.")


def test_interpretar_edicion_fuera_de_catalogo_da_mensaje_amigable(monkeypatch):
    datos = {"operaciones": [
        {"tipo": "modificar_area", "ambiente": "piscina", "area_objetivo": 0}
    ]}
    monkeypatch.setattr(
        edit_interpreter, "chat_con_reintentos", lambda **kw: _respuesta(datos)
    )
    with pytest.raises(ValueError, match="ambiente soportado") as info:
        edit_interpreter.interpretar_edicion("agrega una piscina")
    assert "validar" in str(info.value)
