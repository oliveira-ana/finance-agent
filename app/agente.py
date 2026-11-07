from strands import Agent
from strands.models.openai import OpenAIModel

from app.config import Config

PROMPT_SISTEMA = (
    "Você é um assistente de finanças pessoais. Responda em português do Brasil, "
    "de forma clara e objetiva. Não dê recomendações de investimento personalizadas."
)


def criar_agente(config: Config) -> Agent:
    modelo = OpenAIModel(
        client_args={"api_key": config.openai_api_key},
        model_id=config.openai_model,
    )
    return Agent(model=modelo, system_prompt=PROMPT_SISTEMA)
