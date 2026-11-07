from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

from app.lgpd import mascarar_texto
from app.permissoes import exigir

if TYPE_CHECKING:
    from app.config import Config
    from app.repositorio import Repositorio
    from app.sessao import SessaoUsuario

TIPOS = {"DEPOSITO": "Depósito", "SAQUE": "Saque", "ESTORNO": "Estorno"}
MOTIVO_MIN_CARACTERES = 10
EXTRATO_MAX_ITENS = 50
_MILHAR = re.compile(r"^\d{1,3}(\.\d{3})+$")


class ErroOperacao(Exception):
    """Erro de regra de negócio, com mensagem curta para o usuário."""


class AprovacaoNecessaria(ErroOperacao):
    pass


def para_centavos(valor: str | int | float) -> int:
    """RN01: aceita '150', '150,50', '1.234,56', 'R$ 200' e devolve centavos (int)."""
    texto = str(valor).strip().replace("R$", "").replace(" ", "")
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif _MILHAR.match(texto):
        texto = texto.replace(".", "")
    try:
        numero = Decimal(texto)
    except InvalidOperation:
        raise ErroOperacao("Valor inválido. Use, por exemplo, 150,00.") from None
    if not numero.is_finite() or numero <= 0:
        raise ErroOperacao("O valor deve ser maior que zero.")
    if numero != numero.quantize(Decimal("0.01")):
        raise ErroOperacao("O valor pode ter no máximo 2 casas decimais.")
    return int(numero * 100)


def formatar_reais(centavos: int) -> str:
    sinal = "-" if centavos < 0 else ""
    reais, resto = divmod(abs(centavos), 100)
    return f"{sinal}R$ {reais:,}".replace(",", ".") + f",{resto:02d}"


def formatar_data_hora(iso: str) -> str:
    return datetime.fromisoformat(iso).strftime("%d/%m/%Y %H:%M")


def _data_hora(movimentacao: dict) -> datetime:
    return datetime.fromisoformat(movimentacao["data_hora"])


class Banco:
    """Regras de negócio (RN01–RN10) sem IA. A autorização também é conferida aqui."""

    def __init__(self, repo: Repositorio, config: Config):
        self.repo = repo
        self.config = config

    def consultar_conta(self, conta: str) -> dict:
        registro = self.repo.buscar_conta(conta)
        if registro is None:
            raise ErroOperacao("Conta não encontrada.")
        return registro

    def extrato(self, conta: str, inicio: date | None = None, fim: date | None = None) -> tuple[date, date, list[dict]]:
        self.consultar_conta(conta)
        fim = fim or self.config.agora().date()
        inicio = inicio or fim - timedelta(days=self.config.extrato_dias_padrao)
        if inicio > fim:
            raise ErroOperacao("A data inicial é depois da data final.")
        itens = [m for m in self.repo.movimentacoes(conta) if inicio <= _data_hora(m).date() <= fim]
        itens.sort(key=_data_hora, reverse=True)
        return inicio, fim, itens[:EXTRATO_MAX_ITENS]

    def _saques(self, conta: str) -> list[dict]:
        return sorted((m for m in self.repo.movimentacoes(conta) if m["tipo"] == "SAQUE"), key=_data_hora)

    def motivo_aprovacao_saque(self, conta: str, valor: int) -> str | None:
        """RN05/RN06: devolve por que o saque precisa de aprovador, ou None."""
        saques = self._saques(conta)
        if len(saques) < self.config.saque_min_historico:
            limite = self.config.saque_limite_sem_historico_centavos
            if valor > limite:
                return (
                    f"cliente com menos de {self.config.saque_min_historico} saques no histórico "
                    f"e valor acima de {formatar_reais(limite)}"
                )
            return None
        recentes = [m["valor_centavos"] for m in saques[-self.config.saque_qtd_media :]]
        media = Decimal(sum(recentes)) / len(recentes)
        if valor > self.config.saque_multiplicador_media * media:
            vezes = f"{Decimal(valor) / media:.1f}".replace(".", ",")
            return f"{vezes}x a média dos últimos {len(recentes)} saques ({formatar_reais(int(media))})"
        return None

    def motivo_aprovacao_estorno(self, valor: int) -> str | None:
        """RN08."""
        limite = self.config.estorno_limite_centavos
        if valor > limite:
            return f"estorno acima de {formatar_reais(limite)}"
        return None

    def _movimentar(
        self,
        sessao: SessaoUsuario,
        conta: str,
        tipo: str,
        valor: int,
        aprovado_por: str | None = None,
        motivo: str | None = None,
        transacao_ref: str | None = None,
    ) -> dict:
        saldo = self.consultar_conta(conta)["saldo_centavos"]
        novo_saldo = saldo - valor if tipo == "SAQUE" else saldo + valor
        if novo_saldo < 0:
            raise ErroOperacao("Saldo insuficiente.")
        movimentacao = {
            "id": uuid.uuid4().hex,
            "conta": conta,
            "data_hora": self.config.agora().isoformat(timespec="seconds"),
            "tipo": tipo,
            "valor_centavos": valor,
            "saldo_apos_centavos": novo_saldo,
            "feito_por": sessao.usuario,
            "aprovado_por": aprovado_por,
            "motivo": motivo,
            "transacao_ref": transacao_ref,
        }
        self.repo.registrar_movimentacao(movimentacao)
        return movimentacao

    def depositar(self, sessao: SessaoUsuario, valor: int) -> dict:
        exigir(sessao, "depositar")
        return self._movimentar(sessao, sessao.conta, "DEPOSITO", valor)

    def verificar_saque(self, sessao: SessaoUsuario, valor: int) -> str | None:
        """Confere permissão e saldo (RN03) e devolve o motivo de aprovação, se houver."""
        exigir(sessao, "sacar")
        if self.consultar_conta(sessao.conta)["saldo_centavos"] < valor:
            raise ErroOperacao("Saldo insuficiente.")
        return self.motivo_aprovacao_saque(sessao.conta, valor)

    def sacar(self, sessao: SessaoUsuario, valor: int, aprovado_por: str | None = None) -> dict:
        motivo = self.verificar_saque(sessao, valor)
        if motivo and not aprovado_por:
            raise AprovacaoNecessaria(f"Este saque precisa de aprovação: {motivo}.")
        return self._movimentar(sessao, sessao.conta, "SAQUE", valor, aprovado_por=aprovado_por)

    def verificar_estorno(self, sessao: SessaoUsuario, conta: str, valor: int, motivo: str | None) -> str | None:
        """Confere permissão, conta e motivo (RN07) e devolve o motivo de aprovação, se houver."""
        exigir(sessao, "estornar")
        self.consultar_conta(conta)
        if len((motivo or "").strip()) < MOTIVO_MIN_CARACTERES:
            raise ErroOperacao(f"Informe o motivo do estorno (mínimo de {MOTIVO_MIN_CARACTERES} caracteres).")
        return self.motivo_aprovacao_estorno(valor)

    def estornar(
        self,
        sessao: SessaoUsuario,
        conta: str,
        valor: int,
        motivo: str | None,
        transacao_ref: str | None = None,
        aprovado_por: str | None = None,
    ) -> dict:
        precisa = self.verificar_estorno(sessao, conta, valor, motivo)
        if precisa and not aprovado_por:
            raise AprovacaoNecessaria(f"Este estorno precisa de aprovação: {precisa}.")
        return self._movimentar(
            sessao,
            conta,
            "ESTORNO",
            valor,
            aprovado_por=aprovado_por,
            motivo=mascarar_texto(motivo.strip()),
            transacao_ref=mascarar_texto(transacao_ref.strip())[:64] if transacao_ref else None,
        )
