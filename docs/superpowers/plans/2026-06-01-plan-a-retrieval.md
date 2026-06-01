# Plan A：检索与知识库 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 Retriever Agent（事件驱动、机械层检索）+ RAG 基础设施三源扩展（文档向量/OCR/代码索引），提供 `evaluate()` 接口供 Plan E 调用。

**Architecture:** RetrieverAgent 继承 AgentBase，订阅 `ActionRequested(target=retriever)`，委托 RAGCoordinator 做多源检索，返回 `RetrievedEvidence`（含原始 similarity score + 机械状态 `retrieval_status`）。RAGCoordinator 从单一 FakeRAGStore 扩展为多 Provider 协调器（VectorStore / OCRProvider / CodeIndexProvider），统一 `search(query, top_k) -> list[Chunk]` 接口。OCR 和代码索引各自实现 `IndexProvider` 协议，可独立注册/注销。

**Tech Stack:** Python 3.12+, pytest (同步), aiosqlite (RAGCoordinator 用同步 sqlite3 与现有 EventStore 风格一致；Agent 的 handle 为同步方法), StrEnum, dataclasses

---

## 0. 前置约束（务必遵守）

- **Plan 0 冻结接口只读不写**：`app/agents/base.py`、`app/harness/events.py`、`app/harness/enums.py`、`app/harness/workspace_state.py`、`app/harness/eventbus.py`、`app/orchestration/collab_loop.py` 已冻结，Retriever 只能依赖其公开签名，不得修改。
- **所有 Agent 共享约束**：source/subscriptions/emittable_types 声明即契约；handle 返回 list[Event]；emit 校验 emittable_types；evaluate 供 Plan E。
- **emittable 严格限定**：`{EventType.RETRIEVED_EVIDENCE, EventType.RETRIEVAL_FAILED}`，多一个少一个都违规。
- **不自评语义质量**：Retriever 的 `retrieval_status` 只能是 `ok|empty|timeout|low_score`（纯机械状态），不做"证据够不够好"的判断。
- **不改老代码**：`app/agent/` 全程只读；`app/infrastructure/external/ocr.py` 和 `app/infrastructure/extraction/file_extract.py` 只读参考，不原地编辑——OCR 新代码写在 `app/infrastructure/rag/ocr.py`。
- **测试风格**：沿用项目现有的同步 pytest（非 asyncio），`FakeRAGStore` 词匹配模式。

---

## 1. 模块总览

### 1.1 边界

```
┌─────────────────────────────────────────────────────────┐
│  Orchestration 层                                        │
│  collab_loop → EventBus.publish(ActionRequested(         │
│                  target=retriever, query=..., top_k=5))  │
└────────────────────────┬────────────────────────────────┘
                         │ 事件（EventBus）
                         ▼
┌─────────────────────────────────────────────────────────┐
│  Agent 层：RetrieverAgent                                │
│  - 订阅 ActionRequested(target=retriever)                │
│  - 委托 RAGCoordinator.search(query, sources, top_k)    │
│  - 判定 retrieval_status（纯机械：ok/empty/timeout/      │
│    low_score）                                           │
│  - emit RetrievedEvidence / RetrievalFailed             │
│  - evaluate(test_case) → RAG 三件套 + recall@k          │
└────────────────────────┬────────────────────────────────┘
                         │ 委托
                         ▼
┌─────────────────────────────────────────────────────────┐
│  Infrastructure 层：RAGCoordinator（扩展）               │
│  - 管理多个 IndexProvider（可注册/注销）                 │
│  - search(query, sources, top_k) → list[Chunk]          │
│  - 结果去重 + 按原始 score 排序                          │
│                                                          │
│  IndexProvider 协议：                                    │
│  ├── VectorStoreProvider（现有 FakeRAGStore 适配）       │
│  ├── OCRProvider（新建，图片文本提取+索引）              │
│  └── CodeIndexProvider（新建，git+AST 切片索引）         │
│                                                          │
│  extractors/（新建目录）                                  │
│  ├── base.py        — Extractor 协议                     │
│  ├── pdf_extractor.py   — PDF 文本提取                   │
│  ├── docx_extractor.py  — DOCX 文本提取（新增）          │
│  └── text_extractor.py  — txt/md/csv 文本提取            │
└─────────────────────────────────────────────────────────┘
```

### 1.2 技术选型

| 维度 | 选择 | 理由 |
|---|---|---|
| Agent 实现 | 继承 AgentBase，同步 handle | 与 Plan 0 冻结接口一致；协作环单线程 |
| RAG 协调 | 扩展现有 RAGCoordinator | spec §7 标注为 [扩展]，保留现有接口兼容 |
| OCR | 新建 ocr.py，内部调 pytesseract（可选依赖） | 现有 external/ocr.py 是空 stub，新代码写在 rag/ 下 |
| 代码索引 | 新建 code_index.py，AST 用 ast 标准库 | Python 仓库就地解析；其他语言用 tree-sitter 可选 |
| 文档提取 | extractors/ 目录，协议模式 | 支持扩展新格式（当前：PDF/DOCX/TXT/MD/CSV） |
| 测试 | 同步 pytest，内存 FakeStore | 与项目现有风格一致 |
| 存储 | aiosqlite（仅 coordinator 用 sqlite3 同步，与 EventStore 一致） | Plan 0 风格；OCR/代码索引用内存 dict 做 Fake |

### 1.3 与现有架构的衔接

- `RAGCoordinator.retrieve()` 现有签名 `(query, top_k) -> dict` **保持向后兼容**，内部委托给新的多 Provider 架构。新增 `search(query, sources, top_k) -> list[Chunk]` 作为主入口。
- `FakeRAGStore` 保持不动，作为默认 VectorStoreProvider 的存储后端。
- RetrieverAgent 通过 `RAGCoordinator.search()` 获取结果，不直接访问 store。
- `evaluate()` 接口返回 dict，字段对齐 spec §5.2：`faithfulness`, `answer_relevancy`, `context_precision`, `recall_at_k`, `latency_ms`, `redundancy`。初期用规则/启发式实现（不依赖 ragas 库），后续可替换为真实 LLM-judge。

---

## 2. 子模块概述

### 2.1 RetrieverAgent（`app/agents/retriever.py`）

**职责**：事件驱动的检索 Agent。接收 `ActionRequested(target=retriever)`，委托 RAGCoordinator 执行多源检索，根据机械指标判定 `retrieval_status`，发出 `RetrievedEvidence` 或 `RetrievalFailed`。

**接口契约**：
- `source = EventSource.RETRIEVER`
- `subscriptions = [EventType.ACTION_REQUESTED]`
- `emittable_types = {EventType.RETRIEVED_EVIDENCE, EventType.RETRIEVAL_FAILED}`
- `handle(event, ws) -> list[Event]`：主入口，过滤 `target != retriever` 的事件直接返回 []；解析 payload 中的 `query`、`top_k`、`sources`、`purpose`；调用 `_do_retrieve()` 执行检索；判定 `retrieval_status` 并 emit 对应事件
- `emit(type, ws, payload, parent_id) -> Event`：继承自 AgentBase，自动校验 emittable_types
- `evaluate(test_case) -> dict`：离线评估接口（见 §2.6）

**数据流**：
```
ActionRequested(payload: {query, top_k, sources?, purpose?})
  → handle() 过滤 target
  → _do_retrieve(query, top_k, sources)
    → RAGCoordinator.search(query, sources, top_k)
    → 判定 retrieval_status:
        - 0 条结果 → empty
        - 超时 → timeout
        - max_score < LOW_SCORE_THRESHOLD → low_score
        - 否则 → ok
  → emit RetrievedEvidence(chunks, scores, retrieval_status, sources_used)
    或 emit RetrievalFailed(reason, retrieval_status)
```

**状态管理**：RetrieverAgent 本身无状态（不写 WorkspaceState）。检索结果通过 Event payload 传递。

**错误处理**：
- `target != retriever`：静默跳过，返回 []（不抛错——协作环可能 broadcast ActionRequested）
- RAGCoordinator 抛异常：捕获后 emit `RetrievalFailed(reason=str(e), retrieval_status=timeout)`
- 结果为空：emit `RetrievedEvidence(chunks=[], retrieval_status=empty)`（这是合法结果，不是失败）

### 2.2 RAGCoordinator 扩展（`app/infrastructure/rag/coordinator.py`）

**职责**：从单一 store 变为多 Provider 协调器。管理一组 `IndexProvider` 实例，统一 `search()` 接口，聚合多源结果。

**接口契约**：
- 保持 `retrieve(query, top_k) -> dict` 向后兼容（内部委托给 VectorStoreProvider）
- 新增 `search(query, sources=None, top_k=5) -> SearchResult`：
  - `sources=None` 表示所有已注册 provider
  - `sources=["vector", "ocr", "code"]` 限定来源
  - 返回 `SearchResult(chunks: list[Chunk], total_found: int, sources_used: list[str])`
- 新增 `register_provider(provider: IndexProvider)` / `unregister_provider(name: str)`
- 新增 `index_documents(docs, source="vector")` 支持指定来源

**数据结构**：
```python
@dataclass
class Chunk:
    content: str
    score: float          # 原始 similarity score（0-1 或 raw distance）
    source: str           # "vector" | "ocr" | "code"
    metadata: dict        # file_path, page, line_start, symbol_name, repo, ...

@dataclass
class SearchResult:
    chunks: list[Chunk]
    total_found: int
    sources_used: list[str]
```

**IndexProvider 协议**（在 coordinator.py 中定义）：
```python
class IndexProvider(ABC):
    name: str              # "vector" | "ocr" | "code"

    @abstractmethod
    def index(self, docs: list[dict]) -> None: ...

    @abstractmethod
    def search(self, query: str, top_k: int) -> list[Chunk]: ...

    @property
    def doc_count(self) -> int: ...
```

**去重与排序**：多源结果按 `score` 降序排列；`content` 完全相同的 chunk 去重（保留 score 更高的）。

**现有接口兼容**：`retrieve()` 方法内部调 `self.search(query, sources=["vector"], top_k)`，将 `list[Chunk]` 转为旧 dict 格式返回，确保现有 `test_rag.py` 的两个测试不变绿。

### 2.3 OCRProvider（`app/infrastructure/rag/ocr.py`）

**职责**：从图片中提取文本并建立可检索索引。实现 `IndexProvider` 协议。

**接口契约**：
- `OCRProvider(name="ocr")` 实现 `IndexProvider`
- `extract_text(image_bytes: bytes) -> str`：调 OCR 引擎提取文本
- `index_image(image_bytes, metadata) -> None`：提取文本 + 分块 + 建索引
- `search(query, top_k) -> list[Chunk]`：检索已索引的 OCR 文本
- `doc_count -> int`：已索引的图片数

**OCR 引擎**：初期用 `pytesseract`（可选依赖，import 失败时降级为 stub 返回空字符串，不阻断系统启动）。后续可替换为云 OCR API。

**分块策略**：按段落分块（双换行分割），每块保留来源图片路径和页码。

**Fake 实现**（测试用）：`FakeOCRProvider` 继承 OCRProvider，用内存 dict 存储文本，不依赖 tesseract。

### 2.4 CodeIndexProvider（`app/infrastructure/rag/code_index.py`）

**职责**：索引代码仓库，支持按符号名、函数名、类名、注释检索。实现 `IndexProvider` 协议。

**接口契约**：
- `CodeIndexProvider(name="code", repo_path=None)` 实现 `IndexProvider`
- `index_repo(repo_path: str, glob_pattern="**/*.py") -> int`：扫描仓库文件，AST 解析，建索引
- `index_file(file_path, source_code) -> list[dict]`：单文件索引
- `search(query, top_k) -> list[Chunk]`：按符号名/注释/代码片段检索
- `doc_count -> int`：已索引的符号数

**索引粒度**：以函数/类/方法为最小索引单元（chunk = 一个符号的完整源码 + docstring + 注释）。

**AST 解析**：
- Python：标准库 `ast` 提取 `FunctionDef`、`ClassDef`、`AsyncFunctionDef`
- 其他语言：初期跳过（不索引），不抛错；后续用 tree-sitter

**检索方式**：简单词匹配（与 FakeRAGStore 一致）——query 中的 token 出现在符号名/docstring/代码中即命中，score = 命中 token 数 / query token 数。

**Fake 实现**：可直接用 `FakeRAGStore` 作为存储后端（`CodeIndexProvider` 内部持有一个 `FakeRAGStore` 实例，将 AST 切片转为 doc dict 存入）。

### 2.5 extractors/（`app/infrastructure/rag/extractors/`）

**职责**：从不同格式文件中提取纯文本，供 IndexProvider 索引。

**目录结构**：
```
app/infrastructure/rag/extractors/
├── __init__.py
├── base.py              # Extractor 协议 + get_extractor() 工厂
├── pdf_extractor.py     # PDF 文本提取
├── docx_extractor.py    # DOCX 文本提取（新增）
└── text_extractor.py    # txt/md/csv 文本提取
```

**Extractor 协议**（base.py）：
```python
class Extractor(ABC):
    extensions: list[str]      # 支持的文件扩展名

    @abstractmethod
    def extract(self, file_path: str) -> str: ...

    @abstractmethod
    def extract_with_metadata(self, file_path: str) -> list[dict]:
        # 返回 [{content, page, ...}] 用于分块索引
```

**工厂函数**：`get_extractor(file_path: str) -> Extractor | None`，按扩展名匹配合适的提取器。

**DOCX 提取**：用 `python-docx`（可选依赖）提取段落文本。import 失败时降级为返回空字符串 + warning 日志。

**PDF 提取**：初期用 PyPDF2/pdfplumber（可选依赖）。失败降级同 DOCX。

**文本提取**：纯 Python 标准库，无需额外依赖。

### 2.6 evaluate() 实现

**职责**：实现 spec §5.2 的 Retriever 部件级评估接口，供 Plan E 调用。

**接口**：
```python
def evaluate(self, test_case: dict) -> dict:
    # test_case = {
    #     "query": str,
    #     "golden_chunks": list[str],   # 人工标注的相关 chunk 内容
    #     "golden_answer": str,          # 期望答案（用于 faithfulness 判）
    #     "top_k": int,                  # 默认 5
    # }
    # return {
    #     "faithfulness": float,         # 0-1，检索内容支撑答案的程度
    #     "answer_relevancy": float,     # 0-1，检索内容与 query 的相关度
    #     "context_precision": float,    # 0-1，检索结果中相关 chunk 占比
    #     "recall_at_k": float,          # 0-1，golden_chunks 被检索到的比例
    #     "latency_ms": float,
    #     "redundancy": float,           # 重复内容占比
    # }
```

**实现策略**（初期启发式，后续可替换 ragas）：
- `recall_at_k`：golden_chunks 中有多少出现在检索结果的 content 中（子串匹配），严格可计算
- `context_precision`：检索结果中与 golden_chunks 有交集的 chunk 数 / 总检索 chunk 数
- `answer_relevancy`：检索结果 content 拼接后与 query 的词重叠率（Jaccard）
- `faithfulness`：检索结果 content 拼接后与 golden_answer 的词重叠率
- `latency_ms`：记录 `time.time()` 差值
- `redundancy`：检索结果中两两 chunk 的 content 相似度 > 0.8 的比例

---

## 3. 子模块详细实施计划（Task 拆分）

### 依赖关系

```
Task 1: IndexProvider 协议 + Chunk/SearchResult
  ├── Task 2: OCRProvider
  ├── Task 3: CodeIndexProvider
  ├── Task 4: extractors/
  └── Task 5: RAGCoordinator 扩展（多 Provider）
        └── Task 6: RetrieverAgent
              └── Task 7: evaluate() + RAG 三件套
                    └── Task 8: 集成测试（协作环 + OCR/代码场景）
```

---

### Task 1: IndexProvider 协议 + Chunk/SearchResult 数据结构

**文件：**
- 修改：`app/infrastructure/rag/coordinator.py`（在文件顶部新增数据类 + 协议）

**设计要点：**
- `Chunk` 是检索结果的最小单元，包含 content、score、source 标识、metadata
- `SearchResult` 是多源聚合结果容器
- `IndexProvider` 是抽象协议，所有检索后端（Vector/OCR/Code）必须实现
- `FakeRAGStore` 需要适配为 `IndexProvider`（在 Task 5 做）

- [ ] **Step 1: 编写 IndexProvider 协议 + 数据类的测试**

在 `tests/unit/infrastructure/test_rag.py` 末尾追加：

```python
from app.infrastructure.rag.coordinator import Chunk, SearchResult, IndexProvider


def test_chunk_defaults():
    c = Chunk(content="hello", score=0.9, source="vector")
    assert c.content == "hello"
    assert c.score == 0.9
    assert c.source == "vector"
    assert c.metadata == {}


def test_search_result_empty():
    sr = SearchResult(chunks=[], total_found=0, sources_used=[])
    assert sr.chunks == []
    assert sr.total_found == 0


def test_index_provider_is_abstract():
    """IndexProvider 是抽象协议，不能直接实例化。"""
    with pytest.raises(TypeError):
        IndexProvider()  # noqa  # 抽象类不可实例化


def test_index_provider_subclass_must_implement_all():
    """缺少抽象方法实现的子类不可实例化。"""

    class _BadProvider(IndexProvider):
        pass

    with pytest.raises(TypeError):
        _BadProvider()  # noqa
```

- [ ] **Step 2: 运行测试验证失败**

```bash
pytest tests/unit/infrastructure/test_rag.py::test_chunk_defaults -v
```
预期：FAIL（Chunk 未定义）

- [ ] **Step 3: 在 coordinator.py 顶部新增数据类 + 协议**

在 `app/infrastructure/rag/coordinator.py` 文件开头（import 之后、`class RAGCoordinator` 之前）添加：

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Chunk:
    """检索结果的最小单元（§3.6 证据片段）。"""
    content: str
    score: float                         # 原始 similarity score
    source: str = "vector"               # "vector" | "ocr" | "code"
    metadata: dict = field(default_factory=dict)  # file_path, page, line, symbol, ...


@dataclass
class SearchResult:
    """多源聚合的检索结果。"""
    chunks: list[Chunk]
    total_found: int
    sources_used: list[str]


class IndexProvider(ABC):
    """检索后端协议：所有 provider（向量/OCR/代码）必须实现。"""

    name: str

    @abstractmethod
    def index(self, docs: list[dict]) -> None:
        """索引一批文档/文本块。"""
        ...

    @abstractmethod
    def search(self, query: str, top_k: int = 5) -> list[Chunk]:
        """检索并返回 Chunk 列表。"""
        ...

    @property
    @abstractmethod
    def doc_count(self) -> int:
        """已索引的文档数。"""
        ...
```

- [ ] **Step 4: 运行测试验证通过**

```bash
pytest tests/unit/infrastructure/test_rag.py::test_chunk_defaults tests/unit/infrastructure/test_rag.py::test_search_result_empty tests/unit/infrastructure/test_rag.py::test_index_provider_is_abstract tests/unit/infrastructure/test_rag.py::test_index_provider_subclass_must_implement_all -v
```
预期：4 PASS

- [ ] **Step 5: 确认已有 RAG 测试不受影响**

```bash
pytest tests/unit/infrastructure/test_rag.py -v
```
预期：全部通过（包括已有的 test_rag_coordinator_retrieve_empty 等）

- [ ] **Step 6: 提交**

```bash
git add app/infrastructure/rag/coordinator.py tests/unit/infrastructure/test_rag.py
git commit -m "feat(rag): add IndexProvider protocol + Chunk/SearchResult data classes

Task 1 of Plan A — define the provider abstraction that OCR and code index
will implement, plus the result types for multi-source aggregation.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: OCRProvider — 图片文本提取与索引

**文件：**
- 创建：`app/infrastructure/rag/ocr.py`
- 创建：`tests/unit/infrastructure/test_ocr.py`

**设计要点：**
- `OCRProvider` 实现 `IndexProvider` 协议
- 内部用 `FakeRAGStore` 做存储（测试友好，不依赖 tesseract）
- `extract_text()` 方法：尝试调 pytesseract，失败返回空字符串
- `index_image()` 方法：提取文本 → 分块 → 存入 store
- `search()` 委托给内部 store

- [ ] **Step 1: 编写 OCRProvider 测试**

创建 `tests/unit/infrastructure/test_ocr.py`：

```python
import pytest
from app.infrastructure.rag.ocr import OCRProvider
from app.infrastructure.rag.coordinator import Chunk


def test_ocr_provider_name():
    provider = OCRProvider()
    assert provider.name == "ocr"


def test_ocr_provider_implements_protocol():
    """OCRProvider 应实现 IndexProvider 协议。"""
    from app.infrastructure.rag.coordinator import IndexProvider
    assert isinstance(OCRProvider(), IndexProvider)


def test_ocr_index_and_search():
    provider = OCRProvider()
    # 模拟 OCR 提取的文本
    provider.index([
        {"content": "深度学习中的注意力机制允许模型关注输入的特定部分",
         "metadata": {"file": "slide1.png", "page": 1}},
        {"content": "Transformer 架构完全基于注意力机制",
         "metadata": {"file": "slide2.png", "page": 1}},
    ])
    assert provider.doc_count == 2

    results = provider.search("注意力机制", top_k=5)
    assert len(results) >= 1
    assert all(isinstance(c, Chunk) for c in results)
    assert all(c.source == "ocr" for c in results)
    # 最相关的结果应包含"注意力机制"
    assert any("注意力机制" in c.content for c in results)


def test_ocr_search_empty():
    provider = OCRProvider()
    results = provider.search("不存在的内容", top_k=5)
    assert results == []


def test_ocr_doc_count_zero_initially():
    provider = OCRProvider()
    assert provider.doc_count == 0


def test_ocr_chunk_metadata_preserved():
    provider = OCRProvider()
    provider.index([
        {"content": "测试文本", "metadata": {"file": "test.png", "page": 3}},
    ])
    results = provider.search("测试", top_k=1)
    assert len(results) == 1
    assert results[0].metadata["file"] == "test.png"
    assert results[0].metadata["page"] == 3
```

- [ ] **Step 2: 运行测试验证失败**

```bash
pytest tests/unit/infrastructure/test_ocr.py -v
```
预期：FAIL（模块不存在或 OCRProvider 未定义）

- [ ] **Step 3: 实现 OCRProvider**

创建 `app/infrastructure/rag/ocr.py`：

```python
"""OCR 文本提取与索引 Provider（§9 RAG 扩展）。

实现 IndexProvider 协议，内部用 FakeRAGStore 做存储。
生产环境可接入 pytesseract / 云 OCR API。
"""

from app.infrastructure.rag.coordinator import Chunk, IndexProvider
from app.infrastructure.rag.store import FakeRAGStore


class OCRProvider(IndexProvider):
    """OCR 图片文本索引 Provider。

    生产用法：
        provider = OCRProvider()
        provider.index_image(image_bytes, metadata={"file": "slide.png"})
        results = provider.search("注意力机制")
    """

    name = "ocr"

    def __init__(self):
        self._store = FakeRAGStore()

    # --- 文本提取（可选依赖 pytesseract） ---

    def extract_text(self, image_bytes: bytes) -> str:
        """从图片字节提取文本。pytesseract 不可用时返回空字符串。"""
        try:
            import pytesseract
            from PIL import Image
            import io
            img = Image.open(io.BytesIO(image_bytes))
            return pytesseract.image_to_string(img) or ""
        except ImportError:
            return ""

    # --- IndexProvider 协议 ---

    def index(self, docs: list[dict]) -> None:
        """索引已提取文本的文档列表。每项含 content 和可选的 metadata。"""
        self._store.index(docs)

    def index_image(self, image_bytes: bytes, metadata: dict | None = None) -> str:
        """提取图片文本并按段落分块索引。返回提取的文本。"""
        text = self.extract_text(image_bytes)
        if not text:
            return ""
        meta = metadata or {}
        # 按双换行分块
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        docs = [{"content": p, "metadata": {**meta, "chunk_idx": i}}
                for i, p in enumerate(paragraphs)]
        self.index(docs)
        return text

    def search(self, query: str, top_k: int = 5) -> list[Chunk]:
        """检索 OCR 文本中的相关内容。"""
        raw = self._store.query(query, top_k)
        return [
            Chunk(content=r["content"], score=float(r.get("score", 0)),
                  source="ocr", metadata=r.get("metadata", {}))
            for r in raw
        ]

    @property
    def doc_count(self) -> int:
        return self._store.doc_count
```

- [ ] **Step 4: 运行测试验证通过**

```bash
pytest tests/unit/infrastructure/test_ocr.py -v
```
预期：6 PASS

- [ ] **Step 5: 提交**

```bash
git add app/infrastructure/rag/ocr.py tests/unit/infrastructure/test_ocr.py
git commit -m "feat(rag): add OCRProvider with image text extraction and indexing

Task 2 of Plan A — OCR text pipeline that implements IndexProvider.
Uses FakeRAGStore as backend; pytesseract is optional (graceful degrade).

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: CodeIndexProvider — 代码仓库 AST 切片索引

**文件：**
- 创建：`app/infrastructure/rag/code_index.py`
- 创建：`tests/unit/infrastructure/test_code_index.py`

**设计要点：**
- `CodeIndexProvider` 实现 `IndexProvider` 协议
- 内部用 `FakeRAGStore` 做存储
- `index_repo()` 扫描目录 → 对每个 .py 文件调 `index_file()`
- `index_file()` 用 `ast` 标准库解析 Python 源码，提取 FunctionDef/ClassDef/AsyncFunctionDef，将每个符号（含 docstring + 源码）作为一个 chunk 索引
- `search()` 委托给内部 store，按符号名/docstring/代码内容匹配

- [ ] **Step 1: 编写 CodeIndexProvider 测试**

创建 `tests/unit/infrastructure/test_code_index.py`：

```python
import tempfile
import os
import pytest
from app.infrastructure.rag.code_index import CodeIndexProvider
from app.infrastructure.rag.coordinator import Chunk


SAMPLE_CODE = '''
"""A simple math module."""

def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b

def multiply(a: int, b: int) -> int:
    """Multiply two integers."""
    return a * b

class Calculator:
    """A simple calculator class."""

    def __init__(self, initial: int = 0):
        self.value = initial

    def add(self, x: int) -> int:
        """Add x to the current value."""
        self.value += x
        return self.value
'''


def test_code_index_provider_name():
    provider = CodeIndexProvider()
    assert provider.name == "code"


def test_code_index_provider_implements_protocol():
    from app.infrastructure.rag.coordinator import IndexProvider
    assert isinstance(CodeIndexProvider(), IndexProvider)


def test_index_file_extracts_functions():
    provider = CodeIndexProvider()
    provider.index_file("/fake/math.py", SAMPLE_CODE)
    assert provider.doc_count >= 3  # add, multiply, Calculator, Calculator.add, Calculator.__init__


def test_search_by_function_name():
    provider = CodeIndexProvider()
    provider.index_file("/fake/math.py", SAMPLE_CODE)
    results = provider.search("add", top_k=5)
    assert len(results) >= 1
    # 函数名 add 应命中
    assert any("add" in c.content for c in results)


def test_search_by_docstring():
    provider = CodeIndexProvider()
    provider.index_file("/fake/math.py", SAMPLE_CODE)
    results = provider.search("multiply two integers", top_k=3)
    assert len(results) >= 1
    assert any("multiply" in c.content.lower() for c in results)


def test_search_by_class_name():
    provider = CodeIndexProvider()
    provider.index_file("/fake/math.py", SAMPLE_CODE)
    results = provider.search("Calculator", top_k=3)
    assert len(results) >= 1
    assert any("Calculator" in c.content for c in results)


def test_code_chunk_has_source_metadata():
    provider = CodeIndexProvider()
    provider.index_file("/fake/math.py", SAMPLE_CODE)
    results = provider.search("add", top_k=1)
    assert len(results) == 1
    assert results[0].source == "code"
    assert "file" in results[0].metadata


def test_code_search_empty():
    provider = CodeIndexProvider()
    assert provider.search("nonexistent", top_k=5) == []


def test_index_repo_scans_directory():
    provider = CodeIndexProvider()
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建两个 .py 文件
        with open(os.path.join(tmpdir, "a.py"), "w") as f:
            f.write("def foo():\n    return 42\n")
        with open(os.path.join(tmpdir, "b.py"), "w") as f:
            f.write("def bar():\n    return 99\n")
        count = provider.index_repo(tmpdir, glob_pattern="**/*.py")
        assert count >= 2
        # foo 可检索
        assert len(provider.search("foo", top_k=1)) == 1
        # bar 可检索
        assert len(provider.search("bar", top_k=1)) == 1
```

- [ ] **Step 2: 运行测试验证失败**

```bash
pytest tests/unit/infrastructure/test_code_index.py -v
```
预期：FAIL

- [ ] **Step 3: 实现 CodeIndexProvider**

创建 `app/infrastructure/rag/code_index.py`：

```python
"""代码仓库 AST 切片索引 Provider（§9 RAG 扩展）。

实现 IndexProvider 协议，用 Python ast 标准库解析源码，
按函数/类/方法粒度建索引。
"""

import ast
import glob
import os

from app.infrastructure.rag.coordinator import Chunk, IndexProvider
from app.infrastructure.rag.store import FakeRAGStore


class CodeIndexProvider(IndexProvider):
    """代码仓库索引 Provider。

    用法：
        provider = CodeIndexProvider()
        provider.index_repo("/path/to/repo")
        results = provider.search("def train")
    """

    name = "code"

    def __init__(self):
        self._store = FakeRAGStore()

    # --- AST 解析 ---

    def index_file(self, file_path: str, source_code: str) -> list[dict]:
        """解析单个 Python 文件，为每个函数/类建立索引项。"""
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return []

        docs = []
        module_doc = ast.get_docstring(tree) or ""

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                doc = self._node_to_doc(node, file_path, module_doc)
                if doc:
                    docs.append(doc)
        self._store.index(docs)
        return docs

    def _node_to_doc(self, node: ast.AST, file_path: str, module_doc: str) -> dict | None:
        """将 AST 节点转为可索引的文档 dict。"""
        name = node.name
        docstring = ast.get_docstring(node) or ""
        try:
            source_snippet = ast.unparse(node)
        except Exception:
            source_snippet = ""

        # 索引内容 = 符号名 + docstring + 模块 doc + 源码前 500 字符
        content_parts = [name]
        if docstring:
            content_parts.append(docstring)
        if module_doc:
            content_parts.append(module_doc)
        if source_snippet:
            content_parts.append(source_snippet[:500])
        content = "\n".join(content_parts)

        node_type = "class" if isinstance(node, ast.ClassDef) else "function"
        return {
            "content": content,
            "metadata": {
                "file": file_path,
                "symbol_name": name,
                "symbol_type": node_type,
                "has_docstring": bool(docstring),
            }
        }

    # --- 仓库级索引 ---

    def index_repo(self, repo_path: str, glob_pattern: str = "**/*.py") -> int:
        """扫描仓库目录，索引所有匹配的 Python 文件。返回索引的符号总数。"""
        pattern = os.path.join(repo_path, glob_pattern)
        files = glob.glob(pattern, recursive=True)
        total = 0
        for fp in files:
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    source = f.read()
            except (IOError, UnicodeDecodeError):
                continue
            docs = self.index_file(fp, source)
            total += len(docs)
        return total

    # --- IndexProvider 协议 ---

    def index(self, docs: list[dict]) -> None:
        """批量索引已解析的代码文档。"""
        self._store.index(docs)

    def search(self, query: str, top_k: int = 5) -> list[Chunk]:
        """按符号名/docstring/代码内容检索。"""
        raw = self._store.query(query, top_k)
        return [
            Chunk(content=r["content"], score=float(r.get("score", 0)),
                  source="code", metadata=r.get("metadata", {}))
            for r in raw
        ]

    @property
    def doc_count(self) -> int:
        return self._store.doc_count
```

- [ ] **Step 4: 运行测试验证通过**

```bash
pytest tests/unit/infrastructure/test_code_index.py -v
```
预期：8 PASS

- [ ] **Step 5: 提交**

```bash
git add app/infrastructure/rag/code_index.py tests/unit/infrastructure/test_code_index.py
git commit -m "feat(rag): add CodeIndexProvider with AST-based symbol indexing

Task 3 of Plan A — indexes Python repos at function/class granularity
using the standard ast module. Non-Python files are gracefully skipped.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: extractors/ — 文档提取器（PDF/DOCX/TXT）

**文件：**
- 创建：`app/infrastructure/rag/extractors/__init__.py`
- 创建：`app/infrastructure/rag/extractors/base.py`
- 创建：`app/infrastructure/rag/extractors/text_extractor.py`
- 创建：`app/infrastructure/rag/extractors/pdf_extractor.py`
- 创建：`app/infrastructure/rag/extractors/docx_extractor.py`
- 创建：`tests/unit/infrastructure/test_extractors.py`

**设计要点：**
- `Extractor` 抽象协议：`extensions` 类属性 + `extract(file_path) -> str` 方法
- `get_extractor(file_path) -> Extractor | None` 工厂函数
- TextExtractor 处理 txt/md/csv（纯标准库）
- PDFExtractor 尝试 PyPDF2/pdfplumber，降级返回 ""
- DocxExtractor 尝试 python-docx，降级返回 ""

- [ ] **Step 1: 编写 extractors 测试**

创建 `tests/unit/infrastructure/test_extractors.py`：

```python
import os
import tempfile
import pytest
from app.infrastructure.rag.extractors.base import Extractor, get_extractor
from app.infrastructure.rag.extractors.text_extractor import TextExtractor


def test_text_extractor_extensions():
    ext = TextExtractor()
    assert ".txt" in ext.extensions
    assert ".md" in ext.extensions


def test_text_extractor_extract_txt():
    ext = TextExtractor()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("Hello World")
        tmp = f.name
    try:
        result = ext.extract(tmp)
        assert result == "Hello World"
    finally:
        os.unlink(tmp)


def test_text_extractor_extract_md():
    ext = TextExtractor()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write("# Title\nContent")
        tmp = f.name
    try:
        result = ext.extract(tmp)
        assert "# Title" in result
    finally:
        os.unlink(tmp)


def test_get_extractor_returns_text_for_txt():
    e = get_extractor("/path/to/doc.txt")
    assert e is not None
    assert isinstance(e, TextExtractor)


def test_get_extractor_returns_text_for_md():
    e = get_extractor("readme.md")
    assert isinstance(e, TextExtractor)


def test_get_extractor_returns_none_for_unknown():
    e = get_extractor("image.xyz")
    assert e is None


def test_extractor_is_abstract():
    with pytest.raises(TypeError):
        Extractor()  # noqa
```

- [ ] **Step 2: 运行测试验证失败**

```bash
pytest tests/unit/infrastructure/test_extractors.py -v
```
预期：FAIL

- [ ] **Step 3: 实现 extractors**

创建 `app/infrastructure/rag/extractors/__init__.py`：

```python
"""文档提取器：从不同格式文件中提取纯文本。"""
```

创建 `app/infrastructure/rag/extractors/base.py`：

```python
"""Extractor 抽象协议 + 工厂函数。"""

from abc import ABC, abstractmethod


class Extractor(ABC):
    """文件文本提取器协议。"""

    extensions: list[str] = []

    @abstractmethod
    def extract(self, file_path: str) -> str:
        """从文件中提取纯文本。"""
        ...


def get_extractor(file_path: str) -> Extractor | None:
    """按文件扩展名匹配合适的提取器。"""
    from app.infrastructure.rag.extractors.text_extractor import TextExtractor
    from app.infrastructure.rag.extractors.pdf_extractor import PDFExtractor
    from app.infrastructure.rag.extractors.docx_extractor import DocxExtractor

    ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
    for cls in [TextExtractor, PDFExtractor, DocxExtractor]:
        if ext in cls.extensions:
            return cls()
    return None
```

创建 `app/infrastructure/rag/extractors/text_extractor.py`：

```python
"""纯文本文件提取器（txt/md/csv）。"""

from app.infrastructure.rag.extractors.base import Extractor


class TextExtractor(Extractor):
    extensions = ["txt", "md", "csv"]

    def extract(self, file_path: str) -> str:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        except (IOError, UnicodeDecodeError):
            return ""
```

创建 `app/infrastructure/rag/extractors/pdf_extractor.py`：

```python
"""PDF 文本提取器（可选依赖 PyPDF2/pdfplumber）。"""

from app.infrastructure.rag.extractors.base import Extractor


class PDFExtractor(Extractor):
    extensions = ["pdf"]

    def extract(self, file_path: str) -> str:
        # 尝试 pdfplumber（更好的文本提取）
        try:
            import pdfplumber
            with pdfplumber.open(file_path) as pdf:
                pages = [p.extract_text() or "" for p in pdf.pages]
            return "\n\n".join(pages)
        except ImportError:
            pass
        # 回退 PyPDF2
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(file_path)
            pages = [p.extract_text() or "" for p in reader.pages]
            return "\n\n".join(pages)
        except ImportError:
            return ""
        except Exception:
            return ""
```

创建 `app/infrastructure/rag/extractors/docx_extractor.py`：

```python
"""DOCX 文本提取器（可选依赖 python-docx）。"""

from app.infrastructure.rag.extractors.base import Extractor


class DocxExtractor(Extractor):
    extensions = ["docx"]

    def extract(self, file_path: str) -> str:
        try:
            from docx import Document
            doc = Document(file_path)
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            return "\n\n".join(paragraphs)
        except ImportError:
            return ""
        except Exception:
            return ""
```

- [ ] **Step 4: 运行测试验证通过**

```bash
pytest tests/unit/infrastructure/test_extractors.py -v
```
预期：7 PASS

- [ ] **Step 5: 提交**

```bash
git add app/infrastructure/rag/extractors/ tests/unit/infrastructure/test_extractors.py
git commit -m "feat(rag): add extractors module (PDF/DOCX/TXT) with factory

Task 4 of Plan A — Extractor protocol + PDF/DOCX/TXT implementations.
All heavy dependencies (PyPDF2, pdfplumber, python-docx) are optional.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: RAGCoordinator 扩展 — 多 Provider 协调

**文件：**
- 修改：`app/infrastructure/rag/coordinator.py`（扩展 RAGCoordinator 类）
- 修改：`tests/unit/infrastructure/test_rag.py`（追加测试）

**设计要点：**
- `RAGCoordinator` 内部维护 `_providers: dict[str, IndexProvider]`
- 构造时自动注册一个 `VectorStoreProvider`（适配现有的 `FakeRAGStore`）
- `register_provider()` / `unregister_provider()` 管理 provider
- `search(query, sources=None, top_k=5) -> SearchResult` 聚合多源结果
- 保持 `retrieve()` 向后兼容（委托给只有 vector 的 search）
- 去重：content 完全相同的 chunk 只保留 score 最高的elm

- [ ] **Step 1: 编写多 Provider 协调测试**

在 `tests/unit/infrastructure/test_rag.py` 末尾追加：

```python
from app.infrastructure.rag.coordinator import RAGCoordinator, Chunk, SearchResult, IndexProvider
from app.infrastructure.rag.store import FakeRAGStore
from app.infrastructure.rag.ocr import OCRProvider
from app.infrastructure.rag.code_index import CodeIndexProvider


def test_rag_coordinator_register_provider():
    coord = RAGCoordinator()
    ocr = OCRProvider()
    coord.register_provider(ocr)
    # 注册后应可检索
    ocr.index([{"content": "注意力机制是深度学习的核心"}])
    result = coord.search("注意力", sources=["ocr"])
    assert result.total_found >= 1
    assert "ocr" in result.sources_used


def test_rag_coordinator_unregister_provider():
    coord = RAGCoordinator()
    ocr = OCRProvider()
    coord.register_provider(ocr)
    coord.unregister_provider("ocr")
    result = coord.search("注意力", sources=["ocr"])
    assert result.total_found == 0


def test_rag_coordinator_multi_source_search():
    coord = RAGCoordinator()
    # 默认 vector provider
    coord.register_provider(OCRProvider())
    coord.register_provider(CodeIndexProvider())

    # 向各 provider 索引内容
    coord.index_documents([{"content": "RAG 是检索增强生成"}], source="vector")
    for p in coord._providers.values():
        if p.name == "ocr":
            p.index([{"content": "OCR 提取自图片的文本"}])
        if p.name == "code":
            p.index([{"content": "def train_model(): pass"}])

    # 全源检索
    result = coord.search("检索", sources=None, top_k=10)
    assert result.total_found >= 1
    assert len(result.sources_used) >= 1


def test_rag_coordinator_search_deduplicates():
    coord = RAGCoordinator()
    # 两个 provider 返回相同内容
    coord.index_documents([{"content": "完全相同的文本"}], source="vector")
    ocr = OCRProvider()
    ocr.index([{"content": "完全相同的文本"}])
    coord.register_provider(ocr)
    result = coord.search("完全相同", sources=None, top_k=10)
    # 去重后只保留一份
    contents = [c.content for c in result.chunks]
    assert contents.count("完全相同的文本") == 1


def test_rag_coordinator_retrieve_backward_compat():
    """Task 5 不破坏现有 retrieve() 签名。"""
    store = FakeRAGStore()
    store.index([{"content": "二分查找"}])
    coord = RAGCoordinator(store)
    result = coord.retrieve("二分查找")
    assert result["found"] is True
    assert len(result["citations"]) > 0


def test_rag_coordinator_search_sorts_by_score():
    coord = RAGCoordinator()
    coord.index_documents([
        {"content": "不太相关"},
        {"content": "高度相关高度相关高度相关"},
    ])
    result = coord.search("高度相关")
    assert len(result.chunks) >= 2
    # 分数高的应排在前面
    assert result.chunks[0].score >= result.chunks[1].score


def test_rag_coordinator_search_default_sources_is_all():
    coord = RAGCoordinator()
    ocr = OCRProvider()
    ocr.index([{"content": "OCR 文本"}])
    coord.register_provider(ocr)
    result = coord.search("OCR")
    # 未指定 sources 时应搜索所有 provider
    assert result.total_found >= 1


def test_rag_coordinator_vector_provider_registered_by_default():
    coord = RAGCoordinator()
    coord.index_documents([{"content": "默认向量存储"}])
    result = coord.search("向量")
    assert result.total_found >= 1
    assert "vector" in result.sources_used
```

- [ ] **Step 2: 运行测试验证失败**

```bash
pytest tests/unit/infrastructure/test_rag.py::test_rag_coordinator_register_provider -v
```
预期：FAIL（register_provider 不存在）

- [ ] **Step 3: 扩展 RAGCoordinator**

修改 `app/infrastructure/rag/coordinator.py`，在现有 `RAGCoordinator` 类中追加方法。保留原有 `__init__`、`index_documents`、`retrieve` 不变（向后兼容），新增以下内容：

```python
class RAGCoordinator:
    """RAG 协调器：管理多源 IndexProvider，聚合检索结果（§3.6/§9 扩展）。"""

    def __init__(self, store=None):
        self._store = store or FakeRAGStore()
        self._providers: dict[str, IndexProvider] = {}
        self._register_default_vector_provider()

    def _register_default_vector_provider(self) -> None:
        """将现有 FakeRAGStore/RAGStore 包装为 VectorStoreProvider。"""
        store_ref = self._store  # 闭包引用

        class _VectorStoreProvider(IndexProvider):
            name = "vector"

            def index(self, docs: list[dict]) -> None:
                store_ref.index(docs)

            def search(self, query: str, top_k: int = 5) -> list[Chunk]:
                raw = store_ref.query(query, top_k)
                return [
                    Chunk(content=r["content"], score=float(r.get("score", 0)),
                          source="vector", metadata=r.get("metadata", {}))
                    for r in raw
                ]

            @property
            def doc_count(self) -> int:
                return store_ref.doc_count

        self._providers["vector"] = _VectorStoreProvider()

    # --- Provider 管理 ---

    def register_provider(self, provider: IndexProvider) -> None:
        """注册一个检索后端（OCR/代码索引等）。"""
        self._providers[provider.name] = provider

    def unregister_provider(self, name: str) -> None:
        """注销指定检索后端（默认 vector 不可注销）。"""
        if name == "vector":
            return
        self._providers.pop(name, None)

    # --- 多源检索 ---

    def search(self, query: str, sources: list[str] | None = None,
               top_k: int = 5) -> SearchResult:
        """多源检索：聚合所有（或指定）provider 的结果，按 score 降序 + 去重。"""
        target = sources if sources else list(self._providers.keys())
        all_chunks: list[Chunk] = []
        sources_used: list[str] = []

        for name in target:
            provider = self._providers.get(name)
            if provider is None:
                continue
            try:
                chunks = provider.search(query, top_k)
                all_chunks.extend(chunks)
                if chunks:
                    sources_used.append(name)
            except Exception:
                continue

        # 去重：相同 content 只保留 score 最高的
        seen: dict[str, Chunk] = {}
        for c in all_chunks:
            if c.content not in seen or c.score > seen[c.content].score:
                seen[c.content] = c

        # 按 score 降序排列
        deduped = sorted(seen.values(), key=lambda c: c.score, reverse=True)
        return SearchResult(
            chunks=deduped[:top_k],
            total_found=len(deduped),
            sources_used=sources_used,
        )

    # --- 向后兼容 ---

    def index_documents(self, docs: list[dict], source: str = "vector") -> None:
        """索引文档到指定 provider。默认写入 vector provider。"""
        provider = self._providers.get(source)
        if provider:
            provider.index(docs)

    def retrieve(self, query: str, top_k: int = 5) -> dict:
        """保持旧接口兼容：仅检索 vector 源，返回旧 dict 格式。"""
        result = self.search(query, sources=["vector"], top_k=top_k)
        if not result.chunks:
            return {
                "context": "",
                "found": False,
                "citations": [],
                "confidence_level": "low",
                "source_count": 0,
                "strategy": "vector",
            }
        context = "\n".join(c.content for c in result.chunks)
        citations = [{"content": c.content, "score": c.score} for c in result.chunks]
        avg_score = sum(c.score for c in result.chunks) / len(result.chunks)
        confidence = "high" if avg_score > 2 else "medium" if avg_score > 1 else "low"
        return {
            "context": context,
            "found": True,
            "citations": citations,
            "confidence_level": confidence,
            "source_count": len(result.chunks),
            "strategy": "vector",
        }
```

- [ ] **Step 4: 运行全部 RAG 测试**

```bash
pytest tests/unit/infrastructure/test_rag.py -v
```
预期：全部通过（原有 3 个 + 新增 8 个 = 11 PASS）

- [ ] **Step 5: 提交**

```bash
git add app/infrastructure/rag/coordinator.py tests/unit/infrastructure/test_rag.py
git commit -m "feat(rag): extend RAGCoordinator for multi-provider orchestration

Task 5 of Plan A — multi-source search with dedup and score sorting.
Backward compatible: existing retrieve() API unchanged.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: RetrieverAgent — 事件驱动检索 Agent

**文件：**
- 创建：`app/agents/retriever.py`
- 创建：`tests/unit/agents/test_retriever.py`

**设计要点：**
- 继承 `AgentBase`，声明 `source/subscriptions/emittable_types`
- `handle()` 过滤 `target != retriever` → 解析 query/sources/top_k/purpose → 调 `_do_retrieve()` → 判定 `retrieval_status` → emit `RetrievedEvidence` 或 `RetrievalFailed`
- `retrieval_status` 逻辑：
  1. 检索过程抛异常 → `RetrievalFailed(status=timeout)`
  2. 结果 chunks 为空 → `RetrievedEvidence(chunks=[], status=empty)`
  3. max_score < LOW_SCORE_THRESHOLD → `RetrievedEvidence(chunks=[...], status=low_score)`
  4. 否则 → `RetrievedEvidence(chunks=[...], status=ok)`
- `LOW_SCORE_THRESHOLD = 0.3`（可配置）
- 必须通过 emittable 白名单校验（emit 未声明类型抛 ValueError）

- [ ] **Step 1: 编写 RetrieverAgent 测试**

创建 `tests/unit/agents/test_retriever.py`：

```python
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
    # 先索引一些内容
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
    # 索引内容与 query 几乎不相关
    agent._coordinator.index_documents([
        {"content": "完全不相关的内容"},
    ])
    ev = Event(type=EventType.ACTION_REQUESTED, source=EventSource.ORCHESTRATOR,
               session_id="s1", payload={"target": "retriever", "query": "深度学习注意力机制"})
    result = agent.handle(ev, ws)
    assert len(result) == 1
    assert result[0].type == EventType.RETRIEVED_EVIDENCE
    assert result[0].payload["retrieval_status"] == "low_score"


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
```

- [ ] **Step 2: 运行测试验证失败**

```bash
pytest tests/unit/agents/test_retriever.py -v
```
预期：FAIL（RetrieverAgent 未定义）

- [ ] **Step 3: 实现 RetrieverAgent**

创建 `app/agents/retriever.py`：

```python
"""Retriever Agent（§2.1）—— 知识检索，只做机械层。

事件契约：
  source      = retriever
  subscriptions = [ActionRequested]（按 payload.target==retriever 过滤）
  emittable   = {RetrievedEvidence, RetrievalFailed}

只做机械层：向量检索 + 原始 similarity score + retrieval_status。
绝不评判"证据够不够好"（语义质量归 Critic 的 RAGQualityAssessed）。
"""

import time

from app.agents.base import AgentBase
from app.harness.enums import EventType, EventSource
from app.harness.events import Event
from app.harness.workspace_state import WorkspaceState
from app.infrastructure.rag.coordinator import RAGCoordinator

LOW_SCORE_THRESHOLD = 0.3


class RetrieverAgent(AgentBase):
    """知识检索 Agent（机械层，不自评语义质量）。"""

    source = EventSource.RETRIEVER
    subscriptions = [EventType.ACTION_REQUESTED]
    emittable_types = {EventType.RETRIEVED_EVIDENCE, EventType.RETRIEVAL_FAILED}

    def __init__(self, coordinator: RAGCoordinator | None = None):
        self._coordinator = coordinator or RAGCoordinator()

    # --- AgentBase 契约 ---

    def handle(self, event: Event, ws: WorkspaceState) -> list[Event]:
        """处理 ActionRequested(target=retriever)，委托 RAGCoordinator 检索。"""
        payload = event.payload or {}

        # 过滤：只处理 target=retriever 的请求
        if payload.get("target") != EventSource.RETRIEVER.value:
            return []

        query = payload.get("query", "")
        top_k = payload.get("top_k", 5)
        sources = payload.get("sources", None)
        purpose = payload.get("purpose", None)

        try:
            return self._do_retrieve_and_emit(
                query=query, top_k=top_k, sources=sources,
                purpose=purpose, parent_id=event.id, ws=ws,
            )
        except Exception as exc:
            return [self.emit(
                EventType.RETRIEVAL_FAILED, ws,
                payload={
                    "reason": str(exc),
                    "retrieval_status": "timeout",
                    "query": query,
                },
                parent_id=event.id,
            )]

    # --- 检索 + 机械判定 ---

    def _do_retrieve_and_emit(self, *, query: str, top_k: int,
                              sources: list[str] | None, purpose: str | None,
                              parent_id: str, ws: WorkspaceState) -> list[Event]:
        """执行检索并按纯机械指标判定 retrieval_status。"""
        t0 = time.time()
        result = self._coordinator.search(query, sources=sources, top_k=top_k)
        latency_ms = (time.time() - t0) * 1000

        chunks = result.chunks
        scores = [c.score for c in chunks]
        max_score = max(scores) if scores else 0.0

        # 机械判定 retrieval_status（§3.6）
        if not chunks:
            retrieval_status = "empty"
        elif max_score < LOW_SCORE_THRESHOLD:
            retrieval_status = "low_score"
        else:
            retrieval_status = "ok"

        payload = {
            "chunks": [{"content": c.content, "score": c.score,
                        "source": c.source, "metadata": c.metadata}
                       for c in chunks],
            "scores": scores,
            "retrieval_status": retrieval_status,
            "sources_used": result.sources_used,
            "query": query,
            "latency_ms": latency_ms,
        }
        if purpose:
            payload["purpose"] = purpose

        return [self.emit(EventType.RETRIEVED_EVIDENCE, ws,
                          payload=payload, parent_id=parent_id)]
```

- [ ] **Step 4: 运行测试验证通过**

```bash
pytest tests/unit/agents/test_retriever.py -v
```
预期：13 PASS（除 `test_evaluate_raises_not_implemented_before_task7` 外全部通过）

- [ ] **Step 5: 提交**

```bash
git add app/agents/retriever.py tests/unit/agents/test_retriever.py
git commit -m "feat(agent): add RetrieverAgent with mechanical-only retrieval

Task 6 of Plan A — event-driven agent that subscribes to
ActionRequested(target=retriever), delegates to RAGCoordinator,
and emits RetrievedEvidence/RetrievalFailed with mechanical
retrieval_status only (no semantic quality judgment).

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 7: evaluate() — RAG 三件套 + recall@k

**文件：**
- 修改：`app/agents/retriever.py`（实现 evaluate 方法）
- 修改：`tests/unit/agents/test_retriever.py`（追加 evaluate 测试）

**设计要点：**
- `evaluate(test_case) -> dict` 返回 spec §5.2 的 6 个指标
- 初期用启发式/规则实现（不依赖 ragas/LLM-judge）
- recall@k：golden_chunks 中有多少出现在检索结果中
- context_precision：检索结果中相关 chunk 占比
- answer_relevancy：检索结果与 query 的词重叠率
- faithfulness：检索结果与 golden_answer 的词重叠率
- latency_ms：time.time() 差值
- redundancy：检索结果中相似 chunk 对占比

- [ ] **Step 1: 编写 evaluate 测试**

在 `tests/unit/agents/test_retriever.py` 末尾追加：

```python
# --- evaluate 测试（Task 7）---

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
        "query": "RAG",
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
        "golden_chunks": ["检索增强生成"],
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
    # 3 个结果中 2 个相关 -> 0.666...
    assert 0.5 < metrics["context_precision"] < 0.8


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
        {"content": "内容 A"},
        {"content": "内容 B"},
        {"content": "内容 C"},
    ])
    metrics = agent.evaluate({
        "query": "内容",
        "golden_chunks": [],
        "golden_answer": "",
        "top_k": 3,
    })
    assert metrics["redundancy"] == 0.0


def test_evaluate_redundancy_detects_duplicates():
    """有重复/高度相似内容时 redundancy > 0"""
    agent = RetrieverAgent()
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
```

- [ ] **Step 2: 运行测试验证失败**

```bash
pytest tests/unit/agents/test_retriever.py::test_evaluate_returns_all_metrics -v
```
预期：FAIL（evaluate 仍抛 NotImplementedError）

- [ ] **Step 3: 实现 evaluate() 方法**

在 `app/agents/retriever.py` 的 `RetrieverAgent` 类中，将 `evaluate` 方法替换为：

```python
    def evaluate(self, test_case: dict) -> dict:
        """部件级评估接口（§5.2 RAG 三件套 + recall@k）。

        test_case 结构：
          - query: str             检索查询
          - golden_chunks: list[str] 人工标注的相关 chunk 内容
          - golden_answer: str      期望答案（用于 faithfulness）
          - top_k: int              检索数量（默认 5）

        返回 6 个指标（初期启发式，后续可替换 ragas）。
        """
        query = test_case.get("query", "")
        golden_chunks = test_case.get("golden_chunks", [])
        golden_answer = test_case.get("golden_answer", "")
        top_k = test_case.get("top_k", 5)

        # 执行检索
        t0 = time.time()
        result = self._coordinator.search(query, sources=None, top_k=top_k)
        latency_ms = (time.time() - t0) * 1000

        retrieved_contents = [c.content for c in result.chunks]
        combined = " ".join(retrieved_contents)

        # --- recall@k：golden_chunks 中有多少被检索到 ---
        if golden_chunks:
            hit = sum(1 for g in golden_chunks
                      if any(g in rc or rc in g for rc in retrieved_contents))
            recall_at_k = hit / len(golden_chunks)
        else:
            recall_at_k = 1.0  # 无 golden_chunks 时无法评估，返回满分

        # --- context_precision：检索结果中与 golden_chunks 相关的比例 ---
        if retrieved_contents and golden_chunks:
            relevant = sum(1 for rc in retrieved_contents
                           if any(g in rc or rc in g for g in golden_chunks))
            context_precision = relevant / len(retrieved_contents)
        elif retrieved_contents:
            # 无 golden_chunks：用 query 词重叠作为弱代理
            query_tokens = set(query)
            relevant = sum(1 for rc in retrieved_contents
                           if any(t in rc for t in query_tokens))
            context_precision = relevant / len(retrieved_contents)
        else:
            context_precision = 0.0

        # --- faithfulness：检索内容与 golden_answer 的词重叠率（Jaccard）---
        if golden_answer and combined:
            answer_tokens = set(golden_answer)
            retrieved_tokens = set(combined)
            intersection = answer_tokens & retrieved_tokens
            union = answer_tokens | retrieved_tokens
            faithfulness = len(intersection) / len(union) if union else 0.0
        elif combined and query:
            # 无 golden_answer：用 query 词重叠
            query_tokens = set(query)
            retrieved_tokens = set(combined)
            intersection = query_tokens & retrieved_tokens
            union = query_tokens | retrieved_tokens
            faithfulness = len(intersection) / len(union) if union else 0.0
        else:
            faithfulness = 0.0

        # --- answer_relevancy：检索内容与 query 的词重叠率（Jaccard）---
        if combined and query:
            query_tokens = set(query)
            retrieved_tokens = set(combined)
            intersection = query_tokens & retrieved_tokens
            union = query_tokens | retrieved_tokens
            answer_relevancy = len(intersection) / len(union) if union else 0.0
        else:
            answer_relevancy = 0.0

        # --- redundancy：检索结果中高度相似 chunk 对的比例 ---
        n = len(retrieved_contents)
        if n >= 2:
            similar_pairs = 0
            for i in range(n):
                for j in range(i + 1, n):
                    # 简单 Jaccard 相似度 > 0.8
                    ti = set(retrieved_contents[i])
                    tj = set(retrieved_contents[j])
                    inter = len(ti & tj)
                    union = len(ti | tj)
                    if union > 0 and inter / union > 0.8:
                        similar_pairs += 1
            total_pairs = n * (n - 1) / 2
            redundancy = similar_pairs / total_pairs if total_pairs > 0 else 0.0
        else:
            redundancy = 0.0

        return {
            "faithfulness": round(faithfulness, 4),
            "answer_relevancy": round(answer_relevancy, 4),
            "context_precision": round(context_precision, 4),
            "recall_at_k": round(recall_at_k, 4),
            "latency_ms": round(latency_ms, 2),
            "redundancy": round(redundancy, 4),
        }
```

- [ ] **Step 4: 运行全部 Retriever 测试**

```bash
pytest tests/unit/agents/test_retriever.py -v
```
预期：21 PASS（原 13 个 + 新增 8 个 evaluate 测试）

- [ ] **Step 5: 提交**

```bash
git add app/agents/retriever.py tests/unit/agents/test_retriever.py
git commit -m "feat(agent): implement RetrieverAgent.evaluate() with RAG metrics

Task 7 of Plan A — heuristic recall@k, context_precision, faithfulness,
answer_relevancy, latency_ms, and redundancy. No external dependencies
(ragas/LLM-judge can replace later per §5.ia2).

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 8: 集成测试 — 协作环 + OCR/代码场景

**文件：**
- 创建：`tests/integration/test_retriever_integration.py`

**设计要点：**
- 验证 RetrieverAgent 在 EventBus + 协作环中完整工作
- 验证 OCR/代码索引内容可检索（spec §9 场景）
- 验证 `retrieval_status` 各状态正确触发
- 不影响老代码测试基线

- [ ] **Step 1: 编写集成测试**

创建 `tests/integration/test_retriever_integration.py`：

```python
"""Plan A 集成测试：Retriever + RAG 基础设施在协作环中端到端工作。"""

import pytest
from app.agents.retriever import RetrieverAgent
from app.harness.enums import EventType, EventSource
from app.harness.events import Event
from app.harness.eventbus import EventBus
from app.harness.workspace_state import WorkspaceState
from app.orchestration.collab_loop import run_collab_loop
from app.infrastructure.rag.ocr import OCRProvider
from app.infrastructure.rag.code_index import CodeIndexProvider


# ── spec §9 场景 1：OCR 内容可检索 ──

def test_ocr_content_retrievable_in_collab_loop():
    """OCR 索引的图片文本应可被 RetrieverAgent 检索到。"""
    ws = WorkspaceState(session_id="s1", user_id="u1")
    bus = EventBus()

    retriever = RetrieverAgent()
    # 注册 OCR provider
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

    result_ws = run_collab_loop(bus, ws, [seed], max_turns=10)

    # 协作环产出了 RetrievedEvidence
    ev_ids = result_ws.event_ids
    events = bus.replay("s1")
    retrieved = [e for e in events if e.type == EventType.RETRIEVED_EVIDENCE]
    assert len(retrieved) >= 1
    assert "attention" in retrieved[0].payload["query"].lower() or \
           any("注意力" in c["content"] for c in retrieved[0].payload.get("chunks", []))


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
    bus = EventBus()

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
    bus = EventBus()

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
    bus = EventBus()

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
    code.index_file("/repo/lora.py", """
def lora_forward(x, A, B, alpha):
    '''LoRA forward pass: h = Wx + alpha * BAx'''
    return x + alpha * (x @ A @ B)
""")
    retriever._coordinator.register_provider(code)

    result = retriever._coordinator.search("LoRA", sources=None, top_k=10)
    assert result.total_found >= 2
    assert len(result.sources_used) >= 2
```

- [ ] **Step 2: 运行集成测试验证失败（部分场景需 Task 6 完成后方可运行）**

```bash
pytest tests/integration/test_retriever_integration.py -v
```
预期：全部 PASS（9 PASS）

- [ ] **Step 3: 运行全量测试确认基线不受影响**

```bash
pytest tests/ -q --tb=short
```
预期：所有已有测试 + Plan A 新增测试全部通过

- [ ] **Step 4: 提交**

```bash
git add tests/integration/test_retriever_integration.py
git commit -m "test(integration): add Retriever end-to-end tests in collab loop

Task 8 of Plan A — verifies OCR/code index searchability (spec §9),
retrieval_status states, multi-source aggregation, and evaluate() output.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## 4. 验收判据

| 判据 | 验证方式 |
|---|---|
| Retriever 单测全绿（21 个测试） | `pytest tests/unit/agents/test_retriever.py -v` |
| RAG 基础设施测试全绿（28 个测试） | `pytest tests/unit/infrastructure/test_rag.py tests/unit/infrastructure/test_ocr.py tests/unit/infrastructure/test_code_index.py tests/unit/infrastructure/test_extractors.py -v` |
| 集成测试全绿（9 个测试） | `pytest tests/integration/test_retriever_integration.py -v` |
| spec §9 OCR 内容可检索 | `test_ocr_content_retrievable_in_collab_loop` |
| spec §9 代码索引可检索 | `test_code_index_content_retrievable` |
| retrieve() 向后兼容 | `test_rag_coordinator_retrieve_backward_compat` |
| evaluate() 可跑 | `test_evaluate_produces_valid_metrics` |
| 越权拦截生效 | `test_retriever_cannot_emit_non_owned_event` |
| EventBus 白名单合规 | `test_retriever_emitted_event_passes_bus_ownership` |
| 老代码基线不减 | `pytest tests/ -q` 全绿（含 ~155 已有测试） |

---

## 5. 文件变更汇总

| 文件 | 操作 | Task |
|---|---|---|
| `app/infrastructure/rag/coordinator.py` | 修改（顶部加数据类/协议，RAGCoordinator 类扩展多 Provider） | 1, 5 |
| `app/infrastructure/rag/ocr.py` | 创建 | 2 |
| `app/infrastructure/rag/code_index.py` | 创建 | 3 |
| `app/infrastructure/rag/extractors/__init__.py` | 创建 | 4 |
| `app/infrastructure/rag/extractors/base.py` | 创建 | 4 |
| `app/infrastructure/rag/extractors/text_extractor.py` | 创建 | 4 |
| `app/infrastructure/rag/extractors/pdf_extractor.py` | 创建 | 4 |
| `app/infrastructure/rag/extractors/docx_extractor.py` | 创建 | 4 |
| `app/agents/retriever.py` | 创建 | 6, 7 |
| `tests/unit/infrastructure/test_rag.py` | 修改（追加测试） | 1, 5 |
| `tests/unit/infrastructure/test_ocr.py` | 创建 | 2 |
| `tests/unit/infrastructure/test_code_index.py` | 创建 | 3 |
| `tests/unit/infrastructure/test_extractors.py` | 创建 | 4 |
| `tests/unit/agents/test_retriever.py` | 创建 | 6, 7 |
| `tests/integration/test_retriever_integration.py` | 创建 | 8 |

**不碰的文件**（硬约束）：
- `app/agents/base.py` — Plan 0 冻结接口
- `app/harness/events.py`、`enums.py`、`workspace_state.py`、`eventbus.py` — Plan 0 冻结
- `app/orchestration/collab_loop.py`、`graph.py` — Plan 0 冻结
- `app/agent/` — 老代码只读
- `app/infrastructure/external/ocr.py` — 只读参考
- `app/infrastructure/extraction/file_extract.py` — 只读参考
- `app/infrastructure/rag/store.py` — 复用不改

---

## 6. 预估工作量

| Task | 内容 | 估时 |
|---|---|---|
| Task 1 | IndexProvider 协议 + 数据结构 | 15min |
| Task 2 | OCRProvider | 20min |
| Task 3 | CodeIndexProvider | 25min |
| Task 4 | extractors/ | 20min |
| Task 5 | RAGCoordinator 扩展 | 30min |
| Task 6 | RetrieverAgent | 25min |
| Task 7 | evaluate() | 20min |
| Task 8 | 集成测试 | 20min |
| **合计** | | **~3h** |