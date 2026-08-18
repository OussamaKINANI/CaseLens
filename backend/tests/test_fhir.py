from fastapi.testclient import TestClient


SYNTHETIC_FHIR_BUNDLE = {
    "resourceType": "Bundle",
    "id": "synthetic-bundle-001",
    "type": "collection",
    "entry": [
        {
            "fullUrl": "urn:uuid:synthetic-patient-001",
            "resource": {
                "resourceType": "Patient",
                "id": "synthetic-patient-001",
            },
        },
        {
            "fullUrl": "urn:uuid:synthetic-condition-001",
            "resource": {
                "resourceType": "Condition",
                "id": "synthetic-condition-001",
                "code": {
                    "text": "Synthetic lower-back pain",
                },
            },
        },
    ],
}


def create_case(client: TestClient) -> dict:
    response = client.post(
        "/v1/cases",
        json={
            "patient_external_id": "SYNTH-FHIR-001",
            "requested_service": "Lumbar spine MRI",
        },
    )

    assert response.status_code == 201
    return response.json()


def test_import_fhir_bundle(
    client: TestClient,
) -> None:
    case = create_case(client)

    response = client.post(
        f"/v1/cases/{case['id']}/fhir-bundles",
        json=SYNTHETIC_FHIR_BUNDLE,
    )

    assert response.status_code == 201

    body = response.json()

    assert body["bundle_type"] == "collection"
    assert body["resource_counts"] == {
        "Condition": 1,
        "Patient": 1,
    }
    assert body["document"]["media_type"] == (
        "application/fhir+json"
    )
    assert "content" not in body["document"]

    events = client.get(
        f"/v1/cases/{case['id']}/audit"
    ).json()

    assert events[-1]["event_type"] == "document_uploaded"
    assert events[-1]["details"]["document_kind"] == "fhir_bundle"


def test_rejects_duplicate_fhir_bundle(
    client: TestClient,
) -> None:
    case = create_case(client)
    endpoint = f"/v1/cases/{case['id']}/fhir-bundles"

    first_response = client.post(
        endpoint,
        json=SYNTHETIC_FHIR_BUNDLE,
    )
    second_response = client.post(
        endpoint,
        json=SYNTHETIC_FHIR_BUNDLE,
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 409