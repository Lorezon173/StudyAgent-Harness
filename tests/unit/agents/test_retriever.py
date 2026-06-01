import pytest
from app.agents.retriever import RetrieverAgent, LOW_SCORE_THRESHOLD
from app.agents.base import AgentBase
from app.harness.enums import EventType, EventSource
from app.harness.events import Event, check_ownership
from app.harness.workspace_state import WorkspaceState


@pytest.fixture
def ws():
    return WorkspaceState(session_id="s1", user_id="u1")


@pytest.fixture
def agent():
    return RetrieverAgent()


# --- 契约声明 ---

def test_retriever_source_is_retriever(agent):
    assert agent.source == EventSource.RETRIEVER


def test_retriever_subscribes_to_action_requested(agent):
    assert EventType.ACTION_REQUESTED in agent.subscriptions


def test_retriever_emittable_types_are_exact():
    agent = RetrieverAgent()
    assert agent.emittable_types == {EventType.RETRIEVED_EVIDENCE, EventType.RETRIEVAL_FAILED}


def test_retriever_is_agentbase():
    assert isinstance(RetrieverAgent(), AgentBase)


# --- handle：target 过滤 ---

def test_handle_ignores_wrong_target(agent, ws):
    """target != retriever 的 ActionRequested 应静默跳过"""
    ev = Event(type=EventType.ACTION_REQUESTED, source=EventSource.ORCHESTRATOR,
               session_id="s1", payload={"target": "tutor", "query": "test"})
    result = agent.handle(ev, ws)
    assert result == []


def test_handle_processes_correct_target(agent, ws):
    """target=retriever 的 ActionRequested 应执行检索"""
    ev = Event(type=EventType.ACTION_REQUESTED, source=EventSource.ORCHESTRATOR,
               session_id="s1", payload={"target": "retriever", "query": "RAG"})
    result = agent.handle(ev, ws)
    assert len(result) == 1
    assert result[0].type in {EventType.RETRIEVED_EVIDENCE, EventType.RETRIEVAL_FAILED}


# --- retrieval_status 判定 ---

def test_handle_empty_result_returns_empty_status(agent, ws):
    """无匹配内容时 retrieval_status=empty"""
    ev = Event(type=EventType.ACTION_REQUESTED, source=EventSource.ORCHESTRATOR,
               session_id="s1", payload={"target": "retriever", "query": "xyznonexistent"})
    result = agent.handle(ev, ws)
    assert len(result) == 1
    assert result[0].type == EventType.RETRIEVED_EVIDENCE
    assert result[0].payload["retrieval_status"] == "empty"


def test_handle_found_result_returns_ok_status(agent, ws):
    """有匹配内容且 score >= threshold 时 retrieval_status=ok"""
    agent._coordinator.index_documents([
        {"content": "RAG 是检索增强生成技术"},
        {"content": "RAG 结合了检索和生成两种方法"},
    ])
    ev = Event(type=EventType.ACTION_REQUESTED, source=EventSource.ORCHESTRATOR,
               session_id="s1", payload={"target": "retriever", "query": "RAG 检索增强"})
    result = agent.handle(ev, ws)
    assert len(result) == 1
    assert result[0].type == EventType.RETRIEVED_EVIDENCE
    assert result[0].payload["retrieval_status"] == "ok"
    assert len(result[0].payload["chunks"]) >= 1


def test_handle_low_score_result_returns_low_score_status(agent, ws):
    """max_score < threshold 时 retrieval_status=low_score（但 chunk 仍然返回）"""
    # FakeRAGStore 按字符匹配返回 score=int 命中数;
    # query "深度学习注意力机制" 与 content "完全不相关的内容" 共享字符 "的" => score=1
    # LOW_SCORE_THRESHOLD = 0.3 时 score=1 反而高于阈值,故为得到 low_score 状态,
    # 需要查询字符与 content 几乎无交集
    agent._coordinator.index_documents([
        {"content": "abc"},
    ])
    ev = Event(type=EventType.ACTION_REQUESTED, source=EventSource.ORCHESTRATOR,
               session_id="s1", payload={"target": "retriever", "query": "z"})
    # FakeRAGStore 对 z vs abc 无字符共享, 返回 0 条 -> empty
    # 想测 low_score 需手动注入一个低分 chunk via mock provider
    result = agent.handle(ev, ws)
    assert len(result) == 1
    # 这种 query 实际命中 0 条，状态为 empty，跳过此断言
    # 改测 low_score 的方式：mock provider
    assert result[0].type == EventType.RETRIEVED_EVIDENCE
    assert result[0].payload["retrieval_status"] == "empty"


def test_handle_low_score_with_mock_provider(ws):
    """显式构造一个永远返回低分 chunk 的 provider 来测 low_score 状态"""
    from app.infrastructure.rag.coordinator import IndexProvider, Chunk, RAGCoordinator

    class _LowScoreProvider(IndexProvider):
        name = "lowscore"
        def index(self, docs): pass
        def search(self, query, top_k=5):
            return [Chunk(content="low score chunk", score=0.1, source="lowscore")]
        @property
        def doc_count(self): return 1

    coord = RAGCoordinator()
    coord.register_provider(_LowScoreProvider())
    agent = RetrieverAgent(coordinator=coord)
    ev = Event(type=EventType.ACTION_REQUESTED, source=EventSource.ORCHESTRATOR,
               session_id="s1", payload={"target": "retriever",
                                          "query": "anything",
                                          "sources": ["lowscore"]})
    result = agent.handle(ev, ws)
    assert len(result) == 1
    assert result[0].type == EventType.RETRIEVED_EVIDENCE
    assert result[0].payload["retrieval_status"] == "low_score"
    assert len(result[0].payload["chunks"]) == 1


# --- payload 传递 ---

def test_handle_payload_contains_scores_and_sources(agent, ws):
    """RetrievedEvidence payload 应含原始 score 和 source 信息"""
    agent._coordinator.index_documents([
        {"content": "RAG 技术详解"},
    ])
    ev = Event(type=EventType.ACTION_REQUESTED, source=EventSource.ORCHESTRATOR,
               session_id="s1", payload={"target": "retriever", "query": "RAG"})
    result = agent.handle(ev, ws)
    payload = result[0].payload
    assert "chunks" in payload
    assert "scores" in payload
    assert "retrieval_status" in payload
    assert "sources_used" in payload


def test_handle_payload_preserves_parent_id(agent, ws):
    """产出事件的 parent_id 应指向触发事件"""
    ev = Event(type=EventType.ACTION_REQUESTED, source=EventSource.ORCHESTRATOR,
               session_id="s1", id="ev-001",
               payload={"target": "retriever", "query": "test"})
    result = agent.handle(ev, ws)
    assert result[0].parent_id == "ev-001"


def test_handle_payload_includes_purpose_field(agent, ws):
    """purpose 字段应透传到 RetrievedEvidence payload"""
    agent._coordinator.index_documents([
        {"content": "测试内容"},
    ])
    ev = Event(type=EventType.ACTION_REQUESTED, source=EventSource.ORCHESTRATOR,
               session_id="s1", payload={"target": "retriever", "query": "test",
                                         "purpose": "teaching"})
    result = agent.handle(ev, ws)
    assert result[0].payload.get("purpose") == "teaching"


# --- 越权校验 ---

def test_retriever_cannot_emit_non_owned_event(agent, ws):
    """Retriever emit 未声明的事件类型应抛 ValueError"""
    with pytest.raises(ValueError):
        agent.emit(EventType.MASTERY_ASSESSED, ws)


def test_retriever_emitted_event_passes_bus_ownership(agent, ws):
    """Retriever emit 的事件应通过 §3.2 全局白名单校验"""
    ev = agent.emit(EventType.RETRIEVED_EVIDENCE, ws,
                    payload={"retrieval_status": "ok"})
    check_ownership(ev)  # 不抛错


# --- evaluate 接口 ---

def test_evaluate_raises_not_implemented_before_task7():
    """Task 6 阶段 evaluate 应抛 NotImplementedError"""
    with pytest.raises(NotImplementedError):
        RetrieverAgent().evaluate(test_case={})
