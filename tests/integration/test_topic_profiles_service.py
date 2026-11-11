"""真实 SQLite / 随机隔离 PostgreSQL：读快照与调用方事务边界。"""
import asyncio
import os
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import event, select, update
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.database import Base
from app.models.tables import MessageTable, SessionTable, UserTable
from app.models.workspace_tables import (
    ChatRequestTable,
    ProfileEdgeTable,
    ProfileEvidenceTable,
    ProfileNodeTable,
    TopicProfileTable,
)
from app.orchestration.profile_service import ProfileService, ProfileVersionConflict

pytestmark = pytest.mark.integration


@pytest.fixture(params=["sqlite", "postgresql"])
def database(request, tmp_path):
    maintenance = None
    database_name = None
    if request.param == "sqlite":
        url = f"sqlite+aiosqlite:///{tmp_path / 'snapshot.db'}"
    else:
        configured = os.environ.get("WORKSPACE_TEST_DATABASE_URL")
        if not configured:
            pytest.skip("需独立 WORKSPACE_TEST_DATABASE_URL；skip 不作为验收")
        test_url = make_url(configured)
        database_name = "workspace_task5_" + uuid4().hex
        maintenance = sa.create_engine(test_url.set(drivername="postgresql+psycopg"), isolation_level="AUTOCOMMIT")
        with maintenance.connect() as connection:
            connection.execute(sa.text(f'CREATE DATABASE "{database_name}"'))
        url = test_url.set(database=database_name, drivername="postgresql+asyncpg")

    async def run(check):
        engine = create_async_engine(url)
        if request.param == "sqlite":
            @event.listens_for(engine.sync_engine, "connect")
            def enable_foreign_keys(connection, _):
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
            await asyncio.wait_for(check(factory, engine), timeout=25)
        finally:
            await engine.dispose()
    try:
        yield lambda check: asyncio.run(run(check))
    finally:
        if maintenance is not None:
            with maintenance.connect() as connection:
                connection.execute(sa.text(f'DROP DATABASE "{database_name}"'))
            maintenance.dispose()


async def seed(factory):
    async with factory() as db:
        detail = await ProfileService(db).create(1, "快照")
        pid, nid = detail.profile.id, detail.nodes[0].id
        other = ProfileNodeTable(profile_id=pid, title="另一个")
        db.add(other)
        node = await db.get(ProfileNodeTable, nid)
        node.mastery = 40
        await db.flush()
        db.add(ProfileEdgeTable(profile_id=pid, from_node_id=nid, to_node_id=other.id, weight=.2))
        sid = uuid4().hex
        db.add(SessionTable(id=sid, user_id=1, profile_id=pid, state_json="{}"))
        await db.flush()
        db.add(ChatRequestTable(user_id=1, session_id=sid, request_id="r", profile_id=pid,
            payload_hash="x", request_payload={}, base_state_version=0, status="completed"))
        message = MessageTable(session_id=sid, role="user", content="原始证据", turn_index=0)
        db.add(message)
        await db.flush()
        evidence = ProfileEvidenceTable(user_id=1, profile_id=pid, node_id=nid, session_id=sid,
            request_id="r", message_id=message.id, score=40)
        db.add(evidence)
        await db.commit()
        return pid, nid, evidence.id


async def connection_fingerprint(connection):
    """在同一仍持有的连接上获取PID；返回driver强引用避免对象ID回收歧义。"""
    driver = await connection.run_sync(lambda conn: conn.connection.driver_connection)
    pid = await connection.scalar(sa.text("SELECT pg_backend_pid()")) if connection.dialect.name == "postgresql" else None
    return {"driver": driver, "pid": pid}


async def independent_read(url, profile_id=None, occupied=()):
    engine = create_async_engine(url, poolclass=NullPool)
    if engine.dialect.name == "sqlite":
        @event.listens_for(engine.sync_engine, "connect")
        def enable_foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
    try:
        async with engine.connect() as connection:
            fingerprint = await connection_fingerprint(connection)
            for held in occupied:
                assert fingerprint["driver"] is not held["driver"], "必须为独立物理driver"
                if fingerprint["pid"] is not None:
                    assert fingerprint["pid"] != held["pid"], "必须为独立PG backend"
            if connection.dialect.name == "sqlite":
                assert await connection.scalar(sa.text("PRAGMA foreign_keys")) == 1
            rows = {}
            for name, table in [("profiles", TopicProfileTable), ("nodes", ProfileNodeTable),
                                ("edges", ProfileEdgeTable), ("evidence", ProfileEvidenceTable)]:
                statement = select(table.__table__)
                if profile_id is not None:
                    statement = statement.where(table.id == profile_id) if name == "profiles" else statement.where(table.profile_id == profile_id)
                rows[name] = list((await connection.execute(statement)).mappings().all())
            rows["username"] = await connection.scalar(select(UserTable.username).where(UserTable.id == 1))
            print("independent", connection.engine.url.database, "pid", fingerprint["pid"],
                  "driver", id(fingerprint["driver"]), "held_pids", [item["pid"] for item in occupied],
                  "held_drivers", [id(item["driver"]) for item in occupied],
                  "revisions", [row["revision"] for row in rows["profiles"]])
            return rows
    finally:
        await engine.dispose()


async def observe_pg_lock(url, reader_pid, writer_pid, writer_task):
    """第三个独立backend有界查询数据库事实；无sleep或基于调度速度的推断。"""
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            observer_pid = await connection.scalar(sa.text("SELECT pg_backend_pid()"))
            assert observer_pid not in {reader_pid, writer_pid}
            deadline = asyncio.get_running_loop().time() + 6
            latest = None
            while asyncio.get_running_loop().time() < deadline:
                await connection.execute(sa.text("SELECT pg_stat_clear_snapshot()"))
                latest = (await connection.execute(sa.text(
                    "SELECT pid,wait_event_type,wait_event,pg_blocking_pids(pid) AS blockers "
                    "FROM pg_stat_activity WHERE pid=:pid AND datname=current_database()"
                ), {"pid": writer_pid})).mappings().one_or_none()
                if latest and latest["wait_event_type"] == "Lock" and reader_pid in latest["blockers"]:
                    record = dict(latest)
                    print("PG_LOCK_OBSERVED", connection.engine.url.database, "reader_pid", reader_pid,
                          "writer_pid", writer_pid, "observer_pid", observer_pid, "record", record)
                    return record
                if writer_task.done():
                    break
            raise AssertionError(f"PG writer did not enter reader lock wait: {dict(latest) if latest else None}")
    finally:
        await engine.dispose()


@pytest.mark.parametrize("method", ["get_detail", "get_summary"])
def test_reads_one_real_snapshot_while_writer_attempts_profile_cas(database, method):
    async def check(factory, engine):
        pid, nid, eid = await seed(factory)
        profile_read = asyncio.Event()
        writer_pid_ready = asyncio.Event()
        writer_attempted = asyncio.Event()
        observer_confirmed = asyncio.Event()
        reader_released = asyncio.Event()
        writer_committed = asyncio.Event()
        postgres = engine.dialect.name == "postgresql"

        @event.listens_for(engine.sync_engine, "before_cursor_execute")
        def signal_attempt(connection, cursor, statement, parameters, context, executemany):
            if statement.lstrip().upper().startswith("UPDATE TOPIC_PROFILES"):
                writer_attempted.set()

        tasks = []
        try:
            async with engine.connect() as reader_connection, engine.connect() as writer_connection:
                reader_fp = await connection_fingerprint(reader_connection)
                writer_fp = await connection_fingerprint(writer_connection)
                assert reader_fp["driver"] is not writer_fp["driver"]
                if postgres:
                    assert reader_fp["pid"] != writer_fp["pid"]
                await reader_connection.rollback()
                await writer_connection.rollback()
                writer_pid_ready.set()

                async def writer():
                    await asyncio.wait_for(profile_read.wait(), 10)
                    async with factory(bind=writer_connection) as db:
                        result = await db.execute(update(TopicProfileTable).where(
                            TopicProfileTable.id == pid, TopicProfileTable.revision == 0).values(revision=1))
                        assert result.rowcount == 1
                        await db.execute(update(ProfileNodeTable).where(ProfileNodeTable.id == nid).values(mastery=90, revision=1))
                        await db.execute(update(ProfileEdgeTable).where(ProfileEdgeTable.profile_id == pid).values(weight=.9))
                        await db.execute(update(ProfileEvidenceTable).where(ProfileEvidenceTable.id == eid).values(score=90))
                        await db.commit()
                        writer_committed.set()

                writer_task = asyncio.create_task(writer())
                tasks.append(writer_task)

                async def observer():
                    await asyncio.wait_for(profile_read.wait(), 10)
                    await asyncio.wait_for(writer_pid_ready.wait(), 10)
                    record = await observe_pg_lock(engine.url, reader_fp["pid"], writer_fp["pid"], writer_task)
                    observer_confirmed.set()
                    return record

                observer_task = asyncio.create_task(observer()) if postgres else None
                if observer_task:
                    tasks.append(observer_task)

                class PausedReader(ProfileService):
                    async def _get_owned(self, user_id, profile_id, lock="read"):
                        result = await super()._get_owned(user_id, profile_id, lock)
                        if not postgres:
                            real_transaction = await reader_connection.run_sync(
                                lambda conn: conn.connection.driver_connection.in_transaction)
                            print("SQLITE_REAL_TRANSACTION", real_transaction, "driver", id(reader_fp["driver"]))
                            assert real_transaction, "SQLite real transaction missing"
                        profile_read.set()
                        if postgres:
                            await asyncio.wait_for(observer_task, 10)
                            assert observer_confirmed.is_set()
                        else:
                            await asyncio.wait_for(writer_attempted.wait(), 10)
                        return result

                try:
                    async with factory(bind=reader_connection) as reader:
                        try:
                            assert await reader.get(UserTable, 1) is not None
                            if not postgres:
                                assert not reader_fp["driver"].in_transaction, "JWT逻辑autobegin不应伪造真实BEGIN"
                            before = await getattr(PausedReader(reader), method)(1, pid)
                            assert not writer_committed.is_set()
                            assert before.profile_revision == 0
                            assert next(node for node in before.nodes if node.id == nid).mastery == 40
                            assert before.edges[0].weight == .2
                            if method == "get_summary":
                                assert before.recent_evidence[0].score == 40
                                assert before.mastery_score == 40
                        finally:
                            await reader.rollback()
                            reader_released.set()
                    await asyncio.wait_for(writer_task, 10)
                    assert reader_released.is_set() and writer_committed.is_set()
                    after = await independent_read(engine.url, pid, [reader_fp, writer_fp])
                    assert after["profiles"][0]["revision"] == 1
                    assert next(node for node in after["nodes"] if node["id"] == nid)["mastery"] == 90
                    assert after["edges"][0]["weight"] == .9
                    assert after["evidence"][0]["score"] == 90
                finally:
                    # 观察失败/负控制同样先释放reader，再取消并收束writer，避免残留任务持锁。
                    await reader_connection.rollback()
                    reader_released.set()
                    for task in tasks:
                        if not task.done():
                            task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", signal_attempt)
    database(check)


def test_service_never_commits_caller_transaction_and_versions_persist(database):
    async def check(factory, engine):
        pid, nid, _eid = await seed(factory)
        async with engine.connect() as caller_connection:
            held = await connection_fingerprint(caller_connection)
            await caller_connection.rollback()
            async with factory(bind=caller_connection) as db:
                user = await db.get(UserTable, 1)
                user.username = "调用方未提交"
                await db.flush()
                updated = await ProfileService(db).update_node(1, pid, nid, 0, {"title": "节点改名"})
                assert updated.profile_revision == 1
                await ProfileService(db).get_summary(1, pid)
                await db.rollback()
            rolled_back = await independent_read(engine.url, pid, [held])
            assert rolled_back["username"] == "one"
            assert next(row for row in rolled_back["nodes"] if row["id"] == nid)["title"] == "快照"
            assert rolled_back["profiles"][0]["revision"] == 0
            async with factory(bind=caller_connection) as db:
                await ProfileService(db).update_profile(1, pid, 0, {"name": "已提交"})
                await db.commit()
            committed = await independent_read(engine.url, pid, [held])
            assert committed["profiles"][0]["revision"] == 1
            assert committed["profiles"][0]["name"] == "已提交"
            async with factory(bind=caller_connection) as db:
                with pytest.raises(ProfileVersionConflict):
                    await ProfileService(db).update_node(1, pid, nid, 0, {"title": "过时覆盖"})
                await db.rollback()
            unchanged = await independent_read(engine.url, pid, [held])
            assert next(row for row in unchanged["nodes"] if row["id"] == nid)["title"] == "快照"
            assert unchanged["profiles"][0]["revision"] == 1
    database(check)


def test_failed_initial_node_flush_rolls_back_profile_and_node(database):
    async def check(factory, engine):
        @event.listens_for(engine.sync_engine, "before_cursor_execute")
        def fail_node(connection, cursor, statement, parameters, context, executemany):
            if statement.lstrip().upper().startswith("INSERT INTO PROFILE_NODES"):
                raise RuntimeError("initial node failed")
        try:
            async with engine.connect() as caller_connection:
                held = await connection_fingerprint(caller_connection)
                await caller_connection.rollback()
                async with factory(bind=caller_connection) as db:
                    with pytest.raises(RuntimeError, match="initial node failed"):
                        await ProfileService(db).create(1, "失败创建")
                    await db.rollback()
                rows = await independent_read(engine.url, occupied=[held])
                assert rows["profiles"] == []
                assert rows["nodes"] == []
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", fail_node)
    database(check)
