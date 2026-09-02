# RAG P0 决策面板

> 当前范围：BLK-001 已确认、BLK-002 已确认、BLK-003/005 待确认。  
> 使用方式：先看“决策路径”，再审待确认卡片；本页是阅读视图的源文件，最终事实源仍为 `docs/rag-work/plans/2026-07-24-rag-foundation-parallel-todolist.md`。

## 1. 决策路径

```text
可信身份与数据可见性
  BLK-001：谁能看到什么？                         已确认
      ↓
正式摄入链
  BLK-002：数据如何进入产品索引并留下证明？       已确认
      ↓
在线请求关联与证据消费
  BLK-003/005：证据如何唯一、安全地进入 Tutor？   待确认
      ↓
后续 P0
  BLK-004：Chunk ID / provenance
  BLK-006：backend / outcome 真实性
  BLK-007：黄金集 baseline admission
```

## 2. 总览

| 决策 | 核心问题 | 当前状态 | 主要责任方 | 对后续的约束 |
|---|---|---|---|---|
| BLK-001 | 用户与范围如何隔离 | ✅ 已确认 | RAG-C | 摄入与检索都 fail closed |
| BLK-002 | 文件如何经产品链进入 PgVector | ✅ 已确认 | RAG-A + RAG-B | 必须全有或全无，并生成 attestation |
| BLK-003/005 | 一次检索如何关联并只生成一次 Tutor 回复 | 🟡 待确认 | RAG-C | 决定在线事件协议与路由状态 |

## 3. BLK-001：用户与范围隔离

### 3.1 已证实事实

- JWT 身份已经通过 `get_current_user` 验签，并验证用户仍存在。
- chat 与 chat-stream 使用 JWT 用户 ID，不信任 `ChatRequest.user_id`。
- `WorkspaceState.user_id` 已有可信身份。
- 可信身份没有继续进入 Retriever、Coordinator 和 Provider。
- PgVector 写入已有 `scope/user_id`，但 PG 和 SQLite 查询均无过滤。

### 3.2 已确认方案

> ✅ **Provider 在排序和 LIMIT 前执行授权过滤；历史歧义行先 fail closed，再审计迁移。**

| 存储行 | 行为 |
|---|---|
| `global + owner=NULL` | 公共可见 |
| `private + owner=当前用户` | 本人可见 |
| `private + owner=其他用户` | 不可见 |
| `private + owner=NULL` | 不可见 + 审计 |
| `global + owner≠NULL` | 不可见 + 审计 |
| 未知或缺失 scope | 不可见 + 审计 |
| 缺失认证身份 | `invalid-request`，不检索 |

### 3.3 冻结边界

- P0 scope 仅支持 `global/private`。
- 不复用语义不同的 `MemoryScope`。
- 身份只来自 JWT，不来自请求体、用户文本或 LLM。
- 类型化 visibility 上下文沿检索链单向传递。
- Provider 负责执行授权；Coordinator、Tutor 不做事后补救。
- `shared/course` 后置。

### 3.4 验收

- PG 与 SQLite 得到相同授权集合。
- 未授权高相似数据不能占据 top-k。
- evidence、citation、Tutor prompt 无未授权 sentinel。
- 歧义行有审计可观测性。

## 4. BLK-002：正式产品摄入主链

### 4.1 已证实事实

当前存在但未连接：

```text
文件 → Extractor → str

list[dict] → RAGCoordinator.index_documents → PgVectorProvider
```

中间缺失：

```text
适配 → 规范化 → Chunking → metadata/identity
→ KnowledgeIngestionService → 可审计写入结果
```

### 4.2 已确认职责

| 组件 | 做什么 | 不做什么 |
|---|---|---|
| EpubExtractor | `.epub → str` | 不切块、不写库、不生成 attestation |
| ChunkingService | 元素/文本 → ChunkDocument | 无 IO、不调 Provider、不做认证 |
| KnowledgeIngestionService | 薄编排：extract/adapt/chunk/index | 不实现解析算法、SQL、embedding |
| PgVectorProvider | embedding、事务、持久化 | 不负责文件提取或 chunk 业务规则 |
| RAG-D | 验证正式产物 | 不补造摄入、切块、索引 |

### 4.3 已确认入口边界

> ✅ **KnowledgeIngestionService 是新增通用文档正式摄入的唯一产品服务边界。**

覆盖：TXT/MD/CSV/PDF/DOCX/EPUB。

不追溯覆盖：

- OCR / Code 专用索引能力；
- Provider / Coordinator 单元测试；
- 数据库迁移测试。

本阶段不扩 `/api/knowledge`，使用受控 runner 与集成测试。

### 4.4 已确认事务与证明

> ✅ **单次 ingestion run 全有或全无。**

- 任一 chunk 写入失败 → 整体 rollback。
- 成功必须满足 planned count = written count。
- 全有或全无不等于重导幂等。
- replace/upsert/delete 后置。

> ✅ **Gate 0 先输出版本化 JSON attestation，不新增 `ingestion_runs` 表。**

`IngestResult/attestation` 至少包括：

| 信息 | 用途 |
|---|---|
| ingestion_run_id | 关联一次正式摄入 |
| source_sha256 / format | 证明输入来源 |
| doc_id | 产品文档身份 |
| normalizer/chunking version | 支持复算 |
| planned/written count | 证明完整写入 |
| backend/dialect | 排除 fake/SQLite 冒充 |
| scope/owner | 授权审计 |
| error_code/safe_summary | 安全失败信息 |

### 4.5 限制

- benchmark 不得生成产品 attestation。
- Extractor 空串是 `extraction_empty` 非成功状态，不进入 index。
- BLK-004 canonical bytes 未通过前，不得写临时 hash 并称 production stable ID。

### 4.6 验收

- 真实 EPUB 走完整产品链。
- 写入失败后无部分数据残留。
- planned/written/DB 实际行数一致。
- JSON 可关联输入 SHA、版本、后端、目标索引与 chunk 数。
- RAG-D 能独立核验该证明。

## 5. BLK-003/005：在线 Evidence 进入 Tutor

> ✅ **已确认：使用受控 payload `retrieval_id`，不修改全局 Event schema；第一轮 P0 `max_attempts=1`，不自动 query expansion。**

### 5.1 已证实事实

- 默认 seeds 直接向 Tutor 发 action，没有 Retriever action。
- Retriever 可以产生 `RetrievedEvidence/RetrievalFailed`。
- Critic 可以评估 teaching evidence 的 RAG 质量。
- Orchestrator 不消费 evidence/failure。
- Tutor prompt 不读取 chunks/citations。
- rule/conductor 生成新 action 时会丢 query、visibility 和证据字段。
- `WorkspaceState.evidence_pool` 没有正式 writer、关联或清理规则。

### 5.2 必须保持的架构边界

```text
Retriever 发事件
→ Orchestrator 关联、路由和投影
→ Tutor 只消费 ActionRequested
```

禁止：

- Retriever 直接调用 Tutor；
- Tutor 直接调用 Coordinator/Provider；
- Tutor 从“最近 evidence”隐式取证。

### 5.3 已确认决策 A：关联字段落点

| | 方案 A：Event 一等字段 | 方案 B：受控 payload `retrieval_id` | 方案 C：只用 parent_id |
|---|---|---|---|
| 改动范围 | 全局 Event/存储/回放 | 仅检索相关路径 | 最小 |
| 直接因果 | 支持 | parent_id 保持原职责 | 支持 |
| 逻辑 retry 关联 | 支持 | 支持 | 不足 |
| 风险 | 局部需求扩散成全局迁移 | 每条路径需保真测试 | retry 后关联断裂 |
| 推荐 | 不选 | **推荐** | 不选 |

推荐语义：

```text
parent_id = 直接物理因果
retrieval_id = 一次逻辑检索单元
```

- 初始 Retriever ActionRequested 的 event.id 成为 retrieval_id。
- evidence/failure、retry、Tutor projection 继承 retrieval_id。
- `attempt` 由 Orchestrator 管理。

### 5.4 已确认决策 B：第一轮不启用自动 query expansion

| | 方案 A：P0 最多一次 expansion | 方案 B：P0 不自动 expansion | 方案 C：按现有规则无限尝试 |
|---|---|---|---|
| 实现范围 | 需新增 query rewrite 契约 | 最小 | 不可控 |
| 当前实现基础 | 没有 | 一次原始 query 足够验证主链 | 规则名存在但无完整实现 |
| 循环风险 | 可控但仍需设计 | 最低 | 高 |
| 推荐 | 后续 | **推荐：max_attempts=1** | 禁止 |

推荐：第一轮 P0 只验证“一次检索安全、唯一地进入 Tutor”。低质量结果受控降级，不自动改写 query。

### 5.5 推荐检索微回合屏障

不建议 evidence 一到就立即 Tutor，因为 Critic 可能稍后判断质量低并触发再次检索。

推荐：

```text
RetrievedEvidence
→ Critic 尝试产生 RAGQualityAssessed
→ Orchestrator 安排 retrieval barrier tick
→ observation 优先于 tick
→ tick 时只做一次最终裁决
   ├─ 当前 P0：生成一次 Tutor action
   └─ 后续启用 expansion 后：retry 或 Tutor
```

Critic 无输出时不能卡死：tick 按机械状态继续，标记 `quality_assessment=unavailable`。

### 5.6 推荐 EvidenceProjection

| 字段 | 用途 |
|---|---|
| retrieval_id | 逻辑关联 |
| retrieval_status | ok/low_score/empty/degraded/failed/invalid-request |
| attempt | 当前尝试 |
| chunks | 已授权、受限正文 |
| citations | 来源与定位 |
| sources_used | 实际 provider |
| safe_summary | 安全降级信息 |

Tutor 不接触 Provider、Embedding、SQL、原始异常或未关联 evidence pool。

### 5.7 验收

- 一条 retrieval_id 最多产生一次最终 Tutor action。
- 初始 action → evidence/failure → Tutor action → Tutor output 的 parent chain 正确。
- 全链 retrieval_id 一致。
- sentinel 确实进入 Tutor LLM user_prompt，而非仅存在于事件。
- 连续 Q1/Q2 证据不串轮。
- empty/failed/Critic 无输出都产生一次受控回复，不落入空回复 fallback。

## 6. 已确认决策记录

### 决策 1：关联字段

> ✅ 采用受控 payload `retrieval_id`，不修改全局 Event schema；`parent_id` 继续表达直接因果。

### 决策 2：第一轮重试策略

> ✅ 第一轮 P0 设 `max_attempts=1`，不自动 query expansion；低质量证据受控降级。

### 决策生效后的实现约束

- 初始 Retriever ActionRequested 的 event.id 成为 retrieval_id；
- evidence/failure、未来 retry、Tutor projection 继承 retrieval_id；
- Orchestrator 维护 attempt 和最终回复唯一性；
- 默认 seeds 不再并发无证据 Tutor action；
- evidence 经微回合屏障后只生成一次最终 Tutor action；
- Critic quality 缺失时机械降级继续，不允许会话卡死。

## 7. 决策影响

若两项均同意：

1. RAG-C spec 可把 retrieval_id、微回合屏障、唯一回复写成可实现契约。
2. 不需要全局 Event/EventStore migration。
3. 第一轮范围不包含 query rewrite，显著降低接线复杂度。
4. 后续 BLK-006 只需补齐 outcome 和安全摘要，不必同时解决 retry 算法。
5. 在线 E2E 可以明确观察“原始问题 → 一次检索 → 一次 Tutor 回复”。

## 8. 下一步顺序

```text
确认 BLK-003/005 两项决策
  ↓
BLK-004：Chunk/stable-ID/provenance
  ↓
BLK-006：backend/outcome 真实性
  ↓
BLK-007：黄金集 baseline admission
```
