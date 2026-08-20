import math
from dataclasses import dataclass
from typing import Self
from uuid import UUID

from pydantic import Field, model_validator

from app.extraction_schemas import StrictModel


class RetrievalEvaluationDocument(StrictModel):
    id: UUID
    content: str = Field(
        min_length=1,
        max_length=20_000,
    )


class RetrievalEvaluationQuery(StrictModel):
    name: str = Field(
        min_length=1,
        max_length=100,
    )
    question: str = Field(
        min_length=1,
        max_length=2000,
    )
    relevant_document_ids: list[UUID] = Field(
        default_factory=list,
    )


class RetrievalEvaluationDataset(StrictModel):
    name: str = Field(
        min_length=1,
        max_length=100,
    )
    documents: list[
        RetrievalEvaluationDocument
    ] = Field(min_length=1)
    queries: list[
        RetrievalEvaluationQuery
    ] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_references(
        self,
    ) -> Self:
        document_ids = {
            document.id
            for document in self.documents
        }

        if len(document_ids) != len(self.documents):
            raise ValueError(
                "Document IDs must be unique"
            )

        query_names = {
            query.name
            for query in self.queries
        }

        if len(query_names) != len(self.queries):
            raise ValueError(
                "Query names must be unique"
            )

        for query in self.queries:
            unknown_ids = (
                set(query.relevant_document_ids)
                - document_ids
            )

            if unknown_ids:
                raise ValueError(
                    f"Query {query.name} references "
                    "unknown documents"
                )

        return self


@dataclass(frozen=True, slots=True)
class RankedDocument:
    document_id: UUID
    similarity: float


@dataclass(frozen=True, slots=True)
class RetrievalQueryEvaluation:
    name: str
    answerable: bool
    top_similarity: float
    hit_at_1: float | None
    hit_at_k: float | None
    reciprocal_rank: float | None


@dataclass(frozen=True, slots=True)
class ThresholdEvaluation:
    threshold: float
    true_positives: int
    false_positives: int
    true_negatives: int
    false_negatives: int
    precision: float
    recall: float
    f1: float
    false_positive_rate: float


def cosine_similarity(
    left: list[float],
    right: list[float],
) -> float:
    if not left or len(left) != len(right):
        raise ValueError(
            "Vectors must have equal nonzero dimensions"
        )

    left_magnitude = math.sqrt(
        sum(value * value for value in left)
    )

    right_magnitude = math.sqrt(
        sum(value * value for value in right)
    )

    if left_magnitude == 0 or right_magnitude == 0:
        raise ValueError(
            "Cosine similarity requires nonzero vectors"
        )

    similarity = sum(
        left_value * right_value
        for left_value, right_value in zip(
            left,
            right,
            strict=True,
        )
    ) / (
        left_magnitude
        * right_magnitude
    )

    return max(
        -1.0,
        min(1.0, similarity),
    )


def evaluate_ranked_documents(
    query: RetrievalEvaluationQuery,
    ranked_documents: list[RankedDocument],
    *,
    top_k: int,
) -> RetrievalQueryEvaluation:
    if top_k <= 0:
        raise ValueError(
            "top_k must be greater than zero"
        )

    if not ranked_documents:
        raise ValueError(
            "At least one ranked document is required"
        )

    relevant_ids = set(
        query.relevant_document_ids
    )

    if not relevant_ids:
        return RetrievalQueryEvaluation(
            name=query.name,
            answerable=False,
            top_similarity=(
                ranked_documents[0].similarity
            ),
            hit_at_1=None,
            hit_at_k=None,
            reciprocal_rank=None,
        )

    first_relevant_rank: int | None = None

    for rank, result in enumerate(
        ranked_documents,
        start=1,
    ):
        if result.document_id in relevant_ids:
            first_relevant_rank = rank
            break

    return RetrievalQueryEvaluation(
        name=query.name,
        answerable=True,
        top_similarity=(
            ranked_documents[0].similarity
        ),
        hit_at_1=float(first_relevant_rank == 1),
        hit_at_k=float(
            first_relevant_rank is not None
            and first_relevant_rank <= top_k
        ),
        reciprocal_rank=(
            0.0
            if first_relevant_rank is None
            else 1.0 / first_relevant_rank
        ),
    )


def evaluate_threshold(
    evaluations: list[RetrievalQueryEvaluation],
    threshold: float,
) -> ThresholdEvaluation:
    if not evaluations:
        raise ValueError(
            "At least one evaluation is required"
        )

    true_positives = 0
    false_positives = 0
    true_negatives = 0
    false_negatives = 0

    for evaluation in evaluations:
        predicted_answerable = (
            evaluation.top_similarity
            >= threshold
        )

        if evaluation.answerable:
            if predicted_answerable:
                true_positives += 1
            else:
                false_negatives += 1
        elif predicted_answerable:
            false_positives += 1
        else:
            true_negatives += 1

    precision = (
        true_positives
        / (true_positives + false_positives)
        if true_positives + false_positives
        else 0.0
    )

    recall = (
        true_positives
        / (true_positives + false_negatives)
        if true_positives + false_negatives
        else 0.0
    )

    f1 = (
        2.0 * precision * recall
        / (precision + recall)
        if precision + recall
        else 0.0
    )

    false_positive_rate = (
        false_positives
        / (false_positives + true_negatives)
        if false_positives + true_negatives
        else 0.0
    )

    return ThresholdEvaluation(
        threshold=threshold,
        true_positives=true_positives,
        false_positives=false_positives,
        true_negatives=true_negatives,
        false_negatives=false_negatives,
        precision=precision,
        recall=recall,
        f1=f1,
        false_positive_rate=false_positive_rate,
    )


def select_candidate_threshold(
    evaluations: list[RetrievalQueryEvaluation],
) -> ThresholdEvaluation:
    if not evaluations:
        raise ValueError(
            "At least one evaluation is required"
        )

    scores = {
        evaluation.top_similarity
        for evaluation in evaluations
    }

    candidates = scores | {
        max(scores) + 1e-9
    }

    results = [
        evaluate_threshold(
            evaluations,
            threshold,
        )
        for threshold in candidates
    ]

    return max(
        results,
        key=lambda result: (
            result.f1,
            -result.false_positive_rate,
            result.precision,
            result.recall,
            result.threshold,
        ),
    )