"""新栈 /api/chat/stream 端到端测试。

验证 POST /api/chat/stream → 协作环 + SSE 流式推送完整链路。
"""
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.chat_stream import router
from app.core.security import get_current_user

_app = FastAPI()
_app.include_router(router, prefix="/api")
# 受保护端点鉴权：测试 override 跳过 DB 用户校验
_app.dependency_overrides[get_current_user] = lambda: {"user_id": 1}
client = TestClient(_app)


def test_stream_new_stack_e2e(mock_llm_invoke_json):
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
