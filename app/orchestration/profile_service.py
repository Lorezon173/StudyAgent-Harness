"""主题画像手动管理及同一数据库快照内的真实摘要。事务由调用方负责。"""
import base64
import binascii
import json
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import MessageTable, SessionTable
from app.models.workspace_schemas import (
    NodeMutationResponse,
    ProfileDetail,
    ProfileEdge,
    ProfileEvidence,
    ProfileItem,
    ProfileNode,
    ProfilePage,
    ProfileSummary,
)
from app.models.workspace_tables import (
    ChatRequestTable,
    ProfileEdgeTable,
    ProfileEvidenceTable,
    ProfileNodeTable,
    TopicProfileTable,
)


class ProfileNotFound(Exception):
    pass


class ProfileVersionConflict(Exception):
    pass


class InvalidProfileCursor(ValueError):
    pass


class ProfileService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _ensure_snapshot_transaction(self):
        connection = await self.db.connection()
        if connection.dialect.name == "sqlite":
            # aiosqlite/legacy transaction control: SQLAlchemy 的逻辑 autobegin
            # 不代表 SELECT 已建立数据库读事务。保留调用者已有的真实事务。
            in_transaction = await connection.run_sync(
                lambda conn: conn.connection.driver_connection.in_transaction)
            if not in_transaction:
                await connection.exec_driver_sql("BEGIN")

    async def _get_owned(self, user_id, profile_id, lock="read"):
        statement = select(TopicProfileTable).where(
            TopicProfileTable.user_id == user_id, TopicProfileTable.id == profile_id)
        if lock:
            statement = statement.with_for_update(read=lock == "read")
        profile = await self.db.scalar(statement.execution_options(populate_existing=True))
        if profile is None:
            raise ProfileNotFound()
        return profile

    async def create(self, user_id, name, scope_description=""):
        profile = TopicProfileTable(user_id=user_id, name=name, scope_description=scope_description)
        self.db.add(profile)
        await self.db.flush()
        self.db.add(ProfileNodeTable(profile_id=profile.id, title=name))
        await self.db.flush()
        return await self.get_detail(user_id, profile.id)

    @staticmethod
    def _decode_cursor(cursor):
        try:
            decoded = base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True)
            if base64.urlsafe_b64encode(decoded).decode().rstrip("=") != cursor:
                raise ValueError()
            value = json.loads(decoded)
            if not isinstance(value, dict) or set(value) != {"created_at", "id"}:
                raise ValueError()
            if not isinstance(value["created_at"], str) or not isinstance(value["id"], str):
                raise ValueError()
            created_at = datetime.fromisoformat(value["created_at"])
            if (created_at.tzinfo is not None or created_at.isoformat() != value["created_at"]
                    or str(UUID(value["id"])) != value["id"]):
                raise ValueError()
            return created_at, value["id"]
        except (ValueError, TypeError, binascii.Error, UnicodeError) as exc:
            raise InvalidProfileCursor("无效分页游标") from exc

    async def list_owned(self, user_id, limit=30, cursor=None):
        statement = select(TopicProfileTable).where(TopicProfileTable.user_id == user_id)
        if cursor is not None:
            created_at, profile_id = self._decode_cursor(cursor)
            statement = statement.where(or_(TopicProfileTable.created_at < created_at,
                and_(TopicProfileTable.created_at == created_at, TopicProfileTable.id < profile_id)))
        rows = list((await self.db.scalars(statement.order_by(
            TopicProfileTable.created_at.desc(), TopicProfileTable.id.desc()).limit(limit + 1))).all())
        next_cursor = None
        if len(rows) > limit:
            last = rows[limit - 1]
            payload = json.dumps({"created_at": last.created_at.isoformat(), "id": last.id}).encode()
            next_cursor = base64.urlsafe_b64encode(payload).decode().rstrip("=")
        return ProfilePage(items=[ProfileItem.model_validate(row) for row in rows[:limit]], next_cursor=next_cursor)

    async def _advance_revision(self, profile, expected_revision):
        result = await self.db.execute(update(TopicProfileTable).where(
            TopicProfileTable.id == profile.id, TopicProfileTable.user_id == profile.user_id,
            TopicProfileTable.revision == expected_revision).values(
                revision=TopicProfileTable.revision + 1).execution_options(synchronize_session=False))
        if result.rowcount != 1:
            raise ProfileVersionConflict()
        await self.db.refresh(profile)

    async def update_profile(self, user_id, profile_id, expected_revision, changes):
        profile = await self._get_owned(user_id, profile_id, "write")
        await self._advance_revision(profile, expected_revision)
        for field, value in changes.items():
            setattr(profile, field, value)
        await self.db.flush()
        return await self.get_detail(user_id, profile_id)

    async def add_node(self, user_id, profile_id, expected_revision, title, description=""):
        profile = await self._get_owned(user_id, profile_id, "write")
        await self._advance_revision(profile, expected_revision)
        node = ProfileNodeTable(profile_id=profile_id, title=title, description=description)
        self.db.add(node)
        await self.db.flush()
        return NodeMutationResponse(node=ProfileNode.model_validate(node), profile_revision=profile.revision)

    async def update_node(self, user_id, profile_id, node_id, expected_revision, changes):
        profile = await self._get_owned(user_id, profile_id, "write")
        node = await self.db.scalar(select(ProfileNodeTable).where(
            ProfileNodeTable.profile_id == profile_id, ProfileNodeTable.id == node_id)
            .execution_options(populate_existing=True))
        if node is None:
            raise ProfileNotFound()
        await self._advance_revision(profile, expected_revision)
        for field, value in changes.items():
            setattr(node, field, value)
        node.revision += 1
        await self.db.flush()
        return NodeMutationResponse(node=ProfileNode.model_validate(node), profile_revision=profile.revision)

    async def get_detail(self, user_id, profile_id):
        await self._ensure_snapshot_transaction()
        profile = await self._get_owned(user_id, profile_id)
        nodes = (await self.db.scalars(select(ProfileNodeTable).where(
            ProfileNodeTable.profile_id == profile_id).order_by(ProfileNodeTable.id)
            .execution_options(populate_existing=True))).all()
        edges = (await self.db.scalars(select(ProfileEdgeTable).where(
            ProfileEdgeTable.profile_id == profile_id).order_by(
                ProfileEdgeTable.from_node_id, ProfileEdgeTable.to_node_id, ProfileEdgeTable.type)
            .execution_options(populate_existing=True))).all()
        return ProfileDetail(profile=ProfileItem.model_validate(profile), profile_revision=profile.revision,
            nodes=[ProfileNode.model_validate(node) for node in nodes],
            edges=[ProfileEdge.model_validate(edge) for edge in edges])

    async def get_summary(self, user_id, profile_id):
        detail = await self.get_detail(user_id, profile_id)
        nodes = [node for node in detail.nodes if not node.archived]
        active_ids = {node.id for node in nodes}
        edges = [edge for edge in detail.edges if edge.from_node_id in active_ids and edge.to_node_id in active_ids]
        evidence = (await self.db.scalars(select(ProfileEvidenceTable)
            .join(SessionTable, and_(SessionTable.id == ProfileEvidenceTable.session_id,
                SessionTable.user_id == ProfileEvidenceTable.user_id, SessionTable.profile_id == ProfileEvidenceTable.profile_id))
            .join(MessageTable, and_(MessageTable.id == ProfileEvidenceTable.message_id,
                MessageTable.session_id == ProfileEvidenceTable.session_id))
            .join(ChatRequestTable, and_(ChatRequestTable.user_id == ProfileEvidenceTable.user_id,
                ChatRequestTable.session_id == ProfileEvidenceTable.session_id,
                ChatRequestTable.request_id == ProfileEvidenceTable.request_id,
                ChatRequestTable.profile_id == ProfileEvidenceTable.profile_id))
            .where(ProfileEvidenceTable.user_id == user_id, ProfileEvidenceTable.profile_id == profile_id)
            .order_by(ProfileEvidenceTable.created_at.desc(), ProfileEvidenceTable.id.desc()).limit(10)
            .execution_options(populate_existing=True))).all()
        assessed = [node.mastery for node in nodes if node.mastery is not None]
        return ProfileSummary(profile_revision=detail.profile_revision, nodes=nodes, edges=edges,
            recent_evidence=[ProfileEvidence.model_validate(row) for row in evidence],
            assessed_count=len(assessed), total_count=len(nodes),
            mastery_score=sum(assessed) / len(assessed) if assessed else None,
            assessment_coverage=len(assessed) / len(nodes) if nodes else None)
