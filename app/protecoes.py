from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from strands.hooks import BeforeInvocationEvent, BeforeToolCallEvent, HookProvider, HookRegistry

from app.lgpd import mascarar_texto

if TYPE_CHECKING:
    from app.auditoria import Auditoria
    from app.sessao import SessaoUsuario

MSG_LIMITE = "Limite de operações por mensagem atingido. Peça uma operação de cada vez."


class ProtecoesHook(HookProvider):
    """Limita as tools por mensagem (ASI02/ASI08) e audita toda chamada de tool (ASI10)."""

    def __init__(self, max_tools_por_mensagem: int, sessao: SessaoUsuario, auditoria: Auditoria):
        self.max_tools = max_tools_por_mensagem
        self.sessao = sessao
        self.auditoria = auditoria
        self.chamadas = 0

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        registry.add_callback(BeforeInvocationEvent, self.zerar_contador)
        registry.add_callback(BeforeToolCallEvent, self.antes_da_tool)

    def zerar_contador(self, event: BeforeInvocationEvent) -> None:
        self.chamadas = 0

    def antes_da_tool(self, event: BeforeToolCallEvent) -> None:
        self.chamadas += 1
        nome = event.tool_use.get("name", "?")
        parametros = mascarar_texto(json.dumps(event.tool_use.get("input", {}), ensure_ascii=False))[:300]
        if self.chamadas > self.max_tools:
            event.cancel_tool = MSG_LIMITE
            self.auditoria.registrar(
                "TOOL_CHAMADA", "NEGADO", sessao=self.sessao, detalhe=f"{nome} {parametros} — limite por mensagem"
            )
            return
        self.auditoria.registrar("TOOL_CHAMADA", "OK", sessao=self.sessao, detalhe=f"{nome} {parametros}")
