from uuid import UUID

from pydantic import Field

from app.extraction_schemas import (
    ClinicalAssertion,
    ClinicalExtraction,
    ClinicalFactType,
    StrictModel,
)


class ExpectedClinicalFact(StrictModel):
    fact_type: ClinicalFactType
    name: str = Field(min_length=1, max_length=200)
    assertion: ClinicalAssertion


class ExtractionEvaluation(StrictModel):
    expected_fact_count: int
    predicted_fact_count: int

    true_positive_count: int
    false_positive_count: int
    false_negative_count: int
    duplicate_fact_count: int

    precision: float = Field(ge=0.0, le=1.0)
    recall: float = Field(ge=0.0, le=1.0)
    f1: float = Field(ge=0.0, le=1.0)

    classification_accuracy: float = Field(
        ge=0.0,
        le=1.0,
    )

    unsupported_fact_rate: float = Field(
        ge=0.0,
        le=1.0,
    )

    citation_validity: float = Field(
        ge=0.0,
        le=1.0,
    )


def normalize_fact_name(name: str) -> str:
    return " ".join(name.casefold().split())


def evaluate_extraction(
    extraction: ClinicalExtraction,
    expected_facts: list[ExpectedClinicalFact],
    documents: dict[UUID, str],
) -> ExtractionEvaluation:
    expected_keys = {
        (
            fact.fact_type.value,
            normalize_fact_name(fact.name),
            fact.assertion.value,
        )
        for fact in expected_facts
    }

    predicted_key_list = [
        (
            fact.fact_type.value,
            normalize_fact_name(fact.name),
            fact.assertion.value,
        )
        for fact in extraction.facts
    ]

    predicted_keys = set(predicted_key_list)

    true_positive_count = len(
        expected_keys & predicted_keys
    )

    false_positive_count = len(
        predicted_keys - expected_keys
    )

    false_negative_count = len(
        expected_keys - predicted_keys
    )

    duplicate_fact_count = (
        len(predicted_key_list) - len(predicted_keys)
    )

    if predicted_keys:
        precision = (
            true_positive_count / len(predicted_keys)
        )
        unsupported_fact_rate = (
            false_positive_count / len(predicted_keys)
        )
    else:
        precision = 1.0 if not expected_keys else 0.0
        unsupported_fact_rate = 0.0

    if expected_keys:
        recall = true_positive_count / len(expected_keys)
    else:
        recall = 1.0

    if precision + recall:
        f1 = (
            2
            * precision
            * recall
            / (precision + recall)
        )
    else:
        f1 = 0.0

    expected_types_by_meaning = {
        (
            normalize_fact_name(fact.name),
            fact.assertion.value,
        ): fact.fact_type.value
        for fact in expected_facts
    }

    classification_matches = 0
    correct_classifications = 0

    for fact_type, name, assertion in predicted_keys:
        expected_type = expected_types_by_meaning.get(
            (name, assertion)
        )

        if expected_type is None:
            continue

        classification_matches += 1

        if fact_type == expected_type:
            correct_classifications += 1

    if classification_matches:
        classification_accuracy = (
            correct_classifications
            / classification_matches
        )
    elif not expected_keys and not predicted_keys:
        classification_accuracy = 1.0
    else:
        classification_accuracy = 0.0

    citation_count = 0
    valid_citation_count = 0

    for fact in extraction.facts:
        for citation in fact.evidence:
            citation_count += 1

            content = documents.get(citation.document_id)

            if content is None:
                continue

            if citation.end_char > len(content):
                continue

            actual_quote = content[
                citation.start_char:citation.end_char
            ]

            if actual_quote == citation.exact_quote:
                valid_citation_count += 1

    if citation_count:
        citation_validity = (
            valid_citation_count / citation_count
        )
    elif not extraction.facts:
        citation_validity = 1.0
    else:
        citation_validity = 0.0

    return ExtractionEvaluation(
        expected_fact_count=len(expected_keys),
        predicted_fact_count=len(predicted_key_list),
        true_positive_count=true_positive_count,
        false_positive_count=false_positive_count,
        false_negative_count=false_negative_count,
        duplicate_fact_count=duplicate_fact_count,
        precision=precision,
        recall=recall,
        f1=f1,
        classification_accuracy=classification_accuracy,
        unsupported_fact_rate=unsupported_fact_rate,
        citation_validity=citation_validity,
    )

class ExtractionEvaluationCase(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    document_id: UUID
    content: str = Field(min_length=1)
    expected_facts: list[ExpectedClinicalFact]