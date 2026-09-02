"""add nullable chunk_id to vector_chunks

Revision ID: 20260729_chunk_id
Revises: m3_unify_user_id_type
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260729_chunk_id"
down_revision: Union[str, Sequence[str], None] = "m3_unify_user_id_type"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("vector_chunks") as batch_op:
        batch_op.add_column(sa.Column("chunk_id", sa.String(length=256), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("vector_chunks") as batch_op:
        batch_op.drop_column("chunk_id")
