from pathlib import Path

import yaml

from app.eval.kernel import ScenarioDefinition


class SystemBench:
    """系统级场景运行器（§5.3）。

    加载 YAML 场景定义，对已运行的 trace 做结果断言 + 过程断言。
    trace 是一组 dict（每个含 'type'，可选 'payload'），通常来自
    EventStore.replay 后转 dict，或测试构造。
    """

    @staticmethod
    def load_scenarios(path: str) -> list[ScenarioDefinition]:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return [ScenarioDefinition(**sc) for sc in data.get("scenarios", [])]

    def assess(self, sc: ScenarioDefinition, trace: list[dict]) -> dict:
        """依据 trace 做结果断言 + 过程断言。"""
        summary = {
            "scenario": sc.name,
            "result_assertions": {},
            "process_assertions": {},
            "passed": True,
            "errors": [],
        }
        expected = sc.expected
        trace_types = [ev["type"] for ev in trace]

        self._assess_result(expected, trace, summary)

        must = expected.get("must_contain_events", [])
        for et in must:
            if et not in trace_types:
                summary["passed"] = False
                summary["errors"].append(f"缺少必需事件：{et}")
        summary["process_assertions"]["must_contain_events"] = {
            "expected": must,
            "all_found": all(et in trace_types for et in must),
        }

        must_not = expected.get("must_not_contain_events", [])
        for et in must_not:
            if et in trace_types:
                summary["passed"] = False
                summary["errors"].append(
                    f"禁止出现事件：{et}（出现 {trace_types.count(et)} 次）")
        summary["process_assertions"]["must_not_contain_events"] = {
            "expected": must_not,
            "none_found": all(et not in trace_types for et in must_not),
        }

        mode_path = expected.get("expected_mode_path", [])
        if mode_path:
            actual_path = self._extract_mode_path(trace)
            deviated = self._mode_path_deviation(mode_path, actual_path)
            if deviated:
                summary["passed"] = False
                summary["errors"].append(
                    f"模式路径偏离：期望 {mode_path}，实际 {actual_path}（{deviated}）")
            summary["process_assertions"]["mode_path"] = {
                "expected": mode_path,
                "actual": actual_path,
                "deviation": deviated,
            }

        return summary

    @staticmethod
    def _assess_result(expected: dict, trace: list[dict],
                       summary: dict) -> None:
        result = summary["result_assertions"]

        expected_mastery = expected.get("mastery_reached")
        if expected_mastery:
            actual = None
            for ev in reversed(trace):
                if ev.get("type") == "MasteryAssessed":
                    actual = ev.get("payload", {}).get("level")
                    break
            ok = actual == expected_mastery
            result["mastery_reached"] = ok
            if not ok:
                summary["errors"].append(
                    f"掌握度未达标：期望 {expected_mastery}，实际 {actual}")
                summary["passed"] = False

        max_turns = expected.get("max_turns")
        if max_turns:
            actual_turns = len(trace) // 3  # 启发式估算（3 事件≈1 回合）
            ok = actual_turns <= max_turns
            result["max_turns"] = ok
            if not ok:
                summary["errors"].append(
                    f"回合数超限：{actual_turns} > {max_turns}")
                summary["passed"] = False

    @staticmethod
    def _extract_mode_path(trace: list[dict]) -> list[str]:
        path: list[str] = []
        for ev in trace:
            if ev.get("type") == "PolicyTransition":
                p = ev.get("payload", {})
                frm, to = p.get("from"), p.get("to")
                if frm and not path:
                    path.append(frm)
                if to:
                    path.append(to)
        return path

    @staticmethod
    def _mode_path_deviation(expected: list[str],
                             actual: list[str]) -> str | None:
        if not actual:
            return "空路径"
        i = 0
        for mode in expected:
            if i < len(actual) and actual[i] == mode:
                i += 1
        if i < len(expected):
            got = actual[i] if i < len(actual) else "无"
            return f"路径在第{i+1}步偏离（期望{expected[i]}，实际{got}）"
        if len(actual) > len(expected):
            return f"路径比期望长{len(actual) - len(expected)}步"
        return None
