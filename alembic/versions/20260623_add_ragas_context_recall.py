"""add ragas_context_recall column to evals

Revision ID: 20260623_ragas_recall
Revises: 20260622_vector_chunks
Create Date: 2026-06-23 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260623_ragas_recall'
down_revision: Union[str, Sequence[str], None] = '20260622_vector_chunks'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('evals', sa.Column('ragas_context_recall', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('evals', 'ragas_context_recall')
