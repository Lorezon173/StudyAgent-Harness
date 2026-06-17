import asyncio
import tempfile
import os

from app.harness.mastery_graph import (
    MasteryNode, MasteryEdge, EdgeType, EdgeSource, MasteryGraph
)
from app.infrastructure.storage.mastery_graph_store import MasteryGraphStore


async def _make_graph(user_id: str = "user_test"):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    store = MasteryGraphStore(db_path=path)
    await store.init()
    graph = MasteryGraph(user_id=user_id, store=store)
    return graph, store, path


def test_create_graph_empty():
    async def _test():
        graph, store, path = await _make_graph()
        assert graph.user_id == "user_test"
        assert len(graph.nodes) == 0
        assert len(graph.edges) == 0
        await store.close()
        os.unlink(path)
    asyncio.run(_test())


def test_add_and_get_node():
    async def _test():
        graph, store, path = await _make_graph()
        graph.add_node(topic_id="linear_algebra", topic_name="线性代数")
        node = graph.get_node("linear_algebra")
        assert node is not None
        assert node.topic_name == "线性代数"
        assert node.mastery == 0.0
        assert node.practice_count == 0
        await store.close()
        os.unlink(path)
    asyncio.run(_test())


def test_add_and_get_edge():
    async def _test():
        graph, store, path = await _make_graph()
        graph.add_node("A", "前置A")
        graph.add_node("B", "主题B")
        graph.add_edge(from_topic="A", to_topic="B", edge_type=EdgeType.PREREQ,
                       confidence=0.5, source=EdgeSource.DOC_ORDER)
        assert "A" in [e.from_topic for e in graph.edges]
        await store.close()
        os.unlink(path)
    asyncio.run(_test())


def test_update_mastery():
    async def _test():
        graph, store, path = await _make_graph()
        graph.add_node("attention", "注意力机制")
        graph.update_mastery("attention", mastery=70)
        node = graph.get_node("attention")
        assert node.mastery == 70
        assert node.practice_count == 1
        assert node.last_practiced_at > 0
        await store.close()
        os.unlink(path)
    asyncio.run(_test())


def test_find_weak_prereqs_detects_below_threshold():
    async def _test():
        graph, store, path = await _make_graph()
        graph.add_node("vector_math", "向量乘法", mastery=20)
        graph.add_node("attention", "注意力机制", mastery=10)
        graph.add_doc_order_edge(from_topic="vector_math", to_topic="attention")
        weak = graph.find_weak_prereqs("attention", mastery_threshold=50)
        assert len(weak) == 1
        assert weak[0]["prereq_topic_id"] == "vector_math"
        assert weak[0]["mastery"] == 20
        assert weak[0]["edge_confidence"] == 0.5
        await store.close()
        os.unlink(path)
    asyncio.run(_test())


def test_find_weak_prereqs_no_weak_when_mastery_high():
    async def _test():
        graph, store, path = await _make_graph()
        graph.add_node("vector_math", "向量乘法", mastery=90)
        graph.add_node("attention", "注意力机制")
        graph.add_doc_order_edge(from_topic="vector_math", to_topic="attention")
        weak = graph.find_weak_prereqs("attention", mastery_threshold=50)
        assert len(weak) == 0
        await store.close()
        os.unlink(path)
    asyncio.run(_test())


def test_find_weak_prereqs_llm_infer_edge_stricter():
    """低置信 LLM_INFER 边(0.3)门槛更严格(adjusted≈37): mastery 40 不触发, 20 触发。"""
    async def _test():
        graph, store, path = await _make_graph()
        graph.add_node("vec", "向量", mastery=40)
        graph.add_node("attn", "注意力")
        graph.add_llm_infer_edge(from_topic="vec", to_topic="attn")
        weak = graph.find_weak_prereqs("attn", mastery_threshold=50)
        assert len(weak) == 0  # 40 > 37.04
        graph.update_mastery("vec", mastery=20)
        weak = graph.find_weak_prereqs("attn", mastery_threshold=50)
        assert len(weak) == 1  # 20 < 37.04
        assert weak[0]["prereq_topic_id"] == "vec"
        await store.close()
        os.unlink(path)
    asyncio.run(_test())


def test_find_weak_prereqs_interaction_edge_lenient():
    """高置信 INTERACTION 边(0.8)门槛宽松(adjusted≈45.45): mastery 50 不触发, 40 触发。"""
    async def _test():
        graph, store, path = await _make_graph()
        graph.add_node("vec", "向量", mastery=50)
        graph.add_node("attn", "注意力")
        graph.strengthen_edge_by_interaction(from_topic="vec", to_topic="attn")
        weak = graph.find_weak_prereqs("attn", mastery_threshold=50)
        assert len(weak) == 0  # 50 > 45.45
        graph.update_mastery("vec", mastery=40)
        weak = graph.find_weak_prereqs("attn", mastery_threshold=50)
        assert len(weak) == 1  # 40 < 45.45
        await store.close()
        os.unlink(path)
    asyncio.run(_test())


def test_find_weak_prereqs_no_prereq_edges_returns_empty():
    async def _test():
        graph, store, path = await _make_graph()
        graph.add_node("attn", "注意力")
        weak = graph.find_weak_prereqs("attn")
        assert len(weak) == 0
        await store.close()
        os.unlink(path)
    asyncio.run(_test())


def test_find_weak_prereqs_prereq_node_not_in_graph_skipped():
    async def _test():
        graph, store, path = await _make_graph()
        graph.add_node("attn", "注意力")
        graph.add_edge(from_topic="ghost", to_topic="attn", edge_type=EdgeType.PREREQ,
                       confidence=0.5, source=EdgeSource.DOC_ORDER)
        weak = graph.find_weak_prereqs("attn")
        assert len(weak) == 0
        await store.close()
        os.unlink(path)
    asyncio.run(_test())


def test_has_any_prereqs():
    async def _test():
        graph, store, path = await _make_graph()
        graph.add_node("A", "前置")
        graph.add_node("B", "主题")
        assert not graph.has_any_prereqs("B")
        graph.add_doc_order_edge(from_topic="A", to_topic="B")
        assert graph.has_any_prereqs("B")
        await store.close()
        os.unlink(path)
    asyncio.run(_test())


def test_graph_persist_roundtrip():
    async def _test():
        graph, store, path = await _make_graph()
        graph.add_node("vec", "向量", mastery=80)
        graph.add_node("attn", "注意力", mastery=30)
        graph.add_doc_order_edge(from_topic="vec", to_topic="attn")
        await graph.save()
        graph2 = MasteryGraph(user_id="user_test", store=store)
        await graph2.load()
        assert len(graph2.nodes) == 2
        assert graph2.nodes["vec"].mastery == 80
        assert graph2.nodes["vec"].topic_name == "向量"
        assert len(graph2.edges) == 1
        assert graph2.edges[0].from_topic == "vec"
        assert graph2.edges[0].confidence == 0.5
        assert graph2.edges[0].source == EdgeSource.DOC_ORDER
        await store.close()
        os.unlink(path)
    asyncio.run(_test())
