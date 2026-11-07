from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.carga_inicial import USUARIOS_EXEMPLO, gerar_base
from app.config import Config
from app.servicos import montar_servicos

AGORA = datetime(2026, 11, 7, 15, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
PINS = {u["usuario"]: u["pin_demo"] for u in USUARIOS_EXEMPLO}


class Relogio:
    def __init__(self, inicio: datetime):
        self.atual = inicio

    def __call__(self) -> datetime:
        return self.atual

    def avancar(self, **delta) -> None:
        self.atual += timedelta(**delta)


class TerminalFalso:
    def __init__(self, confirmar=True, credenciais=("carlos", "4444"), aprovar=True):
        self.resposta_confirmar = confirmar
        self.credenciais = credenciais
        self.aprovar = aprovar
        self.avisos: list[str] = []
        self.confirmacoes: list[str] = []
        self.pedidos_credenciais = 0

    def avisar(self, mensagem):
        self.avisos.append(mensagem)

    def confirmar(self, resumo):
        self.confirmacoes.append(resumo)
        return self.resposta_confirmar

    def credenciais_aprovador(self):
        self.pedidos_credenciais += 1
        return self.credenciais

    def decisao_aprovador(self, resumo):
        return self.aprovar


@pytest.fixture
def relogio():
    return Relogio(AGORA)


@pytest.fixture
def config(tmp_path, relogio):
    return Config(openai_api_key="sk-teste", dados_dir=tmp_path / "dados", relogio=relogio)


@pytest.fixture
def srv(config):
    gerar_base(config, PINS, iteracoes=1_000)
    return montar_servicos(config)


@pytest.fixture
def login(srv):
    def _login(usuario):
        return srv.autenticador.autenticar(usuario, PINS[usuario])

    return _login


@pytest.fixture
def terminal():
    return TerminalFalso()
