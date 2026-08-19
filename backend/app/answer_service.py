import re
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.answer_schemas import (
    GroundedAnswer,
    GroundedAnswerCitation,
)


INSUFFICIENT_EVIDENCE_ANSWER = (
    "Insufficient evidence in the indexed case documents."
)

_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+")
_SENTENCE_PATTERN = re.compile(
    r"[^.!?\n]+(?:[.!?]|$)"
)

_STOP_WORDS = frozenset({
    "a",
    "about",
    "an",
    "and",
    "did",
    "does",
    "for",
    "has",
    "have",
    "in",
    "is",
    "of",
    "patient",
    "record",
    "say",
    "the",
    "to",
    "was",
    "were",
    "what",
    "which",
})


class AnswerProviderError(RuntimeError):
    """Raised when an answer provider fails safely."""


class AnswerEvidenceVerificationError(ValueError):
    """Raised when an answer citation is not trustworthy."""


@dataclass(frozen=True, slots=True)
class AnswerEvidence:
    chunk_id: UUID
    document_id: UUID
    content: str
    start_char: int
    end_char: int


class AnswerProvider(Protocol):
    provider_name: str
    model_name: str

    def answer(
        self,
        question: str,
        evidence: list[AnswerEvidence],
    ) -> GroundedAnswer:
        ...


def create_insufficient_evidence_answer(
) -> GroundedAnswer:
    return GroundedAnswer(
        supported=False,
        answer=INSUFFICIENT_EVIDENCE_ANSWER,
        citations=[],
    )


class FakeAnswerProvider:
    """
    Deterministic provider for tests.

    It selects the evidence sentence with the highest
    exact-token overlap with the question.
    """

    provider_name = "fake"
    model_name = "deterministic-grounded-v1"

    def answer(
        self,
        question: str,
        evidence: list[AnswerEvidence],
    ) -> GroundedAnswer:
        normalized_question = question.strip()

        if not normalized_question:
            raise AnswerProviderError(
                "Question cannot be blank"
            )

        if not evidence:
            return create_insufficient_evidence_answer()

        question_tokens = {
            token
            for token in _TOKEN_PATTERN.findall(
                normalized_question.lower()
            )
            if token not in _STOP_WORDS
        }

        if not question_tokens:
            return create_insufficient_evidence_answer()

        best_score = 0
        best_quote: str | None = None
        best_evidence: AnswerEvidence | None = None
        best_local_start = 0

        for source in evidence:
            if (
                source.end_char - source.start_char
                != len(source.content)
            ):
                raise AnswerProviderError(
                    "Evidence character range does not "
                    "match its content"
                )

            for match in _SENTENCE_PATTERN.finditer(
                source.content
            ):
                raw_sentence = match.group(0)
                quote = raw_sentence.strip()

                if not quote:
                    continue

                leading_whitespace = (
                    len(raw_sentence)
                    - len(raw_sentence.lstrip())
                )

                local_start = (
                    match.start()
                    + leading_whitespace
                )

                sentence_tokens = set(
                    _TOKEN_PATTERN.findall(
                        quote.lower()
                    )
                )

                score = len(
                    question_tokens & sentence_tokens
                )

                if score > best_score:
                    best_score = score
                    best_quote = quote
                    best_evidence = source
                    best_local_start = local_start

        if (
            best_score == 0
            or best_quote is None
            or best_evidence is None
        ):
            return create_insufficient_evidence_answer()

        citation_start = (
            best_evidence.start_char
            + best_local_start
        )

        citation_end = (
            citation_start
            + len(best_quote)
        )

        return GroundedAnswer(
            supported=True,
            answer=best_quote,
            citations=[
                GroundedAnswerCitation(
                    chunk_id=best_evidence.chunk_id,
                    document_id=(
                        best_evidence.document_id
                    ),
                    exact_quote=best_quote,
                    start_char=citation_start,
                    end_char=citation_end,
                )
            ],
        )


def verify_grounded_answer(
    answer: GroundedAnswer,
    evidence: list[AnswerEvidence],
) -> None:
    if not answer.supported:
        if (
            answer.answer
            != INSUFFICIENT_EVIDENCE_ANSWER
        ):
            raise AnswerEvidenceVerificationError(
                "Unsupported answer must use the "
                "standard insufficient-evidence response"
            )

        return

    evidence_by_chunk_id = {
        source.chunk_id: source
        for source in evidence
    }

    for citation_index, citation in enumerate(
        answer.citations
    ):
        source = evidence_by_chunk_id.get(
            citation.chunk_id
        )

        if source is None:
            raise AnswerEvidenceVerificationError(
                "Citation references an unretrieved chunk: "
                f"citation={citation_index}"
            )

        if citation.document_id != source.document_id:
            raise AnswerEvidenceVerificationError(
                "Citation document does not match its chunk: "
                f"citation={citation_index}"
            )

        if (
            citation.start_char < source.start_char
            or citation.end_char > source.end_char
        ):
            raise AnswerEvidenceVerificationError(
                "Citation range exceeds the retrieved chunk: "
                f"citation={citation_index}"
            )

        local_start = (
            citation.start_char
            - source.start_char
        )

        local_end = (
            citation.end_char
            - source.start_char
        )

        actual_quote = source.content[
            local_start:local_end
        ]

        if actual_quote != citation.exact_quote:
            raise AnswerEvidenceVerificationError(
                "Citation quote does not match the "
                "retrieved evidence: "
                f"citation={citation_index}"
            )