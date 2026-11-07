"""Correções dos achados ACH-02 a ACH-04 e da revisão do PR #1."""

import pytest

from app import main
from app.carga_inicial import gerar_base
from app.operacoes import ErroOperacao, para_centavos
from app.repositorio import BaseCorrompida
from tests.conftest import PINS


def test_ach02_saques_fracionados_no_mesmo_dia_pedem_aprovador(srv, login):
    srv.banco.sacar(login("maria"), 60_000)
    motivo = srv.banco.motivo_aprovacao_saque("0001-1", 60_000)
    assert motivo and "somando os saques de hoje (R$ 1.200,00)" in motivo


def test_ach02_saque_aprovado_nao_entra_no_acumulado(srv, login):
    srv.banco.sacar(login("maria"), 70_000, aprovado_por="carlos")
    assert srv.banco.motivo_aprovacao_saque("0001-1", 50_000) is None


def test_ach02_estornos_fracionados_pedem_aprovador(srv, login):
    srv.banco.estornar(login("paula"), "0002-2", 90_000, "cobrança duplicada no cartão")
    assert "somando os estornos de hoje" in srv.banco.motivo_aprovacao_estorno("0002-2", 90_000)
    assert srv.banco.motivo_aprovacao_estorno("0001-1", 90_000) is None


@pytest.mark.parametrize("valor", [-100, 0, "100", 1.5])
def test_banco_recusa_valor_invalido(srv, login, valor):
    maria = login("maria")
    with pytest.raises(ErroOperacao):
        srv.banco.depositar(maria, valor)
    with pytest.raises(ErroOperacao):
        srv.banco.sacar(maria, valor)
    with pytest.raises(ErroOperacao):
        srv.banco.estornar(login("paula"), "0001-1", valor, "motivo de teste válido")
    assert srv.repo.buscar_conta("0001-1")["saldo_centavos"] == 450_000


@pytest.mark.parametrize("texto", ["1e9", "1E3", "١٠٠", "1_000", "Infinity", "0x10", "-5", "1,2,3"])
def test_ach03_formatos_estranhos_recusados(texto):
    with pytest.raises(ErroOperacao):
        para_centavos(texto)


def test_ach03_valor_maximo_por_operacao(srv, login):
    with pytest.raises(ErroOperacao, match="máximo"):
        srv.banco.depositar(login("maria"), srv.config.valor_maximo_centavos + 1)


def test_recriar_base_apaga_conversas_e_mantem_auditoria(srv, login):
    sessao = login("maria")
    srv.indice.registrar(sessao, srv.config.agora())
    pasta = srv.config.dir_sessoes / f"session_{sessao.session_id}"
    pasta.mkdir(parents=True)
    gerar_base(srv.config, PINS, forcar=True, iteracoes=1_000)
    assert not pasta.exists()
    assert srv.indice.listar() == []
    assert [e["acao"] for e in srv.auditoria.eventos()].count("CARGA_INICIAL") == 2


def test_ach04_base_corrompida(srv):
    srv.repo.caminho("usuarios.json").write_text("{", encoding="utf-8")
    with pytest.raises(BaseCorrompida):
        srv.autenticador.autenticar("maria", PINS["maria"])


def test_ach04_main_mostra_mensagem_sem_traceback(srv, monkeypatch, capsys):
    srv.repo.caminho("usuarios.json").write_text("{", encoding="utf-8")
    monkeypatch.setattr(main, "carregar_config", lambda: srv.config)
    monkeypatch.setattr("builtins.input", lambda _="": "maria")
    monkeypatch.setattr(main.getpass, "getpass", lambda _="": PINS["maria"])
    assert main.main() == 1
    assert "corrompido" in capsys.readouterr().out
