from app.infrastructure.llm import LLMConfig, TokenBudgetExceeded, LLMService, FakeLLM


# ── LLMConfig ──

def test_llm_config_defaults():
    cfg = LLMConfig()
    assert cfg.primary_model == "gpt-4o-mini"
    assert cfg.fallback_model == "gpt-4o-mini"
    assert cfg.max_retries == 2
    assert cfg.retry_delay == 1.0
    assert cfg.token_budget == 4096
    assert cfg.temperature == 0.7
    assert cfg.timeout == 30.0


def test_llm_config_custom():
    cfg = LLMConfig(primary_model="gpt-4o", max_retries=3, token_budget=8192)
    assert cfg.primary_model == "gpt-4o"
    assert cfg.max_retries == 3
    assert cfg.token_budget == 8192


# ── TokenBudgetExceeded ──

def test_token_budget_exceeded():
    exc = TokenBudgetExceeded(budget=4096, requested=5000)
    assert exc.budget == 4096
    assert exc.requested == 5000
    assert "4096" in str(exc)
    assert "5000" in str(exc)


# ── FakeLLM ──

def test_fake_invoke_keyword_match():
    llm = FakeLLM()
    result = llm.invoke("system", "请诊断用户理解程度")
    assert "基础了解" in result


def test_fake_invoke_default():
    llm = FakeLLM()
    result = llm.invoke("system", "随机问题")
    assert result == "默认测试回复"


def test_fake_invoke_json():
    llm = FakeLLM()
    result = llm.invoke_json("system", "请输出意图分类意图")
    assert "intent" in result


def test_fake_call_history():
    llm = FakeLLM()
    llm.invoke("system", "诊断")
    llm.invoke("system", "讲解")
    assert llm.call_count == 2


def test_fake_assert_called_with():
    llm = FakeLLM()
    llm.invoke("system", "诊断用户")
    llm.assert_called_with("诊断")


def test_fake_assert_called_with_failure():
    import pytest
    llm = FakeLLM()
    with pytest.raises(AssertionError):
        llm.assert_called_with("不存在的关键词")


def test_fake_stream():
    llm = FakeLLM()
    chunks = list(llm.stream("system", "诊断"))
    assert len(chunks) > 0
    assert "".join(chunks) == llm.RESPONSES["诊断"]


def test_fake_custom_responses():
    llm = FakeLLM(responses={"自定义": "自定义回复"})
    result = llm.invoke("system", "自定义问题")
    assert result == "自定义回复"


def test_fake_summarize_memories():
    llm = FakeLLM()
    result = llm.summarize_memories(["记忆1", "记忆2"])
    assert "2条记忆" in result


# ── Cost Calculation ──

def test_calc_cost_gpt4o_mini():
    cost = LLMService._calc_cost("gpt-4o-mini", 1000, 500)
    expected = 1000 * 0.15 / 1e6 + 500 * 0.60 / 1e6
    assert abs(cost - expected) < 1e-10


def test_calc_cost_gpt4o():
    cost = LLMService._calc_cost("gpt-4o", 1000, 500)
    expected = 1000 * 2.50 / 1e6 + 500 * 10.00 / 1e6
    assert abs(cost - expected) < 1e-10


def test_calc_cost_unknown_model():
    cost = LLMService._calc_cost("unknown-model", 1000, 500)
    assert cost == 0.0


def test_calc_cost_zero_tokens():
    cost = LLMService._calc_cost("gpt-4o-mini", 0, 0)
    assert cost == 0.0


# ── LLMService interface ──

def test_llm_service_has_interface():
    assert hasattr(LLMService, 'invoke')
    assert hasattr(LLMService, 'invoke_json')
    assert hasattr(LLMService, 'stream')
    assert hasattr(LLMService, 'summarize_memories')
