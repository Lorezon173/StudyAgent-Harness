"""工作区 Store 的真实 SQLite 外键、版本及请求栅栏契约。"""
import asyncio
from datetime import datetime, timedelta

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models.tables import MessageTable, SessionTable, UserTable


@pytest.fixture
def workspace_db(tmp_path):
    async def run(check):
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'workspace.db'}")

        @event.listens_for(engine.sync_engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            factory = async_sessionmaker(engine, expire_on_commit=False)
            from app.models.workspace_tables import ProfileNodeTable, TopicProfileTable
            async with factory() as db:
                db.add_all([UserTable(id=i, username=str(i), password_hash="x") for i in (1, 2)])
                await db.flush()
                db.add_all([TopicProfileTable(id=f"p{i}", user_id=i, name="主题") for i in (1, 2)])
                await db.flush()
                db.add_all([ProfileNodeTable(id=f"n{i}", profile_id=f"p{i}", title="节点") for i in (1, 2)])
                await db.flush()
                db.add_all([SessionTable(id=f"s{i}", user_id=i, profile_id=f"p{i}", active_node_id=f"n{i}", state_json='{}') for i in (1, 2)])
                db.add(SessionTable(id="legacy-null", user_id=None, state_json='{}'))
                await db.commit()
            await check(factory)
        finally:
            await engine.dispose()
    return lambda check: asyncio.run(run(check))


def payload(message="原始提问", profile="p1", node="n1", version=0):
    return {"message": message, "profile_id": profile, "active_node_id": node, "base_state_version": version}


def test_claim_saves_original_before_messages_and_duplicate_never_reacquires(workspace_db):
    from app.infrastructure.storage.chat_request_store import (
        ChatRequestStore,
        WorkspaceConflict,
    )
    from app.infrastructure.storage.message_store import MessageStore

    async def check(factory):
        async with factory() as db:
            store = ChatRequestStore(db)
            first = await store.claim(1, "s1", "r1", "hash", payload())
            assert first.acquired and first.attempt == 1 and first.status == "running"
            duplicate = await store.claim(1, "s1", "r1", "hash", payload())
            assert not duplicate.acquired and duplicate.attempt == first.attempt
            assert await MessageStore(db).list_by_session("s1") == []
            await db.commit()
        async with factory() as db:
            restored = await ChatRequestStore(db).get(1, "s1", "r1")
            assert restored.request_payload == payload()
            assert restored.base_state_version == 0
            assert await ChatRequestStore(db).get(2, "s1", "r1") is None
            with pytest.raises(WorkspaceConflict, match="payload_conflict"):
                await ChatRequestStore(db).claim(1, "s1", "r1", "hash", payload("被篡改"))
    workspace_db(check)


def test_claim_owner_scope_busy_and_stale_context(workspace_db):
    from app.infrastructure.storage.chat_request_store import (
        ChatRequestStore,
        WorkspaceConflict,
    )

    async def check(factory):
        async with factory() as db:
            store = ChatRequestStore(db)
            for owner, session, body in [(2, "s1", payload()), (1, "legacy-null", payload()), (1, "s1", payload(profile="p2")), (1, "s1", payload(node="n2"))]:
                with pytest.raises(PermissionError):
                    await store.claim(owner, session, "bad", "hash", body)
            with pytest.raises(WorkspaceConflict, match="stale_context"):
                await store.claim(1, "s1", "stale", "hash", payload(version=1))
            await store.claim(1, "s1", "r1", "hash", payload())
            with pytest.raises(WorkspaceConflict, match="session_busy"):
                await store.claim(1, "s1", "r2", "hash", payload())
    workspace_db(check)


def test_attempt_fence_expiration_renew_and_explicit_retry(workspace_db):
    from app.infrastructure.storage.chat_request_store import (
        ChatRequestStore,
        WorkspaceConflict,
    )

    async def check(factory):
        now = datetime(2026, 1, 1)
        async with factory() as db:
            store = ChatRequestStore(db)
            first = await store.claim(1, "s1", "r1", "hash", payload(), now=now)
            renewed = await store.renew(1, "s1", "r1", first.attempt, now=now + timedelta(seconds=30))
            assert renewed.lease_until == now + timedelta(seconds=210)
            expired = await store.interrupt(1, "s1", "r1", first.attempt, now=now + timedelta(seconds=211), expired_only=True)
            assert expired.status == "interrupted" and expired.attempt > first.attempt
            old = await store.claim(1, "s1", "r1", "hash", payload(), now=now + timedelta(seconds=212))
            assert not old.acquired and old.status == "interrupted"
            with pytest.raises(WorkspaceConflict, match="attempt"):
                await store.complete(1, "s1", "r1", first.attempt, {"answer": "迟到"}, now=now + timedelta(seconds=212))
            retry = await store.retry(1, "s1", "r1", expired.attempt, 0, now=now + timedelta(seconds=212))
            assert retry.acquired and retry.attempt > expired.attempt and retry.request_payload == payload()
            done = await store.complete(1, "s1", "r1", retry.attempt, {"answer": "有效"}, now=now + timedelta(seconds=220))
            assert done.status == "completed"
            repeat = await store.complete(1, "s1", "r1", retry.attempt, {"answer": "不能覆盖"}, now=now + timedelta(seconds=221))
            assert repeat.response_json == {"answer": "有效"}
            assert (await db.get(SessionTable, "s1")).active_request_id is None
            await db.commit()
    workspace_db(check)


def test_failed_requests_need_explicit_retry_at_original_version(workspace_db):
    from app.infrastructure.storage.chat_request_store import (
        ChatRequestStore,
        WorkspaceConflict,
    )

    async def check(factory):
        async with factory() as db:
            store = ChatRequestStore(db)
            claim = await store.claim(1, "s1", "r1", "hash", payload())
            failed = await store.interrupt(1, "s1", "r1", claim.attempt, status="failed", error_code="model_failed")
            assert not (await store.claim(1, "s1", "r1", "hash", payload())).acquired
            session = await db.get(SessionTable, "s1")
            session.state_version = 1
            await db.flush()
            with pytest.raises(WorkspaceConflict, match="stale_context"):
                await store.retry(1, "s1", "r1", failed.attempt, 1)
    workspace_db(check)


def test_view_and_workspace_versions_do_not_overwrite_teaching_state(workspace_db):
    from app.infrastructure.storage.chat_request_store import WorkspaceConflict
    from app.infrastructure.storage.session_view_store import SessionViewStore
    from app.infrastructure.storage.workspace_store import WorkspaceStore

    async def check(factory):
        async with factory() as db:
            view = SessionViewStore(db)
            saved = await view.save(1, "s1", 0, {"draft": "草稿", "reading_anchor": {"message_id": 1, "offset": 0.5}})
            assert saved.version == 1 and saved.draft == "草稿"
            with pytest.raises(WorkspaceConflict) as error:
                await view.save(1, "s1", 0, {"draft": "过期"})
            assert error.value.status_code == 409
            with pytest.raises(PermissionError):
                await view.save(2, "s1", 0, {"draft": "非法"})
            workspace = WorkspaceStore(db)
            state = {"last_session_id": "s1", "sidebar_pinned": True, "sidebar_collapsed": False, "progress_y_ratio": 0.75}
            assert (await workspace.save(1, 0, state)).version == 1
            with pytest.raises(WorkspaceConflict):
                await workspace.save(1, 0, state)
            for ratio in (-0.1, 1.1, float("nan"), float("inf")):
                with pytest.raises(ValueError):
                    await workspace.save(1, 1, {**state, "progress_y_ratio": ratio})
            with pytest.raises(PermissionError):
                await workspace.save(1, 1, {**state, "last_session_id": "s2"})
            assert (await db.get(SessionTable, "s1")).state_version == 0
            assert (await view.get(1, "s1")).draft == "草稿"
            await db.commit()
        async with factory() as db:
            assert (await WorkspaceStore(db).get(1)).progress_y_ratio == 0.75
    workspace_db(check)


def test_session_schema1_roundtrip_messages_have_stable_ids_and_rollback(workspace_db):
    from app.infrastructure.storage.message_store import MessageStore
    from app.infrastructure.storage.session_store import SessionStore

    async def check(factory):
        async with factory() as db:
            state = {"schema_version": 1, "active_node_id": "n1", "committed_turn_count": 1}
            await SessionStore(db).save("s1", state)
            first = await MessageStore(db).add("s1", "user", "问题", 7)
            second = await MessageStore(db).add("s1", "assistant", "回复", 7)
            await db.commit()
        async with factory() as db:
            saved = await SessionStore(db).get("s1")
            assert saved["profile_id"] == "p1" and saved["state_version"] == 0
            assert saved["state_json"] and saved["active_node_id"] == "n1"
            assert [m["id"] for m in await MessageStore(db).list_by_session("s1")] == [first, second]
            with pytest.raises(ValueError, match="schema"):
                await SessionStore(db).save("s1", {"schema_version": 2})
            with pytest.raises(ValueError):
                await SessionStore(db).save("s1", {"schema_version": 1, "bad": object()})
            await MessageStore(db).add("s1", "user", "回滚", 8)
            await db.rollback()
        async with factory() as db:
            assert len(await MessageStore(db).list_by_session("s1")) == 2
    workspace_db(check)


def test_all_workspace_stores_leave_commit_and_rollback_to_caller(workspace_db):
    from app.infrastructure.storage.chat_request_store import ChatRequestStore
    from app.infrastructure.storage.session_store import SessionStore
    from app.infrastructure.storage.session_view_store import SessionViewStore
    from app.infrastructure.storage.workspace_store import WorkspaceStore
    from app.models.workspace_tables import (
        ChatRequestTable,
        SessionViewStateTable,
        UserWorkspaceStateTable,
    )

    async def check(factory):
        async with factory() as db:
            await ChatRequestStore(db).claim(1, "s1", "r1", "hash", payload())
            await SessionViewStore(db).save(1, "s1", 0, {"draft": "不要提交"})
            await WorkspaceStore(db).save(1, 0, {"last_session_id": "s1"})
            await db.rollback()
        async with factory() as db:
            assert await db.scalar(select(ChatRequestTable)) is None
            assert await db.scalar(select(SessionViewStateTable)) is None
            assert await db.scalar(select(UserWorkspaceStateTable)) is None
            assert (await db.get(SessionTable, "s1")).active_request_id is None
            await SessionStore(db).delete("legacy-null")
            await db.flush()
            await db.rollback()
        async with factory() as db:
            assert await SessionStore(db).get("legacy-null") is not None
            await SessionStore(db).delete("legacy-null")
            await db.commit()
        async with factory() as db:
            assert await SessionStore(db).get("legacy-null") is None
    workspace_db(check)


@pytest.mark.parametrize("case", ["session_profile", "session_node", "request_owner", "evidence_node", "evidence_message", "evidence_duplicate", "view_owner", "workspace_owner", "workspace_ratio", "active_request"])
def test_database_constraints_reject_cross_scope_links(workspace_db, case):
    from app.infrastructure.storage.chat_request_store import ChatRequestStore
    from app.models.workspace_tables import (
        ChatRequestTable,
        ProfileEvidenceTable,
        SessionViewStateTable,
        UserWorkspaceStateTable,
    )

    async def check(factory):
        async with factory() as db:
            request = await ChatRequestStore(db).claim(1, "s1", "r1", "hash", payload())
            assert request.acquired
            db.add_all([MessageTable(id=1, session_id="s1", role="assistant", content="一", turn_index=0),
                        MessageTable(id=2, session_id="s2", role="assistant", content="二", turn_index=0)])
            await db.flush()
            evidence = dict(user_id=1, profile_id="p1", node_id="n1", session_id="s1", request_id="r1", message_id=1, score=80, rationale="依据")
            if case == "session_profile":
                (await db.get(SessionTable, "s1")).profile_id = "p2"
            elif case == "session_node":
                (await db.get(SessionTable, "s1")).active_node_id = "n2"
            elif case == "request_owner":
                db.add(ChatRequestTable(user_id=2, session_id="s1", request_id="bad", profile_id="p1", payload_hash="x", request_payload=payload(), base_state_version=0, attempt=1, status="failed"))
            elif case.startswith("evidence"):
                if case == "evidence_duplicate":
                    db.add(ProfileEvidenceTable(**evidence))
                    await db.flush()
                if case == "evidence_node":
                    evidence["node_id"] = "n2"
                if case == "evidence_message":
                    evidence["message_id"] = 2
                db.add(ProfileEvidenceTable(**evidence))
            elif case == "view_owner":
                db.add(SessionViewStateTable(user_id=2, session_id="s1", draft=""))
            elif case == "workspace_owner":
                db.add(UserWorkspaceStateTable(user_id=1, last_session_id="s2"))
            elif case == "workspace_ratio":
                db.add(UserWorkspaceStateTable(user_id=1, progress_y_ratio=2))
            else:
                (await db.get(SessionTable, "s2")).active_request_id = "r1"
            with pytest.raises(IntegrityError):
                await db.flush()
            await db.rollback()
        async with factory() as db:
            assert (await db.get(SessionTable, "s1")).active_request_id is None
            assert await db.scalar(select(ChatRequestTable)) is None
    workspace_db(check)
