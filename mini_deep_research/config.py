"""Validated runtime configuration for mini DeepResearch."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from dotenv import load_dotenv
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration supplied by the deployment environment."""

    app_env: Literal["development", "test", "production"] = "production"
    anthropic_api_key: SecretStr
    anthropic_model: str
    anthropic_base_url: str | None = None
    tavily_api_key: SecretStr

    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load environment variables once and validate required production settings."""

    # Deployment-provided variables win; .env is only a local fallback.
    load_dotenv(override=False)
    return Settings()


__all__ = ["Settings", "get_settings"]
