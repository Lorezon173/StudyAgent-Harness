"""Tests for refactored sessions API with db injection."""
import asyncio

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.main import app
from app.core.database import Base, get_db
from app.infrastructure.storage.session_store import SessionStore
from app.infrastructure.storage.message_store import MessageStore


def _run(coro):
    """Run async coroutine synchronously."""
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_db_ctx():
    """Create engine + session_factory for in-memory SQLite."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, factory


def _init_and_open(engine, factory):
    """Create tables and open a session. Returns the AsyncSession."""
    async def _go():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        session = await factory().__aenter__()
        return session
    return _run(_go())


def _close_db(engine, session):
    """Close session and dispose engine."""
    async def _go():
        if session:
            await session.close()
        await engine.dispose()
    _run(_go())


async def _seed_session(session):
    store = SessionStore(session)
    await store.save("sess-1", {"foo": "bar"}, user_id=1, title="Test Session")
    await session.commit()


async def _seed_messages(session):
    store = MessageStore(session)
    await store.add("sess-msg", "user", "hello", turn_index=0)
    await store.add("sess-msg", "assistant", "hi there", turn_index=1)
    await session.commit()


def _make_client(session):
    """Create a TestClient with get_db overridden to yield the given session."""
    from starlette.testclient import TestClient

    async def _override():
        yield session

    app.dependency_overrides[get_db] = _override
    client = TestClient(app)
    return client


def _cleanup_client(client):
    """Clean up TestClient and dependency overrides."""
    client.close()
    app.dependency_overrides.clear()


# ── Tests ──


def test_list_sessions_no_user_id():
    """GET /api/sessions without user_id returns []."""
    engine, factory = _make_db_ctx()
    session = _init_and_open(engine, factory)
    try:
        client = _make_client(session)
        try:
            resp = client.get("/api/sessions")
            assert resp.status_code == 200
            assert resp.json() == []
        finally:
            _cleanup_client(client)
    finally:
        _close_db(engine, session)


def test_list_sessions_with_user_id():
    """GET /api/sessions?user_id=1 returns SessionSummary list."""
    engine, factory = _make_db_ctx()
    session = _init_and_open(engine, factory)
    try:
        _run(_seed_session(session))
        client = _make_client(session)
        try:
            resp = client.get("/api/sessions?user_id=1")
            assert resp.status_code == 200
            data = resp.json()
            assert isinstance(data, list)
            assert len(data) == 1
            assert data[0]["session_id"] == "sess-1"
            assert data[0]["title"] == "Test Session"
            assert "updated_at" in data[0]
        finally:
            _cleanup_client(client)
    finally:
        _close_db(engine, session)


def test_list_sessions_with_user_id_no_results():
    """GET /api/sessions?user_id=999 returns []."""
    engine, factory = _make_db_ctx()
    session = _init_and_open(engine, factory)
    try:
        client = _make_client(session)
        try:
            resp = client.get("/api/sessions?user_id=999")
            assert resp.status_code == 200
            assert resp.json() == []
        finally:
            _cleanup_client(client)
    finally:
        _close_db(engine, session)


def test_get_session_messages_empty():
    """GET /api/sessions/{id}/messages returns [] when no messages."""
    engine, factory = _make_db_ctx()
    session = _init_and_open(engine, factory)
    try:
        client = _make_client(session)
        try:
            resp = client.get("/api/sessions/nonexistent/messages")
            assert resp.status_code == 200
            assert resp.json() == []
        finally:
            _cleanup_client(client)
    finally:
        _close_db(engine, session)


def test_get_session_messages():
    """GET /api/sessions/{id}/messages returns MessageItem list."""
    engine, factory = _make_db_ctx()
    session = _init_and_open(engine, factory)
    try:
        _run(_seed_messages(session))
        client = _make_client(session)
        try:
            resp = client.get("/api/sessions/sess-msg/messages")
            assert resp.status_code == 200
            data = resp.json()
            assert isinstance(data, list)
            assert len(data) == 2
            assert data[0]["role"] == "user"
            assert data[0]["content"] == "hello"
            assert data[1]["role"] == "assistant"
            assert data[1]["content"] == "hi there"
        finally:
            _cleanup_client(client)
    finally:
        _close_db(engine, session)


def test_get_session_not_found():
    """GET /api/sessions/{id} returns 404."""
    engine, factory = _make_db_ctx()
    session = _init_and_open(engine, factory)
    try:
        client = _make_client(session)
        try:
            resp = client.get("/api/sessions/nonexistent")
            assert resp.status_code == 404
        finally:
            _cleanup_client(client)
    finally:
        _close_db(engine, session)


def test_get_session_found():
    """GET /api/sessions/{id} returns SessionResponse."""
    engine, factory = _make_db_ctx()
    session = _init_and_open(engine, factory)
    try:
        _run(_seed_session(session))
        client = _make_client(session)
        try:
            resp = client.get("/api/sessions/sess-1")
            assert resp.status_code == 200
            data = resp.json()
            assert data["session_id"] == "sess-1"
            assert data["user_id"] == 1
        finally:
            _cleanup_client(client)
    finally:
        _close_db(engine, session)
