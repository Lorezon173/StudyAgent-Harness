from app.harness.observability import (
    LLMSpan, SessionStats, Observability,
    FakeObservability, ConsoleObservability, get_observability,
)


def test_llm_span_defaults():
    span = LLMSpan(model="gpt-4o-mini")
    assert span.model == "gpt-4o-mini"
    assert span.prompt_tokens == 0
    assert span.completion_tokens == 0
    assert span.total_tokens == 0
    assert span.latency_ms == 0.0
    assert span.cost_usd == 0.0
    assert span.metadata == {}


def test_session_stats_add_span():
    stats = SessionStats(session_id="s1")
    span = LLMSpan(
        model="gpt-4o-mini",
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
        latency_ms=200.0,
        cost_usd=0.0001,
        node="diagnose",
    )
    stats.add_span(span)
    assert stats.total_prompt_tokens == 100
    assert stats.total_completion_tokens == 50
    assert stats.total_tokens == 150
    assert stats.total_cost_usd == 0.0001
    assert stats.total_llm_calls == 1
    assert "diagnose" in stats.node_latencies
    assert stats.node_latencies["diagnose"] == [200.0]


def test_session_stats_multiple_spans():
    stats = SessionStats(session_id="s1")
    stats.add_span(LLMSpan(model="gpt-4o", total_tokens=100, node="a", latency_ms=100.0))
    stats.add_span(LLMSpan(model="gpt-4o", total_tokens=200, node="a", latency_ms=200.0))
    stats.add_span(LLMSpan(model="gpt-4o", total_tokens=50, node="b", latency_ms=50.0))
    assert stats.total_tokens == 350
    assert stats.total_llm_calls == 3
    assert stats.node_latencies["a"] == [100.0, 200.0]
    assert stats.node_latencies["b"] == [50.0]


def test_session_stats_summary():
    stats = SessionStats(session_id="s1")
    stats.add_span(LLMSpan(model="gpt-4o", total_tokens=100, cost_usd=0.01, node="x", latency_ms=100.0))
    stats.add_span(LLMSpan(model="gpt-4o", total_tokens=200, cost_usd=0.02, node="x", latency_ms=200.0))
    s = stats.summary()
    assert s["session_id"] == "s1"
    assert s["total_tokens"] == 300
    assert s["total_cost_usd"] == 0.03
    assert s["total_llm_calls"] == 2
    assert s["avg_node_latency_ms"]["x"] == 150.0


def test_session_stats_empty():
    stats = SessionStats(session_id="s1")
    s = stats.summary()
    assert s["total_tokens"] == 0
    assert s["total_llm_calls"] == 0
    assert s["avg_node_latency_ms"] == {}


# ── FakeObservability ──

def test_fake_obs_trace_records():
    obs = FakeObservability()
    obs.trace("s1", "diagnose", "start", {"key": "val"})
    obs.assert_traced("trace", node="diagnose", event="start")
    assert len(obs.calls) == 1


def test_fake_obs_llm_span_records():
    obs = FakeObservability()
    span = LLMSpan(model="gpt-4o", node="diagnose", session_id="s1")
    obs.llm_span(span)
    obs.assert_traced("llm_span")
    assert obs.calls[0]["span"].model == "gpt-4o"


def test_fake_obs_start_end_trace():
    obs = FakeObservability()
    tid = obs.start_trace("s1")
    assert tid == "fake-trace-id"
    obs.end_trace(tid)
    assert len(obs.calls) == 2
    assert obs.calls[0]["method"] == "start_trace"
    assert obs.calls[1]["method"] == "end_trace"


def test_fake_obs_session_summary():
    obs = FakeObservability()
    obs.start_trace("s1")
    obs.llm_span(LLMSpan(model="gpt-4o", total_tokens=100, session_id="s1"))
    stats = obs.session_summary("s1")
    assert stats is not None
    assert stats.total_tokens == 100


def test_fake_obs_session_summary_missing():
    obs = FakeObservability()
    assert obs.session_summary("nonexistent") is None


def test_fake_obs_assert_traced_failure():
    obs = FakeObservability()
    obs.trace("s1", "diagnose", "start")
    import pytest
    with pytest.raises(AssertionError, match="未找到调用"):
        obs.assert_traced("trace", node="nonexistent")


def test_fake_obs_metric_and_log():
    obs = FakeObservability()
    obs.metric("latency", 100.0, {"node": "x"})
    obs.log("info", "something_happened", {"detail": "test"})
    assert obs.calls[0]["method"] == "metric"
    assert obs.calls[1]["method"] == "log"


# ── Factory ──

def test_factory_returns_console_by_default(monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    obs = get_observability()
    assert isinstance(obs, ConsoleObservability)


def test_factory_returns_console_with_empty_keys(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "")
    obs = get_observability()
    assert isinstance(obs, ConsoleObservability)
