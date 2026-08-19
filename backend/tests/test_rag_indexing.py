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
    content: str,
) -> dict:
    response = client.post(
        f"/v1/cases/{case_id}/documents",
        files={
            "file": (
                "synthetic-note.txt",
                content.encode("utf-8"),
                "text/plain",
            )
        },
    )

    assert response.status_code == 201
    return response.json()


def test_index_document_persists_traceable_chunks(
    client: TestClient,
) -> None:
    case = create_case(
        client,
        "SYNTH-RAG-001",
    )

    content = (
        "Lower back pain is present. "
        "Physical therapy was attempted but "
        "symptoms did not improve. "
    ) * 30

    document = upload_document(
        client,
        case["id"],
        content,
    )

    response = client.post(
        f"/v1/cases/{case['id']}/documents/"
        f"{document['id']}/index"
    )

    assert response.status_code == 200

    body = response.json()

    assert body["document_id"] == document["id"]
    assert body["chunk_count"] >= 2
    assert body["reused_existing"] is False
    assert body["embedding_model"] == (
        "fake/deterministic-hash-v1/1536"
    )

    for chunk in body["chunks"]:
        assert chunk["content"] == content[
            chunk["start_char"]:
            chunk["end_char"]
        ]
        assert len(chunk["content_sha256"]) == 64
        assert "embedding" not in chunk

    audit_response = client.get(
        f"/v1/cases/{case['id']}/audit"
    )

    assert audit_response.status_code == 200

    document_indexed_events = [
        event
        for event in audit_response.json()
        if event["event_type"] == "document_indexed"
    ]

    assert len(document_indexed_events) == 1
    assert (
        document_indexed_events[0]["details"][
            "document_id"
        ]
        == document["id"]
    )


def test_repeated_indexing_reuses_existing_chunks(
    client: TestClient,
) -> None:
    case = create_case(
        client,
        "SYNTH-RAG-002",
    )

    document = upload_document(
        client,
        case["id"],
        "Synthetic clinical evidence.",
    )

    url = (
        f"/v1/cases/{case['id']}/documents/"
        f"{document['id']}/index"
    )

    first = client.post(url)
    second = client.post(url)

    assert first.status_code == 200
    assert second.status_code == 200

    assert first.json()["reused_existing"] is False
    assert second.json()["reused_existing"] is True

    first_ids = [
        chunk["id"]
        for chunk in first.json()["chunks"]
    ]
    second_ids = [
        chunk["id"]
        for chunk in second.json()["chunks"]
    ]

    assert first_ids == second_ids
    audit_response = client.get(
        f"/v1/cases/{case['id']}/audit"
    )

    document_indexed_events = [
        event
        for event in audit_response.json()
        if event["event_type"] == "document_indexed"
    ]

    assert len(document_indexed_events) == 1

def test_document_cannot_be_indexed_through_wrong_case(
    client: TestClient,
) -> None:
    first_case = create_case(
        client,
        "SYNTH-RAG-003",
    )
    second_case = create_case(
        client,
        "SYNTH-RAG-004",
    )

    document = upload_document(
        client,
        first_case["id"],
        "Synthetic clinical evidence.",
    )

    response = client.post(
        f"/v1/cases/{second_case['id']}/documents/"
        f"{document['id']}/index"
    )

    assert response.status_code == 404


def test_whitespace_document_cannot_be_indexed(
    client: TestClient,
) -> None:
    case = create_case(
        client,
        "SYNTH-RAG-005",
    )

    document = upload_document(
        client,
        case["id"],
        "     ",
    )

    response = client.post(
        f"/v1/cases/{case['id']}/documents/"
        f"{document['id']}/index"
    )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "Document contains no searchable text"
    )