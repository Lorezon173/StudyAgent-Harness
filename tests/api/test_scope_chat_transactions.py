import asyncio

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api._persist import persist_turn
from app.core.database import Base
from app.models.schemas import ChatRequest
from app.models.tables import MasteryNodeTable, MessageTable, SessionTable, UserTable
from app.models.workspace_tables import ChatRequestTable, TopicProfileTable
from app.orchestration.assembly import NewStackResult
from app.orchestration.conversation_service import ConversationService


def test_completed_replay_and_legacy_guard(tmp_path):
    async def check():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'scope.db'}")
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with factory() as db:
            db.add_all([UserTable(id=1, username='one', password_hash='x'), UserTable(id=2, username='two', password_hash='x')])
            await db.flush()
            db.add(TopicProfileTable(id='profile', user_id=1, name='legacy', kind='legacy'))
            await db.flush()
            db.add(SessionTable(id='legacy', user_id=1, profile_id='profile', state_json='{}'))
            await db.commit()
        async with factory() as db:
            assert await persist_turn(db, 'legacy', 1, 'before', 'reply') == 0
        calls = []
        def runner(sid, uid, message, topic, graph, callback):
            calls.append(message)
            graph.add_node('actual', 'Actual', mastery=42)
            return NewStackResult(reply='done', mastery_score=42, turn_count=1, mode_path=[], cost_est_usd=None)
        service = ConversationService(factory, runner=runner)
        request = ChatRequest(session_id='legacy', message='next', request_id='r1', profile_id='profile', expected_state_version=0)
        result = await service.submit_turn(1, request)
        assert result.status == 'completed' and result.persisted and result.state_version == 1
        replay = await service.submit_turn(1, request)
        assert replay.reply == 'done' and calls == ['next']
        async with factory() as db:
            assert len((await db.scalars(select(MessageTable))).all()) == 4
            assert (await db.get(MasteryNodeTable, (1, 'actual'))).mastery == 42
            assert (await db.get(ChatRequestTable, (1, 'legacy', 'r1'))).status == 'completed'
            with pytest.raises(HTTPException) as denied:
                await persist_turn(db, 'legacy', 1, 'late', 'reply')
            assert denied.value.status_code == 409
            await db.rollback()
            with pytest.raises(HTTPException) as forbidden:
                await persist_turn(db, 'legacy', 2, 'foreign', 'reply')
            assert forbidden.value.status_code == 403
        await service.aclose()
        await engine.dispose()
    asyncio.run(check())


def test_graph_and_messages_rollback_when_request_completion_fails(tmp_path, monkeypatch):
    from app.infrastructure.storage.chat_request_store import ChatRequestStore
    async def check():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'rollback.db'}")
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with factory() as db:
            db.add(UserTable(id=1, username='one', password_hash='x'))
            await db.flush()
            db.add(TopicProfileTable(id='profile', user_id=1, name='profile', kind='normal'))
            await db.flush()
            db.add(SessionTable(id='session', user_id=1, profile_id='profile', state_json='{}', workspace_entered=True))
            await db.commit()
        def runner(sid, uid, message, topic, graph, callback):
            graph.add_node('actual', 'Actual', mastery=42)
            return NewStackResult(reply='done', mastery_score=42, turn_count=1, mode_path=[], cost_est_usd=None)
        async def fail(*args, **kwargs):
            raise RuntimeError('injected completion failure')
        monkeypatch.setattr(ChatRequestStore, 'complete', fail)
        service = ConversationService(factory, runner=runner)
        response = await service.submit_turn(1, ChatRequest(session_id='session', message='message', request_id='r', profile_id='profile', expected_state_version=0))
        assert response.status == 'failed' and not response.persisted
        async with factory() as db:
            assert (await db.scalars(select(MessageTable))).all() == []
            assert await db.get(MasteryNodeTable, (1, 'actual')) is None
            session = await db.get(SessionTable, 'session')
            assert session.state_version == 0 and session.next_turn_index == 0 and session.active_request_id is None
            assert (await db.get(ChatRequestTable, (1, 'session', 'r'))).status == 'failed'
        await service.aclose()
        await engine.dispose()
    asyncio.run(check())


def test_legacy_http_and_sse_and_workspace_rejection(tmp_path, monkeypatch):
    import json

    import httpx

    import app.api.chat as chat_module
    import app.api.chat_stream as stream_module
    from app.core.database import get_db
    from app.core.security import create_access_token
    from app.main import app
    async def check():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'http.db'}")
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with factory() as db:
            db.add(UserTable(id=1, username='one', password_hash='x'))
            await db.flush()
            db.add(TopicProfileTable(id='legacy-profile', user_id=1, name='legacy', kind='legacy'))
            await db.flush()
            db.add_all([SessionTable(id='old-http', user_id=1, profile_id='legacy-profile', state_json='{}'),
                        SessionTable(id='old-sse', user_id=1, profile_id='legacy-profile', state_json='{}'),
                        SessionTable(id='entered', user_id=1, profile_id='legacy-profile', state_json='{}', workspace_entered=True)])
            await db.commit()
        async def db_override():
            async with factory() as db:
                yield db
        def runner(*args):
            return NewStackResult(reply='answer', mastery_score=40, turn_count=1, mode_path=[], cost_est_usd=None)
        monkeypatch.setattr(chat_module, 'async_session', factory)
        monkeypatch.setattr(stream_module, 'async_session', factory)
        monkeypatch.setattr('app.orchestration.assembly.run_online_agent_session', runner)
        app.dependency_overrides[get_db] = db_override
        try:
            headers={'Authorization': f'Bearer {create_access_token(1)}'}
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                response = await client.post('/api/chat', json={'session_id':'old-http','message':'hello'}, headers=headers)
                assert response.status_code == 200 and response.json()['reply'] == 'answer'
                assert 'request_id' not in response.json()
                response = await client.post('/api/chat/stream', json={'session_id':'old-sse','message':'hello'}, headers=headers)
                events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
                assert response.status_code == 200 and events[-1]['type'] == 'final' and events[-1]['persisted']
                for path in ['/api/chat', '/api/chat/stream']:
                    response = await client.post(path, json={'session_id':'entered','message':'blocked'}, headers=headers)
                    assert response.status_code == 409 and response.json()['detail']['code'] == 'workspace_session'
            async with factory() as db:
                assert len((await db.scalars(select(MessageTable))).all()) == 4
        finally:
            app.dependency_overrides.pop(get_db, None)
            await engine.dispose()
    asyncio.run(check())


def test_workspace_http_and_sse_commit_real_messages(tmp_path, monkeypatch):
    import json

    import httpx

    from app.core.database import get_db
    from app.core.security import create_access_token
    from app.main import app

    async def check():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'new-http.db'}")
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with factory() as db:
            db.add(UserTable(id=1, username='one', password_hash='x'))
            await db.flush()
            db.add(TopicProfileTable(id='p', user_id=1, name='profile', kind='normal'))
            await db.flush()
            db.add_all([SessionTable(id='http', user_id=1, profile_id='p', state_json='{}', workspace_entered=True),
                        SessionTable(id='sse', user_id=1, profile_id='p', state_json='{}', workspace_entered=True)])
            await db.commit()
        async def override():
            async with factory() as db:
                yield db
        def runner(*args):
            return NewStackResult(reply='answer', mastery_score=40, turn_count=1, mode_path=[], cost_est_usd=None)
        service = ConversationService(factory, runner=runner)
        app.state.conversation_service = service
        app.dependency_overrides[get_db] = override
        try:
            headers = {'Authorization': f'Bearer {create_access_token(1)}'}
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                body = {'session_id':'http', 'message':'hello', 'request_id':'http-r', 'profile_id':'p', 'expected_state_version':0}
                response = await client.post('/api/chat', json=body, headers=headers)
                assert response.status_code == 200 and response.json()['status'] == 'completed' and response.json()['persisted']
                response = await client.post('/api/chat/stream', json={**body, 'session_id':'sse', 'request_id':'sse-r'}, headers=headers)
                events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
                assert response.status_code == 200 and events[-1]['type'] == 'final' and events[-1]['persisted']
            async with factory() as db:
                assert len((await db.scalars(select(MessageTable))).all()) == 4
        finally:
            app.dependency_overrides.pop(get_db, None)
            del app.state.conversation_service
            await service.aclose()
            await engine.dispose()
    asyncio.run(check())


def test_legacy_stream_rejects_inflight_workspace_entry(tmp_path, monkeypatch):
    import json
    import threading

    import httpx

    import app.api.chat_stream as stream_module
    from app.core.database import get_db
    from app.core.security import create_access_token
    from app.main import app

    async def check():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'inflight.db'}")
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with factory() as db:
            db.add(UserTable(id=1, username='one', password_hash='x'))
            await db.flush()
            db.add(SessionTable(id='s', user_id=1, state_json='{}'))
            await db.commit()
        ready, release = asyncio.Event(), threading.Event()
        loop = asyncio.get_running_loop()
        def runner(*args):
            loop.call_soon_threadsafe(ready.set)
            assert release.wait(10)
            return NewStackResult(reply='late', mastery_score=40, turn_count=1, mode_path=[], cost_est_usd=None)
        async def override():
            async with factory() as db:
                yield db
        monkeypatch.setattr(stream_module, 'async_session', factory)
        monkeypatch.setattr('app.orchestration.assembly.run_online_agent_session', runner)
        app.dependency_overrides[get_db] = override
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                task = asyncio.create_task(client.post('/api/chat/stream', json={'session_id':'s','message':'old'},
                    headers={'Authorization': f'Bearer {create_access_token(1)}'}))
                await asyncio.wait_for(ready.wait(), 5)
                async with factory() as db:
                    row = await db.get(SessionTable, 's')
                    row.workspace_entered = True
                    await db.commit()
                release.set()
                response = await task
            events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
            assert events[-1]['type'] == 'error' and events[-1]['code'] == 'workspace_session'
            assert not any(event['type'] == 'final' for event in events)
            async with factory() as db:
                assert (await db.scalars(select(MessageTable))).all() == []
        finally:
            release.set()
            app.dependency_overrides.pop(get_db, None)
            await engine.dispose()
    asyncio.run(check())


def test_legacy_sparse_turn_indices_are_not_reused(tmp_path):
    async def check():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'sparse.db'}")
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with factory() as db:
            db.add(UserTable(id=1, username='one', password_hash='x'))
            await db.flush()
            db.add(TopicProfileTable(id='p', user_id=1, name='legacy', kind='legacy'))
            await db.flush()
            db.add(SessionTable(id='s', user_id=1, profile_id='p', state_json='{}', next_turn_index=9))
            await db.flush()
            db.add_all([MessageTable(session_id='s', role='user', content='a', turn_index=2),
                        MessageTable(session_id='s', role='assistant', content='b', turn_index=8)])
            await db.commit()
        async with factory() as db:
            assert await persist_turn(db, 's', 1, 'new', 'answer') == 9
        async with factory() as db:
            assert (await db.get(SessionTable, 's')).next_turn_index == 10
            assert [(m.turn_index, m.role) for m in (await db.scalars(select(MessageTable).where(MessageTable.turn_index == 9))).all()] == [(9, 'user'), (9, 'assistant')]
        await engine.dispose()
    asyncio.run(check())
