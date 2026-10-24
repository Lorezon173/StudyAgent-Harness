"""新栈 /api/chat/stream 端到端测试。

验证 POST /api/chat/stream → 协作环 + SSE 流式推送完整链路。

RAG-C Phase 2（C-11）：SSE 入口已切在线 composition（DEC-007），
单测需模拟在线配置（pgvector + postgres URL）方可走通正常流。
"""
import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.chat_stream import router
from app.core.config import settings
from app.core.security import get_current_user

_app = FastAPI()
_app.include_router(router, prefix="/api")
# 受保护端点鉴权：测试 override 跳过 DB 用户校验
_app.dependency_overrides[get_current_user] = lambda: {"user_id": 1}
client = TestClient(_app)


@pytest.fixture(autouse=True)
def isolated_database(db_fixture, monkeypatch):
    from sqlalchemy import event
    from app.models.tables import UserTable, SessionTable

    async def setup():
        engine, factory = await db_fixture.setup_db()
        @event.listens_for(engine.sync_engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
        await engine.dispose()
        async with factory() as db:
            db.add(UserTable(id=1, username="rag-test", password_hash="unused"))
            await db.flush()
            db.add(SessionTable(id="sse-rag-off", user_id=1, state_json="{}"))
            await db.commit()
        return engine, factory

    engine, factory = db_fixture.run(setup())
    monkeypatch.setattr("app.api.chat_stream.async_session", factory)
    yield factory
    db_fixture.run(engine.dispose())


@pytest.fixture
def online_rag_composition(monkeypatch):
    """模拟在线 composition 三条件（DEC-007），使单测可走在线入口。"""
    monkeypatch.setitem(settings.__dict__, "rag_enabled", True)
    monkeypatch.setattr(settings, "rag_backend", "pgvector")
    monkeypatch.setattr(settings, "database_url",
                        "postgresql+asyncpg://test:test@localhost:5432/test")


def test_stream_new_stack_e2e(mock_llm_invoke_json, online_rag_composition):
    """POST /api/chat/stream 走新栈，SSE 含 Tutor 引导问题。"""
    mock_llm_invoke_json({
        "tutor_ask": {"content": "新栈引导问题"},
        "critic_assess": {},
    })
    resp = client.post("/api/chat/stream",
                       json={"message": "帮我理解 RAG", "session_id": "e2e-stream"})
    assert resp.status_code == 200
    assert "新栈引导问题" in resp.text
    assert "data:" in resp.text


def test_stream_fail_fast_when_backend_not_pgvector(mock_llm_invoke_json, monkeypatch):
    """composition 校验失败 → SSE 内输出分类错误事件（不回退 fake）。"""
    monkeypatch.setitem(settings.__dict__, "rag_enabled", True)
    monkeypatch.setattr(settings, "rag_backend", "fake")
    resp = client.post("/api/chat/stream",
                       json={"message": "帮我理解 RAG", "session_id": "e2e-fail-s"})
    assert resp.status_code == 200  # SSE 总是 200，错误在流内
    assert "RAG_BACKEND_UNAVAILABLE" in resp.text
    assert "检索服务当前不可用" in resp.text


def test_stream_disabled_rag_still_teaches(mock_llm_invoke_json, monkeypatch):
    monkeypatch.setitem(settings.__dict__, "rag_enabled", False)
    def forbidden(*args, **kwargs):
        pytest.fail("禁用 RAG 时创建在线检索链")
    monkeypatch.setattr("app.orchestration.assembly.build_online_rag_coordinator", forbidden)
    mock_llm_invoke_json({"tutor_ask": {"content": "流式普通教学问题"}, "critic_assess": {}})
    response = client.post("/api/chat/stream", json={"message": "递归", "session_id": "sse-rag-off"})
    assert response.status_code == 200
    assert "流式普通教学问题" in response.text
    assert "RAG_BACKEND_UNAVAILABLE" not in response.text
    import json
    messages = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    assert next(item for item in messages if item["type"] == "final")["persisted"] is True
