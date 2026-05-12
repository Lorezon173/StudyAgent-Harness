from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.tables import UserTable


class UserStore:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, username: str, password_hash: str) -> UserTable:
        user = UserTable(username=username, password_hash=password_hash)
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def find_by_username(self, username: str) -> UserTable | None:
        result = await self.db.execute(
            select(UserTable).where(UserTable.username == username)
        )
        return result.scalar_one_or_none()
