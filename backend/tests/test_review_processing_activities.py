from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from temporalio.exceptions import ApplicationError

from app.embedding_service import (
    FakeEmbeddingProvider,
)
from app.extraction_service import (
    FakeExtractionProvider,
)
from app.review_activities import CaseReviewActivities
from app.review_processing_activities import (
    ReviewProcessingActivities,
)
from app.temporal_models import (
    CaseReviewWorkflowInput,
    ReviewDocumentActivityInput,
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
                f"SYNTH-PROCESSING-{uuid4()}"
            ),
            "requested_service": "Lumbar spine MRI",
            "priority": "routine",
        },
    ).json()

    content = (
        "Lower back pain is present. "
        "Physical therapy was attempted."
    )

    document = client.post(
        f"/v1/cases/{case['id']}/documents",
        files={
            "file": (
                "processing-note.txt",
                content.encode("utf-8"),
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


def build_processing_activities(
) -> ReviewProcessingActivities:
    return ReviewProcessingActivities(
        session_factory=TestSessionLocal,
        embedding_provider_factory=(
            lambda: FakeEmbeddingProvider(
                dimensions=1536
            )
        ),
        extraction_provider_factory=(
            lambda: FakeExtractionProvider()
        ),
    )


def test_processing_activities_persist_and_reuse_results(
    client: TestClient,
) -> None:
    case, document, review_run = (
        create_review_run(client)
    )

    control_activities = CaseReviewActivities(
        session_factory=TestSessionLocal
    )

    processing_activities = (
        build_processing_activities()
    )

    control_activities.start_case_review(
        ReviewRunActivityInput(
            review_run_id=review_run["id"]
        )
    )

    control_activities.validate_case_review_documents(
        CaseReviewWorkflowInput(
            review_run_id=review_run["id"],
            case_id=case["id"],
            document_ids=[document["id"]],
        )
    )

    processing_input = (
        ReviewDocumentActivityInput(
            review_run_id=review_run["id"],
            document_id=document["id"],
        )
    )

    first_index = (
        processing_activities
        .index_case_review_document(
            processing_input
        )
    )

    second_index = (
        processing_activities
        .index_case_review_document(
            processing_input
        )
    )

    assert first_index.chunk_count >= 1
    assert first_index.reused_existing is False
    assert second_index.reused_existing is True

    first_extraction = (
        processing_activities
        .extract_case_review_document(
            processing_input
        )
    )

    second_extraction = (
        processing_activities
        .extract_case_review_document(
            processing_input
        )
    )

    assert first_extraction.fact_count == 2
    assert (
        first_extraction.reused_existing
        is False
    )
    assert (
        second_extraction.reused_existing
        is True
    )
    assert (
        first_extraction.extraction_id
        == second_extraction.extraction_id
    )

    extraction_response = client.get(
        f"/v1/cases/{case['id']}/extractions"
    )

    assert extraction_response.status_code == 200
    assert len(extraction_response.json()) == 1


def test_processing_rejects_document_outside_run(
    client: TestClient,
) -> None:
    _, _, first_run = create_review_run(client)
    _, second_document, _ = create_review_run(
        client
    )

    activities = build_processing_activities()

    with pytest.raises(
        ApplicationError,
        match="outside the review run",
    ):
        activities.index_case_review_document(
            ReviewDocumentActivityInput(
                review_run_id=first_run["id"],
                document_id=(
                    second_document["id"]
                ),
            )
        )