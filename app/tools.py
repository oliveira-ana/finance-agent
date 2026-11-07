from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date
from typing import TYPE_CHECKING

from strands import tool

from app.aprovacao import Terminal, solicitar_aprovacao
from app.lgpd import abreviar_nome, mascarar_texto
from app.operacoes import TIPOS, ErroOperacao, formatar_data_hora, formatar_reais, para_centavos
from app.permissoes import PERMISSOES, AcessoNegado, exigir

if TYPE_CHECKING:
    from app.servicos import Servicos
    from app.sessao import SessaoUsuario

FORMATO_CONTA = re.compile(r"^\d{4}-\d$")
MSG_OUTRA_CONTA = "Operação não permitida: você só pode acessar a sua própria conta."
MSG_FALHA = "Não foi possível concluir a operação."


def _data(texto: str | None, campo: str) -> date | None:
    if not texto:
        return None
    try:
        return date.fromisoformat(texto.strip())
    except ValueError:
        raise ErroOperacao(f"Data {campo} inválida. Use AAAA-MM-DD.") from None


def _item_extrato(movimentacao: dict) -> dict:
    item = {
        "data_hora": formatar_data_hora(movimentacao["data_hora"]),
        "tipo": TIPOS[movimentacao["tipo"]],
        "valor": formatar_reais(movimentacao["valor_centavos"]),
        "saldo_apos": formatar_reais(movimentacao["saldo_apos_centavos"]),
    }
    if movimentacao.get("aprovado_por"):
        item["aprovado_por"] = movimentacao["aprovado_por"]
    if movimentacao.get("motivo"):
        item["motivo"] = mascarar_texto(movimentacao["motivo"])
    return item


def criar_tools(sessao: SessaoUsuario, terminal: Terminal, srv: Servicos) -> list:
    """Cria só as tools do perfil logado. A identidade fica guardada na closure (ASI03)."""
    banco = srv.banco

    def auditar(acao: str, resultado: str, ctx: dict, detalhe: str | None = None) -> None:
        srv.auditoria.registrar(
            acao, resultado, sessao=sessao, conta=ctx.get("conta"), valor_centavos=ctx.get("valor"), detalhe=detalhe
        )

    def executar(acao: str, funcao: Callable[[dict], dict]) -> dict:
        ctx: dict = {}
        try:
            return funcao(ctx)
        except AcessoNegado as erro:
            auditar(acao, "NEGADO", ctx, str(erro))
            return {"resultado": "NEGADO", "mensagem": str(erro)}
        except ErroOperacao as erro:
            auditar(acao, "ERRO", ctx, str(erro))
            return {"resultado": "ERRO", "mensagem": str(erro)}
        except Exception as erro:
            auditar(acao, "ERRO", ctx, type(erro).__name__)
            return {"resultado": "ERRO", "mensagem": MSG_FALHA}

    def conta_alvo(conta: str | None, ctx: dict) -> str:
        informado = (conta or "").strip()
        if sessao.perfil == "cliente":
            ctx["conta"] = informado or sessao.conta
            if informado and informado != sessao.conta:
                raise AcessoNegado(MSG_OUTRA_CONTA)
            return sessao.conta
        if not informado:
            raise ErroOperacao("Informe o número da conta (ou o usuário) do cliente.")
        if not FORMATO_CONTA.match(informado):
            registro = srv.repo.conta_do_usuario(informado.lower())
            if registro is None:
                raise ErroOperacao("Conta não encontrada.")
            informado = registro["conta"]
        ctx["conta"] = informado
        return informado

    def titular(registro_conta: dict) -> str:
        dono = srv.repo.buscar_usuario(registro_conta["usuario"])
        nome = dono["nome"] if dono else registro_conta["usuario"]
        return nome.split()[0] if sessao.perfil == "cliente" else abreviar_nome(nome)

    @tool
    def consultar_saldo(conta: str | None = None) -> dict:
        """Consulta o saldo de uma conta.

        Args:
            conta: Número da conta (ex.: 0001-1) ou usuário do cliente. Só o atendente informa; para o cliente vale sempre a própria conta.
        """

        def regra(ctx: dict) -> dict:
            exigir(sessao, "consultar_saldo")
            alvo = conta_alvo(conta, ctx)
            registro = banco.consultar_conta(alvo)
            auditar("CONSULTAR_SALDO", "OK", ctx)
            return {
                "resultado": "OK",
                "conta": alvo,
                "titular": titular(registro),
                "saldo": formatar_reais(registro["saldo_centavos"]),
            }

        return executar("CONSULTAR_SALDO", regra)

    @tool
    def consultar_extrato(conta: str | None = None, inicio: str | None = None, fim: str | None = None) -> dict:
        """Consulta o extrato (movimentações) de uma conta num período, da mais recente para a mais antiga.

        Args:
            conta: Número da conta (ex.: 0001-1) ou usuário do cliente. Só o atendente informa; para o cliente vale sempre a própria conta.
            inicio: Data inicial no formato AAAA-MM-DD. Se não informar, usa os últimos 30 dias.
            fim: Data final no formato AAAA-MM-DD. Se não informar, usa hoje.
        """

        def regra(ctx: dict) -> dict:
            exigir(sessao, "consultar_extrato")
            alvo = conta_alvo(conta, ctx)
            data_inicio, data_fim, itens = banco.extrato(alvo, _data(inicio, "inicial"), _data(fim, "final"))
            auditar("CONSULTAR_EXTRATO", "OK", ctx, f"{data_inicio.isoformat()} a {data_fim.isoformat()}")
            return {
                "resultado": "OK",
                "conta": alvo,
                "periodo": f"{data_inicio:%d/%m/%Y} a {data_fim:%d/%m/%Y}",
                "movimentacoes": [_item_extrato(m) for m in itens],
            }

        return executar("CONSULTAR_EXTRATO", regra)

    @tool
    def depositar(valor: str) -> dict:
        """Deposita um valor na própria conta do cliente. O sistema pede a confirmação no terminal.

        Args:
            valor: Valor em reais como texto, ex.: "150,00".
        """

        def regra(ctx: dict) -> dict:
            exigir(sessao, "depositar")
            ctx["conta"] = sessao.conta
            ctx["valor"] = centavos = para_centavos(valor)
            resumo = f"Depósito de {formatar_reais(centavos)} na conta {sessao.conta}."
            if not terminal.confirmar(resumo):
                auditar("DEPOSITO", "REJEITADO", ctx, "cancelado pelo usuário")
                return {"resultado": "CANCELADO", "mensagem": "Depósito cancelado pelo usuário."}
            movimentacao = banco.depositar(sessao, centavos)
            auditar("DEPOSITO", "OK", ctx)
            return {
                "resultado": "OK",
                "valor": formatar_reais(centavos),
                "novo_saldo": formatar_reais(movimentacao["saldo_apos_centavos"]),
            }

        return executar("DEPOSITO", regra)

    @tool
    def sacar(valor: str) -> dict:
        """Saca um valor da própria conta do cliente. O sistema pede a confirmação e, se o saque estiver fora do padrão, a aprovação no terminal.

        Args:
            valor: Valor em reais como texto, ex.: "150,00".
        """

        def regra(ctx: dict) -> dict:
            exigir(sessao, "sacar")
            ctx["conta"] = sessao.conta
            ctx["valor"] = centavos = para_centavos(valor)
            motivo = banco.verificar_saque(sessao, centavos)
            resumo = f"Saque de {formatar_reais(centavos)} da conta {sessao.conta}."
            if motivo:
                resumo += f" Precisa de aprovação: {motivo}."
            if not terminal.confirmar(resumo):
                auditar("SAQUE", "REJEITADO", ctx, "cancelado pelo usuário")
                return {"resultado": "CANCELADO", "mensagem": "Saque cancelado pelo usuário."}
            aprovador = None
            if motivo:
                aprovador = solicitar_aprovacao(terminal, srv.autenticador, sessao, resumo, motivo)
                if aprovador is None:
                    auditar("SAQUE", "REJEITADO", ctx, f"não aprovado ({motivo})")
                    return {"resultado": "REJEITADO", "mensagem": "Saque não aprovado. Nada foi alterado."}
            movimentacao = banco.sacar(sessao, centavos, aprovado_por=aprovador)
            auditar("SAQUE", "OK", ctx, f"aprovado por {aprovador} ({motivo})" if aprovador else None)
            resposta = {
                "resultado": "OK",
                "valor": formatar_reais(centavos),
                "novo_saldo": formatar_reais(movimentacao["saldo_apos_centavos"]),
            }
            if aprovador:
                resposta["aprovado_por"] = aprovador
            return resposta

        return executar("SAQUE", regra)

    @tool
    def estornar(conta: str, valor: str, motivo: str, transacao_ref: str | None = None) -> dict:
        """Faz um depósito de estorno na conta de um cliente (só atendente). Exige motivo. Acima do limite, o sistema pede a aprovação no terminal.

        Args:
            conta: Número da conta (ex.: 0001-1) ou usuário do cliente.
            valor: Valor em reais como texto, ex.: "300,00".
            motivo: Motivo do estorno, com pelo menos 10 caracteres. Pergunte ao atendente se ele não informou.
            transacao_ref: Identificador opcional da transação que está sendo estornada.
        """

        def regra(ctx: dict) -> dict:
            exigir(sessao, "estornar")
            alvo = conta_alvo(conta, ctx)
            ctx["valor"] = centavos = para_centavos(valor)
            precisa = banco.verificar_estorno(sessao, alvo, centavos, motivo)
            resumo = f"Estorno de {formatar_reais(centavos)} na conta {alvo}. Motivo: {mascarar_texto(motivo.strip())}."
            if precisa:
                resumo += f" Precisa de aprovação: {precisa}."
            if not terminal.confirmar(resumo):
                auditar("ESTORNO", "REJEITADO", ctx, "cancelado pelo usuário")
                return {"resultado": "CANCELADO", "mensagem": "Estorno cancelado pelo usuário."}
            aprovador = None
            if precisa:
                aprovador = solicitar_aprovacao(terminal, srv.autenticador, sessao, resumo, precisa)
                if aprovador is None:
                    auditar("ESTORNO", "REJEITADO", ctx, f"não aprovado ({precisa})")
                    return {"resultado": "REJEITADO", "mensagem": "Estorno não aprovado. Nada foi alterado."}
            movimentacao = banco.estornar(sessao, alvo, centavos, motivo, transacao_ref, aprovado_por=aprovador)
            detalhe = f"motivo: {motivo.strip()}" + (f"; aprovado por {aprovador} ({precisa})" if aprovador else "")
            auditar("ESTORNO", "OK", ctx, detalhe)
            resposta = {
                "resultado": "OK",
                "conta": alvo,
                "valor": formatar_reais(centavos),
                "novo_saldo": formatar_reais(movimentacao["saldo_apos_centavos"]),
            }
            if aprovador:
                resposta["aprovado_por"] = aprovador
            return resposta

        return executar("ESTORNO", regra)

    todas = [consultar_saldo, consultar_extrato, depositar, sacar, estornar]
    return [t for t in todas if t.tool_name in PERMISSOES[sessao.perfil]]
