import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.tables import SessionTable


class SessionStore:
    def __init__(self, db: AsyncSession | None = None):
        self.db = db
        self._memory: dict[str, dict] = {}

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

    async def save(self, session_id: str, state: dict, user_id: int | None = None) -> None:
        if self.db:
            result = await self.db.execute(
                select(SessionTable).where(SessionTable.id == session_id)
            )
            row = result.scalar_one_or_none()
            if row is None:
                row = SessionTable(id=session_id, state_json=json.dumps(state), user_id=user_id)
                self.db.add(row)
            else:
                row.state_json = json.dumps(state)
                if user_id is not None:
                    row.user_id = user_id
            await self.db.commit()
        else:
            self._memory[session_id] = {
                "session_id": session_id,
                "user_id": user_id,
                "state_json": json.dumps(state),
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
                select(SessionTable).where(SessionTable.user_id == user_id)
            )
            return [{"session_id": r.id, "state_json": r.state_json} for r in result.scalars().all()]
        return [
            {"session_id": sid, "user_id": s.get("user_id"), "state_json": s.get("state_json", "{}")}
            for sid, s in self._memory.items() if s.get("user_id") == user_id
        ]
