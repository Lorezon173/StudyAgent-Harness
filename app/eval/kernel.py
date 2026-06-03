from dataclasses import dataclass, field


@dataclass
class TestCase:
    """部件级评估的单个测试用例（§5.2）。

    name:       测试用例名称
    component:  被测部件标识（tutor|retriever|critic|curator|conductor）
    input:      输入参数（传给 Agent.evaluate()）
    expected:   期望的指标值
    meta:       元信息（来源、版本、标注者等）
    """
    __test__ = False  # 防止 pytest 误把本数据类收集为测试类

    name: str
    component: str
    input: dict = field(default_factory=dict)
    expected: dict = field(default_factory=dict)
    meta: dict = field(default_factory=dict)


@dataclass
class EvalResult:
    """单个测试用例的评估结果。"""
    test_name: str
    component: str
    passed: bool
    metrics: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)


@dataclass
class ScenarioDefinition:
    """系统级场景定义（§5.3）。

    script:    模拟用户的多轮回复
    expected:  结果断言 + 过程断言（§5.3 格式 + §5.4 轨迹偏离）
    meta:      场景元信息
    """
    name: str
    user_profile: dict = field(default_factory=dict)
    topic: str = ""
    script: list[dict] = field(default_factory=list)
    expected: dict = field(default_factory=dict)
    meta: dict = field(default_factory=dict)


class EvalKernel:
    """评估内核 —— 薄编排层，统一委托各 bench（§5）。

    agent_map: {component_name: AgentBase 实例}
    """

    def __init__(self, agent_map: dict | None = None):
        from app.eval.component_bench import ComponentBench
        from app.eval.system_bench import SystemBench
        self._agent_map = agent_map or {}
        self._component_bench = ComponentBench(self._agent_map)
        self._system_bench = SystemBench()

    def run_component_bench(self, component: str, test_cases: list) -> list:
        """委托 ComponentBench（§5.2）。未注册组件返回失败结果（不抛异常）。"""
        return self._component_bench.run(component, test_cases)

    def run_system_bench(self, scenarios: list, event_store=None) -> list:
        """委托 SystemBench（§5.3）。event_store 给定则 replay 取 trace。"""
        results = []
        for sc in scenarios:
            trace = event_store.replay(sc.name) if event_store is not None else []
            results.append(self._system_bench.assess(sc, trace))
        return results

    def run_collaboration_bench(self, session_id: str, event_store=None) -> dict:
        """委托 CollaborationBench（§5.4）。"""
        from app.eval.collaboration_bench import (
            collaboration_report_from_store, compute_collaboration_metrics)
        if event_store is None:
            return compute_collaboration_metrics(session_id, events=[])
        return collaboration_report_from_store(event_store, session_id)

    def run_ablation(self, config, control_sys, treatment_sys, scenarios) -> dict:
        """委托 ABController 组件消融（§5.5）。config 可为 dict 或 AblationConfig。"""
        from app.eval.ab_controller import run_ablation_experiment, AblationConfig
        if isinstance(config, dict):
            config = AblationConfig(
                name=config.get("name", "ablation"),
                control=config.get("control", {}),
                treatment=config.get("treatment", {}),
                metrics_to_compare=config.get("metrics_to_compare", []))
        return run_ablation_experiment(config, control_sys, treatment_sys, scenarios)
