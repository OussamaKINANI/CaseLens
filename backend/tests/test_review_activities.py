from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from temporalio.exceptions import ApplicationError

from app.review_activities import CaseReviewActivities
from app.temporal_models import (
    CaseReviewWorkflowInput,
    FinalizeReviewActivityInput,
    HumanReviewUpdate,
    ReviewRunActivityInput,
)
from tests.conftest import TestSessionLocal


def create_review_run(
    client: TestClient,
) -> tuple[dict, dict, dict]:
    case = client.post(
        "/v1/cases",
        json={
            "patient_external_id": (
                f"SYNTH-ACTIVITY-{uuid4()}"
            ),
            "requested_service": "Lumbar spine MRI",
            "priority": "routine",
        },
    ).json()

    document = client.post(
        f"/v1/cases/{case['id']}/documents",
        files={
            "file": (
                "activity-note.txt",
                b"Synthetic clinical evidence.",
                "text/plain",
            )
        },
    ).json()

    review_run = client.post(
        f"/v1/cases/{case['id']}/review-runs",
        json={
            "document_ids": [document["id"]],
        },
    ).json()

    return case, document, review_run


def build_activities() -> CaseReviewActivities:
    return CaseReviewActivities(
        session_factory=TestSessionLocal
    )


def test_review_activities_complete_approved_run(
    client: TestClient,
) -> None:
    case, document, review_run = (
        create_review_run(client)
    )

    activities = build_activities()

    start_result = activities.start_case_review(
        ReviewRunActivityInput(
            review_run_id=review_run["id"],
        )
    )

    assert start_result == "running"

    validation_result = (
        activities.validate_case_review_documents(
            CaseReviewWorkflowInput(
                review_run_id=review_run["id"],
                case_id=case["id"],
                document_ids=[document["id"]],
            )
        )
    )

    assert validation_result == "validated"

    awaiting_result = (
        activities.mark_case_review_awaiting_human(
            ReviewRunActivityInput(
                review_run_id=review_run["id"],
            )
        )
    )

    assert (
        awaiting_result
        == "awaiting_human_review"
    )

    final_result = activities.finalize_case_review(
        FinalizeReviewActivityInput(
            review_run_id=review_run["id"],
            decision="approve",
        )
    )

    assert final_result.status == "completed"

    response = client.get(
        f"/v1/cases/{case['id']}/review-runs/"
        f"{review_run['id']}"
    )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["started_at"] is not None
    assert response.json()["completed_at"] is not None


def test_start_activity_is_idempotent(
    client: TestClient,
) -> None:
    case, _, review_run = create_review_run(client)
    activities = build_activities()

    activity_input = ReviewRunActivityInput(
        review_run_id=review_run["id"],
    )

    first = activities.start_case_review(
        activity_input
    )
    second = activities.start_case_review(
        activity_input
    )

    assert first == "running"
    assert second == "running"

    audit_response = client.get(
        f"/v1/cases/{case['id']}/audit"
    )

    review_status_events = [
        event
        for event in audit_response.json()
        if (
            event["event_type"] == "status_changed"
            and event["details"].get(
                "review_run_id"
            )
            == review_run["id"]
        )
    ]

    assert len(review_status_events) == 1


def test_workflow_scope_mismatch_is_rejected(
    client: TestClient,
) -> None:
    _, document, review_run = create_review_run(
        client
    )

    activities = build_activities()

    with pytest.raises(
        ApplicationError,
        match="does not match",
    ):
        activities.validate_case_review_documents(
            CaseReviewWorkflowInput(
                review_run_id=review_run["id"],
                case_id=str(uuid4()),
                document_ids=[document["id"]],
            )
        )


def test_rejection_notes_are_hashed_in_audit(
    client: TestClient,
) -> None:
    case, document, review_run = (
        create_review_run(client)
    )

    activities = build_activities()

    activities.start_case_review(
        ReviewRunActivityInput(
            review_run_id=review_run["id"],
        )
    )

    activities.validate_case_review_documents(
        CaseReviewWorkflowInput(
            review_run_id=review_run["id"],
            case_id=case["id"],
            document_ids=[document["id"]],
        )
    )

    activities.mark_case_review_awaiting_human(
        ReviewRunActivityInput(
            review_run_id=review_run["id"],
        )
    )

    activities.finalize_case_review(
        FinalizeReviewActivityInput(
            review_run_id=review_run["id"],
            decision="reject",
            notes="Synthetic rejection reason",
        )
    )

    audit_response = client.get(
        f"/v1/cases/{case['id']}/audit"
    )

    human_review_event = next(
        event
        for event in audit_response.json()
        if event["event_type"]
        == "human_review_completed"
    )

    assert human_review_event["details"][
        "decision"
    ] == "reject"

    assert human_review_event["details"][
        "notes_sha256"
    ] is not None

    assert (
        "Synthetic rejection reason"
        not in str(human_review_event)
    )