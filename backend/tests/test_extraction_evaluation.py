from uuid import uuid4

import pytest

from app.extraction_evaluation import (
    ExpectedClinicalFact,
    evaluate_extraction,
)
from app.extraction_schemas import ClinicalExtraction


def test_perfect_extraction_scores_one() -> None:
    document_id = uuid4()
    content = (
        "Lower back pain is present. "
        "Physical therapy was attempted."
    )

    extraction = ClinicalExtraction.model_validate(
        {
            "facts": [
                {
                    "fact_type": "symptom",
                    "name": "Lower back pain",
                    "assertion": "present",
                    "evidence": [
                        {
                            "document_id": str(document_id),
                            "exact_quote": (
                                "Lower back pain is present."
                            ),
                            "start_char": 0,
                            "end_char": 27,
                        }
                    ],
                },
                {
                    "fact_type": "procedure",
                    "name": "Physical therapy",
                    "assertion": "historical",
                    "evidence": [
                        {
                            "document_id": str(document_id),
                            "exact_quote": (
                                "Physical therapy was attempted."
                            ),
                            "start_char": 28,
                            "end_char": 59,
                        }
                    ],
                },
            ]
        }
    )

    expected = [
        ExpectedClinicalFact(
            fact_type="symptom",
            name="lower back pain",
            assertion="present",
        ),
        ExpectedClinicalFact(
            fact_type="procedure",
            name="physical therapy",
            assertion="historical",
        ),
    ]

    result = evaluate_extraction(
        extraction=extraction,
        expected_facts=expected,
        documents={document_id: content},
    )

    assert result.precision == 1.0
    assert result.recall == 1.0
    assert result.f1 == 1.0
    assert result.classification_accuracy == 1.0
    assert result.unsupported_fact_rate == 0.0
    assert result.citation_validity == 1.0


def test_misclassified_and_unsupported_facts_reduce_score() -> None:
    document_id = uuid4()
    content = (
        "Lower back pain is present. "
        "Physical therapy was attempted."
    )

    extraction = ClinicalExtraction.model_validate(
        {
            "facts": [
                {
                    "fact_type": "condition",
                    "name": "Lower back pain",
                    "assertion": "present",
                    "evidence": [
                        {
                            "document_id": str(document_id),
                            "exact_quote": (
                                "Lower back pain is present."
                            ),
                            "start_char": 0,
                            "end_char": 27,
                        }
                    ],
                },
                {
                    "fact_type": "procedure",
                    "name": "Physical therapy",
                    "assertion": "historical",
                    "evidence": [
                        {
                            "document_id": str(document_id),
                            "exact_quote": (
                                "Physical therapy was attempted."
                            ),
                            "start_char": 28,
                            "end_char": 59,
                        }
                    ],
                },
                {
                    "fact_type": "other",
                    "name": "Unsupported additional fact",
                    "assertion": "present",
                    "evidence": [
                        {
                            "document_id": str(document_id),
                            "exact_quote": (
                                "Physical therapy was attempted."
                            ),
                            "start_char": 28,
                            "end_char": 59,
                        }
                    ],
                },
            ]
        }
    )

    expected = [
        ExpectedClinicalFact(
            fact_type="symptom",
            name="Lower back pain",
            assertion="present",
        ),
        ExpectedClinicalFact(
            fact_type="procedure",
            name="Physical therapy",
            assertion="historical",
        ),
    ]

    result = evaluate_extraction(
        extraction=extraction,
        expected_facts=expected,
        documents={document_id: content},
    )

    assert result.precision == pytest.approx(1 / 3)
    assert result.recall == pytest.approx(1 / 2)
    assert result.f1 == pytest.approx(0.4)
    assert result.classification_accuracy == 0.5
    assert result.unsupported_fact_rate == pytest.approx(2 / 3)
    assert result.citation_validity == 1.0


def test_invalid_citation_scores_zero() -> None:
    document_id = uuid4()

    extraction = ClinicalExtraction.model_validate(
        {
            "facts": [
                {
                    "fact_type": "symptom",
                    "name": "Headache",
                    "assertion": "present",
                    "evidence": [
                        {
                            "document_id": str(document_id),
                            "exact_quote": "Headache",
                            "start_char": 0,
                            "end_char": 8,
                        }
                    ],
                }
            ]
        }
    )

    expected = [
        ExpectedClinicalFact(
            fact_type="symptom",
            name="Headache",
            assertion="present",
        )
    ]

    result = evaluate_extraction(
        extraction=extraction,
        expected_facts=expected,
        documents={
            document_id: "Back pain"
        },
    )

    assert result.citation_validity == 0.0