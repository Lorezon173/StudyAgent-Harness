"""以画像绑定既有 MasteryGraph 四方法契约，仅供受控初始化/离线写入。"""
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.infrastructure.storage.topic_profile_store import TopicProfileStore
from app.models.workspace_tables import ProfileEdgeTable, ProfileNodeTable, TopicProfileTable


class ProfileMasteryStore:
    def __init__(self, db: AsyncSession, profile_id: str):
        self.db = db
        self.profile_id = profile_id
        self._node_revisions: dict[str, int] = {}
        self._profile_revision: int | None = None
        self._known_edges: set[tuple] = set()
        self._write_failed = False

    async def _owned(self, user_id: int) -> TopicProfileTable:
        if self._write_failed:
            raise RuntimeError("failed write: caller must rollback and create a new ProfileMasteryStore")
        profile = await TopicProfileStore(self.db).get_owned(user_id, self.profile_id)
        if profile is None:
            raise PermissionError("topic profile does not belong to user")
        return profile

    def _observe_revision(self, revision: int) -> None:
        if self._profile_revision is not None and self._profile_revision != revision:
            raise ValueError("profile revision changed during snapshot; create a new store")
        self._profile_revision = revision

    async def _advance_revision(self, profile: TopicProfileTable) -> None:
        expected = self._profile_revision if self._profile_revision is not None else profile.revision
        result = await self.db.execute(
            update(TopicProfileTable).where(TopicProfileTable.id == self.profile_id,
                                           TopicProfileTable.user_id == profile.user_id,
                                           TopicProfileTable.revision == expected)
            .values(revision=expected + 1, updated_at=func.now())
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            raise ValueError("profile revision conflict; caller must rollback")
        self._profile_revision = expected + 1

    async def load_nodes(self, user_id: int) -> dict[str, dict]:
        profile = await self._owned(user_id)
        self._observe_revision(profile.revision)
        rows = (await self.db.scalars(select(ProfileNodeTable).where(
            ProfileNodeTable.profile_id == self.profile_id).execution_options(populate_existing=True))).all()
        self._node_revisions = {row.id: row.revision for row in rows}
        return {row.id: {
            "topic_id": row.id, "topic_name": row.title, "description": row.description,
            "mastery": row.mastery, "last_practiced_at": row.last_practiced_at,
            "practice_count": row.practice_count, "confusion_with": [],
            "rationale": row.rationale, "revision": row.revision, "archived": row.archived,
        } for row in rows}

    async def save_nodes(self, user_id: int, nodes: list[dict]) -> None:
        try:
            await self._save_nodes(user_id, nodes)
        except Exception:
            self._write_failed = True
            raise

    async def _save_nodes(self, user_id: int, nodes: list[dict]) -> None:
        profile = await self._owned(user_id)
        if not nodes:
            return
        await self._advance_revision(profile)
        for node in nodes:
            node_id = str(UUID(node["topic_id"]))
            row = await self.db.get(ProfileNodeTable, node_id, populate_existing=True)
            values = {
                column: node[key] for key, column in {
                    "topic_name": "title", "description": "description", "mastery": "mastery",
                    "last_practiced_at": "last_practiced_at", "practice_count": "practice_count",
                    "rationale": "rationale", "archived": "archived",
                }.items() if key in node
            }
            if row is None:
                self.db.add(ProfileNodeTable(id=node_id, profile_id=self.profile_id, **values))
                await self.db.flush()
                self._node_revisions[node_id] = 0
            else:
                if row.profile_id != self.profile_id:
                    raise PermissionError("node does not belong to topic profile")
                expected = node.get("revision", self._node_revisions.get(node_id))
                if expected is None:
                    raise ValueError("node revision required; caller must rollback")
                result = await self.db.execute(
                    update(ProfileNodeTable).where(ProfileNodeTable.id == node_id,
                                                   ProfileNodeTable.profile_id == self.profile_id,
                                                   ProfileNodeTable.revision == expected)
                    .values(**values, revision=expected + 1)
                    .execution_options(synchronize_session=False)
                )
                if result.rowcount != 1:
                    raise ValueError("node revision conflict; caller must rollback")
                self._node_revisions[node_id] = expected + 1

    async def load_edges(self, user_id: int) -> list[dict]:
        profile = await self._owned(user_id)
        self._observe_revision(profile.revision)
        rows = (await self.db.scalars(select(ProfileEdgeTable).where(
            ProfileEdgeTable.profile_id == self.profile_id).execution_options(populate_existing=True))).all()
        self._known_edges = {(self.profile_id, row.from_node_id, row.to_node_id, row.type) for row in rows}
        return [{"from_topic": row.from_node_id, "to_topic": row.to_node_id,
                 "type": row.type, "weight": row.weight, "confidence": row.confidence,
                 "source": row.source} for row in rows]

    async def save_edges(self, user_id: int, edges: list[dict]) -> None:
        try:
            await self._save_edges(user_id, edges)
        except Exception:
            self._write_failed = True
            raise

    async def _save_edges(self, user_id: int, edges: list[dict]) -> None:
        profile = await self._owned(user_id)
        if not edges:
            return
        await self._advance_revision(profile)
        for edge in edges:
            key = (self.profile_id, str(UUID(edge["from_topic"])), str(UUID(edge["to_topic"])), edge.get("type", "PREREQ"))
            row = await self.db.get(ProfileEdgeTable, key, populate_existing=True)
            values = {"weight": edge.get("weight", 1.0), "confidence": edge.get("confidence", 0.5),
                      "source": edge.get("source", "LLM_INFER")}
            if row is None:
                self.db.add(ProfileEdgeTable(profile_id=key[0], from_node_id=key[1], to_node_id=key[2], type=key[3], **values))
            else:
                if key not in self._known_edges:
                    raise ValueError("profile revision required for existing edge; caller must rollback")
                row.weight, row.confidence, row.source = values["weight"], values["confidence"], values["source"]
        await self.db.flush()
        self._known_edges.update((self.profile_id, str(UUID(edge["from_topic"])), str(UUID(edge["to_topic"])),
                                  edge.get("type", "PREREQ")) for edge in edges)
