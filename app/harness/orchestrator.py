from pathlib import Path

import yaml

from app.harness.enums import ActionKind

_RULES_DEFAULT_PATH = Path(__file__).resolve().parent.parent / \
    "orchestration" / "orchestrator_rules.yaml"


def load_rules(path: Path | str | None = None) -> list[dict]:
    """加载 §3.4 规则 YAML，按 priority 降序返回。"""
    p = Path(path) if path else _RULES_DEFAULT_PATH
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    rules = data.get("rules", [])
    rules.sort(key=lambda r: r.get("priority", 0), reverse=True)
    return rules


class RuleEngine:
    """根据观察集匹配规则，返回 ActionKind。

    观察集字段（扁平 dict）：mastery / confusion / contradiction /
    prereq_weak / prereq_basis / rag_quality_low / repeat_count /
    topic_complete。规则 `when` 内字段值需全部相等（`repeat_lt: 2` 是
    特殊比较：`repeat_count < 2`）。
    """

    def __init__(self, rules: list[dict]):
        self._rules = rules

    def match(self, obs: dict) -> ActionKind:
        for rule in self._rules:
            if self._cond_match(rule.get("when", {}), obs):
                return ActionKind(rule["action"])
        return ActionKind.CONDUCTOR_DECIDE

    @staticmethod
    def _cond_match(when: dict, obs: dict) -> bool:
        for key, expected in when.items():
            if key == "repeat_lt":
                if obs.get("repeat_count", 0) >= expected:
                    return False
                continue
            if obs.get(key) != expected:
                return False
        return True
