# RAG Foundation 决策画布 · BLK-004

> **本页目的**：先说明我们最终要建成什么、BLK-004 在整体计划里解决什么，再下钻到 `chunk_id` 与 range 的技术选择。  
> **当前状态**：两项技术裁决（D-004-1/2）已由用户确认并固化（DEC-005/006）；W-001/W-002 展示工作流仍待确认。本页是决策阅读视图的源，不是已确认事实源。  
> **正式事实源**：已确认决策写入 `2026-07-27-rag-p0-confirmed-decisions.md`；阶段状态与 blocker 写入 RAG Foundation 主清单。  
> **阅读建议**：只想判断方向是否符合需求，读第 0–3 节与第 13 节；要审上下文与实现合理性，再读第 4–12 节；遇到不熟的模块名或术语，随时查文末「附录 A 名词对照清单」。

---

## 0. 三分钟决策摘要

### 我们最终想得到什么

```text
用户提出问题
  → 只检索该用户有权查看的正式产品知识
  → 找到可回查来源的证据块
  → 证据只进入当前这次检索和当前 Tutor 回复
  → 返回一次受控、grounded 的教学回答
  → 能区分“没召回 / 基础设施失败 / 生成失败”，并留下可审计证明
```

RAG Foundation 当前阶段的最终验收点不是“向量库里有数据”或“跑出了 RAGAS 分数”，而是 **Phase 6 能在真实 `/api/chat` 与 `/api/chat/stream` 中验证有权限、可追溯、因果隔离的 grounded answer**。阶段定义见 `docs/designs/2026-07-27-rag-foundation-execution-order.md:216-232`。

### BLK-004 为什么值得现在决策

BLK-004 为每条产品证据建立“出生证明”：它来自哪份文档、哪次切块规则、原文什么范围、检索回来后是否还是同一块。

如果不先冻结这层：

- 正式摄入无法证明“计划写入的块”和“数据库里的块”是同一批；
- Retriever 找到的内容无法稳定回查到产品知识源；
- RAG-D 只能用文本包含关系做弱代理，不能做严格 identity 对齐；
- Tutor 即使拿到了 evidence，也无法审计证据是否来自当前正式索引；
- A/B/C/D 可能各自发明不同 ID，后续集成时再返工。

### 当前只需判断两件事

| 待确认 | 推荐 | 为什么与上层目标有关 | 现在不决定的后果 |
|---|---|---|---|
| `chunk_id` 存储位置 | 新增 SQL 顶层可空列，暂不唯一 | 让数据库、检索结果、attestation 能围绕同一 identity 核验 | provenance 继续藏在任意 JSON，Phase 2 的正式契约无法收口 |
| range 坐标语义 | 0-based + Unicode code point + 半开 `[start,end)` | 让不同实现能从规范文本复算 chunk 范围 | stable ID 的 hash 输入仍有歧义，RAG-B 不能提交可靠测试向量 |

> ⚠️ 同意这两项不等于同意最终 hash 算法，也不等于承诺幂等。canonical bytes 与测试向量仍需 RAG-B 补证后再次复核。

---

## 1. 上层建筑：四个能力支柱

这轮 RAG Foundation 不是一组互不相关的技术补丁，而是在补齐一条可信产品链。

| 能力支柱 | 用户最终获得什么 | 已确认/待解决 | 主要阶段 |
|---|---|---|---|
| 正式摄入与证据身份 | 知识真实进入产品索引，每块证据可回查 | DEC-002 已确认；**BLK-004 当前待决** | Phase 1B → 2 → 4 |
| 授权隔离 | 只检索当前用户有权看的内容 | DEC-001 已确认 | Phase 2 → 4 → 6 |
| 当前回合证据消费 | 当前检索证据只进入当前 Tutor 回复 | DEC-003/004 已确认 | Phase 3 → 6 |
| 真实结果与评测 | fake、失败、空结果不冒充成功；baseline 只测正式产品索引 | BLK-006/007 后续收口 | Phase 2 → 5 → 6 |

### 四个支柱如何合成产品结果

```text
[正式摄入 + chunk identity] ─┐
[visibility 授权过滤]       ├─→ 可用且有权的 RetrievedEvidence
[backend/outcome 真实性]    ┘                  │
                                               ↓
[retrieval_id + Orchestrator 投影] ─→ 当前 Tutor 回复
                                               │
                                               ↓
[attestation + baseline + E2E] ─────→ 可审计的产品结论
```

**BLK-004 只负责左上角的“证据是谁、从哪来”。**它不负责授权判断、不负责在线事件关联，也不负责回答质量，但后面三者都需要消费它产生的 provenance。

---

## 2. 产品主链与 ID 分工

```text
知识源文件
  │ source_sha256：输入文件证明
  ↓
Extractor
  ↓
ChunkingService
  │ doc_id：逻辑文档身份
  │ chunk_id：证据块身份
  │ source_locator：人类可回查位置
  ↓
KnowledgeIngestionService
  │ ingestion_run_id：一次正式摄入运行
  ↓
PgVectorProvider / vector_chunks
  ↓
Retriever
  │ retrieval_id：一次逻辑检索，不是 chunk 身份
  ↓
Orchestrator
  │ parent_id：直接物理因果，不是文档身份
  ↓
Tutor grounded answer
```

| ID / locator | 生命周期 | 回答的问题 | 不能替代什么 |
|---|---|---|---|
| `source_sha256` | 原始输入文件 | “输入字节是哪一份？” | 不能定位某个 chunk |
| `doc_id` | 规范文档 | “这是哪份逻辑文档？” | 不能标识文档内的具体证据块 |
| `chunk_id` | 特定 normalizer/chunking 版本下的 chunk | “检索和评测看到的是哪一块？” | 不等于数据库 row ID，也不自动提供幂等 |
| `source_locator` | 来源格式定位 | “人到哪里复核？” | 不作为跨格式稳定主键 |
| `ingestion_run_id` | 单次摄入运行 | “这批数据由哪次运行写入？” | 不能替代内容 identity |
| `retrieval_id` | 单次逻辑检索 | “这批 evidence 属于哪个问题？” | 不能替代 `doc_id/chunk_id` |
| `parent_id` | 相邻事件因果 | “这个事件直接由谁产生？” | 不能表达文档或检索单元身份 |
| benchmark `paragraph_id` | 黄金集定位 | “人工 gold 在 benchmark corpus 哪里？” | 不能成为 production identity |

这张分工表解释了为什么 BLK-004 不能用既有 `retrieval_id`、数据库自增 ID 或 benchmark `paragraph_id` 简化掉：它们回答的是不同问题。

---

## 3. BLK-004 在 Phase 0–6 中的位置

```text
Phase 0  已确认 DEC-001~004，分发窗口边界
   ↓
Phase 1  A 提取器 │ B bytes/range/测试向量 │ C 在线 spec │ D 只读评测工具
                     ▲
                     └── 你现在正在裁决 BLK-004 的存储与 range 基线
   ↓  只有 B 协议通过主控复核才进入正式 identity 编码
Phase 2  Chunking + Ingestion + provenance round-trip + visibility + outcome
   ↓
Phase 3  evidence 真正进入当前 Tutor 回合
   ↓
Phase 4  首本 EPUB 正式摄入，生成 attestation，核对 doc/chunk provenance
   ↓
Phase 5  在正式索引上跑 Retriever baseline
   ↓
Phase 6  用真实 API 验证 grounded answer
```

### 决策的下游传播

| 本轮决定 | Phase 2 影响 | Phase 4 影响 | Phase 5/6 影响 |
|---|---|---|---|
| 顶层 `chunk_id` | migration、表模型、Provider 写读契约、fixture 需同步 | attestation 与 DB 可按 chunk identity 核验 | 检索证据可被评测和在线审计直接引用 |
| range 基线 | `ChunkingService` 的 element/range 数据结构与 ID 生成器据此实现 | 相同输入可复算 chunk 边界 | gold locator 可与产品 chunk 做可解释映射 |
| 暂不冻结 hash 细节 | 正式 ID 编码继续等待 B 测试向量 | 禁止临时 hash 冒充正式证明 | 防止 baseline 建立在漂移 ID 上 |

因此，这不是为了“表里多一个字段”，而是为了让 **Phase 2 的实现能在 Phase 4 留下证明，并被 Phase 5/6 消费**。

---

## 4. RAG 子框架全景：模块、职责与 BLK-004 的位置

BLK-004 不是孤立的“表里加字段”，它落在 RAG 子框架的「证据身份段」上。这一节先给子框架本身的完整设计与真实状态，再标出 BLK-004 覆盖的边界。

### 4.1 子框架是什么、怎么分层

RAG 子框架的任务是把「文件 → 文本 → 块 → 向量 → 检索证据 → 当前 Tutor 回复」串成一条**可信产品链**。按项目四层架构，它横跨三层（`docs/designs/2026-07-24-project-chunking-service-spec.md:91-112`）：

- **Infrastructure 层**：Extractor / EmbeddingService / Provider / Store——只做机械的抽取、向量化、存取；
- **Harness 层**：ChunkingService——纯服务，无 IO、不认证、不写库；
- **Orchestration / Agents 层**：KnowledgeIngestionService（摄入薄编排）、RetrieverAgent（机械检索）、Orchestrator（evidence 进入 Tutor 的唯一投影边界）。

### 4.2 模块全景与真实状态

| 模块 | 层 | 职责 | 状态 | 出处 |
|---|---|---|---|---|
| Extractor（text/pdf/docx） | Infrastructure | 文件 → 纯文本 `str` | 已实现 | `app/infrastructure/rag/extractors/base.py:7-28` |
| EpubExtractor | Infrastructure | `.epub → str`，只抽取、不生成 ID | 已确认职责·未编码 | `docs/designs/2026-07-27-rag-p0-confirmed-decisions.md:56-67` |
| adapter（NormalizedElement） | Infrastructure → Harness | 纯文本/结构 → 统一元素序列 | spec 设计 | `docs/designs/2026-07-24-project-chunking-service-spec.md:157-171` |
| **ChunkingService** | Harness | 元素序列 → ChunkDocument（doc/chunk 身份 + range） | 已确认职责·未编码 | 同上 `:173-194` |
| **KnowledgeIngestionService** | Orchestration | extract→adapt→chunk→index 唯一正式摄入边界；产出 IngestResult 与 attestation | 已确认决策·未编码 | `docs/designs/2026-07-27-rag-p0-confirmed-decisions.md:62-103` |
| EmbeddingService | Infrastructure | 文本 → 向量 | 已实现 | `app/infrastructure/rag/embedding.py:17-101` |
| RAGCoordinator / IndexProvider | Infrastructure | Provider 注册、聚合、去重、排序 | 已实现 | `app/infrastructure/rag/coordinator.py:24-175` |
| **PgVectorProvider** | Infrastructure | `vector_chunks` 写入与近邻检索 | 已实现·round-trip 有缺口 | `app/infrastructure/rag/pgvector_provider.py:22-187` |
| **vector_chunks 表** | Infrastructure | 块存储；有顶层 `doc_id`、**无顶层 `chunk_id`** | 已实现 | `app/models/tables.py:92-111` |
| RetrieverAgent | Agents | 机械检索；发 `RetrievedEvidence / RetrievalFailed` | 已实现 | `app/agents/retriever.py:24-101` |
| Orchestrator EvidenceProjection | Orchestration | evidence → Tutor 的唯一投影边界 | 已确认决策·未编码 | `docs/designs/2026-07-27-rag-p0-confirmed-decisions.md:115-148` |
| Tutor | Agents | 生成 grounded answer | 已实现·prompt 目前不含 evidence | `app/agents/tutor.py:74-97` |

> 💡 状态口径：「已实现」= 代码已存在；「已确认·未编码」= 职责边界已被裁决但尚未实现；「spec 设计」= 仅有设计文档。**加粗的四行是 BLK-004 直接触碰的模块**：身份在 ChunkingService 产生、在 PgVectorProvider / vector_chunks 存取、由 KnowledgeIngestionService 串成正式摄入链。

### 4.3 BLK-004 在子框架里的精确位置

```text
Extractor → adapter → ChunkingService → KnowledgeIngestionService
                          │ 产生 doc_id / chunk_id / range / locator
                          │        ← BLK-004 左边界：身份生成契约
                          ↓
               RAGCoordinator.index_documents
                          ↓
               PgVectorProvider ⇄ vector_chunks
                          │ 读侧应回传同一 identity（当前 doc_id 未回填）
                          │        ← BLK-004 右边界：provenance round-trip
                          ↓
               RetrieverAgent → Orchestrator 投影 → Tutor
```

一句话：**BLK-004 覆盖「ChunkingService 产生正式证据身份」到「Provider 检索后完整回传身份」这一整段**。左半段的职责与权威来源边界已冻结（`docs/designs/2026-07-24-rag-foundation-parallel-todolist.md:222-230`）；右半段还缺两样东西——存储列（决策一）与 range 坐标（决策二），即本页待裁决项。

### 4.4 子框架的四条设计约束（模块为什么这样分工）

| 设计约束 | 内容 | 出处 |
|---|---|---|
| 单一摄入边界 | 通用文档只经 KnowledgeIngestionService 正式摄入；extractor 不生成 ID、不写库 | `docs/designs/2026-07-27-rag-p0-confirmed-decisions.md:56-79` |
| 身份与授权分离 | visibility 管“能不能看”，identity 管“看的是哪块”，不可互相简化（DEC-001） | 同上 `:20-40` |
| 证据身份与检索身份分离 | `chunk_id` 标证据本体，`retrieval_id` 标一次检索的使用（DEC-003） | 同上 `:115-148` |
| 评测只读 | RAG-D 只消费正式产物与 attestation，不补造摄入链（DEC-002） | 同上 `:52-67` |

---

## 5. 模块间数据流与决策影响

### 5.1 当前真实数据流（代码已实现部分）

```text
【写入】当前没有“文件 → 索引”的通用入口；调用方须预先构造 dict
list[dict]{content, metadata, doc_id?, source, scope, user_id}
  → RAGCoordinator.index_documents   只转发，不切块、不校验   coordinator.py:135-139
  → PgVectorProvider.index           取字段、批量 embedding    pgvector_provider.py:60-83
  → EmbeddingService.embed_many      OpenAI 兼容 embedding API embedding.py:17-101
  → INSERT INTO vector_chunks        逐行写入并提交            pgvector_provider.py:85-109

【检索】
query: str
  → RAGCoordinator.search            多 Provider 聚合、去重、排序 coordinator.py:100-131
  → PgVectorProvider.search          embed_one → <=> 距离 → score=1/(1+d) pgvector_provider.py:111-157
  → Chunk{content, score, source, metadata}
       ⚠ SQL 已 SELECT doc_id，但构造 Chunk 时未回填    pgvector_provider.py:137-156
  → RetrieverAgent                   计算 retrieval_status，转 dict  retriever.py:67-101
  → RetrievedEvidence payload{chunks[], scores, retrieval_status, sources_used}
```

> ⚠️ 已实现代码里的两个关键缺口：① 检索侧 `doc_id` 读了不回填，provenance round-trip 断在 Provider（`app/infrastructure/rag/pgvector_provider.py:150-156`）——正是 BLK-004 要修的；② PG/SQLite 查询没有 `scope/user_id` 过滤（同文件 `:131-180`）——属 DEC-001 授权隔离的后续实现，不在本页裁决范围。

### 5.2 目标完整数据流（⟦ ⟧ = 已确认职责或 spec 设计、尚未编码的环节）

```text
文件（.epub / .pdf / ...）
  → ⟦Extractor / EpubExtractor⟧        纯文本 str
  → ⟦adapter⟧                          NormalizedElement 序列
  → ⟦ChunkingService⟧                  ChunkDocument{doc_id, chunk_id, range, source_locator, scope, version}
  → ⟦KnowledgeIngestionService⟧        全有或全无摄入；IngestResult + JSON attestation
  → RAGCoordinator.index_documents → PgVectorProvider → vector_chunks
  → search → Chunk → RetrievedEvidence
  → ⟦Orchestrator EvidenceProjection⟧  {retrieval_id, 已授权 chunks, citations, safe_summary}
  → ⟦唯一 Tutor ActionRequested⟧       Tutor prompt ← evidence
  → Tutor grounded answer
```

目标链出处：摄入段 `docs/designs/2026-07-24-project-chunking-service-spec.md:31-47,157-225`；投影段 `docs/designs/2026-07-24-rag-foundation-parallel-todolist.md:199-210` 与 `docs/designs/2026-07-27-rag-p0-confirmed-decisions.md:115-148`。

### 5.3 两个决策点对数据流的具体影响

| 决策点 | 改动的数据载体 | 影响的模块/文件 | 数据流上的具体变化 |
|---|---|---|---|
| **D-004-1** 新增可空顶层 `chunk_id` | `vector_chunks` 表结构；ChunkDocument 契约；`Chunk`/metadata 契约 | alembic migration、`app/models/tables.py`、`PgVectorProvider.index/search`、PG/SQLite 两侧 fixture 与契约测试 | 写入：`chunk_id` 从自由 metadata 升格为顶层列；检索：SELECT 与回填带上它，round-trip 才有权威来源；attestation 可按列直接关联 DB 行 |
| **D-004-2** range 采用 0-based + Unicode code point + 半开 `[start,end)` | ChunkingService 的 element/range 数据结构；未来 ID 生成器的 hash 输入 | 待建 `app/harness/chunking_service.py`；须同步修订 `docs/designs/2026-07-24-project-chunking-service-spec.md:312-353` 的“闭区间”草案 | 切块输出的每个 range 语义被冻结，RAG-B 的测试向量与 RAG-D 的 gold↔产品 chunk 映射才具备可复算前提 |
| 暂不冻结 hash（两项确认的附带边界） | ChunkDocument 的 `chunk_id` 填值时机 | ChunkingService、KnowledgeIngestionService | canonical bytes 与测试向量通过主控复核前，写入路径不得用临时 hash、row ID 或 `chunk_index` 填充并宣称 production stable ID |

---

## 6. 用产品需求反向判断本方案

| 你的上层需求 | 必须成立的技术保证 | BLK-004 如何支撑 | 如果推荐方案不符合需求，应怎么改 |
|---|---|---|---|
| 回答必须基于正式知识，而非 fake 或临时数据 | evidence 能关联正式摄入证明 | `chunk_id/doc_id` 与 attestation、DB 行建立关联 | 若你不要求逐 chunk 审计，可降低为 doc 级，但会削弱 baseline 与问题排查 |
| 无权限内容不能进入回答 | evidence 在过滤后仍保留可信 identity | visibility 负责“能否看”，identity 负责“看的是哪块” | 不能通过删除 identity 简化授权；两者职责不同 |
| 连续问题不能串证据 | chunk identity 与 retrieval identity 分离 | `chunk_id` 标证据，`retrieval_id` 标当前检索单元 | 若合并两类 ID，重试/复用同一 chunk 时因果会混乱 |
| 结果要可定位、可复现 | 范围与 normalizer/chunking 版本无歧义 | range + canonical bytes + 测试向量 | 若只需人工定位，可只留 locator，但不能再宣称可复算 stable ID |
| 先做 P0，不提前实现完整生命周期 | schema 可演进但不承诺去重 | 可空列、无唯一约束、append-only | 若现在就要求幂等/替换，需要另立生命周期 spec，范围会显著扩大 |

### 主控判断

若你的目标确实是“**真实、有权限、可追溯的 grounded answer，并能被正式 baseline 与 E2E 审计**”，BLK-004 是必要基础，不是局部优化。

若你的实际目标只是“先让单本书能搜到相似文本做演示”，则本方案偏重；可以选择 metadata-only 的临时方案，但只能诚实标为 prototype，不能满足当前 Phase 4–6 的正式验收口径。

---

## 7. 已确认决策如何约束 BLK-004

| 已确认决策 | 对 BLK-004 的约束 | 决策原因 |
|---|---|---|
| DEC-001：`global/private` + fail closed | identity/provenance 必须与规范 scope/owner 一起写入和回传 | 知道“哪一块”但不知道“谁能看”仍不安全 |
| DEC-002：A extractor-only、B 统一 ingestion、单次全有或全无 | A 不生成 ID；B 在正式摄入边界统一生成和校验；attestation 记录结果 | 防止每个 extractor/benchmark 各造一套 ID |
| DEC-003：payload `retrieval_id` | `retrieval_id` 只关联一次检索；证据本体继续由 `doc_id/chunk_id` 标识 | 分开“证据是谁”和“证据被哪次请求使用” |
| DEC-004：P0 `max_attempts=1` | BLK-004 不为 query expansion/retry 设计额外身份层 | 先验证一次原始检索到一次 Tutor 回复，控制 P0 范围 |

---

## 8. 已核验事实

| 事实 | 证据 | 影响 |
|---|---|---|
| 正式 `vector_chunks` 有顶层 `doc_id`，没有顶层 `chunk_id` | `alembic/versions/20260622_add_vector_chunks_table.py:34-43` | chunk identity 目前只能依赖 metadata，数据库不可直接查询或约束它 |
| Provider 写入 `doc_id` 与 `metadata_json` | `app/infrastructure/rag/pgvector_provider.py:77-107` | 有 provenance 存储入口 |
| Provider 查询 SQL 已读出 `doc_id`，但构造 `Chunk` 时未回填 metadata | `app/infrastructure/rag/pgvector_provider.py:137-156` | 当前 doc identity round-trip 未完成 |
| `Chunk` 只有 `content/score/source/metadata`，无一等 `doc_id/chunk_id` 字段 | `app/infrastructure/rag/coordinator.py:7-14` | P0 可由受控 metadata/Provider 契约承载 identity，但必须有写前与读后测试 |
| 现有 Chunking spec 有 ID 公式草案，但明确“待主控冻结” | `docs/designs/2026-07-24-project-chunking-service-spec.md:312-353` | 不得把草案 hash 当正式 production stable ID |
| 该草案把 `canonical_element_range` 描述为闭区间 | `docs/designs/2026-07-24-project-chunking-service-spec.md:318` | 与推荐的半开区间不同，确认后必须同步修订 spec 与测试 |
| benchmark `paragraph_id` 对同一 EPUB 与抽取脚本稳定，但它是 gold 定位 | `benchmarks/rag/books/the-myth-of-sisyphus/annotation-guide.md:39-59` | 可用于 benchmark 审计，不能升格为产品 ID |

> ⚠️ 当前没有已冻结的 canonical bytes serializer、stable-ID generator 或公开复算测试向量；因此本轮不能批准实现“正式 hash 公式”。

---

## 9. 决策一：`chunk_id` 放在哪里？

### 为什么必须做这个选择

当前表只有顶层 `doc_id`，而 chunk identity 若长期仅存在自由形态 JSON 中，数据库无法稳定查询、约束或直接核验它。Phase 4 要核对 doc/chunk provenance，Phase 5/6 要引用真实 evidence，因此现在需要先决定正式存储边界。

| | A：新增 SQL 顶层 `chunk_id`（推荐） | B：仅放 `metadata_json` | C：暂不持久化 `chunk_id` |
|---|---|---|---|
| 做法 | migration 增加可空列；正式协议通过后新摄入必填；暂不唯一 | 继续只在 JSON 中保存 | 只用自增 `id` 或 `chunk_index` |
| 上层收益 | DB、检索、attestation、评测共享同一 identity 面 | 能保存，但审计与查询契约弱 | 最快得到 prototype |
| 实施影响 | migration、模型、Provider、PG/SQLite fixture 与测试同步 | Provider 校验 JSON 必填与一致性 | 无 migration |
| 风险 | bytes 协议冻结前不能填临时 production 值 | 字段易缺失、重命名或被 metadata 覆盖 | 无法可靠回查同一 chunk |
| 幂等承诺 | 无；重复导入仍可追加 | 无 | 无 |
| 适用目标 | 正式产品链 | 过渡性内部实现 | 演示原型 |

**推荐裁决 D-004-1：选择 A，但分两步实施。**

1. 现在批准 `chunk_id` 成为 `vector_chunks` 的独立、**可空**顶层 provenance 列；不加唯一约束、不改变 Gate 0 append-only 语义。
2. canonical bytes/range 和测试向量通过主控复核后，新摄入正式 chunk 才必须写入稳定 `chunk_id`；此前不得用临时 hash、row ID 或 `chunk_index` 填充并宣称 production stable ID。

**选择原因**：把“可审计的存储槽位”与“最终 hash 算法”分开冻结。这样既不提前固化错误算法，又避免核心 identity 永久藏在任意 JSON 中。

---

## 10. 决策二：range 使用什么基线？

### 为什么必须做这个选择

即使 hash 字段顺序固定，如果实现者对“第几个字符”和“结束位置是否包含”理解不同，相同 chunk 仍会生成不同 ID。range 语义必须先于测试向量冻结。

| | A：0-based Unicode code point、半开 `[start,end)`（推荐） | B：1-based、闭区间 `[start,end]` | C：只保存 chunk_index / 格式 locator |
|---|---|---|---|
| 切片复算 | 可直接使用 `text[start:end]` | 需要 `+1/-1` 转换 | 无法精确复算 |
| 空范围 / 相邻块 | 天然表示；`A.end == B.start` | 需要额外规则 | 无统一规则 |
| Unicode 单位 | 明确 code point，不依赖 UTF-8 byte/tokenizer | 仍需另约定单位 | 各格式自行解释 |
| 跨格式 | element index + element 内 offset 可统一 | 可实现但转换更多 | locator 难统一 |
| 文档影响 | 修订现有“闭区间”草案 | 与草案表面一致 | 放弃可复算 stable ID |
| 适用目标 | 正式产品链 | 可实现但更易边界出错 | 仅人工定位/原型 |

**推荐裁决 D-004-2：选择 A。**

```text
- element 序号：0-based
- element 内 offset：Unicode code point 计数
- 区间：半开 [start, end)
- identity 输入：规范元素序列范围 + 规范 chunk 文本
- source_locator：章节、页码、spine、路径等格式定位，仅 metadata 审计
```

**选择原因**：它直接对应 Python 字符串切片，相邻范围可无歧义拼接，空范围也有统一表示；比闭区间少一层边界换算。

> ⚠️ 这里只冻结 range 坐标，不冻结 Unicode normalization form、换行/空白顺序或 hash framing。

---

## 11. 确认后怎么实施，而不是“决定完就算完成”

### 11.1 RAG-B 必须先补证

| 待补证项 | 可审计产物 | 通过标准 |
|---|---|---|
| canonical document bytes | 字段 framing、UTF-8、版本字段、Unicode/换行/空白处理顺序 | 不同运行环境对同一输入得到相同 `doc_id` |
| canonical chunk bytes | `doc_id`、chunking version、range、chunk text 的无歧义序列化 | 字段边界不可碰撞，顺序可机械验证 |
| 测试向量 | 至少两组，覆盖 Unicode、CRLF、空白、相邻 range | 独立实现得到相同 ID |
| provider round-trip | 写前一致性、读侧权威值、PG/SQLite 契约测试 | `doc_id/chunk_id/source_locator` 不丢失、不冲突 |

### 11.2 实施责任链

```text
RAG-A  输出 text / 结构信息；不生成 ID、不写库
RAG-B  定义 bytes → 生成 identity → 编排摄入 → 修复 provenance round-trip
RAG-C  对已授权 evidence 做在线投影；不定义文档 ID
RAG-D  用 paragraph_id 做 gold locator；只消费正式 product identity/attestation
主控   复核协议、测试向量、跨窗口冲突与解除证据
```

### 11.3 Happy-path 与失败路径验收

| 路径 | 必须验证 |
|---|---|
| Happy-path | 同一规范输入重复执行得到同一 doc/chunk ID；写入后 PG 检索回传相同 identity 与 locator；attestation 可关联 DB 行 |
| 冲突路径 | 顶层 `doc_id/chunk_id` 与 metadata 不一致时写前拒绝，不产生部分写入 |
| Unicode/换行 | Unicode、CRLF/LF、空白测试向量按冻结规则得到预期结果 |
| 授权路径 | 未授权高相似 chunk 在排序与 LIMIT 前过滤，identity 不泄露到 citation/Tutor |
| 基础设施路径 | migration/schema 不满足时诚实失败，不用 fake/手工 schema 冒充正式通过 |

本轮两项决策确认后，BLK-004 仍保持 `blocked`，直到上述协议、实现与运行证据全部满足。

---

## 12. 以后所有技术决策的建议展示工作流

你遇到的问题不是“细节不够”，而是**细节没有挂到目标、架构和阶段上**。建议以后采用两级视图、六步闭环。

### 12.1 两级视图

| 视图 | 回答什么 | 内容 | 更新频率 |
|---|---|---|---|
| **A. Program Cockpit（全局驾驶舱）** | 我们最终要去哪、现在在哪、什么阻塞全局 | 产品目标、四大能力支柱、Phase 0–6、blocker 状态、关键决策与下一里程碑 | 每次主控状态变化时更新 |
| **B. Decision Canvas（单项决策画布）** | 这个决策为什么存在、方案是否符合上层需求、怎么实现和验收 | 目标追溯、架构位置、备选对照、推荐原因、影响传播、实现责任、验收 | 每个需要用户裁决的 blocker 一份 |

当前页面是 **Decision Canvas 原型**。它保留必要的全局上下文，但不复制完整主清单。后续若你认可，应另建一个常驻 Program Cockpit，并从全局 blocker 卡片链接到每个 Decision Canvas。

### 12.2 六步闭环

```text
1. 目标对齐
   先说最终用户能力、当前里程碑、为何现在讨论
        ↓
2. 事实核验
   区分已实现 / 已确认 / 提案 / 未证实
        ↓
3. 决策画布
   显示架构位置、方案对照、推荐原因、延后代价
        ↓
4. 用户裁决
   只要求确认真正影响方向或不可逆成本的事项
        ↓
5. Canonical Markdown 固化
   更新 confirmed-decisions、主清单、相关 spec；HTML 重新渲染
        ↓
6. 实施与证据回流
   子任务编码/测试/运行 → 主控复核 → 更新 cockpit 状态
```

### 12.3 每张决策画布的固定阅读层级

1. **三分钟摘要**：目标、为什么现在做、只需决定什么。
2. **上层连接**：产品目标、架构支柱、Phase 位置、已确认决策约束。
3. **需求追溯**：每项技术选择如何改变用户最终能力。
4. **方案裁决**：完整备选、收益、代价、推荐理由、延后后果。
5. **实现下钻**：影响文件/模块、责任方、数据流与迁移范围。
6. **验收门槛**：happy-path、失败路径、真实环境证据和解除条件。

这能同时支持两条阅读路径：

```text
快速决策：摘要 → 上层连接 → 推荐与原因 → 确认
深度审查：事实 → 数据流 → 方案对照 → 实现影响 → 验收
```

---

## 13. 本页待确认

> ✅ **D-004-1、D-004-2 已由用户确认，并固化为 DEC-005/006**（见 `docs/designs/2026-07-27-rag-p0-confirmed-decisions.md`）；range 定义已同步修订于 `docs/designs/2026-07-24-project-chunking-service-spec.md`。**W-001/W-002 展示工作流仍待确认。**

### 技术裁决

1. **D-004-1**：新增可空顶层 `chunk_id`；正式协议通过后新摄入必填；不加唯一约束、不承诺幂等。
2. **D-004-2**：range 采用 **0-based + Unicode code point + 半开 `[start,end)`**；规范 range 参与未来 identity，格式 locator 仅用于审计。

### 展示与治理工作流

3. **W-001**：后续采用“一个常驻 Program Cockpit + 每个待决 blocker 一张 Decision Canvas”的两级 HTML 视图。
4. **W-002**：每项决策按“目标对齐 → 事实核验 → 决策画布 → 用户确认 → Markdown 固化 → 实施证据回流”闭环推进。

确认后才会：

- 将 D-004-1/2 写入已确认决策记录和主清单；
- 修订 Chunking spec 中与 range/存储边界冲突的提案；
- 建立常驻 Program Cockpit（若 W-001/2 获确认）；
- 再进入 BLK-006，而不是继续用孤立技术卡片推进。

---

## 附录 A. 名词对照清单

> 按主题分组；「状态」沿用本页口径：已实现 / 已确认（含已确认·未编码）/ spec 设计 / 待确认。ID 类名词的分工对照详见第 2 节。

### A.1 身份与 ID

| 名词 | 一句释义 | 状态 |
|---|---|---|
| `source_sha256` | 输入文件字节哈希，证明“摄入的是哪份输入”；不定位具体 chunk | spec 设计 |
| `doc_id` | 规范化逻辑文档的身份；DB 已有顶层列（`app/models/tables.py:103-110`） | 列已实现·生成协议待确认 |
| `chunk_id` | 特定 normalizer/chunking 版本下某个证据块的身份；决策一裁决其存储位置 | 待确认（D-004-1） |
| `source_locator` | 人可回查的格式定位（章节/页码/spine/路径）；不作跨格式稳定主键 | spec 设计 |
| `ingestion_run_id` | 一次正式摄入运行的标识，用于关联 attestation | 已确认 |
| `retrieval_id` | 一次逻辑检索的标识，关联 evidence 与当前回复；≠ chunk 身份（DEC-003） | 已确认 |
| `parent_id` | 事件间的直接物理因果 ID；≠ 文档/检索身份 | 已确认 |
| benchmark `paragraph_id` | 黄金集人工标注的段落定位；只属于 benchmark，不得升格为产品 ID | 已确认 |
| canonical bytes | 计算 ID 前的无歧义字节表示（编码、字段 framing、固定顺序、规范化） | 待 RAG-B 补证 |
| canonical element range | chunk 在规范元素流中的范围；其坐标语义即决策二 | 待确认（D-004-2） |
| `normalizer_version` | 文本规范化规则版本；规则变化应改变 doc/chunk identity | spec 设计 |
| `chunking_spec_version` | 切块规则版本；长度单位或规则变化时升级 | spec 设计 |
| stable ID | 由 canonical bytes 计算出的稳定身份；本页不冻结其 hash 算法 | 待补证 |
| provenance round-trip | 身份从摄入写入、经检索完整回传的闭环；当前断在 Provider 读侧 | 已实现但有缺口 |

### A.2 模块与服务

| 名词 | 一句释义 | 状态 |
|---|---|---|
| Extractor | 文件 → 纯文本的基础设施协议；现有 text/pdf/docx 三种 | 已实现 |
| EpubExtractor | EPUB 提取器，职责仅限 `.epub → str` | 已确认·未编码 |
| adapter / NormalizedElement | 把纯文本或结构化结果统一成 ChunkingService 可消费的元素序列 | spec 设计 |
| ChunkingService | 无状态纯切块服务；元素 → ChunkDocument；无 IO、不写库 | 已确认·未编码 |
| ChunkDocument | 摄入链中 chunk 的逻辑契约：content + 身份 + scope + 版本 + locator | spec 设计 |
| KnowledgeIngestionService | extract→adapt→chunk→index 的薄编排；通用文档唯一正式摄入边界 | 已确认·未编码 |
| IngestResult | 摄入运行结果：状态、run ID、输入 SHA、版本、planned/written count、错误摘要 | 已确认·未编码 |
| attestation | 版本化 JSON 摄入证明：某输入经正式产品链到底写入了什么 | 已确认 |
| EmbeddingService | 文本 → 定长向量的统一服务（OpenAI 兼容 API） | 已实现 |
| IndexProvider | 所有检索后端须实现的 `index/search/doc_count` 协议 | 已实现 |
| RAGCoordinator | Provider 注册、选择、聚合、去重、排序的统一检索入口 | 已实现 |
| Chunk | 检索结果最小数据类：`content/score/source/metadata` | 已实现 |
| SearchResult | 多源聚合结果：`chunks/total_found/sources_used` | 已实现 |
| PgVectorProvider | 以 PostgreSQL + pgvector 做写入与近邻检索的 vector Provider | 已实现 |
| pgvector | PostgreSQL 向量扩展；代码用 `<=>` 算距离 | 已实现 |
| `vector_chunks` | 正式块存储表；现有顶层 `doc_id`、无顶层 `chunk_id` | 已实现 |
| `metadata_json` | `vector_chunks` 的自由 JSON 列；目前 provenance 只能藏在这里 | 已实现 |
| FakeRAGStore | 内存假存储，字符重叠评分；不是真向量检索 | 已实现（测试/降级用） |
| OCRProvider / CodeIndexProvider | 图片 OCR / Python AST 两个专用 Provider；需显式注册才生效，默认不注册 | 已实现 |

### A.3 在线链与评测

| 名词 | 一句释义 | 状态 |
|---|---|---|
| RetrieverAgent | 机械检索 Agent：调 Coordinator、发证据/失败事件 | 已实现 |
| RetrievedEvidence | Retriever 检索后发出的证据事件（payload 含 chunks/scores/status） | 已实现 |
| RetrievalFailed | 检索抛异常时发出的失败事件 | 已实现 |
| `retrieval_status` | 机械检索状态：当前为 `empty/low_score/ok`；目标规范将扩展 | 已实现·规范待扩 |
| EvidenceProjection | Orchestrator 为 Tutor 构造的受限证据快照（retrieval_id + 已授权 chunks + citations + safe_summary） | 已确认·未编码 |
| retrieval micro-turn barrier | 检索微回合屏障：evidence 到齐后只产生一次最终 Tutor action | 已确认·未编码 |
| grounded answer | 由当前正式、已授权 evidence 支撑的回答；Phase 6 的验收对象 | 目标·未实现 |
| sentinel | E2E 测试中植入的唯一标记，证明 evidence 真的进了 Tutor prompt | 已确认验收条件 |
| visibility | 授权可见性：`global/private` 语义（DEC-001） | 已确认·读侧过滤未实现 |
| fail closed | 授权信息缺失时默认拒绝，宁可不召回也不泄露（DEC-001） | 已确认 |
| RAGAS | RAG 评测库；当前评测路径可选调用，缺失时降级不阻断 | 已实现（可选依赖） |
| recall@k | 黄金块被 top-k 结果覆盖的比例；当前用文本包含代理计算 | 已实现·待升级为严格 identity |
| containment proxy | 用文本包含关系做的弱 identity 对齐；≠ 严格 chunk-ID recall | 已实现·待替换 |
| admission gate | baseline 运行前的准入检查（PG、正式 attestation、语料隔离等） | 已确认 |

### A.4 角色与流程

| 名词 | 一句释义 |
|---|---|
| RAG-A / B / C / D | 四个并行工作流：A 提取器、B 摄入与身份协议、C 在线投影、D 只读评测 |
| 主控 | 跨窗口复核与共享契约冻结的治理角色 |
| 主账本 | `docs/designs/2026-07-24-rag-foundation-parallel-todolist.md`，blocker 与全局状态的正式事实源 |
| DEC-001~004 | 已确认决策编号，逐条见第 7 节 |
| BLK-004 / 006 / 007 | 主账本 blocker 编号；本页裁决 BLK-004 的两个前置项 |
| Phase 0–6 | RAG Foundation 执行阶段，定义见 `docs/designs/2026-07-27-rag-foundation-execution-order.md` |
| Gate 0 | 第一阶段摄入闭环范围：切块/索引/召回可用，但无上传 API、无生命周期管理 |
| append-only | 重复导入只追加；不承诺幂等、替换、删除 |
| planned/written count | 计划写入数与实际写入数；成功运行必须相等 |
