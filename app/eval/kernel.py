from dataclasses import dataclass, field
from typing import Any


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
    """评估内核 —— 统一编排三层次评估 + A/B 消融（§5）。

    agent_map: {component_name: AgentBase_instance}
    """

    def __init__(self, agent_map: dict[str, "AgentBase"] | None = None):
        self._agent_map = agent_map or {}

    # ---- ComponentBench（§5.2）----

    def run_component_bench(self, component: str,
                            test_cases: list[TestCase]) -> list[EvalResult]:
        if component not in self._agent_map:
            raise ValueError(
                f"ComponentBench 无注册 Agent：{component}")
        agent = self._agent_map[component]
        results: list[EvalResult] = []
        for tc in test_cases:
            try:
                metrics = agent.evaluate(tc.input)
            except NotImplementedError as e:
                results.append(EvalResult(
                    test_name=tc.name, component=component,
                    passed=False, errors=[str(e)]))
                continue
            passed = self._check_expected(tc.expected, metrics)
            errors = []
            if not passed:
                for key, threshold in tc.expected.items():
                    actual = metrics.get(key)
                    if actual is None or (
                            isinstance(threshold, (int, float))
                            and actual < threshold):
                        errors.append(
                            f"{key}: expected>={threshold}, got={actual}")
            results.append(EvalResult(
                test_name=tc.name, component=component,
                passed=passed, metrics=metrics, errors=errors))
        return results

    @staticmethod
    def _check_expected(expected: dict, actual: dict) -> bool:
        for key, threshold in expected.items():
            val = actual.get(key)
            if val is None:
                return False
            if isinstance(threshold, (int, float)):
                if val < threshold:
                    return False
            elif val != threshold:
                return False
        return True

    # ---- SystemBench（§5.3）----

    def run_system_bench(self, scenarios: list[ScenarioDefinition],
                         event_store=None) -> list[dict]:
        """运行系统级场景评估。

        实际运行时 event_store 为 EventStore 实例，用于 replay 已运行场景。
        返回每个场景的评估摘要。Task 5 会把 _assess_scenario 委托给 SystemBench。
        """
        results: list[dict] = []
        for sc in scenarios:
            trace = None
            if event_store is not None:
                trace = event_store.replay(sc.name)
            results.append(self._assess_scenario(sc, trace))
        return results

    def _assess_scenario(self, sc: ScenarioDefinition,
                         trace: list | None) -> dict:
        """占位：Task 5 用真正的 SystemBench.assess 替换。"""
        return {
            "scenario": sc.name,
            "result_assertions": {},
            "process_assertions": {},
            "passed": True,
            "errors": [],
        }

    # ---- CollaborationBench（§5.4）—— 惰性委托，Task 6 落地 ----

    def run_collaboration_bench(self, session_id: str,
                                event_store=None) -> dict:
        """对一次会话回放计算六维协作指标（委托 collaboration_bench，Task 6）。"""
        from app.eval.collaboration_bench import collaboration_report_from_store
        if event_store is None:
            from app.eval.collaboration_bench import compute_collaboration_metrics
            return compute_collaboration_metrics(session_id, events=[])
        return collaboration_report_from_store(event_store, session_id)

    # ---- ABController（§5.5）—— 惰性委托，Task 8 落地 ----

    def run_ablation(self, config, scenarios, event_store=None) -> dict:
        """运行消融实验（委托 ab_controller，Task 8）。"""
        from app.eval.ab_controller import run_ablation_experiment, AblationConfig
        if isinstance(config, dict):
            config = AblationConfig(
                name=config.get("name", "ablation"),
                control=config.get("control", {}),
                treatment=config.get("treatment", {}),
                metrics_to_compare=config.get("metrics_to_compare", []),
            )
        # control/treatment 系统对象由调用方在 Task 8/10 装配；此处仅占位委托
        raise NotImplementedError(
            "run_ablation 需 Task 8 的 ab_controller + 装配好的系统对象")
