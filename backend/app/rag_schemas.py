from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


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