from decimal import Decimal

import pytest

from app import config


@pytest.fixture(autouse=True)
def sem_dotenv(monkeypatch):
    monkeypatch.setattr(config, "load_dotenv", lambda: None)
    for nome in (
        "OPENAI_MODEL",
        "DADOS_DIR",
        "FUSO",
        "SAQUE_MULTIPLICADOR_MEDIA",
        "ESTORNO_LIMITE",
        "PIN_TENTATIVAS",
        "SAQUE_LIMITE_SEM_HISTORICO",
    ):
        monkeypatch.delenv(nome, raising=False)


def test_carrega_chave_e_modelo(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-teste")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o")
    cfg = config.carregar_config()
    assert cfg.openai_api_key == "sk-teste"
    assert cfg.openai_model == "gpt-4o"


def test_modelo_padrao(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-teste")
    assert config.carregar_config().openai_model == config.MODELO_PADRAO


def test_sem_chave_falha(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        config.carregar_config()


def test_chave_de_exemplo_conta_como_ausente(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", config.CHAVE_EXEMPLO)
    with pytest.raises(RuntimeError):
        config.carregar_config()
    assert config.carregar_config(exigir_chave=False).openai_api_key == ""


def test_parametros_padrao(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-teste")
    cfg = config.carregar_config()
    assert cfg.saque_multiplicador_media == Decimal("3")
    assert cfg.saque_qtd_media == 10
    assert cfg.estorno_limite_centavos == 100_000
    assert cfg.pin_tentativas == 3
    assert cfg.pin_bloqueio_min == 15
    assert cfg.extrato_dias_padrao == 30
    assert cfg.saque_min_historico == 3
    assert cfg.saque_limite_sem_historico_centavos == 100_000
    assert cfg.max_tools_por_mensagem == 5
    assert cfg.retencao_sessoes_dias == 90
    assert cfg.retencao_auditoria_anos == 5
    assert cfg.dados_dir == config.RAIZ_PROJETO / "dados"
    assert cfg.dir_sessoes == cfg.dados_dir / "sessoes"
    assert cfg.agora().utcoffset() is not None


def test_parametros_do_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-teste")
    monkeypatch.setenv("SAQUE_MULTIPLICADOR_MEDIA", "2,5")
    monkeypatch.setenv("ESTORNO_LIMITE", "500.50")
    monkeypatch.setenv("PIN_TENTATIVAS", "5")
    cfg = config.carregar_config()
    assert cfg.saque_multiplicador_media == Decimal("2.5")
    assert cfg.estorno_limite_centavos == 50_050
    assert cfg.pin_tentativas == 5


@pytest.mark.parametrize(
    ("nome", "valor"),
    [("PIN_TENTATIVAS", "abc"), ("PIN_TENTATIVAS", "0"), ("ESTORNO_LIMITE", "-1"), ("FUSO", "Lugar/Nenhum")],
)
def test_parametro_invalido_falha(monkeypatch, nome, valor):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-teste")
    monkeypatch.setenv(nome, valor)
    with pytest.raises(RuntimeError):
        config.carregar_config()
