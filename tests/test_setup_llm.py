"""Tests de setup_llm.py (siempre sobre un .env temporal, nunca el real)."""

from dotenv import dotenv_values

import setup_llm


def _entradas(monkeypatch, *respuestas):
    it = iter(respuestas)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(it))


def test_groq_crea_env_con_proveedor_y_clave(monkeypatch, tmp_path):
    monkeypatch.setattr(setup_llm, "ENV_FILE", tmp_path / ".env")
    _entradas(monkeypatch, "gsk_prueba")

    assert setup_llm.setup_groq() is True

    valores = dotenv_values(tmp_path / ".env")
    assert valores["LLM_PROVIDER"] == "groq"
    assert valores["GROQ_API_KEY"] == "gsk_prueba"


def test_no_borra_otras_claves_del_env_existente(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text("GROQ_API_KEY=gsk_vieja\nPROXY_ACCESS_TOKEN=secreto\n")
    monkeypatch.setattr(setup_llm, "ENV_FILE", env)
    _entradas(monkeypatch, "http://localhost:11434")

    setup_llm.setup_ollama()

    valores = dotenv_values(env)
    assert valores["LLM_PROVIDER"] == "ollama"
    assert valores["GROQ_API_KEY"] == "gsk_vieja"
    assert valores["PROXY_ACCESS_TOKEN"] == "secreto"


def test_proxy_guarda_token_solo_si_se_indica(monkeypatch, tmp_path):
    monkeypatch.setattr(setup_llm, "ENV_FILE", tmp_path / ".env")
    _entradas(monkeypatch, "https://demo.example.com", "")

    setup_llm.setup_proxy()

    valores = dotenv_values(tmp_path / ".env")
    assert valores["PROXY_URL"] == "https://demo.example.com"
    assert "PROXY_ACCESS_TOKEN" not in valores


def test_entrada_vacia_no_escribe_nada(monkeypatch, tmp_path):
    monkeypatch.setattr(setup_llm, "ENV_FILE", tmp_path / ".env")
    _entradas(monkeypatch, "")

    assert setup_llm.setup_groq() is False
    assert not (tmp_path / ".env").exists()


def test_claude_guarda_proveedor_y_clave(monkeypatch, tmp_path):
    monkeypatch.setattr(setup_llm, "ENV_FILE", tmp_path / ".env")
    _entradas(monkeypatch, "sk-ant-prueba")

    assert setup_llm.setup_claude() is True

    valores = dotenv_values(tmp_path / ".env")
    assert valores["LLM_PROVIDER"] == "claude"
    assert valores["ANTHROPIC_API_KEY"] == "sk-ant-prueba"


def test_el_menu_solo_ofrece_proveedores_que_get_provider_soporta(monkeypatch, capsys):
    _entradas(monkeypatch, "5")

    setup_llm.main()

    salida = capsys.readouterr().out
    for ofrecido in ("Groq", "Ollama", "Proxy", "Claude"):
        assert ofrecido in salida
    assert "OpenAI" not in salida
    assert "Mixtral" not in salida
