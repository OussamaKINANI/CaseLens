from app.answer_service import (
    AnswerProvider,
    AnswerProviderError,
    FakeAnswerProvider,
)
from app.config import settings
from app.openai_answer_provider import (
    OpenAIAnswerProvider,
)


def get_answer_provider() -> AnswerProvider:
    if settings.ai_provider == "fake":
        return FakeAnswerProvider()

    if settings.ai_provider == "openai":
        if not settings.openai_api_key:
            raise AnswerProviderError(
                "OPENAI_API_KEY is required when "
                "AI_PROVIDER=openai"
            )

        return OpenAIAnswerProvider(
            api_key=settings.openai_api_key,
            model_name=settings.openai_model,
            timeout_seconds=(
                settings.openai_timeout_seconds
            ),
        )

    raise AnswerProviderError(
        "Unsupported answer provider: "
        f"{settings.ai_provider}"
    )