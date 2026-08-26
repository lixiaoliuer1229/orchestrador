"""Shared LLM gateway configuration and per-request model selection."""

from __future__ import annotations

import os

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic


load_dotenv(override=False)


SUPPORTED_MODELS = (
    "coding-chat",
    "strong-chat",
    "cheap-chat",
    "minimax-latest",
)
DEFAULT_MODEL = "coding-chat"


def configured_model() -> str:
    """Return a safe configured default model."""
    model = os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL)
    return model if model in SUPPORTED_MODELS else DEFAULT_MODEL


def create_chat_model(model_name: str | None = None) -> ChatAnthropic:
    """Create a gateway model for one explicit internal model alias."""
    selected_model = model_name or configured_model()
    if selected_model not in SUPPORTED_MODELS:
        raise ValueError(f"Unsupported model: {selected_model}")
    return ChatAnthropic(
        model_name=selected_model,
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        base_url=os.getenv("ANTHROPIC_BASE_URL") or None,
    )
