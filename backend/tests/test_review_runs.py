from fastapi.testclient import TestClient


def create_case(
    client: TestClient,
    external_id: str,
) -> dict:
    response = client.post(
        "/v1/cases",
        json={
            "patient_external_id": external_id,
            "requested_service": "Lumbar spine MRI",
            "priority": "routine",
        },
    )

    assert response.status_code == 201
    return response.json()


def upload_document(
    client: TestClient,
    case_id: str,
    filename: str,
) -> dict:
    response = client.post(
        f"/v1/cases/{case_id}/documents",
        files={
            "file": (
                filename,
                b"Synthetic clinical evidence.",
                "text/plain",
            )
        },
    )

    assert response.status_code == 201
    return response.json()


def test_create_review_run(
    client: TestClient,
) -> None:
    case = create_case(
        client,
        "SYNTH-REVIEW-001",
    )

    document = upload_document(
        client,
        case["id"],
        "review-note.txt",
    )

    response = client.post(
        f"/v1/cases/{case['id']}/review-runs",
        json={
            "document_ids": [document["id"]],
        },
    )

    assert response.status_code == 201

    body = response.json()

    assert body["case_id"] == case["id"]
    assert body["document_ids"] == [document["id"]]
    assert body["status"] == "queued"
    assert body["temporal_workflow_id"] == (
        f"case-review-{body['id']}"
    )
    assert body["failure_code"] is None
    assert body["started_at"] is None
    assert body["completed_at"] is None


def test_review_run_rejects_document_from_another_case(
    client: TestClient,
) -> None:
    first_case = create_case(
        client,
        "SYNTH-REVIEW-002",
    )

    second_case = create_case(
        client,
        "SYNTH-REVIEW-003",
    )

    document = upload_document(
        client,
        first_case["id"],
        "wrong-case-note.txt",
    )

    response = client.post(
        f"/v1/cases/{second_case['id']}/review-runs",
        json={
            "document_ids": [document["id"]],
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == (
        "One or more documents were not found for this case"
    )


def test_list_and_get_review_runs(
    client: TestClient,
) -> None:
    case = create_case(
        client,
        "SYNTH-REVIEW-004",
    )

    document = upload_document(
        client,
        case["id"],
        "list-note.txt",
    )

    created = client.post(
        f"/v1/cases/{case['id']}/review-runs",
        json={
            "document_ids": [document["id"]],
        },
    ).json()

    list_response = client.get(
        f"/v1/cases/{case['id']}/review-runs"
    )

    assert list_response.status_code == 200
    assert len(list_response.json()) == 1
    assert list_response.json()[0]["id"] == created ["id"]

    get_response = client.get(
        f"/v1/cases/{case['id']}/review-runs/"
        f"{created['id']}"
    )

    assert get_response.status_code == 200
    assert get_response.json()["id"] == created["id"]


def test_review_run_cannot_be_read_through_wrong_case(
    client: TestClient,
) -> None:
    first_case = create_case(
        client,
        "SYNTH-REVIEW-005",
    )

    second_case = create_case(
        client,
        "SYNTH-REVIEW-006",
    )

    document = upload_document(
        client,
        first_case["id"],
        "scoped-note.txt",
    )

    review_run = client.post(
        f"/v1/cases/{first_case['id']}/review-runs",
        json={
            "document_ids": [document["id"]],
        },
    ).json()

    response = client.get(
        f"/v1/cases/{second_case['id']}/review-runs/"
        f"{review_run['id']}"
    )

    assert response.status_code == 404