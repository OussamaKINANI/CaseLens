from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.extraction_schemas import ClinicalExtraction


def test_clinical_extraction_accepts_supported_fact() -> None:
    document_id = uuid4()

    extraction = ClinicalExtraction.model_validate(
        {
            "schema_version": "1.0",
            "facts": [
                {
                    "fact_type": "symptom",
                    "name": "lower back pain",
                    "value": "persistent for six weeks",
                    "assertion": "present",
                    "evidence": [
                        {
                            "document_id": str(document_id),
                            "exact_quote": (
                                "Persistent lower back pain "
                                "for six weeks."
                            ),
                            "start_char": 0,
                            "end_char": 41,
                        }
                    ],
                }
            ],
            "missing_information": [],
            "warnings": [],
        }
    )

    assert len(extraction.facts) == 1
    assert extraction.facts[0].name == "lower back pain"
    assert extraction.facts[0].evidence[0].document_id == document_id


def test_clinical_fact_requires_evidence() -> None:
    with pytest.raises(ValidationError):
        ClinicalExtraction.model_validate(
            {
                "facts": [
                    {
                        "fact_type": "condition",
                        "name": "diabetes",
                        "assertion": "present",
                        "evidence": [],
                    }
                ]
            }
        )


def test_evidence_rejects_invalid_character_range() -> None:
    with pytest.raises(ValidationError):
        ClinicalExtraction.model_validate(
            {
                "facts": [
                    {
                        "fact_type": "symptom",
                        "name": "headache",
                        "assertion": "present",
                        "evidence": [
                            {
                                "document_id": str(uuid4()),
                                "exact_quote": "headache",
                                "start_char": 20,
                                "end_char": 10,
                            }
                        ],
                    }
                ]
            }
        )


def test_clinical_extraction_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ClinicalExtraction.model_validate(
            {
                "facts": [],
                "unexpected_field": "not permitted",
            }
        )