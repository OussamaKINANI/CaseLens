import pytest

from app.config import Settings
from app.embedding_factory import (
    create_embedding_provider,
)
from app.embedding_service import (
    EmbeddingProviderError,
    FakeEmbeddingProvider,
)
from app.openai_embedding_provider import (
    OpenAIEmbeddingProvider,
)


def make_settings(
    **overrides: object,
) -> Settings:
    values: dict[str, object] = {
        "database_url": (
            "postgresql+psycopg://user:password"
            "@localhost:5432/caselens"
        ),
        "test_database_url": (
            "postgresql+psycopg://user:password"
            "@localhost:5432/caselens_test"
        ),
        "embedding_provider": "fake",
        "openai_api_key": None,
        "openai_embedding_model": (
            "text-embedding-3-small"
        ),
        "embedding_dimensions": 1536,
        "openai_timeout_seconds": 120.0,
    }

    values.update(overrides)

    return Settings(
        _env_file=None,
        **values,
    )


def test_factory_creates_fake_provider() -> None:
    settings = make_settings(
        embedding_provider="fake",
        embedding_dimensions=1536,
    )

    provider = create_embedding_provider(settings)

    assert isinstance(
        provider,
        FakeEmbeddingProvider,
    )
    assert provider.dimensions == 1536


def test_factory_requires_key_for_openai() -> None:
    settings = make_settings(
        embedding_provider="openai",
        openai_api_key=None,
    )

    with pytest.raises(
        EmbeddingProviderError,
        match="OPENAI_API_KEY",
    ):
        create_embedding_provider(settings)


def test_factory_creates_openai_provider() -> None:
    settings = make_settings(
        embedding_provider="openai",
        openai_api_key="synthetic-test-key",
        openai_embedding_model=(
            "text-embedding-3-small"
        ),
        embedding_dimensions=1536,
    )

    provider = create_embedding_provider(settings)

    assert isinstance(
        provider,
        OpenAIEmbeddingProvider,
    )
    assert provider.model_name == (
        "text-embedding-3-small"
    )
    assert provider.dimensions == 1536