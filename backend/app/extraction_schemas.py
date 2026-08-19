from enum import Enum
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from datetime import datetime


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


class ClinicalFactType(str, Enum):
    condition = "condition"
    symptom = "symptom"
    medication = "medication"
    procedure = "procedure"
    lab_result = "lab_result"
    allergy = "allergy"
    demographic = "demographic"
    other = "other"


class ClinicalAssertion(str, Enum):
    present = "present"
    absent = "absent"
    possible = "possible"
    historical = "historical"


class EvidenceCitation(StrictModel):
    document_id: UUID
    exact_quote: str = Field(min_length=1, max_length=500)
    start_char: int = Field(ge=0)
    end_char: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_character_range(self) -> Self:
        if self.end_char <= self.start_char:
            raise ValueError(
                "end_char must be greater than start_char"
            )

        return self


class ClinicalFact(StrictModel):
    fact_type: ClinicalFactType
    name: str = Field(min_length=1, max_length=200)
    value: str | None = Field(default=None, max_length=500)
    assertion: ClinicalAssertion
    evidence: list[EvidenceCitation] = Field(min_length=1)


class ClinicalExtraction(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    facts: list[ClinicalFact] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

class ClinicalExtractionRead(StrictModel):
    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        str_strip_whitespace=True,
    )

    id: UUID
    case_id: UUID
    document_id: UUID
    provider_name: str
    model_name: str
    schema_version: str
    source_sha256: str
    result: ClinicalExtraction
    created_at: datetime