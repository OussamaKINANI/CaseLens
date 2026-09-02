from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.audit_schemas import AuditActorType, AuditEventType
from app.database import Base


class AuditEventRecord(Base):
    __tablename__ = "audit_events"

    __table_args__ = (
        CheckConstraint(
            """
            event_type IN (
                'case_created',
                'status_changed',
                'ai_review_started',
                'ai_review_completed',
                'human_review_completed',
                'processing_failed',
                'document_uploaded',
                'document_indexed',
                'rag_answer_generated'
            )
            """,
            name="ck_audit_events_event_type",
        ),
        CheckConstraint(
            "actor_type IN ('system', 'reviewer')",
            name="ck_audit_events_actor_type",
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

    event_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    actor_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=AuditActorType.system.value,
    )

    actor_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("reviewers.id"),
        nullable=True,
        index=True,
    )

    actor_label: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
