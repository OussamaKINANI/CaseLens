from typing import Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from app.extraction_schemas import StrictModel


class GroundedAnswerCitation(StrictModel):
    chunk_id: UUID
    document_id: UUID
    exact_quote: str = Field(
        min_length=1,
        max_length=1000,
    )
    start_char: int = Field(ge=0)
    end_char: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_character_range(
        self,
    ) -> Self:
        if self.end_char <= self.start_char:
            raise ValueError(
                "end_char must be greater than start_char"
            )

        return self


class GroundedAnswer(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    supported: bool
    answer: str = Field(
        min_length=1,
        max_length=4000,
    )
    citations: list[GroundedAnswerCitation] = Field(
        default_factory=list,
    )

    @model_validator(mode="after")
    def validate_support_and_citations(
        self,
    ) -> Self:
        if self.supported and not self.citations:
            raise ValueError(
                "Supported answers require citations"
            )

        if not self.supported and self.citations:
            raise ValueError(
                "Unsupported answers cannot have citations"
            )

        return self