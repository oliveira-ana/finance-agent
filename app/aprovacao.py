from __future__ import annotations

import getpass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.auth import Autenticador
    from app.sessao import SessaoUsuario

RESPOSTAS_SIM = {"s", "sim", "y", "yes"}


class Terminal(Protocol):
    """Interação feita pelo código, fora da IA. Os testes usam uma versão falsa."""

    def avisar(self, mensagem: str) -> None: ...

    def confirmar(self, resumo: str) -> bool: ...

    def credenciais_aprovador(self) -> tuple[str, str]: ...

    def decisao_aprovador(self, resumo: str) -> bool: ...


class TerminalConsole:
    def avisar(self, mensagem: str) -> None:
        print(f"\n{mensagem}")

    def _perguntar_sim_nao(self, pergunta: str) -> bool:
        try:
            return input(pergunta).strip().lower() in RESPOSTAS_SIM
        except (EOFError, KeyboardInterrupt):
            return False

    def confirmar(self, resumo: str) -> bool:
        print(f"\n{resumo}")
        return self._perguntar_sim_nao("Confirma? (sim/não): ")

    def credenciais_aprovador(self) -> tuple[str, str]:
        print("\nAprovador, informe suas credenciais.")
        try:
            return input("Usuário aprovador: ").strip(), getpass.getpass("PIN: ")
        except (EOFError, KeyboardInterrupt):
            return "", ""

    def decisao_aprovador(self, resumo: str) -> bool:
        print(f"\n{resumo}")
        return self._perguntar_sim_nao("Aprovador: aprova a operação? (sim/não): ")


def solicitar_aprovacao(
    terminal: Terminal,
    autenticador: Autenticador,
    solicitante: SessaoUsuario,
    resumo: str,
    motivo: str,
) -> str | None:
    """RF01.8: devolve o usuário do aprovador quando a operação foi aprovada, ou None."""
    terminal.avisar(f"Esta operação precisa de aprovação: {motivo}.")
    usuario, pin = terminal.credenciais_aprovador()
    aprovador = autenticador.validar_aprovador(usuario, pin, solicitante.usuario)
    if aprovador is None:
        terminal.avisar("Credenciais de aprovador inválidas. A operação não foi aprovada.")
        return None
    if not terminal.decisao_aprovador(resumo):
        terminal.avisar("Operação rejeitada pelo aprovador.")
        return None
    return aprovador
