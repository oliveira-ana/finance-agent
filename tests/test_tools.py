import json

import pytest

from app.tools import criar_tools
from tests.conftest import TerminalFalso


def ferramentas(sessao, terminal, srv):
    return {t.tool_name: t for t in criar_tools(sessao, terminal, srv)}


def saldo(srv, conta):
    return srv.repo.buscar_conta(conta)["saldo_centavos"]


def ultimo_evento(srv, acao):
    return [e for e in srv.auditoria.eventos() if e["acao"] == acao][-1]


def test_tools_por_perfil(srv, login, terminal):
    assert set(ferramentas(login("maria"), terminal, srv)) == {"consultar_saldo", "consultar_extrato", "depositar", "sacar"}
    assert set(ferramentas(login("paula"), terminal, srv)) == {"consultar_saldo", "consultar_extrato", "estornar"}


def test_ca03_cliente_ve_o_proprio_saldo(srv, login, terminal):
    resposta = ferramentas(login("maria"), terminal, srv)["consultar_saldo"]()
    assert resposta == {"resultado": "OK", "conta": "0001-1", "titular": "Maria", "saldo": "R$ 4.500,00"}


def test_ca04_cliente_pede_outra_conta(srv, login, terminal):
    tools = ferramentas(login("maria"), terminal, srv)
    for nome in ("consultar_saldo", "consultar_extrato"):
        resposta = tools[nome](conta="0002-2")
        assert resposta["resultado"] == "NEGADO"
        assert "R$" not in json.dumps(resposta)
    evento = ultimo_evento(srv, "CONSULTAR_EXTRATO")
    assert (evento["resultado"], evento["conta"], evento["usuario"]) == ("NEGADO", "0002-2", "maria")


def test_deposito_com_confirmacao(srv, login, terminal):
    resposta = ferramentas(login("maria"), terminal, srv)["depositar"](valor="200,00")
    assert resposta["novo_saldo"] == "R$ 4.700,00"
    assert terminal.confirmacoes == ["Depósito de R$ 200,00 na conta 0001-1."]


def test_deposito_cancelado_nao_altera_saldo(srv, login):
    resposta = ferramentas(login("maria"), TerminalFalso(confirmar=False), srv)["depositar"](valor="200")
    assert resposta["resultado"] == "CANCELADO"
    assert saldo(srv, "0001-1") == 450_000
    assert ultimo_evento(srv, "DEPOSITO")["resultado"] == "REJEITADO"


def test_valor_invalido_volta_mensagem_curta(srv, login, terminal):
    resposta = ferramentas(login("maria"), terminal, srv)["depositar"](valor="dez reais")
    assert resposta == {"resultado": "ERRO", "mensagem": "Valor inválido. Use, por exemplo, 150,00."}


def test_ca05_saque_sem_saldo(srv, login, terminal):
    resposta = ferramentas(login("joao"), terminal, srv)["sacar"](valor="3500")
    assert resposta["mensagem"] == "Saldo insuficiente."
    assert terminal.confirmacoes == []


def test_ca06_saque_no_padrao_sem_aprovador(srv, login, terminal):
    resposta = ferramentas(login("maria"), terminal, srv)["sacar"](valor="500")
    assert resposta["resultado"] == "OK"
    assert terminal.pedidos_credenciais == 0
    assert saldo(srv, "0001-1") == 400_000


def test_ca07_ca08_saque_fora_do_padrao_aprovado(srv, login, terminal):
    maria = login("maria")
    tools = ferramentas(maria, terminal, srv)
    resposta = tools["sacar"](valor="700")
    assert terminal.pedidos_credenciais == 1
    assert resposta["aprovado_por"] == "carlos"
    assert saldo(srv, "0001-1") == 380_000
    extrato = tools["consultar_extrato"]()
    assert extrato["movimentacoes"][0]["aprovado_por"] == "carlos"
    assert "aprovado por carlos" in ultimo_evento(srv, "SAQUE")["detalhe"]


@pytest.mark.parametrize(
    "terminal_aprovacao",
    [TerminalFalso(aprovar=False), TerminalFalso(credenciais=("carlos", "0000"))],
    ids=["aprovador-rejeita", "pin-errado"],
)
def test_ca09_aprovacao_rejeitada(srv, login, terminal_aprovacao):
    resposta = ferramentas(login("maria"), terminal_aprovacao, srv)["sacar"](valor="700")
    assert resposta["resultado"] == "REJEITADO"
    assert saldo(srv, "0001-1") == 450_000
    assert ultimo_evento(srv, "SAQUE")["resultado"] == "REJEITADO"


@pytest.mark.parametrize("credenciais", [("joao", "2222"), ("paula", "3333"), ("maria", "1111")])
def test_ca10_credenciais_de_cliente_ou_atendente(srv, login, credenciais):
    resposta = ferramentas(login("maria"), TerminalFalso(credenciais=credenciais), srv)["sacar"](valor="700")
    assert resposta["resultado"] == "REJEITADO"
    assert saldo(srv, "0001-1") == 450_000


def test_ca11_atendente_consulta_cliente(srv, login, terminal):
    tools = ferramentas(login("paula"), terminal, srv)
    por_conta = tools["consultar_saldo"](conta="0001-1")
    por_usuario = tools["consultar_saldo"](conta="maria")
    assert por_conta == por_usuario == {"resultado": "OK", "conta": "0001-1", "titular": "Maria S.", "saldo": "R$ 4.500,00"}
    assert tools["consultar_extrato"](conta="joao")["movimentacoes"] == []
    assert tools["consultar_saldo"]()["resultado"] == "ERRO"
    assert tools["consultar_saldo"](conta="carlos")["mensagem"] == "Conta não encontrada."


def test_ca12_estorno_sem_motivo(srv, login, terminal):
    resposta = ferramentas(login("paula"), terminal, srv)["estornar"](conta="0002-2", valor="300", motivo="")
    assert "motivo" in resposta["mensagem"]
    assert saldo(srv, "0002-2") == 300_000
    assert terminal.confirmacoes == []


def test_ca13_estorno_com_motivo(srv, login, terminal):
    tools = ferramentas(login("paula"), terminal, srv)
    resposta = tools["estornar"](conta="0002-2", valor="300", motivo="Tarifa cobrada indevidamente")
    assert resposta["resultado"] == "OK" and "aprovado_por" not in resposta
    assert saldo(srv, "0002-2") == 330_000
    item = tools["consultar_extrato"](conta="0002-2")["movimentacoes"][0]
    assert (item["tipo"], item["motivo"]) == ("Estorno", "Tarifa cobrada indevidamente")
    assert ultimo_evento(srv, "ESTORNO")["usuario"] == "paula"


def test_ca14_estorno_acima_do_limite_pede_aprovador(srv, login, terminal):
    resposta = ferramentas(login("paula"), terminal, srv)["estornar"](
        conta="0002-2", valor="1500", motivo="Cobrança duplicada no cartão"
    )
    assert terminal.pedidos_credenciais == 1
    assert resposta["aprovado_por"] == "carlos"
    assert saldo(srv, "0002-2") == 450_000


def test_ca15_atendente_nao_tem_tool_de_saque(srv, login, terminal):
    tools = ferramentas(login("paula"), terminal, srv)
    assert "sacar" not in tools and "depositar" not in tools


def test_ca16_tool_nao_aceita_aprovacao_por_parametro(srv, login, terminal):
    sacar = ferramentas(login("maria"), terminal, srv)["sacar"]
    assert set(sacar.tool_spec["inputSchema"]["json"]["properties"]) == {"valor"}
    resposta = ferramentas(login("maria"), TerminalFalso(credenciais=("", "")), srv)["sacar"](valor="700")
    assert resposta["resultado"] == "REJEITADO"
    assert saldo(srv, "0001-1") == 450_000


def test_ca18_cliente_sem_historico_pede_aprovador(srv, login, terminal):
    ferramentas(login("joao"), terminal, srv)["sacar"](valor="1200")
    assert terminal.pedidos_credenciais == 1


def test_ca17_retorno_das_tools_sem_dados_pessoais(srv, login, terminal):
    tools = ferramentas(login("paula"), terminal, srv)
    texto = json.dumps([tools["consultar_saldo"](conta="maria"), tools["consultar_extrato"](conta="maria")])
    for dado in ("123.456.789-09", "maria@exemplo.com", "98765-4321", "Souza", "pin"):
        assert dado not in texto


def test_motivo_do_estorno_mascarado(srv, login, terminal):
    ferramentas(login("paula"), terminal, srv)["estornar"](
        conta="0002-2", valor="10", motivo="Cliente CPF 987.654.321-00 cobrado em dobro"
    )
    conteudo = srv.repo.caminho("movimentacoes.json").read_text(encoding="utf-8")
    conteudo += srv.auditoria.arquivo.read_text(encoding="utf-8")
    assert "987.654.321-00" not in conteudo
    assert "***.654.321-**" in conteudo
