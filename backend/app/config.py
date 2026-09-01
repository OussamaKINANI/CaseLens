from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from typing import Literal
from pydantic import Field

from app.auth_schemas import ReviewerRole



PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Placeholder so a fresh checkout and the test suite run without any
# secret configuration. Any deployment must override it: tokens signed
# with a published key can be forged by anyone.
DEVELOPMENT_JWT_SECRET_KEY = (
    "caselens-development-only-secret-change-me"
)


class Settings(BaseSettings):
    app_name: str = "CaseLens API"
    environment: str = "development"
    database_url: str
    test_database_url: str

    jwt_secret_key: str = Field(
        default=DEVELOPMENT_JWT_SECRET_KEY,
        min_length=32,
    )

    access_token_expire_minutes: int = Field(
        default=60,
        gt=0,
        le=1440,
    )

    # Bootstrap sign-in account, created by app.seed_reviewers.
    # Seeding is skipped entirely when no password is configured.
    seed_reviewer_email: str | None = None
    seed_reviewer_password: str | None = None
    seed_reviewer_full_name: str = "CaseLens Reviewer"
    seed_reviewer_role: ReviewerRole = ReviewerRole.administrator

    ai_provider: Literal["fake", "openai"] = "fake"
    openai_api_key: str | None = None
    openai_model: str = "gpt-5-mini"
    openai_timeout_seconds: float = 120.0

    embedding_provider: Literal["fake", "openai"] = "fake"
    openai_embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536

    # Calibrated for text-embedding-3-small question-vs-chunk retrieval:
    # relevant paraphrases score ~0.35-0.6, unrelated questions ~0.25-0.30.
    # This is a coarse pre-filter; the answer provider still refuses when
    # the retrieved evidence cannot support a cited answer.
    rag_min_similarity: float = Field(
        default=0.32,
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


def uses_development_jwt_secret_key() -> bool:
    return settings.jwt_secret_key == DEVELOPMENT_JWT_SECRET_KEY