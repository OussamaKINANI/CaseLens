from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.audit_models import AuditEventRecord
from app.audit_schemas import (
    AuditActorType,
    AuditEventRead,
    AuditEventType,
)
from app.database import get_database_session
from app.document_models import ClinicalDocumentRecord
from app.extraction_models import ClinicalExtractionRecord
from app.models import CaseRecord
from app.review_models import CaseReviewRunRecord
from app.review_schemas import ReviewRunStatus
from app.schemas import (
    CaseCreate,
    CaseRead,
    CaseStatus,
    CaseStatusUpdate,
)


router = APIRouter(prefix="/v1/cases")


ACTIVE_REVIEW_RUN_STATUSES: set[ReviewRunStatus] = {
    ReviewRunStatus.queued,
    ReviewRunStatus.running,
    ReviewRunStatus.awaiting_human_review,
}


ALLOWED_STATUS_TRANSITIONS: dict[CaseStatus, set[CaseStatus]] = {
    CaseStatus.received: {
        CaseStatus.processing,
        CaseStatus.failed,
    },
    CaseStatus.processing: {
        CaseStatus.awaiting_review,
        CaseStatus.failed,
    },
    CaseStatus.awaiting_review: {
        CaseStatus.processing,
        CaseStatus.completed,
        CaseStatus.failed,
    },
    CaseStatus.completed: set(),
    CaseStatus.failed: {
        CaseStatus.processing,
    },
}


@router.post(
    "",
    response_model=CaseRead,
    status_code=status.HTTP_201_CREATED,
    tags=["cases"],
)
def create_case(
    payload: CaseCreate,
    database: Session = Depends(get_database_session),
) -> CaseRecord:
    case = CaseRecord(
        patient_external_id=payload.patient_external_id,
        requested_service=payload.requested_service,
        priority=payload.priority.value,
        status=CaseStatus.received.value,
    )

    database.add(case)
    database.flush()

    audit_event = AuditEventRecord(
        case_id=case.id,
        event_type=AuditEventType.case_created.value,
        actor_type=AuditActorType.system.value,
        details={
            "initial_status": case.status,
            "priority": case.priority,
        },
    )

    database.add(audit_event)
    database.commit()
    database.refresh(case)

    return case


@router.get(
    "",
    response_model=list[CaseRead],
    tags=["cases"],
)
def list_cases(
    database: Session = Depends(get_database_session),
) -> list[CaseRecord]:
    statement = select(CaseRecord).order_by(
        CaseRecord.created_at.desc(),
    )

    return list(database.scalars(statement).all())


@router.get(
    "/{case_id}",
    response_model=CaseRead,
    tags=["cases"],
)
def get_case(
    case_id: UUID,
    database: Session = Depends(get_database_session),
) -> CaseRecord:
    case = database.get(CaseRecord, case_id)

    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found",
        )

    return case


@router.delete(
    "/{case_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["cases"],
)
def delete_case(
    case_id: UUID,
    database: Session = Depends(get_database_session),
) -> Response:
    case = database.get(CaseRecord, case_id)

    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found",
        )

    active_run = database.scalar(
        select(CaseReviewRunRecord.id)
        .where(
            CaseReviewRunRecord.case_id == case_id,
            CaseReviewRunRecord.status.in_(
                [
                    run_status.value
                    for run_status in ACTIVE_REVIEW_RUN_STATUSES
                ]
            ),
        )
        .limit(1)
    )

    if active_run is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Cannot delete a case while a durable review "
                "is in progress. Complete or reject the review "
                "first."
            ),
        )

    # Delete dependents in FK order. Document chunks cascade at the
    # database level when their owning documents are removed.
    database.execute(
        delete(ClinicalExtractionRecord).where(
            ClinicalExtractionRecord.case_id == case_id,
        )
    )

    database.execute(
        delete(ClinicalDocumentRecord).where(
            ClinicalDocumentRecord.case_id == case_id,
        )
    )

    database.execute(
        delete(CaseReviewRunRecord).where(
            CaseReviewRunRecord.case_id == case_id,
        )
    )

    database.execute(
        delete(AuditEventRecord).where(
            AuditEventRecord.case_id == case_id,
        )
    )

    database.delete(case)
    database.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch(
    "/{case_id}/status",
    response_model=CaseRead,
    tags=["cases"],
)
def update_case_status(
    case_id: UUID,
    payload: CaseStatusUpdate,
    database: Session = Depends(get_database_session),
) -> CaseRecord:
    case = database.get(CaseRecord, case_id)

    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found",
        )

    current_status = CaseStatus(case.status)
    allowed_statuses = ALLOWED_STATUS_TRANSITIONS[current_status]

    if payload.status not in allowed_statuses:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Cannot transition case from "
                f"{current_status.value} to {payload.status.value}"
            ),
        )

    case.status = payload.status.value

    audit_event = AuditEventRecord(
        case_id=case.id,
        event_type=AuditEventType.status_changed.value,
        actor_type=AuditActorType.system.value,
        details={
            "previous_status": current_status.value,
            "new_status": payload.status.value,
            "reason": payload.reason,
        },
    )

    database.add(audit_event)
    database.commit()
    database.refresh(case)

    return case


@router.get(
    "/{case_id}/audit",
    response_model=list[AuditEventRead],
    tags=["audit"],
)
def list_case_audit_events(
    case_id: UUID,
    database: Session = Depends(get_database_session),
) -> list[AuditEventRecord]:
    case = database.get(CaseRecord, case_id)

    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found",
        )

    statement = (
        select(AuditEventRecord)
        .where(AuditEventRecord.case_id == case_id)
        .order_by(
            AuditEventRecord.created_at.asc(),
            AuditEventRecord.id.asc(),
        )
    )

    return list(database.scalars(statement).all())