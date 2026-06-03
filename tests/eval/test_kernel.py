import json
from dataclasses import asdict

import pytest

from app.eval.kernel import TestCase, EvalResult, ScenarioDefinition
from app.eval.kernel import EvalKernel


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
    def test_run_component_bench_requires_agent_map(self):
        kernel = EvalKernel(agent_map={})
        with pytest.raises(ValueError, match="ComponentBench 无注册 Agent"):
            kernel.run_component_bench("tutor", [])

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
