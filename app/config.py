import os
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

MODELO_PADRAO = "gpt-4o-mini"
CHAVE_EXEMPLO = "sk-..."
RAIZ_PROJETO = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Config:
    openai_api_key: str
    openai_model: str = MODELO_PADRAO
    dados_dir: Path = RAIZ_PROJETO / "dados"
    fuso: str = "America/Sao_Paulo"
    saque_multiplicador_media: Decimal = Decimal("3")  # P01
    saque_qtd_media: int = 10  # P02
    estorno_limite_centavos: int = 100_000  # P03
    pin_tentativas: int = 3  # P04
    pin_bloqueio_min: int = 15  # P05
    extrato_dias_padrao: int = 30  # P06
    saque_min_historico: int = 3  # P07
    saque_limite_sem_historico_centavos: int = 100_000  # P08
    max_tools_por_mensagem: int = 5
    retencao_sessoes_dias: int = 90
    retencao_auditoria_anos: int = 5
    relogio: Callable[[], datetime] | None = field(default=None, repr=False, compare=False)

    @property
    def dir_sessoes(self) -> Path:
        return self.dados_dir / "sessoes"

    def agora(self) -> datetime:
        if self.relogio is not None:
            return self.relogio()
        return datetime.now(ZoneInfo(self.fuso))


def _texto(nome: str, padrao: str) -> str:
    return os.getenv(nome, "").strip() or padrao


def _inteiro(nome: str, padrao: int) -> int:
    bruto = os.getenv(nome, "").strip()
    if not bruto:
        return padrao
    try:
        valor = int(bruto)
    except ValueError:
        raise RuntimeError(f"{nome} deve ser um número inteiro.") from None
    if valor < 1:
        raise RuntimeError(f"{nome} deve ser maior que zero.")
    return valor


def _decimal(nome: str, padrao: str) -> Decimal:
    bruto = os.getenv(nome, "").strip() or padrao
    try:
        valor = Decimal(bruto.replace(",", "."))
    except InvalidOperation:
        raise RuntimeError(f"{nome} deve ser um número (ex.: {padrao}).") from None
    if not valor.is_finite() or valor <= 0:
        raise RuntimeError(f"{nome} deve ser maior que zero.")
    return valor


def _centavos(nome: str, padrao: str) -> int:
    return int((_decimal(nome, padrao) * 100).to_integral_value())


def _diretorio(nome: str, padrao: str) -> Path:
    caminho = Path(_texto(nome, padrao))
    return caminho if caminho.is_absolute() else RAIZ_PROJETO / caminho


def carregar_config(exigir_chave: bool = True) -> Config:
    load_dotenv()
    chave = os.getenv("OPENAI_API_KEY", "").strip()
    if chave == CHAVE_EXEMPLO:
        chave = ""
    if exigir_chave and not chave:
        raise RuntimeError("OPENAI_API_KEY não definida. Copie .env.example para .env e preencha a chave.")
    fuso = _texto("FUSO", "America/Sao_Paulo")
    try:
        ZoneInfo(fuso)
    except (ZoneInfoNotFoundError, ValueError):
        raise RuntimeError(f"FUSO inválido: {fuso}. Instale o pacote tzdata ou use America/Sao_Paulo.") from None
    return Config(
        openai_api_key=chave,
        openai_model=_texto("OPENAI_MODEL", MODELO_PADRAO),
        dados_dir=_diretorio("DADOS_DIR", "dados"),
        fuso=fuso,
        saque_multiplicador_media=_decimal("SAQUE_MULTIPLICADOR_MEDIA", "3"),
        saque_qtd_media=_inteiro("SAQUE_QTD_MEDIA", 10),
        estorno_limite_centavos=_centavos("ESTORNO_LIMITE", "1000.00"),
        pin_tentativas=_inteiro("PIN_TENTATIVAS", 3),
        pin_bloqueio_min=_inteiro("PIN_BLOQUEIO_MIN", 15),
        extrato_dias_padrao=_inteiro("EXTRATO_DIAS_PADRAO", 30),
        saque_min_historico=_inteiro("SAQUE_MIN_HISTORICO", 3),
        saque_limite_sem_historico_centavos=_centavos("SAQUE_LIMITE_SEM_HISTORICO", "1000.00"),
        max_tools_por_mensagem=_inteiro("MAX_TOOLS_POR_MENSAGEM", 5),
        retencao_sessoes_dias=_inteiro("RETENCAO_SESSOES_DIAS", 90),
        retencao_auditoria_anos=_inteiro("RETENCAO_AUDITORIA_ANOS", 5),
    )
