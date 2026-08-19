from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_database_session
from app.document_indexing_service import (
    DocumentIndexingError,
    index_document,
)
from app.document_models import ClinicalDocumentRecord
from app.embedding_factory import get_embedding_provider
from app.embedding_service import (
    EmbeddingProvider,
    EmbeddingProviderError,
)
from app.rag_schemas import (
    CaseSearchRequest,
    CaseSearchResponse,
    DocumentIndexResponse,
    RetrievedChunkRead,
)
from app.audit_models import AuditEventRecord
from app.audit_schemas import (
    AuditActorType,
    AuditEventType,
)
from app.document_retrieval_service import (
    DocumentRetrievalError,
    retrieve_case_chunks,
)
from app.models import CaseRecord

router = APIRouter(
    prefix="/v1/cases",
    tags=["rag"],
)


@router.post(
    "/{case_id}/documents/{document_id}/index",
    response_model=DocumentIndexResponse,
)
def index_clinical_document(
    case_id: UUID,
    document_id: UUID,
    database: Annotated[
        Session,
        Depends(get_database_session),
    ],
    provider: Annotated[
        EmbeddingProvider,
        Depends(get_embedding_provider),
    ],
) -> DocumentIndexResponse:
    statement = select(
        ClinicalDocumentRecord
    ).where(
        ClinicalDocumentRecord.id == document_id,
        ClinicalDocumentRecord.case_id == case_id,
    )

    document = database.scalar(statement)

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found for this case",
        )

    try:
        result = index_document(
            database,
            document=document,
            provider=provider,
        )

        if not result.reused_existing:
            audit_event = AuditEventRecord(
                case_id=case_id,
                event_type=(
                    AuditEventType.document_indexed.value
                ),
                actor_type=AuditActorType.system.value,
                details={
                    "document_id": str(document.id),
                    "chunk_count": len(result.chunks),
                    "embedding_model": (
                        result.embedding_model
                    ),
                    "document_sha256": (
                        document.content_sha256
                    ),
                },
            )

            database.add(audit_event)

        database.commit()
    except DocumentIndexingError as error:
        database.rollback()

        raise HTTPException(
            status_code=(
                status.HTTP_422_UNPROCESSABLE_CONTENT
            ),
            detail=str(error),
        ) from error
    except EmbeddingProviderError as error:
        database.rollback()

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Embedding provider failed",
        ) from error
    except IntegrityError as error:
        database.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document indexing conflict",
        ) from error

    for chunk in result.chunks:
        database.refresh(chunk)

    return DocumentIndexResponse(
        document_id=document.id,
        chunk_count=len(result.chunks),
        embedding_model=result.embedding_model,
        reused_existing=result.reused_existing,
        chunks=result.chunks,
    )

@router.post(
    "/{case_id}/search",
    response_model=CaseSearchResponse,
)
def search_case_documents(
    case_id: UUID,
    payload: CaseSearchRequest,
    database: Annotated[
        Session,
        Depends(get_database_session),
    ],
    provider: Annotated[
        EmbeddingProvider,
        Depends(get_embedding_provider),
    ],
) -> CaseSearchResponse:
    case = database.get(CaseRecord, case_id)

    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found",
        )

    try:
        retrieval = retrieve_case_chunks(
            database,
            case_id=case_id,
            query=payload.query,
            provider=provider,
            top_k=payload.top_k,
        )
    except DocumentRetrievalError as error:
        raise HTTPException(
            status_code=(
                status.HTTP_422_UNPROCESSABLE_CONTENT
            ),
            detail=str(error),
        ) from error
    except EmbeddingProviderError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Embedding provider failed",
        ) from error

    results = [
        RetrievedChunkRead(
            id=item.chunk.id,
            document_id=item.chunk.document_id,
            chunk_index=item.chunk.chunk_index,
            content=item.chunk.content,
            start_char=item.chunk.start_char,
            end_char=item.chunk.end_char,
            content_sha256=(
                item.chunk.content_sha256
            ),
            embedding_model=(
                item.chunk.embedding_model
            ),
            similarity=item.similarity,
        )
        for item in retrieval.results
    ]

    return CaseSearchResponse(
        query=payload.query,
        top_k=payload.top_k,
        embedding_model=retrieval.embedding_model,
        result_count=len(results),
        results=results,
    )