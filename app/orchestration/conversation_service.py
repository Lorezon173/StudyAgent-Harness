"""HTTP/SSE共用教学请求状态机；所有DB事务在同步生成之前释放。"""
import asyncio
import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api._dirty_flag import DirtyFlag
from app.harness.mastery_graph import MasteryGraph
from app.infrastructure.llm import LLMService
from app.infrastructure.storage.chat_request_store import (
    ChatRequestStore,
    Claim,
    WorkspaceConflict,
    utc_now,
)
from app.infrastructure.storage.sqlalchemy_mastery_store import SQLAlchemyMasteryStore
from app.models.schemas import ChatResponse
from app.models.tables import SessionTable
from app.models.workspace_tables import ChatRequestTable, TopicProfileTable
from app.orchestration import turn_commit
from app.orchestration.assembly import (
    NewStackResult,
    OnlineRAGCompositionError,
    run_online_agent_session,
)
from app.orchestration.session_service import SessionService

logger = logging.getLogger(__name__)


class Clock:
    def monotonic_now(self):
        return time.monotonic()

    def utc_now(self):
        return datetime.now(UTC)

    async def wait_until(self, deadline):
        await asyncio.sleep(max(0, deadline - self.monotonic_now()))


@dataclass(frozen=True)
class PreparedTurn:
    user_id: int
    session_id: str
    request_id: str
    profile_id: str
    claim: Claim
    started: float

    @property
    def key(self):
        return (self.user_id, self.session_id, self.request_id, self.claim.attempt)


@dataclass(frozen=True)
class TurnInput:
    snapshot: object
    messages: list
    graph: MasteryGraph
    profile_summary: object
    prepared: PreparedTurn


@dataclass(frozen=True)
class TurnOutcome:
    result: NewStackResult
    context_reduced: bool
    reduction_reasons: tuple[str, ...]
    graph: MasteryGraph


@dataclass
class Execution:
    prepared: PreparedTurn
    task: object
    closed: threading.Event = field(default_factory=threading.Event)
    generation: object = None
    commit: object = None


def normalize_payload(message, profile_id, active_node_id, base_state_version):
    payload = dict(message=message, profile_id=profile_id, active_node_id=active_node_id, base_state_version=base_state_version)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return payload, hashlib.sha256(encoded.encode('utf-8')).hexdigest()


class ConversationService:
    def __init__(self, session_factory, *, llm=None, runner=None, clock=None):
        self.session_factory = session_factory
        self.llm = llm if llm is not None else LLMService()
        self.runner = runner if runner is not None else run_online_agent_session
        self.clock = clock if clock is not None else Clock()
        self.executions = {}
        self.closed = False

    async def _owned(self, db, user_id, session_id, *, missing=False):
        row = await db.scalar(select(SessionTable).where(SessionTable.id == session_id)
            .with_for_update().execution_options(populate_existing=True))
        if row is None:
            if missing:
                return None
            raise HTTPException(404, '会话不存在')
        if row.user_id is None or row.user_id != user_id:
            raise HTTPException(403, '无权写入该会话')
        return row

    async def _profile(self, db, user_id, profile_id):
        row = await db.scalar(select(TopicProfileTable).where(TopicProfileTable.id == profile_id,
            TopicProfileTable.user_id == user_id))
        if row is None:
            raise HTTPException(404, '画像不存在')
        return row

    @staticmethod
    def _expected_unique(error, name, sqlite_text):
        original = error.orig
        actual = getattr(getattr(original, 'diag', None), 'constraint_name', None)
        actual = actual or getattr(original, 'constraint_name', None)
        actual = actual or getattr(getattr(original, '__cause__', None), 'constraint_name', None)
        return actual == name or (sqlite_text in str(original) and 'UNIQUE constraint failed' in str(original))

    async def _default_profile(self, user_id):
        for attempt in range(2):
            async with self.session_factory() as db:
                try:
                    row = await db.scalar(select(TopicProfileTable).where(TopicProfileTable.user_id == user_id,
                        TopicProfileTable.kind == 'legacy'))
                    if row is None:
                        if attempt:
                            raise WorkspaceConflict('session_busy')
                        row = TopicProfileTable(id=str(uuid4()), user_id=user_id, name='历史待整理', kind='legacy')
                        db.add(row)
                        await db.flush()
                    pid = row.id
                    await db.commit()
                    return pid
                except IntegrityError as error:
                    await db.rollback()
                    if attempt or not self._expected_unique(error, 'uq_topic_profile_legacy_owner', 'topic_profiles.user_id'):
                        raise
        raise WorkspaceConflict('session_busy')

    async def recover_session_requests(self, user_id, session_id, request_id=None):
        async with self.session_factory() as db:
            await self._owned(db, user_id, session_id)
            statement = select(ChatRequestTable).where(ChatRequestTable.user_id == user_id,
                ChatRequestTable.session_id == session_id, ChatRequestTable.status == 'running',
                ChatRequestTable.lease_until <= utc_now(self.clock.utc_now()))
            if request_id is not None:
                statement = statement.where(ChatRequestTable.request_id == request_id)
            rows = list((await db.scalars(statement)).all())
            for row in rows:
                await ChatRequestStore(db).recover_expired(user_id, session_id, row.request_id, now=self.clock.utc_now)
            await db.commit()

    async def recover_expired(self, user_id, session_id, request_id):
        await self.recover_session_requests(user_id, session_id, request_id)
        async with self.session_factory() as db:
            await self._owned(db, user_id, session_id)
            row = await ChatRequestStore(db).get(user_id, session_id, request_id)
            return ChatRequestStore._claim(row) if row else None

    async def prepare_request(self, user_id, request):
        if self.closed:
            raise HTTPException(503, {'code':'conversation_service_unavailable'})
        rid = request.request_id or str(uuid4())
        async with self.session_factory() as db:
            existing = await self._owned(db, user_id, request.session_id, missing=True)
            needs_profile = existing is None or existing.profile_id is None
        default = await self._default_profile(user_id) if needs_profile and request.profile_id is None else request.profile_id
        for creation_attempt in range(2):
            async with self.session_factory() as db:
                try:
                    row = await self._owned(db, user_id, request.session_id, missing=True)
                    if row is None:
                        await self._profile(db, user_id, default)
                        row = SessionTable(id=request.session_id, user_id=user_id, profile_id=default,
                            state_json="{}", workspace_entered=True, title=request.message.strip()[:24] or '新会话',
                            state_version=0, next_turn_index=0)
                        db.add(row)
                        await db.flush()
                    if row.profile_id is None:
                        await self._profile(db, user_id, default)
                        row.profile_id = default
                        await db.flush()
                    row.workspace_entered = True
                    store = ChatRequestStore(db)
                    saved = await store.get(user_id, row.id, rid)
                    if saved is not None:
                        old = saved.request_payload
                        body, digest = normalize_payload(request.message,
                            request.profile_id if request.profile_id is not None else old['profile_id'],
                            old['active_node_id'], request.expected_state_version if request.expected_state_version is not None else old['base_state_version'])
                        if body != old or digest != saved.payload_hash:
                            raise WorkspaceConflict('payload_conflict')
                        claim = await store.recover_expired(user_id, row.id, rid, now=self.clock.utc_now)
                    else:
                        if request.profile_id is not None:
                            await self._profile(db, user_id, request.profile_id)
                            if request.profile_id != row.profile_id:
                                raise WorkspaceConflict('profile_context_mismatch')
                        if row.active_request_id is not None:
                            await store.recover_expired(user_id, row.id, row.active_request_id, now=self.clock.utc_now)
                        base = row.state_version if request.expected_state_version is None else request.expected_state_version
                        body, digest = normalize_payload(request.message, row.profile_id, row.active_node_id, base)
                        claim = await store.claim(user_id, row.id, rid, digest, body, now=self.clock.utc_now)
                    prepared = PreparedTurn(user_id, row.id, rid, row.profile_id, claim, self.clock.monotonic_now())
                    await db.commit()
                    return prepared
                except IntegrityError as error:
                    await db.rollback()
                    if not self._expected_unique(error, 'sessions_pkey', 'sessions.id'):
                        raise
                    if creation_attempt:
                        raise WorkspaceConflict('session_busy') from error
        raise WorkspaceConflict('session_busy')

    async def retry_turn(self, *, user_id, session_id, request_id, expected_attempt, expected_state_version,
                         disconnect_event=None):
        prepared = None
        try:
            async with self.session_factory() as db:
                row = await self._owned(db, user_id, session_id)
                claim = await ChatRequestStore(db).retry(user_id, session_id, request_id, expected_attempt,
                    expected_state_version, now=self.clock.utc_now)
                prepared = PreparedTurn(user_id, session_id, request_id, row.profile_id, claim, self.clock.monotonic_now())
                await db.commit()
            return await self.run_claim(prepared, disconnect_event=disconnect_event)
        except asyncio.CancelledError:
            if prepared is not None:
                async def cleanup():
                    try:
                        # 原事务已退出；管理commit的实际结果只能由独立连接确认。
                        async with self.session_factory() as db:
                            session = await self._owned(db, user_id, session_id)
                            current = await ChatRequestStore(db).get(user_id, session_id, request_id)
                            owned = (current is not None and current.status == 'running'
                                and current.attempt == prepared.claim.attempt
                                and session.active_request_id == request_id)
                        if owned:
                            await self.cancel_owned(prepared)
                    except Exception:
                        logger.exception('cancelled retry outcome could not be confirmed: %s', request_id)
                from anyio import CancelScope
                with CancelScope(shield=True):
                    await asyncio.shield(cleanup())
            raise

    async def load_turn_context(self, prepared):
        async with self.session_factory() as db:
            service = SessionService(db)
            snapshot = await service.load_snapshot(prepared.user_id, prepared.session_id)
            if (snapshot.session.state_version != prepared.claim.base_state_version
                    or snapshot.session.active_request_id != prepared.request_id
                    or snapshot.session.profile_id != prepared.profile_id):
                raise WorkspaceConflict('stale_context')
            pending = next((item for item in snapshot.pending_requests if item.request_id == prepared.request_id), None)
            if pending is None or pending.attempt != prepared.claim.attempt or pending.status != 'running':
                raise WorkspaceConflict('attempt_conflict')
            if pending.lease_until is None or pending.lease_until <= utc_now(self.clock.utc_now()):
                raise WorkspaceConflict('lease_expired')
            messages = await service.load_messages(prepared.user_id, prepared.session_id)
            graph = MasteryGraph(prepared.user_id, SQLAlchemyMasteryStore(db))
            await graph.load()
            await db.rollback()
        return TurnInput(snapshot, messages, graph, None, prepared)

    def run_turn(self, loaded, on_event):
        result = self.runner(loaded.prepared.session_id, loaded.prepared.user_id,
            loaded.prepared.claim.request_payload['message'], None, loaded.graph, on_event)
        return TurnOutcome(result, False, (), loaded.graph)

    @staticmethod
    def _response(prepared, claim):
        if claim.status == 'completed' and claim.response_json is not None:
            return ChatResponse.model_validate(claim.response_json)
        return ChatResponse(reply='', session_id=prepared.session_id, request_id=prepared.request_id,
            active_node_id=claim.request_payload.get('active_node_id'), status=claim.status, attempt=claim.attempt,
            error_code=claim.error_code, persisted=False, stack='new')

    async def _read_claim(self, prepared):
        async with self.session_factory() as db:
            await self._owned(db, prepared.user_id, prepared.session_id)
            row = await ChatRequestStore(db).get(prepared.user_id, prepared.session_id, prepared.request_id)
            return ChatRequestStore._claim(row) if row else None

    async def _interrupt(self, prepared, reason, status='interrupted'):
        async with self.session_factory() as db:
            await self._owned(db, prepared.user_id, prepared.session_id)
            store = ChatRequestStore(db)
            row = await store.get(prepared.user_id, prepared.session_id, prepared.request_id)
            if row is None:
                return None
            if row.status == 'running' and row.attempt == prepared.claim.attempt:
                claim = await store.interrupt(prepared.user_id, prepared.session_id, prepared.request_id,
                    prepared.claim.attempt, status=status, error_code=reason, now=self.clock.utc_now)
                await db.commit()
                return claim
            return store._claim(row)

    async def cancel_owned(self, prepared, reason='client_disconnected'):
        if not prepared.claim.acquired:
            return prepared.claim
        execution = self.executions.get(prepared.key)
        if execution is not None:
            execution.closed.set()
        claim = await self._interrupt(prepared, reason)
        if execution is not None and execution.generation is not None and not execution.generation.done():
            execution.generation.cancel()
            await asyncio.gather(execution.generation, return_exceptions=True)
        return claim

    async def _commit(self, prepared, outcome):
        async with self.session_factory() as db:
            try:
                if self.clock.monotonic_now() >= prepared.started + 300:
                    raise WorkspaceConflict('deadline_exceeded')
                committed = await turn_commit.commit_turn(db, user_id=prepared.user_id, session_id=prepared.session_id,
                    request_id=prepared.request_id, attempt=prepared.claim.attempt,
                    base_state_version=prepared.claim.base_state_version, result=outcome.result, graph=outcome.graph,
                    context_reduced=outcome.context_reduced, reduction_reasons=outcome.reduction_reasons, now=self.clock.utc_now)
                if self.clock.monotonic_now() >= prepared.started + 300:
                    raise WorkspaceConflict('deadline_exceeded')
                await db.commit()
            except BaseException:
                await db.rollback()
                raise
        DirtyFlag.clear_dirty(prepared.user_id)
        return committed.response

    async def run_claim(self, prepared, *, on_event=None, disconnect_event=None):
        if not prepared.claim.acquired:
            return self._response(prepared, prepared.claim)
        if prepared.key in self.executions:
            return self._response(prepared, await self._read_claim(prepared))
        execution = Execution(prepared, asyncio.current_task())
        self.executions[prepared.key] = execution
        waiters = []
        loop = asyncio.get_running_loop()
        def callback(event):
            if execution.closed.is_set() or on_event is None:
                return
            try:
                loop.call_soon_threadsafe(deliver, event)
            except RuntimeError:
                pass
        def deliver(event):
            if not execution.closed.is_set() and self.executions.get(prepared.key) is execution:
                on_event(event)
        try:
            if disconnect_event is not None and disconnect_event.is_set():
                return self._response(prepared, await self.cancel_owned(prepared))
            loaded = await self.load_turn_context(prepared)
            if self.clock.monotonic_now() >= prepared.started + 300:
                return self._response(prepared, await self.cancel_owned(prepared, 'deadline_exceeded'))
            if execution.closed.is_set():
                return self._response(prepared, await self._read_claim(prepared))
            execution.generation = asyncio.create_task(asyncio.to_thread(self.run_turn, loaded, callback))
            deadline, renewal = prepared.started + 300, prepared.started + 30
            disconnect = asyncio.create_task(disconnect_event.wait()) if disconnect_event is not None else None
            if disconnect is not None:
                waiters.append(disconnect)
            while True:
                timer = asyncio.create_task(self.clock.wait_until(min(renewal, deadline)))
                waiters.append(timer)
                watching = [execution.generation, timer] + ([disconnect] if disconnect is not None else [])
                await asyncio.wait(watching, return_when=asyncio.FIRST_COMPLETED)
                timer.cancel()
                await asyncio.gather(timer, return_exceptions=True)
                if disconnect_event is not None and disconnect_event.is_set():
                    return self._response(prepared, await self.cancel_owned(prepared))
                now = self.clock.monotonic_now()
                if now >= deadline:
                    return self._response(prepared, await self.cancel_owned(prepared, 'deadline_exceeded'))
                if now >= renewal:
                    async with self.session_factory() as db:
                        await ChatRequestStore(db).renew(prepared.user_id, prepared.session_id, prepared.request_id,
                            prepared.claim.attempt, now=self.clock.utc_now)
                        await db.commit()
                    renewal = now + 30
                if execution.generation.done():
                    outcome = await execution.generation
                    break
            execution.commit = asyncio.create_task(self._commit(prepared, outcome))
            if disconnect is not None:
                done, _ = await asyncio.wait([execution.commit, disconnect], return_when=asyncio.FIRST_COMPLETED)
                if disconnect in done and disconnect_event.is_set():
                    claim = await self.cancel_owned(prepared)
                    await asyncio.gather(execution.commit, return_exceptions=True)
                    return self._response(prepared, claim)
            return await asyncio.shield(execution.commit)
        except asyncio.CancelledError:
            await asyncio.shield(self.cancel_owned(prepared))
            if execution.commit is not None:
                await asyncio.shield(asyncio.gather(execution.commit, return_exceptions=True))
            raise
        except Exception as error:
            logger.exception('teaching request failed: %s', prepared.request_id)
            DirtyFlag.mark_dirty(prepared.user_id)
            try:
                claim = await self._read_claim(prepared)
                if claim is not None and claim.status == 'completed':
                    DirtyFlag.clear_dirty(prepared.user_id)
                    return self._response(prepared, claim)
                code = getattr(error, 'code', getattr(error, 'error_code', 'turn_failed'))
                if self.clock.monotonic_now() >= prepared.started + 300:
                    code = 'deadline_exceeded'
                claim = await self._interrupt(prepared, code, 'interrupted' if code == 'deadline_exceeded' else 'failed')
            except Exception:
                logger.exception('request outcome could not be confirmed')
                return self._response(prepared, prepared.claim)
            if code == 'deadline_exceeded':
                return self._response(prepared, claim)
            if isinstance(error, OnlineRAGCompositionError):
                raise HTTPException(503, {'error_code':error.error_code, 'message':error.safe_summary}) from error
            if isinstance(error, WorkspaceConflict):
                raise HTTPException(409, {'code':error.code}) from error
            return self._response(prepared, claim)
        finally:
            execution.closed.set()
            for waiter in waiters:
                waiter.cancel()
            await asyncio.gather(*waiters, return_exceptions=True)
            if execution.generation is not None and not execution.generation.done():
                execution.generation.cancel()
                await asyncio.gather(execution.generation, return_exceptions=True)
            self.executions.pop(prepared.key, None)

    async def submit_turn(self, user_id, request, *, on_event=None, disconnect_event=None):
        prepared = await self.prepare_request(user_id, request)
        try:
            return await self.run_claim(prepared, on_event=on_event, disconnect_event=disconnect_event)
        except asyncio.CancelledError:
            await asyncio.shield(self.cancel_owned(prepared))
            raise

    async def aclose(self):
        self.closed = True
        active = list(self.executions.values())
        for execution in active:
            execution.closed.set()
        await asyncio.gather(*(self.cancel_owned(item.prepared, 'service_shutdown') for item in active), return_exceptions=True)
        tasks = [item.task for item in active if item.task is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
