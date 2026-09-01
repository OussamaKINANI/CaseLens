from collections.abc import Generator
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session, sessionmaker

from app.answer_provider_factory import (
    get_answer_provider,
)
from app.answer_service import FakeAnswerProvider
from app.audit_models import AuditEventRecord
from app.auth_models import ReviewerRecord
from app.auth_schemas import ReviewerRole
from app.config import (
    get_rag_min_similarity,
    settings,
)
from app.database import get_database_session
from app.document_models import ClinicalDocumentRecord
from app.embedding_factory import get_embedding_provider
from app.embedding_service import FakeEmbeddingProvider
from app.extraction_models import (
    ClinicalExtractionRecord,
)
from app.extraction_provider_factory import (
    get_extraction_provider,
)
from app.extraction_service import (
    FakeExtractionProvider,
)
from app.main import app
from app.models import CaseRecord
from app.rag_models import DocumentChunkRecord
from app.review_models import CaseReviewRunRecord
from app.security import create_access_token, hash_password

test_engine = create_engine(
    settings.test_database_url,
    pool_pre_ping=True,
)

TestSessionLocal = sessionmaker(
    bind=test_engine,
    autoflush=False,
    expire_on_commit=False,
)

REVIEWER_ID = UUID("11111111-1111-4111-8111-111111111111")
REVIEWER_EMAIL = "reviewer@caselens.test"
REVIEWER_PASSWORD = "reviewer-test-password"

ADMINISTRATOR_ID = UUID("22222222-2222-4222-8222-222222222222")
ADMINISTRATOR_EMAIL = "administrator@caselens.test"
ADMINISTRATOR_PASSWORD = "administrator-test-password"

# Password hashing is deliberately slow, so the two fixture accounts
# are hashed once per test session rather than once per test.
REVIEWER_PASSWORD_HASH = hash_password(REVIEWER_PASSWORD)
ADMINISTRATOR_PASSWORD_HASH = hash_password(ADMINISTRATOR_PASSWORD)


def clear_test_database() -> None:
    with TestSessionLocal() as session:
        session.execute(delete(CaseReviewRunRecord))
        session.execute(delete(ClinicalExtractionRecord))
        session.execute(delete(DocumentChunkRecord))
        session.execute(delete(AuditEventRecord))
        session.execute(delete(ClinicalDocumentRecord))
        session.execute(delete(CaseRecord))
        session.execute(delete(ReviewerRecord))
        session.commit()


def seed_test_reviewers() -> None:
    with TestSessionLocal() as session:
        session.add(
            ReviewerRecord(
                id=REVIEWER_ID,
                email=REVIEWER_EMAIL,
                full_name="Test Reviewer",
                password_hash=REVIEWER_PASSWORD_HASH,
                role=ReviewerRole.reviewer.value,
                is_active=True,
            )
        )

        session.add(
            ReviewerRecord(
                id=ADMINISTRATOR_ID,
                email=ADMINISTRATOR_EMAIL,
                full_name="Test Administrator",
                password_hash=ADMINISTRATOR_PASSWORD_HASH,
                role=ReviewerRole.administrator.value,
                is_active=True,
            )
        )

        session.commit()


def build_access_token(
    reviewer_id: UUID,
    role: ReviewerRole,
) -> str:
    token, _ = create_access_token(
        reviewer_id=reviewer_id,
        role=role,
    )

    return token


def authenticated_client(
    application: FastAPI,
    reviewer_id: UUID,
    role: ReviewerRole,
) -> TestClient:
    return TestClient(
        application,
        headers={
            "Authorization": (
                f"Bearer {build_access_token(reviewer_id, role)}"
            ),
        },
    )


@pytest.fixture
def database_session() -> Generator[Session, None, None]:
    """Direct database access for tests that set up fixture rows."""
    with TestSessionLocal() as session:
        yield session


@pytest.fixture
def configured_app() -> Generator[FastAPI, None, None]:
    def override_database_session(
    ) -> Generator[Session, None, None]:
        with TestSessionLocal() as session:
            yield session

    clear_test_database()
    seed_test_reviewers()

    app.dependency_overrides[
        get_database_session
    ] = override_database_session

    app.dependency_overrides[
        get_embedding_provider
    ] = lambda: FakeEmbeddingProvider(
        dimensions=1536
    )

    app.dependency_overrides[
        get_extraction_provider
    ] = lambda: FakeExtractionProvider()

    app.dependency_overrides[
        get_answer_provider
    ] = lambda: FakeAnswerProvider()

    app.dependency_overrides[
        get_rag_min_similarity
    ] = lambda: 0.0

    try:
        yield app
    finally:
        app.dependency_overrides.clear()
        clear_test_database()


@pytest.fixture
def client(
    configured_app: FastAPI,
) -> Generator[TestClient, None, None]:
    # Most tests exercise clinical behaviour rather than access
    # control, so the default client is signed in as an
    # administrator: the role allowed to reach every endpoint.
    with authenticated_client(
        configured_app,
        ADMINISTRATOR_ID,
        ReviewerRole.administrator,
    ) as test_client:
        yield test_client


@pytest.fixture
def reviewer_client(
    configured_app: FastAPI,
) -> Generator[TestClient, None, None]:
    with authenticated_client(
        configured_app,
        REVIEWER_ID,
        ReviewerRole.reviewer,
    ) as test_client:
        yield test_client


@pytest.fixture
def anonymous_client(
    configured_app: FastAPI,
) -> Generator[TestClient, None, None]:
    with TestClient(configured_app) as test_client:
        yield test_client
