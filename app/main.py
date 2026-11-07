from __future__ import annotations

import getpass
import sys
from collections.abc import Callable

from app import lgpd
from app.agente import criar_agente
from app.aprovacao import Terminal, TerminalConsole
from app.auth import LoginRecusado
from app.config import carregar_config
from app.servicos import Servicos, montar_servicos
from app.sessao import SessaoUsuario, nova_sessao

COMANDOS_SAIR = {"sair", "exit", "quit"}
COMANDO_LOGOUT = "logout"
COMANDO_MEUS_DADOS = "meus dados"
COMANDOS_APAGAR = {"apagar meu histórico", "apagar meu historico"}
AVISO_TRANSPARENCIA = (
    "Aviso: este é um assistente de IA. Suas mensagens são processadas pela OpenAI, com CPF, e-mail e telefone "
    "mascarados, e a conversa fica guardada neste computador por {dias} dias.\n"
    "Comandos: 'meus dados', 'apagar meu histórico', 'logout', 'sair'."
)


def ler(pergunta: str) -> str | None:
    try:
        return input(pergunta)
    except (EOFError, KeyboardInterrupt):
        return None


def fazer_login(srv: Servicos) -> SessaoUsuario | None:
    while True:
        usuario = ler("\nUsuário (ou 'sair'): ")
        if usuario is None or usuario.strip().lower() in COMANDOS_SAIR:
            return None
        if not usuario.strip():
            continue
        try:
            pin = getpass.getpass("PIN: ")
        except (EOFError, KeyboardInterrupt):
            return None
        try:
            return srv.autenticador.autenticar(usuario, pin)
        except LoginRecusado as erro:
            print(erro)


def mensagem_erro_modelo(erro: Exception) -> str:
    nome = type(erro).__name__
    if "Authentication" in nome or "PermissionDenied" in nome:
        return "Não foi possível acessar a OpenAI: confira a OPENAI_API_KEY no .env."
    if "Connection" in nome or "Timeout" in nome:
        return "Sem conexão com a OpenAI. Tente de novo em instantes."
    if "Throttl" in nome or "RateLimit" in nome:
        return "A OpenAI está limitando as requisições. Aguarde um pouco e tente de novo."
    return "Não consegui processar seu pedido agora. Tente de novo; operações já confirmadas aparecem no extrato."


def conversar(
    sessao: SessaoUsuario,
    srv: Servicos,
    terminal: Terminal,
    fabrica_agente: Callable = criar_agente,
) -> bool:
    """Loop do chat de um login. Devolve True se o usuário pediu para sair do programa."""
    config = srv.config
    srv.indice.registrar(sessao, config.agora())
    agente = fabrica_agente(config, sessao, terminal, srv)
    print(f"\nOlá, {sessao.primeiro_nome} ({sessao.perfil}). Como posso ajudar?")
    print(AVISO_TRANSPARENCIA.format(dias=config.retencao_sessoes_dias))
    try:
        while True:
            texto = ler("\nVocê: ")
            if texto is None:
                return True
            comando = " ".join(texto.lower().split())
            if not comando:
                continue
            if comando in COMANDOS_SAIR:
                return True
            if comando == COMANDO_LOGOUT:
                return False
            if comando == COMANDO_MEUS_DADOS:
                print(lgpd.meus_dados(sessao, srv))
                continue
            if comando in COMANDOS_APAGAR:
                aviso = (
                    "Apagar todo o seu histórico de conversas? Movimentações e auditoria são mantidas por "
                    "obrigação legal."
                )
                if terminal.confirmar(aviso):
                    quantidade = lgpd.apagar_historico(sessao, srv)
                    sessao = nova_sessao(sessao)
                    srv.indice.registrar(sessao, config.agora())
                    agente = fabrica_agente(config, sessao, terminal, srv)
                    print(f"{quantidade} conversa(s) apagada(s). Começamos uma conversa nova.")
                continue
            print()
            try:
                agente(lgpd.mascarar_texto(texto))
            except KeyboardInterrupt:
                print("\nPedido interrompido.")
            except Exception as erro:
                srv.auditoria.registrar("AGENTE", "ERRO", sessao=sessao, detalhe=type(erro).__name__)
                print(mensagem_erro_modelo(erro))
            print()
    finally:
        srv.indice.encerrar(sessao.session_id, config.agora())
        srv.auditoria.registrar("LOGOUT", "OK", sessao=sessao)


def main() -> int:
    try:
        config = carregar_config()
    except RuntimeError as erro:
        print(erro)
        return 1
    srv = montar_servicos(config)
    if not srv.repo.existe_base():
        print(f"Base de dados não encontrada em {config.dados_dir}. Rode primeiro: python -m app.carga_inicial")
        return 1
    lgpd.aplicar_retencao(srv)
    terminal = TerminalConsole()
    print("Finance Agent — chat bancário. Digite 'sair' para encerrar.")
    while True:
        sessao = fazer_login(srv)
        if sessao is None or conversar(sessao, srv, terminal):
            break
    print("Até logo!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
