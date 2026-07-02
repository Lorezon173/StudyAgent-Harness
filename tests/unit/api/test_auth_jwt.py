"""Tests for auth endpoint changes (Task 10 / P0-③).

Verifies:
- register returns JWT token
- login returns JWT token
- login wrong password → 401
- login nonexistent user → 401
- password stored as bcrypt hash (not plaintext)
"""
from starlette.testclient import TestClient

from app.main import app
from app.core.security import verify_password


def test_register_returns_token():
    """register 返回非 null 的 JWT token。"""
    client = TestClient(app)
    resp = client.post("/api/auth/register",
                       json={"username": "token_user1", "password": "pass123"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["token"] is not None
    assert len(data["token"]) > 0


def test_login_returns_token():
    """login 返回非 null 的 JWT token。"""
    client = TestClient(app)
    client.post("/api/auth/register",
                json={"username": "token_user2", "password": "pass123"})
    resp = client.post("/api/auth/login",
                       json={"username": "token_user2", "password": "pass123"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["token"] is not None


def test_login_wrong_password_401():
    """login 错误密码 → 401。"""
    client = TestClient(app)
    client.post("/api/auth/register",
                json={"username": "token_user3", "password": "correct"})
    resp = client.post("/api/auth/login",
                       json={"username": "token_user3", "password": "wrong"})
    assert resp.status_code == 401


def test_login_nonexistent_user_401():
    """login 不存在的用户 → 401。"""
    client = TestClient(app)
    resp = client.post("/api/auth/login",
                       json={"username": "no_such_user_xyz", "password": "anything"})
    assert resp.status_code == 401


def test_password_stored_as_hash():
    """register 后密码以 bcrypt 哈希存储，非明文。"""
    import asyncio
    from app.infrastructure.storage.user_store import UserStore

    store = UserStore()  # 内存模式（与 auth.py 共享同一实例）

    async def _test():
        # 先注册（通过 API 走完整流程）
        client = TestClient(app)
        client.post("/api/auth/register",
                    json={"username": "hash_check_user", "password": "my_secret"})
        # 直接从 store 读取（auth.py 的 _store 是模块级单例）
        from app.api.auth import _store
        user = await _store.find_by_username("hash_check_user")
        assert user is not None
        stored = user["password_hash"]
        # 不是明文
        assert stored != "my_secret"
        # 是 bcrypt 哈希
        assert stored.startswith("$2b$")
        # 可以验证
        assert verify_password("my_secret", stored) is True

    asyncio.run(_test())
