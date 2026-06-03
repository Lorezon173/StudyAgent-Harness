from app.core.feature_flags import use_new_agent_graph


def test_default_off_when_unset(monkeypatch):
    monkeypatch.delenv("FEATURE_USE_NEW_AGENT_GRAPH", raising=False)
    assert use_new_agent_graph() is False


def test_true_variants_enable(monkeypatch):
    for v in ["true", "TRUE", "True", "1", "yes", "on", "  true  "]:
        monkeypatch.setenv("FEATURE_USE_NEW_AGENT_GRAPH", v)
        assert use_new_agent_graph() is True, f"{v!r} 应启用新栈"


def test_false_variants_disable(monkeypatch):
    for v in ["false", "0", "no", "off", "", "garbage"]:
        monkeypatch.setenv("FEATURE_USE_NEW_AGENT_GRAPH", v)
        assert use_new_agent_graph() is False, f"{v!r} 应回退老栈"


def test_runtime_switchable(monkeypatch):
    """同一进程内改环境变量即时生效（不缓存）——支持运行时灰度切换。"""
    monkeypatch.setenv("FEATURE_USE_NEW_AGENT_GRAPH", "true")
    assert use_new_agent_graph() is True
    monkeypatch.setenv("FEATURE_USE_NEW_AGENT_GRAPH", "false")
    assert use_new_agent_graph() is False
