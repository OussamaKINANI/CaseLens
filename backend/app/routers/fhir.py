import json
from collections import Counter
from hashlib import sha256
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
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
from app.fhir_schemas import FHIRBundle, FHIRImportRead
from app.models import CaseRecord


router = APIRouter(
    prefix="/v1/cases",
    tags=["fhir"],
)


@router.post(
    "/{case_id}/fhir-bundles",
    response_model=FHIRImportRead,
    status_code=status.HTTP_201_CREATED,
)
def import_fhir_bundle(
    case_id: UUID,
    bundle: FHIRBundle,
    database: Session = Depends(get_database_session),
) -> FHIRImportRead:
    case = database.get(CaseRecord, case_id)

    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found",
        )

    bundle_data = bundle.model_dump(
        by_alias=True,
        exclude_none=True,
    )

    content = json.dumps(
        bundle_data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )

    content_bytes = content.encode("utf-8")
    content_hash = sha256(content_bytes).hexdigest()

    resource_counts = Counter(
        entry.resource["resourceType"]
        for entry in bundle.entry
    )

    document = ClinicalDocumentRecord(
        case_id=case.id,
        filename=f"fhir-{content_hash[:12]}.json",
        media_type="application/fhir+json",
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
                "document_kind": "fhir_bundle",
                "filename": document.filename,
                "bundle_type": bundle.type,
                "resource_counts": dict(resource_counts),
                "content_sha256": document.content_sha256,
            },
        )

        database.add(audit_event)
        database.commit()
    except IntegrityError as error:
        database.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This FHIR Bundle has already been imported",
        ) from error

    database.refresh(document)

    return FHIRImportRead(
        document=ClinicalDocumentRead.model_validate(document),
        bundle_type=bundle.type,
        resource_counts=dict(sorted(resource_counts.items())),
    )