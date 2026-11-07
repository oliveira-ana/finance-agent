import os
from dataclasses import dataclass

from dotenv import load_dotenv

MODELO_PADRAO = "gpt-4o-mini"


@dataclass(frozen=True)
class Config:
    openai_api_key: str
    openai_model: str


def carregar_config() -> Config:
    load_dotenv()
    chave = os.getenv("OPENAI_API_KEY", "").strip()
    if not chave:
        raise RuntimeError("OPENAI_API_KEY não definida. Copie .env.example para .env e preencha a chave.")
    modelo = os.getenv("OPENAI_MODEL", "").strip() or MODELO_PADRAO
    return Config(openai_api_key=chave, openai_model=modelo)
