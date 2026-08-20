from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from typing import Literal
from pydantic import Field



PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "CaseLens API"
    environment: str = "development"
    database_url: str
    test_database_url: str

    ai_provider: Literal["fake", "openai"] = "fake"
    openai_api_key: str | None = None
    openai_model: str = "gpt-5-mini"
    openai_timeout_seconds: float = 120.0

    embedding_provider: Literal["fake", "openai"] = "fake"
    openai_embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536

    rag_min_similarity: float = Field(
        default=0.50,
        ge=-1.0,
        le=1.0,
    )
    temporal_address: str = Field(
        default="localhost:7233",
        min_length=1,
    )

    temporal_namespace: str = Field(
        default="default",
        min_length=1,
    )

    temporal_task_queue: str = Field(
        default="caselens-review",
        min_length=1,
    )
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
def get_rag_min_similarity() -> float:
    return settings.rag_min_similarity