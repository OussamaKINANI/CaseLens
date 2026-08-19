from uuid import uuid4

from fastapi.testclient import TestClient


def create_case_and_document(
    client: TestClient,
) -> tuple[dict, dict]:
    case = client.post(
        "/v1/cases",
        json={
            "patient_external_id": f"SYNTH-AI-{uuid4()}",
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


def test_create_clinical_extraction(
    client: TestClient,
) -> None:
    case, document = create_case_and_document(client)

    response = client.post(
        f"/v1/cases/{case['id']}"
        f"/documents/{document['id']}/extractions"
    )

    assert response.status_code == 201

    body = response.json()

    assert body["case_id"] == case["id"]
    assert body["document_id"] == document["id"]
    assert body["provider_name"] == "fake"
    assert body["model_name"] == "deterministic-rules-v1"
    assert body["source_sha256"] == document["content_sha256"]

    fact_names = [
        fact["name"]
        for fact in body["result"]["facts"]
    ]

    assert fact_names == [
        "lower back pain",
        "physical therapy",
    ]

    audit_response = client.get(
        f"/v1/cases/{case['id']}/audit"
    )

    event_types = [
        event["event_type"]
        for event in audit_response.json()
    ]

    assert "ai_review_started" in event_types
    assert "ai_review_completed" in event_types


def test_list_clinical_extractions(
    client: TestClient,
) -> None:
    case, document = create_case_and_document(client)

    client.post(
        f"/v1/cases/{case['id']}"
        f"/documents/{document['id']}/extractions"
    )

    response = client.get(
        f"/v1/cases/{case['id']}/extractions"
    )

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["document_id"] == document["id"]


def test_duplicate_extraction_is_rejected(
    client: TestClient,
) -> None:
    case, document = create_case_and_document(client)

    endpoint = (
        f"/v1/cases/{case['id']}"
        f"/documents/{document['id']}/extractions"
    )

    first_response = client.post(endpoint)
    second_response = client.post(endpoint)

    assert first_response.status_code == 201
    assert second_response.status_code == 409