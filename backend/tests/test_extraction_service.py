from uuid import uuid4

import pytest

from app.extraction_schemas import ClinicalExtraction
from app.extraction_service import (
    EvidenceVerificationError,
    FakeExtractionProvider,
    verify_extraction_evidence,
)


def test_fake_provider_extracts_supported_facts() -> None:
    document_id = uuid4()
    content = (
        "Persistent lower back pain for six weeks. "
        "Physical therapy did not improve symptoms."
    )

    provider = FakeExtractionProvider()

    extraction = provider.extract(
        document_id=document_id,
        content=content,
    )

    fact_names = [fact.name for fact in extraction.facts]

    assert fact_names == [
        "lower back pain",
        "physical therapy",
    ]

    verify_extraction_evidence(
        extraction=extraction,
        documents={document_id: content},
    )


def test_fake_provider_returns_missing_information() -> None:
    document_id = uuid4()

    provider = FakeExtractionProvider()

    extraction = provider.extract(
        document_id=document_id,
        content="Synthetic record without a supported phrase.",
    )

    assert extraction.facts == []
    assert extraction.missing_information == [
        "No supported clinical facts were found."
    ]


def test_verifier_rejects_fabricated_quote() -> None:
    document_id = uuid4()

    extraction = ClinicalExtraction.model_validate(
        {
            "facts": [
                {
                    "fact_type": "condition",
                    "name": "diabetes",
                    "assertion": "present",
                    "evidence": [
                        {
                            "document_id": str(document_id),
                            "exact_quote": "diabetes",
                            "start_char": 0,
                            "end_char": 8,
                        }
                    ],
                }
            ]
        }
    )

    with pytest.raises(
        EvidenceVerificationError,
        match="does not match",
    ):
        verify_extraction_evidence(
            extraction=extraction,
            documents={
                document_id: "headache"
            },
        )