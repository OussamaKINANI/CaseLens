from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import (
    ARRAY,
    UUID as PostgreSQLUUID,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.review_schemas import ReviewRunStatus


class CaseReviewRunRecord(Base):
    __tablename__ = "case_review_runs"

    __table_args__ = (
        CheckConstraint(
            """
            status IN (
                'queued',
                'running',
                'awaiting_human_review',
                'completed',
                'rejected',
                'failed'
            )
            """,
            name="ck_case_review_runs_status",
        ),
        CheckConstraint(
            "cardinality(document_ids) BETWEEN 1 AND 50",
            name="ck_case_review_runs_document_count",
        ),
        UniqueConstraint(
            "temporal_workflow_id",
            name="uq_case_review_runs_temporal_workflow_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    case_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("cases.id"),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=ReviewRunStatus.queued.value,
        server_default=ReviewRunStatus.queued.value,
        index=True,
    )

    document_ids: Mapped[list[UUID]] = mapped_column(
        ARRAY(PostgreSQLUUID(as_uuid=True)),
        nullable=False,
    )

    temporal_workflow_id: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    failure_code: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )