import json

from app import lgpd
from app.lgpd import abreviar_nome, mascarar_cpf, mascarar_email, mascarar_telefone, mascarar_texto


def test_mascaras():
    assert mascarar_cpf("123.456.789-09") == "***.456.789-**"
    assert mascarar_cpf("12345678909") == "***.456.789-**"
    assert mascarar_email("maria@exemplo.com") == "m***@exemplo.com"
    assert mascarar_telefone("(11) 98765-4321") == "(11) *****-4321"
    assert mascarar_telefone("11987654321") != "11987654321"
    assert abreviar_nome("Maria Souza") == "Maria S."
    assert abreviar_nome("Maria") == "Maria"


def test_mascarar_texto_preserva_valores_contas_e_datas():
    texto = "saca 4000 da conta 0001-1 em 2026-11-07 às 15:30, R$ 1.234,56"
    assert mascarar_texto(texto) == texto


def test_mascarar_texto_em_frase():
    texto = "meu cpf é 123.456.789-09, email maria@exemplo.com e fone (11) 98765-4321"
    mascarado = mascarar_texto(texto)
    assert mascarado == "meu cpf é ***.456.789-**, email m***@exemplo.com e fone (11) *****-4321"


def test_auditoria_grava_mascarado(srv):
    srv.auditoria.registrar("TESTE", "OK", detalhe="cpf 123.456.789-09 e maria@exemplo.com")
    conteudo = srv.auditoria.arquivo.read_text(encoding="utf-8")
    assert "123.456.789-09" not in conteudo and "maria@exemplo.com" not in conteudo


def test_meus_dados_completo_e_auditado(srv, login):
    texto = lgpd.meus_dados(login("maria"), srv)
    for dado in ("Maria Souza", "123.456.789-09", "maria@exemplo.com", "(11) 98765-4321", "0001-1"):
        assert dado in texto
    assert srv.auditoria.eventos()[-1]["acao"] == "MEUS_DADOS"
    assert "123.456.789-09" not in srv.auditoria.arquivo.read_text(encoding="utf-8")


def _criar_sessao(srv, sessao):
    srv.indice.registrar(sessao, srv.config.agora())
    pasta = srv.config.dir_sessoes / f"session_{sessao.session_id}"
    pasta.mkdir(parents=True)
    (pasta / "session.json").write_text("{}", encoding="utf-8")
    return pasta


def test_apagar_historico_so_do_titular(srv, login):
    maria1, maria2, joao = login("maria"), login("maria"), login("joao")
    pastas_maria = [_criar_sessao(srv, maria1), _criar_sessao(srv, maria2)]
    pasta_joao = _criar_sessao(srv, joao)
    movimentacoes_antes = srv.repo.caminho("movimentacoes.json").read_text(encoding="utf-8")
    assert lgpd.apagar_historico(maria2, srv) == 2
    assert not any(p.exists() for p in pastas_maria)
    assert pasta_joao.exists()
    assert srv.indice.do_usuario("maria") == []
    assert srv.repo.caminho("movimentacoes.json").read_text(encoding="utf-8") == movimentacoes_antes
    assert srv.auditoria.eventos()[-1]["acao"] == "APAGAR_HISTORICO"


def test_retencao(srv, login, relogio):
    antiga = _criar_sessao(srv, login("maria"))
    relogio.avancar(days=91)
    recente = _criar_sessao(srv, login("joao"))
    srv.auditoria.arquivo.write_text(
        json.dumps({"data_hora": "2020-01-01T00:00:00-03:00", "acao": "VELHO"}) + "\n"
        + srv.auditoria.arquivo.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    assert lgpd.aplicar_retencao(srv) == (1, 1)
    assert not antiga.exists() and recente.exists()
    acoes = [e["acao"] for e in srv.auditoria.eventos()]
    assert "VELHO" not in acoes and "CARGA_INICIAL" in acoes
    assert acoes[-1] == "RETENCAO"
