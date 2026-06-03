import pytest
import yaml
from pathlib import Path

from app.eval.system_bench import SystemBench
from app.eval.kernel import ScenarioDefinition

SCENARIOS_YAML = (Path(__file__).resolve().parent.parent.parent /
                  "app/eval/scenarios/standard_scenarios.yaml")


class TestScenarioLoading:
    def test_load_yaml(self):
        bench = SystemBench()
        scenarios = bench.load_scenarios(str(SCENARIOS_YAML))
        assert len(scenarios) >= 4
        names = [s.name for s in scenarios]
        assert "零基础学习RAG" in names
        assert "前置薄弱触发回退" in names

    def test_scenario_has_process_assertions(self):
        bench = SystemBench()
        scenarios = bench.load_scenarios(str(SCENARIOS_YAML))
        sc = [s for s in scenarios if s.name == "零基础学习RAG"][0]
        assert "expected_mode_path" in sc.expected
        assert "must_contain_events" in sc.expected
        assert "must_not_contain_events" in sc.expected


class TestSystemBench:
    def test_assess_with_trace(self):
        bench = SystemBench()
        trace = [
            {"type": "TopicEntered", "source": "orchestrator"},
            {"type": "TutorExplained", "source": "tutor"},
            {"type": "MasteryAssessed", "source": "critic",
             "payload": {"level": "mastered"}},
        ]
        sc = ScenarioDefinition(
            name="test",
            expected={
                "mastery_reached": "mastered",
                "must_contain_events": ["TutorExplained"],
                "must_not_contain_events": ["ConductorRequested"],
            },
        )
        result = bench.assess(sc, trace)
        assert result["result_assertions"]["mastery_reached"] is True

    def test_assess_missing_required_event(self):
        bench = SystemBench()
        trace = [{"type": "UserMessage"}]
        sc = ScenarioDefinition(
            name="test",
            expected={"must_contain_events": ["MasteryAssessed"]},
        )
        result = bench.assess(sc, trace)
        assert result["passed"] is False
        assert "缺少必需事件" in str(result["errors"])

    def test_assess_forbidden_event_detected(self):
        bench = SystemBench()
        trace = [
            {"type": "UserMessage"},
            {"type": "ConductorRequested", "source": "orchestrator"},
        ]
        sc = ScenarioDefinition(
            name="test",
            expected={"must_not_contain_events": ["ConductorRequested"]},
        )
        result = bench.assess(sc, trace)
        assert result["passed"] is False
        assert "禁止出现" in str(result["errors"])

    def test_assess_mode_path(self):
        bench = SystemBench()
        trace = [
            {"type": "PolicyTransition",
             "payload": {"from": "Socratic", "to": "Feynman"}},
            {"type": "PolicyTransition",
             "payload": {"from": "Feynman", "to": "Analogy"}},
        ]
        sc = ScenarioDefinition(
            name="test",
            expected={"expected_mode_path": ["Socratic", "Feynman", "Analogy"]},
        )
        result = bench.assess(sc, trace)
        assert result["passed"] is True

    def test_assess_mode_path_deviation(self):
        bench = SystemBench()
        trace = [
            {"type": "PolicyTransition",
             "payload": {"from": "Socratic", "to": "Regress"}},
        ]
        sc = ScenarioDefinition(
            name="test",
            expected={"expected_mode_path": ["Socratic", "Feynman", "Analogy"]},
        )
        result = bench.assess(sc, trace)
        assert result["passed"] is False
        assert "偏离" in str(result["errors"])
