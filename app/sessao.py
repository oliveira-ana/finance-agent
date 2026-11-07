from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import datetime
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from app.repositorio import Repositorio

Perfil = Literal["cliente", "atendente", "aprovador"]
ARQUIVO_INDICE = "sessoes_indice.json"


@dataclass(frozen=True)
class SessaoUsuario:
    """Quem está logado. Fica só na memória do processo; o modelo não lê nem altera."""

    usuario: str
    nome: str
    perfil: Perfil
    conta: str | None
    session_id: str

    @property
    def primeiro_nome(self) -> str:
        return self.nome.split()[0] if self.nome.strip() else self.usuario


def novo_session_id() -> str:
    return uuid.uuid4().hex


def nova_sessao(sessao: SessaoUsuario) -> SessaoUsuario:
    return replace(sessao, session_id=novo_session_id())


class IndiceSessoes:
    """Liga usuário → session_id sem colocar o usuário no nome da pasta da sessão."""

    def __init__(self, repo: Repositorio):
        self.repo = repo

    def listar(self) -> list[dict]:
        return self.repo.ler(ARQUIVO_INDICE)

    def registrar(self, sessao: SessaoUsuario, quando: datetime) -> None:
        itens = self.listar()
        itens.append(
            {
                "session_id": sessao.session_id,
                "usuario": sessao.usuario,
                "criada_em": quando.isoformat(timespec="seconds"),
                "encerrada_em": None,
            }
        )
        self.repo.gravar(ARQUIVO_INDICE, itens)

    def encerrar(self, session_id: str, quando: datetime) -> None:
        itens = self.listar()
        for item in itens:
            if item["session_id"] == session_id and not item.get("encerrada_em"):
                item["encerrada_em"] = quando.isoformat(timespec="seconds")
        self.repo.gravar(ARQUIVO_INDICE, itens)

    def do_usuario(self, usuario: str) -> list[str]:
        return [item["session_id"] for item in self.listar() if item["usuario"] == usuario]

    def remover(self, session_ids: set[str]) -> None:
        if not session_ids:
            return
        itens = [item for item in self.listar() if item["session_id"] not in session_ids]
        self.repo.gravar(ARQUIVO_INDICE, itens)
