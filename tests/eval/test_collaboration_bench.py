import pytest

from app.eval.collaboration_bench import (
    compute_collaboration_metrics,
    build_causal_tree,
    compute_violation_rate,
    compute_efficiency,
    compute_decision_stability,
    compute_conflict_resolution,
    compute_causal_chain_quality,
    compute_trajectory_deviation,
)
from app.harness.events import Event
from app.harness.enums import EventType, EventSource


class TestBuildCausalTree:
    def test_basic_chain(self):
        events = [
            Event(type=EventType.USER_MESSAGE, source=EventSource.USER,
                  session_id="s1", id="ev1"),
            Event(type=EventType.MASTERY_ASSESSED, source=EventSource.CRITIC,
                  session_id="s1", id="ev2", parent_id="ev1"),
            Event(type=EventType.GRAPH_PREREQ_WEAK_DETECTED,
                  source=EventSource.CURATOR, session_id="s1",
                  id="ev3", parent_id="ev2"),
        ]
        tree = build_causal_tree(events)
        assert "ev1" in tree
        assert "ev2" in tree["ev1"]["children"]
        assert "ev3" in tree["ev2"]["children"]

    def test_orphan_detection(self):
        events = [
            Event(type=EventType.USER_MESSAGE, source=EventSource.USER,
                  session_id="s1", id="ev1"),
            Event(type=EventType.TUTOR_ASKED, source=EventSource.TUTOR,
                  session_id="s1", id="ev2"),
        ]
        tree = build_causal_tree(events)
        orphans = [eid for eid, node in tree.items()
                   if node["parent"] is None
                   and node["event"].type != EventType.USER_MESSAGE]
        assert len(orphans) == 1


class TestCollaborationMetrics:
    @pytest.fixture
    def sample_events(self):
        return [
            Event(type=EventType.USER_MESSAGE, source=EventSource.USER,
                  session_id="s1", id="e1"),
            Event(type=EventType.MASTERY_ASSESSED, source=EventSource.CRITIC,
                  session_id="s1", id="e2", parent_id="e1"),
            Event(type=EventType.ORCHESTRATOR_TICK, source=EventSource.ORCHESTRATOR,
                  session_id="s1", id="e3"),
            Event(type=EventType.ACTION_REQUESTED, source=EventSource.ORCHESTRATOR,
                  session_id="s1", id="e4", parent_id="e3"),
            Event(type=EventType.TUTOR_EXPLAINED, source=EventSource.TUTOR,
                  session_id="s1", id="e5", parent_id="e4"),
            Event(type=EventType.USER_MESSAGE, source=EventSource.USER,
                  session_id="s1", id="e6"),
            Event(type=EventType.MASTERY_ASSESSED, source=EventSource.CRITIC,
                  session_id="s1", id="e7", parent_id="e6"),
            Event(type=EventType.LOOP_EXIT, source=EventSource.ORCHESTRATOR,
                  session_id="s1", id="e8", parent_id="e7"),
        ]

    def test_violation_rate_zero(self, sample_events):
        assert compute_violation_rate(sample_events, []) == 0.0

    def test_violation_rate_nonzero(self, sample_events):
        rate = compute_violation_rate(sample_events, ["v1", "v2"])
        assert rate == 2 / len(sample_events)

    def test_efficiency(self, sample_events):
        eff = compute_efficiency(sample_events, 2)
        assert eff["events_per_turn"] == len(sample_events) / 2
        assert "ineffective_rate" in eff
        assert 0 <= eff["ineffective_rate"] <= 1

    def test_decision_stability(self, sample_events):
        stab = compute_decision_stability(sample_events)
        assert "mode_switches" in stab
        assert "repent_rate" in stab

    def test_conflict_resolution(self, sample_events):
        cr = compute_conflict_resolution(sample_events)
        assert "conflict_rate" in cr
        assert 0 <= cr["conflict_rate"] <= 1

    def test_causal_chain_quality(self, sample_events):
        cc = compute_causal_chain_quality(sample_events)
        assert "orphan_rate" in cc
        assert 0 <= cc["orphan_rate"] <= 1
        assert "max_depth" in cc

    def test_trajectory_deviation(self, sample_events):
        td = compute_trajectory_deviation(sample_events, ["Socratic", "Feynman"])
        assert "deviation_score" in td

    def test_compute_all_metrics(self, sample_events):
        result = compute_collaboration_metrics(
            session_id="s1", events=sample_events, violation_log=[],
            expected_mode_path=["Socratic", "Feynman"])
        assert "violation_count" in result
        assert "violation_rate" in result
        assert "events_per_turn" in result
        assert "ineffective_rate" in result
        assert "mode_switches" in result
        assert "conflict_rate" in result
        assert "orphan_rate" in result
        assert "max_depth" in result
        assert "deviation_score" in result
        assert result["violation_count"] == 0
