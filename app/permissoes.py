from app.sessao import SessaoUsuario

PERMISSOES: dict[str, frozenset[str]] = {
    "cliente": frozenset({"consultar_saldo", "consultar_extrato", "depositar", "sacar"}),
    "atendente": frozenset({"consultar_saldo", "consultar_extrato", "estornar"}),
    "aprovador": frozenset(),
}
MSG_NAO_PERMITIDO = "Operação não permitida para o seu perfil."


class AcessoNegado(Exception):
    def __init__(self, mensagem: str = MSG_NAO_PERMITIDO):
        super().__init__(mensagem)


def pode(perfil: str, operacao: str) -> bool:
    return operacao in PERMISSOES.get(perfil, frozenset())


def exigir(sessao: SessaoUsuario, operacao: str) -> None:
    if not pode(sessao.perfil, operacao):
        raise AcessoNegado()
