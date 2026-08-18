from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_database_session
from app.models import CaseRecord
from app.schemas import (
    CaseCreate,
    CaseRead,
    CaseStatus,
    CaseStatusUpdate,
)
from app.audit_models import AuditEventRecord
from app.audit_schemas import (
    AuditActorType,
    AuditEventRead,
    AuditEventType,
)


app = FastAPI(
    title="CaseLens API",
    description="Evidence-grounded clinical case review API",
    version="0.1.0",
)

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


@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    return {
        "status": "healthy",
        "service": "caselens-api",
    }


@app.get("/ready", tags=["system"])
def readiness_check(
    database: Session = Depends(get_database_session),
) -> dict[str, str]:
    try:
        database.execute(text("SELECT 1"))
    except SQLAlchemyError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        ) from error

    return {
        "status": "ready",
        "database": "reachable",
    }


@app.post(
    "/v1/cases",
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

@app.get(
    "/v1/cases",
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


@app.get(
    "/v1/cases/{case_id}",
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

@app.get(
    "/v1/cases/{case_id}/audit",
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

@app.patch(
    "/v1/cases/{case_id}/status",
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