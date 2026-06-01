"""Plan A 集成测试：Retriever + RAG 基础设施在协作环中端到端工作。

覆盖：
- spec §9 场景 1：OCR 内容可在协作环中被检索
- spec §9 场景 2：代码索引内容可被检索
- retrieval_status 三态在真实 EventBus 下正确产出（ok / empty）
- emit 事件的 source 满足 §3.2 白名单
- 多源聚合（向量 + OCR + 代码）
- evaluate() 输出合法指标
"""

from app.agents.retriever import RetrieverAgent
from app.harness.enums import EventType, EventSource
from app.harness.events import Event
from app.harness.eventbus import EventBus
from app.harness.workspace_state import WorkspaceState
from app.orchestration.collab_loop import run_collab_loop
from app.infrastructure.rag.ocr import OCRProvider
from app.infrastructure.rag.code_index import CodeIndexProvider


# ── 测试用内存 EventStore ───────────────────────────────────────────────
# EventBus.publish 会调 store.append；EventBus.replay 会调 store.replay。
# 这里用纯内存 list 替代 sqlite EventStore，避免 IO 开销与文件清理。
class _InMemoryStore:
    """符合 EventBus 协议的最小事件存储：仅 append + replay，按 session 过滤。"""

    def __init__(self):
        self._events: list[Event] = []

    def append(self, event: Event) -> None:
        self._events.append(event)

    def replay(self, session_id: str) -> list[Event]:
        return [e for e in self._events if e.session_id == session_id]


# ── spec §9 场景 1：OCR 内容可检索 ──

def test_ocr_content_retrievable_in_collab_loop():
    """OCR 索引的图片文本应可被 RetrieverAgent 检索到。"""
    ws = WorkspaceState(session_id="s1", user_id="u1")
    bus = EventBus(store=_InMemoryStore())

    retriever = RetrieverAgent()
    ocr = OCRProvider()
    ocr.index([{"content": "Transformer 架构由 Vaswani 等人在 2017 年提出",
                "metadata": {"file": "slide1.png"}},
               {"content": "注意力机制计算公式为 Attention(Q,K,V)",
                "metadata": {"file": "slide2.png"}}])
    retriever._coordinator.register_provider(ocr)

    bus.subscribe(retriever, retriever.subscriptions)

    seed = Event(type=EventType.ACTION_REQUESTED, source=EventSource.ORCHESTRATOR,
                 session_id="s1", payload={
                     "target": "retriever",
                     "query": "注意力机制",
                     "sources": ["ocr"],
                 })

    run_collab_loop(bus, ws, [seed], max_turns=10)

    events = bus.replay("s1")
    retrieved = [e for e in events if e.type == EventType.RETRIEVED_EVIDENCE]
    assert len(retrieved) >= 1
    # 检索结果应包含注意力机制相关内容
    chunks = retrieved[0].payload.get("chunks", [])
    assert any("注意力" in c["content"] for c in chunks)


# ── spec §9 场景 2：代码索引内容可检索 ──

def test_code_index_content_retrievable():
    """代码仓库索引的符号应可被检索到。"""
    retriever = RetrieverAgent()
    code = CodeIndexProvider()
    code.index_file("/repo/model.py", '''
"""Deep learning model definitions."""

class Transformer:
    """A Transformer model with multi-head attention."""

    def __init__(self, num_heads: int = 8):
        self.num_heads = num_heads

    def forward(self, x):
        """Forward pass through the transformer."""
        return x

def attention(query, key, value):
    """Scaled dot-product attention."""
    import math
    d_k = query.shape[-1]
    scores = (query @ key.transpose(-2, -1)) / math.sqrt(d_k)
    return scores
''')
    retriever._coordinator.register_provider(code)

    # 按函数名检索
    results = retriever._coordinator.search("attention", sources=["code"])
    assert results.total_found >= 1
    assert any("attention" in c.content for c in results.chunks)

    # 按类名检索
    results2 = retriever._coordinator.search("Transformer", sources=["code"])
    assert results2.total_found >= 1
    assert any("Transformer" in c.content for c in results2.chunks)


# ── retrieval_status 各状态集成验证 ──

def test_retrieval_status_ok_in_collab_loop():
    """有匹配内容时 retrieval_status=ok"""
    ws = WorkspaceState(session_id="s2", user_id="u1")
    bus = EventBus(store=_InMemoryStore())

    retriever = RetrieverAgent()
    retriever._coordinator.index_documents([
        {"content": "RAG 是检索增强生成技术"},
    ])
    bus.subscribe(retriever, retriever.subscriptions)

    seed = Event(type=EventType.ACTION_REQUESTED, source=EventSource.ORCHESTRATOR,
                 session_id="s2", payload={
                     "target": "retriever",
                     "query": "RAG",
                 })

    run_collab_loop(bus, ws, [seed], max_turns=10)
    events = bus.replay("s2")
    evidence = [e for e in events if e.type == EventType.RETRIEVED_EVIDENCE]
    assert len(evidence) == 1
    assert evidence[0].payload["retrieval_status"] == "ok"


def test_retrieval_status_empty_in_collab_loop():
    """无匹配内容时 retrieval_status=empty"""
    ws = WorkspaceState(session_id="s3", user_id="u1")
    bus = EventBus(store=_InMemoryStore())

    retriever = RetrieverAgent()
    bus.subscribe(retriever, retriever.subscriptions)

    seed = Event(type=EventType.ACTION_REQUESTED, source=EventSource.ORCHESTRATOR,
                 session_id="s3", payload={
                     "target": "retriever",
                     "query": "xyznonexistent12345",
                 })

    run_collab_loop(bus, ws, [seed], max_turns=10)
    events = bus.replay("s3")
    evidence = [e for e in events if e.type == EventType.RETRIEVED_EVIDENCE]
    assert len(evidence) == 1
    assert evidence[0].payload["retrieval_status"] == "empty"


def test_retrieval_event_source_is_retriever():
    """产出事件 source 必须为 retriever（白名单合规）"""
    ws = WorkspaceState(session_id="s4", user_id="u1")
    bus = EventBus(store=_InMemoryStore())

    retriever = RetrieverAgent()
    retriever._coordinator.index_documents([{"content": "测试"}])
    bus.subscribe(retriever, retriever.subscriptions)

    seed = Event(type=EventType.ACTION_REQUESTED, source=EventSource.ORCHESTRATOR,
                 session_id="s4", payload={"target": "retriever", "query": "测试"})

    run_collab_loop(bus, ws, [seed], max_turns=10)
    events = bus.replay("s4")
    evidence = [e for e in events if e.type == EventType.RETRIEVED_EVIDENCE]
    assert len(evidence) == 1
    assert evidence[0].source == EventSource.RETRIEVER


# ── evaluate 可跑验证 ──

def test_evaluate_produces_valid_metrics():
    """evaluate() 输出应为合法数值（供 Plan E 调用）。"""
    retriever = RetrieverAgent()
    retriever._coordinator.index_documents([
        {"content": "BERT 使用双向 Transformer 编码器"},
        {"content": "GPT 使用单向 Transformer 解码器"},
        {"content": "今天天气不错"},
    ])
    metrics = retriever.evaluate({
        "query": "Transformer 架构",
        "golden_chunks": ["双向 Transformer 编码器", "单向 Transformer 解码器"],
        "golden_answer": "BERT 双向，GPT 单向",
        "top_k": 3,
    })
    # 所有值应在 [0, 1] 区间（latency_ms 除外）
    assert 0.0 <= metrics["recall_at_k"] <= 1.0
    assert 0.0 <= metrics["context_precision"] <= 1.0
    assert 0.0 <= metrics["faithfulness"] <= 1.0
    assert 0.0 <= metrics["answer_relevancy"] <= 1.0
    assert 0.0 <= metrics["redundancy"] <= 1.0
    assert metrics["latency_ms"] >= 0


# ── 多源聚合集成 ──

def test_multi_source_retrieval_integration():
    """向量+OCR+代码三源同时检索，结果合并返回。"""
    retriever = RetrieverAgent()

    # 向量源
    retriever._coordinator.index_documents([
        {"content": "LoRA 是低秩适配方法"},
    ])

    # OCR 源
    ocr = OCRProvider()
    ocr.index([{"content": "LoRA 论文图表展示参数效率"}])
    retriever._coordinator.register_provider(ocr)

    # 代码源
    code = CodeIndexProvider()
    code.index_file("/repo/lora.py", '''
def lora_forward(x, A, B, alpha):
    """LoRA forward pass: h = Wx + alpha * BAx"""
    return x + alpha * (x @ A @ B)
''')
    retriever._coordinator.register_provider(code)

    result = retriever._coordinator.search("LoRA", sources=None, top_k=10)
    assert result.total_found >= 2
    assert len(result.sources_used) >= 2
