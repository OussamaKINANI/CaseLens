import math
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.document_models import ClinicalDocumentRecord
from app.embedding_service import EmbeddingProvider
from app.rag_models import DocumentChunkRecord


class DocumentRetrievalError(RuntimeError):
    """Raised when retrieval cannot be completed safely."""


@dataclass(slots=True)
class RetrievedChunk:
    chunk: DocumentChunkRecord
    similarity: float


@dataclass(slots=True)
class DocumentRetrievalResult:
    results: list[RetrievedChunk]
    embedding_model: str


def retrieve_case_chunks(
    database: Session,
    *,
    case_id: UUID,
    query: str,
    provider: EmbeddingProvider,
    top_k: int = 5,
    min_similarity: float = 0.0,
) -> DocumentRetrievalResult:
    normalized_query = query.strip()

    if not normalized_query:
        raise DocumentRetrievalError(
            "Search query cannot be blank"
        )

    if not 1 <= top_k <= 20:
        raise DocumentRetrievalError(
            "top_k must be between 1 and 20"
        )

    if not -1.0 <= min_similarity <= 1.0:
        raise DocumentRetrievalError(
            "min_similarity must be between -1 and 1"
        )

    embedding_model = (
        f"{provider.provider_name}/"
        f"{provider.model_name}/"
        f"{provider.dimensions}"
    )

    if len(embedding_model) > 100:
        raise DocumentRetrievalError(
            "Embedding model identifier is too long"
        )

    candidate_statement = (
        select(DocumentChunkRecord.id)
        .join(
            ClinicalDocumentRecord,
            ClinicalDocumentRecord.id
            == DocumentChunkRecord.document_id,
        )
        .where(
            ClinicalDocumentRecord.case_id == case_id,
            DocumentChunkRecord.embedding_model
            == embedding_model,
        )
        .limit(1)
    )

    if database.scalar(candidate_statement) is None:
        return DocumentRetrievalResult(
            results=[],
            embedding_model=embedding_model,
        )

    vectors = provider.embed([normalized_query])

    if len(vectors) != 1:
        raise DocumentRetrievalError(
            "Embedding provider returned the wrong "
            "number of query vectors"
        )

    query_vector = vectors[0]

    if len(query_vector) != provider.dimensions:
        raise DocumentRetrievalError(
            "Embedding provider returned a query vector "
            "with invalid dimensions"
        )

    if any(
        not math.isfinite(value)
        for value in query_vector
    ):
        raise DocumentRetrievalError(
            "Embedding provider returned a non-finite "
            "query vector"
        )

    cosine_distance = (
        DocumentChunkRecord.embedding.cosine_distance(
            query_vector
        )
    )

    statement = (
        select(
            DocumentChunkRecord,
            cosine_distance.label("cosine_distance"),
        )
        .join(
            ClinicalDocumentRecord,
            ClinicalDocumentRecord.id
            == DocumentChunkRecord.document_id,
        )
        .where(
            ClinicalDocumentRecord.case_id == case_id,
            DocumentChunkRecord.embedding_model
            == embedding_model,
            cosine_distance
            <= 1.0 - min_similarity,
        )
        .order_by(
            cosine_distance.asc(),
            DocumentChunkRecord.id.asc(),
        )
        .limit(top_k)
    )

    rows = database.execute(statement).all()

    results = [
        RetrievedChunk(
            chunk=row[0],
            similarity=1.0 - float(row[1]),
        )
        for row in rows
    ]

    return DocumentRetrievalResult(
        results=results,
        embedding_model=embedding_model,
    )