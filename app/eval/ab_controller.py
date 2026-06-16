from dataclasses import dataclass, field


@dataclass
class AblationConfig:
    """组件消融实验配置（§5.5 类型二）。

    control:   对照配置（all_agents:true 或完整参数）
    treatment: 实验配置（disable_agent:"curator" 等）
    """
    name: str
    control: dict = field(default_factory=dict)
    treatment: dict = field(default_factory=dict)
    metrics_to_compare: list[str] = field(default_factory=list)
    repeats: int = 1


def run_parameter_ab(control, treatment, scenarios: list[str],
                     metrics_to_compare: list[str],
                     experiment_name: str = "A/B Experiment") -> dict:
    """参数 A/B（§5.5 类型一）。control/treatment 实现 run_scenario(name)->dict。"""
    control_results = {sc: control.run_scenario(sc) for sc in scenarios}
    treatment_results = {sc: treatment.run_scenario(sc) for sc in scenarios}

    deltas: dict[str, float] = {}
    for metric in metrics_to_compare:
        if metric == "mastery_reached":
            continue  # 字符串结果指标不计 delta
        c_val = _avg_metric(control_results, metric)
        t_val = _avg_metric(treatment_results, metric)
        if c_val and c_val != 0:
            deltas[metric] = round((t_val - c_val) / c_val * 100, 1)
        else:
            deltas[metric] = 0.0

    return {
        "experiment_name": experiment_name,
        "scenarios": list(scenarios),
        "control": dict(control_results),
        "treatment": dict(treatment_results),
        "delta": deltas,
    }


def _avg_metric(results: dict[str, dict], metric: str) -> float:
    vals = [r.get(metric, 0) or 0 for r in results.values()]
    return sum(vals) / len(vals) if vals else 0.0


def run_ablation_experiment(config: AblationConfig, control_sys, treatment_sys,
                            scenarios: list[str]) -> dict:
    """组件消融（§5.5 类型二）：对比禁用某组件前后的 delta，回答"该组件值多少增益"。"""
    ab_result = run_parameter_ab(
        control=control_sys, treatment=treatment_sys, scenarios=scenarios,
        metrics_to_compare=config.metrics_to_compare,
        experiment_name=config.name)

    deltas = ab_result["delta"]
    all_zero = all(abs(v) < 1.0 for v in deltas.values()) if deltas else True
    if all_zero:
        recommendation, reason = "keep", "消融前后指标无显著差异，建议保持当前配置"
    else:
        worse = sum(1 for v in deltas.values() if v < 0)
        better = sum(1 for v in deltas.values() if v > 0)
        if worse > better:
            recommendation = "keep"
            reason = f"消融后 {worse} 项指标变差，该组件有正向贡献"
        else:
            recommendation = "review"
            reason = f"消融后 {better} 项指标变好，建议评估是否可移除"

    ab_result["recommendation"] = recommendation
    ab_result["reason"] = reason
    return ab_result


class StubAgent:
    """消融用桩 Agent（§5.5）：被禁用组件的产出由桩返回空/默认值。

    handle 永远返回 []（不 emit 任何事件），evaluate 返回 {}。用于"禁用某组件，
    其产出由 stub 返回默认值"的消融对照（design §5.5）。
    """

    def __init__(self, source=None):
        self.source = source
        self.subscriptions: list = []
        self.emittable_types: set = set()

    def handle(self, event, ws) -> list:
        return []

    def evaluate(self, test_case) -> dict:
        return {}


def make_ablation_agent_map(agent_map: dict, disable: str) -> dict:
    """返回禁用 `disable` 组件后的 agent_map（该组件替换为 StubAgent）。§5.5。

    这是消融的载荷原语：把被消融 Agent 换成桩，再由调用方在实际系统上跑场景对比
    delta。纯旁路侧只提供桩与替换；live 执行由集成层（Plan D 在线栈）驱动。
    """
    ablated = dict(agent_map)
    if disable in ablated:
        original = ablated[disable]
        ablated[disable] = StubAgent(source=getattr(original, "source", None))
    return ablated
