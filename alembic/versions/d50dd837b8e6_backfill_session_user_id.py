"""backfill_session_user_id

Revision ID: d50dd837b8e6
Revises: 0208fcea3709
Create Date: 2026-07-02 18:16:01.827214

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd50dd837b8e6'
down_revision: Union[str, Sequence[str], None] = '0208fcea3709'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Backfill historical sessions with user_id=1 (dev environment)."""
    # 历史会话（user_id=NULL）分配给第一个用户（user_id=1）
    # 假设 dev 环境有 user_id=1 的测试用户
    op.execute("UPDATE sessions SET user_id = 1 WHERE user_id IS NULL")


def downgrade() -> None:
    """Revert backfill (no-op: cannot distinguish original user_id=1 from backfilled)."""
    # 无法区分"原本就是 user_id=1"和"回填的 user_id=1"，不做回退
    # dev 环境可接受，prod 环境应备份数据后再跑 upgrade
    pass
