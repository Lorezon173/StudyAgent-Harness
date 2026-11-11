"""用户所属主题画像与确定性历史图谱迁移。

Revision ID: 20261023_topic_profiles
Revises: 20260729_chunk_id
"""
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa

from alembic import op

revision = "20261023_topic_profiles"
down_revision = "20260729_chunk_id"
branch_labels = None
depends_on = None


def _legacy_rows(connection):
    metadata = sa.MetaData()
    metadata.reflect(connection, only=["users", "mastery_nodes", "mastery_edges"])
    users, nodes, edges = (metadata.tables[name] for name in ("users", "mastery_nodes", "mastery_edges"))
    node_rows = connection.execute(sa.select(nodes).join(users, nodes.c.user_id == users.c.id)).mappings().all()
    edge_rows = connection.execute(sa.select(edges).join(users, edges.c.user_id == users.c.id)).mappings().all()
    node_keys = {(row["user_id"], row["topic_id"]) for row in node_rows}
    valid_edges = [row for row in edge_rows
        if all((row["user_id"], row[field]) in node_keys for field in ("from_topic", "to_topic"))]
    return node_rows, valid_edges


def _migrate_legacy_graphs(connection):
    """重复前置检查时只补缺失记录，不覆盖已迁移后修改的画像。"""
    node_rows, edge_rows = _legacy_rows(connection)
    metadata = sa.MetaData()
    metadata.reflect(connection, only=["topic_profiles", "profile_nodes", "profile_edges"])
    profiles, nodes, edges = (metadata.tables[name] for name in ("topic_profiles", "profile_nodes", "profile_edges"))
    profile_ids = {}
    for user_id in sorted({row["user_id"] for row in node_rows}):
        existing = connection.scalar(sa.select(profiles.c.id).where(profiles.c.user_id == user_id, profiles.c.kind == "legacy"))
        profile_id = existing or str(uuid5(NAMESPACE_URL, f"studyagent:legacy-profile:{user_id}"))
        if existing is None:
            connection.execute(profiles.insert().values(id=profile_id, user_id=user_id, name="历史待整理", kind="legacy"))
        profile_ids[user_id] = profile_id
    for row in node_rows:
        profile_id = profile_ids[row["user_id"]]
        node_id = str(uuid5(NAMESPACE_URL, f"studyagent:legacy-node:{row['user_id']}:{row['topic_id']}"))
        existing_profile = connection.scalar(sa.select(nodes.c.profile_id).where(nodes.c.id == node_id))
        if existing_profile is not None:
            if existing_profile != profile_id:
                raise ValueError("legacy node UUID belongs to another profile")
            continue
        connection.execute(nodes.insert().values(
            id=node_id, profile_id=profile_id, title=row["topic_name"], mastery=row["mastery"],
            last_practiced_at=row["last_practiced_at"], practice_count=row["practice_count"], rationale=row["rationale"],
        ))
    for row in edge_rows:
        profile_id = profile_ids[row["user_id"]]
        from_id = str(uuid5(NAMESPACE_URL, f"studyagent:legacy-node:{row['user_id']}:{row['from_topic']}"))
        to_id = str(uuid5(NAMESPACE_URL, f"studyagent:legacy-node:{row['user_id']}:{row['to_topic']}"))
        exists = connection.scalar(sa.select(edges.c.profile_id).where(
            edges.c.profile_id == profile_id, edges.c.from_node_id == from_id,
            edges.c.to_node_id == to_id, edges.c.type == row["type"]))
        if exists is None:
            connection.execute(edges.insert().values(
                profile_id=profile_id, from_node_id=from_id, to_node_id=to_id, type=row["type"],
                weight=row["weight"], confidence=row["confidence"], source=row["source"],
            ))


def upgrade():
    connection = op.get_bind()
    op.create_table(
        "topic_profiles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("scope_description", sa.Text(), nullable=False, server_default=""),
        sa.Column("kind", sa.String(16), nullable=False, server_default="normal"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "id", name="uq_topic_profile_owner"),
        sa.CheckConstraint("kind IN ('normal', 'legacy')", name="ck_topic_profile_kind"),
        sa.CheckConstraint("revision >= 0", name="ck_topic_profile_revision"),
    )
    op.create_index("ix_topic_profiles_user_id", "topic_profiles", ["user_id"])
    op.create_index("uq_topic_profile_legacy_owner", "topic_profiles", ["user_id"], unique=True,
                    sqlite_where=sa.text("kind = 'legacy'"), postgresql_where=sa.text("kind = 'legacy'"))
    op.create_table(
        "profile_nodes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("profile_id", sa.String(36), sa.ForeignKey("topic_profiles.id"), nullable=False),
        sa.Column("title", sa.String(512), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("mastery", sa.Float(), nullable=True),
        sa.Column("last_practiced_at", sa.Float(), nullable=False, server_default="0"),
        sa.Column("practice_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rationale", sa.Text(), nullable=False, server_default=""),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("profile_id", "id", name="uq_profile_node_scope"),
        sa.CheckConstraint("revision >= 0", name="ck_profile_node_revision"),
    )
    op.create_index("ix_profile_nodes_profile_id", "profile_nodes", ["profile_id"])
    op.create_table(
        "profile_edges",
        sa.Column("profile_id", sa.String(36), sa.ForeignKey("topic_profiles.id"), primary_key=True),
        sa.Column("from_node_id", sa.String(36), primary_key=True),
        sa.Column("to_node_id", sa.String(36), primary_key=True),
        sa.Column("type", sa.String(16), primary_key=True, server_default="PREREQ"),
        sa.Column("weight", sa.Float(), nullable=False, server_default="1"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("source", sa.String(16), nullable=False, server_default="LLM_INFER"),
        sa.ForeignKeyConstraint(["profile_id", "from_node_id"], ["profile_nodes.profile_id", "profile_nodes.id"], name="fk_profile_edge_from_node"),
        sa.ForeignKeyConstraint(["profile_id", "to_node_id"], ["profile_nodes.profile_id", "profile_nodes.id"], name="fk_profile_edge_to_node"),
    )
    _migrate_legacy_graphs(connection)


def downgrade():
    connection = op.get_bind()
    for name in ("profile_edges", "profile_nodes", "topic_profiles"):
        if connection.scalar(sa.text(f"SELECT COUNT(*) FROM {name}")):
            raise RuntimeError("workspace profile data exists; export and explicitly remove data before downgrade")
    op.drop_table("profile_edges")
    op.drop_index("ix_profile_nodes_profile_id", table_name="profile_nodes")
    op.drop_table("profile_nodes")
    op.drop_index("uq_topic_profile_legacy_owner", table_name="topic_profiles")
    op.drop_index("ix_topic_profiles_user_id", table_name="topic_profiles")
    op.drop_table("topic_profiles")
