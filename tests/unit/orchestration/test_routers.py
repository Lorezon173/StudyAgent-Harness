from app.orchestration.routers import route_decision


def test_route_decision_default_enters_collab_loop():
    assert route_decision({"enter_loop": True}) == "collab_loop"


def test_route_decision_enter_loop_false_goes_wrap_up():
    assert route_decision({"enter_loop": False}) == "wrap_up"


def test_route_decision_missing_field_defaults_to_collab_loop():
    assert route_decision({}) == "collab_loop"
