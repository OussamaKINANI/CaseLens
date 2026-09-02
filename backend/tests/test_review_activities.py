from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from temporalio.exceptions import ApplicationError

from app.review_activities import CaseReviewActivities
from app.temporal_models import (
    CaseReviewWorkflowInput,
    FailReviewActivityInput,
    FinalizeReviewActivityInput,
    ReviewRunActivityInput,
)
from tests.conftest import (
    ADMINISTRATOR_ID,
    TestSessionLocal,
)


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


def get_case(
    client: TestClient,
    case_id: str,
) -> dict:
    response = client.get(
        f"/v1/cases/{case_id}"
    )

    assert response.status_code == 200
    return response.json()


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
    assert get_case(
        client,
        case["id"],
    )["status"] == "processing"

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

    assert get_case(
        client,
        case["id"],
    )["status"] == "awaiting_review"

    final_result = activities.finalize_case_review(
        FinalizeReviewActivityInput(
            review_run_id=review_run["id"],
            decision="approve",
            reviewer_id=str(ADMINISTRATOR_ID),
            reviewer_label="Test Administrator",
        )
    )

    assert final_result.status == "completed"

    assert get_case(
        client,
        case["id"],
    )["status"] == "completed"

    response = client.get(
        f"/v1/cases/{case['id']}/review-runs/"
        f"{review_run['id']}"
    )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["started_at"] is not None
    assert response.json()["completed_at"] is not None

    audit_response = client.get(
        f"/v1/cases/{case['id']}/audit"
    )

    case_statuses = [
        event["details"]["new_status"]
        for event in audit_response.json()
        if (
            event["event_type"] == "status_changed"
            and event["details"].get(
                "entity_type"
            )
            == "case"
            and event["details"].get(
                "review_run_id"
            )
            == review_run["id"]
        )
    ]

    human_review_event = next(
        event
        for event in audit_response.json()
        if event["event_type"]
        == "human_review_completed"
    )

    assert human_review_event["actor_type"] == "reviewer"
    assert human_review_event["actor_id"] == str(ADMINISTRATOR_ID)
    assert (
        human_review_event["actor_label"]
        == "Test Administrator"
    )

    assert case_statuses == [
        "processing",
        "awaiting_review",
        "completed",
    ]


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

    status_events = [
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

    review_run_status_events = [
        event
        for event in status_events
        if event["details"].get(
            "entity_type"
        )
        == "case_review_run"
    ]

    case_status_events = [
        event
        for event in status_events
        if event["details"].get(
            "entity_type"
        )
        == "case"
    ]

    assert len(review_run_status_events) == 1
    assert len(case_status_events) == 1

    assert (
        case_status_events[0]["details"][
            "new_status"
        ]
        == "processing"
    )


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

    final_result = (
        activities.finalize_case_review(
            FinalizeReviewActivityInput(
                review_run_id=review_run["id"],
                decision="reject",
                notes=(
                    "Synthetic rejection reason"
                ),
                reviewer_id=str(ADMINISTRATOR_ID),
                reviewer_label="Test Administrator",
            )
        )
    )

    assert final_result.status == "rejected"

    # The review decision is rejected, but the
    # parent case lifecycle has finished.
    assert get_case(
        client,
        case["id"],
    )["status"] == "completed"

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
    assert human_review_event["actor_id"] == str(ADMINISTRATOR_ID)
    assert (
        human_review_event["actor_label"]
        == "Test Administrator"
    )

    assert human_review_event["details"][
        "notes_sha256"
    ] is not None

    assert (
        "Synthetic rejection reason"
        not in str(human_review_event)
    )


def test_failed_review_marks_parent_case_failed(
    client: TestClient,
) -> None:
    case, _, review_run = create_review_run(
        client
    )

    activities = build_activities()

    activities.start_case_review(
        ReviewRunActivityInput(
            review_run_id=review_run["id"],
        )
    )

    failure_result = activities.fail_case_review(
        FailReviewActivityInput(
            review_run_id=review_run["id"],
            failure_code="SYNTHETIC_TEST_FAILURE",
        )
    )

    assert failure_result == "failed"

    assert get_case(
        client,
        case["id"],
    )["status"] == "failed"

    review_response = client.get(
        f"/v1/cases/{case['id']}/review-runs/"
        f"{review_run['id']}"
    )

    assert review_response.status_code == 200
    assert review_response.json()["status"] == "failed"
    assert (
        review_response.json()["failure_code"]
        == "SYNTHETIC_TEST_FAILURE"
    )
