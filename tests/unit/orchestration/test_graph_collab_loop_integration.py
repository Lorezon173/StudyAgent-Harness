import os
import tempfile

from app.orchestration.graph import build_main_graph, build_collab_runtime
from app.harness.eventbus import EventBus
from app.infrastructure.storage.event_store import EventStore
from app.harness.events import Event
from app.harness.enums import EventType, EventSource
from app.harness.workspace_state import WorkspaceState
from app.harness.orchestrator import Orchestrator
from app.agents.tutor import TutorAgent
from app.agents.critic import CriticAgent
from app.agents.conductor import ConductorAgent


def _store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = EventStore(db_path=path)
    s.init()
    return s, path


def test_collab_runtime_factory_returns_bus_orchestrator_agents():
    store, path = _store()
    try:
        runtime = build_collab_runtime(EventBus(store=store))
        assert runtime.bus is not None
        assert runtime.orchestrator is not None
        assert TutorAgent in {type(a) for a in
                              runtime.bus.subscribers_of(EventType.ACTION_REQUESTED)}
        assert CriticAgent in {type(a) for a in
                               runtime.bus.subscribers_of(EventType.USER_MESSAGE)}
        assert ConductorAgent in {type(a) for a in
                                  runtime.bus.subscribers_of(EventType.CONDUCTOR_REQUESTED)}
    finally:
        store.close()
        os.unlink(path)


def test_collab_loop_node_runs_when_runtime_present(mock_llm_invoke_json):
    mock_llm_invoke_json({
        "critic_assess": {"mastery_level": "mastered", "rationale": "ok"},
    })
    store, path = _store()
    try:
        bus = EventBus(store=store)
        runtime = build_collab_runtime(bus)
        ws = WorkspaceState(session_id="s1", user_id="u1", current_topic="RAG")
        seeds = [Event(type=EventType.USER_MESSAGE, source=EventSource.USER,
                       session_id="s1", payload={"text": "我已经懂 RAG 了"})]
        g = build_main_graph()
        out = g.invoke({
            "session_id": "s1", "user_id": "u1", "enter_loop": True,
            "_runtime": {"runtime": runtime, "ws": ws, "seeds": seeds},
        }, config={"configurable": {"thread_id": "t-int-1"}})
        assert "collab_loop" in out["visited"]
        events = bus.replay("s1")
        types = [e.type for e in events]
        assert EventType.USER_MESSAGE in types
        assert EventType.MASTERY_ASSESSED in types
        assert EventType.LOOP_EXIT in types
    finally:
        store.close()
        os.unlink(path)
