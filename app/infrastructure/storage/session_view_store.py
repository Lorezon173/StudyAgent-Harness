"""按会话保存界面草稿；界面版本独立于教学快照版本。"""
from sqlalchemy import select, update

from app.infrastructure.storage.chat_request_store import (
    WorkspaceConflict,
    serializable,
)
from app.models.tables import SessionTable
from app.models.workspace_tables import SessionViewStateTable


class SessionViewStore:
    def __init__(self, db):
        self.db = db

    async def _owned(self, user_id, session_id):
        row = await self.db.scalar(select(SessionTable).where(
            SessionTable.id == session_id, SessionTable.user_id == user_id,
        ).with_for_update())
        if row is None or row.user_id is None:
            raise PermissionError("session is not owned")

    async def get(self, user_id, session_id):
        await self._owned(user_id, session_id)
        return await self.db.get(SessionViewStateTable, (user_id, session_id), populate_existing=True)

    async def save(self, user_id, session_id, expected_version, state):
        await self._owned(user_id, session_id)
        state = serializable(state)
        if not isinstance(state, dict) or set(state) - {"draft", "reading_anchor"}:
            raise ValueError("invalid view state")
        if "draft" in state and not isinstance(state["draft"], str):
            raise ValueError("draft must be text")
        row = await self.db.get(SessionViewStateTable, (user_id, session_id), populate_existing=True)
        if row is None:
            if expected_version != 0:
                raise WorkspaceConflict("view_version_conflict")
            row = SessionViewStateTable(user_id=user_id, session_id=session_id, version=1, **state)
            self.db.add(row)
        else:
            result = await self.db.execute(update(SessionViewStateTable).where(
                SessionViewStateTable.user_id == user_id, SessionViewStateTable.session_id == session_id,
                SessionViewStateTable.version == expected_version,
            ).values(**state, version=expected_version + 1).execution_options(synchronize_session=False))
            if result.rowcount != 1:
                raise WorkspaceConflict("view_version_conflict")
            await self.db.refresh(row)
        await self.db.flush()
        return row
