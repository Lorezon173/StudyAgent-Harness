"""私有文本卡片 Store；事务由调用方提交。"""
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workspace_tables import LibraryItemTable, TopicProfileTable


class LibraryStore:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _ensure_profile_owned(self, user_id: int, profile_id: str | None):
        if profile_id is not None:
            owned = await self.db.scalar(select(TopicProfileTable.id).where(
                TopicProfileTable.user_id == user_id, TopicProfileTable.id == profile_id))
            if owned is None:
                raise PermissionError("画像不存在")

    async def create(self, user_id: int, fields: dict) -> LibraryItemTable:
        await self._ensure_profile_owned(user_id, fields.get("profile_id"))
        item = LibraryItemTable(user_id=user_id, source_type="manual", **fields)
        self.db.add(item)
        await self.db.flush()
        return item

    async def get(self, user_id: int, item_id: int) -> LibraryItemTable | None:
        return await self.db.scalar(select(LibraryItemTable).where(
            LibraryItemTable.user_id == user_id, LibraryItemTable.id == item_id))

    async def list(self, user_id: int, q: str | None = None, profile_id: str | None = None,
                   limit: int = 50, before_id: int | None = None) -> list[LibraryItemTable]:
        statement = select(LibraryItemTable).where(LibraryItemTable.user_id == user_id)
        if profile_id is not None:
            statement = statement.where(LibraryItemTable.profile_id == profile_id)
        if before_id is not None:
            statement = statement.where(LibraryItemTable.id < before_id)
        if q is not None:
            escaped_query = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            statement = statement.where(or_(*[
                column.contains(escaped_query, escape="\\") for column in (
                    LibraryItemTable.name, LibraryItemTable.description, LibraryItemTable.content_text)]))
        return list((await self.db.scalars(statement.order_by(LibraryItemTable.id.desc()).limit(limit))).all())

    async def update(self, user_id: int, item_id: int, changes: dict) -> LibraryItemTable | None:
        item = await self.get(user_id, item_id)
        if item is None:
            return None
        if "profile_id" in changes:
            await self._ensure_profile_owned(user_id, changes["profile_id"])
        for field, value in changes.items():
            setattr(item, field, value)
        await self.db.flush()
        # updated_at 在数据库生成；显式刷新避免异步序列化触发隐式 IO。
        await self.db.refresh(item)
        return item

    async def delete(self, user_id: int, item_id: int) -> bool:
        item = await self.get(user_id, item_id)
        if item is None:
            return False
        await self.db.delete(item)
        await self.db.flush()
        return True
