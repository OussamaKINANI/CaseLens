"""enable pgvector extension

Revision ID: 9996410307a3
Revises: bce1889409c0
Create Date: 2026-08-18 22:29:01.046594

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9996410307a3'
down_revision: Union[str, Sequence[str], None] = 'bce1889409c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    """Enable vector storage and similarity search."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    """Disable vector storage and similarity search."""
    op.execute("DROP EXTENSION IF EXISTS vector")