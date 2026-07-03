"""Tests for auth endpoint changes (Task 10 / P0-③).

Verifies:
- register returns JWT token
- login returns JWT token
- login wrong password → 401
- login nonexistent user → 401
- password stored as bcrypt hash (not plaintext)
"""
import asyncio

import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from starlette.testclient import TestClient

from app.main import app
from app.core.database import Base, get_db
from app.core.security import verify_password


@pytest.fixture()
def client():
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
            yield c, session, loop
    finally:
        app.dependency_overrides.clear()
        loop.run_until_complete(session.close())
        loop.run_until_complete(engine.dispose())
        loop.close()


def test_register_returns_token(client):
    """register 返回非 null 的 JWT token。"""
    c, _, _ = client
    resp = c.post("/api/auth/register",
                  json={"username": "token_user1", "password": "pass123"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["token"] is not None
    assert len(data["token"]) > 0


def test_login_returns_token(client):
    """login 返回非 null 的 JWT token。"""
    c, _, _ = client
    c.post("/api/auth/register",
           json={"username": "token_user2", "password": "pass123"})
    resp = c.post("/api/auth/login",
                  json={"username": "token_user2", "password": "pass123"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["token"] is not None


def test_login_wrong_password_401(client):
    """login 错误密码 → 401。"""
    c, _, _ = client
    c.post("/api/auth/register",
           json={"username": "token_user3", "password": "correct"})
    resp = c.post("/api/auth/login",
                  json={"username": "token_user3", "password": "wrong"})
    assert resp.status_code == 401


def test_login_nonexistent_user_401(client):
    """login 不存在的用户 → 401。"""
    c, _, _ = client
    resp = c.post("/api/auth/login",
                  json={"username": "no_such_user_xyz", "password": "anything"})
    assert resp.status_code == 401


def test_password_stored_as_hash(client):
    """register 后密码以 bcrypt 哈希存储，非明文。"""
    from sqlalchemy import text

    c, session, loop = client
    c.post("/api/auth/register",
           json={"username": "hash_check_user", "password": "my_secret"})

    async def _check():
        result = await session.execute(
            text("SELECT password_hash FROM users WHERE username = :u"),
            {"u": "hash_check_user"},
        )
        row = result.fetchone()
        assert row is not None
        stored = row[0]
        assert stored != "my_secret"
        assert stored.startswith("$2b$")
        assert verify_password("my_secret", stored) is True

    loop.run_until_complete(_check())
