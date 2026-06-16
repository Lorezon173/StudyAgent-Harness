from app.orchestration.graph import build_main_graph

_CFG = {"configurable": {"thread_id": "t1"}}


def test_graph_compiles():
    assert build_main_graph() is not None


def test_enter_loop_path_visits_collab_loop():
    g = build_main_graph()
    out = g.invoke({"session_id": "s1", "user_id": "u1", "enter_loop": True}, config=_CFG)
    assert out["stage"] == "wrap_up"            # 终点
    assert "collab_loop" in out["visited"]      # 进环


def test_skip_loop_path_bypasses_collab_loop():
    g = build_main_graph()
    out = g.invoke({"session_id": "s2", "user_id": "u1", "enter_loop": False},
                   config={"configurable": {"thread_id": "t2"}})
    assert out["stage"] == "wrap_up"
    assert "collab_loop" not in out["visited"]  # 纯 FAQ 不进环（§3.5.4）
    assert out["visited"] == ["ingest", "route", "wrap_up"]
