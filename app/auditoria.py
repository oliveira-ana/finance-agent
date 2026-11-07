from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from app.lgpd import mascarar_texto
from app.repositorio import gravar_atomico

if TYPE_CHECKING:
    from app.sessao import SessaoUsuario

ARQUIVO_AUDITORIA = "auditoria.jsonl"
RESULTADOS = {"OK", "NEGADO", "REJEITADO", "LOGIN_FALHOU", "BLOQUEADO", "ERRO"}


class Auditoria:
    """Grava um evento por linha em auditoria.jsonl, sempre com dados pessoais mascarados."""

    def __init__(self, arquivo: Path, relogio: Callable[[], datetime]):
        self.arquivo = Path(arquivo)
        self.relogio = relogio

    def registrar(
        self,
        acao: str,
        resultado: str,
        *,
        sessao: SessaoUsuario | None = None,
        usuario: str | None = None,
        perfil: str | None = None,
        conta: str | None = None,
        valor_centavos: int | None = None,
        detalhe: str | None = None,
    ) -> None:
        if resultado not in RESULTADOS:
            raise ValueError(f"resultado de auditoria inválido: {resultado}")
        if sessao is not None:
            usuario = usuario or sessao.usuario
            perfil = perfil or sessao.perfil
        evento = {
            "data_hora": self.relogio().isoformat(timespec="seconds"),
            "usuario": mascarar_texto(usuario)[:64] if usuario else None,
            "perfil": perfil,
            "sessao": sessao.session_id if sessao else None,
            "acao": acao,
            "conta": conta,
            "valor_centavos": valor_centavos,
            "resultado": resultado,
            "detalhe": mascarar_texto(detalhe)[:500] if detalhe else None,
        }
        self.arquivo.parent.mkdir(parents=True, exist_ok=True)
        with self.arquivo.open("a", encoding="utf-8", newline="\n") as arquivo:
            arquivo.write(json.dumps(evento, ensure_ascii=False) + "\n")

    def linhas(self) -> list[str]:
        if not self.arquivo.exists():
            return []
        return [linha for linha in self.arquivo.read_text(encoding="utf-8").splitlines() if linha.strip()]

    def eventos(self) -> list[dict]:
        return [json.loads(linha) for linha in self.linhas()]

    def reescrever(self, linhas: list[str]) -> None:
        gravar_atomico(self.arquivo, "".join(f"{linha}\n" for linha in linhas))
