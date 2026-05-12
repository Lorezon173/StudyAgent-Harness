import logging
from app.harness.observability import Observability, get_observability


def test_trace_logs(caplog):
    obs = Observability()
    with caplog.at_level(logging.INFO):
        obs.trace("session1", "diagnose", "start", {"key": "val"})
    assert any("session1" in r.message for r in caplog.records)


def test_metric_logs(caplog):
    obs = Observability()
    with caplog.at_level(logging.INFO):
        obs.metric("latency_ms", 150.0, {"node": "diagnose"})
    assert any("latency_ms" in r.message for r in caplog.records)


def test_get_observability_singleton():
    obs1 = get_observability()
    obs2 = get_observability()
    assert obs1 is obs2
