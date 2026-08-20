from uuid import UUID, uuid4

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
from app.document_models import ClinicalDocumentRecord
from app.models import CaseRecord
from app.review_models import CaseReviewRunRecord
from app.review_schemas import (
    CaseReviewRunCreate,
    CaseReviewRunRead,
    HumanReviewRequest,
    ReviewRunStatus,
    ReviewWorkflowCommandResponse,
)
from app.review_workflow_gateway import (
    ReviewWorkflowGateway,
    ReviewWorkflowGatewayError,
    get_review_workflow_gateway,
)
from app.temporal_models import (
    CaseReviewWorkflowInput,
    HumanReviewUpdate,
)


router = APIRouter(
    prefix="/v1/cases",
    tags=["review workflows"],
)


def get_scoped_review_run(
    database: Session,
    *,
    case_id: UUID,
    review_run_id: UUID,
) -> CaseReviewRunRecord:
    statement = select(
        CaseReviewRunRecord
    ).where(
        CaseReviewRunRecord.id == review_run_id,
        CaseReviewRunRecord.case_id == case_id,
    )

    review_run = database.scalar(statement)

    if review_run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review run not found for this case",
        )

    return review_run


@router.post(
    "/{case_id}/review-runs",
    response_model=CaseReviewRunRead,
    status_code=status.HTTP_201_CREATED,
)
def create_case_review_run(
    case_id: UUID,
    payload: CaseReviewRunCreate,
    database: Session = Depends(get_database_session),
) -> CaseReviewRunRecord:
    case = database.get(CaseRecord, case_id)

    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found",
        )

    document_statement = select(
        ClinicalDocumentRecord.id
    ).where(
        ClinicalDocumentRecord.case_id == case_id,
        ClinicalDocumentRecord.id.in_(
            payload.document_ids
        ),
    )

    found_document_ids = set(
        database.scalars(
            document_statement
        ).all()
    )

    if found_document_ids != set(payload.document_ids):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "One or more documents were not found "
                "for this case"
            ),
        )

    review_run_id = uuid4()

    review_run = CaseReviewRunRecord(
        id=review_run_id,
        case_id=case_id,
        status=ReviewRunStatus.queued.value,
        document_ids=payload.document_ids,
        temporal_workflow_id=(
            f"case-review-{review_run_id}"
        ),
    )

    try:
        database.add(review_run)
        database.commit()
    except IntegrityError as error:
        database.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Unable to create review run",
        ) from error

    database.refresh(review_run)
    return review_run


@router.post(
    "/{case_id}/review-runs/{review_run_id}/start",
    response_model=ReviewWorkflowCommandResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_case_review_run(
    case_id: UUID,
    review_run_id: UUID,
    database: Session = Depends(get_database_session),
    gateway: ReviewWorkflowGateway = Depends(
        get_review_workflow_gateway
    ),
) -> ReviewWorkflowCommandResponse:
    review_run = get_scoped_review_run(
        database,
        case_id=case_id,
        review_run_id=review_run_id,
    )

    if review_run.status in {
        ReviewRunStatus.completed.value,
        ReviewRunStatus.rejected.value,
        ReviewRunStatus.failed.value,
    }:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Review run is already terminal",
        )

    workflow_input = CaseReviewWorkflowInput(
        review_run_id=str(review_run.id),
        case_id=str(review_run.case_id),
        document_ids=[
            str(document_id)
            for document_id
            in review_run.document_ids
        ],
    )

    try:
        command_status = gateway.start_review(
            workflow_id=(
                review_run.temporal_workflow_id
            ),
            workflow_input=workflow_input,
        )
    except ReviewWorkflowGatewayError as error:
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail="Temporal service is unavailable",
        ) from error

    return ReviewWorkflowCommandResponse(
        review_run_id=review_run.id,
        temporal_workflow_id=(
            review_run.temporal_workflow_id
        ),
        command_status=command_status,
    )


@router.post(
    (
        "/{case_id}/review-runs/{review_run_id}"
        "/human-review"
    ),
    response_model=ReviewWorkflowCommandResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def submit_case_human_review(
    case_id: UUID,
    review_run_id: UUID,
    payload: HumanReviewRequest,
    database: Session = Depends(get_database_session),
    gateway: ReviewWorkflowGateway = Depends(
        get_review_workflow_gateway
    ),
) -> ReviewWorkflowCommandResponse:
    review_run = get_scoped_review_run(
        database,
        case_id=case_id,
        review_run_id=review_run_id,
    )

    if (
        review_run.status
        != ReviewRunStatus
        .awaiting_human_review
        .value
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Review run is not awaiting "
                "human review"
            ),
        )

    try:
        command_status = (
            gateway.submit_human_review(
                workflow_id=(
                    review_run.temporal_workflow_id
                ),
                review=HumanReviewUpdate(
                    decision=payload.decision.value,
                    notes=payload.notes,
                ),
            )
        )
    except ReviewWorkflowGatewayError as error:
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail="Temporal service is unavailable",
        ) from error

    return ReviewWorkflowCommandResponse(
        review_run_id=review_run.id,
        temporal_workflow_id=(
            review_run.temporal_workflow_id
        ),
        command_status=command_status,
    )


@router.get(
    "/{case_id}/review-runs",
    response_model=list[CaseReviewRunRead],
)
def list_case_review_runs(
    case_id: UUID,
    database: Session = Depends(get_database_session),
) -> list[CaseReviewRunRecord]:
    case = database.get(CaseRecord, case_id)

    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found",
        )

    statement = (
        select(CaseReviewRunRecord)
        .where(
            CaseReviewRunRecord.case_id == case_id
        )
        .order_by(
            CaseReviewRunRecord.created_at.desc(),
            CaseReviewRunRecord.id.desc(),
        )
    )

    return list(
        database.scalars(statement).all()
    )


@router.get(
    "/{case_id}/review-runs/{review_run_id}",
    response_model=CaseReviewRunRead,
)
def get_case_review_run(
    case_id: UUID,
    review_run_id: UUID,
    database: Session = Depends(get_database_session),
) -> CaseReviewRunRecord:
    return get_scoped_review_run(
        database,
        case_id=case_id,
        review_run_id=review_run_id,
    )