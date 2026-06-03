"""协作级评估（§5.4）：消费 EventStore.replay 的 parent_id 因果链，算六维指标。

六维：职能正交违约 / 协作效率 / 决策稳定性 / 冲突消解 / 因果链质量 / 轨迹偏离。
全部在 Event 对象列表上做旁路分析，不影响在线流量。
"""

from app.harness.events import Event
from app.harness.enums import EventType


# ---- 因果链构建 ----

def build_causal_tree(events: list[Event]) -> dict[str, dict]:
    """构建 parent_id 因果树。

    返回 {event_id: {"event": Event, "parent": str|None, "children": list[str]}}
    """
    tree: dict[str, dict] = {}
    for ev in events:
        tree[ev.id] = {"event": ev, "parent": ev.parent_id, "children": []}
    for eid, node in tree.items():
        parent = node["parent"]
        if parent and parent in tree:
            tree[parent]["children"].append(eid)
    return tree


# ---- 维度1：职能正交违约 ----

def compute_violation_rate(events: list[Event], violation_log: list[str]) -> float:
    """违约率 = 违规事件数 / 总事件数（#14 白名单拦截日志）。应恒为 0。"""
    if not events:
        return 0.0
    return len(violation_log) / len(events)


# ---- 维度2：协作效率 ----

def compute_efficiency(events: list[Event], num_teaching_turns: int) -> dict:
    """events_per_turn + ineffective_rate（emit 但未被任何后续事件引用为 parent）。"""
    if num_teaching_turns <= 0:
        num_teaching_turns = 1
    referenced: set[str] = {ev.parent_id for ev in events if ev.parent_id}
    control_types = {EventType.ORCHESTRATOR_TICK, EventType.LOOP_EXIT,
                     EventType.POLICY_TRANSITION, EventType.ACTION_REQUESTED,
                     EventType.CONDUCTOR_REQUESTED}
    ineffective = sum(
        1 for ev in events
        if ev.id not in referenced
        and ev.type not in control_types
        and ev.source.name != "USER")
    return {
        "events_per_turn": round(len(events) / num_teaching_turns, 2),
        "ineffective_rate": round(ineffective / len(events), 4) if events else 0.0,
        "total_events": len(events),
        "ineffective_count": ineffective,
    }


# ---- 维度3：决策稳定性 ----

def compute_decision_stability(events: list[Event]) -> dict:
    """mode_switches + repent_rate（A→B→A 反悔）。"""
    transitions = [ev for ev in events if ev.type == EventType.POLICY_TRANSITION]
    total = len(transitions)
    if total < 2:
        return {"mode_switches": total, "repent_rate": 0.0, "repent_count": 0}
    repents = 0
    for i in range(1, len(transitions) - 1):
        p0, p1 = transitions[i - 1].payload, transitions[i].payload
        if p0.get("from") == p1.get("to") and p0.get("to") == p1.get("from"):
            repents += 1
    return {
        "mode_switches": total,
        "repent_rate": round(repents / total, 4) if total else 0.0,
        "repent_count": repents,
    }


# ---- 维度4：冲突消解 ----

def compute_conflict_resolution(events: list[Event]) -> dict:
    """维度4：冲突消解（代理指标）。

    注：spec §5.4 原指"Critic/Curator 观察冲突率 + 回合屏障日志是否真消解"。
    桩期用"掌握度评分短时大幅波动（>50/100）"作为冲突的代理信号，待回合屏障日志
    可得后替换为精确信号。
    """
    mastery_events = [ev for ev in events if ev.type == EventType.MASTERY_ASSESSED]
    conflicts = 0
    for i in range(1, len(mastery_events)):
        prev = mastery_events[i - 1].payload.get("score", 0) or 0
        curr = mastery_events[i].payload.get("score", 0) or 0
        if abs(curr - prev) > 50:
            conflicts += 1
    total = len(mastery_events)
    return {
        "conflict_rate": round(conflicts / total, 4) if total else 0.0,
        "mastery_conflicts": conflicts,
        "total_mastery_events": total,
    }


# ---- 维度5：因果链质量 ----

def compute_causal_chain_quality(events: list[Event]) -> dict:
    """orphan_rate（无 parent 且非种子事件）+ max_depth + avg_depth。"""
    tree = build_causal_tree(events)
    seed_types = {EventType.USER_MESSAGE, EventType.TOPIC_ENTERED,
                  EventType.ORCHESTRATOR_TICK}
    orphans = [eid for eid, node in tree.items()
               if node["parent"] is None
               and node["event"].type not in seed_types]

    def _depth(eid: str, visited: set[str] | None = None) -> int:
        if visited is None:
            visited = set()
        if eid in visited:
            return 0
        visited.add(eid)
        node = tree[eid]
        if not node["children"]:
            return 1
        return 1 + max(_depth(c, visited) for c in node["children"])

    roots = [eid for eid in tree if tree[eid]["parent"] is None]
    depths = [_depth(eid) for eid in roots]
    return {
        "orphan_rate": round(len(orphans) / len(events), 4) if events else 0.0,
        "orphan_count": len(orphans),
        "max_depth": max(depths) if depths else 0,
        "avg_depth": round(sum(depths) / len(depths), 2) if depths else 0.0,
    }


# ---- 维度6：轨迹偏离 ----

def compute_trajectory_deviation(events: list[Event],
                                  expected_path: list[str]) -> dict:
    """实际模式路径 vs 黄金轨迹偏离度（§5.4 / #21）。"""
    actual_path = [ev.payload.get("to", "")
                   for ev in events if ev.type == EventType.POLICY_TRANSITION]
    if not expected_path:
        return {"deviation_score": 0.0, "actual_path": actual_path}
    if not actual_path:
        return {"deviation_score": 1.0, "actual_path": actual_path}
    matches, i, j = 0, 0, 0
    while i < len(expected_path) and j < len(actual_path):
        if expected_path[i] == actual_path[j]:
            matches += 1
            i += 1
        j += 1
    deviation = 1.0 - (matches / len(expected_path))
    return {
        "deviation_score": round(deviation, 4),
        "actual_path": actual_path,
        "expected_path": expected_path,
        "matches": matches,
        "total_expected": len(expected_path),
    }


# ---- 汇总（FLAT 无前缀 key）----

def compute_collaboration_metrics(
    session_id: str,
    events: list[Event] | None = None,
    violation_log: list[str] | None = None,
    expected_mode_path: list[str] | None = None,
    num_teaching_turns: int = 1,
) -> dict:
    """六维协作指标汇总。各维度 dict 直接展平合并（key 无前缀，互不冲突）。"""
    events = events or []
    violation_log = violation_log or []
    expected_mode_path = expected_mode_path or []
    return {
        "session_id": session_id,
        "violation_count": len(violation_log),
        "violation_rate": compute_violation_rate(events, violation_log),
        **compute_efficiency(events, num_teaching_turns),
        **compute_decision_stability(events),
        **compute_conflict_resolution(events),
        **compute_causal_chain_quality(events),
        **compute_trajectory_deviation(events, expected_mode_path),
    }


# ---- EventStore 集成入口（旁路读取已运行会话）----

def collaboration_report_from_store(
    store,
    session_id: str,
    violation_log: list[str] | None = None,
    expected_mode_path: list[str] | None = None,
) -> dict:
    """从 EventStore 回放 trace 并计算六维协作指标（Plan E 主入口之一）。"""
    events = store.replay(session_id)
    return compute_collaboration_metrics(
        session_id=session_id,
        events=events,
        violation_log=violation_log or [],
        expected_mode_path=expected_mode_path or [],
        num_teaching_turns=max(
            1, len([e for e in events if e.type == EventType.ORCHESTRATOR_TICK])),
    )
