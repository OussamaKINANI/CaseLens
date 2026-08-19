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
    CaseAnswerRequest,
    CaseAnswerResponse,
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
from hashlib import sha256

from app.answer_provider_factory import (
    get_answer_provider,
)
from app.answer_service import (
    AnswerEvidence,
    AnswerEvidenceVerificationError,
    AnswerProvider,
    AnswerProviderError,
    create_insufficient_evidence_answer,
    verify_grounded_answer,
)

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

@router.post(
    "/{case_id}/answer",
    response_model=CaseAnswerResponse,
)
def answer_case_question(
    case_id: UUID,
    payload: CaseAnswerRequest,
    database: Annotated[
        Session,
        Depends(get_database_session),
    ],
    embedding_provider: Annotated[
        EmbeddingProvider,
        Depends(get_embedding_provider),
    ],
    answer_provider: Annotated[
        AnswerProvider,
        Depends(get_answer_provider),
    ],
) -> CaseAnswerResponse:
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
            provider=embedding_provider,
            top_k=payload.top_k,
        )

        evidence = [
            AnswerEvidence(
                chunk_id=item.chunk.id,
                document_id=item.chunk.document_id,
                content=item.chunk.content,
                start_char=item.chunk.start_char,
                end_char=item.chunk.end_char,
            )
            for item in retrieval.results
        ]

        if evidence:
            grounded_answer = answer_provider.answer(
                payload.query,
                evidence,
            )
        else:
            grounded_answer = (
                create_insufficient_evidence_answer()
            )

        verify_grounded_answer(
            grounded_answer,
            evidence,
        )
    except DocumentRetrievalError as error:
        raise HTTPException(
            status_code=(
                status.HTTP_422_UNPROCESSABLE_CONTENT
            ),
            detail=str(error),
        ) from error
    except (
        EmbeddingProviderError,
        AnswerProviderError,
    ) as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI provider failed",
        ) from error
    except AnswerEvidenceVerificationError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Generated answer failed evidence "
                "verification"
            ),
        ) from error

    retrieved_chunk_ids = [
        str(item.chunk.id)
        for item in retrieval.results
    ]

    audit_event = AuditEventRecord(
        case_id=case_id,
        event_type=(
            AuditEventType.rag_answer_generated.value
        ),
        actor_type=AuditActorType.system.value,
        details={
            "query_sha256": sha256(
                payload.query.encode("utf-8")
            ).hexdigest(),
            "top_k": payload.top_k,
            "retrieved_chunk_count": len(evidence),
            "retrieved_chunk_ids": retrieved_chunk_ids,
            "embedding_model": retrieval.embedding_model,
            "answer_provider": (
                answer_provider.provider_name
            ),
            "answer_model": answer_provider.model_name,
            "supported": grounded_answer.supported,
            "citation_count": len(
                grounded_answer.citations
            ),
        },
    )

    try:
        database.add(audit_event)
        database.commit()
    except IntegrityError as error:
        database.rollback()

        raise HTTPException(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail="Unable to record answer audit event",
        ) from error

    return CaseAnswerResponse(
        query=payload.query,
        top_k=payload.top_k,
        embedding_model=retrieval.embedding_model,
        answer_provider=answer_provider.provider_name,
        answer_model=answer_provider.model_name,
        retrieved_chunk_count=len(evidence),
        answer=grounded_answer,
    )