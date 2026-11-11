"""Workspace isolation and old/new coordination on a dedicated PostgreSQL database."""
import asyncio
import os
from uuid import uuid4

import httpx
import pytest
import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.api._persist import persist_turn
from app.core.database import Base, get_db
from app.core.security import create_access_token
from app.main import app
from app.models.tables import MessageTable, SessionTable, UserTable
from app.models.workspace_tables import TopicProfileTable

pytestmark = pytest.mark.integration


@pytest.fixture
def pg_database():
    configured = os.environ.get('WORKSPACE_TEST_DATABASE_URL')
    if not configured:
        pytest.skip('WORKSPACE_TEST_DATABASE_URL is required')
    url = make_url(configured)
    assert url.host in {'127.0.0.1', 'localhost'}
    name = 'workspace_scope_' + uuid4().hex
    maintenance = sa.create_engine(url.set(drivername='postgresql+psycopg'), isolation_level='AUTOCOMMIT')
    with maintenance.connect() as conn:
        conn.execute(sa.text(f'CREATE DATABASE "{name}"'))
    async def run(check):
        engine = create_async_engine(url.set(drivername='postgresql+asyncpg', database=name), poolclass=NullPool)
        try:
            async with engine.begin() as conn:
                await conn.execute(sa.text('CREATE EXTENSION IF NOT EXISTS vector'))
                await conn.run_sync(Base.metadata.create_all)
            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory() as db:
                db.add_all([UserTable(id=i, username=str(i), password_hash='x') for i in (1, 2)])
                await db.commit()
            await asyncio.wait_for(check(factory, engine), 30)
        finally:
            await engine.dispose()
    try:
        yield lambda check: asyncio.run(run(check))
    finally:
        with maintenance.connect() as conn:
            conn.execute(sa.text(f'DROP DATABASE "{name}"'))
        maintenance.dispose()


def test_pg_old_write_waits_for_workspace_lock_and_rejects(pg_database):
    async def check(factory, engine):
        async with factory() as db:
            db.add(TopicProfileTable(id='legacy', user_id=1, name='legacy', kind='legacy'))
            await db.flush()
            db.add(SessionTable(id='s', user_id=1, profile_id='legacy', state_json='{}'))
            await db.commit()
        async with factory() as winner, factory() as loser:
            row = await winner.scalar(sa.select(SessionTable).where(SessionTable.id == 's').with_for_update())
            pid = await loser.scalar(sa.text('SELECT pg_backend_pid()'))
            async def old_write():
                with pytest.raises(HTTPException) as rejected:
                    await persist_turn(loser, 's', 1, 'old', 'late')
                assert rejected.value.status_code == 409
                await loser.rollback()
            task = asyncio.create_task(old_write())
            deadline = asyncio.get_running_loop().time() + 8
            async with engine.connect() as observer:
                while asyncio.get_running_loop().time() < deadline:
                    await observer.execute(sa.text('SELECT pg_stat_clear_snapshot()'))
                    blocked = await observer.scalar(sa.text('SELECT cardinality(pg_blocking_pids(:pid)) > 0'), {'pid': pid})
                    if blocked:
                        break
                else:
                    raise AssertionError('PostgreSQL row-lock wait was not observed')
            row.workspace_entered = True
            await winner.commit()
            await task
        async with factory() as db:
            assert (await db.scalars(sa.select(MessageTable))).all() == []
            assert (await db.get(SessionTable, 's')).workspace_entered
    pg_database(check)


def test_two_jwt_users_same_named_profiles_are_isolated(pg_database):
    async def check(factory, engine):
        async with factory() as db:
            db.add_all([TopicProfileTable(id='p1', user_id=1, name='same'), TopicProfileTable(id='p2', user_id=2, name='same')])
            await db.commit()
        async def override():
            async with factory() as db:
                yield db
        app.dependency_overrides[get_db] = override
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                for uid, own, other in [(1, 'p1', 'p2'), (2, 'p2', 'p1')]:
                    headers = {'Authorization': f'Bearer {create_access_token(uid)}'}
                    assert (await client.get('/api/topic-profiles/' + own, headers=headers)).status_code == 200
                    assert (await client.get('/api/topic-profiles/' + other, headers=headers)).status_code == 404
        finally:
            app.dependency_overrides.pop(get_db, None)
    pg_database(check)


def test_pg_same_id_first_write_rechecks_new_claim(pg_database, monkeypatch):
    import app.api._persist as legacy
    from app.models.schemas import ChatRequest
    from app.models.workspace_tables import ChatRequestTable
    from app.orchestration.conversation_service import ConversationService

    async def check(factory, engine):
        async with factory() as db:
            db.add(TopicProfileTable(id='profile', user_id=1, name='profile', kind='normal'))
            await db.commit()
        checked, release = asyncio.Event(), asyncio.Event()
        original = legacy.ensure_session_writable
        async def pause_missing(db, session_id, user_id):
            row = await original(db, session_id, user_id)
            if row is None:
                checked.set()
                await release.wait()
            return row
        monkeypatch.setattr(legacy, 'ensure_session_writable', pause_missing)
        async def old_write():
            async with factory() as db:
                with pytest.raises(HTTPException) as rejected:
                    await legacy.persist_turn(db, 'same', 1, 'old', 'late')
                assert rejected.value.status_code == 409
        task = asyncio.create_task(old_write())
        await checked.wait()
        service = ConversationService(factory)
        prepared = await service.prepare_request(1, ChatRequest(session_id='same', request_id='new',
            profile_id='profile', message='new', expected_state_version=0))
        assert prepared.claim.acquired
        release.set()
        await task
        async with factory() as db:
            session = await db.get(SessionTable, 'same')
            assert session.workspace_entered and session.active_request_id == 'new'
            assert (await db.scalars(sa.select(MessageTable))).all() == []
            assert (await db.get(ChatRequestTable, (1, 'same', 'new'))).status == 'running'
        await service.cancel_owned(prepared)
        await service.aclose()
    pg_database(check)
