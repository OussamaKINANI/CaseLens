from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit_models import AuditEventRecord
from app.audit_schemas import (
    AuditActorType,
    AuditEventRead,
    AuditEventType,
)
from app.database import get_database_session
from app.models import CaseRecord
from app.schemas import (
    CaseCreate,
    CaseRead,
    CaseStatus,
    CaseStatusUpdate,
)


router = APIRouter(prefix="/v1/cases")


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