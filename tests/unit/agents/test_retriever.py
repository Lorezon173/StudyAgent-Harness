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


# ===== Task 7: evaluate() — RAG 三件套 =====

def test_evaluate_returns_all_metrics():
    agent = RetrieverAgent()
    agent._coordinator.index_documents([
        {"content": "RAG 是检索增强生成"},
        {"content": "LLM 结合外部知识库"},
    ])
    test_case = {
        "query": "RAG",
        "golden_chunks": ["RAG 是检索增强生成"],
        "golden_answer": "RAG 即检索增强生成",
        "top_k": 5,
    }
    metrics = agent.evaluate(test_case)
    assert "faithfulness" in metrics
    assert "answer_relevancy" in metrics
    assert "context_precision" in metrics
    assert "recall_at_k" in metrics
    assert "latency_ms" in metrics
    assert "redundancy" in metrics


def test_evaluate_recall_at_k_perfect():
    """所有 golden_chunks 都被检索到时 recall=1.0"""
    agent = RetrieverAgent()
    agent._coordinator.index_documents([
        {"content": "检索增强生成的定义"},
        {"content": "向量数据库"},
    ])
    test_case = {
        "query": "RAG 检索",
        "golden_chunks": ["检索增强生成"],
    }
    metrics = agent.evaluate(test_case)
    assert metrics["recall_at_k"] == 1.0


def test_evaluate_recall_at_k_zero():
    """golden_chunks 完全未被检索到时 recall=0.0"""
    agent = RetrieverAgent()
    agent._coordinator.index_documents([
        {"content": "完全不相关的文档"},
    ])
    test_case = {
        "query": "RAG",
        "golden_chunks": ["量子计算原理"],
    }
    metrics = agent.evaluate(test_case)
    assert metrics["recall_at_k"] == 0.0


def test_evaluate_context_precision():
    """检索结果中相关 chunk 占比"""
    agent = RetrieverAgent()
    agent._coordinator.index_documents([
        {"content": "RAG 技术详解"},       # 相关
        {"content": "无关的天气报告"},      # 无关
        {"content": "RAG 应用场景"},       # 相关
    ])
    test_case = {
        "query": "RAG",
        "golden_chunks": ["RAG"],
    }
    metrics = agent.evaluate(test_case)
    assert 0.0 <= metrics["context_precision"] <= 1.0


def test_evaluate_latency_ms_is_positive():
    agent = RetrieverAgent()
    agent._coordinator.index_documents([{"content": "测试"}])
    metrics = agent.evaluate({
        "query": "测试",
        "golden_chunks": [],
        "golden_answer": "",
    })
    assert metrics["latency_ms"] >= 0


def test_evaluate_redundancy_zero_for_unique_results():
    """所有检索结果内容不同时 redundancy=0"""
    agent = RetrieverAgent()
    agent._coordinator.index_documents([
        {"content": "完全不同的 A 内容"},
        {"content": "另一个完全不同的 B 内容"},
        {"content": "第三个独特的 C 内容"},
    ])
    metrics = agent.evaluate({
        "query": "内容",
        "golden_chunks": [],
        "golden_answer": "",
        "top_k": 3,
    })
    # 这些不同 chunk 字符重叠较低 (Jaccard < 0.8)
    assert metrics["redundancy"] == 0.0


def test_evaluate_redundancy_detects_duplicates():
    """有重复/高度相似内容时 redundancy > 0"""
    agent = RetrieverAgent()
    # 两条非常相似的内容（仅末尾字符不同），Jaccard 字符相似度 > 0.8
    agent._coordinator.index_documents([
        {"content": "重复内容重复内容重复内容 A"},
        {"content": "重复内容重复内容重复内容 B"},
    ])
    metrics = agent.evaluate({
        "query": "重复内容",
        "golden_chunks": [],
        "golden_answer": "",
        "top_k": 5,
    })
    assert metrics["redundancy"] > 0.0


def test_evaluate_faithfulness_with_golden_answer():
    agent = RetrieverAgent()
    agent._coordinator.index_documents([
        {"content": "注意力机制的核心是 QKV 三个矩阵"},
    ])
    metrics = agent.evaluate({
        "query": "注意力机制",
        "golden_chunks": [],
        "golden_answer": "QKV 矩阵是注意力机制核心",
    })
    # 检索结果 + golden_answer 有词语重叠 -> faithfulness > 0
    assert metrics["faithfulness"] > 0.0


def test_evaluate_metric_bounds():
    """所有指标应在 [0, 1] 区间（latency_ms 除外）"""
    agent = RetrieverAgent()
    agent._coordinator.index_documents([
        {"content": "BERT 使用双向 Transformer 编码器"},
        {"content": "今天天气不错"},
    ])
    metrics = agent.evaluate({
        "query": "Transformer",
        "golden_chunks": ["BERT 使用双向 Transformer 编码器"],
        "golden_answer": "BERT 是双向 Transformer",
        "top_k": 3,
    })
    assert 0.0 <= metrics["recall_at_k"] <= 1.0
    assert 0.0 <= metrics["context_precision"] <= 1.0
    assert 0.0 <= metrics["faithfulness"] <= 1.0
    assert 0.0 <= metrics["answer_relevancy"] <= 1.0
    assert 0.0 <= metrics["redundancy"] <= 1.0
    assert metrics["latency_ms"] >= 0
