from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)
from sqlalchemy.orm import Session

from app.auth_models import ReviewerRecord
from app.auth_schemas import ReviewerRole
from app.database import get_database_session
from app.security import (
    InvalidAccessTokenError,
    decode_access_token,
)


# auto_error is disabled so a missing header produces the same
# 401 shape as an invalid one, instead of Starlette's 403.
bearer_scheme = HTTPBearer(
    scheme_name="Reviewer access token",
    auto_error=False,
)


def unauthenticated_error(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_reviewer(
    credentials: HTTPAuthorizationCredentials | None = Depends(
        bearer_scheme
    ),
    database: Session = Depends(get_database_session),
) -> ReviewerRecord:
    if credentials is None:
        raise unauthenticated_error(
            "Not authenticated",
        )

    try:
        claims = decode_access_token(credentials.credentials)
    except InvalidAccessTokenError as error:
        raise unauthenticated_error(
            "Invalid or expired access token",
        ) from error

    reviewer = database.get(
        ReviewerRecord,
        claims.reviewer_id,
    )

    if reviewer is None:
        raise unauthenticated_error(
            "Invalid or expired access token",
        )

    if not reviewer.is_active:
        raise unauthenticated_error(
            "Reviewer account is disabled",
        )

    return reviewer


def require_roles(
    *allowed_roles: ReviewerRole,
) -> Callable[..., ReviewerRecord]:
    """Build a dependency that also enforces a reviewer role.

    The stored role is authoritative. A token minted before a role
    change cannot keep using the permissions it was issued with.
    """
    allowed_role_values = {role.value for role in allowed_roles}

    def dependency(
        reviewer: ReviewerRecord = Depends(get_current_reviewer),
    ) -> ReviewerRecord:
        if reviewer.role not in allowed_role_values:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "This action requires one of the following "
                    "roles: "
                    + ", ".join(sorted(allowed_role_values))
                ),
            )

        return reviewer

    return dependency


require_administrator = require_roles(
    ReviewerRole.administrator,
)
