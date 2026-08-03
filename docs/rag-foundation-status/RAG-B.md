# RAG-B 状态：通用 Chunking 能力

> 唯一写者：窗口 B  
> 主清单：[`../designs/2026-07-24-rag-foundation-parallel-todolist.md`](../designs/2026-07-24-rag-foundation-parallel-todolist.md)  
> 当前状态：🚧 第二轮独立复审完成：两个编码前阻断项成立，待主控冻结/裁决后再修订

## 1. 当前结论

1. **RAG-B 的正确范围是 Gate 0 无图 chunking/ingestion 闭环**：先打通 extract/adapt → chunk → `RAGCoordinator.index_documents(..., source="vector")`，不先做图检索，也不把在线 Tutor 消费混进第一批默认验收。
2. **ChunkingService 应是 Harness 层无状态纯服务**，只负责“元素/文本 → docs dict”；`KnowledgeIngestionService` 才负责提取、适配、切块、委托现有 `RAGCoordinator.index_documents` 的编排。不得把 chunk 逻辑塞进 API 或 provider。
3. **不得另造 RAG 主链**：最终写入必须沿现有 `EmbeddingService / PgVectorProvider / RAGCoordinator / RetrieverAgent / RetrieverAgent.evaluate`，不得并行发明第二条检索/评测链。
4. **第二轮 spec 已将四项阻断设计写成可执行提案，仍待主控冻结**：
   - `doc_id = sha256("doc-v1" + import_namespace + normalizer_version + normalized_document_text)`；
   - `chunk_id = sha256("chunk-v1" + doc_id + chunking_spec_version + canonical_element_range + canonical_chunk_text)`；
   - Gate 0 官方入口仅为 `KnowledgeIngestionService` 服务边界，不包含上传 API；
   - Gate 0 明确 append-only，不承诺重导幂等/replace/delete/隔离；SQL 顶层 `doc_id` 是回传权威来源。
5. EPUB 首批是否纳入仍必须由主控协调 RAG-A；未纳入时必须 explicit unsupported。
6. 第二轮独立复审确认：此前“主资产清单单写者”不是 RAG-B 的有效阻断项；但仍保留 2 个真实编码前阻断项：
   - 稳定 ID 仍缺字节级、可跨实现复算的协议（normalizer 顺序、Unicode 形式、`canonical_element_range` schema、唯一序列化算法、测试向量均未冻结）；
   - stable-ID 评测尚未被约束到既有 `RetrieverAgent.evaluate` 主链，仍可能被实现者做成旁路评测适配层。

## 2. 已核实事实

| 事实 | 位置 | 验证方式 | 路径归属 |
|---|---|---|---|
| `Extractor.extract(self, file_path: str) -> str` 是当前统一契约；factory 只支持 `.txt/.md/.csv/.pdf/.docx` | `app/infrastructure/rag/extractors/base.py:7-28` | 读源码 | 现状代码事实 |
| `TextExtractor` / `PDFExtractor` / `DocxExtractor` 都只返回纯 `str`，异常/缺依赖时降级 `""` | `app/infrastructure/rag/extractors/text_extractor.py:6-14`、`pdf_extractor.py:6-27`、`docx_extractor.py:6-18` | 读源码 | 现状代码事实 |
| 现有 `/api/knowledge` 仅为 name/description CRUD，不是文件上传/摄入入口 | `app/api/knowledge.py:1-28` | 读源码 | 现状代码事实 |
| `IndexProvider.index(docs: list[dict]) -> None` 与 `RAGCoordinator.index_documents(docs, source="vector") -> None` 只是接收开放 dict 并转交 provider；不做 chunking/schema 校验 | `app/infrastructure/rag/coordinator.py:24-43,135-139` | 读源码 | 现状代码事实 |
| `PgVectorProvider.index` 实际消费字段：`content`、`metadata`、`doc_id`、`source`、`scope`、`user_id` | `app/infrastructure/rag/pgvector_provider.py:77-83` | 读源码 | 现状代码事实 |
| `PgVectorProvider.search` 会 `SELECT doc_id`，但当前构造返回 `Chunk` 时未回填 doc_id；且 query 侧没有 `user_id/scope` WHERE 条件 | `app/infrastructure/rag/pgvector_provider.py:137-156` | 读源码 | 现状代码事实 |
| `RAGCoordinator.search(..., sources=None)` 会搜索所有已注册 provider，不是只搜 vector | `app/infrastructure/rag/coordinator.py:100-131` | 读源码 | 现状代码事实 |
| 当前 vector schema 为 2048 维，不是 README 曾写的 1536 | `app/models/tables.py:92-111`、`alembic/versions/20260622_add_vector_chunks_table.py:21-69` | 读源码 + 迁移 | 现状代码事实 |
| 当前默认在线教学链不保证产生非空 retriever query，因此不能把离线闭环写成“教学闭环已通” | `app/orchestration/assembly.py:144-156`、`app/harness/orchestrator.py:149-163`、`app/agents/retriever.py:44-47` | 读源码 | 现状代码事实 |
| `RetrieverAgent.evaluate` 走的是独立离线路径，输入 `query/golden_chunks/golden_answer/top_k`，当前主要是 substring 匹配 + RAGAS 降级逻辑，不是 chunk 正确性的充分证明 | `app/agents/retriever.py:103-265` | 读源码 | 现状代码事实 |
| `OCRProvider.index_image` 是当前唯一已落地的“提取→按段落分块→索引”闭环先例 | `app/infrastructure/rag/ocr.py:44-55` | 读源码 | 现状代码事实 |
| B-③ 中的 `LayoutPDFExtractor` / `LayoutElement` / `ChunkingService` / `KnowledgeIngestionService` 仍是待实现设计，不是当前代码事实 | `docs/designs/2026-07-03-phase-b3-pdf-layout-parsing-spec.md:161-180,277-296` 等 | 读现有 spec | 既有待实现设计 |
| B-① review 已明确要求先过无图 Gate 0，再谈图检索 | `docs/spec-modify/modify-2026-07-03-phase-b1-lightrag-dual-retrieval-spec.md:220-251` | 读 review 文档 | 既有 review 约束 |

## 3. 不确定项 / 阻断项

| 不确定项 | 原因 | 验证方式 | 是否阻断 |
|---|---|---|---|
| `import_namespace` / `normalizer_version` / `canonical_element_range` 的字节级编码协议 | 当前 spec 已给 hash 公式，但未冻结 bytes 前像；不同实现仍可得出不同 ID | 主控冻结共享契约：normalizer 顺序、Unicode 形式、range schema、唯一序列化算法、测试向量 | ✅ 阻断 |
| stable-ID 评测是否必须收敛到 `RetrieverAgent.evaluate` 主链 | 当前 spec 仍允许“评测适配层”被实现成旁路；违背现有主链要求 | 主控裁决并要求 RAG-D / RAG-B 对齐到 `RetrieverAgent.evaluate` 扩展输入 | ✅ 阻断 |
| `doc_id` 的稳定生成输入域（路径 / 归一化全文 / 外部逻辑 ID / 导入命名空间） | 当前 spec 只给原则，不足以指导实现者稳定落地 | 需主控冻结共享契约 | ✅ 阻断 |
| `chunk_id` 是否绑定元素范围、顺序、内容哈希、`chunking_spec_version` 的组合 | 当前 spec 只写“文档身份 + 元素范围/顺序 + 规范版本派生”，仍过宽 | 需主控冻结共享契约 | ✅ 阻断 |
| Gate 0 是否官方只允许服务/脚本入口，还是要同步建设上传 API | 当前 spec 写“API 或脚本调用”，容易范围漂移 | 主控裁决范围 | ✅ 阻断 |
| 重复导入是否必须在 Gate 0 就具备幂等 / replace / delete | 现有 provider 明确 append-only，不支持；但 spec 尚未把“非承诺”写死 | 主控裁决范围并冻结负面承诺 | ✅ 阻断 |
| provider 回传时 `doc_id` 的权威来源（SQL 顶层列 vs `metadata.doc_id`） | 影响 provenance 可信性与后续评测/删除 | 主控冻结共享契约 | ✅ 阻断 |
| EPUB 是否首批实现 | 与 RAG-A 直接耦合；影响 RAG-B Gate 0 验收矩阵 | 主控协调 RAG-A / RAG-B 顺序 | ⚠️ 条件阻断 |
| 长度单位第一版是否以 Unicode 字符数冻结 | 当前只是建议；若不先冻结，测试矩阵难收敛 | 主控冻结共享契约 | ⚠️ 条件阻断 |
| 未来若引入结构化 PDF / EPUB 元素，RAG-B 是否要冻结统一 `NormalizedElement` 形状 | 与 B-③ / RAG-A 的接口对接强相关 | 主控协调冻结接口草案 | ⚠️ 条件阻断 |

## 4. 拟修改资产

| 文件/资产 | 当前职责 | 拟改动 | 三色 | 与谁共享 |
|---|---|---|---|---|
| `docs/designs/2026-07-24-project-chunking-service-spec.md` | RAG-B Gate 0 正式 spec | 第二轮修订：补 4 个阻断项（ID 规则 / append-only 负面承诺 / 官方入口 / provenance source-of-truth） | 🟡 改动 | 主控、RAG-A、RAG-C、RAG-D |
| `app/harness/chunking_service.py` | 待建 | 无状态纯 chunk 服务 | 🔴 新建 | 主控、RAG-A |
| `app/harness/knowledge_ingestion.py` | 待建 | 摄入薄编排，串 extract/adapt/chunk/index | 🔴 新建 | 主控、RAG-A、RAG-C |
| `app/infrastructure/rag/pgvector_provider.py` | 当前 vector 写入 / 查询 provider | 最小必要改动：回填 `doc_id/chunk_id` provenance；若主控要求再扩生命周期能力 | 🟡 改动 | 主控、RAG-C、RAG-D |
| `app/infrastructure/rag/extractors/base.py` | 现有 extractor 工厂 | 若首批纳入 EPUB，则注册 `.epub`；若不纳入则不改 | 🟡 条件改动 | 主控、RAG-A |
| `tests/unit/infrastructure/test_rag.py` | Fake/coordinator 契约测试 | 补 chunk docs 经 `index_documents` 后 metadata 保留/回传面测试 | 🟡 改动 | 主控、RAG-D |
| `tests/unit/infrastructure/test_pgvector_provider.py` | provider 单测 | 补 provenance round-trip / append-only 明确行为 / 负例测试 | 🟡 改动 | 主控、RAG-D |
| `tests/integration/test_pgvector_real.py` | 真实 PG + embedding integration | 补真实 round-trip 与 Gate 0 召回样本测试 | 🟡 改动 | 主控、RAG-D |

## 5. 输入/输出契约

### 5.1 RAG-B 当前建议冻结的最小输入契约（待主控裁决）

**ChunkingService 输入**：
- `elements`: 线性或结构化元素序列（由纯文本 adapter 或未来结构化 extractor 提供）
- `context`: 至少包含 `source_format`、导入上下文、可选逻辑文档身份、scope/user_id 上下文
- `policy`: chunking 参数（长度单位、阈值、overlap、句界/硬切策略等）

> 当前不建议在 spec 文字层冻结最终 Python 函数签名；但必须冻结“输入信息域”有哪些。

### 5.2 RAG-B 当前建议冻结的最小输出契约（待主控裁决）

每个输出 chunk docs 至少满足：

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
  }
}
```

### 5.3 错误行为建议

- 空 / 全空白输入 → 返回空列表，不生成空 chunk
- extractor unsupported → 在摄入编排层返回明确 unsupported，不静默空索引
- metadata 不可 JSON 序列化 → fail fast，不允许脏 metadata 进入 provider
- 结构化 extractor 缺依赖或失败 → 允许回退纯文本路径，但必须在 metadata 标示 fallback
- **Gate 0 append-only 负面承诺（建议冻结）**：重复导入不会自动 replace/delete/upsert，可能混入旧/新 chunk

## 6. 方案对照与选择理由

### 6.1 先做 Gate 0 chunking vs 先做图检索

| | 本方案 | 备选 |
|---|---|---|
| 做法 | 先打通无图 chunking/ingestion 闭环 | 先做 B-① 图检索 |
| 收益 | 直接补摄入主链缺口，给图能力提供稳定 chunk 基座 | 更早验证图是否提升多跳/跨章节检索 |
| 代价 | 仍需新增编排、契约、测试 | 当前无正式摄入链 / 在线 query 断路，图难抵达用户价值 |

**结论**：先做 Gate 0。依据见 B-① review。 

### 6.2 保持 Extractor 旧签名 vs 直接结构化返回

| | 本方案 | 备选 |
|---|---|---|
| 做法 | 保持 `extract(file_path)->str`，新增 adapter / 可选 `extract_structured` | 直接改抽象基类为结构化返回 |
| 收益 | 向后兼容现有测试、调用方、回退链 | 类型更统一 |
| 代价 | 多一个适配层 | 破坏当前稳定 extractor 契约 |

**结论**：保持旧签名。现有 `Extractor` 协议与 B-③ 规划都支持这个方向。 

### 6.3 ChunkingService 纯服务 vs 把 chunk 逻辑塞进 API/provider

| | 本方案 | 备选 |
|---|---|---|
| 做法 | ChunkingService 在 Harness，KnowledgeIngestionService 做薄编排 | API 或 provider 内联 chunk 逻辑 |
| 收益 | 保持分层单向依赖、便于复用、便于单测 | 少一个模块 |
| 代价 | 要新建编排服务 | 业务逻辑与 IO 强耦合、难测 |

**结论**：ChunkingService 必须是纯服务。 

### 6.4 doc/chunk 身份独立于 benchmark paragraph_id vs 直接复用 paragraph_id

| | 本方案 | 备选 |
|---|---|---|
| 做法 | 生产 `doc_id/chunk_id` 独立定义；benchmark id 只进 `external_locators` | 直接复用 `paragraph_id` |
| 收益 | production 不被单 benchmark 反向主导 | 最省事 |
| 代价 | 需要额外定义稳定规则与映射层 | 共享契约会被单书 benchmark 绑死 |

**结论**：必须独立定义生产 ID。 

### 6.5 长度单位：Unicode 字符数 vs 直接 token 化

| | 本方案 | 备选 |
|---|---|---|
| 做法 | 第一版统一用 Unicode 字符数；未来如改 token 再升 `chunking_spec_version` | 第一版就按 token 切 |
| 收益 | 无需先引 tokenizer 抽象，测试稳定简单 | 与 embedding token 预算更一致 |
| 代价 | 需补极长文本 guardrail | 当前项目无 tokenizer 抽象，复杂度更高 |

**结论**：建议先冻结为 Unicode 字符数，但必须补“超长文本二切 / 失败策略”。

## 7. 影响传播

- **上游**：
  - TXT/PDF/DOCX 当前 extractor；未来 RAG-A 的 `EpubExtractor`
  - 未来 B-③ 若结构化 PDF 落地，将接到同一 chunk 契约
- **下游**：
  - `RAGCoordinator.index_documents`
  - `PgVectorProvider.index/search`
  - `RetrieverAgent.handle/evaluate`
- **数据库**：
  - 短期可不改 `vector_chunks` schema；但 provider provenance 回传要改
  - 若主控要求 delete/replace/scope-user filter，则会升级为 schema/provider 级改造
- **在线事件**：
  - 本轮默认不宣称打通 Tutor；若主控把在线接线纳入 Gate 0，会直接牵连 RAG-C
- **离线评测**：
  - RAG-D 需消费 stable `chunk_id/source_locator`，不能继续只靠 substring 证明 chunking 正确
- **测试**：
  - 需新增 chunk 纯函数单测、adapter 单测、provider round-trip、Gate 0 编排测试
- **文档**：
  - RAG-B spec 需第二轮修订；主控若冻结共享契约，应回写主清单
  - 资产清单已收录 RAG-B 规划资产

## 8. 验证状态表

| 声称/API/签名 | 状态 | 依据 |
|---|---|---|
| `Extractor.extract(file_path) -> str` 是当前统一 extractor 契约 | ✅ | `app/infrastructure/rag/extractors/base.py:7-28` |
| 当前 factory 已支持 `.epub` | ❌ | `app/infrastructure/rag/extractors/base.py:20-27` |
| `/api/knowledge` 已是现成文件摄入入口 | ❌ | `app/api/knowledge.py:1-28` |
| `index_documents` 当前会做 chunking/schema 校验 | ❌ | `app/infrastructure/rag/coordinator.py:135-139` |
| `PgVectorProvider.index` 消费 `content/metadata/doc_id/source/scope/user_id` | ✅ | `app/infrastructure/rag/pgvector_provider.py:77-83` |
| `PgVectorProvider.search` 当前已把 `doc_id` 回填到返回 `Chunk` | ❌ | `app/infrastructure/rag/pgvector_provider.py:147-156` |
| `sources=None` 仅搜索 vector | ❌ | `app/infrastructure/rag/coordinator.py:103-117` |
| 当前默认在线教学链会自动给 Retriever 非空 query | ❌ | `app/orchestration/assembly.py:144-156`、`app/harness/orchestrator.py:149-163`、`app/agents/retriever.py:44-47` |
| `vector_chunks` 当前 embedding 维度是 2048 | ✅ | `app/models/tables.py:92-111`、`alembic/versions/20260622_add_vector_chunks_table.py:21-69` |
| B-③ 的 `LayoutPDFExtractor/ChunkingService` 已实现 | ❌ | 仅存在于待实现设计文档 |
| 当前 provider 是 append-only，无 delete/replace/upsert | ✅ | `app/infrastructure/rag/pgvector_provider.py:85-109` |

## 9. 测试矩阵

### happy-path

- [ ] 普通 TXT → 线性元素 → chunk → `index_documents` → round-trip provenance
- [ ] DOCX（多段落）→ 线性元素 → 长短段规则生效
- [ ] PDF 纯文本 fallback → 标记 `extraction_mode='plain_text_fallback'`
- [ ] 超长自然段 → 二次切分 + overlap 规则
- [ ] 多个过短自然段 → 合并规则
- [ ] 结构化元素（未来接口）中 table/formula 原子保留

### 降级路径

- [ ] 空文本 / 只有空白
- [ ] extractor unsupported（`.epub` 若首批未纳入）
- [ ] extractor 缺依赖 / 提取失败回退
- [ ] metadata 不可 JSON 序列化
- [ ] 空 query 检索
- [ ] Fake / SQLite / PG 三环境行为差异但回传面一致
- [ ] 重复导入在 append-only Gate 0 下的明确非幂等行为

### 共享契约专项

- [ ] `doc_id` 稳定性：同输入/同版本两次生成一致
- [ ] `chunk_id` 稳定性：同输入/同版本两次生成一致
- [ ] 变更 `chunking_spec_version` 后 `chunk_id` 变化
- [ ] provider round-trip 后 `doc_id/chunk_id/source_locator` 不丢失
- [ ] benchmark `paragraph_id` 仅出现在 `external_locators`，不进入生产唯一主键域

## 10. 请求主控冻结/修订

### 请求主控冻结（RAG-B 提案）

**Freeze-B1：ChunkDocument 最小共享契约**
- 顶层必须有：`content/doc_id/source/scope/user_id/metadata`
- metadata 必须有：`doc_id/chunk_id/chunk_index/chunking_spec_version/source_format/source_locator`
- benchmark `paragraph_id` 只允许进入 `external_locators`
- **新增请求**：主控需继续冻结字节级稳定 ID 协议（Unicode 形式、换行/空白规范化顺序、`canonical_element_range` schema、唯一序列化算法、测试向量）

**Freeze-B2：Gate 0 范围**
- 第一批默认只验“离线摄入/索引/召回闭环”
- 不默认把在线 Tutor 消费纳入 RAG-B Gate 0
- 若主控要纳入，则需与 RAG-C 合并调度
- Gate 0 官方入口仅为 `KnowledgeIngestionService` 服务边界，不包含上传 API

**Freeze-B3：Provider 最小回传契约**
- 检索返回的 `Chunk.metadata` 必须带回可信的 `doc_id/chunk_id`
- 需要主控裁决：当 SQL 顶层 `doc_id` 与 `metadata.doc_id` 冲突时，以谁为准（RAG-B 建议：以顶层列为权威）

**Freeze-B4：评测主链约束**
- stable-ID / source locator 的评测适配必须收敛到既有 `RetrieverAgent.evaluate` 扩展输入，不得另建旁路检索或评测入口
- 需要主控协调 RAG-D：`golden_chunk_ids/source_locators` 与现有 `golden_chunks` 的兼容、优先级、降级语义

### 请求主控修订（RAG-B 阻断）

**Revise-B1：ID 规则需要主控裁决**
- `doc_id` 稳定输入域
- `chunk_id` 的 canonical 组成
- 是否允许路径参与稳定 ID

**Revise-B2：append-only 负面承诺需要主控裁决**
- Gate 0 是否显式写死“不保证重导幂等 / 替换 / 删除 / 用户隔离”

**Revise-B3：EPUB 首批纳入与否需主控协调 RAG-A**
- 若首批不纳入，RAG-B 测试矩阵必须把 `.epub` 标为 unsupported 降级路径，而不是 happy-path

## 11. 未做事项

- 未根据独立 review 的 4 个阻断项修订 `docs/designs/2026-07-24-project-chunking-service-spec.md` 第二版
- 未与 RAG-A 对齐 EPUB 首批是否纳入 Gate 0
- 未与 RAG-C 对齐“在线 Tutor 消费是否纳入 Gate 0”
- 未与 RAG-D 对齐 stable `chunk_id/source_locator` 如何进入黄金集评测 adapter
- 未形成最终 `doc_id/chunk_id` 稳定生成公式
- 未形成 provider provenance source-of-truth 决策
- 未形成 append-only Gate 0 的最终负面承诺文案

---

# 主控集中决策简报（RAG-B 提交）

> 用途：主控按本节逐项裁决共享契约，再将裁决写入唯一主清单并分发给 RAG-A/B/C/D。  
> 本节不是对共享契约的擅自冻结；所有“建议”均待主控确认。

## A. 决策目标：为什么现在必须裁决

RAG-B 的目标不是新建一套 RAG，而是让项目现有主链第一次拥有统一的、可追溯的文档 chunk 输入：

```text
Extractor / Adapter
→ ChunkingService
→ KnowledgeIngestionService
→ RAGCoordinator.index_documents(source="vector")
→ PgVectorProvider / EmbeddingService
→ RAGCoordinator.search
→ RetrieverAgent / RetrieverAgent.evaluate
```

当前 `RAGCoordinator.index_documents` 只把开放的 `list[dict]` 原样交给 provider（`app/infrastructure/rag/coordinator.py:135-139`）；若不先由主控冻结共享字段、身份和验收口径，RAG-A/B/C/D 会各自产生不兼容的 document identity、metadata、评测和入口语义。

### 这次裁决的成功标准

1. 同一文档、同一规范、同一输入可产生跨实现一致的 `doc_id/chunk_id`；
2. EPUB、chunking、在线 evidence、黄金集不会各自重定义 provenance；
3. 第一批明确只交付离线摄入/索引/召回，避免把上传 API、在线教学或数据库生命周期偷渡进 RAG-B；
4. stable-ID 评测复用 `RetrieverAgent.evaluate`，不新建旁路评测主链；
5. 主控冻结后，各窗口能据此独立编码而不需要重新协商字段含义。

## B. 现有体系与依赖关系

| 现有资产 | 当前事实 | 对本次决策的依赖 |
|---|---|---|
| `Extractor` / `get_extractor` | `extract(file_path)->str`；factory 当前仅支持 txt/md/csv/pdf/docx | RAG-A 的 EPUB 需要兼容此边界；RAG-B 不能强改既有返回类型。`app/infrastructure/rag/extractors/base.py:7-28` |
| `RAGCoordinator.index_documents` | 不校验 docs、不切块，只委托 provider | 必须冻结 ChunkDocument，否则上游会各造开放 dict。`app/infrastructure/rag/coordinator.py:135-139` |
| `PgVectorProvider.index` | 实际读取 `content/metadata/doc_id/source/scope/user_id` | ChunkDocument 顶层字段必须与真实写入面一致。`app/infrastructure/rag/pgvector_provider.py:77-83` |
| `PgVectorProvider.search` | 会读 SQL `doc_id`，但当前未回填 Chunk metadata；无 user/scope WHERE | 必须冻结 provenance 权威来源；不可把 scope/user_id 描述为已有隔离。`app/infrastructure/rag/pgvector_provider.py:137-156` |
| `PgVectorProvider.index` | append-only INSERT，无 delete/replace/upsert | 必须冻结 Gate 0 生命周期非承诺。`app/infrastructure/rag/pgvector_provider.py:85-109` |
| `RetrieverAgent.evaluate` | 既有部件级评测入口，当前以 `golden_chunks` 文本匹配为主 | RAG-D 的 stable-ID 对齐必须扩展它，而非新建旁路。`app/agents/retriever.py:103-265` |
| 在线 Retriever 路径 | 默认会话不保证给 Retriever 非空 query | RAG-B Gate 0 不能宣称在线教学闭环；这归 RAG-C。`app/orchestration/assembly.py:144-156`、`app/harness/orchestrator.py:149-163` |
| benchmark `paragraph_id` | 书籍 benchmark 的局部证据定位标签 | 只能成为 `external_locators`，不可反向成为生产 ID。`benchmarks/rag/books/the-myth-of-sisyphus/` |

## C. 主控需要按顺序裁决的冻结项

> **顺序不可颠倒**：身份协议先于输出契约；输出契约先于 provider 回传；入口和生命周期边界先于任务排期；评测主链最后依赖前述 identity/provenance。

### 决策 1：Freeze-1 — doc_id 字节级身份协议

**目标**：确保同一逻辑文档在 RAG-A/B/D 中可被完全相同地识别。

| 选项 | 内容 | 代价/风险 |
|---|---|---|
| A | 只说“doc_id 要稳定” | 不同实现可产生不同 ID；不可接受 |
| B | 只冻结 hash 公式 | Unicode、换行、字段边界仍不一致 |
| **C（建议）** | 冻结完整字节协议与测试向量 | 需要主控现在明确 normalizer/序列化细节 |

**建议裁决 C，最少须写死**：
- `doc_id = SHA-256(canonical_bytes({protocol:"doc-v1", import_namespace, normalizer_version, normalized_document_text}))`；
- Unicode 形式（NFC 或 NFKC）；
- CRLF/CR/LF 归一化顺序；
- 空白规则；
- canonical serialization（推荐固定字段集、字典序 key、UTF-8 canonical JSON）；
- 至少两组含 Unicode / 换行 / 空白的测试向量。

**依赖/影响**：RAG-B 实现 normalizer；RAG-A EPUB 走同一协议；RAG-D 用同一文档身份建 golden 映射。未决后果：跨窗口重复导入、重构和评测无法确认“同一文档”。

### 决策 2：Freeze-2 — chunk_id 字节级身份协议

**目标**：让一个 chunk 的身份不依赖 chunk_index、文件路径或 benchmark paragraph_id。

| 选项 | 内容 | 代价/风险 |
|---|---|---|
| A | `doc_id + chunk_index` | 策略变化时身份不可靠；不可接受 |
| B | 有 hash 公式但 range 不冻结 | 跨实现仍不一致 |
| **C（建议）** | 冻结 range schema、文本规则、序列化和向量 | 需要定义元素索引/offset 语义 |

**建议裁决 C，最少须写死**：
- `chunk_id = SHA-256(canonical_bytes({protocol:"chunk-v1", doc_id, chunking_spec_version, canonical_element_range, canonical_chunk_text}))`；
- `canonical_element_range` 固定为 start/end element index + start/end char offset；
- index 采用 0-based；offset 采用 Unicode 字符数；区间采用闭区间或半开区间（二选一）；
- `canonical_chunk_text` 使用 Freeze-1 同一 normalizer；
- `chunk_index` 只能排序/展示，不是身份来源；
- 至少两组含元素偏移的精确测试向量。

**依赖/影响**：RAG-B chunk 实现；RAG-A EPUB 的 spine/paragraph 元素顺序；RAG-D golden chunk ID；RAG-C evidence 定位。未决后果：chunk 身份无法稳定、评测只能退回 substring。

### 决策 3：Freeze-3 — ChunkDocument 最小共享契约

**目标**：把现有开放 dict 收紧成项目级 docs 输出面，但不另造 provider 或 schema。

**建议冻结**：

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
  },
}
```

**附带规则**：
- `external_locators.paragraph_id` 可存在，但绝不进入生产 ID hash；
- metadata 不可 JSON 序列化则 fail fast；
- `scope/user_id` 当前只是写入 provenance，不是查询隔离承诺。

**依赖/影响**：RAG-B 产生；RAG-A 输出适配；RAG-C 消费证据；RAG-D 读取定位。未决后果：各窗口会继续各自追加字段，round-trip 无统一验收。

### 决策 4：Freeze-4 — Gate 0 范围与唯一入口

**目标**：防止 RAG-B 同时被拉去做上传 API、在线教学或 provider 旁路。

| 选项 | 内容 | 代价/风险 |
|---|---|---|
| A | 一次做 API、在线 Tutor、全格式 | 范围混入 RAG-A/C，失控 |
| B | 只做离线，但 API/脚本/provider 直调都算官方入口 | 可绕开统一编排 |
| **C（建议）** | 只做离线摄入/索引/召回；唯一服务边界是 `KnowledgeIngestionService` | 上传和在线价值延后到独立任务 |

**建议冻结 C**：
- Gate 0 路径为 `extract/adapt → ChunkingService → KnowledgeIngestionService → RAGCoordinator.index_documents(source="vector") → provider round-trip`；
- 上传 API 不属于 Gate 0；现有 `/api/knowledge` 不扩展；
- 测试夹具与脚本可调用 Service，但不得绕过 Service 直写 provider；
- 在线 Tutor evidence 消费由 RAG-C 另行验收。

**依赖/影响**：RAG-B 只实现 service/chunker；RAG-C 继续负责 online P0；RAG-A 只提供 extractor/元素；RAG-D 从 service 输出评测。未决后果：实现范围重叠，形成多条摄入入口。

### 决策 5：Freeze-5 — append-only 生命周期非承诺

**目标**：把现有 provider 的真实能力和未实现能力清楚分开。

**建议冻结**：Gate 0 只承诺一次调用把 docs 追加写入现有 vector 链；不承诺：
- 重复导入幂等；
- 自动 replace/upsert/delete；
- 文档撤回/版本替换；
- 按 doc_id 生命周期管理；
- user/scope 查询隔离；
- `doc_count` 是逻辑文档数。

**依赖/影响**：RAG-B 测试断言重复导入会追加；RAG-C 如需可见性过滤须单列 SQL/provider 改造；RAG-D 报告不得误把重复 chunk 当自然集合；RAG-A 重导 EPUB 也不能假设覆盖。未决后果：stable ID 被误读为“自动幂等”。

### 决策 6：Freeze-6 — provider provenance 权威来源

**目标**：使检索结果中的 `doc_id/chunk_id/source_locator` 可可信回溯。

**建议冻结**：
- 写入前：顶层 `doc_id == metadata.doc_id`，且 `metadata.chunk_id` 非空，否则 fail fast；
- 读取时：SQL `vector_chunks.doc_id` 是权威来源；provider 用它覆盖/补齐 `Chunk.metadata["doc_id"]`；
- `chunk_id` 从 metadata 原样返回；
- Fake/SQLite/PostgreSQL 可以排序不同，但 `content/source/doc_id/chunk_id/source_locator` 回传面一致。

**依赖/影响**：RAG-B 改 provider round-trip；RAG-C 才能安全传 evidence；RAG-D 才能精确对齐；RAG-A locator 才不会断链。未决后果：每个窗口都可能自行定义 provenance 修复。

### 决策 7：Freeze-7 — EPUB 首批范围

| 选项 | 内容 | 代价/风险 |
|---|---|---|
| A | EPUB 本批 happy-path | 范围拉宽，依赖 RAG-A 就绪 |
| **B（建议）** | EPUB 是正式目标，但首批 explicit unsupported | 交付较克制，接口仍预留 |
| C | 完全不提 EPUB | 后续回补会再改契约 |

**建议冻结 B**：首批 happy-path 仅 TXT / DOCX / PDF plain-text fallback；在 RAG-A 的 `EpubExtractor` 合入前，Service 必须 explicit unsupported，不得空串后静默索引。

**依赖/影响**：RAG-A 独立接入 extractor；RAG-B 预留 `source_format="epub"` 和结构化元素；RAG-D 仅通过 adapter 处理书籍 locator。未决后果：验收矩阵持续摇摆。

### 决策 8：Freeze-8 — stable-ID 评测主链

**目标**：不因升级评测而新造旁路 RAG / evaluator。

**建议冻结**：stable ID / source locator 评测只能作为 `RetrieverAgent.evaluate` 的向后兼容扩展实现；禁止新建独立检索或评测主入口。

**建议的后向兼容输入与优先级**：

```python
{
  "query": str,
  "golden_chunks": list[str],                 # 旧字段
  "golden_chunk_ids": list[str] | None,       # 新字段
  "golden_source_locators": list[dict] | None,# 新字段
  "golden_answer": str,
  "top_k": int,
}
```

命中优先级：`golden_chunk_ids` → `golden_source_locators` → `golden_chunks`；输出必须标识 `evaluation_alignment` 为 `chunk_id` / `source_locator` / `content_substring`。

**依赖/影响**：RAG-D 负责给出兼容/降级语义；RAG-B 保证 ID/locator 产出和回传；RAG-C 不可另建评测入口；RAG-A 未来 EPUB 同用该证据语义。未决后果：离线 benchmark 可能通过、但现有 agent 评测主链完全不知情。

## D. 建议的集中决策顺序

1. Freeze-1（doc ID 字节协议）
2. Freeze-2（chunk ID 字节协议）
3. Freeze-3（ChunkDocument 最小契约）
4. Freeze-6（provenance 权威来源）
5. Freeze-4（Gate 0 范围与唯一入口）
6. Freeze-5（append-only 非承诺）
7. Freeze-7（EPUB 首批范围）
8. Freeze-8（评测主链及 RAG-D 扩展语义）

## E. 裁决后必须立即发生的动作

| 冻结项 | 主控动作 | 任务窗口动作 |
|---|---|---|
| Freeze-1/2 | 将完整 bytes protocol 与向量写入主清单 | A/B/D 在各自状态片段确认遵守，并将实现计划对齐 |
| Freeze-3/6 | 写入共享 docs/provenance 契约 | B 修改 spec；A/C/D 明确生产/消费字段 |
| Freeze-4/5 | 记录 Gate 0 范围与负面承诺 | B 缩定实现；C 不被拉入 Gate 0；D 不误设生命周期指标 |
| Freeze-7 | 记录 EPUB happy-path 或 unsupported | A/B 更新测试矩阵与排期 |
| Freeze-8 | 记录唯一评测入口与新 golden 字段语义 | D 出 evaluate 扩展设计；B 保证输入字段；C 不建旁路 |

## F. 未裁决的风险清单

- 不冻结 Freeze-1/2：不同窗口的 ID 不可复算，后续任何 provenance/评测都不可靠；
- 不冻结 Freeze-4/5：RAG-B 会在 API、在线教学、删除/幂等间范围漂移；
- 不冻结 Freeze-6：provider 的 SQL ID 与 metadata ID 会持续断裂；
- 不冻结 Freeze-7：EPUB 是否是第一批验收持续摇摆；
- 不冻结 Freeze-8：RAG-D 可能另建评测入口，违反现有 `RetrieverAgent.evaluate` 主链。

## G. 主控裁决回执模板

```markdown
# RAG Foundation 共享契约冻结回执

日期：2026-07-24
适用任务：RAG-A / RAG-B / RAG-C / RAG-D
唯一主清单写者：主控窗口

- Freeze-1 doc_id：裁决 [ ]；具体协议/测试向量：[ ]
- Freeze-2 chunk_id：裁决 [ ]；range schema/测试向量：[ ]
- Freeze-3 ChunkDocument：裁决 [ ]；最终字段：[ ]
- Freeze-4 Gate 0：裁决 [ ]；官方入口：[ ]；在线/API 是否纳入：[ ]
- Freeze-5 append-only：裁决 [ ]；明确非承诺：[ ]
- Freeze-6 provenance：裁决 [ ]；doc_id 权威来源/冲突策略：[ ]
- Freeze-7 EPUB：裁决 [ ]；第一批状态：[happy-path / explicit unsupported]
- Freeze-8 evaluation：裁决 [ ]；golden 输入优先级/降级语义：[ ]

分发日期：[ ]
要求各窗口回执期限：[ ]
```

## H. 主控确认后统一分发提示词

```text
【RAG Foundation 共享契约已冻结｜必须遵守】

主控已将最终裁决写入唯一主清单：
docs/designs/2026-07-24-rag-foundation-parallel-todolist.md

你只能更新自己的状态片段；不得改主清单或其他窗口状态片段。

共同硬边界：
1. 不得另造 RAG，必须沿 EmbeddingService → PgVectorProvider → RAGCoordinator → RetrieverAgent → RetrieverAgent.evaluate。
2. 不得把 benchmark paragraph_id 作为生产 doc_id/chunk_id；它只能在 metadata.external_locators。
3. 不得把 Gate 0 离线闭环表述为在线 Tutor 教学闭环。
4. 不得新建独立检索或评测主链。
5. 对冻结项冲突只能在自己的状态片段提出“请求主控修订”，不得自行更改定义。

【主控在此粘贴 Freeze-1 至 Freeze-8 的最终裁决】

请在自己的状态片段确认：已读取、已按冻结项调整任务边界；如有冲突，列出冲突与所需主控裁决，不得直接编码。
```
