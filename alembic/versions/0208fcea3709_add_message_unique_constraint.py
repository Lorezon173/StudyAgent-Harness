"""add_message_unique_constraint

Revision ID: 0208fcea3709
Revises: 20260623_ragas_recall
Create Date: 2026-06-28 20:11:10.253658

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '0208fcea3709'
down_revision: Union[str, Sequence[str], None] = '20260623_ragas_recall'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('messages') as batch_op:
        batch_op.create_unique_constraint('uq_message_turn', ['session_id', 'turn_index', 'role'])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('messages') as batch_op:
        batch_op.drop_constraint('uq_message_turn', type_='unique')
