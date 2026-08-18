from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.database import get_database_session
from app.main import app
from app.models import CaseRecord

from app.audit_models import AuditEventRecord

from app.document_models import ClinicalDocumentRecord


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
        session.execute(delete(AuditEventRecord))
        session.execute(delete(ClinicalDocumentRecord))
        session.execute(delete(CaseRecord))
        session.commit()

@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    def override_database_session() -> Generator[Session, None, None]:
        with TestSessionLocal() as session:
            yield session

    clear_test_database()
    app.dependency_overrides[get_database_session] = (
        override_database_session
    )

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        clear_test_database()