from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_database_session
from app.models import CaseRecord
from app.schemas import CaseCreate, CaseRead, CaseStatus


app = FastAPI(
    title="CaseLens API",
    description="Evidence-grounded clinical case review API",
    version="0.1.0",
)


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