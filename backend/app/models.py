from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.schemas import CasePriority, CaseStatus


class CaseRecord(Base):
    __tablename__ = "cases"

    __table_args__ = (
        CheckConstraint(
            "priority IN ('routine', 'urgent')",
            name="ck_cases_priority",
        ),
        CheckConstraint(
            """
            status IN (
                'received',
                'processing',
                'awaiting_review',
                'completed',
                'failed'
            )
            """,
            name="ck_cases_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    patient_external_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    requested_service: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    priority: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=CasePriority.routine.value,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=CaseStatus.received.value,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )