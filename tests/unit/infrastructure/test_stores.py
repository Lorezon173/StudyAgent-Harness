import asyncio
from app.infrastructure.storage.eval_store import EvalStore
from app.infrastructure.storage.knowledge_store import KnowledgeStore


def test_eval_store_save_and_get():
    store = EvalStore()
    eid = asyncio.get_event_loop().run_until_complete(
        store.save("session_1", {"mastery_score": 75, "mastery_level": "partial"})
    )
    assert eid == 1
    result = asyncio.get_event_loop().run_until_complete(store.get(eid))
    assert result["mastery_score"] == 75


def test_eval_store_list_by_session():
    store = EvalStore()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(store.save("s1", {"score": 80}))
    loop.run_until_complete(store.save("s1", {"score": 90}))
    loop.run_until_complete(store.save("s2", {"score": 60}))
    results = loop.run_until_complete(store.list_by_session("s1"))
    assert len(results) == 2


def test_knowledge_store_crud():
    store = KnowledgeStore()
    loop = asyncio.get_event_loop()
    kid = loop.run_until_complete(store.create("算法知识库", "包含算法相关资料"))
    assert kid == 1
    item = loop.run_until_complete(store.get(kid))
    assert item["name"] == "算法知识库"
    all_items = loop.run_until_complete(store.list_all())
    assert len(all_items) == 1
    deleted = loop.run_until_complete(store.delete(kid))
    assert deleted is True
    assert loop.run_until_complete(store.get(kid)) is None


def test_knowledge_store_delete_missing():
    store = KnowledgeStore()
    result = asyncio.get_event_loop().run_until_complete(store.delete(999))
    assert result is False
