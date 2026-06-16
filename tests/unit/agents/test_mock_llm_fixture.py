from app.infrastructure.llm import LLMService


def test_mock_llm_invoke_json_returns_mapped_response(mock_llm_invoke_json):
    mock_llm_invoke_json({"tutor_ask": {"content": "为什么 LLM 需要 RAG？"}})
    svc = LLMService()
    out = svc.invoke_json("sys", "user_prompt", intent="tutor_ask")
    assert out == {"content": "为什么 LLM 需要 RAG？"}


def test_mock_llm_invoke_json_default_when_intent_missing(mock_llm_invoke_json):
    mock_llm_invoke_json({"tutor_ask": {"content": "X"}})
    svc = LLMService()
    out = svc.invoke_json("sys", "u", intent="unknown_intent")
    assert out == {}   # 未配置的 intent → 空 dict（默认）
