from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.review_schemas import (
    CaseReviewRunCreate,
    HumanReviewDecision,
    HumanReviewRequest,
    ReviewRunStatus,
)


def test_review_run_accepts_unique_documents() -> None:
    first_document_id = uuid4()
    second_document_id = uuid4()

    payload = CaseReviewRunCreate(
        document_ids=[
            first_document_id,
            second_document_id,
        ]
    )

    assert payload.document_ids == [
        first_document_id,
        second_document_id,
    ]


def test_review_run_rejects_duplicate_documents() -> None:
    document_id = uuid4()

    with pytest.raises(
        ValidationError,
        match="must not contain duplicates",
    ):
        CaseReviewRunCreate(
            document_ids=[
                document_id,
                document_id,
            ]
        )


def test_review_run_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        CaseReviewRunCreate.model_validate(
            {
                "document_ids": [str(uuid4())],
                "bypass_safety_review": True,
            }
        )


def test_rejection_requires_notes() -> None:
    with pytest.raises(
        ValidationError,
        match="notes are required",
    ):
        HumanReviewRequest(
            decision=HumanReviewDecision.reject,
        )


def test_approval_does_not_require_notes() -> None:
    payload = HumanReviewRequest(
        decision=HumanReviewDecision.approve,
    )

    assert payload.decision is HumanReviewDecision.approve
    assert payload.notes is None


def test_review_run_status_values_are_stable() -> None:
    assert ReviewRunStatus.queued.value == "queued"
    assert (
        ReviewRunStatus.awaiting_human_review.value
        == "awaiting_human_review"
    )