"""Centralized configuration loaded from environment variables / .env."""
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- LLM ----
    openai_api_key: Optional[str] = Field(default=None)
    openai_base_url: Optional[str] = Field(default=None)
    openai_model: str = Field(default="gpt-4o-mini")

    anthropic_api_key: Optional[str] = Field(default=None)
    anthropic_base_url: Optional[str] = Field(default=None)
    anthropic_model: str = Field(default="claude-sonnet-4-6")

    # ---- LangSmith ----
    langsmith_tracing: bool = Field(default=False)
    langsmith_api_key: Optional[str] = Field(default=None)
    langsmith_project: str = Field(default="langgraph-backend-studio")

    # ---- Storage ----
    chroma_persist_dir: str = Field(default="./data/chroma")
    redis_url: str = Field(default="redis://localhost:6379/0")
    langgraph_database_url: str = Field(default="sqlite:///./data/langgraph.db")

    # ---- Server ----
    app_host: str = Field(default="0.0.0.0")
    app_port: int = Field(default=8000)
    app_env: str = Field(default="development")
    log_level: str = Field(default="INFO")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings accessor."""
    return Settings()


settings = get_settings()