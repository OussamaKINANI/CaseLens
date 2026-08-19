from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit_models import AuditEventRecord
from app.audit_schemas import AuditActorType, AuditEventType
from app.database import get_database_session
from app.document_models import ClinicalDocumentRecord
from app.extraction_models import ClinicalExtractionRecord
from app.extraction_schemas import ClinicalExtractionRead
from app.extraction_provider_factory import (
    get_extraction_provider,
)
from app.extraction_service import (
    EvidenceVerificationError,
    ExtractionProvider,
    ExtractionProviderError,
    verify_extraction_evidence,
)
from app.models import CaseRecord


router = APIRouter(
    prefix="/v1/cases",
    tags=["extractions"],
)


@router.post(
    "/{case_id}/documents/{document_id}/extractions",
    response_model=ClinicalExtractionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_clinical_extraction(
    case_id: UUID,
    document_id: UUID,
    database: Session = Depends(get_database_session),
    extraction_provider: ExtractionProvider = Depends(
        get_extraction_provider
    ),
) -> ClinicalExtractionRecord:
    document = database.scalar(
        select(ClinicalDocumentRecord).where(
            ClinicalDocumentRecord.id == document_id,
            ClinicalDocumentRecord.case_id == case_id,
        )
    )

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clinical document not found",
        )

    existing_extraction = database.scalar(
        select(ClinicalExtractionRecord).where(
            ClinicalExtractionRecord.document_id == document_id,
            ClinicalExtractionRecord.provider_name
            == extraction_provider.provider_name,
            ClinicalExtractionRecord.model_name
            == extraction_provider.model_name,
            ClinicalExtractionRecord.schema_version == "1.0",
        )
    )

    if existing_extraction is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Extraction already exists for this document",
        )

    try:
        extraction = extraction_provider.extract(
            document_id=document.id,
            content=document.content,
        )

        verify_extraction_evidence(
            extraction=extraction,
            documents={
                document.id: document.content,
            },
        )
    except ExtractionProviderError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Extraction provider failed",
        ) from error
    
    except EvidenceVerificationError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Extraction provider returned unverifiable evidence",
        ) from error

    extraction_record = ClinicalExtractionRecord(
        case_id=case_id,
        document_id=document.id,
        provider_name=extraction_provider.provider_name,
        model_name=extraction_provider.model_name,
        schema_version=extraction.schema_version,
        source_sha256=document.content_sha256,
        result=extraction.model_dump(mode="json"),
    )

    started_event = AuditEventRecord(
        case_id=case_id,
        event_type=AuditEventType.ai_review_started.value,
        actor_type=AuditActorType.system.value,
        details={
            "document_id": str(document.id),
            "provider_name": extraction_provider.provider_name,
            "model_name": extraction_provider.model_name,
        },
    )

    database.add(extraction_record)
    database.add(started_event)
    database.flush()

    completed_event = AuditEventRecord(
        case_id=case_id,
        event_type=AuditEventType.ai_review_completed.value,
        actor_type=AuditActorType.system.value,
        details={
            "document_id": str(document.id),
            "extraction_id": str(extraction_record.id),
            "fact_count": len(extraction.facts),
            "provider_name": extraction_provider.provider_name,
            "model_name": extraction_provider.model_name,
        },
    )

    database.add(completed_event)

    try:
        database.commit()
    except IntegrityError as error:
        database.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Extraction already exists for this document",
        ) from error

    database.refresh(extraction_record)

    return extraction_record


@router.get(
    "/{case_id}/extractions",
    response_model=list[ClinicalExtractionRead],
)
def list_clinical_extractions(
    case_id: UUID,
    database: Session = Depends(get_database_session),
) -> list[ClinicalExtractionRecord]:
    case = database.get(CaseRecord, case_id)

    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found",
        )

    return list(
        database.scalars(
            select(ClinicalExtractionRecord)
            .where(ClinicalExtractionRecord.case_id == case_id)
            .order_by(ClinicalExtractionRecord.created_at)
        )
    )