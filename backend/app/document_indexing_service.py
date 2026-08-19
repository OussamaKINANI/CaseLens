import math
from dataclasses import dataclass
from hashlib import sha256

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.chunking import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    chunk_text,
)
from app.document_models import ClinicalDocumentRecord
from app.embedding_service import EmbeddingProvider
from app.rag_models import DocumentChunkRecord


class DocumentIndexingError(RuntimeError):
    """Raised when a document cannot be safely indexed."""


@dataclass(slots=True)
class DocumentIndexingResult:
    chunks: list[DocumentChunkRecord]
    embedding_model: str
    reused_existing: bool


def index_document(
    database: Session,
    *,
    document: ClinicalDocumentRecord,
    provider: EmbeddingProvider,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> DocumentIndexingResult:
    if document.id is None:
        raise DocumentIndexingError(
            "Document must be persisted before indexing"
        )

    text_chunks = chunk_text(
        document.content,
        chunk_size=chunk_size,
        overlap=overlap,
    )

    if not text_chunks:
        raise DocumentIndexingError(
            "Document contains no searchable text"
        )

    embedding_model = (
        f"{provider.provider_name}/"
        f"{provider.model_name}/"
        f"{provider.dimensions}"
    )

    if len(embedding_model) > 100:
        raise DocumentIndexingError(
            "Embedding model identifier is too long"
        )

    chunk_hashes = [
        sha256(
            chunk.content.encode("utf-8")
        ).hexdigest()
        for chunk in text_chunks
    ]

    existing_statement = (
        select(DocumentChunkRecord)
        .where(
            DocumentChunkRecord.document_id
            == document.id,
            DocumentChunkRecord.embedding_model
            == embedding_model,
        )
        .order_by(
            DocumentChunkRecord.chunk_index.asc()
        )
    )

    existing_chunks = list(
        database.scalars(
            existing_statement
        ).all()
    )

    existing_index_is_current = (
        len(existing_chunks) == len(text_chunks)
        and all(
            record.chunk_index == chunk.chunk_index
            and record.content == chunk.content
            and record.start_char == chunk.start_char
            and record.end_char == chunk.end_char
            and record.content_sha256 == content_hash
            for record, chunk, content_hash in zip(
                existing_chunks,
                text_chunks,
                chunk_hashes,
                strict=True,
            )
        )
    )

    if existing_index_is_current:
        return DocumentIndexingResult(
            chunks=existing_chunks,
            embedding_model=embedding_model,
            reused_existing=True,
        )

    vectors = provider.embed([
        chunk.content
        for chunk in text_chunks
    ])

    if len(vectors) != len(text_chunks):
        raise DocumentIndexingError(
            "Embedding provider returned the wrong "
            "number of vectors"
        )

    for vector in vectors:
        if len(vector) != provider.dimensions:
            raise DocumentIndexingError(
                "Embedding provider returned a vector "
                "with invalid dimensions"
            )

        if any(
            not math.isfinite(value)
            for value in vector
        ):
            raise DocumentIndexingError(
                "Embedding provider returned a "
                "non-finite vector"
            )

    database.execute(
        delete(DocumentChunkRecord).where(
            DocumentChunkRecord.document_id
            == document.id,
            DocumentChunkRecord.embedding_model
            == embedding_model,
        )
    )

    records = [
        DocumentChunkRecord(
            document_id=document.id,
            chunk_index=chunk.chunk_index,
            content=chunk.content,
            start_char=chunk.start_char,
            end_char=chunk.end_char,
            content_sha256=content_hash,
            embedding_model=embedding_model,
            embedding=vector,
        )
        for chunk, content_hash, vector in zip(
            text_chunks,
            chunk_hashes,
            vectors,
            strict=True,
        )
    ]

    database.add_all(records)
    database.flush()

    return DocumentIndexingResult(
        chunks=records,
        embedding_model=embedding_model,
        reused_existing=False,
    )