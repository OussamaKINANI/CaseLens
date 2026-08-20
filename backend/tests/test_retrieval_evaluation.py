from uuid import uuid4

import pytest

from app.retrieval_evaluation import (
    RankedDocument,
    RetrievalEvaluationQuery,
    RetrievalQueryEvaluation,
    cosine_similarity,
    evaluate_ranked_documents,
    select_candidate_threshold,
)


def test_cosine_similarity(
) -> None:
    assert cosine_similarity(
        [1.0, 0.0],
        [1.0, 0.0],
    ) == pytest.approx(1.0)

    assert cosine_similarity(
        [1.0, 0.0],
        [0.0, 1.0],
    ) == pytest.approx(0.0)


def test_retrieval_metrics_use_relevant_rank(
) -> None:
    relevant_id = uuid4()
    distractor_id = uuid4()

    query = RetrievalEvaluationQuery(
        name="therapy",
        question="What treatment was attempted?",
        relevant_document_ids=[relevant_id],
    )

    evaluation = evaluate_ranked_documents(
        query,
        [
            RankedDocument(
                document_id=distractor_id,
                similarity=0.9,
            ),
            RankedDocument(
                document_id=relevant_id,
                similarity=0.8,
            ),
        ],
        top_k=3,
    )

    assert evaluation.hit_at_1 == 0.0
    assert evaluation.hit_at_k == 1.0
    assert evaluation.reciprocal_rank == 0.5


def test_threshold_selection_separates_queries(
) -> None:
    evaluations = [
        RetrievalQueryEvaluation(
            name="answerable-one",
            answerable=True,
            top_similarity=0.80,
            hit_at_1=1.0,
            hit_at_k=1.0,
            reciprocal_rank=1.0,
        ),
        RetrievalQueryEvaluation(
            name="answerable-two",
            answerable=True,
            top_similarity=0.70,
            hit_at_1=1.0,
            hit_at_k=1.0,
            reciprocal_rank=1.0,
        ),
        RetrievalQueryEvaluation(
            name="unanswerable-one",
            answerable=False,
            top_similarity=0.40,
            hit_at_1=None,
            hit_at_k=None,
            reciprocal_rank=None,
        ),
        RetrievalQueryEvaluation(
            name="unanswerable-two",
            answerable=False,
            top_similarity=0.30,
            hit_at_1=None,
            hit_at_k=None,
            reciprocal_rank=None,
        ),
    ]

    selected = select_candidate_threshold(
        evaluations
    )

    assert selected.threshold == pytest.approx(
        0.70
    )
    assert selected.f1 == pytest.approx(1.0)
    assert selected.false_positive_rate == 0.0
    assert selected.false_negatives == 0