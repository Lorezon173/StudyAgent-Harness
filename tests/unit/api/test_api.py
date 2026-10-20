import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.testclient import TestClient

from app.core.database import Base, get_db
from app.main import app


@pytest.fixture()
def db_client():
    """Create a TestClient with in-memory SQLite, tables pre-created."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        return await factory().__aenter__()

    loop = asyncio.new_event_loop()
    session = loop.run_until_complete(_setup())

    async def _override():
        yield session

    app.dependency_overrides[get_db] = _override
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()
        loop.run_until_complete(session.close())
        loop.run_until_complete(engine.dispose())
        loop.close()


def test_health():
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_auth_register_and_login(db_client):
    client = db_client
    resp = client.post("/api/auth/register", json={"username": "testuser", "password": "test123"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "testuser"

    resp2 = client.post("/api/auth/login", json={"username": "testuser", "password": "test123"})
    assert resp2.status_code == 200

    resp3 = client.post("/api/auth/register", json={"username": "testuser", "password": "test123"})
    assert resp3.status_code == 409


def test_knowledge_crud():
    from starlette.testclient import TestClient
    client = TestClient(app)
    resp = client.post("/api/knowledge", json={"name": "算法知识库", "description": "test"})
    assert resp.status_code == 200
    kid = resp.json()["id"]

    resp2 = client.get("/api/knowledge")
    assert resp2.status_code == 200
    assert len(resp2.json()) >= 1

    resp3 = client.delete(f"/api/knowledge/{kid}")
    assert resp3.status_code == 200


def test_sessions_empty(auth_headers):
    from starlette.testclient import TestClient
    client = TestClient(app)
    resp = client.get("/api/sessions", headers=auth_headers())
    assert resp.status_code == 200


def test_eval_empty(db_client, auth_headers):
    """GET /api/eval/{session_id} 返回 eval 列表；需 seed session 通过所有权校验。"""
    import asyncio

    from app.infrastructure.storage.session_store import SessionStore

    # db_client 已 override get_db 到一个固定 session；seed 同一 session
    loop = asyncio.new_event_loop()

    async def _seed():
        gen = app.dependency_overrides[get_db]()
        db = await gen.__anext__()
        try:
            await SessionStore(db).save("test-session", state={}, user_id=1, title="t")
            await db.commit()
        finally:
            await gen.aclose()
    loop.run_until_complete(_seed())
    loop.close()

    resp = db_client.get("/api/eval/test-session", headers=auth_headers())
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_profile(auth_headers):
    from starlette.testclient import TestClient
    client = TestClient(app)
    resp = client.get("/api/profile/", headers=auth_headers())
    assert resp.status_code == 200
    assert resp.json()["user_id"] == 1
