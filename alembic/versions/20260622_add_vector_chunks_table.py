"""add vector_chunks table for semantic search

Revision ID: 20260622_vector_chunks
Revises: d48d7137f57f
Create Date: 2026-06-22 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260622_vector_chunks'
down_revision: Union[str, Sequence[str], None] = 'd48d7137f57f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: create vector_chunks table with dialect-specific embedding column."""
    conn = op.get_bind()
    dialect = conn.dialect.name

    # PostgreSQL: 确保 pgvector 扩展存在
    if dialect == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # 创建 vector_chunks 表，embedding 列根据 dialect 选择类型
    if dialect == "postgresql":
        # PostgreSQL: 使用 pgvector 的 vector(1536) 类型
        op.execute("""
            CREATE TABLE vector_chunks (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                scope VARCHAR(16) NOT NULL DEFAULT 'global',
                content TEXT NOT NULL,
                embedding vector(1536),
                source VARCHAR(16) NOT NULL DEFAULT 'vector',
                doc_id VARCHAR(256) DEFAULT '',
                metadata_json JSON DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        op.create_index('ix_vector_chunks_scope', 'vector_chunks', ['scope'])
    else:
        # SQLite/其他: embedding 退化为 TEXT（存储 JSON）
        op.create_table(
            'vector_chunks',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=True),
            sa.Column('scope', sa.String(length=16), nullable=False, server_default='global'),
            sa.Column('content', sa.Text(), nullable=False),
            sa.Column('embedding', sa.Text(), nullable=True),  # JSON string in sqlite
            sa.Column('source', sa.String(length=16), nullable=False, server_default='vector'),
            sa.Column('doc_id', sa.String(length=256), server_default=''),
            sa.Column('metadata_json', sa.JSON(), server_default='{}'),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)')),
            sa.ForeignKeyConstraint(['user_id'], ['users.id']),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index('ix_vector_chunks_scope', 'vector_chunks', ['scope'], unique=False)


def downgrade() -> None:
    """Downgrade schema: drop vector_chunks table."""
    op.drop_index('ix_vector_chunks_scope', table_name='vector_chunks')
    op.drop_table('vector_chunks')
