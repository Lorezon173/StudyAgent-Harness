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


@pytest.fixture
def online_rag_composition(monkeypatch):
    """模拟在线 composition 三条件（DEC-007），使单测可走在线入口。"""
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
    monkeypatch.setattr(settings, "rag_backend", "fake")
    resp = client.post("/api/chat/stream",
                       json={"message": "帮我理解 RAG", "session_id": "e2e-fail-s"})
    assert resp.status_code == 200  # SSE 总是 200，错误在流内
    assert "RAG_BACKEND_UNAVAILABLE" in resp.text
    assert "检索服务当前不可用" in resp.text
