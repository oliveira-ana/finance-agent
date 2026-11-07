import pytest

from app import config
from app.agente import criar_agente


@pytest.fixture(autouse=True)
def sem_dotenv(monkeypatch):
    monkeypatch.setattr(config, "load_dotenv", lambda: None)


def test_carrega_chave_e_modelo(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-teste")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o")
    cfg = config.carregar_config()
    assert cfg.openai_api_key == "sk-teste"
    assert cfg.openai_model == "gpt-4o"


def test_modelo_padrao(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-teste")
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    assert config.carregar_config().openai_model == config.MODELO_PADRAO


def test_sem_chave_falha(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        config.carregar_config()


def test_cria_agente_sem_chamar_api():
    agente = criar_agente(config.Config(openai_api_key="sk-teste", openai_model="gpt-4o-mini"))
    assert "finanças" in agente.system_prompt
