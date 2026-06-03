import pytest

from app.eval.selection_reporter import SelectionReporter


class TestSelectionReporter:
    def test_aggregate_component_results(self):
        reporter = SelectionReporter()
        component_results = [
            {"component": "retriever", "passed": 5, "total": 6,
             "metrics_avg": {"faithfulness": 0.85, "recall_at_k": 0.9}},
        ]
        report = reporter.aggregate_component(component_results)
        assert "retriever" in report
        assert report["retriever"]["pass_rate"] == 5 / 6

    def test_aggregate_system_results(self):
        reporter = SelectionReporter()
        system_results = [
            {"scenario": "zero_rag", "passed": True,
             "result_assertions": {"mastery_reached": True}},
            {"scenario": "cross_topic", "passed": False,
             "errors": ["conductor not triggered"]},
        ]
        report = reporter.aggregate_system(system_results)
        assert report["pass_rate"] == 0.5
        assert report["passed"] == 1
        assert report["total"] == 2

    def test_aggregate_collaboration_results(self):
        reporter = SelectionReporter()
        collab_results = {
            "session_1": {"violation_count": 0, "violation_rate": 0.0,
                          "events_per_turn": 8.0, "mode_switches": 2},
        }
        report = reporter.aggregate_collaboration(collab_results)
        assert report["total_sessions"] == 1
        assert report["all_violations_zero"] is True

    def test_report_to_markdown(self):
        reporter = SelectionReporter()
        markdown = reporter.to_markdown(
            component_report={"retriever": {"pass_rate": 0.9,
                                            "metrics_avg": {}}},
            system_report={"pass_rate": 0.75, "passed": 3, "total": 4},
            collaboration_report={"total_sessions": 1,
                                  "all_violations_zero": True},
            ablation_results=[{
                "experiment_name": "Curator 价值消融",
                "recommendation": "keep",
                "reason": "消融后指标变差",
                "delta": {"regress_to_prereq_trigger_rate": -15.0},
            }])
        assert "# 选型建议报告" in markdown
        assert "Curator 价值消融" in markdown
        assert "retriever" in markdown
        assert markdown.count("##") >= 1
