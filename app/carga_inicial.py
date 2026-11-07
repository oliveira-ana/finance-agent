"""Cria a base fictícia em dados/: python -m app.carga_inicial [--demo] [--forcar]"""

from __future__ import annotations

import argparse
import getpass
import re
import sys
import uuid
from datetime import datetime, timedelta

from app.auditoria import ARQUIVO_AUDITORIA, Auditoria
from app.auth import ITERACOES_PADRAO, gerar_hash
from app.config import Config, carregar_config
from app.repositorio import CONTAS, MOVIMENTACOES, USUARIOS, Repositorio

FORMATO_PIN = re.compile(r"^\d{4,6}$")

# Todos os dados pessoais abaixo são fictícios.
USUARIOS_EXEMPLO = [
    {
        "usuario": "maria",
        "nome": "Maria Souza",
        "cpf": "123.456.789-09",
        "email": "maria@exemplo.com",
        "telefone": "(11) 98765-4321",
        "perfil": "cliente",
        "conta": "0001-1",
        "pin_demo": "1111",
    },
    {
        "usuario": "joao",
        "nome": "João Lima",
        "cpf": "987.654.321-00",
        "email": "joao@exemplo.com",
        "telefone": "(21) 91234-5678",
        "perfil": "cliente",
        "conta": "0002-2",
        "pin_demo": "2222",
    },
    {
        "usuario": "paula",
        "nome": "Paula Mendes",
        "cpf": "111.222.333-96",
        "email": "paula@exemplo.com",
        "telefone": "(11) 97777-1111",
        "perfil": "atendente",
        "conta": None,
        "pin_demo": "3333",
    },
    {
        "usuario": "carlos",
        "nome": "Carlos Pereira",
        "cpf": "444.555.666-73",
        "email": "carlos@exemplo.com",
        "telefone": "(11) 96666-2222",
        "perfil": "aprovador",
        "conta": None,
        "pin_demo": "4444",
    },
]


def _movimentacoes_exemplo(agora: datetime) -> tuple[list[dict], dict[str, int]]:
    """Maria: 10 saques de R$ 200 (média R$ 200). João: sem saques."""
    movimentacoes: list[dict] = []
    saldos: dict[str, int] = {}

    def adicionar(conta: str, dias_atras: int, tipo: str, valor: int, feito_por: str) -> None:
        saldos[conta] = saldos.get(conta, 0) + (-valor if tipo == "SAQUE" else valor)
        movimentacoes.append(
            {
                "id": uuid.uuid4().hex,
                "conta": conta,
                "data_hora": (agora - timedelta(days=dias_atras)).replace(microsecond=0).isoformat(),
                "tipo": tipo,
                "valor_centavos": valor,
                "saldo_apos_centavos": saldos[conta],
                "feito_por": feito_por,
                "aprovado_por": None,
                "motivo": None,
                "transacao_ref": None,
            }
        )

    adicionar("0001-1", 120, "DEPOSITO", 500_000, "maria")
    adicionar("0001-1", 115, "DEPOSITO", 150_000, "maria")
    for i in range(10):
        adicionar("0001-1", 110 - i * 10, "SAQUE", 20_000, "maria")
    adicionar("0002-2", 60, "DEPOSITO", 300_000, "joao")
    return movimentacoes, saldos


def gerar_base(
    config: Config,
    pins: dict[str, str],
    forcar: bool = False,
    iteracoes: int = ITERACOES_PADRAO,
) -> None:
    repo = Repositorio(config.dados_dir)
    if repo.existe_base() and not forcar:
        raise RuntimeError(f"A base já existe em {config.dados_dir}. Use --forcar para recriar (apaga os dados atuais).")
    agora = config.agora()
    usuarios = []
    for exemplo in USUARIOS_EXEMPLO:
        registro = {k: v for k, v in exemplo.items() if k != "pin_demo"}
        registro.update(gerar_hash(pins[exemplo["usuario"]], iteracoes=iteracoes))
        registro.update({"tentativas_erradas": 0, "bloqueado_ate": None})
        usuarios.append(registro)
    movimentacoes, saldos = _movimentacoes_exemplo(agora)
    contas = [
        {"conta": u["conta"], "usuario": u["usuario"], "saldo_centavos": saldos.get(u["conta"], 0)}
        for u in USUARIOS_EXEMPLO
        if u["conta"]
    ]
    repo.gravar(USUARIOS, usuarios)
    repo.gravar(CONTAS, contas)
    repo.gravar(MOVIMENTACOES, movimentacoes)
    Auditoria(config.dados_dir / ARQUIVO_AUDITORIA, config.agora).registrar(
        "CARGA_INICIAL", "OK", detalhe=f"{len(usuarios)} usuários e {len(contas)} contas fictícios"
    )


def pedir_pin(usuario: str) -> str:
    while True:
        pin = getpass.getpass(f"PIN para {usuario} (4 a 6 dígitos): ")
        if not FORMATO_PIN.match(pin):
            print("O PIN deve ter de 4 a 6 dígitos.")
            continue
        if getpass.getpass("Repita o PIN: ") != pin:
            print("Os PINs não conferem.")
            continue
        return pin


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cria a base bancária fictícia em dados/.")
    parser.add_argument("--demo", action="store_true", help="usa os PINs de demonstração (ver README)")
    parser.add_argument("--forcar", action="store_true", help="recria a base mesmo se ela já existir")
    args = parser.parse_args(argv)
    config = carregar_config(exigir_chave=False)
    if args.demo:
        pins = {u["usuario"]: u["pin_demo"] for u in USUARIOS_EXEMPLO}
    else:
        pins = {u["usuario"]: pedir_pin(u["usuario"]) for u in USUARIOS_EXEMPLO}
    try:
        gerar_base(config, pins, forcar=args.forcar)
    except RuntimeError as erro:
        print(erro)
        return 1
    print(f"Base criada em {config.dados_dir}:")
    for u in USUARIOS_EXEMPLO:
        print(f"  {u['usuario']:<8} {u['perfil']:<10} conta {u['conta'] or '-'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
