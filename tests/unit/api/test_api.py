import asyncio
from httpx import AsyncClient, ASGITransport
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from starlette.testclient import TestClient

from app.main import app
from app.core.database import Base, get_db


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


def test_sessions_empty():
    from starlette.testclient import TestClient
    client = TestClient(app)
    resp = client.get("/api/sessions")
    assert resp.status_code == 200


def test_eval_empty():
    from starlette.testclient import TestClient
    from app.core.security import get_current_user
    app.dependency_overrides[get_current_user] = lambda: {"user_id": 1}
    try:
        client = TestClient(app)
        resp = client.get("/api/eval/test-session")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_profile():
    from starlette.testclient import TestClient
    client = TestClient(app)
    resp = client.get("/api/profile/1")
    assert resp.status_code == 200
    assert resp.json()["user_id"] == 1
