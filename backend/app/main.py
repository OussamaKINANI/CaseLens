from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import FastAPI, status

from app.schemas import CaseCreate, CaseRead, CaseStatus


app = FastAPI(
    title="CaseLens API",
    description="Evidence-grounded clinical case review API",
    version="0.1.0",
)


cases: dict[UUID, CaseRead] = {}


@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    return {
        "status": "healthy",
        "service": "caselens-api",
    }


@app.post(
    "/v1/cases",
    response_model=CaseRead,
    status_code=status.HTTP_201_CREATED,
    tags=["cases"],
)
def create_case(payload: CaseCreate) -> CaseRead:
    case = CaseRead(
        id=uuid4(),
        status=CaseStatus.received,
        created_at=datetime.now(timezone.utc),
        **payload.model_dump(),
    )

    cases[case.id] = case
    return case