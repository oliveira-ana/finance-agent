from datetime import date

import pytest

from app.operacoes import AprovacaoNecessaria, ErroOperacao, formatar_reais, para_centavos
from app.permissoes import AcessoNegado


@pytest.mark.parametrize(
    ("texto", "centavos"),
    [("150", 15_000), ("150,5", 15_050), ("1.234,56", 123_456), ("R$ 200,00", 20_000), ("1.000", 100_000),
     ("99.90", 9_990), (40, 4_000)],
)
def test_rn01_conversao_de_valor(texto, centavos):
    assert para_centavos(texto) == centavos


@pytest.mark.parametrize("texto", ["0", "-10", "abc", "10,123", "", "nan"])
def test_rn01_valor_invalido(texto):
    with pytest.raises(ErroOperacao):
        para_centavos(texto)


def test_formatar_reais():
    assert formatar_reais(125_000) == "R$ 1.250,00"
    assert formatar_reais(5) == "R$ 0,05"
    assert formatar_reais(123_456_789) == "R$ 1.234.567,89"


def test_ca06_saque_dentro_do_padrao(srv):
    assert srv.banco.motivo_aprovacao_saque("0001-1", 50_000) is None
    assert srv.banco.motivo_aprovacao_saque("0001-1", 60_000) is None


def test_ca07_saque_fora_do_padrao(srv):
    motivo = srv.banco.motivo_aprovacao_saque("0001-1", 70_000)
    assert motivo == "3,5x a média dos últimos 10 saques (R$ 200,00)"


def test_ca18_cliente_sem_historico(srv):
    assert srv.banco.motivo_aprovacao_saque("0002-2", 100_000) is None
    assert "menos de 3 saques" in srv.banco.motivo_aprovacao_saque("0002-2", 120_000)


def test_rn08_limite_do_estorno(srv):
    assert srv.banco.motivo_aprovacao_estorno("0002-2", 100_000) is None
    assert srv.banco.motivo_aprovacao_estorno("0002-2", 100_001) == "estorno acima de R$ 1.000,00"


def test_ca05_saldo_insuficiente(srv, login):
    with pytest.raises(ErroOperacao, match="Saldo insuficiente"):
        srv.banco.sacar(login("joao"), 300_001)
    assert srv.repo.buscar_conta("0002-2")["saldo_centavos"] == 300_000


def test_saque_fora_do_padrao_sem_aprovador_nao_executa(srv, login):
    with pytest.raises(AprovacaoNecessaria):
        srv.banco.sacar(login("maria"), 70_000)
    movimentacao = srv.banco.sacar(login("maria"), 70_000, aprovado_por="carlos")
    assert movimentacao["aprovado_por"] == "carlos"
    assert srv.repo.buscar_conta("0001-1")["saldo_centavos"] == 380_000


def test_deposito_e_saque(srv, login):
    maria = login("maria")
    srv.banco.depositar(maria, 10_000)
    srv.banco.sacar(maria, 5_000)
    assert srv.repo.buscar_conta("0001-1")["saldo_centavos"] == 455_000


def test_rn09_atendente_nao_saca_nem_deposita(srv, login):
    paula = login("paula")
    with pytest.raises(AcessoNegado):
        srv.banco.sacar(paula, 100)
    with pytest.raises(AcessoNegado):
        srv.banco.depositar(paula, 100)


def test_cliente_nao_estorna(srv, login):
    with pytest.raises(AcessoNegado):
        srv.banco.estornar(login("maria"), "0001-1", 100, "motivo qualquer")


def test_rn07_estorno_exige_motivo(srv, login):
    with pytest.raises(ErroOperacao, match="motivo"):
        srv.banco.estornar(login("paula"), "0002-2", 30_000, "curto")


def test_extrato_padrao_ultimos_30_dias(srv):
    inicio, fim, itens = srv.banco.extrato("0001-1")
    assert (inicio, fim) == (date(2026, 10, 8), date(2026, 11, 7))
    assert [m["tipo"] for m in itens] == ["SAQUE", "SAQUE"]
    assert itens[0]["data_hora"] > itens[-1]["data_hora"]


def test_extrato_periodo_e_validacao(srv):
    _, _, itens = srv.banco.extrato("0001-1", date(2026, 7, 1), date(2026, 7, 31))
    assert {m["tipo"] for m in itens} == {"DEPOSITO", "SAQUE"}
    with pytest.raises(ErroOperacao):
        srv.banco.extrato("0001-1", date(2026, 8, 1), date(2026, 7, 1))
    with pytest.raises(ErroOperacao):
        srv.banco.extrato("9999-9")
