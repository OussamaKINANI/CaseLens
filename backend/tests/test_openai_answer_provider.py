from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.answer_service import (
    INSUFFICIENT_EVIDENCE_ANSWER,
    AnswerEvidence,
    AnswerProviderError,
    verify_grounded_answer,
)
from app.openai_answer_provider import (
    OpenAIAnswerProvider,
)
from app.openai_answer_schemas import (
    OpenAIAnswerCitation,
    OpenAIGroundedAnswerResponse,
)


class StubResponses:
    def __init__(
        self,
        parsed: OpenAIGroundedAnswerResponse,
    ) -> None:
        self.parsed = parsed
        self.kwargs: dict | None = None

    def parse(self, **kwargs) -> SimpleNamespace:
        self.kwargs = kwargs

        return SimpleNamespace(
            output_parsed=self.parsed
        )


class FailingResponses:
    def parse(self, **kwargs) -> None:
        raise TimeoutError("Synthetic timeout")


def create_evidence() -> AnswerEvidence:
    content = (
        "Lower back pain is present. "
        "Physical therapy was attempted."
    )

    return AnswerEvidence(
        chunk_id=uuid4(),
        document_id=uuid4(),
        content=content,
        start_char=100,
        end_char=100 + len(content),
    )


def create_provider(
    responses: object,
) -> OpenAIAnswerProvider:
    client = SimpleNamespace(
        responses=responses
    )

    return OpenAIAnswerProvider(
        api_key="test-key",
        model_name="gpt-5-mini",
        client=client,
    )


def test_openai_provider_maps_verified_citation(
) -> None:
    evidence = create_evidence()

    raw_answer = OpenAIGroundedAnswerResponse(
        supported=True,
        answer="Physical therapy was attempted.",
        citations=[
            OpenAIAnswerCitation(
                chunk_id=evidence.chunk_id,
                exact_quote=(
                    "Physical therapy was attempted."
                ),
            )
        ],
    )

    responses = StubResponses(raw_answer)
    provider = create_provider(responses)

    answer = provider.answer(
        "What treatment was attempted?",
        [evidence],
    )

    assert answer.supported is True
    assert answer.answer == (
        "Physical therapy was attempted."
    )
    assert answer.citations[0].document_id == (
        evidence.document_id
    )
    assert answer.citations[0].start_char == 128
    assert answer.citations[0].end_char == 159

    verify_grounded_answer(
        answer,
        [evidence],
    )

    assert responses.kwargs is not None
    assert responses.kwargs["model"] == (
        "gpt-5-mini"
    )
    assert responses.kwargs["text_format"] is (
        OpenAIGroundedAnswerResponse
    )


def test_openai_provider_normalizes_abstention(
) -> None:
    evidence = create_evidence()

    raw_answer = OpenAIGroundedAnswerResponse(
        supported=False,
        answer="The record does not say.",
        citations=[],
    )

    answer = create_provider(
        StubResponses(raw_answer)
    ).answer(
        "What kidney medication was prescribed?",
        [evidence],
    )

    assert answer.supported is False
    assert answer.answer == (
        INSUFFICIENT_EVIDENCE_ANSWER
    )
    assert answer.citations == []


def test_openai_provider_rejects_unknown_chunk(
) -> None:
    evidence = create_evidence()

    raw_answer = OpenAIGroundedAnswerResponse(
        supported=True,
        answer="Unsupported answer.",
        citations=[
            OpenAIAnswerCitation(
                chunk_id=uuid4(),
                exact_quote="Lower back pain",
            )
        ],
    )

    with pytest.raises(
        AnswerProviderError,
        match="unretrieved chunk",
    ):
        create_provider(
            StubResponses(raw_answer)
        ).answer(
            "What does the evidence say?",
            [evidence],
        )


def test_openai_provider_rejects_unmatched_quote(
) -> None:
    evidence = create_evidence()

    raw_answer = OpenAIGroundedAnswerResponse(
        supported=True,
        answer="A fabricated answer.",
        citations=[
            OpenAIAnswerCitation(
                chunk_id=evidence.chunk_id,
                exact_quote="A fabricated quote.",
            )
        ],
    )

    with pytest.raises(
        AnswerProviderError,
        match="quote was not found",
    ):
        create_provider(
            StubResponses(raw_answer)
        ).answer(
            "What does the evidence say?",
            [evidence],
        )


def test_openai_provider_wraps_api_failure(
) -> None:
    evidence = create_evidence()

    with pytest.raises(
        AnswerProviderError,
        match="OpenAI answer request failed",
    ):
        create_provider(
            FailingResponses()
        ).answer(
            "What treatment was attempted?",
            [evidence],
        )