from uuid import UUID, uuid4
from fastapi.testclient import TestClient




def test_create_case(client: TestClient) -> None:
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


def test_create_case_rejects_invalid_data(client: TestClient) -> None:
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


def test_get_case_by_id(client: TestClient) -> None:
    created_response = client.post(
        "/v1/cases",
        json={
            "patient_external_id": "SYNTH-002",
            "requested_service": "Knee MRI",
            "priority": "routine",
        },
    )

    case_id = created_response.json()["id"]

    response = client.get(f"/v1/cases/{case_id}")

    assert response.status_code == 200
    assert response.json()["id"] == case_id
    assert response.json()["requested_service"] == "Knee MRI"


def test_get_missing_case_returns_404(client: TestClient) -> None:
    missing_case_id = uuid4()

    response = client.get(f"/v1/cases/{missing_case_id}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Case not found"}


def test_list_cases(client: TestClient) -> None:
    for external_id in ["SYNTH-001", "SYNTH-002"]:
        response = client.post(
            "/v1/cases",
            json={
                "patient_external_id": external_id,
                "requested_service": "Lumbar spine MRI",
                "priority": "routine",
            },
        )

        assert response.status_code == 201

    response = client.get("/v1/cases")

    assert response.status_code == 200
    assert len(response.json()) == 2

def test_create_case_records_audit_event(
    client: TestClient,
) -> None:
    created_response = client.post(
        "/v1/cases",
        json={
            "patient_external_id": "SYNTH-AUDIT-001",
            "requested_service": "Cardiac MRI",
            "priority": "urgent",
        },
    )

    assert created_response.status_code == 201

    case_id = created_response.json()["id"]
    audit_response = client.get(f"/v1/cases/{case_id}/audit")

    assert audit_response.status_code == 200

    events = audit_response.json()

    assert len(events) == 1
    assert events[0]["case_id"] == case_id
    assert events[0]["event_type"] == "case_created"
    assert events[0]["actor_type"] == "system"
    assert events[0]["details"] == {
        "initial_status": "received",
        "priority": "urgent",
    }

def test_update_case_status_records_audit_event(
    client: TestClient,
) -> None:
    created = client.post(
        "/v1/cases",
        json={
            "patient_external_id": "SYNTH-STATUS-001",
            "requested_service": "Cardiac MRI",
            "priority": "routine",
        },
    ).json()

    response = client.patch(
        f"/v1/cases/{created['id']}/status",
        json={
            "status": "processing",
            "reason": "AI review started",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "processing"

    events = client.get(
        f"/v1/cases/{created['id']}/audit"
    ).json()

    assert len(events) == 2
    assert events[1]["event_type"] == "status_changed"
    assert events[1]["details"] == {
        "previous_status": "received",
        "new_status": "processing",
        "reason": "AI review started",
    }


def test_invalid_status_transition_returns_conflict(
    client: TestClient,
) -> None:
    created = client.post(
        "/v1/cases",
        json={
            "patient_external_id": "SYNTH-STATUS-002",
            "requested_service": "Cardiac MRI",
            "priority": "routine",
        },
    ).json()

    response = client.patch(
        f"/v1/cases/{created['id']}/status",
        json={
            "status": "completed",
            "reason": "Attempted invalid transition",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Cannot transition case from received to completed"
    )

def test_upload_clinical_document(
    client: TestClient,
) -> None:
    created = client.post(
        "/v1/cases",
        json={
            "patient_external_id": "SYNTH-DOC-001",
            "requested_service": "Cardiac MRI",
            "priority": "routine",
        },
    ).json()

    note = (
        b"Synthetic clinical note. "
        b"Patient completed six weeks of physical therapy."
    )

    response = client.post(
        f"/v1/cases/{created['id']}/documents",
        files={
            "file": (
                "clinical-note.txt",
                note,
                "text/plain",
            ),
        },
    )

    assert response.status_code == 201

    body = response.json()

    assert body["case_id"] == created["id"]
    assert body["filename"] == "clinical-note.txt"
    assert body["media_type"] == "text/plain"
    assert body["size_bytes"] == len(note)
    assert len(body["content_sha256"]) == 64
    assert "content" not in body

    events = client.get(
        f"/v1/cases/{created['id']}/audit"
    ).json()

    assert events[-1]["event_type"] == "document_uploaded"


def test_rejects_unsupported_document_type(
    client: TestClient,
) -> None:
    created = client.post(
        "/v1/cases",
        json={
            "patient_external_id": "SYNTH-DOC-002",
            "requested_service": "Cardiac MRI",
        },
    ).json()

    response = client.post(
        f"/v1/cases/{created['id']}/documents",
        files={
            "file": (
                "record.pdf",
                b"not a real PDF",
                "application/pdf",
            ),
        },
    )

    assert response.status_code == 415


def test_rejects_duplicate_document(
    client: TestClient,
) -> None:
    created = client.post(
        "/v1/cases",
        json={
            "patient_external_id": "SYNTH-DOC-003",
            "requested_service": "Cardiac MRI",
        },
    ).json()

    upload = {
        "file": (
            "note.txt",
            b"Synthetic clinical record",
            "text/plain",
        ),
    }

    first_response = client.post(
        f"/v1/cases/{created['id']}/documents",
        files=upload,
    )

    second_response = client.post(
        f"/v1/cases/{created['id']}/documents",
        files=upload,
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 409