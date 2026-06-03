from datetime import datetime


class SelectionReporter:
    """选型报告生成器（§5.6）。聚合四类评估结果，输出 Markdown 选型建议报告。"""

    @staticmethod
    def aggregate_component(results: list[dict]) -> dict[str, dict]:
        report: dict[str, dict] = {}
        for r in results:
            comp = r["component"]
            report[comp] = {
                "pass_rate": r.get("passed", 0) / max(r.get("total", 1), 1),
                "passed": r.get("passed", 0),
                "total": r.get("total", 0),
                "metrics_avg": r.get("metrics_avg", {}),
            }
        return report

    @staticmethod
    def aggregate_system(results: list[dict]) -> dict:
        passed = sum(1 for r in results if r.get("passed"))
        total = len(results)
        return {
            "pass_rate": passed / total if total else 0.0,
            "passed": passed,
            "total": total,
            "details": results,
        }

    @staticmethod
    def aggregate_collaboration(results: dict[str, dict]) -> dict:
        violations = sum(r.get("violation_count", 0) for r in results.values())
        return {
            "total_sessions": len(results),
            "all_violations_zero": violations == 0,
            "total_violations": violations,
            "details": results,
        }

    @staticmethod
    def _component_markdown(report: dict) -> str:
        lines = ["## 部件级评估\n"]
        for comp, data in report.items():
            lines.append(f"### {comp}")
            passed = data.get("passed", "?")
            total = data.get("total", "?")
            pass_rate = data.get("pass_rate", 0.0)
            lines.append(f"- 通过率：{passed}/{total} ({pass_rate:.1%})")
            if data.get("metrics_avg"):
                lines.append(f"- 平均指标：{data['metrics_avg']}")
            lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _system_markdown(report: dict) -> str:
        lines = ["## 系统级评估\n"]
        lines.append(
            f"**场景通过率**：{report.get('passed', 0)}/{report.get('total', 0)} "
            f"({report.get('pass_rate', 0.0):.1%})\n")
        for detail in report.get("details", []):
            status = "✅" if detail.get("passed") else "❌"
            lines.append(f"- {status} {detail.get('scenario', '?')}")
            for err in detail.get("errors", []):
                lines.append(f"  - {err}")
        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _collaboration_markdown(report: dict) -> str:
        lines = ["## 协作级评估\n"]
        v = "✅ 全部为零" if report.get("all_violations_zero") else "❌ 有违规"
        lines.append(f"- 职能违约：{v}（{report.get('total_violations', 0)} 次）")
        lines.append(f"- 评估会话数：{report.get('total_sessions', 0)}")
        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _ablation_markdown(results: list[dict]) -> str:
        if not results:
            return ""
        lines = ["## 消融实验\n"]
        for r in results:
            lines.append(f"### {r['experiment_name']}")
            lines.append(f"- 推荐：**{r['recommendation']}**")
            lines.append(f"- 理由：{r.get('reason', '')}")
            if r.get("delta"):
                lines.append(f"- Delta：{r['delta']}")
            lines.append("")
        return "\n".join(lines)

    def to_markdown(self, component_report=None, system_report=None,
                    collaboration_report=None, ablation_results=None) -> str:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        lines = [f"# 选型建议报告 — {timestamp}\n"]
        if component_report:
            lines.append(self._component_markdown(component_report))
        if system_report:
            lines.append(self._system_markdown(system_report))
        if collaboration_report:
            lines.append(self._collaboration_markdown(collaboration_report))
        if ablation_results:
            lines.append(self._ablation_markdown(ablation_results))
        return "\n".join(lines)
