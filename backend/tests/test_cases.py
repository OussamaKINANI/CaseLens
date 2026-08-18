from uuid import UUID

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_create_case() -> None:
    response = client.post(
        "/v1/cases",
        json={
            "patient_external_id": "SYNTH-001",
            "requested_service": "Lumbar spine MRI",
            "priority": "urgent",
        },
    )

    assert response.status_code == 201

    body = response.json()

    assert UUID(body["id"])
    assert body["patient_external_id"] == "SYNTH-001"
    assert body["requested_service"] == "Lumbar spine MRI"
    assert body["priority"] == "urgent"
    assert body["status"] == "received"
    assert body["created_at"]


def test_create_case_rejects_invalid_data() -> None:
    response = client.post(
        "/v1/cases",
        json={
            "patient_external_id": "",
            "requested_service": "Lumbar spine MRI",
            "priority": "extremely-urgent",
            "unexpected_field": "not permitted",
        },
    )

    assert response.status_code == 422
    assert "detail" in response.json()