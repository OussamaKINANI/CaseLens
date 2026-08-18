from hashlib import sha256
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit_models import AuditEventRecord
from app.audit_schemas import (
    AuditActorType,
    AuditEventType,
)
from app.database import get_database_session
from app.document_models import ClinicalDocumentRecord
from app.document_schemas import ClinicalDocumentRead
from app.models import CaseRecord


router = APIRouter(prefix="/v1/cases")

MAX_DOCUMENT_SIZE_BYTES = 1_000_000
ALLOWED_DOCUMENT_MEDIA_TYPES = {"text/plain"}


@router.post(
    "/{case_id}/documents",
    response_model=ClinicalDocumentRead,
    status_code=status.HTTP_201_CREATED,
    tags=["documents"],
)
def upload_clinical_document(
    case_id: UUID,
    file: Annotated[UploadFile, File()],
    database: Session = Depends(get_database_session),
) -> ClinicalDocumentRecord:
    case = database.get(CaseRecord, case_id)

    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found",
        )

    if file.content_type not in ALLOWED_DOCUMENT_MEDIA_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only UTF-8 text files are supported",
        )

    content_bytes = file.file.read(MAX_DOCUMENT_SIZE_BYTES + 1)
    file.file.close()

    if not content_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Document is empty",
        )

    if len(content_bytes) > MAX_DOCUMENT_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Document exceeds the 1 MB limit",
        )

    try:
        content = content_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Document must use UTF-8 encoding",
        ) from error

    raw_filename = file.filename or "clinical-note.txt"
    safe_filename = raw_filename.replace("\\", "/").split("/")[-1]
    content_hash = sha256(content_bytes).hexdigest()

    document = ClinicalDocumentRecord(
        case_id=case.id,
        filename=safe_filename,
        media_type=file.content_type,
        size_bytes=len(content_bytes),
        content_sha256=content_hash,
        content=content,
    )

    try:
        database.add(document)
        database.flush()

        audit_event = AuditEventRecord(
            case_id=case.id,
            event_type=AuditEventType.document_uploaded.value,
            actor_type=AuditActorType.system.value,
            details={
                "document_id": str(document.id),
                "filename": document.filename,
                "size_bytes": document.size_bytes,
                "content_sha256": document.content_sha256,
            },
        )

        database.add(audit_event)
        database.commit()
    except IntegrityError as error:
        database.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This document has already been uploaded",
        ) from error

    database.refresh(document)
    return document


@router.get(
    "/{case_id}/documents",
    response_model=list[ClinicalDocumentRead],
    tags=["documents"],
)
def list_clinical_documents(
    case_id: UUID,
    database: Session = Depends(get_database_session),
) -> list[ClinicalDocumentRecord]:
    case = database.get(CaseRecord, case_id)

    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found",
        )

    statement = (
        select(ClinicalDocumentRecord)
        .where(ClinicalDocumentRecord.case_id == case_id)
        .order_by(
            ClinicalDocumentRecord.uploaded_at.asc(),
            ClinicalDocumentRecord.id.asc(),
        )
    )

    return list(database.scalars(statement).all())