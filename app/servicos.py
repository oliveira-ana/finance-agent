from dataclasses import dataclass

from app.auditoria import ARQUIVO_AUDITORIA, Auditoria
from app.auth import Autenticador
from app.config import Config
from app.operacoes import Banco
from app.repositorio import Repositorio
from app.sessao import IndiceSessoes


@dataclass
class Servicos:
    config: Config
    repo: Repositorio
    auditoria: Auditoria
    autenticador: Autenticador
    banco: Banco
    indice: IndiceSessoes


def montar_servicos(config: Config) -> Servicos:
    repo = Repositorio(config.dados_dir)
    auditoria = Auditoria(config.dados_dir / ARQUIVO_AUDITORIA, config.agora)
    return Servicos(
        config=config,
        repo=repo,
        auditoria=auditoria,
        autenticador=Autenticador(repo, auditoria, config),
        banco=Banco(repo, config),
        indice=IndiceSessoes(repo),
    )
