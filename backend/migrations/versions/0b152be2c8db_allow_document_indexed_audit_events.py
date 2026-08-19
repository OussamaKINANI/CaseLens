"""allow document indexed audit events

Revision ID: 0b152be2c8db
Revises: d2dc75257440
Create Date: 2026-08-19 15:32:47.892992

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0b152be2c8db'
down_revision: Union[str, Sequence[str], None] = 'd2dc75257440'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Allow document indexing audit events."""
    op.drop_constraint(
        "ck_audit_events_event_type",
        "audit_events",
        type_="check",
    )

    op.create_check_constraint(
        "ck_audit_events_event_type",
        "audit_events",
        """
        event_type IN (
            'case_created',
            'status_changed',
            'ai_review_started',
            'ai_review_completed',
            'human_review_completed',
            'processing_failed',
            'document_uploaded',
            'document_indexed'
        )
        """,
    )


def downgrade() -> None:
    """Restore the previous audit event types."""
    op.drop_constraint(
        "ck_audit_events_event_type",
        "audit_events",
        type_="check",
    )

    op.create_check_constraint(
        "ck_audit_events_event_type",
        "audit_events",
        """
        event_type IN (
            'case_created',
            'status_changed',
            'ai_review_started',
            'ai_review_completed',
            'human_review_completed',
            'processing_failed',
            'document_uploaded'
        )
        """,
    )