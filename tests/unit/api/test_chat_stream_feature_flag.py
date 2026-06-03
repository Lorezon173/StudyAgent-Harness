from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.chat_stream import router

_app = FastAPI()
_app.include_router(router, prefix="/api")
client = TestClient(_app)


class _FakeLegacyGraph:
    async def astream_events(self, state, config, version):
        yield {"event": "on_chain_end",
               "data": {"output": {"teaching": {"reply": "老栈流式回复"}}}}


def test_stream_flag_off_uses_legacy(monkeypatch):
    monkeypatch.delenv("FEATURE_USE_NEW_AGENT_GRAPH", raising=False)
    monkeypatch.setattr("app.api.chat_stream._graph", _FakeLegacyGraph())
    resp = client.post("/api/chat/stream",
                       json={"message": "hi", "session_id": "s-off"})
    assert resp.status_code == 200
    assert "老栈流式回复" in resp.text
    assert resp.text.startswith("data:")


def test_stream_flag_on_uses_new_stack(monkeypatch, mock_llm_invoke_json):
    monkeypatch.setenv("FEATURE_USE_NEW_AGENT_GRAPH", "true")
    mock_llm_invoke_json({
        "tutor_ask": {"content": "新栈引导问题"},
        "critic_assess": {},
    })
    resp = client.post("/api/chat/stream",
                       json={"message": "帮我理解 RAG", "session_id": "s-on"})
    assert resp.status_code == 200
    assert "新栈引导问题" in resp.text
    assert "data:" in resp.text
