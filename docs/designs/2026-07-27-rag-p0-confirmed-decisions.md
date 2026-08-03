# RAG P0 已确认决策记录

> 日期：2026-07-27  
> 状态：本文件只记录**已由用户确认**的 P0 决策；未确认提案不在此固化。  
> 事实总账本与 blocker 详情：[RAG Foundation 主清单](2026-07-24-rag-foundation-parallel-todolist.md)。

---

## 1. 决策总览

| 决策 ID | 对应 Blocker | 已确认结论 | 主要责任方 | 直接影响 |
|---|---|---|---|---|
| DEC-001 | BLK-001 | RAG visibility 采用 `global/private` 最小模型；历史歧义行 fail closed | RAG-C | 检索和摄入的授权边界 |
| DEC-002 | BLK-002 | 新文档正式摄入走 A extractor-only + B ingestion；单次摄入全有或全无 | RAG-A、RAG-B | 产品摄入主链与首本书证明 |
| DEC-003 | BLK-003/005 | 检索关联使用 payload `retrieval_id`；不扩全局 Event schema | RAG-C | 在线因果链与证据隔离 |
| DEC-004 | BLK-003/005 | P0 `max_attempts=1`；不启用自动 query expansion | RAG-C | 在线首轮范围与回复唯一性 |
| DEC-005 | BLK-004 | `vector_chunks` 新增可空顶层 `chunk_id` 列；正式协议通过后新摄入必填；不加唯一约束、不承诺幂等 | RAG-B | chunk identity 存储边界与 provenance round-trip |
| DEC-006 | BLK-004 | range 采用 0-based + Unicode code point + 半开 `[start,end)`；格式 locator 仅用于审计 | RAG-B | chunk 范围复算基线与 ID hash 输入 |

---

## 2. DEC-001：最小 visibility 与历史歧义行

### 2.1 已确认授权矩阵

| 存储行 | 已认证请求用户 | P0 行为 |
|---|---:|---|
| `scope=global, user_id=NULL` | 任意已认证用户 | 可见 |
| `scope=private, user_id=当前用户` | 同一用户 | 可见 |
| `scope=private, user_id=其他用户` | 其他用户 | 不可见 |
| `scope=private, user_id=NULL` | 任意 | 不可见并审计 |
| `scope=global, user_id≠NULL` | 任意 | 不可见并审计 |
| 未知或缺失 scope | 任意 | 不可见并审计 |
| 任意受限行 | 缺失认证身份 | `invalid-request`，不检索 |

### 2.2 冻结边界

1. P0 RAG scope 仅支持 `global` 与 `private`。
2. 可信身份只来自 `get_current_user` 的 JWT 验签及用户存在性校验；不得使用 `ChatRequest.user_id`、用户文本或 LLM 输出做授权。
3. visibility 使用类型化上下文沿 API → 编排 → Retriever → Coordinator → Provider 单向传递。
4. Provider 必须在排序、去重、`LIMIT`、citation 和 Tutor 输入之前执行过滤。
5. 历史歧义行先 fail closed；后续审计后显式迁移成规范公共或私有行。
6. `shared/course` 语义后置，不得由实现者自行假定。

### 2.3 解除条件

- PostgreSQL 与 SQLite 返回相同授权集合；
- 未授权高相似 chunk 不抢占 top-k；
- evidence、citation、Tutor prompt 都不含未授权 sentinel；
- 歧义行被拒绝且可审计。

---

## 3. DEC-002：正式摄入主链、原子性与 attestation

### 3.1 职责分工

```text
RAG-A：EpubExtractor，.epub → str
RAG-B：adapter → ChunkingService → KnowledgeIngestionService → index_documents
RAG-D：只读取正式产物并验证，不补造摄入链
```

| 组件 | 已确认职责 | 明确不负责 |
|---|---|---|
| `EpubExtractor` | `.epub → str` | chunk、ID、写库、attestation |
| `ChunkingService` | 文本/元素 → ChunkDocument | 文件 IO、认证、Provider 调用 |
| `KnowledgeIngestionService` | extract/adapt/chunk/index 的薄编排 | 解析算法、SQL、embedding |
| `PgVectorProvider` | embedding、事务、持久化 | 文件提取与 chunk 业务规则 |

### 3.2 入口边界

`KnowledgeIngestionService` 是 TXT/MD/CSV/PDF/DOCX/EPUB **新增通用文档正式摄入**的唯一产品服务边界。

该边界不追溯覆盖：

- OCR/Code 的现有专用索引能力；
- Provider/Coordinator 单元测试；
- 数据库迁移测试。

P0 不扩展 `/api/knowledge`；使用受控项目 runner 和集成测试调用 Service。上传 API 后置。

### 3.3 写入语义

1. 单次 ingestion run 全有或全无；任一 chunk 写入失败，整体 rollback。
2. 成功 run 的 `planned_chunk_count == written_chunk_count`。
3. 全有或全无不等于幂等；重复成功导入仍可能追加数据。
4. replace/upsert/delete 和生命周期管理后置。
5. Extractor 空串归为 `extraction_empty` 非成功状态，不切块、不写入、不生成成功证明。
6. scope/owner 写入组合复用 DEC-001 的 fail-closed 矩阵。

### 3.4 Gate 0 attestation

Gate 0 暂不新增 `ingestion_runs` 表。受控产品 runner 必须将成功 `IngestResult` 写成版本化 JSON attestation，至少包含：

- `ingestion_run_id`；
- `source_sha256`、`source_format`；
- `doc_id`；
- normalizer / chunking 版本；
- planned / written chunk count；
- backend、dialect；
- scope、owner；
- 安全错误码和摘要。

禁止 benchmark 生成或伪造产品 attestation。

### 3.5 解除条件

- 真实 EPUB 完整经过产品 Extractor → Chunking → Ingestion → PgVector；
- 写入失败后无部分行残留；
- 数据库行数与 `written_chunk_count` 可核对；
- JSON attestation 可关联输入 SHA、版本、目标后端和 chunk 数；
- RAG-D admission 能独立消费并核验该证明。

---

## 4. DEC-003：`retrieval_id` 与因果关系

### 4.1 已确认字段语义

```text
parent_id    = 直接物理因果
retrieval_id = 一次逻辑检索单元
```

1. 不修改全局 `Event` schema。
2. 使用受控检索 payload 字段 `retrieval_id`。
3. 初始 Retriever `ActionRequested.id` 是本次 `retrieval_id`。
4. `RetrievedEvidence`、`RetrievalFailed`、未来 retry 与 Tutor projection 都继承该值。
5. `attempt` 仅由 Orchestrator 维护；Conductor、LLM、用户文本不得改写 visibility 或关联字段。

### 4.2 证据投影边界

```text
Retriever
→ 事件
→ Orchestrator 关联、裁决、投影
→ Tutor ActionRequested
→ Tutor
```

- Retriever 是唯一检索发起者；
- Orchestrator 是 evidence → Tutor 的唯一投影边界；
- Tutor 不直连 Coordinator、Provider、Embedding、SQL；
- Tutor 不读取未关联 `evidence_pool` 的“最近证据”；
- seed、rule、conductor 三条路径必须保真完整检索请求或证据投影。

### 4.3 回复唯一性

同一 `retrieval_id` 最多产生一次最终 Tutor action。Orchestrator 维护该检索单元的请求、结果、attempt、quality、直接因果 ID 与最终回复标记。

---

## 5. DEC-004：第一轮 P0 不自动 query expansion

1. 初始 `attempt=1`，`max_attempts=1`。
2. 不自动运行 `retriever_expand_query`。
3. low-score 或质量不足时，使用受控降级 projection，而不是未定义的 query rewrite。
4. Evidence/failure 到达后使用检索微回合屏障：Critic 的 quality observation 优先于 barrier tick；tick 只产生一次最终 Tutor action。
5. Critic 没有输出时，不得卡死；按机械检索状态继续，并标记 quality assessment unavailable。

### 验收条件

- 初始 action → evidence/failure → Tutor action → Tutor output 的 `parent_id` 链正确；
- 全链 `retrieval_id` 一致；
- sentinel 真正进入 Tutor LLM user prompt；
- 两个连续请求不串证据；
- 重复 evidence、迟到 quality、重复 tick 不产生第二份最终回复；
- empty、failed、Critic 无输出仍产生一次受控 Tutor 回复，不落入空回复 fallback。

---

## 6. DEC-005：`chunk_id` 顶层存储边界

### 6.1 已确认结论

1. `vector_chunks` 通过正式 Alembic migration 新增顶层 `chunk_id` 列，**可空**、**不加唯一约束**、不改变 Gate 0 append-only 语义。
2. canonical bytes 协议、range 规则与公开复算测试向量通过主控复核前，新摄入的正式 chunk 不得写入 `chunk_id`；此前不得用临时 hash、数据库自增 `id` 或 `chunk_index` 填充并宣称 production stable ID。
3. 协议通过后，新摄入的正式 chunk 写入 `chunk_id` 为必填；`chunk_id` 一经写入即只读保留，不承诺幂等、替换、删除。
4. 写入前摄入编排必须保证顶层 `doc_id` 与 `metadata.doc_id` 字节相等，且 `metadata.chunk_id` 非空（协议生效后）；不满足时 fail fast。
5. 读侧 SQL 顶层 `doc_id`/`chunk_id` 是权威来源；Provider 必须在构造返回 `Chunk` 时回填/覆盖 metadata。

### 6.2 冻结边界

- P0 `chunk_id` 仅作为 provenance 列存在，不承担检索键、去重键或生命周期键职责。
- `chunk_id` 不等于数据库 row ID，也不等于 `chunk_index`；后者只用于顺序展示与调试。
- 可空列的空值只允许出现在“协议未生效前的过渡数据”或“非正式摄入路径”；正式产品摄入 attestation 关联的行不得为空。
- 重复导入可产生多条相同 `chunk_id` 行，这由 append-only 语义承担，不由 `chunk_id` 唯一约束承担。

### 6.3 解除条件（BLK-004 整体解除仍需满足）

- canonical bytes/range 文档与测试向量通过主控复核；
- `ChunkingService` / `KnowledgeIngestionService` 真正生成并写入正式 `doc_id/chunk_id`；
- Provider 写入与检索回传 `doc_id/chunk_id/source_locator`，PG 与 SQLite 回传契约有测试；
- 真实 ingestion attestation 能关联 doc/chunk identity 并与 DB 行核对。

---

## 7. DEC-006：range 坐标基线

### 7.1 已确认结论

生产 `canonical_element_range` 的坐标与区间语义冻结为：

```text
- element 序号：0-based
- element 内 offset：Unicode code point 计数
- 区间：半开 [start, end)
- 身份输入：规范元素序列范围 + 规范 chunk 文本
- source_locator：章节、页码、spine、路径等格式定位，仅 metadata 审计，不参与 chunk 身份
```

### 7.2 冻结边界

- 半开区间 `[start, end)` 表示包含 start、不包含 end；可直接用 `text[start:end]` 复算 chunk 文本。
- 相邻 chunk 满足 `A.end == B.start`；空范围用 `start == end` 表示。
- Unicode code point 计数不依赖 UTF-8 字节数或 tokenizer。
- 0-based 序号从规范元素流的首元素起算。

### 7.3 仍未冻结（仍属 BLK-004 补证项）

DEC-006 只冻结 range 的**坐标单位与区间语义**。以下仍待 RAG-B 补证后由主控复核：

- canonical document bytes 的字段 framing、UTF-8、版本字段；
- Unicode normalization form（NFC/NFD 等）；
- 换行（CRLF/LF/CR）与空白归一化顺序；
- canonical chunk bytes 的无歧义序列化与字段顺序；
- `doc_id/chunk_id` 的最终 hash framing；
- 至少两组公开复算测试向量。

### 7.4 解除条件

- 上述补证项通过主控复核；
- 同一规范输入在不同运行环境复算得到同一 `doc_id/chunk_id`；
- 相邻/空范围、Unicode、CRLF、空白变化下测试向量得到预期结果。

---

## 8. 尚未确认、不得提前实现的事项

| 项目 | 当前状态 | 归属 |
|---|---|---|
| canonical bytes、Unicode form、换行/空白顺序、hash framing、测试向量 | 待 RAG-B 补证与主控冻结 | BLK-004 / RAG-B |
| `empty/degraded/failed/invalid-request` 完整归约 | 待讨论 | BLK-006 / RAG-C |
| 生产 pgvector composition 机制 | 待讨论 | BLK-006 / RAG-C |
| baseline admission/corpus isolation | 待讨论 | BLK-007 / RAG-D |
| shared/course、幂等/replace/delete、上传 API | 明确后置 | BLK-011/012 |
