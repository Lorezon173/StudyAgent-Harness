from pathlib import Path

import pytest

from app.harness.orchestrator import RuleEngine, load_rules, Orchestrator
from app.harness.enums import ActionKind, MasteryLevel, EventType, EventSource
from app.harness.events import Event
from app.harness.workspace_state import WorkspaceState


def test_load_rules_from_default_path():
    rules = load_rules()
    actions = {r["action"] for r in rules}
    assert "regress_to_prereq" in actions
    assert "tutor_probe_prereq" in actions
    assert "tutor_offer_analogy" in actions
    assert "tutor_request_recap" in actions
    assert "loop_exit" in actions
    assert "retriever_expand_query" in actions
    assert "conductor_decide" in actions


def test_rule_engine_priority_prereq_observed_over_confusion():
    engine = RuleEngine(load_rules())
    action = engine.match({
        "confusion": True,
        "prereq_weak": True,
        "prereq_basis": "observed",
    })
    assert action == ActionKind.REGRESS_TO_PREREQ


def test_rule_engine_prereq_historical_routes_to_probe():
    engine = RuleEngine(load_rules())
    action = engine.match({
        "prereq_weak": True, "prereq_basis": "historical",
    })
    assert action == ActionKind.TUTOR_PROBE_PREREQ


def test_rule_engine_mastery_partial_request_recap():
    engine = RuleEngine(load_rules())
    action = engine.match({"mastery": "partial"})
    assert action == ActionKind.TUTOR_REQUEST_RECAP


def test_rule_engine_unknown_observations_fallback_to_conductor():
    engine = RuleEngine(load_rules())
    action = engine.match({})
    assert action == ActionKind.CONDUCTOR_DECIDE


def test_observation_event_buffers_and_injects_tick():
    orch = Orchestrator()
    ws = WorkspaceState(session_id="s1", user_id="u1")
    out = orch.on_event(Event(
        type=EventType.MASTERY_ASSESSED, source=EventSource.CRITIC,
        session_id="s1", payload={"level": "partial"}), ws)
    assert len(out) == 1
    assert out[0].type == EventType.ORCHESTRATOR_TICK
    assert out[0].source == EventSource.ORCHESTRATOR


def test_only_one_tick_injected_per_micro_turn():
    orch = Orchestrator()
    ws = WorkspaceState(session_id="s1", user_id="u1")
    out1 = orch.on_event(Event(
        type=EventType.MASTERY_ASSESSED, source=EventSource.CRITIC,
        session_id="s1", payload={"level": "weak"}), ws)
    out2 = orch.on_event(Event(
        type=EventType.CONFUSION_DETECTED, source=EventSource.CRITIC,
        session_id="s1", payload={"concept_a": "A", "concept_b": "B"}), ws)
    assert len(out1) == 1                          # 第一个观察注入 Tick
    assert len(out2) == 0                          # 同 micro-turn 内不再注入


def test_non_observation_event_no_buffer_no_tick():
    orch = Orchestrator()
    ws = WorkspaceState(session_id="s1", user_id="u1")
    out = orch.on_event(Event(
        type=EventType.TUTOR_ASKED, source=EventSource.TUTOR,
        session_id="s1"), ws)
    assert out == []                               # Tutor 产出不触发裁决


def test_tick_with_partial_mastery_emits_request_recap():
    orch = Orchestrator()
    ws = WorkspaceState(session_id="s1", user_id="u1")
    orch.on_event(Event(type=EventType.MASTERY_ASSESSED,
                        source=EventSource.CRITIC, session_id="s1",
                        payload={"level": "partial"}), ws)
    out = orch.on_event(Event(type=EventType.ORCHESTRATOR_TICK,
                              source=EventSource.ORCHESTRATOR,
                              session_id="s1", payload={}), ws)
    types = [e.type for e in out]
    assert EventType.ACTION_REQUESTED in types
    action_ev = next(e for e in out if e.type == EventType.ACTION_REQUESTED)
    assert action_ev.payload["action"] == "tutor_request_recap"
    assert action_ev.payload["target"] == "tutor"


def test_tick_with_prereq_observed_emits_regress():
    orch = Orchestrator()
    ws = WorkspaceState(session_id="s1", user_id="u1")
    orch.on_event(Event(type=EventType.GRAPH_PREREQ_WEAK_DETECTED,
                        source=EventSource.CURATOR, session_id="s1",
                        payload={"basis": "observed", "prereq_topic": "X"}), ws)
    out = orch.on_event(Event(type=EventType.ORCHESTRATOR_TICK,
                              source=EventSource.ORCHESTRATOR,
                              session_id="s1", payload={}), ws)
    action_ev = next(e for e in out if e.type == EventType.ACTION_REQUESTED)
    assert action_ev.payload["action"] == "regress_to_prereq"


def test_tick_with_priority_prereq_over_confusion():
    orch = Orchestrator()
    ws = WorkspaceState(session_id="s1", user_id="u1")
    orch.on_event(Event(type=EventType.CONFUSION_DETECTED,
                        source=EventSource.CRITIC, session_id="s1",
                        payload={"concept_a": "A", "concept_b": "B"}), ws)
    orch.on_event(Event(type=EventType.GRAPH_PREREQ_WEAK_DETECTED,
                        source=EventSource.CURATOR, session_id="s1",
                        payload={"basis": "observed"}), ws)
    out = orch.on_event(Event(type=EventType.ORCHESTRATOR_TICK,
                              source=EventSource.ORCHESTRATOR,
                              session_id="s1", payload={}), ws)
    action_ev = next(e for e in out if e.type == EventType.ACTION_REQUESTED)
    assert action_ev.payload["action"] == "regress_to_prereq"


def test_tick_emits_policy_transition_when_mode_changes():
    orch = Orchestrator()
    ws = WorkspaceState(session_id="s1", user_id="u1")
    orch.on_event(Event(type=EventType.MASTERY_ASSESSED,
                        source=EventSource.CRITIC, session_id="s1",
                        payload={"level": "partial"}), ws)
    out = orch.on_event(Event(type=EventType.ORCHESTRATOR_TICK,
                              source=EventSource.ORCHESTRATOR,
                              session_id="s1", payload={}), ws)
    pt = [e for e in out if e.type == EventType.POLICY_TRANSITION]
    assert len(pt) == 1
    assert pt[0].payload["from"] == "Socratic"
    assert pt[0].payload["to"] == "Feynman"


def test_tick_clears_buffer_for_next_micro_turn():
    orch = Orchestrator()
    ws = WorkspaceState(session_id="s1", user_id="u1")
    orch.on_event(Event(type=EventType.MASTERY_ASSESSED,
                        source=EventSource.CRITIC, session_id="s1",
                        payload={"level": "partial"}), ws)
    orch.on_event(Event(type=EventType.ORCHESTRATOR_TICK,
                        source=EventSource.ORCHESTRATOR, session_id="s1",
                        payload={}), ws)
    out = orch.on_event(Event(type=EventType.MASTERY_ASSESSED,
                              source=EventSource.CRITIC, session_id="s1",
                              payload={"level": "weak"}), ws)
    assert any(e.type == EventType.ORCHESTRATOR_TICK for e in out)


def test_tick_with_no_match_emits_conductor_requested():
    orch = Orchestrator()
    ws = WorkspaceState(session_id="s1", user_id="u1")
    orch.on_event(Event(type=EventType.LOW_CONFIDENCE_DETECTED,
                        source=EventSource.CRITIC, session_id="s1",
                        payload={"signal": "user_uncertain"}), ws)
    out = orch.on_event(Event(type=EventType.ORCHESTRATOR_TICK,
                              source=EventSource.ORCHESTRATOR,
                              session_id="s1", payload={}), ws)
    assert any(e.type == EventType.CONDUCTOR_REQUESTED for e in out)
    cr = next(e for e in out if e.type == EventType.CONDUCTOR_REQUESTED)
    assert "observations" in cr.payload


def test_conductor_decided_translated_to_action_requested():
    orch = Orchestrator()
    ws = WorkspaceState(session_id="s1", user_id="u1")
    decided = Event(type=EventType.CONDUCTOR_DECIDED,
                    source=EventSource.CONDUCTOR, session_id="s1",
                    payload={"action": "tutor_offer_analogy", "target": "tutor",
                             "observation_enough": True})
    out = orch.on_event(decided, ws)
    assert len(out) == 1
    assert out[0].type == EventType.ACTION_REQUESTED
    assert out[0].payload["action"] == "tutor_offer_analogy"
    assert out[0].payload["target"] == "tutor"
    assert out[0].parent_id == decided.id


def test_conductor_decided_request_observation_routes_to_critic():
    orch = Orchestrator()
    ws = WorkspaceState(session_id="s1", user_id="u1")
    decided = Event(type=EventType.CONDUCTOR_DECIDED,
                    source=EventSource.CONDUCTOR, session_id="s1",
                    payload={"action": "request_observation",
                             "target": "critic",
                             "observation_enough": False})
    out = orch.on_event(decided, ws)
    assert out[0].type == EventType.ACTION_REQUESTED
    assert out[0].payload["action"] == "request_observation"
    assert out[0].payload["target"] == "critic"


def test_conductor_decided_loop_exit_emits_loop_exit():
    orch = Orchestrator()
    ws = WorkspaceState(session_id="s1", user_id="u1")
    decided = Event(type=EventType.CONDUCTOR_DECIDED,
                    source=EventSource.CONDUCTOR, session_id="s1",
                    payload={"action": "loop_exit", "observation_enough": True})
    out = orch.on_event(decided, ws)
    assert out[0].type == EventType.LOOP_EXIT
