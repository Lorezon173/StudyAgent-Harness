"""用户工作区偏好及乐观版本。"""
import math

from sqlalchemy import select, update

from app.infrastructure.storage.chat_request_store import (
    WorkspaceConflict,
    serializable,
)
from app.models.tables import SessionTable, UserTable
from app.models.workspace_tables import UserWorkspaceStateTable


class WorkspaceStore:
    def __init__(self, db):
        self.db = db

    async def get(self, user_id):
        return await self.db.get(UserWorkspaceStateTable, user_id, populate_existing=True)

    async def save(self, user_id, expected_version, state):
        state = serializable(state)
        fields = {"last_session_id", "sidebar_pinned", "sidebar_collapsed", "progress_y_ratio"}
        if not isinstance(state, dict) or set(state) - fields:
            raise ValueError("invalid workspace state")
        for name in ("sidebar_pinned", "sidebar_collapsed"):
            if name in state and not isinstance(state[name], bool):
                raise ValueError(f"{name} must be boolean")
        ratio = state.get("progress_y_ratio", 0.5)
        if isinstance(ratio, bool) or not isinstance(ratio, (int, float)) or not math.isfinite(ratio) or not 0 <= ratio <= 1:
            raise ValueError("progress_y_ratio must be between 0 and 1")
        owner = await self.db.scalar(select(UserTable).where(UserTable.id == user_id).with_for_update(key_share=True))
        if owner is None:
            raise PermissionError("user does not exist")
        last = state.get("last_session_id")
        if last is not None and await self.db.scalar(select(SessionTable.id).where(
            SessionTable.id == last, SessionTable.user_id == user_id,
        )) is None:
            raise PermissionError("last session is not owned")
        row = await self.get(user_id)
        if row is None:
            if expected_version != 0:
                raise WorkspaceConflict("workspace_version_conflict")
            row = UserWorkspaceStateTable(user_id=user_id, version=1, **state)
            self.db.add(row)
        else:
            result = await self.db.execute(update(UserWorkspaceStateTable).where(
                UserWorkspaceStateTable.user_id == user_id,
                UserWorkspaceStateTable.version == expected_version,
            ).values(**state, version=expected_version + 1).execution_options(synchronize_session=False))
            if result.rowcount != 1:
                raise WorkspaceConflict("workspace_version_conflict")
            await self.db.refresh(row)
        await self.db.flush()
        return row
