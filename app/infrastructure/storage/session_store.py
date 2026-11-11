import json

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import SessionTable


def _serialize_state(state):
    if "schema_version" in state and state["schema_version"] != 1:
        raise ValueError("unsupported teaching state schema")
    try:
        return json.dumps(state, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValueError("teaching state must be JSON serializable") from error


class SessionStore:
    def __init__(self, db: AsyncSession | None = None):
        self.db = db
        self._memory: dict[str, dict] = {}
        self._seq = 0

    async def get(self, session_id: str) -> dict | None:
        if self.db:
            result = await self.db.execute(
                select(SessionTable).where(SessionTable.id == session_id)
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return {"session_id": row.id, "user_id": row.user_id, "state_json": row.state_json,
                    "profile_id": row.profile_id, "active_node_id": row.active_node_id,
                    "state_version": row.state_version, "next_turn_index": row.next_turn_index,
                    "active_request_id": row.active_request_id}
        return self._memory.get(session_id)

    async def save(self, session_id: str, state: dict, user_id: int | None = None, title: str | None = None) -> None:
        state_json = _serialize_state(state)
        if self.db:
            result = await self.db.execute(
                select(SessionTable).where(SessionTable.id == session_id)
            )
            row = result.scalar_one_or_none()
            if row is None:
                row = SessionTable(id=session_id, state_json=state_json, user_id=user_id, title=title or "")
                self.db.add(row)
            else:
                row.state_json = state_json
                # Existing session ownership is immutable, including legacy NULL.
                row.updated_at = func.now()
            # C3: caller commits — do NOT commit here
        else:
            self._seq += 1
            existing = self._memory.get(session_id)
            existing_title = existing.get("title", "") if existing else ""
            self._memory[session_id] = {
                "session_id": session_id,
                "user_id": existing.get("user_id") if existing else user_id,
                "state_json": state_json,
                "title": title if title is not None else existing_title,
                "_updated_seq": self._seq,
            }

    async def delete(self, session_id: str) -> None:
        if self.db:
            result = await self.db.execute(
                select(SessionTable).where(SessionTable.id == session_id)
            )
            row = result.scalar_one_or_none()
            if row:
                await self.db.delete(row)
        else:
            self._memory.pop(session_id, None)

    async def list_by_user(self, user_id: int) -> list[dict]:
        if self.db:
            result = await self.db.execute(
                select(SessionTable)
                .where(SessionTable.user_id == user_id)
                .order_by(SessionTable.updated_at.desc())
            )
            return [
                {"session_id": r.id, "title": r.title, "updated_at": r.updated_at}
                for r in result.scalars().all()
            ]
        items = [
            {"session_id": sid, "title": s.get("title", ""), "updated_at": s.get("_updated_seq", 0)}
            for sid, s in self._memory.items() if s.get("user_id") == user_id
        ]
        items.sort(key=lambda x: x["updated_at"], reverse=True)
        return items
