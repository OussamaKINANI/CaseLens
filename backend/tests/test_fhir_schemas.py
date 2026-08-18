import pytest
from pydantic import ValidationError

from app.fhir_schemas import FHIRBundle


def test_accepts_synthetic_fhir_collection_bundle() -> None:
    bundle = FHIRBundle.model_validate(
        {
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
                    },
                },
            ],
        }
    )

    assert bundle.resource_type == "Bundle"
    assert bundle.type == "collection"
    assert len(bundle.entry) == 2


def test_rejects_non_bundle_resource() -> None:
    with pytest.raises(ValidationError):
        FHIRBundle.model_validate(
            {
                "resourceType": "Patient",
                "type": "collection",
                "entry": [],
            }
        )


def test_rejects_entry_without_resource_type() -> None:
    with pytest.raises(ValidationError):
        FHIRBundle.model_validate(
            {
                "resourceType": "Bundle",
                "type": "collection",
                "entry": [
                    {
                        "fullUrl": "urn:uuid:synthetic-resource-001",
                        "resource": {
                            "id": "synthetic-resource-001",
                        },
                    }
                ],
            }
        )