from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_reviewer, unauthenticated_error
from app.auth_models import ReviewerRecord
from app.auth_schemas import (
    AccessTokenResponse,
    LoginRequest,
    ReviewerRead,
    ReviewerRole,
)
from app.database import get_database_session
from app.security import (
    create_access_token,
    spend_password_verification_time,
    verify_password,
)


router = APIRouter(
    prefix="/v1/auth",
    tags=["authentication"],
)


# Deliberately identical for an unknown email, a wrong password, and
# a disabled account: sign-in must not reveal which reviewers exist.
INVALID_CREDENTIALS_DETAIL = "Invalid email or password"


@router.post(
    "/login",
    response_model=AccessTokenResponse,
)
def login(
    payload: LoginRequest,
    database: Session = Depends(get_database_session),
) -> AccessTokenResponse:
    statement = select(ReviewerRecord).where(
        ReviewerRecord.email == payload.email,
    )

    reviewer = database.scalar(statement)

    if reviewer is None:
        spend_password_verification_time()

        raise unauthenticated_error(INVALID_CREDENTIALS_DETAIL)

    password_matches = verify_password(
        payload.password,
        reviewer.password_hash,
    )

    if not password_matches or not reviewer.is_active:
        raise unauthenticated_error(INVALID_CREDENTIALS_DETAIL)

    token, expires_in_seconds = create_access_token(
        reviewer_id=reviewer.id,
        role=ReviewerRole(reviewer.role),
    )

    return AccessTokenResponse(
        access_token=token,
        expires_in_seconds=expires_in_seconds,
        reviewer=ReviewerRead.model_validate(reviewer),
    )


@router.get(
    "/me",
    response_model=ReviewerRead,
)
def read_current_reviewer(
    reviewer: ReviewerRecord = Depends(get_current_reviewer),
) -> ReviewerRecord:
    return reviewer
