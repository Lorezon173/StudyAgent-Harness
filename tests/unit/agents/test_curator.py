import asyncio
import tempfile
import os

import pytest

from app.agents.curator import Curator
from app.harness.events import Event, check_ownership
from app.harness.enums import EventType, EventSource
from app.harness.workspace_state import WorkspaceState
from app.harness.mastery_graph import MasteryGraph
from app.infrastructure.storage.mastery_graph_store import MasteryGraphStore


async def _setup_curator(user_id: str = "user_1",
                         session_id: str = "s1",
                         current_topic: str = "attention"):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    store = MasteryGraphStore(db_path=path)
    await store.init()
    graph = MasteryGraph(user_id=user_id, store=store)
    curator = Curator(graph=graph, store=store)
    ws = WorkspaceState(
        session_id=session_id, user_id=user_id, current_topic=current_topic)
    return curator, ws, store, path


# ---- 声明契约 ----

def test_curator_source():
    assert Curator.source == EventSource.CURATOR


def test_curator_subscriptions():
    assert EventType.MASTERY_ASSESSED in Curator.subscriptions
    assert EventType.TOPIC_ENTERED in Curator.subscriptions


def test_curator_emittable_types():
    assert Curator.emittable_types == {
        EventType.PROFILE_UPDATED,
        EventType.GRAPH_NODE_STRENGTHENED,
        EventType.GRAPH_PREREQ_WEAK_DETECTED,
    }


# ---- MasteryAssessed 触发 ----

def test_handle_mastery_assessed_updates_node():
    async def _test():
        curator, ws, store, path = await _setup_curator()
        curator.graph.add_node("attention", "注意力机制", mastery=30)
        event = Event(type=EventType.MASTERY_ASSESSED, source=EventSource.CRITIC,
                      session_id="s1", payload={
                          "topic_id": "attention",
                          "level": "partial",
                          "score": 65,
                          "rationale": "能复述核心定义但举例不充分",
                      })
        results = curator.handle(event, ws)
        node = curator.graph.get_node("attention")
        assert node is not None
        assert node.mastery == 65
        assert node.practice_count == 1
        assert node.last_practiced_at > 0
        strengthened = [e for e in results if e.type == EventType.GRAPH_NODE_STRENGTHENED]
        assert len(strengthened) == 1
        assert strengthened[0].payload["topic_id"] == "attention"
        assert strengthened[0].payload["mastery"] == 65
        assert strengthened[0].payload["rationale"] == "能复述核心定义但举例不充分"
        profile_updates = [e for e in results if e.type == EventType.PROFILE_UPDATED]
        assert len(profile_updates) == 1
        await store.close()
        os.unlink(path)
    asyncio.run(_test())


def test_handle_mastery_assessed_with_weak_prereq_emits_observed():
    async def _test():
        curator, ws, store, path = await _setup_curator(current_topic="transformer")
        # 线性代数 weak (20) → transformer; 注意力 strong (70) → transformer
        curator.graph.add_node("linear_algebra", "线性代数", mastery=20)
        curator.graph.add_node("attention", "注意力机制", mastery=70)
        curator.graph.add_node("transformer", "Transformer架构", mastery=30)
        curator.graph.add_doc_order_edge(from_topic="linear_algebra", to_topic="transformer")
        curator.graph.add_doc_order_edge(from_topic="attention", to_topic="transformer")
        event = Event(type=EventType.MASTERY_ASSESSED, source=EventSource.CRITIC,
                      session_id="s1", payload={
                          "topic_id": "transformer",
                          "level": "weak",
                          "score": 30,
                      })
        results = curator.handle(event, ws)
        prereq_events = [e for e in results if e.type == EventType.GRAPH_PREREQ_WEAK_DETECTED]
        assert len(prereq_events) >= 1
        prereq_ids = [e.payload["prereq_topic_id"] for e in prereq_events]
        assert "linear_algebra" in prereq_ids
        assert "attention" not in prereq_ids
        for e in prereq_events:
            assert e.payload["basis"] == "observed"
        await store.close()
        os.unlink(path)
    asyncio.run(_test())


def test_handle_mastery_assessed_no_prereqs_no_prereq_event():
    async def _test():
        curator, ws, store, path = await _setup_curator()
        curator.graph.add_node("attention", "注意力机制", mastery=30)
        event = Event(type=EventType.MASTERY_ASSESSED, source=EventSource.CRITIC,
                      session_id="s1", payload={
                          "topic_id": "attention",
                          "level": "weak",
                          "score": 30,
                      })
        results = curator.handle(event, ws)
        prereq_events = [e for e in results if e.type == EventType.GRAPH_PREREQ_WEAK_DETECTED]
        assert len(prereq_events) == 0
        await store.close()
        os.unlink(path)
    asyncio.run(_test())


# ---- TopicEntered 触发 — 渐进启用 ----

def test_handle_topic_entered_cold_start_no_historical_signal():
    """冷启动：图谱无 PREREQ 边 → historical 分支不触发。"""
    async def _test():
        curator, ws, store, path = await _setup_curator(current_topic="attention")
        curator.graph.add_node("attention", "注意力机制", mastery=0.0)
        event = Event(type=EventType.TOPIC_ENTERED, source=EventSource.ORCHESTRATOR,
                      session_id="s1", payload={"topic_id": "attention"})
        results = curator.handle(event, ws)
        prereq_events = [e for e in results if e.type == EventType.GRAPH_PREREQ_WEAK_DETECTED]
        assert len(prereq_events) == 0
        await store.close()
        os.unlink(path)
    asyncio.run(_test())


def test_handle_topic_entered_with_historical_weak_prereq():
    """画像有数据：前置 mastery 低 → 发 basis=historical。"""
    async def _test():
        curator, ws, store, path = await _setup_curator(current_topic="transformer")
        curator.graph.add_node("linear_algebra", "线性代数", mastery=20)
        curator.graph.add_node("attention", "注意力机制", mastery=90)
        curator.graph.add_node("transformer", "Transformer架构")
        curator.graph.add_doc_order_edge(from_topic="linear_algebra", to_topic="transformer")
        curator.graph.add_doc_order_edge(from_topic="attention", to_topic="transformer")
        event = Event(type=EventType.TOPIC_ENTERED, source=EventSource.ORCHESTRATOR,
                      session_id="s1", payload={"topic_id": "transformer"})
        results = curator.handle(event, ws)
        prereq_events = [e for e in results if e.type == EventType.GRAPH_PREREQ_WEAK_DETECTED]
        assert len(prereq_events) >= 1
        for e in prereq_events:
            assert e.payload["basis"] == "historical"
        prereq_ids = [e.payload["prereq_topic_id"] for e in prereq_events]
        assert "linear_algebra" in prereq_ids
        assert "attention" not in prereq_ids
        await store.close()
        os.unlink(path)
    asyncio.run(_test())


def test_handle_topic_entered_with_no_weak_prereq_emits_nothing():
    """画像所有前置都强 → 不发事件。"""
    async def _test():
        curator, ws, store, path = await _setup_curator(current_topic="transformer")
        curator.graph.add_node("linear_algebra", "线性代数", mastery=90)
        curator.graph.add_node("attention", "注意力机制", mastery=95)
        curator.graph.add_node("transformer", "Transformer架构")
        curator.graph.add_doc_order_edge(from_topic="linear_algebra", to_topic="transformer")
        curator.graph.add_doc_order_edge(from_topic="attention", to_topic="transformer")
        event = Event(type=EventType.TOPIC_ENTERED, source=EventSource.ORCHESTRATOR,
                      session_id="s1", payload={"topic_id": "transformer"})
        results = curator.handle(event, ws)
        prereq_events = [e for e in results if e.type == EventType.GRAPH_PREREQ_WEAK_DETECTED]
        assert len(prereq_events) == 0
        await store.close()
        os.unlink(path)
    asyncio.run(_test())


# ---- 事件所有权 ----

def test_curator_events_pass_ownership():
    """Curator emit 的事件经 EventBus 白名单校验不抛错。"""
    async def _test():
        curator, ws, _store, path = await _setup_curator()
        for etype in (EventType.PROFILE_UPDATED, EventType.GRAPH_NODE_STRENGTHENED,
                      EventType.GRAPH_PREREQ_WEAK_DETECTED):
            ev = curator.emit(etype, ws)
            check_ownership(ev)  # 不抛错 = 白名单校验通过
        await _store.close()
        os.unlink(path)
    asyncio.run(_test())


def test_curator_cannot_emit_critic_event():
    """Curator 不能 emit Critic 的事件（emittable_types 拦截）。"""
    async def _test():
        curator, ws, store, path = await _setup_curator()
        with pytest.raises(ValueError):
            curator.emit(EventType.CONFUSION_DETECTED, ws)
        await store.close()
        os.unlink(path)
    asyncio.run(_test())


# ---- evaluate 接口 ----

def test_curator_evaluate_returns_metrics():
    async def _test():
        curator, ws, store, path = await _setup_curator()
        curator.graph.add_node("A", "前置A", mastery=80)
        curator.graph.add_node("B", "主题B", mastery=50)
        curator.graph.add_doc_order_edge(from_topic="A", to_topic="B")
        metrics = curator.evaluate({
            "graph_nodes": {"A": 80, "B": 50},
            "graph_edges": [{"from": "A", "to": "B"}],
        })
        assert isinstance(metrics, dict)
        assert "coverage" in metrics
        assert metrics["coverage"] == 1.0
        await store.close()
        os.unlink(path)
    asyncio.run(_test())


def test_curator_evaluate_partial_coverage():
    async def _test():
        curator, ws, store, path = await _setup_curator()
        curator.graph.add_node("A", "前置A", mastery=80)
        metrics = curator.evaluate({
            "graph_nodes": {"A": 80, "B": 50},
            "graph_edges": [],
        })
        assert isinstance(metrics, dict)
        assert metrics["coverage"] == 0.5
        await store.close()
        os.unlink(path)
    asyncio.run(_test())
