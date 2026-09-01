from collections.abc import Generator
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import app
from app.review_activities import CaseReviewActivities
from app.review_workflow_gateway import (
    FakeReviewWorkflowGateway,
    get_review_workflow_gateway,
)
from app.temporal_models import ReviewRunActivityInput
from tests.conftest import (
    REVIEWER_ID,
    TestSessionLocal,
)


@pytest.fixture
def workflow_gateway(
    client: TestClient,
) -> Generator[
    FakeReviewWorkflowGateway,
    None,
    None,
]:
    gateway = FakeReviewWorkflowGateway()

    app.dependency_overrides[
        get_review_workflow_gateway
    ] = lambda: gateway

    try:
        yield gateway
    finally:
        app.dependency_overrides.pop(
            get_review_workflow_gateway,
            None,
        )


def create_review_run(
    client: TestClient,
) -> tuple[dict, dict, dict]:
    case = client.post(
        "/v1/cases",
        json={
            "patient_external_id": (
                f"SYNTH-WORKFLOW-{uuid4()}"
            ),
            "requested_service": "Lumbar spine MRI",
            "priority": "routine",
        },
    ).json()

    document = client.post(
        f"/v1/cases/{case['id']}/documents",
        files={
            "file": (
                "workflow-note.txt",
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


def test_start_review_sends_workflow(
    client: TestClient,
    workflow_gateway: FakeReviewWorkflowGateway,
) -> None:
    case, document, review_run = create_review_run(
        client
    )

    response = client.post(
        f"/v1/cases/{case['id']}/review-runs/"
        f"{review_run['id']}/start"
    )

    assert response.status_code == 202
    assert response.json()["command_status"] == "started"
    assert len(
        workflow_gateway.started_workflows
    ) == 1

    workflow_id, workflow_input = (
        workflow_gateway.started_workflows[0]
    )

    assert workflow_id == (
        review_run["temporal_workflow_id"]
    )
    assert workflow_input.case_id == case["id"]
    assert workflow_input.document_ids == [
        document["id"]
    ]


def test_human_review_sends_validated_update(
    reviewer_client: TestClient,
    workflow_gateway: FakeReviewWorkflowGateway,
) -> None:
    case, _, review_run = create_review_run(
        reviewer_client
    )

    activities = CaseReviewActivities(
        session_factory=TestSessionLocal
    )

    activity_input = ReviewRunActivityInput(
        review_run_id=review_run["id"]
    )

    activities.start_case_review(
        activity_input
    )

    activities.mark_case_review_awaiting_human(
        activity_input
    )

    response = reviewer_client.post(
        f"/v1/cases/{case['id']}/review-runs/"
        f"{review_run['id']}/human-review",
        json={
            "decision": "approve",
        },
    )

    assert response.status_code == 202
    assert response.json()["command_status"] == "accepted"
    assert len(workflow_gateway.human_reviews) == 1

    _, review = workflow_gateway.human_reviews[0]

    assert review.decision == "approve"
    assert review.reviewer_id == str(REVIEWER_ID)
    assert review.reviewer_label == "Test Reviewer"


def test_human_review_requires_awaiting_status(
    client: TestClient,
    workflow_gateway: FakeReviewWorkflowGateway,
) -> None:
    case, _, review_run = create_review_run(
        client
    )

    response = client.post(
        f"/v1/cases/{case['id']}/review-runs/"
        f"{review_run['id']}/human-review",
        json={
            "decision": "approve",
        },
    )

    assert response.status_code == 409
    assert workflow_gateway.human_reviews == []
