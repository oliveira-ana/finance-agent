import contextlib
import json
import os
import tempfile
from pathlib import Path

USUARIOS = "usuarios.json"
CONTAS = "contas.json"
MOVIMENTACOES = "movimentacoes.json"


def gravar_atomico(caminho: Path, conteudo: str) -> None:
    """Grava num temporário da mesma pasta e troca pelo original, para não corromper o arquivo."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    descritor, temporario = tempfile.mkstemp(dir=caminho.parent, prefix=f".{caminho.name}.", suffix=".tmp")
    try:
        with os.fdopen(descritor, "w", encoding="utf-8", newline="\n") as arquivo:
            arquivo.write(conteudo)
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.replace(temporario, caminho)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.remove(temporario)
        raise


class BaseCorrompida(RuntimeError):
    pass


class Repositorio:
    def __init__(self, dados_dir: Path):
        self.dir = Path(dados_dir)

    def caminho(self, nome: str) -> Path:
        return self.dir / nome

    def existe_base(self) -> bool:
        return all(self.caminho(nome).exists() for nome in (USUARIOS, CONTAS, MOVIMENTACOES))

    def ler(self, nome: str) -> list:
        caminho = self.caminho(nome)
        if not caminho.exists():
            return []
        try:
            with caminho.open(encoding="utf-8") as arquivo:
                return json.load(arquivo)
        except json.JSONDecodeError:
            raise BaseCorrompida(
                f"O arquivo {caminho} está corrompido. Restaure um backup ou recrie a base com: "
                "python -m app.carga_inicial --forcar"
            ) from None

    def gravar(self, nome: str, dados: list) -> None:
        gravar_atomico(self.caminho(nome), json.dumps(dados, ensure_ascii=False, indent=2))

    def buscar_usuario(self, usuario: str) -> dict | None:
        return next((u for u in self.ler(USUARIOS) if u["usuario"] == usuario), None)

    def salvar_usuario(self, registro: dict) -> None:
        usuarios = [registro if u["usuario"] == registro["usuario"] else u for u in self.ler(USUARIOS)]
        self.gravar(USUARIOS, usuarios)

    def buscar_conta(self, conta: str) -> dict | None:
        return next((c for c in self.ler(CONTAS) if c["conta"] == conta), None)

    def conta_do_usuario(self, usuario: str) -> dict | None:
        return next((c for c in self.ler(CONTAS) if c["usuario"] == usuario), None)

    def movimentacoes(self, conta: str) -> list[dict]:
        return [m for m in self.ler(MOVIMENTACOES) if m["conta"] == conta]

    def registrar_movimentacao(self, movimentacao: dict) -> None:
        """Grava a movimentação e o novo saldo (saldo_apos_centavos) da conta."""
        movimentacoes = self.ler(MOVIMENTACOES)
        movimentacoes.append(movimentacao)
        contas = self.ler(CONTAS)
        for conta in contas:
            if conta["conta"] == movimentacao["conta"]:
                conta["saldo_centavos"] = movimentacao["saldo_apos_centavos"]
        self.gravar(MOVIMENTACOES, movimentacoes)
        self.gravar(CONTAS, contas)
