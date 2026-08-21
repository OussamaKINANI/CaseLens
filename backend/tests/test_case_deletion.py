from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from app.audit_models import AuditEventRecord
from app.document_models import ClinicalDocumentRecord
from app.extraction_models import ClinicalExtractionRecord
from app.rag_models import DocumentChunkRecord
from app.review_models import CaseReviewRunRecord
from tests.conftest import TestSessionLocal


def create_case_and_document(
    client: TestClient,
) -> tuple[dict, dict]:
    case = client.post(
        "/v1/cases",
        json={
            "patient_external_id": f"SYNTH-DELETE-{uuid4()}",
            "requested_service": "Lumbar spine MRI",
            "priority": "routine",
        },
    ).json()

    document = client.post(
        f"/v1/cases/{case['id']}/documents",
        files={
            "file": (
                "clinical-note.txt",
                (
                    b"Persistent lower back pain for six weeks. "
                    b"Physical therapy did not improve symptoms."
                ),
                "text/plain",
            )
        },
    ).json()

    return case, document


def count_case_rows(
    case_id: str,
    document_id: str,
) -> dict[str, int]:
    case_uuid = UUID(case_id)
    document_uuid = UUID(document_id)

    with TestSessionLocal() as session:
        return {
            "documents": session.scalar(
                select(func.count()).where(
                    ClinicalDocumentRecord.case_id == case_uuid,
                )
            )
            or 0,
            "chunks": session.scalar(
                select(func.count()).where(
                    DocumentChunkRecord.document_id == document_uuid,
                )
            )
            or 0,
            "extractions": session.scalar(
                select(func.count()).where(
                    ClinicalExtractionRecord.case_id == case_uuid,
                )
            )
            or 0,
            "audit_events": session.scalar(
                select(func.count()).where(
                    AuditEventRecord.case_id == case_uuid,
                )
            )
            or 0,
            "review_runs": session.scalar(
                select(func.count()).where(
                    CaseReviewRunRecord.case_id == case_uuid,
                )
            )
            or 0,
        }


def test_delete_case_removes_case_and_children(
    client: TestClient,
) -> None:
    case, document = create_case_and_document(client)

    index_response = client.post(
        f"/v1/cases/{case['id']}"
        f"/documents/{document['id']}/index"
    )
    assert index_response.status_code in (200, 201)

    extraction_response = client.post(
        f"/v1/cases/{case['id']}"
        f"/documents/{document['id']}/extractions"
    )
    assert extraction_response.status_code == 201

    run_response = client.post(
        f"/v1/cases/{case['id']}/review-runs",
        json={"document_ids": [document["id"]]},
    )
    assert run_response.status_code == 201

    # Close the run directly so deletion is permitted.
    with TestSessionLocal() as session:
        session.execute(
            update(CaseReviewRunRecord)
            .where(
                CaseReviewRunRecord.case_id == UUID(case["id"]),
            )
            .values(status="completed")
        )
        session.commit()

    before = count_case_rows(case["id"], document["id"])

    assert before["documents"] == 1
    assert before["chunks"] >= 1
    assert before["extractions"] == 1
    assert before["audit_events"] >= 1
    assert before["review_runs"] == 1

    delete_response = client.delete(f"/v1/cases/{case['id']}")

    assert delete_response.status_code == 204

    assert client.get(f"/v1/cases/{case['id']}").status_code == 404

    after = count_case_rows(case["id"], document["id"])

    assert after == {
        "documents": 0,
        "chunks": 0,
        "extractions": 0,
        "audit_events": 0,
        "review_runs": 0,
    }


def test_delete_missing_case_returns_404(
    client: TestClient,
) -> None:
    response = client.delete(f"/v1/cases/{uuid4()}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Case not found"}


def test_delete_case_with_active_review_run_returns_409(
    client: TestClient,
) -> None:
    case, document = create_case_and_document(client)

    run_response = client.post(
        f"/v1/cases/{case['id']}/review-runs",
        json={"document_ids": [document["id"]]},
    )
    assert run_response.status_code == 201
    assert run_response.json()["status"] == "queued"

    delete_response = client.delete(f"/v1/cases/{case['id']}")

    assert delete_response.status_code == 409
    assert "review" in delete_response.json()["detail"].lower()

    # The case and its records must remain untouched.
    assert client.get(f"/v1/cases/{case['id']}").status_code == 200

    remaining = count_case_rows(case["id"], document["id"])

    assert remaining["documents"] == 1
    assert remaining["review_runs"] == 1
