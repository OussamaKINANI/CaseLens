from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session, sessionmaker

from app.answer_provider_factory import (
    get_answer_provider,
)
from app.answer_service import FakeAnswerProvider
from app.audit_models import AuditEventRecord
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

test_engine = create_engine(
    settings.test_database_url,
    pool_pre_ping=True,
)

TestSessionLocal = sessionmaker(
    bind=test_engine,
    autoflush=False,
    expire_on_commit=False,
)


def clear_test_database() -> None:
    with TestSessionLocal() as session:
        session.execute(delete(CaseReviewRunRecord))
        session.execute(delete(ClinicalExtractionRecord))
        session.execute(delete(DocumentChunkRecord))
        session.execute(delete(AuditEventRecord))
        session.execute(delete(ClinicalDocumentRecord))
        session.execute(delete(CaseRecord))
        session.commit()

@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    def override_database_session(
    ) -> Generator[Session, None, None]:
        with TestSessionLocal() as session:
            yield session

    clear_test_database()

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
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        clear_test_database()