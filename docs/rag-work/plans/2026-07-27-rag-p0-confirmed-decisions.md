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
| DEC-007 | BLK-006 | 在线 composition 入口显式校验 PgVectorProvider + PostgreSQL，不满足 fail-fast；fake/SQLite 仅限非在线路径，禁止静默回退 | RAG-C | production 后端真实性与 baseline 准入基础 |
| DEC-008 | BLK-006 | outcome 五态 `{ok, empty, degraded, failed, invalid-request}`；`low_score` 降为 ok 的质量子标记 | RAG-C | 检索结果可判定状态，支撑受控降级与失败分类 |
| DEC-009 | BLK-006 | payload 只放分类错误码 + 安全摘要；原始异常/SQL/连接串/堆栈只进内部日志；coordinator 异常不再静默吞没 | RAG-C | 失败可分类可观测且不泄密 |
| DEC-010 | BLK-007 | baseline 准入 gate 采用六项版：backend/provider/dialect/provider-set/attestation/corpus 隔离；隔离可走隔离 DB 或正式 identity 生效后的 `doc_id` provenance 过滤 | RAG-D | baseline 只在真实、单一来源的正式索引上运行 |
| DEC-011 | BLK-007 | 第一轮评测口径为 paragraph-containment proxy + gold-answer/context enrichment；benchmark locator 不进 runtime identity；严格 identity 映射归 BLK-013 | RAG-D | 黄金集在正式 identity 落地前能诚实产出第一轮基线 |
| DEC-012 | BLK-004 | canonical bytes 协议冻结（B-04 通过）：doc-v1/doc-norm-1/chunk-v1 + normalize_text 5 步 + length-prefixed framing + 半开 range canonical JSON + V1/V2/V3 回归基线；Phase 2 B/C 线均可编码 | RAG-B | stable ID 可跨实现复算，解锁 Phase 2 编码 |

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
- 至少三组公开复算测试向量。

### 7.4 解除条件

- 上述补证项通过主控复核；
- 同一规范输入在不同运行环境复算得到同一 `doc_id/chunk_id`；
- 相邻/空范围、Unicode、CRLF、空白变化下测试向量得到预期结果。

---

## 8. DEC-007：production 后端真实性（composition 校验）

### 8.1 已确认结论

1. 在线生产 composition（`/api/chat`、`/api/chat/stream` 装配的检索链）必须显式注入 `PgVectorProvider`，并在装配点校验 `rag_backend == "pgvector"` 且运行时 DB dialect 为 postgresql；不满足则 fail-fast，不进入检索。
2. fake、SQLite、多源（OCR/Code）在**非在线路径**（单元测试、集成测试、离线 bench）继续保留，不受本决策限制。
3. 禁止在线路径静默回退 fake；禁止"pgvector 不可用时悄悄用 fake 顶上"。

### 8.2 冻结边界

- "在线 composition 入口"的精确代码落点（assembly / 依赖注入）由 RAG-C 在 spec 里定义；本决策只冻结"必须校验、必须 fail-fast、不静默回退"。
- 默认配置 `rag_backend="fake"`（`app/core/config.py:21`）本身可以保留（服务本地/测试），但在线 composition 不得依赖该默认值静默通过。
- 本决策不要求全局启动即禁 fake（那会误伤测试）；强制点精确落在线热路径装配边界。

### 8.3 实施影响（非零改动，已核验）

- `coordinator.py:54-84` 的 else 分支（默认 fake 包装）在在线 composition 路径上必须被显式配置或注入覆盖；
- admission gate（BLK-007）可据此要求 baseline 运行前提供 backend 真实性证明。

### 8.4 解除条件

- 在线路径误配 fake 或 dialect 非 postgresql 时 fail-fast，有测试证明不进入检索；
- 非在线路径 fake/SQLite 仍可用，既有测试不回归；
- production composition 的可校验证明可被 BLK-007 admission gate 消费。

---

## 9. DEC-008：outcome 五态归约

### 9.1 已确认结论

检索结果状态枚举冻结为五态：

```text
ok               真实 provider 正常返回，有结果
empty            真实 provider 正常返回，无结果（真没数据）
degraded         部分基础设施降级：多 provider 部分失败 / SQLite 字符匹配降级 / embedding 降级但仍可用
failed           全部 provider 失败或基础设施异常（DB 连不上、embedding 服务挂）
invalid-request  缺认证身份 / 无授权 scope / 无效 query（衔接 DEC-001 fail closed，不检索）
```

1. `low_score` 不作为独立 outcome 态，降为 `ok` 的质量子标记（`quality: low/acceptable`）；语义质量继续归 Critic。
2. `degraded` 必须可观测：哪些 provider 失败、是否走了降级路径，进 `sources_used` 与内部日志；安全摘要对外（DEC-009）。
3. `invalid-request` 在检索入口拦截（衔接 DEC-001），不进入 provider 调用。
4. 该枚举填充 DEC-003 冻结的 `EvidenceProjection.retrieval_status` 字段取值；字段位置不变，取值由此决策定义。

### 9.2 实施影响（非零改动，已核验）

- `retriever.py:80-85` 现有 `empty/low_score/ok` 判定与 `retriever.py:59` 硬编码 `"timeout"` 需重构为五态判定；
- 现有测试 `tests/unit/agents/test_retriever.py:84-127` 断言 `low_score` 状态，RAG-C 编码时需同步修订为 `ok + quality=low` 语义；
- `coordinator.py:111-117` 吞异常导致 all-failed 与 empty 混同的问题，由 DEC-009 的异常传播改造配合本决策解决。

### 9.3 解除条件

- 多 provider 部分失败 → degraded；全失败 → failed；无异常无数据 → empty；缺身份/无授权 → invalid-request，四类有测试区分；
- DEC-004 的 empty/failed/Critic 无输出受控回复能据五态判定执行；
- baseline 能按失败类型分类（支撑 BLK-007）。

---

## 10. DEC-009：安全摘要与 provider 异常传播

### 10.1 已确认结论

1. `RetrievalFailed` / `EvidenceProjection.safe_summary` 只允许出现**分类错误码**与**预定义安全摘要**；禁止 `str(exc)`、SQL、连接串、堆栈进入事件 payload、Tutor 输入或 API 响应。
2. `coordinator.py:111-117` 的 `except Exception: continue` 改造为：记录失败 provider 与异常（进内部日志），并据此判定 `degraded`（部分失败）或 `failed`（全部失败），不再静默吞没。
3. 原始异常、SQL、连接串、堆栈只进结构化内部日志（含 trace_id/retrieval_id 关联）。
4. 错误码集合（如 `backend_unavailable`、`embedding_failed`、`db_error`、`invalid_request`）与安全摘要文案由 RAG-C 在 spec 里枚举；本决策只冻结"分类码 + 安全摘要对外、原始异常对内"的边界。

### 10.2 实施影响（非零改动，已核验）

- `retriever.py:58` `"reason": str(exc)` 必须移除，替换为分类错误码 + 安全摘要；
- `coordinator.py` 异常传播改造后，`SearchResult` / `sources_used` 语义需同步（记录调用过但失败的 provider）；
- DEC-002/005 的 attestation 失败态复用同一错误码表达。

### 10.3 解除条件

- payload 全文不含 SQL/连接串/str(exc)，有测试证明；内部日志含完整异常且可关联 retrieval_id；
- 全部 provider 异常 → failed 且 payload 只含错误码；部分失败 → degraded 且 sources_used 反映；
- 安全摘要文案枚举通过主控复核。

---

## 11. DEC-010：baseline 准入 gate 六项版

### 11.1 已确认结论

baseline 运行前必须同时满足六项 gate（在 RAG-D Freeze-D1 五项基础上纳入 corpus 隔离）：

1. `settings.rag_backend == "pgvector"`；
2. 被测 coordinator 的 vector provider 实际为 `PgVectorProvider`；
3. 实际 DB dialect 为 PostgreSQL；
4. 被测 coordinator provider 集合严格为 `{"vector"}`（因 `evaluate()` 固定 `sources=None`，`app/agents/retriever.py:123`）；
5. 存在正式 ingestion attestation，可关联输入 EPUB SHA、normalizer/chunking 版本、目标索引与块计数（来源为 DEC-002 的 IngestResult/JSON attestation）；
6. corpus 隔离：使用仅含本书当前产物的隔离 DB，**或**存在已验证的 corpus/doc provenance 查询过滤。

任一项不满足时 gate 拦截，不执行 `evaluate()`，报告对应 `blocked:*` 状态。

### 11.2 冻结边界

- gate 的第 1–3 项可直接消费 DEC-007 composition 校验的输出，不另造一套后端探测。
- 第 6 项的 provenance 过滤为**新增实现**（当前 `pgvector_provider.search` 无 `doc_id`/visibility WHERE，`app/infrastructure/rag/pgvector_provider.py:131-157`）；该过滤随 Phase 2 C-09 的 visibility WHERE 同批实现，不重复改造。
- gate 约束的是"被测评测实例的 provider 集合"，不是全局永久禁止多源；不阻塞 RAG-C 未来的多源在线能力。
- RAG-D 只记录与核验 attestation，不伪造机器证明；benchmark 不得自建索引补造准入。

### 11.3 解除条件

- D-03 admission gate 按六项版实现，六类拦截各有测试（fake/SQLite/多源/无 attestation/混源/dialect 不符）；
- gate 全绿后运行 20 题、每题一次，报告含 backend/attestation 引用；
- 隔离方式（隔离 DB 或 provenance 过滤）在报告中显式记录。

---

## 12. DEC-011：gold evidence 边界与 containment proxy 口径

### 12.1 已确认结论

批准 RAG-D Freeze-D2 四条临时规则与验收措辞修订：

1. `paragraph_id`、excerpt、source locator 仅在 benchmark audit 层使用；
2. 运行时 `golden_chunks` 采用完整 paragraph text；
3. 指标名称/报告必须称 **paragraph-containment proxy** 与 **gold-answer/context enrichment**；不称 strict evidence-id recall，不外推 Tutor 质量；
4. 禁止 benchmark 创建或冻结 runtime evidence key；正式 chunk identity 契约落地后，由主控决定是否新建版本化 `GoldEvidence → product Chunk` 映射（归 BLK-013）。

验收措辞同步修订：gold evidence "可映射项目实际 Chunk" 不作为正式 identity 落地前的 happy-path 硬条件；改为"gold evidence 可由已验证的 benchmark corpus 映射为完整文本，由项目现有 evaluator 以 containment proxy 比对；严格项目 Chunk identity 映射待正式契约生效"。

### 12.2 冻结边界

- proxy 的已知局限（跨 chunk 切分、改写文本可能误判）必须在报告中显式标注；
- 该口径只适用于 Retriever 第一轮 baseline，不构成在线 Tutor 质量结论；
- `paragraph_id` 与生产 `doc_id/chunk_id` 的分离边界沿用 DEC-005（BLK-004 冻结项），本决策不放宽。

### 12.3 解除条件

- D-02 adapter 按本口径实现并有单测；
- 报告中 proxy/enrichment 命名与局限标注可核验；
- 报告不出现 strict recall / Tutor 质量字样。

---

## 13. DEC-012：canonical bytes 协议冻结（B-04 通过）

### 13.1 复核结论

B-04 主控独立复核通过：两套独立实现（参考脚本 + 仅按规范文字编写的第二套实现）复算 V1~V3 全部 8 个哈希匹配；canonical JSON 字节跨实现等价；normalize 幂等性 3 例通过；framing 抗字段边界歧义通过。

### 13.2 已冻结协议

- **版本号**：doc protocol `doc-v1`；normalizer `doc-norm-1`；chunk protocol `chunk-v1`
- **normalize_text 5 步固定顺序**：NFC -> `\r\n`->`\n` -> `\r`->`\n` -> 行尾 `rstrip(" \t")` -> 连续 3+ `\n` 折叠为 `\n\n` -> `strip("\n")`
- **framing**：`frame(name, bytes) = name + "=" + str(len(bytes)) + ":" + bytes`；`len` 为 UTF-8 字节数（十进制 ASCII）；字段顺序固定
- **doc_id**：`sha256(frames(protocol="doc-v1", import_namespace, normalizer_version="doc-norm-1", normalized_document_text)).hexdigest()`
- **chunk_id**：`sha256(frames(protocol="chunk-v1", doc_id, chunking_spec_version, canonical_element_range, canonical_chunk_text)).hexdigest()`
- **canonical_element_range**：半开 `[start,end)`；canonical JSON `{"end":{"element":N,"offset":M},"start":{"element":K,"offset":L}}`（字典序、无空白）
- **元素流**：canonical 全文按 `\n\n+` 切；元素 i = canonical 全文连续切片 `[es[i], ee[i])`；offset 按 Unicode code point
- **回归基线**：V1（Unicode NFC）、V2（CRLF+空白+折叠）、V3（偏移+相邻+空区间）三组测试向量及其预期哈希为冻结回归基线

### 13.3 冻结边界

- `import_namespace` 必须非空；空值 fail-fast 由 Phase 2 B-09 写前校验补齐
- `chunking_spec_version` 由调用方给定，绑定 chunk policy
- `canonical_chunk_text` 仅用于 hash 输入，不改变 `content` 展示语义
- 协议版本号变化必须升级 `doc-v1`/`chunk-v1`/`doc-norm-1`
- 完整协议与测试向量见 `docs/rag-work/status/RAG-B.md`「Phase 1B 交付」

### 13.4 配套裁决

- **Phase 2 放行**：B 线（B-08~B-11）与 C 线（C-09~C-11）均可进入编码；C-08 provisional 通过（§F composition 精确落点、§G 错误码枚举在编码时定义并经主控复核）
- **EPUB 首批范围**：RAG-A 验收通过（24 测试全绿），EPUB 纳入 Gate 0 happy-path；ChunkingService 预留 `source_format="epub"`
- **stable-ID 评测收敛**：方向冻结，扩展（`golden_chunk_ids`/`golden_source_locators` + 命中优先级 + `evaluation_alignment`）作为 `RetrieverAgent.evaluate` 向后兼容扩展实现，归 RAG-D 设计（BLK-013 前）；禁止旁路评测

### 13.5 解除条件（BLK-004 整体解除仍需满足）

- B-10 `ChunkingService`/`KnowledgeIngestionService` 实现并生成正式 `doc_id/chunk_id`
- B-11 provider provenance round-trip 修复（SQL `doc_id` 权威 + `chunk_id` 回传）
- DEC-005 顶层 `chunk_id` 列 migration 落地
- 真实 ingestion attestation 关联 doc/chunk identity

---

## 14. 尚未确认、不得提前实现的事项

| 项目 | 当前状态 | 归属 |
|---|---|---|
| §F composition 精确代码落点 | C-08 provisional 通过；编码时定义并经主控复核 | BLK-006 / RAG-C |
| EvidenceProjection 字符/token 上限与 citation schema | 待 RAG-C spec 定义 | BLK-003 / RAG-C |
| 错误码集合与用户可见安全摘要文案枚举 | 待 RAG-C spec 枚举后主控复核（边界已由 DEC-009 冻结） | BLK-006 / RAG-C |
| 严格 identity recall 与版本化 GoldEvidence→Chunk 映射 | 明确后置（DEC-011 已冻结 proxy 过渡口径） | BLK-013 / RAG-D |
| shared/course、幂等/replace/delete、上传 API | 明确后置 | BLK-011/012 |
