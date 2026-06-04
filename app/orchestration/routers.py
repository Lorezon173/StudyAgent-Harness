"""主图条件边（§3.5.4 / spec §7）。"""


def route_decision(state: dict) -> str:
    """route 节点的下游判定：是否进入协作环。"""
    return "collab_loop" if state.get("enter_loop", True) else "wrap_up"
