from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.tables import UserTable


class UserStore:
    def __init__(self, db: AsyncSession | None = None):
        self.db = db
        self._memory: dict[int, dict] = {}
        self._next_id = 1

    async def create(self, username: str, password_hash: str) -> int:
        if self.db:
            user = UserTable(username=username, password_hash=password_hash)
            self.db.add(user)
            await self.db.commit()
            await self.db.refresh(user)
            return user.id
        uid = self._next_id
        self._next_id += 1
        self._memory[uid] = {"id": uid, "username": username, "password_hash": password_hash}
        return uid

    async def find_by_username(self, username: str) -> dict | None:
        if self.db:
            result = await self.db.execute(
                select(UserTable).where(UserTable.username == username)
            )
            user = result.scalar_one_or_none()
            if user:
                return {"id": user.id, "username": user.username, "password_hash": user.password_hash}
            return None
        for u in self._memory.values():
            if u["username"] == username:
                return u
        return None
