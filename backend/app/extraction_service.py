from typing import Protocol
from uuid import UUID

from app.extraction_schemas import (
    ClinicalAssertion,
    ClinicalExtraction,
    ClinicalFact,
    ClinicalFactType,
    EvidenceCitation,
)


class ExtractionProvider(Protocol):
    provider_name: str
    model_name: str

    def extract(
        self,
        document_id: UUID,
        content: str,
    ) -> ClinicalExtraction:
        ...


class FakeExtractionProvider:
    provider_name = "fake"
    model_name = "deterministic-rules-v1"

    def extract(
        self,
        document_id: UUID,
        content: str,
    ) -> ClinicalExtraction:
        facts: list[ClinicalFact] = []
        lowered_content = content.lower()

        patterns = [
            (
                "lower back pain",
                ClinicalFactType.symptom,
                "lower back pain",
                ClinicalAssertion.present,
            ),
            (
                "physical therapy",
                ClinicalFactType.procedure,
                "physical therapy",
                ClinicalAssertion.historical,
            ),
        ]

        for (
            phrase,
            fact_type,
            fact_name,
            assertion,
        ) in patterns:
            start_char = lowered_content.find(phrase)

            if start_char == -1:
                continue

            end_char = start_char + len(phrase)
            exact_quote = content[start_char:end_char]

            facts.append(
                ClinicalFact(
                    fact_type=fact_type,
                    name=fact_name,
                    value=None,
                    assertion=assertion,
                    evidence=[
                        EvidenceCitation(
                            document_id=document_id,
                            exact_quote=exact_quote,
                            start_char=start_char,
                            end_char=end_char,
                        )
                    ],
                )
            )

        missing_information: list[str] = []

        if not facts:
            missing_information.append(
                "No supported clinical facts were found."
            )

        return ClinicalExtraction(
            facts=facts,
            missing_information=missing_information,
            warnings=[],
        )


class EvidenceVerificationError(ValueError):
    pass


def verify_extraction_evidence(
    extraction: ClinicalExtraction,
    documents: dict[UUID, str],
) -> None:
    for fact_index, fact in enumerate(extraction.facts):
        for citation_index, citation in enumerate(fact.evidence):
            content = documents.get(citation.document_id)

            if content is None:
                raise EvidenceVerificationError(
                    "Evidence references an unknown document: "
                    f"fact={fact_index}, citation={citation_index}"
                )

            if citation.end_char > len(content):
                raise EvidenceVerificationError(
                    "Evidence character range exceeds document length: "
                    f"fact={fact_index}, citation={citation_index}"
                )

            actual_quote = content[
                citation.start_char:citation.end_char
            ]

            if actual_quote != citation.exact_quote:
                raise EvidenceVerificationError(
                    "Evidence quote does not match source document: "
                    f"fact={fact_index}, citation={citation_index}"
                )

class ExtractionProviderError(RuntimeError):
    pass