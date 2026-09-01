import re
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth_schemas import ReviewerRole
from app.security import create_access_token
from tests.conftest import (
    ADMINISTRATOR_ID,
    REVIEWER_ID,
    authenticated_client,
)


PATH_PARAMETER_PATTERN = re.compile(r"\{[^}]+\}")

# Routes that must stay reachable without a token: liveness and
# readiness probes for orchestrators, and sign-in itself.
PUBLIC_ROUTES: set[tuple[str, str]] = {
    ("GET", "/health"),
    ("GET", "/ready"),
    ("POST", "/v1/auth/login"),
}


def api_routes(application: FastAPI) -> list[tuple[str, str]]:
    """Every documented operation, as (method, path) pairs.

    Read from the OpenAPI schema rather than ``app.routes`` so that
    routes contributed by included routers are all covered.
    """
    schema = application.openapi()

    return [
        (method.upper(), path)
        for path, operations in schema["paths"].items()
        for method in operations
    ]


def concrete_path(path: str) -> str:
    return PATH_PARAMETER_PATTERN.sub(
        lambda _: str(uuid4()),
        path,
    )


def test_every_case_route_requires_authentication(
    configured_app: FastAPI,
    anonymous_client: TestClient,
) -> None:
    protected_routes = [
        route
        for route in api_routes(configured_app)
        if route not in PUBLIC_ROUTES
    ]

    # Guards against the sweep silently passing because the routes
    # were never collected.
    assert len(protected_routes) >= 15

    unprotected_routes: list[tuple[str, str]] = []

    for method, path in protected_routes:
        response = anonymous_client.request(
            method,
            concrete_path(path),
        )

        if response.status_code != 401:
            unprotected_routes.append((method, path))

    assert not unprotected_routes


def test_public_routes_do_not_require_authentication(
    anonymous_client: TestClient,
) -> None:
    assert anonymous_client.get("/health").status_code == 200
    assert anonymous_client.get("/ready").status_code == 200

    login_response = anonymous_client.post(
        "/v1/auth/login",
        json={
            "email": "stranger@caselens.test",
            "password": "irrelevant",
        },
    )

    # Reachable without a token, and still refuses bad credentials.
    assert login_response.status_code == 401


@pytest.mark.parametrize(
    "authorization",
    [
        "",
        "Bearer",
        "Basic cmV2aWV3ZXI6cGFzc3dvcmQ=",
        "Bearer ",
        "Bearer a.b.c",
    ],
)
def test_malformed_authorization_headers_are_rejected(
    anonymous_client: TestClient,
    authorization: str,
) -> None:
    response = anonymous_client.get(
        "/v1/cases",
        headers={"Authorization": authorization},
    )

    assert response.status_code == 401


def test_expired_token_cannot_read_cases(
    anonymous_client: TestClient,
) -> None:
    token, _ = create_access_token(
        reviewer_id=REVIEWER_ID,
        role=ReviewerRole.reviewer,
        expires_in_seconds=-1,
    )

    response = anonymous_client.get(
        "/v1/cases",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Invalid or expired access token",
    }


def test_reviewer_can_use_clinical_endpoints(
    reviewer_client: TestClient,
) -> None:
    created = reviewer_client.post(
        "/v1/cases",
        json={
            "patient_external_id": "SYNTH-AUTHZ-001",
            "requested_service": "Lumbar spine MRI",
        },
    )

    assert created.status_code == 201

    listed = reviewer_client.get("/v1/cases")

    assert listed.status_code == 200
    assert len(listed.json()) == 1


def test_reviewer_cannot_delete_a_case(
    reviewer_client: TestClient,
) -> None:
    created = reviewer_client.post(
        "/v1/cases",
        json={
            "patient_external_id": "SYNTH-AUTHZ-002",
            "requested_service": "Lumbar spine MRI",
        },
    ).json()

    response = reviewer_client.delete(
        f"/v1/cases/{created['id']}"
    )

    assert response.status_code == 403
    assert "administrator" in response.json()["detail"]

    still_present = reviewer_client.get(
        f"/v1/cases/{created['id']}"
    )

    assert still_present.status_code == 200


def test_administrator_can_delete_a_case(
    client: TestClient,
) -> None:
    created = client.post(
        "/v1/cases",
        json={
            "patient_external_id": "SYNTH-AUTHZ-003",
            "requested_service": "Lumbar spine MRI",
        },
    ).json()

    response = client.delete(f"/v1/cases/{created['id']}")

    assert response.status_code == 204


def test_stored_role_overrides_the_token_role_claim(
    configured_app: FastAPI,
    reviewer_client: TestClient,
) -> None:
    created = reviewer_client.post(
        "/v1/cases",
        json={
            "patient_external_id": "SYNTH-AUTHZ-004",
            "requested_service": "Lumbar spine MRI",
        },
    ).json()

    # A token minted for a reviewer, but claiming the administrator
    # role. Authorization must use the stored role, not the claim.
    with authenticated_client(
        configured_app,
        REVIEWER_ID,
        ReviewerRole.administrator,
    ) as escalated_client:
        response = escalated_client.delete(
            f"/v1/cases/{created['id']}"
        )

    assert response.status_code == 403


def test_reviewer_identity_comes_from_the_token(
    configured_app: FastAPI,
    reviewer_client: TestClient,
) -> None:
    reviewer_identity = reviewer_client.get("/v1/auth/me").json()

    with authenticated_client(
        configured_app,
        ADMINISTRATOR_ID,
        ReviewerRole.administrator,
    ) as administrator_client:
        administrator_identity = administrator_client.get(
            "/v1/auth/me"
        ).json()

    assert reviewer_identity["id"] == str(REVIEWER_ID)
    assert reviewer_identity["role"] == "reviewer"
    assert administrator_identity["id"] == str(ADMINISTRATOR_ID)
    assert administrator_identity["role"] == "administrator"
