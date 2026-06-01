from pathlib import Path

import pytest

from app.harness.orchestrator import RuleEngine, load_rules
from app.harness.enums import ActionKind, MasteryLevel


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
