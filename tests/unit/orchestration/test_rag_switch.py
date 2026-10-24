"""在线开关与可信可见性：关闭路径无检索，开启路径身份不由事件控制。"""
import pytest

from app.core.config import Settings, settings
from app.harness.enums import ActionKind, EventSource, EventType
from app.harness.events import Event
from app.harness.orchestrator import Orchestrator
from app.harness.workspace_state import WorkspaceState
from app.orchestration import assembly


def _forbid(*args, **kwargs):
    pytest.fail("关闭 RAG 时调用了检索依赖")


def test_default_online_teaching_never_constructs_retrieval(monkeypatch, mock_llm_invoke_json):
    defaults = Settings(_env_file=None)
    monkeypatch.setitem(settings.__dict__, "rag_enabled", defaults.rag_enabled)
    monkeypatch.setattr(settings, "rag_backend", "pgvector")
    monkeypatch.setattr(assembly, "build_online_rag_coordinator", _forbid)
    monkeypatch.setattr(assembly, "RetrieverAgent", _forbid)
    monkeypatch.setattr("app.infrastructure.rag.pgvector_provider.PgVectorProvider", _forbid)
    monkeypatch.setattr("app.infrastructure.rag.embedding.EmbeddingService.__init__", _forbid)
    mock_llm_invoke_json({"tutor_ask": {"content": "请解释你的理解"}, "critic_assess": {}})
    result = assembly.run_online_agent_session("off-default", 7, "什么是递归")
    assert result.reply == "请解释你的理解"
    assert not any(e.source == EventSource.RETRIEVER for e in result.events)


def test_disabled_stack_cannot_subscribe_injected_retriever():
    class InjectedRetriever:
        subscriptions = [EventType.ACTION_REQUESTED]
        handle = _forbid

    injected = InjectedRetriever()
    bus, _, store = assembly.build_new_stack(1, retriever=injected, rag_enabled=False)
    try:
        assert injected not in bus.subscribers_of(EventType.ACTION_REQUESTED)
    finally:
        store.close()


def test_disabled_rule_retrieval_routes_to_tutor():
    orch = Orchestrator(rag_enabled=False)
    ws = WorkspaceState(session_id="off-rule", user_id=1)
    tick = orch.on_event(Event(type=EventType.RAG_QUALITY_ASSESSED,
                              source=EventSource.CRITIC, session_id=ws.session_id,
                              payload={"score": 0.1}), ws)[0]
    actions = [e for e in orch.on_event(tick, ws) if e.type == EventType.ACTION_REQUESTED]
    assert len(actions) == 1
    assert actions[0].payload == {"action": "tutor_ask", "target": "tutor"}


@pytest.mark.parametrize("action,target", [
    ("retriever_search", "retriever"), ("retriever_expand_query", ""),
    ("tutor_explain", "retriever"),
])
def test_disabled_conductor_retrieval_routes_to_tutor(action, target):
    orch = Orchestrator(rag_enabled=False)
    ws = WorkspaceState(session_id="off-conductor", user_id=1)
    out = orch.on_event(Event(type=EventType.CONDUCTOR_DECIDED,
                             source=EventSource.CONDUCTOR, session_id=ws.session_id,
                             payload={"action": action, "target": target}), ws)
    assert out[0].payload["action"] == "tutor_ask"
    assert out[0].payload["target"] == "tutor"


def test_disabled_conductor_search_ends_without_fuse(monkeypatch, mock_llm_invoke_json):
    monkeypatch.setitem(settings.__dict__, "rag_enabled", False)
    mock_llm_invoke_json({
        "tutor_ask": {"content": "你的理解是什么"},
        "critic_assess": {"low_confidence": True},
        "conductor_decide": {"action": "retriever_search", "target": "retriever"},
    })
    result = assembly.run_online_agent_session("off-loop", 1, "递归")
    assert result.reply == "你的理解是什么"
    assert result.turn_count < 50
    assert not any(e.source == EventSource.RETRIEVER for e in result.events)
    assert not any(e.type == EventType.ACTION_REQUESTED and e.payload.get("target") == "retriever"
                   for e in result.events)


def _online_retriever(monkeypatch):
    from app.infrastructure.rag.coordinator import RAGCoordinator
    from app.infrastructure.rag.pgvector_provider import PgVectorProvider

    monkeypatch.setitem(settings.__dict__, "rag_enabled", True)
    monkeypatch.setattr(settings, "rag_backend", "pgvector")
    monkeypatch.setattr(settings, "database_url", "postgresql+asyncpg://u:p@localhost/test")
    coordinator = RAGCoordinator(vector_provider=PgVectorProvider())
    monkeypatch.setattr(assembly, "build_online_rag_coordinator", lambda: coordinator)
    captured = {}

    def capture(*args, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(assembly, "run_new_agent_session", capture)
    assembly.run_online_agent_session("visible", 7, "递归")
    return captured["retriever"], coordinator


def _request(ws, **payload):
    return Event(type=EventType.ACTION_REQUESTED, source=EventSource.ORCHESTRATOR,
                 session_id=ws.session_id,
                 payload={"target": "retriever", "action": str(ActionKind.RETRIEVER_SEARCH),
                          "query": "知识", **payload})


def test_online_visibility_uses_authenticated_user_and_only_vector(monkeypatch):
    agent, coordinator = _online_retriever(monkeypatch)
    from app.infrastructure.rag.coordinator import Chunk
    seen = []

    def search(query, top_k=5, visibility=None):
        assert visibility is not None
        seen.append(visibility.user_id)
        return [Chunk("知识", 0.9)]

    monkeypatch.setattr(coordinator.get_provider("vector"), "search", search)
    ws = WorkspaceState(session_id="visible", user_id=7)
    out = agent.handle(_request(ws), ws)
    assert out[0].type == EventType.RETRIEVED_EVIDENCE
    assert seen == [7]


@pytest.mark.parametrize("payload,workspace_user", [
    ({"visibility": {"user_id": 8}, "user_id": 8, "retrieval_id": "r"}, 7),
    ({"visibility": None}, 7), ({"user_id": 8}, 7), ({}, 8),
    ({"user_id": 7.0}, 7), ({}, 7.0),
])
def test_online_rejects_visibility_override_or_workspace_mismatch(monkeypatch, payload, workspace_user):
    agent, coordinator = _online_retriever(monkeypatch)
    monkeypatch.setattr(coordinator, "search", _forbid)
    ws = WorkspaceState(session_id="visible", user_id=workspace_user)
    out = agent.handle(_request(ws, **payload), ws)
    assert out[0].type == EventType.RETRIEVAL_FAILED
    assert out[0].payload["error_code"] == "invalid_request"


@pytest.mark.parametrize("source", ["ocr", "code"])
def test_online_never_falls_back_to_unfiltered_sources(monkeypatch, source):
    agent, coordinator = _online_retriever(monkeypatch)
    from app.infrastructure.rag.coordinator import IndexProvider

    class UnsafeProvider(IndexProvider):
        name = source
        index = _forbid
        search = _forbid
        doc_count = 0

    coordinator.register_provider(UnsafeProvider())
    monkeypatch.setattr(coordinator.get_provider("vector"), "search", lambda *a, **k: [])
    ws = WorkspaceState(session_id="visible", user_id=7)
    assert agent.handle(_request(ws), ws)[0].payload["retrieval_status"] == "empty"
    out = agent.handle(_request(ws, sources=[source]), ws)
    assert out[0].type == EventType.RETRIEVAL_FAILED
    assert out[0].payload["error_code"] == "invalid_request"


def test_online_visibility_filters_real_vector_rows_across_topics(monkeypatch):
    """真实 PgVectorProvider SQL 过滤；仅数据库和 embedding 用离线替身。"""
    from types import SimpleNamespace
    from sqlalchemy import create_engine, text

    agent, coordinator = _online_retriever(monkeypatch)
    provider = coordinator.get_provider("vector")
    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as connection:
        connection.execute(text("""CREATE TABLE vector_chunks (
            content TEXT, source TEXT, doc_id TEXT, chunk_id TEXT,
            metadata_json TEXT, scope TEXT, user_id INTEGER)"""))
        for content, scope, owner, topic in [
            ("公共知识", "global", None, "public"),
            ("本人主题甲知识", "private", 7, "topic-a"),
            ("本人主题乙知识", "private", 7, "topic-b"),
            ("他人知识", "private", 8, "topic-a"),
            ("无主私有知识", "private", None, "topic-a"),
        ]:
            connection.execute(text("INSERT INTO vector_chunks VALUES "
                                    "(:content, 'vector', :topic, '', '{}', :scope, :owner)"),
                               {"content": content, "topic": topic, "scope": scope, "owner": owner})
        monkeypatch.setattr(provider, "_get_conn", lambda: connection)
        monkeypatch.setattr(provider, "_embedding", SimpleNamespace(embed_one=lambda query: [0.5]))
        ws = WorkspaceState(session_id="visible", user_id=7)
        out = agent.handle(_request(ws), ws)
        assert out[0].type == EventType.RETRIEVED_EVIDENCE
        assert {chunk["content"] for chunk in out[0].payload["chunks"]} == {
            "公共知识", "本人主题甲知识", "本人主题乙知识"}
    engine.dispose()
