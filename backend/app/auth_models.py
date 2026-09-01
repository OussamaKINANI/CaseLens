from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    String,
    UniqueConstraint,
    func,
    true,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.auth_schemas import ReviewerRole
from app.database import Base


class ReviewerRecord(Base):
    __tablename__ = "reviewers"

    __table_args__ = (
        CheckConstraint(
            "role IN ('reviewer', 'administrator')",
            name="ck_reviewers_role",
        ),
        UniqueConstraint(
            "email",
            name="uq_reviewers_email",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    # Stored lower-cased so sign-in is case-insensitive while the
    # unique constraint stays a plain equality check.
    email: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        index=True,
    )

    full_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    # Never a raw password: see app.security.hash_password.
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ReviewerRole.reviewer.value,
        server_default=ReviewerRole.reviewer.value,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
