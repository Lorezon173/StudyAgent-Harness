import asyncio
from httpx import AsyncClient, ASGITransport

from app.main import app


def test_health():
    from starlette.testclient import TestClient
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_auth_register_and_login():
    from starlette.testclient import TestClient
    client = TestClient(app)
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
    client = TestClient(app)
    resp = client.get("/api/eval/test-session")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_profile():
    from starlette.testclient import TestClient
    client = TestClient(app)
    resp = client.get("/api/profile/1")
    assert resp.status_code == 200
    assert resp.json()["user_id"] == 1
