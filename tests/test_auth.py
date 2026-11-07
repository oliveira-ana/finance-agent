import pytest

from app.auth import MSG_APROVADOR_SEM_LOGIN, MSG_LOGIN_INVALIDO, LoginRecusado, gerar_hash, verificar_pin


def test_hash_com_salt_aleatorio():
    a = gerar_hash("1234", iteracoes=1_000)
    b = gerar_hash("1234", iteracoes=1_000)
    assert a["pin_hash"] != b["pin_hash"]
    assert verificar_pin("1234", a) and not verificar_pin("4321", a)
    assert "1234" not in a["pin_hash"]


def test_ca01_login_ok(srv):
    sessao = srv.autenticador.autenticar(" Maria ", "1111")
    assert (sessao.usuario, sessao.nome, sessao.perfil, sessao.conta) == ("maria", "Maria Souza", "cliente", "0001-1")
    assert len(sessao.session_id) == 32
    assert srv.auditoria.eventos()[-1]["acao"] == "LOGIN"


def test_cada_login_gera_session_id_novo(login):
    assert login("maria").session_id != login("maria").session_id


def test_pin_errado_mensagem_generica(srv):
    with pytest.raises(LoginRecusado, match=MSG_LOGIN_INVALIDO):
        srv.autenticador.autenticar("maria", "0000")
    with pytest.raises(LoginRecusado, match=MSG_LOGIN_INVALIDO):
        srv.autenticador.autenticar("ninguem", "0000")
    resultados = [e["resultado"] for e in srv.auditoria.eventos()]
    assert resultados.count("LOGIN_FALHOU") == 2


def test_ca02_bloqueio_apos_tentativas(srv, relogio):
    for _ in range(3):
        with pytest.raises(LoginRecusado):
            srv.autenticador.autenticar("maria", "0000")
    with pytest.raises(LoginRecusado):
        srv.autenticador.autenticar("maria", "1111")
    assert srv.auditoria.eventos()[-1]["resultado"] == "BLOQUEADO"
    relogio.avancar(minutes=16)
    assert srv.autenticador.autenticar("maria", "1111").usuario == "maria"


def test_acerto_zera_tentativas(srv):
    for _ in range(2):
        with pytest.raises(LoginRecusado):
            srv.autenticador.autenticar("maria", "0000")
    srv.autenticador.autenticar("maria", "1111")
    assert srv.repo.buscar_usuario("maria")["tentativas_erradas"] == 0


def test_ca19_aprovador_nao_abre_sessao(srv):
    with pytest.raises(LoginRecusado, match="aprovador"):
        srv.autenticador.autenticar("carlos", "4444")
    assert MSG_APROVADOR_SEM_LOGIN
    evento = srv.auditoria.eventos()[-1]
    assert (evento["acao"], evento["resultado"]) == ("LOGIN", "NEGADO")


def test_validar_aprovador(srv):
    assert srv.autenticador.validar_aprovador("carlos", "4444", "maria") == "carlos"
    assert srv.autenticador.validar_aprovador("carlos", "0000", "maria") is None


@pytest.mark.parametrize(("usuario", "pin"), [("maria", "1111"), ("paula", "3333")])
def test_ca10_credenciais_sem_perfil_aprovador(srv, usuario, pin):
    assert srv.autenticador.validar_aprovador(usuario, pin, "joao") is None


def test_rn10_aprovador_igual_ao_solicitante(srv):
    assert srv.autenticador.validar_aprovador("carlos", "4444", "carlos") is None


def test_pin_errado_do_aprovador_conta_para_bloqueio(srv):
    for _ in range(3):
        srv.autenticador.validar_aprovador("carlos", "0000", "maria")
    assert srv.autenticador.validar_aprovador("carlos", "4444", "maria") is None


def test_ca17_pin_nao_vai_para_auditoria(srv):
    srv.autenticador.autenticar("maria", "1111")
    with pytest.raises(LoginRecusado):
        srv.autenticador.autenticar("maria", "9876")
    conteudo = srv.auditoria.arquivo.read_text(encoding="utf-8")
    assert "1111" not in conteudo and "9876" not in conteudo
