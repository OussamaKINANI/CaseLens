from typing import Literal
from uuid import UUID

from pydantic import Field

from app.extraction_schemas import (
    ClinicalAssertion,
    ClinicalFactType,
    StrictModel,
)


class OpenAIEvidenceCitation(StrictModel):
    document_id: UUID
    exact_quote: str = Field(
        min_length=1,
        max_length=500,
    )


class OpenAIClinicalFact(StrictModel):
    fact_type: ClinicalFactType
    name: str = Field(min_length=1, max_length=200)
    value: str | None = Field(default=None, max_length=500)
    assertion: ClinicalAssertion

    evidence: list[OpenAIEvidenceCitation] = Field(
        min_length=1,
    )


class OpenAIExtractionResponse(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    facts: list[OpenAIClinicalFact] = Field(
        default_factory=list,
    )
    missing_information: list[str] = Field(
        default_factory=list,
    )
    warnings: list[str] = Field(
        default_factory=list,
    )