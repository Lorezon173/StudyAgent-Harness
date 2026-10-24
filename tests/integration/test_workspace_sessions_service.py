"""Task6：真实物理连接、SQLite BEGIN、PG 锁等待及归档双向对抗。"""
import asyncio
import json
import os
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import event, select, update
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.database import Base
from app.infrastructure.storage.chat_request_store import WorkspaceConflict
from app.models.tables import MessageTable, SessionTable, UserTable
from app.models.workspace_tables import ChatRequestTable, ProfileNodeTable, SessionViewStateTable, TopicProfileTable
from app.orchestration.profile_service import ProfileService
from app.orchestration.session_service import SessionService

pytestmark = pytest.mark.integration


@pytest.fixture(params=["sqlite", "postgresql"])
def database(request, tmp_path):
    maintenance = name = None
    if request.param == "sqlite":
        url = f"sqlite+aiosqlite:///{tmp_path / 'task6.db'}"
    else:
        configured = os.environ.get("WORKSPACE_TEST_DATABASE_URL")
        if not configured:
            pytest.fail("Task6真实PG验收必须设置WORKSPACE_TEST_DATABASE_URL")
        test_url = make_url(configured)
        assert test_url.host in {"127.0.0.1", "localhost"} and test_url.port == 55440
        name = "workspace_task6_" + uuid4().hex
        maintenance = sa.create_engine(test_url.set(drivername="postgresql+psycopg"), isolation_level="AUTOCOMMIT")
        with maintenance.connect() as conn:
            conn.execute(sa.text(f'CREATE DATABASE "{name}"'))
        url = test_url.set(database=name, drivername="postgresql+asyncpg")
    async def run(check):
        engine = create_async_engine(url, poolclass=NullPool)
        if request.param == "sqlite":
            @event.listens_for(engine.sync_engine, "connect")
            def fk(connection, _):
                connection.execute("PRAGMA foreign_keys=ON")
        try:
            async with engine.begin() as connection:
                if request.param == "postgresql":
                    await connection.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
                else:
                    assert await connection.scalar(sa.text("PRAGMA foreign_keys")) == 1
                await connection.run_sync(Base.metadata.create_all)
            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory() as db:
                db.add(UserTable(id=1, username="one", password_hash="x"))
                await db.commit()
            await asyncio.wait_for(check(factory, engine), 35)
        finally:
            await engine.dispose()
    try:
        yield lambda check: asyncio.run(run(check))
    finally:
        if maintenance:
            with maintenance.connect() as conn:
                conn.execute(sa.text(f'DROP DATABASE "{name}"'))
            maintenance.dispose()


async def fingerprint(connection):
    driver = await connection.run_sync(lambda conn: conn.connection.driver_connection)
    pid = await connection.scalar(sa.text("SELECT pg_backend_pid()")) if connection.dialect.name == "postgresql" else None
    return {"driver": driver, "pid": pid}


async def observe_lock(engine, blocker, waiter, task):
    async with engine.connect() as observer:
        observer_pid = await observer.scalar(sa.text("SELECT pg_backend_pid()"))
        assert observer_pid not in {blocker["pid"], waiter["pid"]}
        deadline = asyncio.get_running_loop().time() + 6
        latest = None
        while asyncio.get_running_loop().time() < deadline:
            await observer.execute(sa.text("SELECT pg_stat_clear_snapshot()"))
            latest = (await observer.execute(sa.text("SELECT pid,wait_event_type,wait_event,pg_blocking_pids(pid) AS blockers "
                "FROM pg_stat_activity WHERE pid=:pid AND datname=current_database()"), {"pid": waiter["pid"]})).mappings().one()
            if latest["wait_event_type"] == "Lock" and blocker["pid"] in latest["blockers"]:
                print("PG_LOCK_OBSERVED", engine.url.database, "blocker", blocker["pid"], "waiter", waiter["pid"],
                    "observer", observer_pid, dict(latest))
                return
            if task.done():
                break
        raise AssertionError(f"未观察到真实PG锁等待: {dict(latest) if latest else None}")


async def independent(factory, held=()):
    async with factory() as db:
        conn = await db.connection()
        fp = await fingerprint(conn)
        assert all(fp["driver"] is not prior["driver"] for prior in held)
        if fp["pid"]:
            assert all(fp["pid"] != prior["pid"] for prior in held)
        else:
            assert await conn.scalar(sa.text("PRAGMA foreign_keys")) == 1
        print("INDEPENDENT_PHYSICAL", "pid", fp["pid"], "driver", id(fp["driver"]),
            "held", [(item["pid"], id(item["driver"])) for item in held])
        return {"sessions": list((await db.scalars(select(SessionTable))).all()),
            "views": list((await db.scalars(select(SessionViewStateTable))).all()),
            "messages": list((await db.scalars(select(MessageTable))).all()),
            "requests": list((await db.scalars(select(ChatRequestTable))).all()),
            "username": await db.scalar(select(UserTable.username).where(UserTable.id == 1))}


async def seed(factory):
    async with factory() as db:
        profile = await ProfileService(db).create(1, "主题")
        pid, nid = profile.profile.id, profile.nodes[0].id
        session = await SessionService(db).create(1, pid)
        sid = session.session_id
        db.add(MessageTable(session_id=sid, role="user", content="已提交原文", turn_index=0))
        db.add(ChatRequestTable(user_id=1, session_id=sid, request_id="r", profile_id=pid,
            payload_hash="hash", request_payload={"message": "待处理原文"}, base_state_version=0, status="failed"))
        await SessionService(db).save_view_state(1, sid, 0, {"draft": "原草稿"})
        await db.commit()
        return pid, nid, sid


def test_create_and_versions_restore_on_distinct_connections_and_rollback(database):
    async def check(factory, engine):
        async with factory() as db:
            profile = await ProfileService(db).create(1, "主题")
            pid, nid = profile.profile.id, profile.nodes[0].id
            await db.commit()
        async with engine.connect() as connection:
            held = await fingerprint(connection)
            await connection.rollback()
            async with factory(bind=connection) as db:
                user = await db.get(UserTable, 1)
                user.username = "调用方"
                await db.flush()
                item = await SessionService(db).create(1, pid, active_node_id=nid)
                await SessionService(db).save_view_state(1, item.session_id, 0, {"draft": "未保存"})
                await db.rollback()
            rows = await independent(factory, [held])
            assert rows["sessions"] == rows["views"] == [] and rows["username"] == "one"
            async with factory(bind=connection) as db:
                item = await SessionService(db).create(1, pid)
                await SessionService(db).save_view_state(1, item.session_id, 0, {"draft": "保留"})
                await SessionService(db).save_workspace(1, 0, {"last_session_id": item.session_id})
                await SessionService(db).set_active_node(1, item.session_id, 0, nid)
                await db.commit()
            rows = await independent(factory, [held])
            assert len(rows["sessions"]) == 1 and rows["messages"] == []
            async with factory() as reader:
                snap = await SessionService(reader).load_snapshot(1, item.session_id)
                assert snap.session.state_version == snap.view_state.version == 1
                assert snap.teaching_state["active_node_id"] == nid and snap.view_state.draft == "保留"
                assert (await SessionService(reader).get_workspace(1)).version == 1
            async with factory(bind=connection) as db:
                with pytest.raises(WorkspaceConflict):
                    await SessionService(db).set_active_node(1, item.session_id, 0, None)
                await db.rollback()
            assert (await independent(factory, [held]))["sessions"][0].state_version == 1
    database(check)


@pytest.mark.parametrize("failure", ["create_flush", "node_flush"])
def test_failure_after_work_rolls_back_every_caller_change(database, failure):
    async def check(factory, engine):
        pid, nid, sid = await seed(factory)
        @event.listens_for(engine.sync_engine, "before_cursor_execute")
        def fail(connection, cursor, statement, parameters, context, executemany):
            sql = statement.lstrip().upper()
            if ((failure == "create_flush" and sql.startswith("INSERT INTO SESSIONS"))
                    or (failure == "node_flush" and sql.startswith("UPDATE SESSIONS"))):
                raise RuntimeError("Task6 injected failure")
        try:
            async with factory() as db:
                user = await db.get(UserTable, 1)
                user.username = "失败调用方"
                with pytest.raises(RuntimeError, match="Task6 injected failure"):
                    if failure == "create_flush":
                        await SessionService(db).create(1, pid, active_node_id=nid)
                    else:
                        await SessionService(db).set_active_node(1, sid, 0, nid)
                await db.rollback()
            rows = await independent(factory)
            assert len(rows["sessions"]) == 1 and rows["sessions"][0].active_node_id is None
            assert rows["sessions"][0].state_version == 0 and rows["username"] == "one"
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", fail)
    database(check)


def test_snapshot_session_then_profile_is_consistent_and_blocks_writer(database):
    async def check(factory, engine):
        pid, nid, sid = await seed(factory)
        postgres = engine.dialect.name == "postgresql"
        locked, attempted = asyncio.Event(), asyncio.Event()
        tasks = []
        @event.listens_for(engine.sync_engine, "before_cursor_execute")
        def attempt(connection, cursor, statement, parameters, context, executemany):
            if statement.lstrip().upper().startswith("UPDATE SESSIONS"):
                attempted.set()
        try:
            async with engine.connect() as rc, engine.connect() as wc:
                rf, wf = await fingerprint(rc), await fingerprint(wc)
                assert rf["driver"] is not wf["driver"]
                await rc.rollback()
                await wc.rollback()
                async def writer():
                    await locked.wait()
                    async with factory(bind=wc) as db:
                        row = await db.get(SessionTable, sid)
                        state = json.loads(row.state_json)
                        state["committed_turn_count"] = 1
                        await db.execute(update(SessionTable).where(SessionTable.id == sid).values(
                            state_version=1, next_turn_index=1, state_json=json.dumps(state)))
                        await db.execute(update(TopicProfileTable).where(TopicProfileTable.id == pid).values(revision=1))
                        await db.execute(update(SessionViewStateTable).where(SessionViewStateTable.session_id == sid).values(draft="新草稿", version=2))
                        await db.execute(update(ChatRequestTable).where(ChatRequestTable.session_id == sid).values(status="completed"))
                        db.add(MessageTable(session_id=sid, turn_index=1, role="assistant", content="新消息"))
                        await db.commit()
                writer_task = asyncio.create_task(writer())
                tasks.append(writer_task)
                class Paused(SessionService):
                    async def _owned(self, user_id, session_id, lock=None):
                        row = await super()._owned(user_id, session_id, lock)
                        if lock == "read":
                            if not postgres:
                                assert rf["driver"].in_transaction
                                print("SQLITE_REAL_BEGIN_SNAPSHOT", id(rf["driver"]), rf["driver"].in_transaction)
                            locked.set()
                            if postgres:
                                await observe_lock(engine, rf, wf, writer_task)
                            else:
                                await asyncio.wait_for(attempted.wait(), 8)
                        return row
                try:
                    async with factory(bind=rc) as db:
                        await db.get(UserTable, 1)
                        if not postgres:
                            assert not rf["driver"].in_transaction
                        snap = await Paused(db).load_snapshot(1, sid)
                        assert snap.session.state_version == snap.profile_summary.profile_revision == 0
                        assert snap.view_state.draft == "原草稿" and len(snap.messages.items) == 1
                        assert snap.pending_requests[0].status == "failed"
                        await db.rollback()
                    await asyncio.wait_for(writer_task, 10)
                    rows = await independent(factory, [rf, wf])
                    assert rows["sessions"][0].state_version == 1 and len(rows["messages"]) == 2
                    async with factory() as db:
                        after = await SessionService(db).load_snapshot(1, sid)
                        assert after.profile_summary.profile_revision == 1 and after.pending_requests == []
                        assert after.view_state.version == 2 and after.view_state.draft == "新草稿"
                finally:
                    await rc.rollback()
                    for task in tasks:
                        if not task.done():
                            task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", attempt)
    database(check)


@pytest.mark.parametrize("operation", ["create", "set_node"])
@pytest.mark.parametrize("first", ["archive", "session"])
def test_node_archive_checks_are_protected_until_commit_in_both_directions(database, operation, first):
    async def check(factory, engine):
        pid, nid, sid = await seed(factory)
        postgres = engine.dialect.name == "postgresql"
        # SQLite 验证检查与写入位于真实事务；PG 额外验证两方向实际行锁等待。
        if not postgres:
            class Checked(SessionService):
                async def _node(self, user_id, profile_id, node_id):
                    conn = await self.db.connection()
                    real = await conn.run_sync(lambda c: c.connection.driver_connection.in_transaction)
                    assert real
                    print("SQLITE_REAL_BEGIN_NODE_CHECK", operation, real)
                    return await super()._node(user_id, profile_id, node_id)
            async with factory() as db:
                await db.get(UserTable, 1)
                service = Checked(db)
                if operation == "create":
                    await service.create(1, pid, active_node_id=nid)
                else:
                    await service.set_active_node(1, sid, 0, nid)
                await db.rollback()
            return
        async with engine.connect() as ac, engine.connect() as sc:
            af, sf = await fingerprint(ac), await fingerprint(sc)
            assert af["pid"] != sf["pid"]
            await ac.rollback()
            await sc.rollback()
            async with factory(bind=ac) as archive_db, factory(bind=sc) as session_db:
                async def archive():
                    await ProfileService(archive_db).update_node(1, pid, nid, 0, {"archived": True})
                async def session_change():
                    service = SessionService(session_db)
                    if operation == "create":
                        return await service.create(1, pid, active_node_id=nid)
                    return await service.set_active_node(1, sid, 0, nid)
                task = None
                try:
                    if first == "archive":
                        await archive()
                        task = asyncio.create_task(session_change())
                        await observe_lock(engine, af, sf, task)
                        await archive_db.commit()
                        from fastapi import HTTPException
                        with pytest.raises(HTTPException) as error:
                            await asyncio.wait_for(task, 8)
                        assert error.value.status_code == 404
                        await session_db.rollback()
                    else:
                        await session_change()
                        task = asyncio.create_task(archive())
                        await observe_lock(engine, sf, af, task)
                        await session_db.commit()
                        await asyncio.wait_for(task, 8)
                        await archive_db.commit()
                    rows = await independent(factory, [af, sf])
                    if first == "archive":
                        assert len(rows["sessions"]) == 1 and rows["sessions"][0].state_version == 0
                        assert rows["sessions"][0].active_node_id is None
                    elif operation == "create":
                        assert len(rows["sessions"]) == 2
                    else:
                        assert rows["sessions"][0].active_node_id == nid and rows["sessions"][0].state_version == 1
                finally:
                    await archive_db.rollback()
                    await session_db.rollback()
                    if task is not None and not task.done():
                        task.cancel()
                        await asyncio.gather(task, return_exceptions=True)
    database(check)
