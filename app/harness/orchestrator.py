from pathlib import Path

import yaml

from app.harness.enums import ActionKind, EventType, EventSource
from app.harness.events import Event
from app.harness.workspace_state import WorkspaceState
from app.harness.teaching_policy import TeachingPolicy, ObservationSet

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


_OBSERVATION_TYPES = {
    EventType.MASTERY_ASSESSED,
    EventType.CONFUSION_DETECTED,
    EventType.CONTRADICTION_DETECTED,
    EventType.LOW_CONFIDENCE_DETECTED,
    EventType.RAG_QUALITY_ASSESSED,
    EventType.GRAPH_PREREQ_WEAK_DETECTED,
}


class Orchestrator:
    """事件路由器（§3.3）。Plan 0 `run_collab_loop` 的钩子。

    回合屏障（§3.5.3）：观察类事件进入 `_pending_obs` 缓冲，并仅在 micro-turn
    内首次出现时注入 `OrchestratorTick` 哨兵（priority=100，最低）。当 Tick
    被弹出时（说明同一 micro-turn 的全部观察都已入队），Orchestrator 对完整
    观察集做唯一一次路由裁决。
    """

    def __init__(self, rules_path: str | None = None,
                 policy: TeachingPolicy | None = None):
        self._engine = RuleEngine(load_rules(rules_path))
        self._policy = policy or TeachingPolicy()
        self._pending_obs: list[Event] = []
        self._tick_pending: bool = False

    def on_event(self, event: Event, ws: WorkspaceState) -> list[Event]:
        if event.type in _OBSERVATION_TYPES:
            self._pending_obs.append(event)
            if not self._tick_pending:
                self._tick_pending = True
                return [Event(
                    type=EventType.ORCHESTRATOR_TICK,
                    source=EventSource.ORCHESTRATOR,
                    session_id=ws.session_id,
                    payload={"reason": "micro_turn_barrier"})]
            return []

        if event.type == EventType.ORCHESTRATOR_TICK:
            return self._on_tick(event, ws)

        if event.type == EventType.CONDUCTOR_DECIDED:
            return self._translate_conductor_decision(event, ws)

        return []

    def _on_tick(self, tick: Event, ws: WorkspaceState) -> list[Event]:
        obs = self._collect_observations(self._pending_obs, ws)
        self._pending_obs = []
        self._tick_pending = False

        action = self._engine.match(obs)
        if action == ActionKind.CONDUCTOR_DECIDE:
            return [Event(type=EventType.CONDUCTOR_REQUESTED,
                          source=EventSource.ORCHESTRATOR,
                          session_id=ws.session_id,
                          payload={"observations": [self._obs_summary(e)
                                                    for e in obs.get("_raw", [])],
                                   "reason": "rule fallthrough"},
                          parent_id=tick.id)]

        emits: list[Event] = []
        target_mode, _ = self._policy.next(self._to_obs_set(obs))
        if target_mode != ws.current_mode:
            emits.append(Event(type=EventType.POLICY_TRANSITION,
                               source=EventSource.ORCHESTRATOR,
                               session_id=ws.session_id,
                               payload={"from": str(ws.current_mode),
                                        "to": str(target_mode)},
                               parent_id=tick.id))
            ws.current_mode = target_mode

        if action == ActionKind.LOOP_EXIT:
            emits.append(Event(type=EventType.LOOP_EXIT,
                               source=EventSource.ORCHESTRATOR,
                               session_id=ws.session_id,
                               payload={"reason": "rule_loop_exit"},
                               parent_id=tick.id))
        else:
            emits.append(Event(type=EventType.ACTION_REQUESTED,
                               source=EventSource.ORCHESTRATOR,
                               session_id=ws.session_id,
                               payload={"action": str(action),
                                        "target": self._target_of(action)},
                               parent_id=tick.id))
        return emits

    @staticmethod
    def _target_of(action: ActionKind) -> str:
        if str(action).startswith("retriever"):
            return str(EventSource.RETRIEVER)
        if str(action).startswith("tutor") or action == ActionKind.REGRESS_TO_PREREQ:
            return str(EventSource.TUTOR)
        return ""

    @staticmethod
    def _collect_observations(events: list[Event], ws: WorkspaceState) -> dict:
        obs: dict = {"_raw": events, "repeat_count": 0,
                     "topic_complete": False, "turn_over_limit": False}
        for ev in events:
            if ev.type == EventType.MASTERY_ASSESSED:
                obs["mastery"] = ev.payload.get("level")
            elif ev.type == EventType.CONFUSION_DETECTED:
                obs["confusion"] = True
            elif ev.type == EventType.CONTRADICTION_DETECTED:
                obs["contradiction"] = True
            elif ev.type == EventType.LOW_CONFIDENCE_DETECTED:
                obs["low_confidence"] = True
            elif ev.type == EventType.RAG_QUALITY_ASSESSED:
                obs["rag_quality_low"] = (ev.payload.get("score") or 0) < 0.5
            elif ev.type == EventType.GRAPH_PREREQ_WEAK_DETECTED:
                obs["prereq_weak"] = True
                obs["prereq_basis"] = ev.payload.get("basis")
        return obs

    @staticmethod
    def _obs_summary(ev: Event) -> dict:
        return {"type": str(ev.type), **ev.payload}

    @staticmethod
    def _to_obs_set(obs: dict) -> ObservationSet:
        from app.harness.enums import MasteryLevel
        m = obs.get("mastery")
        return ObservationSet(
            mastery=MasteryLevel(m) if m else None,
            confusion=bool(obs.get("confusion")),
            contradiction=bool(obs.get("contradiction")),
            prereq_weak=bool(obs.get("prereq_weak")),
            prereq_basis=obs.get("prereq_basis"),
            rag_quality_low=bool(obs.get("rag_quality_low")),
            repeat_count=obs.get("repeat_count", 0),
            topic_complete=bool(obs.get("topic_complete")),
            turn_over_limit=bool(obs.get("turn_over_limit")),
        )

    def _translate_conductor_decision(self, event: Event,
                                       ws: WorkspaceState) -> list[Event]:
        # 在 Task 5.4 落地
        return []
