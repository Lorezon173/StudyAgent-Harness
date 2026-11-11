"""私有手动文本知识卡；旧 knowledge 与向量资产保留。

Revision ID: 20261023_private_library
Revises: 20261023_session_workspace_state
"""
import sqlalchemy as sa

from alembic import op

revision = "20261023_private_library"
down_revision = "20261023_session_workspace_state"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "library_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("profile_id", sa.String(36), nullable=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("content_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("source_type", sa.String(16), nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id", "profile_id"], ["topic_profiles.user_id", "topic_profiles.id"], name="fk_library_profile_owner"),
    )
    op.create_index("ix_library_owner_id", "library_items", ["user_id", "id"])
    op.create_index("ix_library_owner_profile_id", "library_items", ["user_id", "profile_id", "id"])


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT COUNT(*) FROM library_items")):
        raise RuntimeError("library data exists; export and explicitly remove data before downgrade")
    op.drop_table("library_items")
