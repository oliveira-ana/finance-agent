# finance-agent

Chat bancário no terminal, em Python, com [Strands Agents](https://strandsagents.com) e o modelo da OpenAI. Usa dados bancários **fictícios** em arquivos JSON locais e tem perfis de acesso (cliente, atendente e aprovador).

Documentação: [requisito RF01](requisitos/RF01-chat-bancario-com-perfis.md), [design](requisitos/RF01-design.md) e [plano de implementação](requisitos/RF01-plano-implementacao.md).

## Requisitos

- Python 3.10+ (testado no 3.14, Windows)
- Uma chave da OpenAI

## Instalação (Windows, cmd)

```cmd
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Abra o `.env` e preencha `OPENAI_API_KEY`. Os outros parâmetros (limites de saque e estorno, bloqueio de PIN, retenção) já vêm com os valores do RF01.

No Linux/macOS: `python -m venv .venv`, `source .venv/bin/activate` e `cp .env.example .env`.

## Carga inicial dos dados

Cria a pasta `dados/` (fora do git) com usuários e contas fictícios:

```cmd
python -m app.carga_inicial
```

O script pede o PIN de cada usuário (4 a 6 dígitos). Para testes rápidos, `--demo` usa PINs fixos, e `--forcar` recria a base.

| Usuário | Perfil | Conta | PIN com `--demo` | Observação |
|---|---|---|---|---|
| `maria` | cliente | 0001-1 | 1111 | 10 saques de R$ 200: acima de R$ 600 precisa de aprovador |
| `joao` | cliente | 0002-2 | 2222 | sem histórico de saques: acima de R$ 1.000 precisa de aprovador |
| `paula` | atendente | — | 3333 | consulta clientes e faz estorno |
| `carlos` | aprovador | — | 4444 | não faz login; só aprova operações |

## Uso

```cmd
python -m app.main
```

Faça login com usuário e PIN e converse em português: "qual meu saldo?", "extrato de outubro", "deposita 200", "saca 700". Como atendente: "saldo da conta 0001-1", "estorno de 300 na conta da maria, motivo tarifa cobrada indevidamente".

Depósito, saque e estorno pedem confirmação no terminal. Saques fora do padrão e estornos acima de R$ 1.000 pedem as credenciais de um aprovador, também no terminal. Usuário e PIN nunca são enviados à OpenAI.

Comandos que não passam pela IA:

| Comando | O que faz |
|---|---|
| `meus dados` | mostra seus dados pessoais completos (LGPD, direito de acesso) |
| `apagar meu histórico` | apaga suas conversas salvas e começa uma conversa nova |
| `logout` | encerra a sessão e volta ao login |
| `sair` | encerra o programa |

## Onde ficam os dados

| Arquivo | Conteúdo |
|---|---|
| `dados/usuarios.json` | usuários, dados pessoais fictícios, hash + salt do PIN |
| `dados/contas.json` | contas e saldos (em centavos) |
| `dados/movimentacoes.json` | depósitos, saques e estornos, com quem aprovou |
| `dados/auditoria.jsonl` | um evento por linha, com dados pessoais mascarados |
| `dados/sessoes/` | memória de cada login (FileSessionManager do Strands) |

Ao iniciar, o programa apaga as sessões com mais de 90 dias e os eventos de auditoria com mais de 5 anos.

## Testes

```cmd
python -m pytest
```

Os testes não chamam a OpenAI: usam uma pasta `dados` temporária e um modelo simulado.

## Estrutura

| Módulo | Responsabilidade |
|---|---|
| `app/main.py` | login, comandos e loop do chat |
| `app/config.py` | leitura do `.env` |
| `app/agente.py` | agente Strands: modelo OpenAI, prompt, tools do perfil, sessão em arquivo e proteções |
| `app/tools.py` | tools do agente, criadas por perfil |
| `app/operacoes.py` | regras de negócio (saldo, extrato, depósito, saque, estorno, aprovação) |
| `app/permissoes.py` | matriz perfil × operação |
| `app/auth.py` | PIN com PBKDF2, bloqueio e validação do aprovador |
| `app/aprovacao.py` | confirmação e credenciais do aprovador no terminal |
| `app/protecoes.py` | limite de tools por mensagem e auditoria das chamadas |
| `app/lgpd.py` | mascaramento, `meus dados`, `apagar meu histórico` e retenção |
| `app/auditoria.py` | `auditoria.jsonl` |
| `app/repositorio.py` | leitura e gravação atômica dos JSON |
| `app/sessao.py` | usuário logado e índice de sessões |
| `app/servicos.py` | monta os serviços a partir da configuração |
| `app/carga_inicial.py` | base fictícia |
