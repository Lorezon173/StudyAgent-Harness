"""Plan D §8 P8 验收：新旧栈指标对齐 + 一键回退。"""
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.chat import router

_app = FastAPI()
_app.include_router(router, prefix="/api")
client = TestClient(_app)

_ALIGN_KEYS = {"reply", "session_id", "mastery_score", "stack"}


class _FakeLegacyGraph:
    async def ainvoke(self, state, config):
        return {"teaching": {"reply": "老栈回复"},
                "evaluation": {"mastery_score": 60}}


def _post(msg, sid):
    return client.post("/api/chat", json={"message": msg, "session_id": sid}).json()


def test_toggle_flag_switches_stack_and_can_revert(monkeypatch, mock_llm_invoke_json):
    mock_llm_invoke_json({
        "tutor_ask": {"content": "引导问题"},
        "critic_assess": {"mastery_level": "mastered", "mastery_score": 88},
        "conductor_decide": {"action": "loop_exit", "reason": "done"},
    })

    # 开 flag → 新栈
    monkeypatch.setenv("FEATURE_USE_NEW_AGENT_GRAPH", "true")
    new = _post("帮我理解 RAG", "parity-new")
    assert new["stack"] == "new"
    assert new["reply"]

    # 关 flag → 回退老栈（同进程即时切换）
    monkeypatch.setenv("FEATURE_USE_NEW_AGENT_GRAPH", "false")
    monkeypatch.setattr("app.api.chat._graph", _FakeLegacyGraph())
    old = _post("帮我理解 RAG", "parity-old")
    assert old["stack"] == "legacy"
    assert old["reply"] == "老栈回复"


def test_both_stacks_share_aligned_schema(monkeypatch, mock_llm_invoke_json):
    """两栈输出都含对齐关键字段，且 mastery_score 类型一致（int|None）。"""
    mock_llm_invoke_json({
        "tutor_ask": {"content": "Q"},
        "critic_assess": {"mastery_level": "partial", "mastery_score": 50},
        "tutor_request_recap": {"content": "复述"},
    })
    monkeypatch.setenv("FEATURE_USE_NEW_AGENT_GRAPH", "true")
    new = _post("学习 RAG", "align-new")

    monkeypatch.setenv("FEATURE_USE_NEW_AGENT_GRAPH", "false")
    monkeypatch.setattr("app.api.chat._graph", _FakeLegacyGraph())
    old = _post("学习 RAG", "align-old")

    assert _ALIGN_KEYS <= set(new)
    assert _ALIGN_KEYS <= set(old)
    for key in _ALIGN_KEYS:
        assert key in new and key in old
    # mastery_score 两栈均为 int 或 None（对齐可比）
    assert isinstance(new["mastery_score"], (int, type(None)))
    assert isinstance(old["mastery_score"], (int, type(None)))
