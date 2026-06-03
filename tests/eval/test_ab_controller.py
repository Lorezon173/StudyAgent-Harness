import pytest

from app.eval.ab_controller import (
    run_parameter_ab,
    run_ablation_experiment,
    AblationConfig,
)


class FakeSystem:
    """模拟可运行的系统用于 A/B 测试。"""
    def __init__(self, name="default"):
        self.name = name

    def run_scenario(self, scenario_name: str) -> dict:
        if self.name == "slow":
            return {"mastery_reached": "mastered", "cost_usd": 0.15, "turns": 15}
        return {"mastery_reached": "mastered", "cost_usd": 0.05, "turns": 8}


class TestABController:
    def test_parameter_ab(self):
        control = FakeSystem("fast")
        treatment = FakeSystem("slow")
        scenarios = ["zero_rag", "confused_basics"]
        result = run_parameter_ab(
            control=control, treatment=treatment, scenarios=scenarios,
            metrics_to_compare=["mastery_reached", "cost_usd", "turns"],
            experiment_name="Tutor LLM upgrade")
        assert result["experiment_name"] == "Tutor LLM upgrade"
        assert len(result["scenarios"]) == 2
        assert "control" in result
        assert "treatment" in result
        assert "delta" in result

    def test_ablation_experiment_curator(self):
        config = AblationConfig(
            name="Curator 价值消融",
            control={"all_agents": True},
            treatment={"disable_agent": "curator"},
            metrics_to_compare=["regress_to_prereq_trigger_rate",
                               "mastery_reached", "mode_path_deviation"])
        control_sys = FakeSystem("with_curator")
        treatment_sys = FakeSystem("without_curator")
        result = run_ablation_experiment(
            config=config, control_sys=control_sys,
            treatment_sys=treatment_sys, scenarios=["prereq_scenario"])
        assert result["experiment_name"] == "Curator 价值消融"
        assert "control" in result
        assert "treatment" in result
        assert "recommendation" in result

    def test_ablation_no_recommendation_if_both_equal(self):
        config = AblationConfig(
            name="equal_test", control={},
            treatment={"disable_agent": "curator"})
        sys = FakeSystem("default")
        result = run_ablation_experiment(
            config=config, control_sys=sys, treatment_sys=sys,
            scenarios=["dummy"])
        assert result["recommendation"] == "keep"
