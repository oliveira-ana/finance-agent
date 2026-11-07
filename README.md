# finance-agent

Agente de IA para finanças pessoais, em Python com [Strands Agents](https://strandsagents.com) e OpenAI.

## Requisitos

- Python 3.10+
- Uma chave da OpenAI

## Instalação

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows (cmd)
.venv\Scripts\activate

pip install -r requirements.txt
```

Copie `.env.example` para `.env` e preencha `OPENAI_API_KEY` (opcionalmente `OPENAI_MODEL`, padrão `gpt-4o-mini`).

## Uso

```bash
python -m app.main
```

## Testes

```bash
python -m pytest
```

## Estrutura

- `app/config.py` — leitura do `.env`
- `app/agente.py` — criação do agente (modelo OpenAI + prompt de sistema)
- `app/main.py` — chat no terminal
- `tests/` — testes (não chamam a API)
