from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.chat import router

_app = FastAPI()
_app.include_router(router, prefix="/api")
client = TestClient(_app)


class _FakeLegacyGraph:
    async def ainvoke(self, state, config):
        return {"teaching": {"reply": "老栈回复"},
                "evaluation": {"mastery_score": 70}}


def test_chat_flag_off_uses_legacy_stack(monkeypatch):
    """关 flag → 走老栈（app_old 图）；新栈代码不被触及。"""
    monkeypatch.delenv("FEATURE_USE_NEW_AGENT_GRAPH", raising=False)
    monkeypatch.setattr("app.api.chat._graph", _FakeLegacyGraph())
    resp = client.post("/api/chat", json={"message": "在吗", "session_id": "c-off"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["stack"] == "legacy"
    assert data["reply"] == "老栈回复"
    assert data["mastery_score"] == 70


def test_chat_flag_on_uses_new_stack(monkeypatch, mock_llm_invoke_json):
    """开 flag → 走新栈 5 Agent 协作环。"""
    monkeypatch.setenv("FEATURE_USE_NEW_AGENT_GRAPH", "true")
    mock_llm_invoke_json({
        "tutor_ask": {"content": "你怎么理解 RAG？"},
        "critic_assess": {"mastery_level": "partial", "mastery_score": 55},
        "tutor_request_recap": {"content": "请复述 RAG"},
    })
    resp = client.post("/api/chat",
                       json={"message": "帮我理解 RAG", "session_id": "c-on",
                             "user_id": 7})
    assert resp.status_code == 200
    data = resp.json()
    assert data["stack"] == "new"
    assert data["reply"]                       # 非空
    assert data["mastery_score"] == 55
    assert data["turn_count"] is not None
    assert data["mode_path"][0] == "Socratic"
