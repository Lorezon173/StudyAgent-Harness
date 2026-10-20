"""M3: unify user_id type across mastery tables

Revision ID: m3_unify_user_id_type
Revises: d50dd837b8e6
Create Date: 2026-07-03

将 MasteryNodeTable.user_id 和 MasteryEdgeTable.user_id 从 String(64) 改为 Integer + ForeignKey("users.id")，
与 SessionTable/KnowledgeTable/VectorChunkTable 保持一致。
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'm3_unify_user_id_type'
down_revision: str | None = 'd50dd837b8e6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 数据预检：确认现有 user_id 全部为纯数字（Python 侧检查，兼容 SQLite/PG）
    conn = op.get_bind()
    for table in ('mastery_nodes', 'mastery_edges'):
        rows = conn.execute(sa.text(f"SELECT user_id FROM {table}")).fetchall()
        for row in rows:
            val = str(row[0])
            if not val.isdigit():
                raise ValueError(
                    f"{table} 包含非数字 user_id='{val}'，请先清理数据再执行迁移"
                )

    # SQLite 不支持 ALTER COLUMN，需要用 batch_alter_table 重建表
    with op.batch_alter_table('mastery_nodes', schema=None) as batch_op:
        # 修改 user_id 类型：String(64) -> Integer
        batch_op.alter_column('user_id',
                              existing_type=sa.String(length=64),
                              type_=sa.Integer(),
                              existing_nullable=False,
                              postgresql_using='user_id::integer')

    # 添加外键约束（SQLite batch 模式下需要在 batch 外添加）
    with op.batch_alter_table('mastery_nodes', schema=None) as batch_op:
        batch_op.create_foreign_key('fk_mastery_nodes_user_id',
                                    'users', ['user_id'], ['id'])

    with op.batch_alter_table('mastery_edges', schema=None) as batch_op:
        # 修改 user_id 类型：String(64) -> Integer
        batch_op.alter_column('user_id',
                              existing_type=sa.String(length=64),
                              type_=sa.Integer(),
                              existing_nullable=False,
                              postgresql_using='user_id::integer')

    # 添加外键约束
    with op.batch_alter_table('mastery_edges', schema=None) as batch_op:
        batch_op.create_foreign_key('fk_mastery_edges_user_id',
                                    'users', ['user_id'], ['id'])


def downgrade() -> None:
    # 先删除外键约束
    with op.batch_alter_table('mastery_edges', schema=None) as batch_op:
        batch_op.drop_constraint('fk_mastery_edges_user_id', type_='foreignkey')

    with op.batch_alter_table('mastery_edges', schema=None) as batch_op:
        batch_op.alter_column('user_id',
                              existing_type=sa.Integer(),
                              type_=sa.String(length=64),
                              existing_nullable=False,
                              postgresql_using='user_id::varchar')

    with op.batch_alter_table('mastery_nodes', schema=None) as batch_op:
        batch_op.drop_constraint('fk_mastery_nodes_user_id', type_='foreignkey')

    with op.batch_alter_table('mastery_nodes', schema=None) as batch_op:
        batch_op.alter_column('user_id',
                              existing_type=sa.Integer(),
                              type_=sa.String(length=64),
                              existing_nullable=False,
                              postgresql_using='user_id::varchar')
