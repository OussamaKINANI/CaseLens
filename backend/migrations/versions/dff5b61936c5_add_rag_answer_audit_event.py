"""add RAG answer audit event

Revision ID: dff5b61936c5
Revises: 0b152be2c8db
Create Date: 2026-08-19 17:21:21.664970

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dff5b61936c5'
down_revision: Union[str, Sequence[str], None] = '0b152be2c8db'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Allow auditing grounded RAG answers."""
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
            'document_indexed',
            'rag_answer_generated'
        )
        """,
    )


def downgrade() -> None:
    """Remove the grounded RAG answer audit type."""
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
