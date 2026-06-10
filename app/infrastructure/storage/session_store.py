import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.models.tables import SessionTable


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
            return {"session_id": row.id, "user_id": row.user_id, "state_json": row.state_json}
        return self._memory.get(session_id)

    async def save(self, session_id: str, state: dict, user_id: int | None = None, title: str | None = None) -> None:
        if self.db:
            result = await self.db.execute(
                select(SessionTable).where(SessionTable.id == session_id)
            )
            row = result.scalar_one_or_none()
            if row is None:
                row = SessionTable(id=session_id, state_json=json.dumps(state), user_id=user_id, title=title or "")
                self.db.add(row)
            else:
                row.state_json = json.dumps(state)
                if user_id is not None:
                    row.user_id = user_id
                # R1: explicit updated_at refresh — SQLAlchemy onupdate may not fire
                # when state_json is always "{}" and user_id doesn't change
                row.updated_at = func.now()
            # C3: caller commits — do NOT commit here
        else:
            self._seq += 1
            # Memory mode: first-write-wins for title
            existing_title = self._memory.get(session_id, {}).get("title", "")
            self._memory[session_id] = {
                "session_id": session_id,
                "user_id": user_id,
                "state_json": json.dumps(state),
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
                await self.db.commit()
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
