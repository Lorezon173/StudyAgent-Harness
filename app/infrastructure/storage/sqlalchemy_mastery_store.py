from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import MasteryNodeTable, MasteryEdgeTable


class SQLAlchemyMasteryStore:
    """掌握度图谱的 SQLAlchemy 持久化（PG/SQLite 双模）。

    复刻旧 MasteryGraphStore 的 save_nodes/load_nodes/save_edges/load_edges
    四方法契约，使 MasteryGraph.save/load 无需改内部调用。save 不 commit（C3）。
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def save_nodes(self, user_id: str, nodes: list[dict]) -> None:
        for n in nodes:
            row = await self.db.get(MasteryNodeTable, (user_id, n["topic_id"]))
            if row is None:
                self.db.add(MasteryNodeTable(
                    user_id=user_id, topic_id=n["topic_id"],
                    topic_name=n.get("topic_name", ""),
                    mastery=n.get("mastery", 0.0),
                    last_practiced_at=n.get("last_practiced_at", 0.0),
                    practice_count=n.get("practice_count", 0),
                    confusion_with=n.get("confusion_with", []),
                    rationale=n.get("rationale", ""),
                ))
            else:
                row.topic_name = n.get("topic_name", "")
                row.mastery = n.get("mastery", 0.0)
                row.last_practiced_at = n.get("last_practiced_at", 0.0)
                row.practice_count = n.get("practice_count", 0)
                row.confusion_with = n.get("confusion_with", [])
                row.rationale = n.get("rationale", "")

    async def load_nodes(self, user_id: str) -> dict[str, dict]:
        result = await self.db.execute(
            select(MasteryNodeTable).where(MasteryNodeTable.user_id == user_id)
        )
        out: dict[str, dict] = {}
        for r in result.scalars().all():
            out[r.topic_id] = {
                "topic_id": r.topic_id,
                "topic_name": r.topic_name,
                "mastery": r.mastery,
                "last_practiced_at": r.last_practiced_at,
                "practice_count": r.practice_count,
                "confusion_with": r.confusion_with or [],
                "rationale": r.rationale or "",
            }
        return out

    async def save_edges(self, user_id: str, edges: list[dict]) -> None:
        for e in edges:
            result = await self.db.execute(
                select(MasteryEdgeTable).where(
                    MasteryEdgeTable.user_id == user_id,
                    MasteryEdgeTable.from_topic == e["from_topic"],
                    MasteryEdgeTable.to_topic == e["to_topic"],
                    MasteryEdgeTable.type == e.get("type", "PREREQ"),
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                self.db.add(MasteryEdgeTable(
                    user_id=user_id, from_topic=e["from_topic"],
                    to_topic=e["to_topic"], type=e.get("type", "PREREQ"),
                    weight=e.get("weight", 1.0),
                    confidence=e.get("confidence", 0.5),
                    source=e.get("source", "LLM_INFER"),
                ))
            else:
                row.weight = e.get("weight", 1.0)
                row.confidence = e.get("confidence", 0.5)
                row.source = e.get("source", "LLM_INFER")

    async def load_edges(self, user_id: str) -> list[dict]:
        result = await self.db.execute(
            select(MasteryEdgeTable).where(MasteryEdgeTable.user_id == user_id)
        )
        return [
            {"from_topic": r.from_topic, "to_topic": r.to_topic,
             "type": r.type, "weight": r.weight,
             "confidence": r.confidence, "source": r.source}
            for r in result.scalars().all()
        ]
