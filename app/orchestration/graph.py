import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.checkpoint.memory import MemorySaver


class MainState(TypedDict, total=False):
    """主图骨架状态（Plan 0）。Wave 1 将以 WorkspaceState 承载真实会话状态。"""
    session_id: str
    user_id: str
    enter_loop: bool                              # route 决策：是否进协作环
    stage: str                                    # 当前阶段（覆盖写）
    visited: Annotated[list[str], operator.add]   # 经过的节点（累加）


def _ingest(state: MainState) -> dict:
    return {"visited": ["ingest"], "stage": "ingest"}


def _route(state: MainState) -> dict:
    return {"visited": ["route"], "stage": "route"}


def _route_decision(state: MainState) -> str:
    # 默认进环；纯 FAQ（enter_loop=False）直接收尾（§3.5.4）
    return "collab_loop" if state.get("enter_loop", True) else "wrap_up"


def _collab_loop_node(state: MainState) -> dict:
    # Plan 0 占位：Plan C 在此调用 run_collab_loop(bus, ws, seeds, orchestrator)
    return {"visited": ["collab_loop"], "stage": "collab_loop"}


def _wrap_up(state: MainState) -> dict:
    return {"visited": ["wrap_up"], "stage": "wrap_up"}


def build_main_graph():
    """4 节点骨架：ingest → route → [collab_loop] → wrap_up（§3.5.4）。"""
    g = StateGraph(MainState)
    g.add_node("ingest", _ingest)
    g.add_node("route", _route)
    g.add_node("collab_loop", _collab_loop_node)
    g.add_node("wrap_up", _wrap_up)
    g.set_entry_point("ingest")
    g.add_edge("ingest", "route")
    g.add_conditional_edges("route", _route_decision,
                            {"collab_loop": "collab_loop", "wrap_up": "wrap_up"})
    g.add_edge("collab_loop", "wrap_up")
    g.add_edge("wrap_up", END)
    return g.compile(checkpointer=MemorySaver())
