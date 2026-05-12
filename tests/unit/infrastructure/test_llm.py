from app.infrastructure.llm import FakeLLM, LLMService


def test_fake_llm_invoke():
    llm = FakeLLM()
    result = llm.invoke("system", "请诊断用户理解程度")
    assert result != "默认测试回复"


def test_fake_llm_invoke_json():
    llm = FakeLLM()
    result = llm.invoke_json("system", "请输出意图分类意图")
    assert "intent" in result


def test_fake_llm_default():
    llm = FakeLLM()
    result = llm.invoke("system", "随机问题")
    assert result == "默认测试回复"


def test_llm_service_has_interface():
    assert hasattr(LLMService, 'invoke')
    assert hasattr(LLMService, 'invoke_json')
