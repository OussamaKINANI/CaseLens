from typing import Literal
from uuid import UUID

from pydantic import Field

from app.extraction_schemas import StrictModel


class OpenAIAnswerCitation(StrictModel):
    chunk_id: UUID
    exact_quote: str = Field(
        min_length=1,
        max_length=1000,
    )


class OpenAIGroundedAnswerResponse(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    supported: bool
    answer: str = Field(
        min_length=1,
        max_length=4000,
    )
    citations: list[OpenAIAnswerCitation] = Field(
        default_factory=list,
    )