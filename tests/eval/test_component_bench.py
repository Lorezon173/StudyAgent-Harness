import pytest

from app.eval.component_bench import ComponentBench
from app.eval.kernel import TestCase, EvalResult
from app.harness.enums import EventSource


class FakeEvaluatable:
    """模拟实现了 evaluate 的 Agent。"""
    source = EventSource.RETRIEVER

    def evaluate(self, test_case: dict) -> dict:
        if test_case.get("query") == "fail":
            raise RuntimeError("eval crash")
        return {
            "faithfulness": test_case.get("expected_faithfulness", 0.8),
            "recall_at_k": test_case.get("expected_recall", 0.9),
        }


class TestComponentBench:
    def test_run_single_agent(self):
        bench = ComponentBench({"retriever": FakeEvaluatable()})
        cases = [
            TestCase(name="test1", component="retriever",
                     input={"query": "RAG", "expected_faithfulness": 0.8},
                     expected={"faithfulness": 0.7, "recall_at_k": 0.8}),
        ]
        results = bench.run("retriever", cases)
        assert len(results) == 1
        assert results[0].passed is True

    def test_run_all_agents(self):
        bench = ComponentBench({
            "retriever": FakeEvaluatable(),
            "tutor": FakeEvaluatable(),
        })
        cases = [
            TestCase(name="t1", component="retriever",
                     input={}, expected={}),
            TestCase(name="t2", component="tutor",
                     input={}, expected={}),
        ]
        results = bench.run_all(cases)
        assert len(results) == 2

    def test_agent_not_registered(self):
        bench = ComponentBench({})
        cases = [TestCase(name="x", component="nonexistent", input={})]
        results = bench.run("nonexistent", cases)
        assert len(results) == 1
        assert not results[0].passed
        assert "未注册" in results[0].errors[0]

    def test_format_report(self):
        bench = ComponentBench({"retriever": FakeEvaluatable()})
        cases = [
            TestCase(name="ok", component="retriever",
                     input={}, expected={}),
            TestCase(name="fail", component="retriever",
                     input={"query": "fail"}, expected={"x": 1.0}),
        ]
        results = bench.run("retriever", cases)
        report = bench.format_report(results)
        assert "ok" in report
        assert "fail" in report
        assert "PASS" in report or "FAIL" in report
