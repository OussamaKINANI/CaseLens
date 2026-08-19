from fastapi.testclient import TestClient

from app.answer_service import (
    INSUFFICIENT_EVIDENCE_ANSWER,
)


def create_case(
    client: TestClient,
    external_id: str,
) -> dict:
    response = client.post(
        "/v1/cases",
        json={
            "patient_external_id": external_id,
            "requested_service": "Clinical review",
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


def index_document(
    client: TestClient,
    case_id: str,
    document_id: str,
) -> None:
    response = client.post(
        f"/v1/cases/{case_id}/documents/"
        f"{document_id}/index"
    )

    assert response.status_code == 200


def test_answer_is_grounded_and_audited(
    client: TestClient,
) -> None:
    case = create_case(
        client,
        "SYNTH-ANSWER-001",
    )

    content = (
        "Lower back pain is present. "
        "Physical therapy was attempted."
    )

    document = upload_document(
        client,
        case["id"],
        content,
    )

    index_document(
        client,
        case["id"],
        document["id"],
    )

    response = client.post(
        f"/v1/cases/{case['id']}/answer",
        json={
            "query": "What treatment was attempted?",
            "top_k": 3,
        },
    )

    assert response.status_code == 200

    body = response.json()
    answer = body["answer"]

    assert body["retrieved_chunk_count"] == 1
    assert body["answer_provider"] == "fake"
    assert body["answer_model"] == (
        "deterministic-grounded-v1"
    )
    assert answer["supported"] is True
    assert answer["answer"] == (
        "Physical therapy was attempted."
    )
    assert len(answer["citations"]) == 1

    citation = answer["citations"][0]

    assert citation["document_id"] == document["id"]
    assert citation["exact_quote"] == (
        "Physical therapy was attempted."
    )
    assert content[
        citation["start_char"]:
        citation["end_char"]
    ] == citation["exact_quote"]

    audit_response = client.get(
        f"/v1/cases/{case['id']}/audit"
    )

    answer_events = [
        event
        for event in audit_response.json()
        if event["event_type"]
        == "rag_answer_generated"
    ]

    assert len(answer_events) == 1

    details = answer_events[0]["details"]

    assert len(details["query_sha256"]) == 64
    assert details["supported"] is True
    assert details["citation_count"] == 1
    assert details["retrieved_chunk_count"] == 1
    assert body["query"] not in str(details)


def test_answer_abstains_when_evidence_is_insufficient(
    client: TestClient,
) -> None:
    case = create_case(
        client,
        "SYNTH-ANSWER-002",
    )

    document = upload_document(
        client,
        case["id"],
        "Lower back pain is present.",
    )

    index_document(
        client,
        case["id"],
        document["id"],
    )

    response = client.post(
        f"/v1/cases/{case['id']}/answer",
        json={
            "query": (
                "What kidney medication was prescribed?"
            ),
            "top_k": 3,
        },
    )

    assert response.status_code == 200

    answer = response.json()["answer"]

    assert answer["supported"] is False
    assert answer["answer"] == (
        INSUFFICIENT_EVIDENCE_ANSWER
    )
    assert answer["citations"] == []


def test_answer_cannot_retrieve_another_case(
    client: TestClient,
) -> None:
    first_case = create_case(
        client,
        "SYNTH-ANSWER-003",
    )

    second_case = create_case(
        client,
        "SYNTH-ANSWER-004",
    )

    document = upload_document(
        client,
        first_case["id"],
        "A private penicillin allergy is documented.",
    )

    index_document(
        client,
        first_case["id"],
        document["id"],
    )

    response = client.post(
        f"/v1/cases/{second_case['id']}/answer",
        json={
            "query": "Is there a penicillin allergy?",
            "top_k": 3,
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["retrieved_chunk_count"] == 0
    assert body["answer"]["supported"] is False
    assert body["answer"]["citations"] == []


def test_answer_request_is_strictly_validated(
    client: TestClient,
) -> None:
    case = create_case(
        client,
        "SYNTH-ANSWER-005",
    )

    invalid_top_k = client.post(
        f"/v1/cases/{case['id']}/answer",
        json={
            "query": "What happened?",
            "top_k": 0,
        },
    )

    unknown_field = client.post(
        f"/v1/cases/{case['id']}/answer",
        json={
            "query": "What happened?",
            "unexpected": "not allowed",
        },
    )

    assert invalid_top_k.status_code == 422
    assert unknown_field.status_code == 422