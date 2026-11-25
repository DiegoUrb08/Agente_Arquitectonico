import json
from unittest.mock import patch, MagicMock

import ollama
import pytest

from src.ai import edit_interpreter, interpreter, ollama_client
from src.ai.ollama_client import OllamaError, chat_con_reintentos


def _respuesta(datos):
    return {"message": {"content": json.dumps(datos)}}


def _mockear_texto(monkeypatch, texto, modulo="interpreter"):
    """Helper: el provider de `src.ai.<modulo>` devuelve `texto` tal cual.

    El patch debe apuntar al módulo que importa get_provider, no a
    src.ai.providers: de lo contrario no surte efecto.
    """
    mock_provider = MagicMock()
    mock_provider.nombre = "mock"
    mock_provider.chat.return_value = {"message": {"content": texto}}
    monkeypatch.setattr(
        f"src.ai.{modulo}.get_provider",
        lambda provider_name=None: mock_provider
    )
    return mock_provider


def _mockear_provider(monkeypatch, datos, modulo="interpreter"):
    """Helper: el provider devuelve `datos` serializados como JSON."""
    return _mockear_texto(monkeypatch, json.dumps(datos), modulo)


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
    _mockear_provider(monkeypatch, datos)

    req = interpreter.interpretar_instruccion("casa de 200 m2")

    assert req.ancho_terreno_m and req.largo_terreno_m
    assert req.area_total_vivienda_m2 > 0
    assert all(a.area_objetivo_m2 > 0 for a in req.ambientes)


def test_interpretar_instruccion_vacia():
    with pytest.raises(ValueError):
        interpreter.interpretar_instruccion("   ")


def test_interpretar_instruccion_json_invalido(monkeypatch):
    _mockear_texto(monkeypatch, "no es json")
    with pytest.raises(ValueError, match="JSON invalido"):
        interpreter.interpretar_instruccion("casa")


def test_interpretar_instruccion_esquema_invalido(monkeypatch):
    _mockear_provider(monkeypatch, {"ambientes": "no es lista"})
    with pytest.raises(ValueError, match="validar"):
        interpreter.interpretar_instruccion("casa")


# ---------------- interpretar_edicion ----------------

def test_interpretar_edicion_valida(monkeypatch):
    datos = {"operaciones": [
        {"tipo": "modificar_area", "ambiente": "Sala", "area_objetivo": 16}
    ]}
    _mockear_provider(monkeypatch, datos, modulo="edit_interpreter")
    solicitud = edit_interpreter.interpretar_edicion("sala a 16 m2")
    assert solicitud.operaciones[0].area_objetivo == 16


def test_interpretar_edicion_incluye_esquema_en_el_prompt(monkeypatch):
    """Groq/proxy no tienen salida estructurada nativa: el esquema va en el prompt."""
    datos = {"operaciones": [
        {"tipo": "modificar_area", "ambiente": "Sala", "area_objetivo": 16}
    ]}
    mock_provider = _mockear_provider(monkeypatch, datos, modulo="edit_interpreter")
    edit_interpreter.interpretar_edicion("sala a 16 m2")

    kwargs = mock_provider.chat.call_args.kwargs
    sistema = kwargs["messages"][0]["content"]
    assert "operaciones" in sistema and "modificar_area" in sistema
    assert "format" not in kwargs, "solo Ollama recibe format="


def test_interpretar_edicion_con_ollama_usa_salida_estructurada(monkeypatch):
    datos = {"operaciones": [
        {"tipo": "modificar_area", "ambiente": "Sala", "area_objetivo": 16}
    ]}
    mock_provider = _mockear_provider(monkeypatch, datos, modulo="edit_interpreter")
    mock_provider.nombre = "ollama"
    edit_interpreter.interpretar_edicion("sala a 16 m2")

    assert mock_provider.chat.call_args.kwargs["format"]["type"] == "object"


def test_interpretar_edicion_rechaza_operacion_incompleta(monkeypatch):
    datos = {"operaciones": [{"tipo": "modificar_area", "ambiente": "Sala"}]}
    _mockear_provider(monkeypatch, datos, modulo="edit_interpreter")
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


# ---------------- reintentos de OllamaProvider ----------------

def _ollama_provider(monkeypatch, cliente):
    from src.ai.providers.ollama_provider import OllamaProvider

    monkeypatch.setattr("src.ai.providers.ollama_provider.time.sleep", lambda s: None)
    provider = OllamaProvider(host="http://localhost:11434", reintentos=2)
    provider.ollama = MagicMock()
    provider.ollama.Client.return_value = cliente
    provider.ollama.ResponseError = ollama.ResponseError
    return provider


def test_ollama_provider_reintenta_y_se_recupera(monkeypatch):
    cliente = _ClienteFalso(fallos=2, error=ConnectionError("caído"))
    provider = _ollama_provider(monkeypatch, cliente)

    r = provider.chat(messages=[])

    assert r["message"]["content"] == "ok"
    assert cliente.llamadas == 3


def test_ollama_provider_agota_reintentos(monkeypatch):
    cliente = _ClienteFalso(fallos=99, error=ConnectionError("caído"))
    provider = _ollama_provider(monkeypatch, cliente)

    with pytest.raises(RuntimeError, match="No se pudo conectar a Ollama"):
        provider.chat(messages=[])

    assert cliente.llamadas == 3


def test_ollama_provider_no_reintenta_errores_4xx(monkeypatch):
    cliente = _ClienteFalso(
        fallos=99, error=ollama.ResponseError("modelo no existe", 404)
    )
    provider = _ollama_provider(monkeypatch, cliente)

    with pytest.raises(RuntimeError):
        provider.chat(messages=[])

    assert cliente.llamadas == 1


def test_ollama_provider_reenvia_la_temperatura(monkeypatch):
    recibido = {}

    class _Cliente:
        def chat(self, **kwargs):
            recibido.update(kwargs)
            return {"message": {"content": "ok"}}

    provider = _ollama_provider(monkeypatch, _Cliente())
    provider.chat(messages=[], temperature=0.1)

    assert recibido["options"]["temperature"] == 0.1


# ---------------- fallback regex del terreno ----------------

DATOS_SIN_TERRENO = {
    "tipo_proyecto": "vivienda",
    "ambientes": [{"nombre": "sala", "cantidad": 1}],
}


@pytest.mark.parametrize("prompt, ancho, largo", [
    ("vivienda en un terreno de 6 x 10 metros con sala", 6.0, 10.0),
    ("casa de 11 x 20 m para una familia de 5 personas", 11.0, 20.0),
    ("house on a 10 x 20 meter lot with a living room", 10.0, 20.0),
])
def test_fallback_regex_extrae_dimensiones_si_el_modelo_las_omite(
    monkeypatch, prompt, ancho, largo
):
    _mockear_provider(monkeypatch, DATOS_SIN_TERRENO)

    req = interpreter.interpretar_instruccion(prompt)

    assert (req.ancho_terreno_m, req.largo_terreno_m) == (ancho, largo)


def test_fallback_regex_extrae_area_del_terreno(monkeypatch):
    _mockear_provider(monkeypatch, DATOS_SIN_TERRENO)

    req = interpreter.interpretar_instruccion("casa en un terreno de 200 m2 con sala")

    assert req.ancho_terreno_m and req.largo_terreno_m
    assert req.ancho_terreno_m * req.largo_terreno_m == pytest.approx(200, rel=0.05)


def test_fallback_regex_no_pisa_lo_que_extrajo_el_modelo(monkeypatch):
    datos = {**DATOS_SIN_TERRENO, "ancho_terreno_m": 10.0, "largo_terreno_m": 20.0}
    _mockear_provider(monkeypatch, datos)

    req = interpreter.interpretar_instruccion("casa con sala, patio de 6 x 10 metros")

    assert (req.ancho_terreno_m, req.largo_terreno_m) == (10.0, 20.0)


def test_interpretar_edicion_fuera_de_catalogo_da_mensaje_amigable(monkeypatch):
    datos = {"operaciones": [
        {"tipo": "modificar_area", "ambiente": "piscina", "area_objetivo": 0}
    ]}
    _mockear_provider(monkeypatch, datos, modulo="edit_interpreter")
    with pytest.raises(ValueError, match="ambiente soportado") as info:
        edit_interpreter.interpretar_edicion("agrega una piscina")
    assert "validar" in str(info.value)
