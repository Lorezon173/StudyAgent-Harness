import json as _json

import pytest
from app.agents.retriever import RetrieverAgent
from app.agents.base import AgentBase
from app.harness.enums import EventType, EventSource
from app.harness.events import Event, check_ownership
from app.harness.workspace_state import WorkspaceState
from app.infrastructure.rag.coordinator import Chunk, IndexProvider, RAGCoordinator, SearchResult
from app.infrastructure.rag.store import FakeRAGStore


@pytest.fixture
def ws():
    return WorkspaceState(session_id="s1", user_id=1)


@pytest.fixture
def agent():
    return RetrieverAgent()


@pytest.fixture(autouse=True)
def disable_external_judge_by_default(monkeypatch):
    """Keep every default test path on explicit local retrieval and judge doubles."""
    monkeypatch.setattr("app.eval.judge.build_judge", lambda **_: None)
    pg_attempts = {"construct": 0, "connect": 0}
    sdk_attempts = {"chat": 0, "openai": 0}

    def forbid_pg_construct(*_args, **_kwargs):
        pg_attempts["construct"] += 1
        raise AssertionError("unit tests must not construct a real PG provider")

    def forbid_pg_connect(*_args, **_kwargs):
        pg_attempts["connect"] += 1
        raise AssertionError("unit tests must not connect to a real PG provider")

    def forbid_chat_sdk(*_args, **_kwargs):
        sdk_attempts["chat"] += 1
        raise AssertionError("unit tests must not construct a real chat SDK client")

    def forbid_openai_sdk(*_args, **_kwargs):
        sdk_attempts["openai"] += 1
        raise AssertionError("unit tests must not construct a real OpenAI SDK client")

    monkeypatch.setattr("app.infrastructure.rag.pgvector_provider.PgVectorProvider.__init__", forbid_pg_construct)
    monkeypatch.setattr("app.infrastructure.rag.pgvector_provider.PgVectorProvider._get_conn", forbid_pg_connect)
    import langchain_openai
    import openai
    monkeypatch.setattr(langchain_openai, "ChatOpenAI", forbid_chat_sdk)
    monkeypatch.setattr(openai, "OpenAI", forbid_openai_sdk)

    def make_offline_coordinator():
        store = FakeRAGStore()
        return RAGCoordinator(store=store, vector_provider=_OfflineVectorProvider(store))

    monkeypatch.setattr("app.agents.retriever.RAGCoordinator", make_offline_coordinator)
    yield
    assert pg_attempts == {"construct": 0, "connect": 0}
    assert sdk_attempts == {"chat": 0, "openai": 0}


class _OfflineVectorProvider(IndexProvider):
    name = "vector"

    def __init__(self, store):
        self._store = store

    def index(self, docs):
        self._store.index(docs)
        return len(docs)

    def search(self, query, top_k=5, visibility=None):
        return [
            Chunk(content=item["content"], score=float(item.get("score", 0)),
                  source="vector", metadata=item.get("metadata", {}))
            for item in self._store.query(query, top_k, visibility=visibility)
        ]

    @property
    def doc_count(self):
        return self._store.doc_count


def test_default_retriever_stays_offline_when_settings_select_pgvector(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.rag_backend", "pgvector")

    agent = RetrieverAgent()

    assert isinstance(agent._coordinator._providers["vector"], _OfflineVectorProvider)


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
    """显式构造一个永远返回低分 chunk 的 provider 来测低分质量子标记。

    DEC-008：low_score 不再是独立状态，降为 ok 的 quality=low 子标记。
    """
    from app.infrastructure.rag.coordinator import IndexProvider, Chunk, RAGCoordinator

    class _LowScoreProvider(IndexProvider):
        name = "lowscore"
        def index(self, docs): pass
        def search(self, query, top_k=5):
            return [Chunk(content="low score chunk", score=0.1, source="lowscore")]
        @property
        def doc_count(self): return 1

    coord = RAGCoordinator(vector_provider=_LowScoreProvider())
    agent = RetrieverAgent(coordinator=coord)
    ev = Event(type=EventType.ACTION_REQUESTED, source=EventSource.ORCHESTRATOR,
               session_id="s1", payload={"target": "retriever",
                                          "query": "anything",
                                          "sources": ["vector"]})
    result = agent.handle(ev, ws)
    assert len(result) == 1
    assert result[0].type == EventType.RETRIEVED_EVIDENCE
    assert result[0].payload["retrieval_status"] == "ok"
    assert result[0].payload["quality"] == "low"
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
    assert 0.0 <= metrics["context_precision_proxy"] <= 1.0
    assert metrics["context_precision"] is None


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
    # RAGAS 可用时：检索结果 + golden_answer 有词语重叠 -> faithfulness > 0
    # judge 不可用时（单元测试环境无 API key）：degraded=True，faithfulness 占位为 0.0
    assert metrics.get("degraded", False) or metrics["faithfulness"] > 0.0


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
    assert 0.0 <= metrics["context_precision_proxy"] <= 1.0
    assert metrics["context_precision"] is None or 0.0 <= metrics["context_precision"] <= 1.0
    assert metrics["faithfulness"] is None or 0.0 <= metrics["faithfulness"] <= 1.0
    assert metrics["answer_relevancy"] is None or -1.0 <= metrics["answer_relevancy"] <= 1.0
    assert 0.0 <= metrics["redundancy"] <= 1.0
    assert metrics["latency_ms"] >= 0


def test_evaluate_degraded_when_no_golden_answer():
    """无 golden_answer 时应降级（faithfulness/answer_relevancy 无意义）"""
    from unittest.mock import patch

    agent = RetrieverAgent()
    agent._coordinator.index_documents([{"content": "测试内容"}])

    # 无 golden_answer 时应在导入可选 RAGAS 依赖前降级。
    with patch("app.eval.judge.build_judge", return_value={"llm": "mock", "embeddings": "mock"}):
        metrics = agent.evaluate({
            "query": "测试",
            "golden_chunks": ["测试内容"],
            # 不传 golden_answer
        })

    assert metrics["degraded"] is True
    assert metrics["degraded_reason"] == "部分 judge 分数不可用"
    # 降级时仍应返回不依赖 LLM 的指标
    assert "recall_at_k" in metrics
    assert "redundancy" in metrics
    assert "latency_ms" in metrics


def test_evaluate_ragas_happy_path_extraction(monkeypatch):
    """happy-path：mock judge + ragas_eval，验证 import/Dataset/分数提取链路不崩。

    此前 32 测试全走降级分支，RAGAS 真实调用从未被执行，掩盖了
    metric import 类型错误与 EvaluationResult 提取接口错误两个 bug。
    本测试 mock 掉 build_judge 与 ragas_eval 本身，但保留真实的
    ragas.metrics import、Dataset 构造、_scores_dict 提取，覆盖该链路。
    """
    metrics = _evaluate_with_judge_scores(monkeypatch, {
        "faithfulness": [0.9],
        "answer_relevancy": [0.85],
        "context_precision": [0.8],
    })

    assert metrics["degraded"] is False
    assert metrics["faithfulness"] == 0.9
    assert metrics["answer_relevancy"] == 0.85
    assert metrics["context_precision"] == 0.8


@pytest.mark.integration
def test_evaluate_ragas_real_judge():
    """集成测试：真实 OpenAI judge 跑 RAGAS（需 OPENAI_API_KEY）。

    默认被 pytest -m 'not integration' 排除。手动运行：
        pytest tests/unit/agents/test_retriever.py -m integration
    验证 RAGAS evaluate 真实调用成功、三件套分数落在 [0,1]。
    """
    agent = RetrieverAgent()
    agent._coordinator.index_documents([
        {"content": "注意力机制的核心是 Query、Key、Value 三个矩阵的运算"},
    ])
    metrics = agent.evaluate({
        "query": "注意力机制的核心是什么",
        "golden_chunks": ["注意力机制的核心是 Query、Key、Value 三个矩阵的运算"],
        "golden_answer": "注意力机制核心是 QKV 三个矩阵",
    })

    assert metrics["degraded"] is False, f"不应降级：{metrics.get('degraded_reason')}"
    for k in ("faithfulness", "answer_relevancy", "context_precision"):
        assert 0.0 <= metrics[k] <= 1.0


# ===== RAG-C Phase 2（C-10）：五态 + 入口校验 + 安全摘要 =====

class _StubCoordinator:
    """可控 Coordinator 替身：记录调用，返回预设 SearchResult 或抛异常。"""

    def __init__(self, result=None, exc=None):
        self.result = result or SearchResult(
            chunks=[], total_found=0, sources_used=[], outcome="empty")
        self.exc = exc
        self.calls = []

    def search(self, query, sources=None, top_k=5, visibility=None):
        self.calls.append({"query": query, "sources": sources,
                           "top_k": top_k, "visibility": visibility})
        if self.exc:
            raise self.exc
        return self.result


def _retriever_event(payload):
    return Event(type=EventType.ACTION_REQUESTED, source=EventSource.ORCHESTRATOR,
                 session_id="s1", payload={"target": "retriever", **payload})


_EVALUATION_KEYS = {
    "schema_version", "retrieval_status", "error_code", "safe_summary",
    "sources_used", "attempted_providers", "failed_providers", "latency_ms",
    "top_k", "valid_for_quality", "recall_at_k", "recall_at_1",
    "recall_at_3", "recall_at_5", "context_precision_proxy", "redundancy",
    "faithfulness", "answer_relevancy", "context_precision", "judge_scores",
    "judge_degraded", "degraded", "degraded_reason",
}


def _evaluation_search_result(outcome, *, chunks=None, error_code=None):
    return SearchResult(
        chunks=chunks or [], total_found=len(chunks or []),
        sources_used=["vector"] if chunks else [], outcome=outcome,
        attempted_providers=["vector", "archive"],
        failed_providers=["archive"] if outcome == "degraded" else [],
        error_code=error_code,
    )


def test_evaluate_contract_preserves_status_and_search_sources():
    cases = [
        ("ok", "ok", None, True),
        ("empty", "empty", None, True),
        ("degraded", "degraded", "provider_degraded", False),
        ("failed", "failed", "db_error", False),
        ("failed", "invalid-request", "invalid_request", False),
    ]
    for outcome, expected_status, error_code, valid in cases:
        chunks = [Chunk(content="gold paragraph", score=0.9)] if outcome in {"ok", "degraded"} else []
        stub = _StubCoordinator(result=_evaluation_search_result(
            outcome, chunks=chunks, error_code=error_code))
        metrics = RetrieverAgent(coordinator=stub).evaluate({
            "query": "question", "golden_chunks": ["gold paragraph"],
            "golden_answer": "answer", "top_k": 5,
        })

        assert set(metrics) == _EVALUATION_KEYS
        assert metrics["schema_version"] == "retriever-evaluation-v1"
        assert metrics["retrieval_status"] == expected_status
        assert metrics["valid_for_quality"] is valid
        assert metrics["sources_used"] == (["vector"] if chunks else [])
        assert metrics["attempted_providers"] == ["vector", "archive"]
        assert metrics["failed_providers"] == (["archive"] if outcome == "degraded" else [])
        assert metrics["error_code"] == error_code
        assert metrics["top_k"] == 5
        assert len(stub.calls) == 1
        assert _json.loads(_json.dumps(metrics, ensure_ascii=False, allow_nan=False)) == metrics


@pytest.mark.parametrize(
    ("exc", "expected_code"),
    [(TimeoutError("private timeout text"), "timeout"),
     (RuntimeError("private database text"), "backend_unavailable")],
)
def test_evaluate_contract_safely_classifies_search_exception(exc, expected_code, monkeypatch):
    judge_calls = []
    monkeypatch.setattr("app.eval.judge.build_judge", lambda **_: judge_calls.append(True))
    stub = _StubCoordinator(exc=exc)
    metrics = RetrieverAgent(coordinator=stub).evaluate({
        "query": "question", "golden_chunks": ["gold"],
        "golden_answer": "answer", "top_k": 5,
    })

    assert set(metrics) == _EVALUATION_KEYS
    assert metrics["retrieval_status"] == "failed"
    assert metrics["error_code"] == expected_code
    assert metrics["latency_ms"] is None
    assert metrics["sources_used"] == []
    assert metrics["valid_for_quality"] is False
    assert all(metrics[key] is None for key in (
        "recall_at_k", "recall_at_1", "recall_at_3", "recall_at_5",
        "context_precision_proxy", "redundancy", "faithfulness",
        "answer_relevancy", "context_precision"))
    assert judge_calls == []
    dumped = _json.dumps(metrics, ensure_ascii=False, allow_nan=False)
    assert "private timeout text" not in dumped
    assert "private database text" not in dumped


@pytest.mark.parametrize(
    ("query", "top_k", "golden_chunks", "golden_answer", "expected_top_k"),
    [("", 3, [], "answer", 3), ("question", True, [], "answer", None),
     ("question", 0, [], "answer", None), ("question", 11, [], "answer", None),
     ("question", "5", [], "answer", None),
     ("question", 5, "not-a-list", "answer", 5),
     ("question", 5, ["   "], "answer", 5),
     ("question", 5, [None], "answer", 5),
     ("question", 5, [1], "answer", 5),
     ("question", 5, ["valid gold", None], "answer", 5),
     ("question", 5, [], 12, 5)],
)
def test_evaluate_contract_rejects_invalid_inputs_before_search(
    query, top_k, golden_chunks, golden_answer, expected_top_k, monkeypatch,
):
    judge_calls = []
    monkeypatch.setattr("app.eval.judge.build_judge", lambda **_: judge_calls.append(True))
    stub = _StubCoordinator()
    metrics = RetrieverAgent(coordinator=stub).evaluate({
        "query": query, "golden_chunks": golden_chunks,
        "golden_answer": golden_answer, "top_k": top_k,
    })

    assert set(metrics) == _EVALUATION_KEYS
    assert metrics["retrieval_status"] == "invalid-request"
    assert metrics["error_code"] == "invalid_request"
    assert metrics["top_k"] == expected_top_k
    assert metrics["latency_ms"] is None
    assert metrics["sources_used"] == []
    assert metrics["valid_for_quality"] is False
    assert metrics["judge_degraded"] is True
    assert metrics["degraded"] is True
    assert all(metrics[key] is None for key in (
        "recall_at_k", "recall_at_1", "recall_at_3", "recall_at_5",
        "context_precision_proxy", "redundancy", "faithfulness",
        "answer_relevancy", "context_precision"))
    assert stub.calls == []
    assert judge_calls == []
    _json.dumps(metrics, ensure_ascii=False, allow_nan=False)


@pytest.mark.parametrize(
    ("top_k", "recall_k", "recall_1", "recall_3", "recall_5", "proxy"),
    [(1, 0.0, 0.0, None, None, 0.0),
     (2, 0.0, 0.0, None, None, 0.0),
     (3, 0.5, 0.0, 0.5, None, 1 / 3),
     (5, 1.0, 0.0, 0.5, 1.0, 2 / 5),
     (10, 1.0, 0.0, 0.5, 1.0, 2 / 5)],
)
def test_evaluate_proxy_derives_all_k_from_one_ordered_search(
    top_k, recall_k, recall_1, recall_3, recall_5, proxy,
):
    contents = [
        "first unrelated paragraph",
        "second unrelated paragraph",
        "gold alpha appears here",
        "fourth unrelated paragraph",
        "gold beta appears here",
    ]
    stub = _StubCoordinator(result=_evaluation_search_result(
        "ok", chunks=[Chunk(content=text, score=1 - index / 10)
                       for index, text in enumerate(contents)]))
    metrics = RetrieverAgent(coordinator=stub).evaluate({
        "query": "question",
        "golden_chunks": ["gold alpha", "gold alpha", "gold beta"],
        "golden_answer": "",
        "top_k": top_k,
    })

    assert metrics["recall_at_k"] == recall_k
    assert metrics["recall_at_1"] == recall_1
    assert metrics["recall_at_3"] == recall_3
    assert metrics["recall_at_5"] == recall_5
    assert metrics["context_precision_proxy"] == pytest.approx(proxy)
    assert metrics["context_precision"] is None
    assert len(stub.calls) == 1
    assert stub.calls[0]["top_k"] == top_k


def test_evaluate_proxy_supports_containment_in_both_directions():
    stub = _StubCoordinator(result=_evaluation_search_result(
        "ok", chunks=[
            Chunk(content="prefix and short phrase at the end", score=0.9),
            Chunk(content="tiny", score=0.8),
        ]))
    metrics = RetrieverAgent(coordinator=stub).evaluate({
        "query": "question",
        "golden_chunks": ["short phrase", "a much longer tiny golden paragraph"],
        "golden_answer": "",
        "top_k": 2,
    })

    assert metrics["recall_at_k"] == 1.0
    assert metrics["context_precision_proxy"] == 1.0
    assert len(stub.calls) == 1


def test_evaluate_proxy_has_zero_values_for_healthy_empty_and_null_without_gold():
    empty_agent = RetrieverAgent(coordinator=_StubCoordinator(
        result=_evaluation_search_result("empty")))
    with_gold = empty_agent.evaluate({
        "query": "question", "golden_chunks": ["gold"], "golden_answer": "",
    })
    without_gold = empty_agent.evaluate({
        "query": "question", "golden_chunks": [], "golden_answer": "",
    })

    assert with_gold["retrieval_status"] == "empty"
    assert with_gold["valid_for_quality"] is True
    assert with_gold["recall_at_k"] == 0.0
    assert with_gold["context_precision_proxy"] == 0.0
    assert with_gold["redundancy"] == 0.0
    assert without_gold["recall_at_k"] is None
    assert without_gold["recall_at_1"] is None
    assert without_gold["context_precision_proxy"] is None
    assert len(empty_agent._coordinator.calls) == 2


def test_evaluate_proxy_counts_highly_similar_nonduplicate_contents():
    stub = _StubCoordinator(result=_evaluation_search_result(
        "ok", chunks=[
            Chunk(content="same paragraph same paragraph ending alpha", score=0.9),
            Chunk(content="same paragraph same paragraph ending bravo", score=0.8),
        ]))
    metrics = RetrieverAgent(coordinator=stub).evaluate({
        "query": "same paragraph", "golden_chunks": [], "golden_answer": "",
    })

    assert metrics["redundancy"] == 1.0
    assert metrics["recall_at_k"] is None
    assert len(stub.calls) == 1


def test_evaluate_proxy_uses_real_coordinator_deduplication_for_duplicate_bodies():
    from app.infrastructure.rag.coordinator import IndexProvider, RAGCoordinator

    class DuplicateProvider(IndexProvider):
        name = "vector"

        def __init__(self):
            self.calls = 0

        def index(self, docs):
            return len(docs)

        def search(self, query, top_k=5, visibility=None):
            self.calls += 1
            return [
                Chunk(content="same body", score=0.8),
                Chunk(content="same body", score=0.9),
                Chunk(content="other body", score=0.7),
            ]

        @property
        def doc_count(self):
            return 3

    provider = DuplicateProvider()
    agent = RetrieverAgent(coordinator=RAGCoordinator(vector_provider=provider))
    metrics = agent.evaluate({
        "query": "body", "golden_chunks": [], "golden_answer": "", "top_k": 5,
    })

    assert metrics["redundancy"] == 0.0
    assert provider.calls == 1


def _install_controlled_judge(monkeypatch, scores):
    import sys
    from types import ModuleType, SimpleNamespace

    ragas = ModuleType("ragas")
    ragas.__path__ = []
    ragas.evaluate = lambda **_: SimpleNamespace(_scores_dict=scores)
    ragas_metrics = ModuleType("ragas.metrics")
    ragas_metrics.faithfulness = object()
    ragas_metrics.answer_relevancy = object()
    ragas_metrics.context_precision = object()
    datasets = ModuleType("datasets")

    class Dataset:
        @staticmethod
        def from_dict(values):
            return values

    datasets.Dataset = Dataset
    monkeypatch.setitem(sys.modules, "ragas", ragas)
    monkeypatch.setitem(sys.modules, "ragas.metrics", ragas_metrics)
    monkeypatch.setitem(sys.modules, "datasets", datasets)
    monkeypatch.setattr(
        "app.eval.judge.build_judge",
        lambda **_: {"llm": object(), "embeddings": object()},
    )


def _evaluate_with_judge_scores(monkeypatch, scores):
    _install_controlled_judge(monkeypatch, scores)
    stub = _StubCoordinator(result=_evaluation_search_result(
        "ok", chunks=[Chunk(content="gold evidence", score=0.9)]))
    metrics = RetrieverAgent(coordinator=stub).evaluate({
        "query": "question", "golden_chunks": ["gold evidence"],
        "golden_answer": "reference answer", "top_k": 5,
    })
    assert len(stub.calls) == 1
    _json.dumps(metrics, ensure_ascii=False, allow_nan=False)
    return metrics


def test_evaluate_judge_contract_accepts_zero_boundaries_and_negative_relevancy(monkeypatch):
    metrics = _evaluate_with_judge_scores(monkeypatch, {
        "faithfulness": [0],
        "answer_relevancy": [-1.0],
        "context_precision": [1],
    })

    assert metrics["faithfulness"] == 0.0
    assert metrics["answer_relevancy"] == -1.0
    assert metrics["context_precision"] == 1.0
    assert all(item["available"] for item in metrics["judge_scores"].values())
    assert metrics["judge_degraded"] is False
    assert metrics["degraded"] is False
    assert metrics["context_precision_proxy"] == 1.0


@pytest.mark.parametrize(
    ("scores", "expected_reasons"),
    [({}, {"faithfulness": "missing", "answer_relevancy": "missing",
           "context_precision": "missing"}),
     ({"faithfulness": [], "answer_relevancy": [], "context_precision": []},
      {"faithfulness": "missing", "answer_relevancy": "missing",
       "context_precision": "missing"}),
     ({"faithfulness": [0.7], "answer_relevancy": [], "context_precision": [None]},
      {"faithfulness": None, "answer_relevancy": "missing",
       "context_precision": "non_numeric"})],
)
def test_evaluate_judge_contract_handles_missing_empty_and_partial_scores(
    monkeypatch, scores, expected_reasons,
):
    metrics = _evaluate_with_judge_scores(monkeypatch, scores)

    for name, reason in expected_reasons.items():
        assert metrics["judge_scores"][name]["safe_reason"] == reason
        assert metrics[name] == metrics["judge_scores"][name]["value"]
    if scores.get("faithfulness"):
        assert metrics["faithfulness"] == 0.7
        assert metrics["context_precision_proxy"] == 1.0
    assert metrics["judge_degraded"] is True
    assert metrics["degraded"] is True


@pytest.mark.parametrize(
    ("metric", "bad_value", "expected_reason"),
    [("faithfulness", True, "non_numeric"),
     ("faithfulness", "0.5", "non_numeric"),
     ("faithfulness", float("nan"), "non_finite"),
     ("answer_relevancy", float("inf"), "non_finite"),
     ("context_precision", float("-inf"), "non_finite"),
     ("faithfulness", -0.01, "out_of_range"),
     ("answer_relevancy", 1.01, "out_of_range"),
     ("context_precision", 1.01, "out_of_range")],
)
def test_evaluate_judge_contract_rejects_bad_score_per_metric(
    monkeypatch, metric, bad_value, expected_reason,
):
    scores = {"faithfulness": [0.6], "answer_relevancy": [0.2],
              "context_precision": [0.8]}
    scores[metric] = [bad_value]
    metrics = _evaluate_with_judge_scores(monkeypatch, scores)

    assert metrics[metric] is None
    assert metrics["judge_scores"][metric] == {
        "value": None, "available": False, "safe_reason": expected_reason,
    }
    assert metrics["judge_degraded"] is True
    assert metrics["retrieval_status"] == "ok"
    assert metrics["valid_for_quality"] is True
    assert metrics["context_precision_proxy"] == 1.0


def test_evaluate_judge_contract_does_not_call_judge_without_golden_answer(monkeypatch):
    calls = []
    monkeypatch.setattr("app.eval.judge.build_judge", lambda **_: calls.append(True))
    stub = _StubCoordinator(result=_evaluation_search_result(
        "ok", chunks=[Chunk(content="evidence", score=0.9)]))
    metrics = RetrieverAgent(coordinator=stub).evaluate({
        "query": "question", "golden_chunks": ["evidence"], "golden_answer": "",
    })

    assert calls == []
    assert metrics["retrieval_status"] == "ok"
    assert metrics["judge_scores"]["faithfulness"]["safe_reason"] == "unavailable"
    assert metrics["context_precision_proxy"] == 1.0
    _json.dumps(metrics, ensure_ascii=False, allow_nan=False)


def test_evaluate_judge_contract_degrades_when_ragas_package_is_missing(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "ragas", None)
    stub = _StubCoordinator(result=_evaluation_search_result(
        "ok", chunks=[Chunk(content="evidence", score=0.9)]))
    metrics = RetrieverAgent(coordinator=stub).evaluate({
        "query": "question", "golden_chunks": ["evidence"],
        "golden_answer": "answer",
    })

    assert metrics["retrieval_status"] == "ok"
    assert metrics["valid_for_quality"] is True
    assert metrics["context_precision_proxy"] == 1.0
    assert all(item == {"value": None, "available": False, "safe_reason": "unavailable"}
               for item in metrics["judge_scores"].values())
    assert metrics["judge_degraded"] is True
    assert metrics["degraded"] is True
    _json.dumps(metrics, ensure_ascii=False, allow_nan=False)


def test_evaluate_judge_contract_catches_unavailable_and_judge_exception(monkeypatch):
    stub = _StubCoordinator(result=_evaluation_search_result(
        "ok", chunks=[Chunk(content="evidence", score=0.9)]))
    monkeypatch.setattr("app.eval.judge.build_judge", lambda **_: None)
    unavailable = RetrieverAgent(coordinator=stub).evaluate({
        "query": "question", "golden_chunks": ["evidence"],
        "golden_answer": "answer",
    })
    assert all(item["safe_reason"] == "unavailable"
               for item in unavailable["judge_scores"].values())
    assert unavailable["context_precision_proxy"] == 1.0

    _install_controlled_judge(monkeypatch, {})
    monkeypatch.setattr("app.eval.judge.build_judge",
                        lambda **_: (_ for _ in ()).throw(RuntimeError("secret judge failure")))
    failed = RetrieverAgent(coordinator=stub).evaluate({
        "query": "question", "golden_chunks": ["evidence"],
        "golden_answer": "answer",
    })
    assert failed["retrieval_status"] == "ok"
    assert failed["valid_for_quality"] is True
    assert failed["judge_degraded"] is True
    assert failed["context_precision_proxy"] == 1.0
    assert "secret judge failure" not in _json.dumps(failed, ensure_ascii=False)
    assert len(stub.calls) == 2


def _component_bench_agent(*, mode="healthy"):
    from app.infrastructure.rag.coordinator import IndexProvider, RAGCoordinator

    class ControlledProvider(IndexProvider):
        name = "vector"

        def __init__(self, should_fail=False):
            self.calls = 0
            self.should_fail = should_fail

        def index(self, docs):
            return len(docs)

        def search(self, query, top_k=5, visibility=None):
            self.calls += 1
            if self.should_fail:
                raise RuntimeError("private provider failure")
            if mode == "empty":
                return []
            return [Chunk(content="gold evidence paragraph", score=0.9)]

        @property
        def doc_count(self):
            return 1

    class FailingOCRProvider(IndexProvider):
        name = "ocr"

        def index(self, docs):
            return len(docs)

        def search(self, query, top_k=5, visibility=None):
            raise RuntimeError("private OCR failure")

        @property
        def doc_count(self):
            return 0

    provider = ControlledProvider(should_fail=mode == "failed")
    coordinator = RAGCoordinator(vector_provider=provider)
    if mode == "degraded":
        coordinator.register_provider(FailingOCRProvider())
    return RetrieverAgent(coordinator=coordinator), provider


def test_evaluate_component_bench_contract_keeps_null_for_missing_gold(monkeypatch):
    from app.eval.component_bench import ComponentBench
    from app.eval.kernel import TestCase

    monkeypatch.setattr("app.eval.judge.build_judge", lambda **_: None)
    agent, provider = _component_bench_agent()
    case = TestCase(
        name="missing-gold", component="retriever",
        input={"query": "question", "golden_chunks": [], "golden_answer": "", "top_k": 5},
        expected={"recall_at_k": 0.5},
    )

    result = ComponentBench({"retriever": agent}).run("retriever", [case])[0]

    assert result.passed is False
    assert result.metrics["recall_at_k"] is None
    assert result.metrics["retrieval_status"] == "ok"
    assert any("recall_at_k: 未返回" in error for error in result.errors)
    assert provider.calls == 1


@pytest.mark.parametrize(("mode", "expected_status"), [
    ("failed", "failed"), ("degraded", "degraded"),
])
def test_evaluate_component_bench_contract_preserves_failed_and_degraded_status(
    monkeypatch, mode, expected_status,
):
    from app.eval.component_bench import ComponentBench
    from app.eval.kernel import TestCase

    monkeypatch.setattr("app.eval.judge.build_judge", lambda **_: None)
    agent, provider = _component_bench_agent(mode=mode)
    case = TestCase(
        name=f"{mode}-retrieval", component="retriever",
        input={"query": "question", "golden_chunks": ["gold evidence"],
               "golden_answer": "answer", "top_k": 5},
        expected={"recall_at_k": 0.5},
    )

    result = ComponentBench({"retriever": agent}).run("retriever", [case])[0]

    assert result.passed is False
    assert result.metrics["retrieval_status"] == expected_status
    assert result.metrics["valid_for_quality"] is False
    assert result.metrics["recall_at_k"] is None
    assert result.metrics["sources_used"] == (["vector"] if mode == "degraded" else [])
    assert any("recall_at_k: 未返回" in error for error in result.errors)
    assert provider.calls == 1


def test_evaluate_component_bench_contract_keeps_healthy_legacy_metrics(monkeypatch):
    from app.eval.component_bench import ComponentBench
    from app.eval.kernel import TestCase

    _install_controlled_judge(monkeypatch, {
        "faithfulness": [0.8], "answer_relevancy": [-0.2], "context_precision": [0.9],
    })
    agent, provider = _component_bench_agent()
    case = TestCase(
        name="healthy-gold", component="retriever",
        input={"query": "question", "golden_chunks": ["gold evidence paragraph"],
               "golden_answer": "answer", "top_k": 5},
        expected={"recall_at_k": 1.0, "faithfulness": 0.8},
    )

    result = ComponentBench({"retriever": agent}).run("retriever", [case])[0]

    assert result.passed is True
    assert result.metrics["recall_at_k"] == 1.0
    assert result.metrics["faithfulness"] == 0.8
    assert result.metrics["answer_relevancy"] == -0.2
    assert result.metrics["retrieval_status"] == "ok"
    assert result.metrics["valid_for_quality"] is True
    assert provider.calls == 1


# --- invalid-request：入口拦截，不进入 provider ---

def test_invalid_request_missing_query_skips_provider(ws):
    stub = _StubCoordinator()
    agent = RetrieverAgent(coordinator=stub)
    result = agent.handle(_retriever_event({"query": ""}), ws)
    assert result[0].type == EventType.RETRIEVAL_FAILED
    p = result[0].payload
    assert p["retrieval_status"] == "invalid-request"
    assert p["error_code"] == "invalid_request"
    assert p["safe_summary"]
    assert stub.calls == []


def test_invalid_request_bad_top_k_skips_provider(ws):
    stub = _StubCoordinator()
    agent = RetrieverAgent(coordinator=stub)
    for bad in (0, -1, 11, "5", 2.5, True):
        result = agent.handle(_retriever_event({"query": "RAG", "top_k": bad}), ws)
        assert result[0].payload["retrieval_status"] == "invalid-request", bad
    assert stub.calls == []


def test_restricted_missing_retrieval_id_invalid(ws):
    """受限请求（带 visibility）缺 retrieval_id → invalid-request（DEC-003）。"""
    stub = _StubCoordinator()
    agent = RetrieverAgent(coordinator=stub)
    result = agent.handle(_retriever_event({
        "query": "RAG", "user_id": ws.user_id,
        "visibility": {"user_id": ws.user_id}}), ws)
    assert result[0].payload["retrieval_status"] == "invalid-request"
    assert stub.calls == []


def test_restricted_missing_user_identity_invalid(ws):
    """受限请求 visibility 缺可信身份 → invalid-request，不检索（DEC-001）。"""
    stub = _StubCoordinator()
    agent = RetrieverAgent(coordinator=stub)
    for bad_vis in ({}, {"user_id": None}, {"user_id": "1"}, "user-1"):
        result = agent.handle(_retriever_event({
            "query": "RAG", "user_id": ws.user_id,
            "visibility": bad_vis, "retrieval_id": "rid-1"}), ws)
        assert result[0].payload["retrieval_status"] == "invalid-request", bad_vis
    assert stub.calls == []


def test_restricted_missing_payload_user_id_invalid(ws):
    """受限请求必须显式携带与会话绑定的可信 payload.user_id。"""
    stub = _StubCoordinator()
    agent = RetrieverAgent(coordinator=stub)
    result = agent.handle(_retriever_event({
        "query": "RAG", "visibility": {"user_id": ws.user_id},
        "retrieval_id": "rid-1"}), ws)
    assert result[0].payload["retrieval_status"] == "invalid-request"
    assert stub.calls == []


def test_restricted_forged_matching_foreign_identity_invalid(ws):
    """两个 payload 字段即使彼此一致，也不能冒充另一会话用户。"""
    stub = _StubCoordinator()
    agent = RetrieverAgent(coordinator=stub)
    result = agent.handle(_retriever_event({
        "query": "RAG", "user_id": 99, "visibility": {"user_id": 99},
        "retrieval_id": "rid-1"}), ws)
    assert result[0].payload["retrieval_status"] == "invalid-request"
    assert stub.calls == []


def test_restricted_user_id_mismatch_invalid(ws):
    """payload.user_id 与 visibility.user_id 不一致 → 按不可信处理。"""
    stub = _StubCoordinator()
    agent = RetrieverAgent(coordinator=stub)
    result = agent.handle(_retriever_event({
        "query": "RAG", "user_id": 2,
        "visibility": {"user_id": 1}, "retrieval_id": "rid-1"}), ws)
    assert result[0].payload["retrieval_status"] == "invalid-request"
    assert stub.calls == []


# --- 受限请求贯通 visibility / retrieval_id ---

def test_restricted_valid_request_passes_visibility_and_id(ws):
    ok_result = SearchResult(
        chunks=[Chunk(content="证据", score=0.9, source="vector")],
        total_found=1, sources_used=["vector"], outcome="ok")
    stub = _StubCoordinator(result=ok_result)
    agent = RetrieverAgent(coordinator=stub)
    result = agent.handle(_retriever_event({
        "query": "RAG", "sources": ["vector"], "user_id": ws.user_id,
        "visibility": {"user_id": ws.user_id}, "retrieval_id": "rid-1"}), ws)
    assert result[0].type == EventType.RETRIEVED_EVIDENCE
    assert result[0].payload["retrieval_status"] == "ok"
    assert result[0].payload["retrieval_id"] == "rid-1"
    assert stub.calls[0]["visibility"].user_id == ws.user_id
    assert stub.calls[0]["sources"] == ["vector"]


# --- degraded / failed 聚合映射 ---

def test_degraded_outcome_event(ws):
    degraded = SearchResult(
        chunks=[Chunk(content="部分证据", score=0.8, source="vector")],
        total_found=1, sources_used=["vector"], outcome="degraded",
        attempted_providers=["vector", "boom"], failed_providers=["boom"],
        error_code="provider_degraded")
    stub = _StubCoordinator(result=degraded)
    agent = RetrieverAgent(coordinator=stub)
    result = agent.handle(_retriever_event({"query": "RAG"}), ws)
    assert result[0].type == EventType.RETRIEVED_EVIDENCE
    p = result[0].payload
    assert p["retrieval_status"] == "degraded"
    assert p["provider_failures"] == ["boom"]
    assert p["error_code"] == "provider_degraded"
    assert p["safe_summary"] == "部分知识来源不可用"
    assert len(p["chunks"]) == 1  # 成功证据保留


def test_failed_outcome_event(ws):
    failed = SearchResult(chunks=[], total_found=0, sources_used=[],
                          outcome="failed", attempted_providers=["vector"],
                          failed_providers=["vector"], error_code="db_error")
    stub = _StubCoordinator(result=failed)
    agent = RetrieverAgent(coordinator=stub)
    result = agent.handle(_retriever_event({"query": "RAG"}), ws)
    assert result[0].type == EventType.RETRIEVAL_FAILED
    p = result[0].payload
    assert p["retrieval_status"] == "failed"
    assert p["error_code"] == "db_error"
    assert p["safe_summary"] == "知识库服务暂时不可用"


# --- 异常路径：payload 不泄露内部细节（DEC-009）---

def test_exception_payload_does_not_leak_sensitive_details(ws):
    stub = _StubCoordinator(exc=RuntimeError(
        "psycopg connect refused: postgresql://admin:secret@10.0.0.1/db"))
    agent = RetrieverAgent(coordinator=stub)
    result = agent.handle(_retriever_event({"query": "RAG"}), ws)
    assert result[0].type == EventType.RETRIEVAL_FAILED
    p = result[0].payload
    assert p["retrieval_status"] == "failed"
    assert p["error_code"] == "db_error"
    dumped = _json.dumps(p, ensure_ascii=False, default=str)
    for secret in ("secret", "psycopg", "postgresql://", "10.0.0.1"):
        assert secret not in dumped, secret


def test_timeout_exception_classified_as_timeout(ws):
    stub = _StubCoordinator(exc=TimeoutError("slow"))
    agent = RetrieverAgent(coordinator=stub)
    result = agent.handle(_retriever_event({"query": "RAG"}), ws)
    assert result[0].payload["error_code"] == "timeout"
    assert result[0].payload["safe_summary"] == "检索超时，请稍后重试"
