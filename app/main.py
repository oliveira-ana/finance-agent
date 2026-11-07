from app.agente import criar_agente
from app.config import carregar_config


def main() -> None:
    agente = criar_agente(carregar_config())
    print("Finance Agent — digite 'sair' para encerrar.")
    while True:
        try:
            pergunta = input("\nVocê: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if pergunta.lower() in {"sair", "exit", "quit"}:
            break
        if pergunta:
            print()
            agente(pergunta)
            print()


if __name__ == "__main__":
    main()
