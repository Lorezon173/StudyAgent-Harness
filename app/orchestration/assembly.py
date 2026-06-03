"""Plan D 端到端装配线（§8 P8）。

把 EventBus + 5 Agent（Tutor/Critic/Retriever/Curator/Conductor）+ Orchestrator
装配成一次同步 run_collab_loop，并从事件流提取面向 API 的回复与对齐指标。
只装配、不改任何冻结接口（§3.5.4：协作环对外是一次同步调用）。
"""
from dataclasses import dataclass, field

from app.harness.events import Event
from app.harness.enums import EventType, EventSource, ActionKind, TeachingMode

from app.agents.tutor import TutorAgent
from app.agents.critic import CriticAgent
from app.agents.retriever import RetrieverAgent
from app.agents.conductor import ConductorAgent
from app.agents.curator import Curator
from app.harness.eventbus import EventBus
from app.harness.orchestrator import Orchestrator
from app.harness.teaching_policy import TeachingPolicy
from app.harness.workspace_state import WorkspaceState
from app.harness.mastery_graph import MasteryGraph
from app.infrastructure.storage.event_store import EventStore
from app.infrastructure.storage.mastery_graph_store import MasteryGraphStore
from app.orchestration.collab_loop import run_collab_loop

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


_EMPTY_REPLY_FALLBACK = "（本轮未生成回复）"


@dataclass
class NewStackResult:
    """新栈一次会话的产出（供 API 层包成 ChatResponse）。"""
    reply: str
    mastery_score: int | None
    turn_count: int
    mode_path: list[str]
    cost_est_usd: float | None
    events: list = field(default_factory=list)   # 完整事件链（调试/对齐用）


def _read_cost(session_id: str) -> float | None:
    """best-effort：从 observability 读本会话累计 LLM 成本（无则 None）。"""
    try:
        from app.harness.observability import get_observability
        stats = get_observability().session_summary(session_id)
        return round(stats.total_cost_usd, 6) if stats is not None else None
    except Exception:
        return None


def build_new_stack(user_id: str):
    """装配 EventBus + 5 Agent + Orchestrator。返回 (bus, orchestrator, store)。

    每会话独立实例；TeachingPolicy 新建以隔离模式历史。store 为内存 EventStore，
    由调用方在用完后 close。
    """
    store = EventStore(db_path=":memory:")
    store.init()
    bus = EventBus(store=store)

    mg_store = MasteryGraphStore(db_path=":memory:")          # Curator.handle 不触其异步方法
    graph = MasteryGraph(user_id=user_id, store=mg_store)

    agents = [
        TutorAgent(),
        CriticAgent(),
        RetrieverAgent(),
        ConductorAgent(),
        Curator(graph=graph, store=mg_store),
    ]
    for agent in agents:
        bus.subscribe(agent, agent.subscriptions)

    orchestrator = Orchestrator(policy=TeachingPolicy())
    return bus, orchestrator, store


def run_new_agent_session(session_id: str, user_id: str, user_message: str,
                          current_topic: str | None = None) -> NewStackResult:
    """新栈一次同步会话：装配 → 跑协作环 → 从事件流提取结果。

    同步函数；API 层用 asyncio.to_thread 调用。
    """
    topic = current_topic or user_message
    bus, orchestrator, store = build_new_stack(user_id)
    try:
        ws = WorkspaceState(session_id=session_id, user_id=user_id,
                            current_topic=topic)
        seeds = [
            Event(type=EventType.USER_MESSAGE, source=EventSource.USER,
                  session_id=session_id,
                  payload={"text": user_message, "user_id": user_id}),
            Event(type=EventType.TOPIC_ENTERED, source=EventSource.ORCHESTRATOR,
                  session_id=session_id, payload={"topic_id": topic}),
            Event(type=EventType.ACTION_REQUESTED, source=EventSource.ORCHESTRATOR,
                  session_id=session_id,
                  payload={"action": str(ActionKind.TUTOR_ASK),
                           "target": str(EventSource.TUTOR)}),
        ]
        run_collab_loop(bus, ws, seeds, orchestrator=orchestrator)
        events = bus.replay(session_id)
        return NewStackResult(
            reply=extract_reply(events) or _EMPTY_REPLY_FALLBACK,
            mastery_score=extract_mastery_score(events),
            turn_count=ws.turn_count,
            mode_path=extract_mode_path(events),
            cost_est_usd=_read_cost(session_id),
            events=events,
        )
    finally:
        store.close()
