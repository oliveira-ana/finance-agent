from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.servicos import Servicos
    from app.sessao import SessaoUsuario

_CPF = re.compile(r"(?<!\d)(\d{3})\.?(\d{3})\.?(\d{3})-?(\d{2})(?!\d)")
_EMAIL = re.compile(r"(?<![\w.%+-])([A-Za-z0-9])[A-Za-z0-9._%+-]*@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)")
_TELEFONE = re.compile(r"(?<!\d)\(?(\d{2})\)?[ ]?(?:9[ ]?)?\d{4}[- ]?(\d{4})(?!\d)")


def mascarar_cpf(cpf: str) -> str:
    return _CPF.sub(r"***.\2.\3-**", cpf)


def mascarar_email(email: str) -> str:
    return _EMAIL.sub(r"\1***@\2", email)


def mascarar_telefone(telefone: str) -> str:
    return _TELEFONE.sub(r"(\1) *****-\2", telefone)


def mascarar_texto(texto: str) -> str:
    """Mascara CPF, e-mail e telefone em qualquer texto livre (RN16)."""
    if not texto:
        return texto
    return mascarar_telefone(mascarar_email(mascarar_cpf(texto)))


def abreviar_nome(nome: str) -> str:
    """Nome de terceiro: 'Maria Souza' → 'Maria S.'."""
    partes = nome.split()
    if len(partes) < 2:
        return nome
    return f"{partes[0]} {partes[-1][0]}."


def meus_dados(sessao: SessaoUsuario, srv: Servicos) -> str:
    """Direito de acesso (art. 18): gerado pelo código, nunca passa pela OpenAI."""
    registro = srv.repo.buscar_usuario(sessao.usuario) or {}
    srv.auditoria.registrar("MEUS_DADOS", "OK", sessao=sessao, conta=sessao.conta)
    linhas = [
        "Seus dados (exibidos só aqui no terminal, sem passar pela OpenAI):",
        f"  Nome:     {registro.get('nome', '-')}",
        f"  CPF:      {registro.get('cpf', '-')}",
        f"  E-mail:   {registro.get('email', '-')}",
        f"  Telefone: {registro.get('telefone', '-')}",
        f"  Perfil:   {registro.get('perfil', '-')}",
        f"  Conta:    {registro.get('conta') or '-'}",
        f"As conversas ficam guardadas por {srv.config.retencao_sessoes_dias} dias. Movimentações e auditoria são "
        "mantidas por obrigação legal (LGPD, art. 16, I).",
    ]
    return "\n".join(linhas)


def _apagar_pastas_de_sessao(srv: Servicos, session_ids: set[str]) -> None:
    for session_id in session_ids:
        shutil.rmtree(srv.config.dir_sessoes / f"session_{session_id}", ignore_errors=True)


def apagar_historico(sessao: SessaoUsuario, srv: Servicos) -> int:
    """Direito de eliminação das conversas. Movimentações e auditoria são mantidas."""
    session_ids = set(srv.indice.do_usuario(sessao.usuario))
    _apagar_pastas_de_sessao(srv, session_ids)
    srv.indice.remover(session_ids)
    srv.auditoria.registrar(
        "APAGAR_HISTORICO", "OK", sessao=sessao, detalhe=f"{len(session_ids)} sessão(ões) apagada(s)"
    )
    return len(session_ids)


def _subtrair_anos(data: datetime, anos: int) -> datetime:
    try:
        return data.replace(year=data.year - anos)
    except ValueError:
        return data.replace(year=data.year - anos, day=28)


def _data_do_evento(linha: str) -> datetime | None:
    try:
        return datetime.fromisoformat(json.loads(linha)["data_hora"])
    except (ValueError, KeyError, TypeError):
        return None


def aplicar_retencao(srv: Servicos) -> tuple[int, int]:
    """RN15: apaga sessões com mais de N dias e eventos de auditoria com mais de N anos."""
    agora = srv.config.agora()
    limite_sessoes = agora - timedelta(days=srv.config.retencao_sessoes_dias)
    antigas = {
        item["session_id"]
        for item in srv.indice.listar()
        if datetime.fromisoformat(item["criada_em"]) < limite_sessoes
    }
    _apagar_pastas_de_sessao(srv, antigas)
    srv.indice.remover(antigas)

    limite_auditoria = _subtrair_anos(agora, srv.config.retencao_auditoria_anos)
    linhas = srv.auditoria.linhas()
    mantidas = [linha for linha in linhas if (data := _data_do_evento(linha)) is None or data >= limite_auditoria]
    eventos_removidos = len(linhas) - len(mantidas)
    if eventos_removidos:
        srv.auditoria.reescrever(mantidas)

    srv.auditoria.registrar(
        "RETENCAO",
        "OK",
        detalhe=f"{len(antigas)} sessão(ões) e {eventos_removidos} evento(s) de auditoria apagados",
    )
    return len(antigas), eventos_removidos
