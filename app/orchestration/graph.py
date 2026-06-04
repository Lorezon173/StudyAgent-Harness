import operator
from dataclasses import dataclass
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from app.agents.conductor import ConductorAgent
from app.agents.critic import CriticAgent
from app.agents.tutor import TutorAgent
from app.harness.enums import EventType
from app.harness.eventbus import EventBus
from app.harness.orchestrator import Orchestrator
from app.orchestration.collab_loop import run_collab_loop
from app.orchestration.routers import route_decision


class MainState(TypedDict, total=False):
    """主图骨架状态（Plan 0 + Plan C 扩展）。

    `_runtime` 是 Plan C 注入的可选运行时字典：
      - "runtime": CollabRuntime（bus / orchestrator）
      - "ws":      WorkspaceState
      - "seeds":   list[Event] 种子事件
    若缺失，`_collab_loop_node` 退化为 stub（保持 Plan 0 测试兼容）。

    运行时对象（EventBus 含 sqlite3.Connection，Orchestrator 含规则引擎）
    本质不可 msgpack/pickle —— 由 `_TolerantSerde` 在 checkpointer 序列化阶段
    静默丢弃（loads 端 MemorySaver 已识别 `("empty", b"")`，§3.5.4 注入语义
    不要求跨步幂等回放）。
    """
    session_id: str
    user_id: str
    enter_loop: bool
    stage: str
    visited: Annotated[list[str], operator.add]
    _runtime: dict


@dataclass
class CollabRuntime:
    bus: EventBus
    orchestrator: Orchestrator


def build_collab_runtime(bus: EventBus,
                          orchestrator: Orchestrator | None = None
                          ) -> CollabRuntime:
    """工厂：装配 3 Agent + Orchestrator 订阅到 Bus。

    Plan C 只装配 Tutor / Critic / Conductor（自有 Agent）；Retriever / Curator
    由 Plan D 的集成层补齐订阅（本 Plan 不引入 A/B 文件）。
    """
    tutor = TutorAgent()
    critic = CriticAgent()
    conductor = ConductorAgent()
    bus.subscribe(tutor, tutor.subscriptions)
    bus.subscribe(critic, critic.subscriptions)
    bus.subscribe(conductor, conductor.subscriptions)
    return CollabRuntime(bus=bus, orchestrator=orchestrator or Orchestrator())


class _TolerantSerde(JsonPlusSerializer):
    """MemorySaver 序列化兜底：遇不可序列化值返回 `("empty", b"")`，
    被 MemorySaver.get_tuple 视为缺失值跳过（运行时对象本就不应跨步回放）。
    """

    def dumps_typed(self, obj: Any) -> tuple[str, bytes]:
        try:
            return super().dumps_typed(obj)
        except (TypeError, ValueError):
            return ("empty", b"")


def _ingest(state: MainState) -> dict:
    return {"visited": ["ingest"], "stage": "ingest"}


def _route(state: MainState) -> dict:
    return {"visited": ["route"], "stage": "route"}


def _collab_loop_node(state: MainState) -> dict:
    """Plan C 接入点（§3.5.4）：若注入运行时则跑真实协作环；否则 stub 兜底。"""
    runtime_bundle = state.get("_runtime")
    if not runtime_bundle:
        return {"visited": ["collab_loop"], "stage": "collab_loop"}
    rt: CollabRuntime = runtime_bundle["runtime"]
    ws = runtime_bundle["ws"]
    seeds = runtime_bundle["seeds"]
    run_collab_loop(rt.bus, ws, seeds, orchestrator=rt.orchestrator)
    return {"visited": ["collab_loop"], "stage": "collab_loop"}


def _wrap_up(state: MainState) -> dict:
    return {"visited": ["wrap_up"], "stage": "wrap_up"}


def build_main_graph():
    """4 节点骨架：ingest → route → [collab_loop] → wrap_up（§3.5.4）。

    零参数版本保留 Plan 0 测试兼容；运行时由 MainState["_runtime"] 注入。
    """
    g = StateGraph(MainState)
    g.add_node("ingest", _ingest)
    g.add_node("route", _route)
    g.add_node("collab_loop", _collab_loop_node)
    g.add_node("wrap_up", _wrap_up)
    g.set_entry_point("ingest")
    g.add_edge("ingest", "route")
    g.add_conditional_edges("route", route_decision,
                            {"collab_loop": "collab_loop", "wrap_up": "wrap_up"})
    g.add_edge("collab_loop", "wrap_up")
    g.add_edge("wrap_up", END)
    return g.compile(checkpointer=MemorySaver(serde=_TolerantSerde()))
