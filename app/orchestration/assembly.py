"""Plan D 端到端装配线（§8 P8）。

把 EventBus + 5 Agent（Tutor/Critic/Retriever/Curator/Conductor）+ Orchestrator
装配成一次同步 run_collab_loop，并从事件流提取面向 API 的回复与对齐指标。
只装配、不改任何冻结接口（§3.5.4：协作环对外是一次同步调用）。
"""
from app.harness.events import Event
from app.harness.enums import EventType, EventSource, ActionKind, TeachingMode

# Tutor 产出的「面向用户」事件类型（提取 reply 用）
_TUTOR_REPLY_TYPES = (
    EventType.TUTOR_ASKED,
    EventType.TUTOR_EXPLAINED,
    EventType.TUTOR_REQUESTED_RECAP,
    EventType.TUTOR_OFFERED_ANALOGY,
)


def extract_reply(events: list[Event]) -> str:
    """取最后一个 Tutor 面向用户事件的 content（无则空串）。"""
    for ev in reversed(events):
        if ev.type in _TUTOR_REPLY_TYPES:
            return ev.payload.get("content", "")
    return ""



def extract_mastery_score(events: list[Event]) -> int | None:
    """取最后一个 MasteryAssessed 的 score（0-100；缺失/为空则 None）。"""
    for ev in reversed(events):
        if ev.type == EventType.MASTERY_ASSESSED:
            score = ev.payload.get("score")
            return int(score) if score is not None else None
    return None



def extract_mode_path(events: list[Event]) -> list[str]:
    """教学模式路径：初始 Socratic + 每个 PolicyTransition 的 to。"""
    path = [str(TeachingMode.SOCRATIC)]
    for ev in events:
        if ev.type == EventType.POLICY_TRANSITION:
            path.append(ev.payload.get("to", ""))
    return path
