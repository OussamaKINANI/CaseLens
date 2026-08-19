from uuid import uuid4

import pytest

from app.answer_schemas import (
    GroundedAnswer,
    GroundedAnswerCitation,
)
from app.answer_service import (
    INSUFFICIENT_EVIDENCE_ANSWER,
    AnswerEvidence,
    AnswerEvidenceVerificationError,
    FakeAnswerProvider,
    verify_grounded_answer,
)


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


def test_fake_provider_returns_grounded_answer(
) -> None:
    evidence = create_evidence()

    answer = FakeAnswerProvider().answer(
        "What treatment was attempted?",
        [evidence],
    )

    assert answer.supported is True
    assert answer.answer == (
        "Physical therapy was attempted."
    )
    assert len(answer.citations) == 1

    citation = answer.citations[0]

    assert citation.chunk_id == evidence.chunk_id
    assert citation.document_id == evidence.document_id
    assert citation.exact_quote == answer.answer

    verify_grounded_answer(
        answer,
        [evidence],
    )


def test_fake_provider_abstains_without_support(
) -> None:
    evidence = create_evidence()

    answer = FakeAnswerProvider().answer(
        "What kidney medication was prescribed?",
        [evidence],
    )

    assert answer.supported is False
    assert answer.answer == (
        INSUFFICIENT_EVIDENCE_ANSWER
    )
    assert answer.citations == []

    verify_grounded_answer(
        answer,
        [evidence],
    )


def test_verification_rejects_unretrieved_chunk(
) -> None:
    evidence = create_evidence()

    answer = GroundedAnswer(
        supported=True,
        answer="Physical therapy was attempted.",
        citations=[
            GroundedAnswerCitation(
                chunk_id=uuid4(),
                document_id=evidence.document_id,
                exact_quote=(
                    "Physical therapy was attempted."
                ),
                start_char=128,
                end_char=159,
            )
        ],
    )

    with pytest.raises(
        AnswerEvidenceVerificationError,
        match="unretrieved chunk",
    ):
        verify_grounded_answer(
            answer,
            [evidence],
        )


def test_verification_rejects_modified_quote(
) -> None:
    evidence = create_evidence()

    answer = GroundedAnswer(
        supported=True,
        answer="Kidney disease.",
        citations=[
            GroundedAnswerCitation(
                chunk_id=evidence.chunk_id,
                document_id=evidence.document_id,
                exact_quote="Kidney disease.",
                start_char=100,
                end_char=115,
            )
        ],
    )

    with pytest.raises(
        AnswerEvidenceVerificationError,
        match="does not match",
    ):
        verify_grounded_answer(
            answer,
            [evidence],
        )