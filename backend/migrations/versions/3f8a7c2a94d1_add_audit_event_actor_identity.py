"""add audit event actor identity

Revision ID: 3f8a7c2a94d1
Revises: f4a1c9e73b26
Create Date: 2026-09-01 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3f8a7c2a94d1'
down_revision: Union[str, Sequence[str], None] = 'f4a1c9e73b26'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Persist the concrete actor behind reviewer audit events."""
    op.add_column(
        'audit_events',
        sa.Column('actor_id', sa.UUID(), nullable=True),
    )
    op.add_column(
        'audit_events',
        sa.Column('actor_label', sa.String(length=200), nullable=True),
    )
    op.create_foreign_key(
        'fk_audit_events_actor_id_reviewers',
        'audit_events',
        'reviewers',
        ['actor_id'],
        ['id'],
    )
    op.create_index(
        op.f('ix_audit_events_actor_id'),
        'audit_events',
        ['actor_id'],
        unique=False,
    )


def downgrade() -> None:
    """Remove actor identity from audit events."""
    op.drop_index(
        op.f('ix_audit_events_actor_id'),
        table_name='audit_events',
    )
    op.drop_constraint(
        'fk_audit_events_actor_id_reviewers',
        'audit_events',
        type_='foreignkey',
    )
    op.drop_column('audit_events', 'actor_label')
    op.drop_column('audit_events', 'actor_id')
