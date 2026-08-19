from app.config import Settings, settings
from app.embedding_service import (
    EmbeddingProvider,
    EmbeddingProviderError,
    FakeEmbeddingProvider,
)
from app.openai_embedding_provider import (
    OpenAIEmbeddingProvider,
)


def create_embedding_provider(
    app_settings: Settings | None = None,
) -> EmbeddingProvider:
    selected_settings = app_settings or settings

    if selected_settings.embedding_provider == "fake":
        return FakeEmbeddingProvider(
            dimensions=(
                selected_settings.embedding_dimensions
            ),
        )

    if selected_settings.embedding_provider == "openai":
        if not selected_settings.openai_api_key:
            raise EmbeddingProviderError(
                "OPENAI_API_KEY is required when "
                "EMBEDDING_PROVIDER=openai"
            )

        return OpenAIEmbeddingProvider(
            api_key=selected_settings.openai_api_key,
            model_name=(
                selected_settings.openai_embedding_model
            ),
            dimensions=(
                selected_settings.embedding_dimensions
            ),
            timeout_seconds=(
                selected_settings.openai_timeout_seconds
            ),
        )

    raise EmbeddingProviderError(
        "Unsupported embedding provider: "
        f"{selected_settings.embedding_provider}"
    )

def get_embedding_provider() -> EmbeddingProvider:
    return create_embedding_provider()