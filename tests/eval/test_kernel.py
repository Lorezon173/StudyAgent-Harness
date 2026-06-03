import json
from dataclasses import asdict

import pytest

from app.eval.kernel import TestCase, EvalResult, ScenarioDefinition


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
