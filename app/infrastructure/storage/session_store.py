import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.tables import SessionTable


class SessionStore:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get(self, session_id: str) -> dict | None:
        result = await self.db.execute(
            select(SessionTable).where(SessionTable.id == session_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return json.loads(row.state_json)

    async def save(self, session_id: str, state: dict, user_id: int | None = None) -> None:
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

    async def delete(self, session_id: str) -> None:
        result = await self.db.execute(
            select(SessionTable).where(SessionTable.id == session_id)
        )
        row = result.scalar_one_or_none()
        if row:
            await self.db.delete(row)
            await self.db.commit()

    async def list_by_user(self, user_id: int) -> list[dict]:
        result = await self.db.execute(
            select(SessionTable).where(SessionTable.user_id == user_id)
        )
        return [{"id": r.id, "created_at": str(r.created_at)} for r in result.scalars().all()]
