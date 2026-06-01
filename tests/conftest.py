import pytest
from app.harness.enums import Stage, Intent
from app.harness.state import LearningState


@pytest.fixture
def blank_state() -> LearningState:
    return {
        "user_input": "",
        "routing": {},
        "teaching": {},
        "retrieval": {},
        "evaluation": {},
        "memory": {},
        "meta": {"session_id": "test", "stage": Stage.INIT, "branch_trace": []},
    }


@pytest.fixture
def teach_state(blank_state) -> LearningState:
    state = blank_state.copy()
    state.update({
        "user_input": "我想学二分查找",
        "routing": {"intent": Intent.TEACH_LOOP, "intent_confidence": 0.9, "intent_source": "rule"},
        "memory": {"topic": "二分查找", "history": []},
    })
    return state


# === Plan C：LLM Mock fixture（决策 #22 — fixture+monkeypatch）===
# 用法：mock_llm_invoke_json({"tutor_ask": {...}, "critic_eval": {...}})
# 三 Agent 测试统一通过此 fixture 注入「intent → 结构化 dict」映射。
@pytest.fixture
def mock_llm_invoke_json(monkeypatch):
    def _install(intent_to_response: dict):
        def _fake_invoke_json(self, system_prompt, user_prompt,
                              session_id="", node="", intent="", **kwargs):
            return intent_to_response.get(intent, {})
        monkeypatch.setattr(
            "app.infrastructure.llm.LLMService.invoke_json",
            _fake_invoke_json,
        )
    return _install
