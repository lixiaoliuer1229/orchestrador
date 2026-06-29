"""LLM factory — single place to instantiate chat models."""
from functools import lru_cache
from typing import Optional

from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI

from src.utils.config import settings
from src.utils.logger import logger


@lru_cache(maxsize=1)
def get_openai_llm(model: Optional[str] = None, temperature: float = 0.0):
    """Return a cached ChatOpenAI instance."""
    if not settings.openai_api_key:
        logger.warning("OPENAI_API_KEY not set — ChatOpenAI calls will fail.")
    return ChatOpenAI(
        model=model or settings.openai_model,
        temperature=temperature,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
    )


@lru_cache(maxsize=1)
def get_anthropic_llm(model: Optional[str] = None, temperature: float = 0.0):
    """Return a cached ChatAnthropic instance."""
    if not settings.anthropic_api_key:
        logger.warning("ANTHROPIC_API_KEY not set — ChatAnthropic calls will fail.")
    return ChatAnthropic(
        model=model or settings.anthropic_model,
        temperature=temperature,
        api_key=settings.anthropic_api_key,
    )


__all__ = ["get_openai_llm", "get_anthropic_llm"]