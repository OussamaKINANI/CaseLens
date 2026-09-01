from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth_models import ReviewerRecord
from app.auth_schemas import ReviewerRole
from app.security import create_access_token
from tests.conftest import (
    ADMINISTRATOR_EMAIL,
    ADMINISTRATOR_ID,
    ADMINISTRATOR_PASSWORD,
    REVIEWER_EMAIL,
    REVIEWER_ID,
    REVIEWER_PASSWORD,
)


def test_login_returns_a_usable_access_token(
    anonymous_client: TestClient,
) -> None:
    response = anonymous_client.post(
        "/v1/auth/login",
        json={
            "email": REVIEWER_EMAIL,
            "password": REVIEWER_PASSWORD,
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["token_type"] == "bearer"
    assert body["expires_in_seconds"] > 0
    assert body["reviewer"]["email"] == REVIEWER_EMAIL
    assert body["reviewer"]["role"] == "reviewer"
    assert body["reviewer"]["id"] == str(REVIEWER_ID)
    assert "password" not in body["reviewer"]
    assert "password_hash" not in body["reviewer"]

    identity = anonymous_client.get(
        "/v1/auth/me",
        headers={
            "Authorization": f"Bearer {body['access_token']}",
        },
    )

    assert identity.status_code == 200
    assert identity.json()["id"] == str(REVIEWER_ID)


def test_login_email_is_case_and_whitespace_insensitive(
    anonymous_client: TestClient,
) -> None:
    response = anonymous_client.post(
        "/v1/auth/login",
        json={
            "email": f"  {ADMINISTRATOR_EMAIL.upper()}  ",
            "password": ADMINISTRATOR_PASSWORD,
        },
    )

    assert response.status_code == 200
    assert response.json()["reviewer"]["id"] == str(
        ADMINISTRATOR_ID
    )


def test_login_rejects_a_wrong_password(
    anonymous_client: TestClient,
) -> None:
    response = anonymous_client.post(
        "/v1/auth/login",
        json={
            "email": REVIEWER_EMAIL,
            "password": "not-the-password",
        },
    )

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Invalid email or password",
    }


def test_login_does_not_reveal_unknown_reviewers(
    anonymous_client: TestClient,
) -> None:
    response = anonymous_client.post(
        "/v1/auth/login",
        json={
            "email": "stranger@caselens.test",
            "password": REVIEWER_PASSWORD,
        },
    )

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Invalid email or password",
    }


def test_login_rejects_a_disabled_reviewer(
    anonymous_client: TestClient,
    database_session: Session,
) -> None:
    reviewer = database_session.get(ReviewerRecord, REVIEWER_ID)

    assert reviewer is not None

    reviewer.is_active = False
    database_session.commit()

    response = anonymous_client.post(
        "/v1/auth/login",
        json={
            "email": REVIEWER_EMAIL,
            "password": REVIEWER_PASSWORD,
        },
    )

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Invalid email or password",
    }


def test_login_rejects_unexpected_fields(
    anonymous_client: TestClient,
) -> None:
    response = anonymous_client.post(
        "/v1/auth/login",
        json={
            "email": REVIEWER_EMAIL,
            "password": REVIEWER_PASSWORD,
            "role": "administrator",
        },
    )

    assert response.status_code == 422


def test_current_reviewer_requires_a_token(
    anonymous_client: TestClient,
) -> None:
    response = anonymous_client.get("/v1/auth/me")

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}
    assert response.headers["www-authenticate"] == "Bearer"


def test_current_reviewer_rejects_a_malformed_token(
    anonymous_client: TestClient,
) -> None:
    response = anonymous_client.get(
        "/v1/auth/me",
        headers={"Authorization": "Bearer not-a-real-token"},
    )

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Invalid or expired access token",
    }


def test_token_for_an_unknown_reviewer_is_rejected(
    anonymous_client: TestClient,
) -> None:
    token, _ = create_access_token(
        reviewer_id=uuid4(),
        role=ReviewerRole.administrator,
    )

    response = anonymous_client.get(
        "/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Invalid or expired access token",
    }


def test_token_for_a_disabled_reviewer_is_rejected(
    anonymous_client: TestClient,
    database_session: Session,
) -> None:
    token, _ = create_access_token(
        reviewer_id=REVIEWER_ID,
        role=ReviewerRole.reviewer,
    )

    reviewer = database_session.get(ReviewerRecord, REVIEWER_ID)

    assert reviewer is not None

    reviewer.is_active = False
    database_session.commit()

    response = anonymous_client.get(
        "/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Reviewer account is disabled",
    }
