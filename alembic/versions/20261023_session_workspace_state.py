"""会话、请求、证据与独立界面版本；保留全部历史消息。

Revision ID: 20261023_session_workspace_state
Revises: 20261023_topic_profiles
"""
import json
from uuid import NAMESPACE_URL, uuid5

from alembic import op
import sqlalchemy as sa

revision = "20261023_session_workspace_state"
down_revision = "20261023_topic_profiles"
branch_labels = None
depends_on = None


def _begin_sqlite_rebuild(connection):
    if connection.dialect.name != "sqlite":
        return
    # sqlite3 legacy transaction mode does not BEGIN for DDL. Never commit an
    # existing caller transaction: establish a real transaction only if absent.
    if not connection.connection.driver_connection.in_transaction:
        connection.exec_driver_sql("BEGIN")
    if connection.scalar(sa.text("PRAGMA foreign_keys")) != 1:
        raise RuntimeError("workspace migration requires SQLite foreign_keys=ON")
    connection.exec_driver_sql("PRAGMA defer_foreign_keys=ON")


def _finish_sqlite_rebuild(connection):
    if connection.dialect.name == "sqlite":
        violations = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(f"foreign key violations after workspace rebuild: {violations}")
        # Recreated parents satisfy every real FK. SQLite retains the removed
        # parent's deferred counter, so clear it only after a full integrity check.
        connection.exec_driver_sql("PRAGMA defer_foreign_keys=OFF")


def _bind_legacy_sessions(connection):
    metadata = sa.MetaData()
    metadata.reflect(connection, only=["users", "sessions", "messages", "topic_profiles"])
    users, sessions, messages, profiles = (metadata.tables[n] for n in ("users", "sessions", "messages", "topic_profiles"))
    owners = connection.execute(sa.select(sessions.c.user_id).join(users, users.c.id == sessions.c.user_id).distinct()).scalars().all()
    for owner in owners:
        profile_id = connection.scalar(sa.select(profiles.c.id).where(profiles.c.user_id == owner, profiles.c.kind == "legacy"))
        if profile_id is None:
            profile_id = str(uuid5(NAMESPACE_URL, f"studyagent:legacy-profile:{owner}"))
            connection.execute(profiles.insert().values(id=profile_id, user_id=owner, name="历史待整理", kind="legacy"))
        connection.execute(sessions.update().where(sessions.c.user_id == owner, sessions.c.profile_id.is_(None)).values(profile_id=profile_id))
    for session_id, maximum in connection.execute(sa.select(messages.c.session_id, sa.func.max(messages.c.turn_index)).group_by(messages.c.session_id)):
        connection.execute(sessions.update().where(sessions.c.id == session_id).values(next_turn_index=max(0, maximum + 1)))


def upgrade():
    connection = op.get_bind()
    _begin_sqlite_rebuild(connection)
    for column in (
        sa.Column("profile_id", sa.String(36), nullable=True),
        sa.Column("active_node_id", sa.String(36), nullable=True),
        sa.Column("state_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_turn_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active_request_id", sa.String(64), nullable=True),
    ):
        op.add_column("sessions", column)
    # The request table is created before the session active-request FK; temporary
    # candidate indexes make its session FK valid throughout SQLite's rebuild.
    sqlite = connection.dialect.name == "sqlite"
    if sqlite:
        op.create_index("_workspace_session_owner", "sessions", ["user_id", "id"], unique=True)
        op.create_index("_workspace_session_profile", "sessions", ["user_id", "id", "profile_id"], unique=True)
    else:
        op.create_unique_constraint("uq_session_owner", "sessions", ["user_id", "id"])
        op.create_unique_constraint("uq_session_profile_owner", "sessions", ["user_id", "id", "profile_id"])
    op.create_table(
        "chat_requests",
        sa.Column("user_id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.String(64), primary_key=True),
        sa.Column("request_id", sa.String(64), primary_key=True),
        sa.Column("profile_id", sa.String(36), nullable=False),
        sa.Column("active_node_id", sa.String(36), nullable=True),
        sa.Column("payload_hash", sa.String(128), nullable=False),
        sa.Column("request_payload", sa.JSON(), nullable=False),
        sa.Column("base_state_version", sa.Integer(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("lease_until", sa.DateTime(), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("response_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "session_id", "request_id", "profile_id", name="uq_request_profile_scope"),
        sa.ForeignKeyConstraint(["user_id", "session_id", "profile_id"], ["sessions.user_id", "sessions.id", "sessions.profile_id"], name="fk_request_session_scope"),
        sa.ForeignKeyConstraint(["profile_id", "active_node_id"], ["profile_nodes.profile_id", "profile_nodes.id"], name="fk_request_node_scope"),
        sa.CheckConstraint("status IN ('running', 'completed', 'failed', 'interrupted')", name="ck_request_status"),
        sa.CheckConstraint("attempt >= 1 AND base_state_version >= 0", name="ck_request_versions"),
        sa.CheckConstraint("status != 'running' OR lease_until IS NOT NULL", name="ck_request_running_lease"),
    )
    with op.batch_alter_table("sessions") as batch:
        if sqlite:
            batch.create_unique_constraint("uq_session_owner", ["user_id", "id"])
            batch.create_unique_constraint("uq_session_profile_owner", ["user_id", "id", "profile_id"])
        batch.create_foreign_key("fk_session_profile_owner", "topic_profiles", ["user_id", "profile_id"], ["user_id", "id"])
        batch.create_foreign_key("fk_session_active_node", "profile_nodes", ["profile_id", "active_node_id"], ["profile_id", "id"])
        batch.create_foreign_key("fk_session_active_request", "chat_requests", ["user_id", "id", "active_request_id"], ["user_id", "session_id", "request_id"])
        batch.create_check_constraint("ck_session_profile_owner", "profile_id IS NULL OR user_id IS NOT NULL")
        batch.create_check_constraint("ck_session_node_profile", "active_node_id IS NULL OR profile_id IS NOT NULL")
        batch.create_check_constraint("ck_session_request_owner", "active_request_id IS NULL OR user_id IS NOT NULL")
        batch.create_check_constraint("ck_session_versions", "state_version >= 0 AND next_turn_index >= 0")
    if sqlite:
        op.drop_index("_workspace_session_owner", table_name="sessions")
        op.drop_index("_workspace_session_profile", table_name="sessions")
    with op.batch_alter_table("messages") as batch:
        batch.create_unique_constraint("uq_message_session_id", ["session_id", "id"])
    _bind_legacy_sessions(connection)
    op.create_table(
        "profile_evidence",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.String(36), nullable=False),
        sa.Column("node_id", sa.String(36), nullable=False),
        sa.Column("session_id", sa.String(64), nullable=False),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "session_id", "request_id", "node_id", name="uq_profile_evidence_request_node"),
        sa.ForeignKeyConstraint(["user_id", "session_id", "request_id", "profile_id"], ["chat_requests.user_id", "chat_requests.session_id", "chat_requests.request_id", "chat_requests.profile_id"], name="fk_evidence_request_scope"),
        sa.ForeignKeyConstraint(["profile_id", "node_id"], ["profile_nodes.profile_id", "profile_nodes.id"], name="fk_evidence_node_scope"),
        sa.ForeignKeyConstraint(["session_id", "message_id"], ["messages.session_id", "messages.id"], name="fk_evidence_message_scope"),
    )
    op.create_table(
        "session_view_states",
        sa.Column("user_id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.String(64), primary_key=True),
        sa.Column("draft", sa.Text(), nullable=False, server_default=""),
        sa.Column("reading_anchor", sa.JSON(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id", "session_id"], ["sessions.user_id", "sessions.id"], name="fk_session_view_owner"),
        sa.CheckConstraint("version >= 0", name="ck_session_view_version"),
    )
    op.create_table(
        "user_workspace_states",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("last_session_id", sa.String(64), nullable=True),
        sa.Column("sidebar_pinned", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sidebar_collapsed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("progress_y_ratio", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id", "last_session_id"], ["sessions.user_id", "sessions.id"], name="fk_workspace_last_session_owner"),
        sa.CheckConstraint("progress_y_ratio >= 0 AND progress_y_ratio <= 1", name="ck_workspace_progress_ratio"),
        sa.CheckConstraint("version >= 0", name="ck_workspace_version"),
    )
    _finish_sqlite_rebuild(connection)


def downgrade():
    connection = op.get_bind()
    for table in ("profile_evidence", "chat_requests", "session_view_states", "user_workspace_states"):
        if connection.scalar(sa.text(f"SELECT COUNT(*) FROM {table}")):
            raise RuntimeError("workspace data exists; export and explicitly remove data before downgrade")
    if connection.scalar(sa.text("SELECT COUNT(*) FROM sessions WHERE profile_id IS NOT NULL OR active_node_id IS NOT NULL OR active_request_id IS NOT NULL OR state_version != 0")):
        raise RuntimeError("workspace session data exists; export before downgrade")
    for state in connection.execute(sa.text("SELECT state_json FROM sessions")).scalars():
        try:
            has_schema = "schema_version" in json.loads(state)
        except (TypeError, ValueError):
            has_schema = False
        if has_schema:
            raise RuntimeError("versioned teaching state data exists; export before downgrade")
    _begin_sqlite_rebuild(connection)
    op.drop_table("profile_evidence")
    op.drop_table("session_view_states")
    op.drop_table("user_workspace_states")
    with op.batch_alter_table("sessions") as batch:
        batch.drop_constraint("fk_session_active_request", type_="foreignkey")
    op.drop_table("chat_requests")
    with op.batch_alter_table("messages") as batch:
        batch.drop_constraint("uq_message_session_id", type_="unique")
    with op.batch_alter_table("sessions") as batch:
        for name in ("fk_session_profile_owner", "fk_session_active_node"):
            batch.drop_constraint(name, type_="foreignkey")
        for name in ("ck_session_profile_owner", "ck_session_node_profile", "ck_session_request_owner", "ck_session_versions"):
            batch.drop_constraint(name, type_="check")
        for name in ("uq_session_owner", "uq_session_profile_owner"):
            batch.drop_constraint(name, type_="unique")
        for name in ("active_request_id", "next_turn_index", "state_version", "active_node_id", "profile_id"):
            batch.drop_column(name)
    _finish_sqlite_rebuild(connection)
