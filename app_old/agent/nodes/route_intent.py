from app.harness.state import LearningState
from app.harness.intent_router import IntentRouter
from app.agent.spec_decorator import with_spec

_router = IntentRouter()


@with_spec(intent="teach_loop", node="route_intent")
def route_intent_node(state: LearningState) -> dict:
    """意图路由节点：判断用户意图"""
    user_input = state["user_input"]
    topic = state.get("memory", {}).get("topic")
    history = state.get("memory", {}).get("history", [])

    routing = _router.route(user_input, topic, history)
    return {"routing": dict(routing)}
