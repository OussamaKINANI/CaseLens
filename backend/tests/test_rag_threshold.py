from fastapi.testclient import TestClient

from app.config import get_rag_min_similarity
from app.main import app


def test_search_filters_results_below_threshold(
    client: TestClient,
) -> None:
    case_response = client.post(
        "/v1/cases",
        json={
            "patient_external_id": (
                "SYNTH-RAG-THRESHOLD-001"
            ),
            "requested_service": "Clinical review",
            "priority": "routine",
        },
    )

    assert case_response.status_code == 201
    case = case_response.json()

    document_response = client.post(
        f"/v1/cases/{case['id']}/documents",
        files={
            "file": (
                "synthetic-note.txt",
                b"Lower back pain is present.",
                "text/plain",
            )
        },
    )

    assert document_response.status_code == 201
    document = document_response.json()

    index_response = client.post(
        f"/v1/cases/{case['id']}/documents/"
        f"{document['id']}/index"
    )

    assert index_response.status_code == 200

    app.dependency_overrides[
        get_rag_min_similarity
    ] = lambda: 1.0

    search_response = client.post(
        f"/v1/cases/{case['id']}/search",
        json={
            "query": "kidney medication",
            "top_k": 3,
        },
    )

    assert search_response.status_code == 200

    body = search_response.json()

    assert body["min_similarity"] == 1.0
    assert body["result_count"] == 0
    assert body["results"] == []