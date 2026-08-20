from datetime import datetime
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from app.answer_schemas import GroundedAnswer


class DocumentChunkRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )

    id: UUID
    document_id: UUID
    chunk_index: int
    content: str
    start_char: int
    end_char: int
    content_sha256: str
    embedding_model: str
    created_at: datetime


class DocumentIndexResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    document_id: UUID
    chunk_count: int
    embedding_model: str
    reused_existing: bool
    chunks: list[DocumentChunkRead]


class CaseSearchRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    query: str = Field(
        min_length=1,
        max_length=2000,
    )

    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
    )

    @field_validator("query")
    @classmethod
    def reject_blank_query(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip()

        if not normalized:
            raise ValueError(
                "Search query cannot be blank"
            )

        return normalized


class RetrievedChunkRead(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    id: UUID
    document_id: UUID
    chunk_index: int
    content: str
    start_char: int
    end_char: int
    content_sha256: str
    embedding_model: str
    similarity: float


class CaseSearchResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    query: str
    top_k: int
    min_similarity: float
    embedding_model: str
    result_count: int
    results: list[RetrievedChunkRead]


class CaseAnswerRequest(CaseSearchRequest):
    pass


class CaseAnswerResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    query: str
    top_k: int
    min_similarity: float
    embedding_model: str
    answer_provider: str
    answer_model: str
    retrieved_chunk_count: int
    answer: GroundedAnswer