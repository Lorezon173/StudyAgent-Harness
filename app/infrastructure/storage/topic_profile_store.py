from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workspace_tables import TopicProfileTable


class TopicProfileStore:
    """主题画像归属入口；事务始终由调用者提交或回滚。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, user_id: int, name: str, scope: str) -> TopicProfileTable:
        row = TopicProfileTable(user_id=user_id, name=name, scope_description=scope)
        self.db.add(row)
        await self.db.flush()
        return row

    async def get_owned(self, user_id: int, profile_id: str) -> TopicProfileTable | None:
        return await self.db.scalar(
            select(TopicProfileTable).where(TopicProfileTable.id == profile_id,
                                           TopicProfileTable.user_id == user_id)
            .execution_options(populate_existing=True)
        )
