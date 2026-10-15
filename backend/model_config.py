"""Builds the LLM every agent uses: gpt-6-luna routed through Portkey.

It uses the OpenAI *Responses* API (/v1/responses). gpt-6-luna refuses tool calls on
/v1/chat/completions while reasoning is on ("Function tools with reasoning_effort are
not supported ... use /v1/responses"), and every agent here needs tools.

The assignment allows exactly one model, so it is fixed here and the code refuses to
start if .env asks for anything else. The key comes from PORTKEY_API_KEY in the
project .env (never committed).
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

# Load the .env sitting at the project root (one level above backend/).
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

MODEL_NAME = "gpt-6-luna"  # the only model allowed in this assignment
PORTKEY_BASE_URL = "https://api.portkey.ai/v1"


def build_model() -> OpenAIResponsesModel:
    api_key = os.getenv("PORTKEY_API_KEY")
    if not api_key:
        raise RuntimeError(
            "PORTKEY_API_KEY is missing. Copy .env.example to .env and add your Portkey key."
        )
    requested = os.getenv("PORTKEY_MODEL", MODEL_NAME)
    if requested != MODEL_NAME:
        raise RuntimeError(f"Only {MODEL_NAME} is allowed; .env asks for {requested!r}.")
    provider = OpenAIProvider(
        api_key=api_key,
        base_url=os.getenv("PORTKEY_BASE_URL", PORTKEY_BASE_URL),
    )
    return OpenAIResponsesModel(MODEL_NAME, provider=provider)
