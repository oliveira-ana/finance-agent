from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from app.sessao import SessaoUsuario, novo_session_id

if TYPE_CHECKING:
    from app.auditoria import Auditoria
    from app.config import Config
    from app.repositorio import Repositorio

ITERACOES_PADRAO = 600_000
MSG_LOGIN_INVALIDO = "Usuário ou PIN inválidos."
MSG_APROVADOR_SEM_LOGIN = (
    "O perfil aprovador não abre sessão de chat. Ele só informa as credenciais na hora de aprovar uma operação."
)


class LoginRecusado(Exception):
    pass


def gerar_hash(pin: str, salt: bytes | None = None, iteracoes: int = ITERACOES_PADRAO) -> dict:
    salt = salt or secrets.token_bytes(16)
    calculado = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, iteracoes)
    return {"pin_hash": calculado.hex(), "pin_salt": salt.hex(), "pin_iteracoes": iteracoes}


def verificar_pin(pin: str, registro: dict) -> bool:
    calculado = hashlib.pbkdf2_hmac(
        "sha256",
        pin.encode("utf-8"),
        bytes.fromhex(registro["pin_salt"]),
        int(registro.get("pin_iteracoes", ITERACOES_PADRAO)),
    )
    return hmac.compare_digest(calculado.hex(), registro["pin_hash"])


def normalizar_usuario(usuario: str) -> str:
    return usuario.strip().lower()[:64]


class Autenticador:
    def __init__(self, repo: Repositorio, auditoria: Auditoria, config: Config):
        self.repo = repo
        self.auditoria = auditoria
        self.config = config

    @staticmethod
    def _bloqueado(registro: dict, agora: datetime) -> bool:
        ate = registro.get("bloqueado_ate")
        return bool(ate) and datetime.fromisoformat(ate) > agora

    def _conferir(self, usuario: str, pin: str, acao: str) -> dict | None:
        """Confere usuário + PIN aplicando o bloqueio (RN12). Devolve o registro se estiver correto."""
        agora = self.config.agora()
        registro = self.repo.buscar_usuario(usuario)
        if registro is None:
            # Mesmo custo de um PIN errado, para não revelar se o usuário existe.
            gerar_hash(pin, salt=b"\0" * 16)
            self.auditoria.registrar(acao, "LOGIN_FALHOU", usuario=usuario, detalhe="usuário inexistente")
            return None
        perfil = registro["perfil"]
        if self._bloqueado(registro, agora):
            self.auditoria.registrar(
                acao, "BLOQUEADO", usuario=usuario, perfil=perfil, detalhe="tentativa durante o bloqueio"
            )
            return None
        if not verificar_pin(pin, registro):
            tentativas = int(registro.get("tentativas_erradas", 0)) + 1
            if tentativas >= self.config.pin_tentativas:
                registro["tentativas_erradas"] = 0
                registro["bloqueado_ate"] = (agora + timedelta(minutes=self.config.pin_bloqueio_min)).isoformat(
                    timespec="seconds"
                )
                self.repo.salvar_usuario(registro)
                self.auditoria.registrar(
                    acao,
                    "BLOQUEADO",
                    usuario=usuario,
                    perfil=perfil,
                    detalhe=f"bloqueado por {self.config.pin_bloqueio_min} min após {tentativas} PINs errados",
                )
            else:
                registro["tentativas_erradas"] = tentativas
                self.repo.salvar_usuario(registro)
                self.auditoria.registrar(
                    acao,
                    "LOGIN_FALHOU",
                    usuario=usuario,
                    perfil=perfil,
                    detalhe=f"PIN errado ({tentativas}/{self.config.pin_tentativas})",
                )
            return None
        if registro.get("tentativas_erradas") or registro.get("bloqueado_ate"):
            registro["tentativas_erradas"] = 0
            registro["bloqueado_ate"] = None
            self.repo.salvar_usuario(registro)
        return registro

    def autenticar(self, usuario: str, pin: str) -> SessaoUsuario:
        usuario = normalizar_usuario(usuario)
        registro = self._conferir(usuario, pin, "LOGIN")
        if registro is None:
            raise LoginRecusado(MSG_LOGIN_INVALIDO)
        if registro["perfil"] == "aprovador":
            self.auditoria.registrar(
                "LOGIN", "NEGADO", usuario=usuario, perfil="aprovador", detalhe="aprovador não abre sessão (RN14)"
            )
            raise LoginRecusado(MSG_APROVADOR_SEM_LOGIN)
        sessao = SessaoUsuario(
            usuario=registro["usuario"],
            nome=registro["nome"],
            perfil=registro["perfil"],
            conta=registro.get("conta"),
            session_id=novo_session_id(),
        )
        self.auditoria.registrar("LOGIN", "OK", sessao=sessao)
        return sessao

    def validar_aprovador(self, usuario: str, pin: str, solicitante: str) -> str | None:
        """Devolve o usuário do aprovador se as credenciais valem para aprovar (RN10, RN14)."""
        usuario = normalizar_usuario(usuario)
        registro = self._conferir(usuario, pin, "APROVACAO_CREDENCIAIS")
        if registro is None:
            return None
        if registro["perfil"] != "aprovador":
            self.auditoria.registrar(
                "APROVACAO_CREDENCIAIS",
                "NEGADO",
                usuario=usuario,
                perfil=registro["perfil"],
                detalhe="credenciais sem perfil aprovador",
            )
            return None
        if registro["usuario"] == solicitante:
            self.auditoria.registrar(
                "APROVACAO_CREDENCIAIS",
                "NEGADO",
                usuario=usuario,
                perfil="aprovador",
                detalhe="aprovador igual ao solicitante (RN10)",
            )
            return None
        return registro["usuario"]
