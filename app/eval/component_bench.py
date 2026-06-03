from app.eval.kernel import TestCase, EvalResult


class ComponentBench:
    """部件级评估（§5.2）：对各 Agent 的 evaluate() 运行黄金用例。"""

    def __init__(self, agent_map: dict[str, object]):
        self._agent_map = agent_map

    def run(self, component: str,
            test_cases: list[TestCase]) -> list[EvalResult]:
        if component not in self._agent_map:
            return [
                EvalResult(test_name=tc.name, component=component,
                           passed=False,
                           errors=[f"Agent '{component}' 未注册"])
                for tc in test_cases
            ]
        agent = self._agent_map[component]
        results: list[EvalResult] = []
        for tc in test_cases:
            try:
                metrics = agent.evaluate(tc.input)
            except Exception as e:
                results.append(EvalResult(
                    test_name=tc.name, component=component,
                    passed=False, errors=[f"evaluate 异常：{e}"]))
                continue
            passed = True
            errors: list[str] = []
            for key, threshold in tc.expected.items():
                actual = metrics.get(key)
                if actual is None:
                    passed = False
                    errors.append(f"{key}: 未返回（期望 >= {threshold}）")
                elif isinstance(threshold, (int, float)):
                    if actual < threshold:
                        passed = False
                        errors.append(f"{key}: {actual} < {threshold}")
                elif isinstance(threshold, str):
                    if str(actual) != threshold:
                        passed = False
                        errors.append(f"{key}: {actual} != {threshold}")
            results.append(EvalResult(
                test_name=tc.name, component=component,
                passed=passed, metrics=metrics, errors=errors))
        return results

    def run_all(self, test_cases: list[TestCase]) -> list[EvalResult]:
        by_component: dict[str, list[TestCase]] = {}
        for tc in test_cases:
            by_component.setdefault(tc.component, []).append(tc)
        results: list[EvalResult] = []
        for comp, cases in by_component.items():
            results.extend(self.run(comp, cases))
        return results

    @staticmethod
    def format_report(results: list[EvalResult]) -> str:
        lines = ["## ComponentBench 报告\n"]
        passed = sum(1 for r in results if r.passed)
        lines.append(f"**通过率**: {passed}/{len(results)}")
        for r in results:
            status = "✅ PASS" if r.passed else "❌ FAIL"
            lines.append(f"\n### {r.test_name} ({status})")
            lines.append(f"- 组件: {r.component}")
            lines.append(f"- 指标: {r.metrics}")
            if r.errors:
                lines.append(f"- 错误: {r.errors}")
        return "\n".join(lines)
