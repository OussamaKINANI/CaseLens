from app.config import settings
from app.extraction_service import (
    ExtractionProvider,
    FakeExtractionProvider,
)
from app.openai_extraction_provider import (
    OpenAIExtractionProvider,
)


def get_extraction_provider() -> ExtractionProvider:
    if settings.ai_provider == "fake":
        return FakeExtractionProvider()

    if not settings.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is required when AI_PROVIDER=openai"
        )

    return OpenAIExtractionProvider(
        api_key=settings.openai_api_key,
        model_name=settings.openai_model,
        timeout_seconds=settings.openai_timeout_seconds,
    )