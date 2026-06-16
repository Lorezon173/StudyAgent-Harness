import json
from dataclasses import asdict

import pytest

from app.eval.kernel import TestCase, EvalResult, ScenarioDefinition
from app.eval.kernel import EvalKernel

from pathlib import Path
import yaml
from app.eval.system_bench import SystemBench
from app.eval.collaboration_bench import compute_collaboration_metrics
from app.eval.ab_controller import run_ablation_experiment, AblationConfig
from app.eval.selection_reporter import SelectionReporter
from app.harness.events import Event
from app.harness.enums import EventType, EventSource


class TestDataClasses:
    def test_test_case_roundtrip(self):
        tc = TestCase(
            name="test_rag_accuracy",
            component="retriever",
            input={"query": "什么是RAG", "top_k": 3},
            expected={"recall@k": 0.8, "faithfulness": 0.7},
            meta={"source": "golden_set_v1"},
        )
        d = asdict(tc)
        restored = TestCase(**d)
        assert restored.name == tc.name
        assert restored.component == tc.component
        assert restored.input == tc.input
        assert restored.expected == tc.expected
        assert restored.meta == tc.meta

    def test_eval_result_roundtrip(self):
        r = EvalResult(
            test_name="test_rag",
            component="retriever",
            passed=True,
            metrics={"faithfulness": 0.85, "recall_at_k": 0.9},
            errors=[],
            meta={"latency_ms": 45.2},
        )
        d = asdict(r)
        restored = EvalResult(**d)
        assert restored.passed is True
        assert restored.metrics["faithfulness"] == 0.85

    def test_eval_result_failure(self):
        r = EvalResult(
            test_name="failing_test",
            component="critic",
            passed=False,
            metrics={},
            errors=["mastery mismatch: expected mastered, got weak"],
        )
        assert r.passed is False
        assert len(r.errors) == 1

    def test_scenario_definition_with_process_assertions(self):
        sc = ScenarioDefinition(
            name="零基础学习RAG",
            user_profile={"type": "blank"},
            topic="RAG",
            script=[{"user_input": "什么是RAG？"}],
            expected={
                "mastery_reached": "mastered",
                "max_turns": 12,
                "expected_mode_path": ["Socratic", "Feynman", "Analogy"],
                "must_contain_events": ["TutorExplained", "RetrievedEvidence"],
                "must_not_contain_events": ["ConductorRequested"],
            },
        )
        assert sc.expected.get("mastery_reached") == "mastered"
        assert "must_contain_events" in sc.expected


class TestCohensKappa:
    def test_perfect_agreement(self):
        from tests.golden.cohens_kappa import cohens_kappa
        a = ["mastered", "weak", "partial", "mastered"]
        b = ["mastered", "weak", "partial", "mastered"]
        k = cohens_kappa(a, b)
        assert k == pytest.approx(1.0, abs=0.01)

    def test_no_agreement(self):
        from tests.golden.cohens_kappa import cohens_kappa
        a = ["mastered", "mastered", "mastered"]
        b = ["weak", "weak", "weak"]
        k = cohens_kappa(a, b)
        assert k == pytest.approx(0.0, abs=0.01)

    def test_partial_agreement(self):
        from tests.golden.cohens_kappa import cohens_kappa
        a = ["mastered", "weak", "partial", "mastered", "weak"]
        b = ["mastered", "weak", "mastered", "partial", "weak"]
        k = cohens_kappa(a, b)
        assert 0.0 < k < 1.0

    def test_kappa_threshold_06(self):
        from tests.golden.cohens_kappa import cohens_kappa
        a = ["mastered", "weak", "partial", "mastered", "weak",
             "mastered", "weak", "partial", "mastered", "weak"]
        b = ["mastered", "weak", "partial", "mastered", "weak",
             "mastered", "weak", "mastered", "partial", "weak"]
        k = cohens_kappa(a, b)
        assert k >= 0.6, f"κ={k} should be >= 0.6 for 80% agreement"


class TestEvalKernel:
    def test_run_component_bench_unregistered_returns_failure(self):
        kernel = EvalKernel(agent_map={})
        results = kernel.run_component_bench(
            "tutor", [TestCase(name="x", component="tutor", input={})])
        assert len(results) == 1
        assert results[0].passed is False
        assert "未注册" in results[0].errors[0]

    def test_run_component_bench_returns_results(self):
        from app.agents.tutor import TutorAgent
        tutor = TutorAgent.__new__(TutorAgent)
        kernel = EvalKernel(agent_map={"tutor": tutor})
        test_cases = [
            TestCase(name="dummy", component="tutor", input={}),
        ]
        results = kernel.run_component_bench("tutor", test_cases)
        assert len(results) == 1
        assert results[0].test_name == "dummy"
        assert results[0].component == "tutor"

    def test_run_system_bench(self):
        kernel = EvalKernel(agent_map={})
        scenarios = [
            ScenarioDefinition(
                name="dummy_scenario",
                user_profile={"type": "blank"},
                topic="test",
                script=[{"user_input": "hello"}],
                expected={},
            ),
        ]
        results = kernel.run_system_bench(scenarios, event_store=None)
        assert len(results) == 1

    def test_run_ablation_delegates(self):
        kernel = EvalKernel(agent_map={})

        class _FakeSys:
            def run_scenario(self, name):
                return {"turns": 8, "cost_usd": 0.04}

        result = kernel.run_ablation(
            {"name": "k-ablation", "metrics_to_compare": ["turns"]},
            control_sys=_FakeSys(), treatment_sys=_FakeSys(),
            scenarios=["s1"])
        assert result["experiment_name"] == "k-ablation"
        assert result["recommendation"] in ("keep", "review")


class FakeAllAgent:
    """模拟实现了 evaluate / run_scenario 的系统对象。"""
    source = EventSource.TUTOR

    def evaluate(self, test_case: dict) -> dict:
        if test_case.get("action") == "tutor_explain":
            return {"explanation_completeness": 0.85}
        return {"result": "ok"}

    def run_scenario(self, scenario_name: str) -> dict:
        return {"mastery_reached": "mastered", "cost_usd": 0.04, "turns": 8}


class TestEndToEnd:
    """spec §5.3-§5.6 验收（旁路模式）。"""

    def test_system_bench_four_scenarios(self):
        """§5.3 四场景加载 + 评估。"""
        scenarios_path = (Path(__file__).resolve().parent.parent.parent /
                          "app/eval/scenarios/standard_scenarios.yaml")
        assert scenarios_path.exists(), "场景文件缺失"
        with open(scenarios_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        assert len(data.get("scenarios", [])) >= 4, "至少 4 场景"

        bench = SystemBench()
        scenarios = bench.load_scenarios(str(scenarios_path))
        for sc in scenarios:
            trace = [
                {"type": "TopicEntered", "source": "orchestrator"},
                {"type": "TutorExplained", "source": "tutor"},
                {"type": "MasteryAssessed", "source": "critic",
                 "payload": {"level": "mastered"}},
            ]
            result = bench.assess(sc, trace)
            assert "scenario" in result
            assert result["scenario"] == sc.name

    def test_collaboration_six_dimensions(self):
        """§5.4 协作六维指标可算（FLAT keys）。"""
        events = [
            Event(type=EventType.USER_MESSAGE, source=EventSource.USER,
                  session_id="e2e_s1", id="e2e_e1"),
            Event(type=EventType.MASTERY_ASSESSED, source=EventSource.CRITIC,
                  session_id="e2e_s1", id="e2e_e2", parent_id="e2e_e1"),
            Event(type=EventType.ORCHESTRATOR_TICK, source=EventSource.ORCHESTRATOR,
                  session_id="e2e_s1", id="e2e_e3"),
            Event(type=EventType.ACTION_REQUESTED, source=EventSource.ORCHESTRATOR,
                  session_id="e2e_s1", id="e2e_e4", parent_id="e2e_e3"),
            Event(type=EventType.LOOP_EXIT, source=EventSource.ORCHESTRATOR,
                  session_id="e2e_s1", id="e2e_e5"),
        ]
        metrics = compute_collaboration_metrics(
            session_id="e2e_s1", events=events)
        assert metrics["violation_count"] == 0
        assert "events_per_turn" in metrics
        assert "mode_switches" in metrics
        assert "conflict_rate" in metrics
        assert "orphan_rate" in metrics
        assert "deviation_score" in metrics

    def test_ablation_curator_value(self):
        """§5.5 Curator 消融实验。"""
        config = AblationConfig(
            name="Curator 价值消融",
            control={"all_agents": True},
            treatment={"disable_agent": "curator"},
            metrics_to_compare=["turns", "cost_usd"])
        result = run_ablation_experiment(
            config=config, control_sys=FakeAllAgent(),
            treatment_sys=FakeAllAgent(), scenarios=["prereq_weak_attention"])
        assert result["experiment_name"] == "Curator 价值消融"
        assert result["recommendation"] in ("keep", "review")

    def test_selection_report_markdown(self):
        """§5.6 选型报告 Markdown 产出。"""
        reporter = SelectionReporter()
        markdown = reporter.to_markdown(
            component_report={"retriever": {"pass_rate": 0.9, "passed": 5,
                                            "total": 6, "metrics_avg": {}}},
            system_report={"pass_rate": 0.75, "passed": 3, "total": 4,
                           "details": []},
            collaboration_report={"total_sessions": 1,
                                  "all_violations_zero": True,
                                  "total_violations": 0},
            ablation_results=[{
                "experiment_name": "Curator 价值消融",
                "recommendation": "keep",
                "reason": "消融后指标变差",
                "delta": {"regress": -15.0}}])
        assert "选型建议报告" in markdown
        assert markdown.count("##") >= 1
        assert len(markdown) > 100
        print("\n=== 选型建议报告样例 ===\n")
        print(markdown)


class TestGoldenTraceWiring:
    def test_golden_trace_consumable(self):
        from tests.golden.golden_traces import GOLDEN_TRACES, GOLDEN_TRACE_ZERO_RAG
        assert "zero_rag" in GOLDEN_TRACES
        assert GOLDEN_TRACE_ZERO_RAG["expected_mode_path"] == \
            ["Socratic", "Feynman", "Analogy"]
        # 黄金轨迹可作为 SystemBench 过程断言的 expected_mode_path 参考来源
        assert GOLDEN_TRACE_ZERO_RAG["expected_assessments"]["mastery_reached"] == "mastered"
