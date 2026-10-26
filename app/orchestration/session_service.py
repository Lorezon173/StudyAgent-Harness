"""工作区会话恢复与短事务写入；提交及回滚始终由 API 调用方负责。"""
import base64
import binascii
from datetime import datetime
import json
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import and_, case, or_, select, tuple_, update

from app.infrastructure.storage.chat_request_store import WorkspaceConflict, utc_now
from app.infrastructure.storage.session_view_store import SessionViewStore
from app.infrastructure.storage.workspace_store import WorkspaceStore
from app.models.tables import MessageTable, SessionTable
from app.models.workspace_tables import ChatRequestTable, ProfileNodeTable, SessionViewStateTable
from app.models.workspace_schemas import (GroupedSessions, MessagePage, ProfileItem, RequestSnapshot,
    SessionGroup, SessionSnapshot, ViewState, WorkspaceMessage, WorkspaceSession, WorkspaceState)
from app.orchestration.profile_service import ProfileService


class SessionService:
    def __init__(self, db):
        self.db = db

    async def _ensure_snapshot_transaction(self):
        await ProfileService(self.db)._ensure_snapshot_transaction()

    async def _owned(self, user_id, session_id, lock=None):
        statement = select(SessionTable).where(SessionTable.id == session_id)
        if lock:
            statement = statement.with_for_update(read=lock == "read")
        row = await self.db.scalar(statement.execution_options(populate_existing=True))
        if row is None:
            raise HTTPException(404, "会话不存在")
        if row.user_id is None or row.user_id != user_id:
            raise HTTPException(403, "无权访问该会话")
        return row

    @staticmethod
    def _session(row):
        return WorkspaceSession(session_id=row.id, **{field: getattr(row, field)
            for field in WorkspaceSession.model_fields if field != "session_id"})

    async def _node(self, user_id, profile_id, node_id):
        if profile_id is None:
            if node_id is not None:
                raise HTTPException(404, "画像或知识点不存在")
            return
        await ProfileService(self.db)._get_owned(user_id, profile_id, "read")
        if node_id is not None:
            node = await self.db.scalar(select(ProfileNodeTable).where(
                ProfileNodeTable.profile_id == profile_id, ProfileNodeTable.id == node_id,
                ProfileNodeTable.archived.is_(False)).execution_options(populate_existing=True))
            if node is None:
                raise HTTPException(404, "画像或知识点不存在")

    async def create(self, user_id, profile_id, title="新会话", active_node_id=None):
        await self._ensure_snapshot_transaction()
        await self._node(user_id, profile_id, active_node_id)
        state = dict(schema_version=1, active_node_id=active_node_id, teaching_mode="Socratic",
            mode_history=["Socratic"], stage="init", last_question=None, summary="",
            summary_until_message_id=None, committed_turn_count=0)
        row = SessionTable(id=str(uuid4()), user_id=user_id, profile_id=profile_id, title=title,
            active_node_id=active_node_id, state_json=json.dumps(state, ensure_ascii=False),
            state_version=0, next_turn_index=0)
        self.db.add(row)
        await self.db.flush()
        return self._session(row)

    @staticmethod
    def _encode_cursor(value):
        return base64.urlsafe_b64encode(json.dumps(value, separators=(",", ":")).encode()).decode().rstrip("=")

    @staticmethod
    def _decode_cursor(cursor, fields, tag):
        try:
            decoded = base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True)
            if base64.urlsafe_b64encode(decoded).decode().rstrip("=") != cursor:
                raise ValueError()
            value = json.loads(decoded)
            if not isinstance(value, dict) or set(value) != fields or value["tag"] != tag:
                raise ValueError()
            return value
        except (ValueError, TypeError, binascii.Error, UnicodeError) as exc:
            raise HTTPException(422, "无效分页游标") from exc

    async def _group_sessions(self, user_id, group_key, limit, cursor):
        statement = select(SessionTable).where(SessionTable.user_id == user_id,
            SessionTable.profile_id.is_(None) if group_key == "unassigned" else SessionTable.profile_id == group_key)
        if cursor is not None:
            value = self._decode_cursor(cursor, {"tag", "group_key", "updated_at", "id"}, "sessions")
            try:
                if value["group_key"] != group_key or not isinstance(value["id"], str) or not 1 <= len(value["id"]) <= 64:
                    raise ValueError()
                timestamp = value["updated_at"]
                if timestamp is None:
                    statement = statement.where(SessionTable.updated_at.is_(None), SessionTable.id < value["id"])
                else:
                    if not isinstance(timestamp, str):
                        raise ValueError()
                    parsed = datetime.fromisoformat(timestamp)
                    if parsed.tzinfo is not None or parsed.isoformat() != timestamp:
                        raise ValueError()
                    statement = statement.where(or_(SessionTable.updated_at < parsed,
                        and_(SessionTable.updated_at == parsed, SessionTable.id < value["id"]), SessionTable.updated_at.is_(None)))
            except (ValueError, TypeError) as exc:
                raise HTTPException(422, "无效分页游标") from exc
        rows = list((await self.db.scalars(statement.order_by(
            SessionTable.updated_at.desc().nulls_last(), SessionTable.id.desc()).limit(limit + 1))).all())
        next_cursor = None
        if len(rows) > limit:
            last = rows[limit - 1]
            next_cursor = self._encode_cursor(dict(tag="sessions", group_key=group_key,
                updated_at=last.updated_at.isoformat() if last.updated_at else None, id=last.id))
        return [self._session(row) for row in rows[:limit]], next_cursor

    async def list_grouped(self, user_id, limit=30, group_limit=30, cursor=None, group_key=None, session_cursor=None):
        if (session_cursor is not None and group_key is None) or (group_key is not None and cursor is not None):
            raise HTTPException(422, "主题和组内游标不能混用")
        profiles = ProfileService(self.db)
        groups = []
        next_group_cursor = None
        if group_key is not None:
            if group_key == "unassigned":
                items = [None]
            else:
                try:
                    if str(UUID(group_key)) != group_key:
                        raise ValueError()
                except (ValueError, TypeError) as exc:
                    raise HTTPException(422, "无效主题标识") from exc
                items = [ProfileItem.model_validate(await profiles._get_owned(user_id, group_key))]
        else:
            page = await profiles.list_owned(user_id, group_limit, cursor)
            items, next_group_cursor = list(page.items), page.next_cursor
            if cursor is None and await self.db.scalar(select(SessionTable.id).where(
                    SessionTable.user_id == user_id, SessionTable.profile_id.is_(None)).limit(1)) is not None:
                items.append(None)
        for profile in items:
            key = profile.id if profile else "unassigned"
            sessions, next_cursor = await self._group_sessions(user_id, key, limit, session_cursor)
            groups.append(SessionGroup(group_key=key, profile=profile,
                summary=await profiles.get_summary(user_id, key) if profile else None,
                sessions=sessions, next_session_cursor=next_cursor))
        return GroupedSessions(groups=groups, next_group_cursor=next_group_cursor)

    async def load_messages(self, user_id, session_id, cursor=None, limit=None):
        await self._owned(user_id, session_id)
        role = case((MessageTable.role == "user", 0), (MessageTable.role == "assistant", 1), else_=2)
        statement = select(MessageTable).where(MessageTable.session_id == session_id)
        if cursor is None and limit is None:
            rows = (await self.db.scalars(statement.order_by(MessageTable.id.asc()))).all()
            return [WorkspaceMessage.model_validate(row) for row in rows]
        limit = limit or 50
        if cursor is not None:
            value = self._decode_cursor(cursor, {"tag", "session_id", "turn_index", "role_order", "id"}, "messages")
            if (value["session_id"] != session_id or type(value["turn_index"]) is not int or value["turn_index"] < 0
                    or type(value["role_order"]) is not int or value["role_order"] not in range(3)
                    or type(value["id"]) is not int or value["id"] <= 0):
                raise HTTPException(422, "无效分页游标")
            statement = statement.where(tuple_(MessageTable.turn_index, role, MessageTable.id) <
                tuple_(value["turn_index"], value["role_order"], value["id"]))
        rows = list((await self.db.scalars(statement.order_by(MessageTable.turn_index.desc(), role.desc(),
            MessageTable.id.desc()).limit(limit + 1))).all())
        next_cursor = None
        if len(rows) > limit:
            last = rows[limit - 1]
            next_cursor = self._encode_cursor(dict(tag="messages", session_id=session_id, turn_index=last.turn_index,
                role_order={"user": 0, "assistant": 1}.get(last.role, 2), id=last.id))
        return MessagePage(items=[WorkspaceMessage.model_validate(row) for row in reversed(rows[:limit])], next_cursor=next_cursor)

    @staticmethod
    def _state(row):
        try:
            state = json.loads(row.state_json)
            if not isinstance(state, dict):
                raise ValueError()
        except (ValueError, TypeError) as exc:
            raise WorkspaceConflict("invalid_teaching_state") from exc
        if "schema_version" not in state:
            return None, "legacy", state
        if type(state["schema_version"]) is not int or state["schema_version"] != 1:
            raise WorkspaceConflict("unsupported_teaching_schema")
        required = {"active_node_id", "teaching_mode", "mode_history", "stage", "last_question", "summary",
                    "summary_until_message_id", "committed_turn_count"}
        if (not required <= state.keys() or state["active_node_id"] != row.active_node_id
                or not isinstance(state["summary"], str) or type(state["committed_turn_count"]) is not int
                or state["committed_turn_count"] < 0):
            raise WorkspaceConflict("invalid_teaching_state")
        return state, "stored", None

    @staticmethod
    def _request(row):
        values = {field: getattr(row, field) for field in RequestSnapshot.model_fields if field != "lease_expired"}
        return RequestSnapshot(**values, lease_expired=row.lease_until is not None and row.lease_until <= utc_now())

    async def load_snapshot(self, user_id, session_id, message_limit=50):
        await self._ensure_snapshot_transaction()
        row = await self._owned(user_id, session_id, "read")
        state, source, legacy = self._state(row)
        profile = summary = None
        if row.profile_id is not None:
            service = ProfileService(self.db)
            profile = ProfileItem.model_validate(await service._get_owned(user_id, row.profile_id, "read"))
            summary = await service.get_summary(user_id, row.profile_id)
        # 直接只读 view；SessionViewStore.get 会升级 session 锁。
        view = await self.db.get(SessionViewStateTable, (user_id, session_id), populate_existing=True)
        requests = (await self.db.scalars(select(ChatRequestTable).where(ChatRequestTable.user_id == user_id,
            ChatRequestTable.session_id == session_id, ChatRequestTable.status != "completed")
            .order_by(ChatRequestTable.created_at, ChatRequestTable.request_id)
            .execution_options(populate_existing=True))).all()
        return SessionSnapshot(session=self._session(row), teaching_state=state, teaching_state_source=source,
            legacy_state=legacy, messages=await self.load_messages(user_id, session_id, limit=message_limit),
            profile=profile, profile_summary=summary, view_state=ViewState.model_validate(view) if view else ViewState(),
            pending_requests=[self._request(request) for request in requests])

    async def save_view_state(self, user_id, session_id, expected_version, changes):
        await self._ensure_snapshot_transaction()
        await self._owned(user_id, session_id, "write")
        anchor = changes.get("reading_anchor")
        if anchor is not None and await self.db.scalar(select(MessageTable.id).where(
                MessageTable.id == anchor["message_id"], MessageTable.session_id == session_id)) is None:
            raise HTTPException(422, "阅读锚点不属于该会话")
        return ViewState.model_validate(await SessionViewStore(self.db).save(user_id, session_id, expected_version, changes))

    async def get_workspace(self, user_id):
        row = await WorkspaceStore(self.db).get(user_id)
        return WorkspaceState.model_validate(row) if row else WorkspaceState()

    async def save_workspace(self, user_id, expected_version, changes):
        await self._ensure_snapshot_transaction()
        return WorkspaceState.model_validate(await WorkspaceStore(self.db).save(user_id, expected_version, changes))

    async def set_active_node(self, user_id, session_id, expected_state_version, node_id):
        await self._ensure_snapshot_transaction()
        row = await self._owned(user_id, session_id, "write")
        if row.active_request_id is not None:
            raise WorkspaceConflict("session_busy")
        if row.state_version != expected_state_version:
            raise WorkspaceConflict("state_version_conflict")
        await self._node(user_id, row.profile_id, node_id)
        state, source, _ = self._state(row)
        if row.active_node_id != node_id:
            values = dict(active_node_id=node_id, state_version=expected_state_version + 1)
            if source == "stored":
                state["active_node_id"] = node_id
                state["last_question"] = None
                state["stage"] = "init"
                values["state_json"] = json.dumps(state, ensure_ascii=False)
            result = await self.db.execute(update(SessionTable).where(SessionTable.id == session_id,
                SessionTable.user_id == user_id, SessionTable.state_version == expected_state_version,
                SessionTable.active_request_id.is_(None)).values(**values).execution_options(synchronize_session=False))
            if result.rowcount != 1:
                raise WorkspaceConflict("state_version_conflict")
            await self.db.refresh(row)
        await self.db.flush()
        return self._session(row)

    async def get_request(self, user_id, session_id, request_id):
        await self._owned(user_id, session_id)
        row = await self.db.get(ChatRequestTable, (user_id, session_id, request_id), populate_existing=True)
        if row is None:
            raise HTTPException(404, "请求不存在")
        return self._request(row)

    async def prepare_retry(self, user_id, session_id, request_id, expected_attempt, expected_state_version):
        session = await self._owned(user_id, session_id)
        request = await self.get_request(user_id, session_id, request_id)
        if request.status not in {"failed", "interrupted"}:
            raise WorkspaceConflict("request_not_retryable")
        if request.attempt != expected_attempt:
            raise WorkspaceConflict("attempt_conflict")
        if expected_state_version != session.state_version or request.base_state_version != session.state_version:
            raise WorkspaceConflict("stale_context")
        if session.active_request_id is not None:
            raise WorkspaceConflict("session_busy")
        return request
