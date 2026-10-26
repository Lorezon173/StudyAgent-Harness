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
    from app.models.tables import UserTable, SessionTable, MessageTable
    from app.models.workspace_tables import TopicProfileTable, ProfileNodeTable
    from app.harness.teaching_context import TeachingState
    from uuid import uuid4
    import json

    async def setup():
        engine, factory = await db_fixture.setup_db()
        @event.listens_for(engine.sync_engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
        await engine.dispose()
        async with factory() as db:
            db.add(UserTable(id=1, username="rag-test", password_hash="unused"))
            await db.flush()
            profile, node = str(uuid4()), str(uuid4())
            db.add(TopicProfileTable(id=profile, user_id=1, name="RAG"))
            await db.flush()
            db.add(ProfileNodeTable(id=node, profile_id=profile, title="RAG"))
            await db.flush()
            for session_id in ('sse-rag-off', "e2e-1"):
                state = TeachingState(active_node_id=node, stage="awaiting_response",last_question="previous question")
                db.add(SessionTable(id=session_id,user_id=1,profile_id=profile,active_node_id=node,state_json=json.dumps(state.to_dict()),next_turn_index=1))
                await db.flush()
                db.add_all([MessageTable(session_id=session_id,role="user",content="previous",turn_index=0),MessageTable(session_id=session_id,role="assistant",content="previous question",turn_index=0)])
            await db.commit()
        return engine, factory

    engine, factory = db_fixture.run(setup())
    from app.core.database import get_db
    from app.orchestration.conversation_service import ConversationService
    async def get_test_db():
        async with factory() as db:
            yield db
    _app.dependency_overrides[get_db] = get_test_db
    monkeypatch.setattr(_app.state, "conversation_service", ConversationService(factory), raising=False)
    yield factory
    _app.dependency_overrides.pop(get_db, None)
    db_fixture.run(_app.state.conversation_service.aclose())
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
