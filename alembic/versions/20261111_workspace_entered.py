"""Persist whether a session has entered the workspace.

Revision ID: 20261111_workspace_entered
Revises: 20261023_private_library
"""
import json

import sqlalchemy as sa

from alembic import op

revision = "20261111_workspace_entered"
down_revision = "20261023_private_library"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("sessions", sa.Column("workspace_entered", sa.Boolean(), nullable=False, server_default=sa.false()))
    connection = op.get_bind()
    rows = connection.execute(sa.text("""
        SELECT s.id, s.state_json, s.state_version, s.active_request_id, p.kind,
            EXISTS (SELECT 1 FROM session_view_states v WHERE v.session_id = s.id) AS has_view,
            EXISTS (SELECT 1 FROM chat_requests r WHERE r.session_id = s.id) AS has_request
        FROM sessions s LEFT JOIN topic_profiles p ON p.id = s.profile_id
    """)).mappings()
    entered = []
    for row in rows:
        try:
            state = json.loads(row['state_json'])
        except (TypeError, ValueError):
            state = None
        if (not isinstance(state, dict) or 'schema_version' in state or row['state_version'] != 0
                or row['active_request_id'] is not None or row['kind'] not in (None, 'legacy')
                or row['has_view'] or row['has_request']):
            entered.append({'session_id': row['id']})
    if entered:
        connection.execute(sa.text("UPDATE sessions SET workspace_entered = :entered WHERE id = :session_id"),
            [{'session_id': row['session_id'], 'entered': True} for row in entered])


def downgrade():
    op.drop_column("sessions", "workspace_entered")
