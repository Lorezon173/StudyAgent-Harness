# 项目级 ChunkingService Spec（Gate 0）

> 创建日期：2026-07-24  
> 状态：⏳ 待用户确认  
> 目标阶段：RAG Gate 0（先打通无图教材摄入/切块/索引闭环）  
> 相关上游：`docs/designs/2026-07-03-phase-b1-lightrag-dual-retrieval-spec.md`、`docs/designs/2026-07-03-phase-b3-pdf-layout-parsing-spec.md`  
> 相关复审：`docs/spec-modify/modify-2026-07-03-phase-b1-lightrag-dual-retrieval-spec.md`

---

## 0. 资产清单

| 三色 | 名字 | 归属子系统 | 功能（干嘛） | 触发 / 入口 | 位置 |
|---|---|---|---|---|---|
| 🟢 | `RAGCoordinator.index_documents` | Infrastructure / RAG | 接收 `list[dict]` docs 并转交指定 provider，当前不做切块/校验 | 摄入编排显式调用 | `app/infrastructure/rag/coordinator.py:135-139` |
| 🟢 | `PgVectorProvider.index/search` | Infrastructure / RAG | 向量写入 `vector_chunks`，查询返回 `Chunk` | `RAGCoordinator` 默认 vector provider | `app/infrastructure/rag/pgvector_provider.py:60-180` |
| 🟢 | `Chunk` / `SearchResult` | Infrastructure / RAG 协议 | 定义检索结果最小证据单元与聚合返回 | `RAGCoordinator.search()` | `app/infrastructure/rag/coordinator.py:7-21` |
| 🟢 | `Extractor` / `get_extractor` | Infrastructure / Extractors | 现有文件提取协议与工厂；只返回纯文本 `str` | 文件解析调用方 | `app/infrastructure/rag/extractors/base.py:7-28` |
| 🟢 | `TextExtractor` / `PDFExtractor` / `DocxExtractor` | Infrastructure / Extractors | `.txt/.md/.csv`、`.pdf`、`.docx` 文本提取；失败降级为空串 | `get_extractor` | `app/infrastructure/rag/extractors/text_extractor.py:6-14`、`pdf_extractor.py:6-27`、`docx_extractor.py:6-18` |
| 🟢 | `OCRProvider.index_image` | Infrastructure / OCR | 项目内唯一已落地的“提取→按段落分块→索引”闭环 | OCR 调用方 | `app/infrastructure/rag/ocr.py:44-55` |
| 🟢 | `RetrieverAgent.handle/evaluate` | Harness / Agent | 在线检索上行 `RetrievedEvidence`；离线 eval 用 `golden_chunks` 文本比对 | 协作事件 / tests | `app/agents/retriever.py:36-265` |
| 🟢 | `/api/knowledge` | API | 当前仅知识条目的内存 CRUD，不是文件上传/摄入入口 | FastAPI 路由 | `app/api/knowledge.py:1-28` |
| 🟢 | `VectorChunkTable` | Models / Persistence | 持久化 content / embedding / source / doc_id / metadata_json / scope / user_id | `PgVectorProvider` 写入 | `app/models/tables.py:92-111` |
| 🟡 | `ChunkingService` | Harness | 拟议的新纯服务：把线性/结构化元素转成可索引 docs | 由摄入编排调用 | `app/harness/chunking_service.py`（待建） |
| 🟡 | `KnowledgeIngestionService` | Harness / Orchestration 边界 | 拟议的新摄入编排：extract/normalize/chunk/index | API 或脚本调用 | `app/harness/knowledge_ingestion.py`（待建） |
| 🟡 | `EpubExtractor` | Infrastructure / Extractors | 拟议的新 EPUB 提取器；当前尚不存在 | `get_extractor` 或专用摄入入口 | `app/infrastructure/rag/extractors/epub_extractor.py`（待建） |
| 🟡 | `LayoutPDFExtractor` / `LayoutElement` | Infrastructure / PDF layout | B-③ 规划中的结构化 PDF 提取器与元素模型；当前尚未实现 | PDF 结构化摄入 | 见 B-③ spec，不是当前代码事实 |

---

## 1. 第一层：模块总览

### 1.1 目标边界

**本 spec 要做什么**：

建立项目级正式 ChunkingService，使文档摄入从“原始文件/纯文本”进入统一的：

```text
extract / adapt
→ normalize
→ chunk
→ docs[{content, metadata, doc_id, source, scope, user_id}]
→ RAGCoordinator.index_documents(..., source="vector")
```

目标是让 chunk 成为项目 RAG 的正式能力，而不是为某一本书、某个 benchmark、或某个临时脚本单独发明一套数据形状。

**本阶段明确要守住的约束**：

1. 不另造检索器；最终写入仍走 `RAGCoordinator.index_documents`。见 `app/infrastructure/rag/coordinator.py:135-139`。
2. 不把 benchmark 的 `paragraph_id` 升格为项目主键。
3. 不把 `/api/knowledge` 误写成现成上传入口；当前它只是 name/description CRUD。见 `app/api/knowledge.py:1-28`。
4. 不把 B-③ PDF layout spec 的待实现接口说成当前代码事实。
5. 不把“离线索引可用”夸写成“在线教学已吃到检索结果”；当前默认教学链并不会自动产生非空 retriever query。见 `app/orchestration/assembly.py:144-156`、`app/harness/orchestrator.py:149-163`、`app/agents/retriever.py:44-47`。

### 1.2 本阶段明确不做

- ❌ 不引入新的 graph provider、LightRAG 库或第二个检索器
- ❌ 不把用户隔离 / scope 过滤 / 文档删除 / 幂等重建偷渡成“默认已有能力”
- ❌ 不把 EPUB 宣称为“当前已支持格式”——当前 factory 没有 `.epub`
- ❌ 不在本 spec 锁定 PDF 结构化解析库（B-③ 明确要求先 spike）
- ❌ 不用 FakeRAGStore 的字符匹配分数证明真实向量检索收益

### 1.2.1 Gate 0 官方入口与明确非承诺（本轮新增，待主控冻结）

**官方入口**：Gate 0 只交付可被测试夹具、离线脚本或未来 API 薄壳调用的 `KnowledgeIngestionService` 服务边界；本阶段**不**新建文件上传 API，也不扩展现有 `/api/knowledge`。上传、鉴权、临时文件、尺寸限制、清理与审计是独立 API 安全设计任务。

**append-only 非承诺**：现有 `PgVectorProvider.index()` 对每个 doc 直接 INSERT，尚无 delete/replace/upsert 或 `doc_id/chunk_id` 唯一约束。见 `app/infrastructure/rag/pgvector_provider.py:85-109`。因此 Gate 0：

- 不保证同一文档重复导入幂等；
- 不保证重导自动替换旧 chunk；
- 不提供按文档删除、撤回或版本替换；
- 不把 `doc_count` 解释为逻辑文档数（当前是 chunk 行数）。

若以后需要上述任一能力，必须另行扩展 provider 生命周期契约、数据库约束/索引和 Alembic migration，不能仅依赖稳定 ID 或 metadata。

### 1.3 为什么先做 Gate 0，而不是先做图

| | 本方案（先做 Gate 0 Chunking） | 备选（先做 B-① 图检索） |
|---|---|---|
| 做法 | 先打通代表教材的提取/切块/索引/召回闭环 | 先实现图抽取、图存储、双层检索 |
| 收益 | 直接补当前最缺的生产摄入链路；给后续图能力提供稳定 chunk 基座 | 能更早探索图是否提升跨章节/多跳问题 |
| 代价 | 仍需新增摄入编排、chunk schema、测试样本 | 在当前无正式教材摄入、在线 query 断路前，图无法抵达用户价值 |
| 风险 | 需要严格限制 scope，不把“离线闭环”夸成“教学闭环” | 容易形成“图建好了但生产路径根本不用”的孤岛 |

**选择理由**：

B-① 的 review 已明确要求先过“无图 Gate 0”。见 `docs/spec-modify/modify-2026-07-03-phase-b1-lightrag-dual-retrieval-spec.md:220-251`。当前生产路径没有上传→提取→切块→`index_documents`，在线协作默认也不给 Retriever 非空 query，因此图能力不是当前最短板。

### 1.4 分层归属（遵守四层单向依赖）

```text
API 层 (app/api/)
  只接收请求 / 做认证 / 委托摄入编排

→ 编排层 / Harness 边界 (app/harness/, app/orchestration/)
  KnowledgeIngestionService: 读输入 → 调 extractor/adapter → 调 ChunkingService → 调 RAGCoordinator.index_documents → 返回结果

→ Harness 纯服务 (app/harness/)
  ChunkingService: 纯切块与 metadata 组装，不做 IO / 不写库 / 不调 API

→ Infrastructure 层 (app/infrastructure/)
  Extractor / PgVectorProvider / FakeRAGStore / EmbeddingService
```

**分层决定**：

- `ChunkingService` 放在 Harness 层，作为纯业务规则服务。
- `KnowledgeIngestionService` 负责 I/O 编排，属于 Harness/Orchestration 边界的薄壳。
- Extractor、Provider、Store 继续留在 Infrastructure。
- API 只调摄入编排，不直接写 chunk 逻辑。

### 1.5 当前事实约束（只写已核实内容）

1. Extractor 当前统一契约是 `extract(file_path: str) -> str`，失败降级 `""`。见 `app/infrastructure/rag/extractors/base.py:7-28`。
2. `PgVectorProvider.index` 当前实际消费字段为 `content`、`metadata`、`doc_id`、`source`、`scope`、`user_id`。见 `app/infrastructure/rag/pgvector_provider.py:77-83`。
3. `PgVectorProvider.search` 会读出 `doc_id`，但当前没放回返回 `Chunk`。见 `app/infrastructure/rag/pgvector_provider.py:137-156`。
4. `RAGCoordinator.search(..., sources=None)` 会搜索所有已注册 provider，不是只搜 vector。见 `app/infrastructure/rag/coordinator.py:100-131`。
5. `VectorChunkTable` 当前 embedding 维度是 2048，不是 README 中写的 1536。见 `app/models/tables.py:92-111` 与迁移 `alembic/versions/20260622_add_vector_chunks_table.py:21-69`。

---

## 2. 第二层：子模块概述

### 2.1 ChunkDocument 逻辑契约（先于实现）

**职责**：定义项目级 chunk 输出的最小公共形状，虽然底层 `IndexProvider.index` 仍接受 `list[dict]`。

**接口契约**：

```python
{
  "content": str,
  "doc_id": str,
  "source": "vector",
  "scope": str,
  "user_id": int | None,
  "metadata": {
    "doc_id": str,
    "chunk_id": str,
    "chunk_index": int,
    "chunking_spec_version": str,
    "source_format": str,
    "source_locator": dict,
    ... optional provenance ...
  }
}
```

**关键设计点**：

- `doc_id` 与 `chunk_id` 分层定义，均不能来自 benchmark paragraph_id。
- `metadata_json` 已足够承载 provenance；只有当字段需要数据库级查询/删除/唯一约束时，才扩 schema。
- `content` 为空或纯空白的 chunk 禁止输出。

### 2.2 NormalizedElement / LinearElement 适配层

**职责**：在不改现有 Extractor 签名的前提下，把 TXT/PDF/DOCX/未来 EPUB 的输出统一成 chunking 可消费的线性/结构化元素序列。

**接口契约**：
- 纯文本 extractor 输出 `str` 时，由 adapter 转成线性元素序列。
- 未来结构化 extractor（如 `extract_structured`) 输出结构化元素时，可直接传给 ChunkingService。

**数据流**：
- 上游：`TextExtractor` / `PDFExtractor` / `DocxExtractor` / 未来 `EpubExtractor` / 未来 `LayoutPDFExtractor`
- 下游：`ChunkingService`

**错误处理**：
- extractor 返回 `""` → 视为无可索引内容
- 结构化 extractor 缺依赖或解析失败 → 可回退到纯文本 extractor，但必须在 metadata 标示 fallback

### 2.3 ChunkingService（纯服务）

**职责**：
把线性/结构化元素切成可索引 docs，并产出稳定 metadata。

**接口契约**：
`chunk(elements, context, policy) -> list[dict]`

> 本 spec 先固定职责与输出，不在文字层钉死最终函数签名细节；避免“散文手抄代码”。

**数据流**：
- 上游：`KnowledgeIngestionService`
- 下游：返回 `list[dict]` 给编排层

**状态管理**：
- 无状态纯服务

**错误处理**：
- 空 elements → 空列表
- 单元素不可切块 → 跳过并记录 warning
- JSON 不可序列化 metadata → 在编排层 fail fast，不让脏数据进入 provider

### 2.4 KnowledgeIngestionService（摄入编排）

**职责**：
把“提取/适配/切块/索引”串起来，但自己不承载 chunk 业务规则。

**接口契约**：
- 接收输入来源（文件路径、导入上下文、scope/user_id 等）
- 调 extractor / adapter / chunker
- 调 `RAGCoordinator.index_documents(docs, source="vector")`
- 返回 `IngestResult`

**数据流**：
```text
入口参数
→ 选择 extractor
→ 抽取文本或结构元素
→ 适配成 elements
→ ChunkingService
→ docs
→ RAGCoordinator.index_documents
→ IngestResult
```

**状态管理**：
- 本身无持久状态
- 不维护索引生命周期；除非后续 provider 增加 replace/delete 契约

**错误处理**：
- extractor 不支持该格式 → 明确 unsupported
- 提取结果为空 → 返回可观察失败/警告
- provider 写入异常 → 返回失败，不吞异常事实

### 2.5 Extractor 迁移策略

| | 本方案（保持旧签名 + 增量扩展） | 备选（直接把 Extractor 改为结构化返回） |
|---|---|---|
| 做法 | 保持 `extract(file_path)->str`，新增 adapter / 可选 `extract_structured` | 直接把抽象基类统一改成结构化输出 |
| 收益 | 向后兼容现有测试、调用者与回退逻辑 | 类型上更统一 |
| 代价 | 需要多一个适配层 | 会破坏现有 extractor 契约与测试 |

**选择理由**：
当前 Extractor 事实契约已稳定，且 B-③ 也要求 `LayoutPDFExtractor` 兼容现有 `extract()->str`。因此先走“旧签名不动 + 新能力增量扩展”。

### 2.6 EPUB 支持边界

**事实**：当前没有 `.epub` extractor。不能把 EPUB 写成“已经统一支持”。

**本 spec 决策**：
- EPUB 是本模块目标格式之一，但属于**新增能力**。
- 在没有 `EpubExtractor` 前，摄入层必须返回明确 unsupported，而不是静默返回空结果。
- `EpubExtractor` 若落地，也必须兼容现有 extractor 工厂风格。

### 2.7 Provider / Schema 改动边界

**当前已知事实**：
- `PgVectorProvider.search` 不返回独立 `doc_id`
- search 没有 `scope/user_id` 查询过滤
- index 是 append-only，无 delete/replace/upsert

**本 spec 决策**：
1. 若只做 Gate 0 离线索引/召回：
   - 可先不改 `vector_chunks` schema
   - 但必须补“检索返回 metadata 带回 doc_id/chunk_id”的契约
2. 若宣称幂等重建 / 按文档删除 / 用户隔离：
   - 必须同步新增 provider 方法、SQL WHERE / DELETE / 事务语义、索引或唯一约束、Alembic migration
   - 不能只在 ChunkingService 内部约定

### 2.8 测试边界

**可复用现有测试骨架**：
- `tests/unit/infrastructure/test_rag.py`
- `tests/unit/infrastructure/test_pgvector_provider.py`
- `tests/integration/test_pgvector_real.py`
- `tests/unit/agents/test_retriever.py`
- `tests/integration/test_retriever_integration.py`

**必须新增的核心测试类别**：
- ChunkingService 纯函数单测
- 纯文本 adapter 单测
- EPUB supported/unsupported 测试
- provider round-trip metadata 测试
- Gate 0 摄入编排测试

---

## 3. 第三层：子模块详细实施计划（文字设计）

> 说明：本层保持“文字设计”形态，不手抄最终代码签名/行号；涉及已核实事实时才引用 `file:line`。

### 3.1 ChunkDocument / metadata 设计

#### 3.1.1 需要确定的字段

**顶层字段**：
- `content`
- `doc_id`
- `source`
- `scope`
- `user_id`
- `metadata`

**metadata 必填字段**：
- `doc_id`
- `chunk_id`
- `chunk_index`
- `chunking_spec_version`
- `source_format`
- `source_locator`

**metadata 推荐字段**：
- `file_path` 或安全的导入标识
- `page_num` / `page_range`
- `section_path`
- `element_types`
- `extraction_mode`
- `external_locators`（只放 benchmark / 外部数据集标签）

#### 3.1.2 doc_id 与 chunk_id 规范化生成规则（range 基线已冻结 DEC-006；hash framing / normalization / 测试向量待 RAG-B 补证）

**术语**：

- `import_namespace`：调用方显式给出的稳定导入域（例如知识库逻辑 ID 或受控的离线语料 ID）；不得默认为临时路径。
- `normalized_document_text`：按当前 normalizer 版本完成 Unicode 规范化、换行规范化、首尾空白处理后的全文。
- `canonical_element_range`：该 chunk 在标准化元素流中的范围。**坐标基线已冻结（DEC-006）**：element 序号 0-based、element 内 offset 按 Unicode code point 计数、区间为半开 `[start, end)`；至少由首/末元素顺序号与该元素内的字符偏移组成。格式特有的 `source_locator`（章节/页码/spine/路径等）只进入 metadata 审计，不参与 chunk 身份。Unicode normalization form、换行/空白归一化顺序与 hash framing 仍待 RAG-B 补证。
- `canonical_chunk_text`：应用当前 normalizer 后的本 chunk 内容；仅用于 hash 输入，不改变最终 `content` 展示语义。

**生成规则**：

```text
doc_id = sha256("doc-v1" + import_namespace + normalizer_version + normalized_document_text)

chunk_id = sha256(
  "chunk-v1" + doc_id + chunking_spec_version
  + canonical_element_range + canonical_chunk_text
)
```

实现时应使用确定的字段序列化方式（固定字段名、固定顺序、UTF-8），避免 dict 顺序或平台换行导致 hash 漂移。

**禁止项**：

- 不允许把文件路径、临时上传 UUID、数据库自增 `vector_chunks.id` 直接作为稳定 `doc_id`；文件路径只可作为 provenance。
- 不允许只用 `chunk_index` 作为唯一 `chunk_id`；它只用于顺序展示与调试。
- 不允许把 benchmark 的 `paragraph_id` 进入 `doc_id` 或 `chunk_id` 的 hash 输入；它只可进入 `metadata.external_locators`。

#### 3.1.3 稳定性与版本规则

同一 `import_namespace`、同一 `normalizer_version`、相同输入全文、相同元素顺序、相同 `chunking_spec_version`：
- 必须生成字节等价的 chunk 序列；
- 必须生成相同的 `doc_id/chunk_id`。

任一项变化：
- `import_namespace`；
- 文档内容；
- normalizer 规则或版本；
- 结构元素顺序/范围；
- chunk 规则或 `chunking_spec_version`；

都必须在相应 ID 中反映。`chunk_index` 可因规则变化而变化，但不是身份来源。

### 3.2 线性/结构化元素适配

#### 3.2.1 纯文本路径

TXT / 当前 PDF / 当前 DOCX 走纯文本路径时：
- 先形成线性元素序列
- 元素至少保留：文本内容、顺序索引、源格式、可能的 locator（如纯文本通常没有页码）
- PDF 纯文本回退时必须标记 `extraction_mode='plain_text_fallback'`

#### 3.2.2 结构化路径

若未来有 `LayoutPDFExtractor.extract_structured()` 或 `EpubExtractor` 的章节/段落输出：
- 直接输入结构化元素
- ChunkingService 依据元素类型决定切块规则
- 不在本 spec 锁定解析库，只锁定“元素 → chunk”的消费契约

### 3.3 ChunkingService 规则

#### 3.3.1 分块主策略

采用：**段落/元素优先，长度兜底，结构只做增强**。

即：
1. 先按输入元素边界处理
2. 对超长文本元素做二次切分
3. 对过短碎片按同一局部上下文合并
4. 表格/公式等原子元素不切裂

#### 3.3.2 长度单位

本 spec 要统一成一种明确单位；推荐先使用**Unicode 字符数**，因为：
- 当前项目没有既定 tokenizer 抽象
- 纯文本 extractor 路径最容易稳定复现
- 测试更简单直接

若未来改成 token，必须：
- 固定 tokenizer/model 版本
- 升级 `chunking_spec_version`

#### 3.3.3 切分规则

- 文本优先在句边界或空白边界切
- 找不到可用边界时允许硬切
- 每个 chunk 保留来源顺序
- overlap 只用于长文本二切，不应制造大量重复原子元素
- 第一版长度单位统一为 **Unicode 字符数**；相关阈值必须与 `chunking_spec_version` 绑定
- 单个文本元素若超过单 chunk 上限，必须进入二次切分；二次切分后仍超过实现方为 embedding 安全阈值设定的 hard limit 时，摄入编排必须返回 warning 或失败，不允许静默写入超长 chunk

#### 3.3.4 原子元素规则

- 表格：整块保留
- 公式：整块保留
- figure/caption：是否合并由结构化路径决定；若无结构化能力则不伪造
- header/footer/page_number：只有在结构化提取明确标出时才可丢弃；纯文本回退不能假装识别出来了

### 3.4 KnowledgeIngestionService 编排

#### 3.4.1 需要的职责步骤

1. 解析输入上下文（文件路径、用户、scope、来源）
2. 选择 extractor
3. 执行提取
4. 将输出适配为元素序列
5. 调用 ChunkingService
6. 将 chunk docs 补齐顶层 provenance
7. 调 `RAGCoordinator.index_documents(docs, source='vector')`
8. 返回 `IngestResult`

#### 3.4.2 不该做的事

- 不在此处直接写 SQL
- 不直接实例化 `PgVectorProvider` 做旁路写入
- 不在编排层实现 chunk 业务规则
- 不偷偷做“重复导入去重承诺”，除非 provider 契约已扩展

### 3.5 Provider provenance 回传与权威来源（本轮新增，待主控冻结）

写入前，摄入编排必须保证顶层 `doc_id` 与 `metadata.doc_id` 字节相等，并保证 `metadata.chunk_id` 非空；不满足时 fail fast，不调用 `index_documents`。

`PgVectorProvider.search` 的数据库顶层 `doc_id` 是**检索回传的权威来源**：

1. provider 从 SQL 行读取 `doc_id` 后，必须覆盖/补齐返回 `Chunk.metadata["doc_id"]`；
2. `metadata_json["doc_id"]` 若存在但与 SQL 顶层值不同，属于写入契约损坏：实现应拒绝该写入，或在读取时以顶层列覆盖并记录可观察错误；Gate 0 推荐在写入前拒绝；
3. `chunk_id` 只来自 metadata，但写入前必须存在，读取后必须原样保留；
4. Fake、SQLite fallback、PostgreSQL 的**相关性排序可不同**，但 `content/source/doc_id/chunk_id/source_locator` 的回传面、空 query 行为、unsupported 行为必须一致。

因此，Gate 0 的最小 provider 改动不是新检索器或新表，而是补齐现有查询结果的 provenance 归一化。`RAGCoordinator.search` 仍是唯一统一检索入口；旧 `retrieve()` 仍会丢 citation metadata，不能作为证据回溯或评测对齐边界。

### 3.6 EPUB 增量实施策略

| | 本阶段立即支持 EPUB | 本阶段先明确 unsupported，后续补 EpubExtractor |
|---|---|---|
| 收益 | 满足“统一 EPUB/PDF/TXT/DOCX”目标更完整 | 降低当前 spec 虚假完备风险 |
| 代价 | 需要新增 extractor 与章节/段落语义适配 | 短期目标不完整 |

**推荐**：若这轮是“spec 细化，不立即编码”，先把 EPUB 作为明确子模块写进 spec；实施时若没有同时交付 `EpubExtractor`，则 Gate 0 验收里必须把 EPUB 标成未完成而非假完成。

### 3.7 Gate 0 验收路径

#### 3.7.1 Happy-path 验收

至少一份：
- TXT
- DOCX
- PDF（可接受纯文本 fallback）

经过：
- 提取
- 适配
- 切块
- `index_documents`
- 检索 round-trip

后，能召回带 provenance 的 chunk。

#### 3.7.2 降级路径验收

必须覆盖：
- extractor 不支持格式
- extractor 缺依赖
- extractor 返回空文本
- metadata 不可序列化
- 顶层 `doc_id` 与 `metadata.doc_id` 不一致
- `metadata.chunk_id` 缺失
- 空 query 检索
- Fake/SQLite/PG 三种环境的相关性排序允许不同，但 provenance 回传面必须一致
- append-only 重复导入：明确断言会追加，而不是假装幂等

#### 3.7.3 在线教学边界验收

本 spec 默认**不把在线教学接入作为 Gate 0 必过项**。若要纳入，必须另加：
- assembly 产生非空 query
- Orchestrator 传 query/scope/purpose
- Retriever 真正发出 `RETRIEVED_EVIDENCE`
- Tutor 真正消费该 evidence

否则，结论只能写：
**“离线摄入/索引/召回闭环已通”**。

---

## 4. 验证状态表

| 断言 | 验证状态 | 依据 |
|---|---|---|
| `Extractor.extract(file_path) -> str` 为当前统一契约 | ✅ 已核实 | `app/infrastructure/rag/extractors/base.py:7-28` |
| 当前 `.epub` 已被 extractor factory 支持 | ❌ 已核否 | 本轮核查未发现 `.epub` 路由；当前仅 txt/md/csv/pdf/docx |
| `/api/knowledge` 已是生产摄入入口 | ❌ 已核否 | `app/api/knowledge.py:1-28` 仅 CRUD name/description |
| `index_documents` 当前会做 chunking / schema 校验 | ❌ 已核否 | `app/infrastructure/rag/coordinator.py:135-139` 仅转交 provider |
| `PgVectorProvider.index` 会消费 metadata/doc_id/source/scope/user_id | ✅ 已核实 | `app/infrastructure/rag/pgvector_provider.py:77-83` |
| `PgVectorProvider.search` 返回的 Chunk 当前自带 doc_id | ❌ 已核否 | `app/infrastructure/rag/pgvector_provider.py:147-156` 未回填 doc_id |
| Gate 0 官方入口默认包含文件上传 API | ❌ 已核否 | 本 spec 第 1.2.1 节已明确 Gate 0 只交付 `KnowledgeIngestionService` 服务边界；`app/api/knowledge.py:1-28` 也不是上传入口 |
| 当前 provider 已支持 delete/replace/upsert 或重导幂等 | ❌ 已核否 | `app/infrastructure/rag/pgvector_provider.py:85-109` 仅 append-only INSERT |
| Gate 0 已定义 `doc_id/chunk_id` 的可执行稳定生成规则 | ✅ 已补入 spec | 本 spec 第 3.1.2-3.1.3 节 |
| Gate 0 已定义 provider provenance 的权威来源与冲突处理 | ✅ 已补入 spec | 本 spec 第 3.5 节 |
| `sources=None` 只搜索 vector | ❌ 已核否 | `app/infrastructure/rag/coordinator.py:103-117` 搜索所有 provider |
| 当前默认在线教学会自动走 retriever 且有非空 query | ❌ 已核否 | `app/orchestration/assembly.py:144-156`、`app/harness/orchestrator.py:149-163`、`app/agents/retriever.py:44-47` |
| `vector_chunks` 当前 embedding 维度是 2048 | ✅ 已核实 | `app/models/tables.py:92-111`、迁移 `20260622_add_vector_chunks_table.py:21-69` |
| B-③ 里的 `LayoutPDFExtractor` / `ChunkingService` 已实现 | ❌ 已核否 | 仅存在于 spec，当前代码中不存在 |

---

## 5. 影响传播检查

### 5.1 对摄入层的影响

- 新增 `KnowledgeIngestionService`
- 新增元素适配层
- 可能新增 `EpubExtractor`
- 未来可能新增 `LayoutPDFExtractor`
- `/api/knowledge` 若扩展上传，需另立 API 设计与安全约束

### 5.2 对检索层的影响

- `index_documents` 调用方将第一次拥有正式 chunk 生产者
- provider 返回路径需要补齐 `doc_id/chunk_id`
- 若后续宣称 user/scope 隔离，必须改 search SQL
- 若后续宣称 replace/delete，必须增 provider 生命周期方法

### 5.3 对评测层的影响

- benchmark 需要 adapter，不能反向主导 production chunk 主键
- `RetrieverAgent.evaluate` 当前仍是 substring 评测，不足以证明 chunk 设计正确
- 需要新增基于 stable chunk_id/source locator 的评测适配层

### 5.4 对文档层的影响

- README 中 vector 维度 1536 → 2048 的漂移需修正
- B-① / B-③ 后续若沿用本 spec 的 chunk contract，需要同步引用本 spec
- `docs/asset-inventory.md` 需补充本次新增资产

---

## 6. 提交 review 前自检

### ① 事实臆测
- [x] 路径/字段/签名均基于已核实源码或既有 spec
- [x] 已明确区分“当前代码事实”与“B-③ 待实现设计”
- [x] 已明确 EPUB 当前未支持
- [x] 已明确 `/api/knowledge` 当前不是摄入入口

### ② 自洽即停
- [x] 已比较“先做 Gate 0 chunking”与“先做图检索”
- [x] 已比较“保持 Extractor 旧签名”与“直接改结构化返回”
- [x] 已比较“立即支持 EPUB”与“先明确 unsupported”

### ③ 局部视角
- [x] 已检查 provider 写入与检索回传之间的 provenance 断裂
- [x] 已检查 chunk 契约对 benchmark/eval 的影响
- [x] 已检查分层归属，避免 ChunkingService 直接写库或直接触 API
- [x] 已检查在线教学链与离线闭环之间的验收边界

---

## 7. 待用户确认的关键决策

1. **Gate 0 的验收是否只做到“离线摄入/索引/召回闭环”**，还是要把“在线教学真实消费检索结果”也一起纳入？
2. **EPUB 是否要求和 TXT/DOCX/PDF 一起进第一批实现**，还是允许第一批先明确 unsupported？
3. **本阶段是否只修 `doc_id/chunk_id` 的回传契约**，还是同步纳入 delete/replace/scope-user filter 这类 provider 生命周期能力？
4. **长度单位是否接受先固定为 Unicode 字符数**，后续如改 token 再升 `chunking_spec_version`？

> 以上四点确认后，再进入编码计划会更稳；否则很容易把 spec 写成“表面完整、实际 scope 漂移”。
