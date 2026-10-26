"""短事务请求领取及 attempt 栅栏；所有 commit/rollback 由调用方负责。"""
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import SessionTable
from app.models.workspace_tables import ChatRequestTable


class WorkspaceConflict(ValueError):
    status_code = 409

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def serializable(value):
    """拒绝非 JSON 值与 NaN，返回独立副本避免外部修改待保存原文。"""
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))
    except (TypeError, ValueError) as error:
        raise ValueError("state must be JSON serializable") from error


def utc_now(now=None):
    value = now() if callable(now) else now
    value = value or datetime.now(timezone.utc)
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


@dataclass(frozen=True)
class Claim:
    status: str
    attempt: int
    lease_until: datetime | None
    acquired: bool
    request_payload: dict
    base_state_version: int
    response_json: dict | None
    error_code: str | None

    @property
    def lease(self):
        return self.lease_until


class ChatRequestStore:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _session(self, user_id, session_id):
        row = await self.db.scalar(select(SessionTable).where(
            SessionTable.id == session_id, SessionTable.user_id == user_id,
        ).with_for_update().execution_options(populate_existing=True))
        if row is None or row.user_id is None or row.profile_id is None:
            raise PermissionError("session is not an owned workspace session")
        return row

    async def get(self, user_id, session_id, request_id):
        return await self.db.scalar(select(ChatRequestTable).where(
            ChatRequestTable.user_id == user_id, ChatRequestTable.session_id == session_id,
            ChatRequestTable.request_id == request_id,
        ).execution_options(populate_existing=True))

    @staticmethod
    def _claim(row, acquired=False):
        return Claim(row.status, row.attempt, row.lease_until, acquired,
                     serializable(row.request_payload), row.base_state_version,
                     serializable(row.response_json), row.error_code)

    async def _occupy(self, session, request_id):
        result = await self.db.execute(update(SessionTable).where(
            SessionTable.id == session.id, SessionTable.user_id == session.user_id,
            SessionTable.active_request_id.is_(None),
            SessionTable.state_version == session.state_version,
        ).values(active_request_id=request_id).execution_options(synchronize_session=False))
        if result.rowcount != 1:
            raise WorkspaceConflict("session_busy")
        session.active_request_id = request_id

    async def claim(self, user_id, session_id, request_id, payload_hash, request_payload, *, now=None):
        session = await self._session(user_id, session_id)
        body = serializable(request_payload)
        row = await self.get(user_id, session_id, request_id)
        if row is not None:
            if row.payload_hash != payload_hash or row.request_payload != body:
                raise WorkspaceConflict("payload_conflict")
            return self._claim(row)
        if not isinstance(body, dict) or not isinstance(body.get("message"), str):
            raise ValueError("request_payload requires original message")
        if body.get("profile_id") != session.profile_id or body.get("active_node_id") != session.active_node_id:
            raise PermissionError("request profile/node does not match session")
        if body.get("base_state_version") != session.state_version:
            raise WorkspaceConflict("stale_context")
        if session.active_request_id is not None:
            raise WorkspaceConflict("session_busy")
        row = ChatRequestTable(
            user_id=user_id, session_id=session_id, request_id=request_id,
            profile_id=session.profile_id, active_node_id=session.active_node_id,
            payload_hash=payload_hash, request_payload=body,
            base_state_version=session.state_version, attempt=1, status="running",
            lease_until=utc_now(now) + timedelta(seconds=180),
        )
        self.db.add(row)
        await self.db.flush()  # request 必须先存在，才能写会话 active_request 外键。
        await self._occupy(session, request_id)
        await self.db.flush()
        return self._claim(row, True)

    async def _running(self, user_id, session_id, request_id, attempt, now):
        session = await self._session(user_id, session_id)
        row = await self.get(user_id, session_id, request_id)
        if row is None or row.attempt != attempt:
            raise WorkspaceConflict("attempt_conflict")
        if row.status != "running" or session.active_request_id != request_id:
            raise WorkspaceConflict("request_not_running")
        if row.lease_until is None or row.lease_until <= utc_now(now):
            raise WorkspaceConflict("lease_expired")
        return session, row

    async def renew(self, user_id, session_id, request_id, attempt, *, now=None):
        _, row = await self._running(user_id, session_id, request_id, attempt, now)
        row.lease_until = utc_now(now) + timedelta(seconds=180)
        await self.db.flush()
        return self._claim(row)

    async def complete(self, user_id, session_id, request_id, attempt, response_json, *, now=None):
        session = await self._session(user_id, session_id)
        row = await self.get(user_id, session_id, request_id)
        if row is None or row.attempt != attempt:
            raise WorkspaceConflict("attempt_conflict")
        if row.status == "completed":
            return self._claim(row)
        session, row = await self._running(user_id, session_id, request_id, attempt, now)
        row.status, row.response_json, row.lease_until = "completed", serializable(response_json), None
        row.error_code = None
        session.active_request_id = None
        await self.db.flush()
        return self._claim(row)

    async def interrupt(self, user_id, session_id, request_id, attempt, *, status="interrupted", error_code=None, expired_only=False, now=None):
        if status not in {"failed", "interrupted"}:
            raise ValueError("interrupt status must be failed or interrupted")
        session = await self._session(user_id, session_id)
        row = await self.get(user_id, session_id, request_id)
        if row is None or row.attempt != attempt:
            raise WorkspaceConflict("attempt_conflict")
        if row.status != "running" or session.active_request_id != request_id:
            raise WorkspaceConflict("request_not_running")
        if expired_only and row.lease_until > utc_now(now):
            return self._claim(row)
        row.status, row.error_code, row.lease_until = status, error_code, None
        row.attempt += 1  # 即刻废止后台仍运行的旧 attempt。
        session.active_request_id = None
        await self.db.flush()
        return self._claim(row)

    async def retry(self, user_id, session_id, request_id, expected_attempt, expected_state_version, *, now=None):
        session = await self._session(user_id, session_id)
        row = await self.get(user_id, session_id, request_id)
        if row is None:
            raise PermissionError("request is not owned by user/session")
        if row.attempt != expected_attempt:
            raise WorkspaceConflict("attempt_conflict")
        if row.status not in {"failed", "interrupted"}:
            raise WorkspaceConflict("request_not_retryable")
        if expected_state_version != session.state_version or row.base_state_version != session.state_version:
            raise WorkspaceConflict("stale_context")
        if session.active_request_id is not None:
            raise WorkspaceConflict("session_busy")
        row.attempt += 1
        row.status, row.error_code, row.response_json = "running", None, None
        row.lease_until = utc_now(now) + timedelta(seconds=180)
        await self._occupy(session, request_id)
        await self.db.flush()
        return self._claim(row, True)


    async def validate_running(self, user_id, session_id, request_id, attempt, *, now=None):
        """公开最终栅栏校验；调用方持有短事务并负责提交。"""
        return await self._running(user_id, session_id, request_id, attempt, now)

    async def recover_expired(self, user_id, session_id, request_id, *, now=None):
        await self._session(user_id, session_id)
        row = await self.get(user_id, session_id, request_id)
        if row is None:
            return None
        if row.status == "running" and row.lease_until is not None and row.lease_until <= utc_now(now):
            return await self.interrupt(user_id, session_id, request_id, row.attempt,
                expired_only=True, error_code="lease_expired", now=now)
        return self._claim(row)
