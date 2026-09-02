"""新栈 /api/chat 端到端测试。

验证 POST /api/chat → 5 Agent 协作环 → ChatResponse 完整链路：
mock LLM 但真实执行装配 / 协作环 / 事件提取 / 响应组装。

RAG-C Phase 2（C-11）：/api/chat 已切在线 composition 入口
（run_online_agent_session，DEC-007 三条件 fail-fast），单测需模拟
在线配置（pgvector + postgres URL）方可走通 200 路径。
"""
import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.chat import router
from app.core.config import settings
from app.core.security import get_current_user
from app.models.schemas import ChatRequest

_app = FastAPI()
_app.include_router(router, prefix="/api")
# 受保护端点鉴权：测试 override 跳过 DB 用户校验
_app.dependency_overrides[get_current_user] = lambda: {"user_id": 1}
client = TestClient(_app)


@pytest.fixture
def online_rag_composition(monkeypatch):
    """模拟在线 composition 三条件（DEC-007），使单测可走在线入口。

    database_url 仅被 PgVectorProvider 的懒连接 URL 解析消费；
    业务 async engine 在模块导入时已用 sqlite 建好，不受此 patch 影响。
    """
    monkeypatch.setattr(settings, "rag_backend", "pgvector")
    monkeypatch.setattr(settings, "database_url",
                        "postgresql+asyncpg://test:test@localhost:5432/test")


def test_chat_new_stack_e2e(mock_llm_invoke_json, online_rag_composition):
    """POST /api/chat 走新栈 5 Agent 协作环，返回对齐字段。"""
    mock_llm_invoke_json({
        "tutor_ask": {"content": "你怎么理解 RAG？"},
        "critic_assess": {"mastery_level": "partial", "mastery_score": 55},
        "tutor_request_recap": {"content": "请复述 RAG"},
    })
    resp = client.post("/api/chat",
                       json={"message": "帮我理解 RAG", "session_id": "e2e-1",
                             "user_id": 7})
    assert resp.status_code == 200
    data = resp.json()
    assert data["stack"] == "new"
    assert data["reply"]                       # 非空
    assert data["mastery_score"] == 55
    assert data["turn_count"] is not None
    assert data["mode_path"][0] == "Socratic"


def test_chat_fail_fast_when_backend_not_pgvector(mock_llm_invoke_json, monkeypatch):
    """在线 composition 校验失败 → 分类 503（DEC-007 fail-fast，不回退 fake）。"""
    monkeypatch.setattr(settings, "rag_backend", "fake")
    resp = client.post("/api/chat",
                       json={"message": "帮我理解 RAG", "session_id": "e2e-fail"})
    assert resp.status_code == 503
    detail = resp.json()["detail"]
    assert detail["error_code"] == "backend_unavailable"
    assert detail["message"] == "检索服务当前不可用"


def test_chat_request_generates_session_id_by_default():
    req = ChatRequest(message="hi")
    assert req.session_id.startswith("s-")
    assert len(req.session_id) > 2


def test_chat_requests_without_session_ids_get_distinct_sessions():
    assert ChatRequest(message="first").session_id != ChatRequest(message="second").session_id
