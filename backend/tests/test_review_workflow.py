import pytest

from app.review_workflow import CaseReviewWorkflow
from app.temporal_models import HumanReviewUpdate


REVIEWER_ID = "11111111-1111-4111-8111-111111111111"
REVIEWER_LABEL = "Test Reviewer"


def human_review_update(
    decision: str,
    notes: str | None = None,
) -> HumanReviewUpdate:
    return HumanReviewUpdate(
        decision=decision,
        notes=notes,
        reviewer_id=REVIEWER_ID,
        reviewer_label=REVIEWER_LABEL,
    )


def test_workflow_starts_in_created_phase() -> None:
    review_workflow = CaseReviewWorkflow()

    assert review_workflow.current_phase() == "created"


def test_human_approval_is_accepted() -> None:
    review_workflow = CaseReviewWorkflow()

    update = human_review_update("approve")

    review_workflow.validate_human_review(update)

    result = review_workflow.submit_human_review(
        update
    )

    assert result == "accepted"


def test_rejection_requires_notes() -> None:
    review_workflow = CaseReviewWorkflow()

    with pytest.raises(
        ValueError,
        match="notes are required",
    ):
        review_workflow.validate_human_review(
            human_review_update("reject")
        )


def test_invalid_decision_is_rejected() -> None:
    review_workflow = CaseReviewWorkflow()

    with pytest.raises(
        ValueError,
        match="decision must be approve or reject",
    ):
        review_workflow.validate_human_review(
            human_review_update("override")
        )


def test_reviewer_identity_is_required() -> None:
    review_workflow = CaseReviewWorkflow()

    with pytest.raises(
        ValueError,
        match="reviewer identity is required",
    ):
        review_workflow.validate_human_review(
            HumanReviewUpdate(
                decision="approve",
            )
        )


def test_second_human_decision_is_rejected() -> None:
    review_workflow = CaseReviewWorkflow()

    first_update = human_review_update("approve")

    review_workflow.validate_human_review(
        first_update
    )

    review_workflow.submit_human_review(
        first_update
    )

    with pytest.raises(
        ValueError,
        match="decision already exists",
    ):
        review_workflow.validate_human_review(
            human_review_update("approve")
        )
