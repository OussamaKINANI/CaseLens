from uuid import uuid4

from fastapi.testclient import TestClient


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


def test_search_ranks_relevant_chunk_first(
    client: TestClient,
) -> None:
    case = create_case(
        client,
        "SYNTH-SEARCH-001",
    )

    allergy_document = upload_document(
        client,
        case["id"],
        "A penicillin allergy is documented.",
    )

    pain_document = upload_document(
        client,
        case["id"],
        "The patient reports chronic lower back pain.",
    )

    index_document(
        client,
        case["id"],
        allergy_document["id"],
    )

    index_document(
        client,
        case["id"],
        pain_document["id"],
    )

    response = client.post(
        f"/v1/cases/{case['id']}/search",
        json={
            "query": "penicillin allergy",
            "top_k": 2,
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["result_count"] == 2
    assert body["embedding_model"] == (
        "fake/deterministic-hash-v1/1536"
    )
    assert (
        body["results"][0]["document_id"]
        == allergy_document["id"]
    )
    assert (
        body["results"][0]["similarity"]
        >= body["results"][1]["similarity"]
    )
    assert "embedding" not in body["results"][0]


def test_search_cannot_leak_chunks_between_cases(
    client: TestClient,
) -> None:
    first_case = create_case(
        client,
        "SYNTH-SEARCH-002",
    )

    second_case = create_case(
        client,
        "SYNTH-SEARCH-003",
    )

    private_document = upload_document(
        client,
        first_case["id"],
        "Cross-case private marker evidence.",
    )

    index_document(
        client,
        first_case["id"],
        private_document["id"],
    )

    response = client.post(
        f"/v1/cases/{second_case['id']}/search",
        json={
            "query": "Cross-case private marker",
            "top_k": 5,
        },
    )

    assert response.status_code == 200
    assert response.json()["result_count"] == 0
    assert response.json()["results"] == []


def test_search_request_is_strictly_validated(
    client: TestClient,
) -> None:
    case = create_case(
        client,
        "SYNTH-SEARCH-004",
    )

    blank_query = client.post(
        f"/v1/cases/{case['id']}/search",
        json={
            "query": "   ",
        },
    )

    invalid_top_k = client.post(
        f"/v1/cases/{case['id']}/search",
        json={
            "query": "pain",
            "top_k": 21,
        },
    )

    unknown_field = client.post(
        f"/v1/cases/{case['id']}/search",
        json={
            "query": "pain",
            "unexpected": "not allowed",
        },
    )

    assert blank_query.status_code == 422
    assert invalid_top_k.status_code == 422
    assert unknown_field.status_code == 422


def test_search_rejects_unknown_case(
    client: TestClient,
) -> None:
    response = client.post(
        f"/v1/cases/{uuid4()}/search",
        json={
            "query": "lower back pain",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Case not found"

def test_utf8_bom_is_not_indexed_as_clinical_content(
    client: TestClient,
) -> None:
    case = create_case(
        client,
        "SYNTH-SEARCH-005",
    )

    upload_response = client.post(
        f"/v1/cases/{case['id']}/documents",
        files={
            "file": (
                "bom-note.txt",
                (
                    b"\xef\xbb\xbf"
                    b"Synthetic fever evidence."
                ),
                "text/plain",
            )
        },
    )

    assert upload_response.status_code == 201

    document = upload_response.json()

    index_document(
        client,
        case["id"],
        document["id"],
    )

    search_response = client.post(
        f"/v1/cases/{case['id']}/search",
        json={
            "query": "fever evidence",
            "top_k": 1,
        },
    )

    assert search_response.status_code == 200

    result = search_response.json()["results"][0]

    assert result["content"] == (
        "Synthetic fever evidence."
    )
    assert not result["content"].startswith("\ufeff")
    assert not result["content"].startswith("ï»¿")