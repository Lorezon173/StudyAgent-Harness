# RAG-C 状态：在线 RAG P0 接线修复

> **任务目的**：修复默认在线会话中“检索未启动 / 检索证据未进入 Tutor / 向量检索未按用户与范围隔离”的 P0 断点，同时坚持既有主链：`EmbeddingService → PgVectorProvider → RAGCoordinator → RetrieverAgent → Tutor`。  
> **唯一写者**：窗口 C  
> **主清单（只读）**：[`../designs/2026-07-24-rag-foundation-parallel-todolist.md`](../designs/2026-07-24-rag-foundation-parallel-todolist.md)  
> **相关正式 spec**：[`../designs/2026-07-24-online-rag-p0-repair-spec.md`](../designs/2026-07-24-online-rag-p0-repair-spec.md)  
> **当前状态**：🟢 **Phase 2 C-09/C-10/C-11 最小实现完成（2026-08-17），身份隔离复审修复已纳入，全量测试通过；§F/§G 落点与文案已按 spec 候选值落地，待主控复核追认**。C-01~C-11 全部完成；Phase 3（C-12+）未开始。

---

## 1. 当前结论

### 1.1 已确认的在线断点

默认在线请求已确认进入新栈，但 RAG 主链尚未闭合：

```text
当前默认链：
/api/chat 或 /api/chat/stream
  → run_new_agent_session
  → UserMessage / TopicEntered / target=tutor 的 ActionRequested
  → Tutor 直接回复

缺失链：
完整 RetrievalRequest
  → RetrieverAgent
  → RAGCoordinator
  → PgVectorProvider
  → RetrievedEvidence / RetrievalFailed
  → Orchestrator EvidenceProjection
  → evidence-aware Tutor ActionRequested
  → Tutor 使用当前回合证据回复
```

已确认的 P0 断点：

1. **默认首轮不触发 Retriever**：默认 seeds 只发 Tutor action；因此默认首轮没有已确认的 `RetrieverAgent → RAGCoordinator` 执行。
2. **`retriever_expand_query` 不可作为首轮补救**：它依赖已有检索质量观察；质量观察又依赖已有证据，形成循环前置。且当前 rule/conductor 动作路径会丢失 query 等检索字段。
3. **Tutor 不消费 `RetrievedEvidence`**：Retriever 能产生证据事件，但 Tutor 只消费 `ActionRequested`，其当前生成输入不含 chunks、citation 或检索状态。
4. **PgVector 读侧无 scope/user 过滤**：写侧已存 `user_id/scope`，但 `search()` 及 PostgreSQL/SQLite 查询不接收也不筛选这些字段。
5. **Provider 失败被伪装为无结果**：Coordinator 对 provider 异常 `continue`；真实断连、embedding 失败与无命中会坍缩，且 Retriever 现有异常分支会把原始异常字符串放入 reason。

### 1.2 当前推荐解决方案

> 下列是窗口 C 的技术建议，**不是已冻结共享契约**。冻结项集中列在 §10，供主控裁决。

- 默认在线首轮采用**检索先行、证据/失败后 Tutor**，不再同时排入一个无证据的最终 Tutor 动作。
- 默认在线课程知识检索建议显式使用 `sources=['vector']`，避免 `sources=None` 把尚未具备 visibility 语义的 OCR/code provider 自动纳入。
- Retriever 仍是唯一检索发起者；Tutor 只接收由 Orchestrator 构造的、当前请求关联的 `EvidenceProjection`。
- 对检索请求、证据、Tutor 投影引入稳定的逻辑关联标识 `request_id`；`parent_id` 只保留直接事件因果。
- 将 `user_id` 与 visibility 上下文经 `RetrieverAgent → RAGCoordinator → IndexProvider → PgVectorProvider` 贯通；过滤必须在 PostgreSQL 和 SQLite 分支中一致执行。
- 结构化区分 `empty / degraded / failed / invalid-request`；内部诊断与对外安全摘要分离。
- 将 `vector_chunks` 的正式 schema / migration / fixture 契约纳入 P0；不能用测试内手工建表替代部署验收。

### 1.3 第二轮隔离评审结论 → Phase 1C 修订完成

- **首轮检索、默认 `sources=['vector']`、动作负载保真、request_id、schema/migration 进入 P0 范围的方向被认可。**
- 第二轮结论为“有条件通过”：spec 需补齐内部契约后可编码。**Phase 1C 已补齐并提交主控复核（C-08）。**
- 关联字段落点已由 **DEC-003** 裁决（受控 payload `retrieval_id`，不改 Event schema）；窗口 C 记录 blast-radius，不再二次裁决。
- 第二轮指出的 4 项内部约束已全部写入 spec：
  1. `RETRIEVED_EVIDENCE / RETRIEVAL_FAILED → Orchestrator → Tutor` 事件路由与投影分支 → spec §C；
  2. VisibilityContext 授权真值表及各 provider 强制点 → spec §D（DEC-001）；
  3. `empty / degraded / failed / invalid-request` 的归约与安全摘要 → spec §E/§G（DEC-008/009）；
  4. 默认在线 composition 如何实际保证 `PgVectorProvider` → spec §F（DEC-007）。

### 1.4 Phase 2 实现结论（C-09/C-10/C-11，2026-08-17）

主控复核授权按 spec 候选值先行最小实现；已落地并全量测试通过：

- **C-09（coordinator + provider）**：`VisibilityContext(user_id)` 类型化单向传递；`SearchResult` 新增 `outcome / attempted_providers / failed_providers / error_code`（带默认值，旧三参构造兼容）。受限路径仅 `vector` 参与，显式选中其他 provider 安全失败（`failed + invalid_request`，不发起调用）；`sources=None` 旧行为仅在**非受限**路径保留。PgVectorProvider PG/SQLite 分支与 FakeRAGStore 均按 DEC-001 谓词过滤，先于排序/去重/LIMIT；provider 异常进内部日志（`logger.exception`），结果对象只带 provider 名与分类码（`timeout` 按 TimeoutError 分类，其余 `db_error`；部分失败 `degraded/provider_degraded`）。
- **C-10（retriever）**：入口校验 query/top_k（1..10）/受限请求的 visibility+user_id 一致性+retrieval_id，`invalid-request` 不调用 provider；**C-09 加固（2026-08-17）：受限请求身份锚定 `WorkspaceState.user_id`（会话/JWT），payload `user_id` 必须为非 bool int 且三方（payload/visibility/ws）一致，缺 payload 身份或冒充他人均 invalid-request**；五态事件映射（`failed`→`RetrievalFailed`，`ok/empty/degraded`→`RetrievedEvidence`）；`low_score` 重构为 `ok + quality="low"`；异常/失败 payload 只含 `error_code + safe_summary`（§G 六码枚举），`str(exc)` 已移除。
- **C-11（assembly/API）**：`run_online_agent_session` 为在线显式入口，先做 DEC-007 三条件校验（backend=pgvector / vector provider isinstance `PgVectorProvider` / dialect=postgresql，dialect 由同步 URL 推导、不建连接）再进协作环；不满足抛 `OnlineRAGCompositionError`（分类安全异常）。`/api/chat` 映射 503 `{"error_code","message"}`；`/api/chat/stream` 在流内输出 `RAG_BACKEND_UNAVAILABLE` 错误事件。`run_new_agent_session` 单元直连路径不经过该校验，fake/SQLite 仍可测。
- **硬约束遵守**：主链 RetrieverAgent→RAGCoordinator→PgVectorProvider 未变；Tutor 未接线检索；Event schema 未改；`retrieval_id` 仅在 payload；`max_attempts=1` 无 expansion；未做 C-12+ seed/evidence/Orchestrator 路由。

---

## 2. 已核实事实

| 事实 | 位置 | 验证方式 / 结论 | 路径归属 |
|---|---|---|---|
| 同步 chat 进入 `run_new_agent_session` | `app/api/chat.py:18-37`；`app/orchestration/assembly.py:132-156` | API 在线程中调用新栈会话函数 | 在线主链 |
| SSE chat 也进入同一会话函数 | `app/api/chat_stream.py:24-50`；`app/orchestration/assembly.py:132-156` | SSE 仅额外接收事件回调，不是另一套 RAG 会话链 | 在线主链 |
| 默认 seeds 只有 UserMessage、TopicEntered、Tutor action | `app/orchestration/assembly.py:144-154` | 没有 `target=retriever` 的首轮请求 | 在线主链 |
| 新栈装配直接创建 `RetrieverAgent()` | `app/orchestration/assembly.py:118-124` | 当前没有给在线会话显式注入特定 Coordinator/provider | 在线 composition |
| rule path 当前仅产出 `action/target` | `app/harness/orchestrator.py:149-154` | query、visibility、request/evidence 字段会在此路径丢失 | 编排协议 |
| conductor path 当前仅产出 `action/target/via_conductor/reason` | `app/harness/orchestrator.py:214-223` | 同样不保留 RetrievalRequest / EvidenceProjection | 编排协议 |
| Orchestrator 当前只处理 observation、tick、ConductorDecided | `app/harness/orchestrator.py:80-98` | 当前不处理 `RETRIEVED_EVIDENCE` 或 `RETRIEVAL_FAILED` | 编排路由 |
| `Event` 只有 `parent_id`，无 request/correlation 字段 | `app/harness/events.py:18-35` | `parent_id` 仅能表达直接事件树因果，未显式表达逻辑检索单元 | 事件协议 |
| Retriever 只消费 `target=retriever`，读取 action payload | `app/agents/retriever.py:36-53` | 当前参数源为 `query/top_k/sources/purpose`，是主链唯一检索入口 | Agent 边界 |
| Retriever 经 Coordinator 执行检索 | `app/agents/retriever.py:49-53` | 满足既有主链约束，不应绕过 | Agent → Infrastructure |
| Retriever 当前仅在 Coordinator 抛异常时发失败，并会带 `str(exc)` | `app/agents/retriever.py:49-63` | 当前安全摘要与结果状态尚未闭合 | 失败语义 |
| Tutor 仅处理 target=tutor 的 ActionRequested | `app/agents/tutor.py:32-72` | 未订阅 evidence 事件 | Agent 边界 |
| Tutor `_ask/_explain` 只使用 topic/mode | `app/agents/tutor.py:74-97` | 当前完全不读取 action payload 的 evidence | 生成输入 |
| `IndexProvider.search` 签名仅 `(query, top_k)` | `app/infrastructure/rag/coordinator.py:24-37` | 当前协议无 visibility / request_id 位置 | 检索协议 |
| `RAGCoordinator.search` 在 `sources=None` 时搜索全部 provider | `app/infrastructure/rag/coordinator.py:100-117` | `sources=None` 或空列表会枚举注册 provider；不能改变其既有多源语义来满足在线默认首轮 | 检索协议 |
| Coordinator 吞掉 provider 异常 | `app/infrastructure/rag/coordinator.py:107-117` | 异常 `continue` 后与真实空结果不可区分 | 失败语义 |
| `rag_backend='pgvector'` 才注册 PgVectorProvider | `app/infrastructure/rag/coordinator.py:54-61` | pgvector 分支真实构造 `PgVectorProvider` | Provider 装配 |
| 非 pgvector 时注册 fake vector provider | `app/infrastructure/rag/coordinator.py:62-84` | 在线未显式固定配置时可走 fake | Provider 装配 |
| `rag_backend` 默认 `fake` | `app/core/config.py:20-23` | “默认在线必经 PgVectorProvider”目前不是可执行事实 | 配置前提 |
| PgVector 写入 `user_id/scope` | `app/infrastructure/rag/pgvector_provider.py:77-109` | 索引侧已持久化字段 | 向量存储 |
| PgVector PG 查询无 visibility WHERE | `app/infrastructure/rag/pgvector_provider.py:131-157` | 查询按 distance 排序/LIMIT，不筛 user_id/scope | 向量存储 |
| PgVector SQLite 查询无 visibility WHERE | `app/infrastructure/rag/pgvector_provider.py:159-180` | 降级分支同样不筛 user_id/scope | 向量存储 |
| OCR/Code provider 仍为二参 search | `app/infrastructure/rag/ocr.py:57`；`app/infrastructure/rag/code_index.py:102` | 现有 provider 未实现 visibility 契约 | 多源能力 |
| 多源 None 行为已有集成测试 | `tests/integration/test_retriever_integration.py:202-230` | `sources=None` 是既有多源/评估语义，RAG-C 不应破坏 | 回归边界 |
| PG 与 SQLite pgvector 测试在 fixture 手工建 `vector_chunks` | `tests/integration/test_pgvector_real.py:48-82`；`tests/unit/infrastructure/test_pgvector_provider.py:40-72` | fixture 是当前显式建表点 | schema / 测试 |
| **正式 `vector_chunks` Alembic migration 已存在**（C-01 修正） | `alembic/versions/20260622_add_vector_chunks_table.py:21-69` | PG 建 `vector` 扩展 + `vector(2048)` + `ix_vector_chunks_scope`；SQLite 退化 embedding 为 TEXT。**问题是 fixture 未消费它，不是 migration 缺失** | schema / 测试 |
| 现有 Retriever 协作测试覆盖 ok / empty | `tests/integration/test_retriever_integration.py:113-160`；`tests/unit/agents/test_retriever.py:59-69` | 现有测试仅覆盖当前 ok/empty，不证明安全 visibility 或 provider outcome 语义 | 测试现状 |
| **Phase 2 新增事实（2026-08-17 实现后核实）** | | | |
| `VisibilityContext` 定义于 coordinator 协议层 | `app/infrastructure/rag/coordinator.py:20-27` | dataclass，`user_id: int`；Retriever→Coordinator→Provider 单向传递 | C-09 |
| `SearchResult` 携带 outcome/attempted/failed/error_code（默认值向后兼容） | `app/infrastructure/rag/coordinator.py:31-44` | 旧三参构造仍可用（回归测试覆盖） | C-09 |
| 受限路径仅 vector 参与；显式选其他 provider → failed+invalid_request 且零调用 | `app/infrastructure/rag/coordinator.py:137-199`（search 聚合与归约） | 单测以 spy provider 证明零调用 | C-09 |
| PgVectorProvider PG 分支 visibility WHERE 先于 ORDER BY/LIMIT | `app/infrastructure/rag/pgvector_provider.py:140-165` | SQLite 分支同谓词（`:180-200`）；单测覆盖矩阵与 filter-before-limit | C-09 |
| FakeRAGStore 受限过滤在打分/排序/截断之前 | `app/infrastructure/rag/store.py:10-36` | 无 scope 历史文档按未知 scope fail closed | C-09 |
| Retriever 入口校验 + invalid-request 不进 provider | `app/agents/retriever.py:56-125` | top_k 上限 10（TOP_K_MAX）；受限请求强制 visibility+retrieval_id+身份三方锚定 `ws.user_id`（缺 payload user_id / 伪造一致外来身份 → invalid-request 且零调用，单测覆盖） | C-10 |
| 五态映射与 low_score→ok+quality=low | `app/agents/retriever.py:141-210` | `failed`→RetrievalFailed；degraded 带 provider_failures+safe_summary | C-10 |
| §G 六码错误码枚举 + 安全摘要文案落在 retriever 模块 | `app/agents/retriever.py:30-40`（SAFE_SUMMARIES） | payload 无 str(exc)/SQL/连接串/堆栈（泄漏测试覆盖） | C-10 |
| 在线 composition 三条件校验 + 分类异常 | `app/orchestration/assembly.py:135-183` | `OnlineRAGCompositionError(error_code=backend_unavailable)`；`run_online_agent_session:185-198` 在种子前 fail-fast | C-11 |
| `/api/chat` 503 分类响应；SSE 流内分类错误事件 | `app/api/chat.py:36-47`；`app/api/chat_stream.py:66-80` | 不静默回退 fake；单元直连 `run_new_agent_session` 不受限 | C-11 |
| PgVectorProvider.dialect_name 由同步 URL 推导（不建连接） | `app/infrastructure/rag/pgvector_provider.py:215-224` | URL dialect == 引擎 dialect；连接不可达由检索时机 db_error 承担 | C-11 |

---

## 3. 阻断项详情

### 3.1 RAG-C 内部阻断：证据到 Tutor 的可编码路由尚未闭合

**目的**：让默认回复实际使用当前回合检索结果，而不允许 Tutor 自行检索。

**现状证据**：
- Retriever 可以发 `RETRIEVED_EVIDENCE` / `RETRIEVAL_FAILED`；事件类型已有所有权定义：`app/harness/events.py:72-75`。
- Orchestrator 当前不处理这两类事件：`app/harness/orchestrator.py:80-98`。
- Tutor 当前不从 action payload 读取 evidence：`app/agents/tutor.py:74-97`。

**如果不解决**：只把首轮 action 改为 retriever 会使 evidence 无消费者，最终可能没有 Tutor 事件，`extract_reply()` 落入空回复 fallback：`app/orchestration/assembly.py:35-40,157-160`。

**RAG-C 应补的解决方案**：
1. 明确 Orchestrator 对成功证据、空证据、降级证据、失败事件各自的处理分支；
2. 定义 EvidenceProjection 字段表、截断策略、来源/citation 结构；
3. 明确每条结果分支生成哪一个 Tutor ActionKind；
4. 明确 Tutor 在 `_ask/_explain` 的输入构造点如何读取投影；
5. 用事件顺序和唯一 chunk sentinel 证明 Tutor prompt 实际获得当前回合证据。

**状态**：🔴 本任务内部 blocker；应由窗口 C 继续补 spec，不需要主控替 C 写实现细节。

### 3.2 RAG-C 内部阻断：VisibilityContext 尚无可执行授权真值表

**目的**：修复 PgVector 已写入 `user_id/scope` 但读侧完全未过滤的隔离缺口。

**现状证据**：见 §2 的 PgVector PG/SQLite 查询、IndexProvider 签名、OCR/Code provider 二参 search。

**必须写清的最小真值表**：

| 输入 / 数据行 | 请求用户 | 建议的预期（待主控冻结） |
|---|---|---|
| `scope=global`, `user_id=NULL` | 已认证用户 | 可见 |
| 私有 scope，`user_id=request.user_id` | 同一用户 | 可见 |
| 私有 scope，`user_id≠request.user_id` | 其他用户 | 不可见 |
| 缺失 `user_id` 的私有请求 | 任意 | 拒绝或仅允许 public；需冻结 |
| shared/course / 非规范 scope | 任意 | P0 暂不支持或另行规则；需冻结 |

**RAG-C 应补的解决方案**：
- 定义 VisibilityContext 的字段、允许 scope 和缺失身份策略；
- 选择强制点：优先让 Coordinator/IndexProvider 显式传递，Provider 负责执行自己的查询过滤；
- 固定默认在线首轮 `sources=['vector']`，避免未支持 visibility 的 OCR/code provider 通过 `sources=None` 旁路；
- 定义 fake provider 在受限请求下的等价过滤或明确拒绝行为；
- 过滤必须发生在排序、LIMIT、去重之前，并覆盖 PG/SQLite。

**状态**：🔴 内部 spec 仍需闭合；其中 global/private/shared 的业务规则需主控/用户冻结，窗口 C 不擅自决定。

### 3.3 RAG-C 内部阻断：结果状态、失败归约与安全摘要尚未闭合

**目的**：让“无结果”“部分 provider 失败”“全部 provider 失败”“无效请求”不再互相伪装。

**现状证据**：Coordinator 吞异常：`app/infrastructure/rag/coordinator.py:107-117`；Retriever 只在上抛时发失败且可能使用 `str(exc)`：`app/agents/retriever.py:49-63`。

**RAG-C 应补的解决方案**：定义 per-provider outcome 和 aggregate outcome，至少包含：

| 聚合状态 | 判定 | Retriever 输出 | Tutor 处理 |
|---|---|---|---|
| `empty` | 所有已成功尝试的 provider 返回零 chunks，且无失败 | `RetrievedEvidence(retrieval_status=empty)` | 无证据教学降级 |
| `degraded` | 至少一个 provider 成功，至少一个失败 | `RetrievedEvidence(retrieval_status=degraded)` + 安全诊断摘要 | 可使用成功证据，标记降级 |
| `failed` | 所有被请求 provider 都失败 | `RetrievalFailed` + 稳定错误码/安全摘要 | 失败降级教学，不泄露底层错误 |
| `invalid-request` | query / top_k / visibility / request_id 不满足契约 | `RetrievalFailed` + 输入错误码 | 不检索；受控说明 |

**额外约束**：
- 需要记录 attempted / succeeded / failed provider；
- 对外字段不得含 `str(exc)`、连接串、SQL 或堆栈；
- 内部日志可保留可分类诊断，但 API/Tutor 只见安全摘要；
- 部分成功不能因一个异常丢弃其他 provider 的成功结果。

**状态**：🔴 本任务内部 blocker；结果 schema 与摘要字段需在 spec 写死到可测试程度。

### 3.4 RAG-C 内部阻断：默认在线 composition 未保证 PgVectorProvider

**目的**：用户要求既有主链不得被绕过，而 P0 happy-path 需要真实 `PgVectorProvider` 而非 fake vector。

**现状证据**：`settings.rag_backend` 默认 fake（`app/core/config.py:20-23`）；`RAGCoordinator` 仅在 pgvector 配置时注册 `PgVectorProvider`（`app/infrastructure/rag/coordinator.py:54-84`）；assembly 当前直接 new RetrieverAgent（`app/orchestration/assembly.py:118-124`）。

**如果不解决**：即便首轮 payload 写 `sources=['vector']`，在线仍可能走 `_VectorStoreProvider`；这不满足“默认在线课程知识检索经 PgVectorProvider”的 P0 happy-path。

**RAG-C 应补的解决方案**：
- spec 必须指定 online composition 的配置或依赖注入方式，使生产在线路径显式要求 pgvector；
- pgvector/embedding/schema 不可用时应产生 `failed/degraded`，不得静默回落到 fake；
- 集成测试需 spy/assert 实际 provider 类型、`rag_backend='pgvector'`、迁移后的 schema 和真实隔离查询；
- fake backend 仍可用于无外部依赖单元测试，但不得冒充真实在线 happy-path。

**状态**：🔴 本任务内部 blocker；这是 RAG-C 可单边补进 spec 的 composition 约束，不是 request_id 类型的外部决策。

### 3.5 共享 / 产品阻断：请求关联字段最终落点 — ✅ 已由 DEC-003 冻结

**已冻结（编码依据）**：`retrieval_id` 走受控检索 payload，不修改全局 `Event` schema；初始 Retriever `ActionRequested.id` 即本次 `retrieval_id`；evidence/failure/未来 retry/Tutor projection 继承该值；`attempt` 仅由 Orchestrator 维护；`parent_id` 只表达直接物理因果。Conductor、LLM、用户文本不得改写 visibility 或关联字段（`2026-07-27-rag-p0-confirmed-decisions.md` §4）。

**窗口 C 记录 blast-radius（不二次裁决）**：
- 改动：`assembly.py`（种子创建 retrieval_id）、`retriever.py`（输出携带 retrieval_id）、`orchestrator.py`（路由状态 + Tutor 动作携带）、`tutor.py`（从动作 payload 读取）、`critic.py`（RAGQualityAssessed 携带 retrieval_id，P0 内 quality 仅作低分降级标记，不驱动第二轮检索）。
- 不改：`events.py` 的 `Event` dataclass、`EVENT_PRIORITY`、`EVENT_OWNERSHIP`。

### 3.6 共享 / 产品阻断：scope 授权语义与用户可见降级 — ✅ 部分已由 DEC-001/008/009 冻结

**已冻结（编码依据）**：
- DEC-001：global/private 最小矩阵 + 历史歧义行 fail closed；可信身份只来自 `get_current_user` 验签；visibility 类型化单向传递；过滤在排序/LIMIT 前。
- DEC-008：outcome 五态 `{ok, empty, degraded, failed, invalid-request}`；`low_score` 降为 ok 的质量子标记。
- DEC-009：payload 只放分类错误码 + 安全摘要；`str(exc)`/SQL/连接串/堆栈只进内部日志；coordinator 异常不再静默吞没。

**仍待主控/产品复核（spec 已定义，未冻结）**：
- 具体错误码集合与安全摘要文案枚举（DEC-009 §10.3 要求 RAG-C spec 枚举后主控复核）；
- EvidenceProjection 的字符/token 上限与 citation schema；
- 在线 composition 入口精确代码落点与校验实现（DEC-007 §8.2 明确由 RAG-C 在 spec 定义）。

---

## 4. 拟修改资产

| 文件/资产 | 当前职责 | RAG-C 拟修改内容 | 三色 | 影响 / 协作 |
|---|---|---|---|---|
| `docs/rag-work/specs/2026-07-24-online-rag-p0-repair-spec.md` | RAG-C 正式设计 | 补 §3.1–§3.4 的四项内部 blocker：事件路由、visibility 真值表、outcome、online composition | 🟡 | 窗口 C；主控审阅 |
| `app/orchestration/assembly.py` | 新栈 seeds / reply 提取 | 首轮 retriever seed、禁止无证据 Tutor 抢先、注入 online RAG composition | 🟡 | C 实现；D 验收 |
| `app/harness/orchestrator.py` | rule/conductor 与事件路由 | payload 保真、检索结果分支、EvidenceProjection、Tutor action | 🟡 | C 实现；D 验收 |
| `app/harness/events.py` | 事件基础协议 | 若主控选 Event 一等字段，增加 request/correlation；否则约束 payload | 🟡 | 共享，需主控冻结 |
| `app/agents/retriever.py` | 唯一检索 Agent | 验证 RetrievalRequest、传 visibility/request、Outcome→事件、安全失败摘要 | 🟡 | C 实现；D 测试 |
| `app/agents/tutor.py` | Tutor 生成输入 | 从 evidence-aware action 读取投影，构造受限 prompt context | 🟡 | C 实现；D 测试 |
| `app/infrastructure/rag/coordinator.py` | 多源协调/协议 | VisibilityContext、provider outcome、异常归约、保持 sources=None 既有语义 | 🟡 | C 实现；D 回归 |
| `app/infrastructure/rag/pgvector_provider.py` | 真实 vector 检索 | PG/SQLite visibility WHERE、过滤后 LIMIT、provider error 分类 | 🟡 | C 实现；D 集成 |
| 正式 migration / DDL（路径待核实） | 生产 vector_chunks schema | 确立 schema 权威来源、extension/index 前置、存量兼容 | 🟡 / 🔴 待核实 | 主控与 C |
| `tests/unit/infrastructure/test_pgvector_provider.py` | SQLite provider fixture | 从正式 schema 契约派生/共享 fixture；visibility 行为 | 🟡 | D 协作 |
| `tests/integration/test_pgvector_real.py` | 真实 PG fixture | 应用迁移后的表、真实 cross-user/scope 隔离、provider 类型断言 | 🟡 | D 协作 |
| `tests/unit/api/test_chat_new_stack_e2e.py` | chat 新栈 E2E | 检索先行、projection→Tutor、空/失败降级 | 🟡 | D 协作 |
| `tests/integration/test_retriever_integration.py` | Retriever 协作 / 多源回归 | 保持 `sources=None` 多源能力，新增 default-online vector-only 与 outcome 矩阵 | 🟡 | D 协作 |

**明确不改**：不新增回答器；不让 Tutor 直连 Coordinator/Provider；不另造索引或绕过 EmbeddingService、PgVectorProvider、RAGCoordinator、RetrieverAgent、RetrieverAgent.evaluate；不改 RAGAS 评测算法、不重做 OCR/code、多源排序或 LangGraph。

**Phase 2 已实施资产（2026-08-17，🟡 全部为既有文件修改，无新建 app 产物；唯一新建测试文件 `tests/unit/orchestration/test_online_composition.py` 🔴）**：`coordinator.py`、`store.py`、`pgvector_provider.py`、`retriever.py`、`assembly.py`、`chat.py`、`chat_stream.py`；测试 `test_rag.py`、`test_pgvector_provider.py`、`test_retriever.py`、`test_chat_new_stack_e2e.py`、`test_chat_stream_new_stack_e2e.py` 追加/重构，`test_chat_persist.py`、`test_chat_anonymous.py`、`test_chat_session_ownership.py`、`tests/api/test_chat_stream_error.py`、`tests/api/test_chat_stream_realtime.py` 仅机械切换 patch 目标。`events.py`、orchestrator、tutor、critic、spec 文档本轮未动。

---

## 5. 输入 / 输出契约（候选，待冻结项已标注）

### 5.1 RetrievalRequest

| 字段 | 首轮来源 | 后续 rule / conductor 来源 | 约束 |
|---|---|---|---|
| `query` | 原始 `user_message` | 复制或受控派生关联请求 | 非空；不由 Tutor/LLM/最近消息猜测 |
| `top_k` | 冻结默认值 | 复制原请求或受限重试值 | 需验证类型和上限 |
| `purpose` | `teaching` | 复制原请求 | 枚举待冻结 |
| `sources` | 建议固定 `['vector']` | 复制原请求 | 不得在默认 online 回退到 `None` 全搜 |
| `user_id` | 受信任会话 | 不可由 LLM 改写 | 只用于授权上下文 |
| `visibility` | 受信任会话 + scope 真值表 | 复制原请求 | 不得由用户文本决定 |
| `request_id` | 首轮创建 | 继承/受控派生 | 字段落点待主控冻结 |

### 5.2 ActionRequested 保真规则

| 产生路径 | 现状 | P0 必须满足 |
|---|---|---|
| seed path | 只有 action/target | retriever seed 带完整 RetrievalRequest；不并发无证据最终 Tutor action |
| rule path | 只有 action/target | target=retriever 时保留完整请求；target=tutor 时保留已截断 EvidenceProjection |
| conductor path | action/target/via_conductor/reason | 同样不丢 query、visibility、request_id 或 EvidenceProjection |

### 5.3 EvidenceProjection

仅由 Orchestrator 构造并交给 `target=tutor` 的 action：

| 字段 | 用途 | 约束 |
|---|---|---|
| `request_id` | 当前逻辑检索单元关联 | 与 Retriever 输出一致 |
| `retrieval_status` | ok / empty / degraded / failed 等冻结后的状态 | 控制 Tutor 降级分支 |
| `chunks` | 当前回合证据正文 | 有总量、单条、字符/Token 上限 |
| `citations` | 来源、定位、分数等 | 不可由 Tutor 编造 |
| `safe_summary` | 失败/降级的安全摘要 | 不含 `str(exc)` / SQL / 堆栈 |

Tutor 不见 Provider/Coordinator/EmbeddingService 引用，不读未关联 `evidence_pool`。

### 5.4 ProviderOutcome / RetrievalOutcome

| 字段 | 目的 |
|---|---|
| requested providers | 审计实际请求 source |
| attempted / succeeded / failed providers | 归约 empty/degraded/failed |
| stable error code | 内部分类与安全摘要映射 |
| internal diagnostic | 仅日志/观测可见 |
| safe summary | Retriever/Tutor/API 可见 |
| chunks / sources_used | 成功证据与 citation 来源 |

### 5.5 输出事件

- `RetrievedEvidence`：`ok / empty / degraded` 的检索结果，带 request_id 与安全投影所需字段。
- `RetrievalFailed`：`failed / invalid-request`，带稳定错误码和安全摘要，不带原始异常。
- `ActionRequested(target=tutor)`：带 EvidenceProjection；Tutor 只以它生成教学响应。

---

## 6. 方案对照与选择理由

### 6.1 Tutor 获得证据

| | A：Orchestrator 投影（建议） | B：Tutor 订阅证据事件 | C：Tutor 读 `evidence_pool` |
|---|---|---|---|
| 做法 | 编排器构造 evidence-aware tutor action | Tutor 直接看 Retriever 事件 | Tutor 从共享可变状态取证据 |
| 收益 | 保持“编排器路由 / Tutor 生成”边界，便于 request_id 隔离 | 接线短 | 表面代码改动少 |
| 代价 | 需补 Orchestrator 事件分支、投影 schema、Tutor 注入点 | Agent 耦合、绕过现有 action 边界 | 当前无稳定 writer/lifecycle，跨轮污染 |
| 选择 | **A** | 不选 | 不选 |

### 6.2 visibility 强制点

| | A：端到端协议 + Provider 执行过滤（建议） | B：只加 PgVector SQL WHERE | C：Coordinator 统一前过滤 |
|---|---|---|---|
| 做法 | Request/Coordinator/Provider 传 visibility，provider 执行其数据源过滤 | 只修 PG 查询 | Coordinator 先过滤后再调用 provider |
| 收益 | 可验证、符合各 provider 数据所有权 | 改动小 | 可集中逻辑 |
| 代价 | 要扩协议和 fixture；各 provider 要声明能力 | fake/OCR/code 可绕过；SQLite 漏洞 | Coordinator 没有各 provider 原始数据，无法对 PG/OCR/code 通用预过滤 |
| 选择 | **A** | 不选 | 不选 |

### 6.3 默认 online source

| | A：固定 `sources=['vector']`（建议） | B：`sources=None` 全部 provider |
|---|---|---|
| 收益 | 默认在线路径只走已纳入 P0 visibility 的 vector source；不破坏 None 的既有多源语义 | 保留多源自动召回 |
| 代价 | P0 不使用 OCR/code | 产生未受限 provider 隔离旁路 |
| 选择 | **A，待主控冻结** | 不选 |

### 6.4 request/correlation 字段落点

| | A：Event 一等字段 | B：受控 payload 字段 |
|---|---|---|
| 收益 | 类型化、统一校验、回放清晰 | 改动集中 |
| 代价 | 影响大量 Event 构造与测试 | 易在路径保真时遗漏 |
| 选择 | **待主控冻结；共同语义已写入 §5** | **待主控冻结** |

### 6.5 online PgVector composition

| | A：线上 composition 显式要求 pgvector（建议） | B：默认配置 fake，按环境隐式决定 |
|---|---|---|
| 收益 | P0 happy-path 可证明命中 PgVectorProvider；不可用时有明确失败 | 本地测试更方便 |
| 代价 | 部署/集成环境需显式配置和真实依赖 | `sources=['vector']` 仍可能是 fake provider，不能满足 P0 |
| 选择 | **A** | 不选 |

---

## 7. 影响传播

| 维度 | 影响 |
|---|---|
| API / 装配 | chat 与 chat_stream 复用同一 session；需保证两者的 online composition 和 event 因果一致 |
| Event / Orchestrator | Event/request 关联、ActionRequested payload、rule/conductor 保真、检索结果路由都会变 |
| Agent | Retriever 增请求验证/outcome 映射；Tutor 增投影注入；两者仍不互调 |
| Infrastructure | IndexProvider 签名、Coordinator 聚合、PgVector SQL、fake provider 行为、provider capability 受影响 |
| 数据库 | vector_chunks schema/migration、pgvector extension/index 前置、scope/user 的存量兼容待处理 |
| 多源扩展 | `sources=None` 的既有多源测试必须保持；默认 online 不应借修改 None 语义达成 vector-only |
| 离线评测 | `RetrieverAgent.evaluate` 不改评测算法；若共享协议类型变更，要检查 fixture/test double 兼容 |
| 测试 | 单元、协作环、API、SSE、PG integration、SQLite fallback、迁移部署冒烟都需补 |
| 文档 | RAG-C 状态片段已同步；正式 spec 仍需补 §3.1–§3.4 blocker 细节；主清单由主控维护 |
| **Phase 2 实际影响（2026-08-17）** | `/api/chat`、`/api/chat/stream` 在 `rag_backend≠pgvector` 或非 PG dialect 时 fail-fast（503 / SSE 分类错误事件）——**本地 fake 配置下的在线请求将明确失败而非静默 fake**（DEC-007 预期行为）；7 个既有 API 测试文件随之机械切换 patch 目标至 `run_online_agent_session`，2 个 e2e 增加在线配置 fixture；`IndexProvider.search` 抽象签名新增可选 `visibility` 参数（旧二参实现不受影响，仅受限路径要求 vector provider 支持） |

---

## 8. 验证状态表

| 声称 / API / 签名 | 状态 | 依据 |
|---|---|---|
| 默认 seeds 只发 Tutor action | ✅ | `app/orchestration/assembly.py:144-154` |
| rule path 会裁掉请求/投影字段 | ✅ | `app/harness/orchestrator.py:149-154` |
| conductor path 会裁掉请求/投影字段 | ✅ | `app/harness/orchestrator.py:214-223` |
| Event 当前无 request/correlation 字段 | ✅ | `app/harness/events.py:18-35` |
| Orchestrator 当前不路由 evidence / failure | ✅ | `app/harness/orchestrator.py:80-98` |
| Tutor 当前不消费 action payload evidence | ✅ | `app/agents/tutor.py:74-97` |
| Retriever 通过 Coordinator 检索 | ✅ | `app/agents/retriever.py:49-53` |
| Coordinator 默认全搜 sources=None，且吞 provider 异常 | ✅ | `app/infrastructure/rag/coordinator.py:100-131` |
| PgVector PG / SQLite 当前无 visibility 过滤 | ✅ | `app/infrastructure/rag/pgvector_provider.py:111-180` |
| 默认 rag backend 为 fake | ✅ | `app/core/config.py:20-23` |
| pgvector 仅在配置为 pgvector 时装配 | ✅ | `app/infrastructure/rag/coordinator.py:54-84` |
| fixture 当前手工建 vector_chunks | ✅ | `tests/integration/test_pgvector_real.py:48-82`；`tests/unit/infrastructure/test_pgvector_provider.py:40-72` |
| 正式 `vector_chunks` migration 已存在 | ✅ 已核实 | `alembic/versions/20260622_add_vector_chunks_table.py:21-69`（PG vector(2048) / SQLite TEXT；`ix_vector_chunks_scope`）。fixture 未消费它是 BLK-008 问题，不是 migration 缺失 |
| scope 真值表（DEC-001）/ outcome 五态（DEC-008）/ 安全摘要边界（DEC-009）/ composition 三条件（DEC-007） | ✅ 已冻结 | `2026-07-27-rag-p0-confirmed-decisions.md` §2/§8/§9/§10 |
| 错误码集合 / 安全摘要文案 / EvidenceProjection 上限 / citation schema / composition 精确落点 | ⏳ 本 spec 已定义（§G/§H/§F），待主控复核 | `docs/rag-work/specs/2026-07-24-online-rag-p0-repair-spec.md`

---

## 9. 测试矩阵

### 9.1 Happy path

- [ ] `/api/chat`：默认请求先生成完整 RetrievalRequest，再到 Retriever → Coordinator → 实际 PgVectorProvider → evidence-aware Tutor。
- [ ] `/api/chat/stream`：与同步入口拥有同一核心事件因果链；仅多 SSE 投递。
- [ ] spy/assert online provider 实例为 `PgVectorProvider`，且 `rag_backend='pgvector'`；不接受 fake 冒充 happy path。
- [ ] 唯一 sentinel chunk + source 被注入 Tutor 输入，证明不是只发 evidence 事件。
- [ ] PG 中 global / 当前用户私有 / 他人私有 / 未授权 scope 四组数据，过滤后再排序/LIMIT。
- [ ] SQLite 降级分支与 PG 对同一 visibility matrix 得到等价授权结果。
- [ ] 默认 online `sources=['vector']`；OCR/code 不因 `sources=None` 被悄然纳入。

### 9.2 动作与关联保真

- [ ] seed path retriever action 保留 query/top_k/purpose/sources/user_id/visibility/request_id。
- [ ] rule path retriever action 完整复制关联请求。
- [ ] conductor path retriever action 完整复制关联请求。
- [ ] Tutor action 保留截断后的 EvidenceProjection。
- [ ] request_id 在 request、RetrievedEvidence/RetrievalFailed、Tutor action 中一致；parent_id 仍表达直接因果。
- [ ] 两个连续 query 的证据不串轮；扩展检索重试按冻结规则关联原请求。

### 9.3 降级 / 安全

- [ ] 缺 query / 非法 top_k / 缺 visibility / 缺 request_id → `invalid-request`，不执行模糊回读。
- [ ] 成功但零结果 → `empty`，不伪装失败。
- [ ] 单 provider 抛敏感异常 → `failed`，对外不含异常文本、SQL、连接串或堆栈。
- [ ] 多 provider 中一成功一失败 → `degraded`，保留成功 evidence 与受控摘要。
- [ ] all failed → `RetrievalFailed`，Tutor 使用失败降级行为。
- [ ] evidence 过长 / citation 过多 → 投影截断且保留来源规则。
- [ ] 无权限文档永不进入 chunk、去重、citation 或 Tutor 输入。

### 9.4 Schema / deployment

- [ ] 从干净数据库执行正式 migration / DDL 后可完成 pgvector index/search。
- [ ] pgvector extension、vector_chunks 所需列、索引/约束前置均被迁移或明确部署步骤覆盖。
- [ ] PG integration fixture 使用正式 schema 作为消费者，而不是独立漂移的手工 schema。
- [ ] 历史 NULL / 非规范 scope 数据按冻结的兼容策略表现正确。

### 9.5 现有回归

- [ ] `tests/unit/agents/test_retriever.py`
- [ ] `tests/integration/test_retriever_integration.py`（包括 sources=None 多源能力）
- [ ] `tests/unit/infrastructure/test_rag.py`
- [ ] `tests/unit/infrastructure/test_pgvector_provider.py`
- [ ] `tests/integration/test_pgvector_real.py`
- [ ] `tests/unit/api/test_chat_new_stack_e2e.py`
- [ ] chat_stream 对应测试；本窗口尚未逐条核验其现有断言位置

---

## 10. 请求主控复核 / 冻结

### 已冻结（编码依据，无需再次裁决）

- DEC-001：global/private visibility 矩阵 + 历史歧义行 fail closed。
- DEC-003：payload `retrieval_id`（不改 Event schema）；`parent_id` 只管直接因果。
- DEC-004：`max_attempts=1`；不自动 query expansion；检索微回合屏障；同一 retrieval 最多一次最终 Tutor action。
- DEC-007：在线 composition 显式校验 PgVectorProvider + PostgreSQL，fail-fast；fake/SQLite 仅非在线路径。
- DEC-008：outcome 五态 `{ok, empty, degraded, failed, invalid-request}`；low_score → ok 质量子标记。
- DEC-009：payload 只放分类错误码 + 安全摘要；原始异常/SQL/连接串/堆栈只进内部日志。

### 本 spec 已定义、需主控复核（C-08）

| 项 | spec 落点 | 需要主控做什么 |
|---|---|---|
| 在线 composition 精确代码落点与校验实现 | §F（`assembly.py:build_new_stack` 注入 + 三条件校验 + fail-fast） | 复核落点是否可接受 |
| 错误码集合与安全摘要文案枚举 | §G（6 个分类错误码） | 复核枚举与摘要文案 |
| EvidenceProjection 上限与 citation schema | §H（chunk ≤5、单 chunk ≤2000 字符、总 ≤6000、citation ≤5） | 复核默认值 / 与产品对齐 |
| evidence/failure → Orchestrator → Tutor 各分支 | §C | 复核分支与 ActionKind 映射 |
| 三路径保真表与 RetrievalRequest 字段 | §A | 复核字段表 |

### Phase 2 实现采用值（C-11/C-10），请主控追认（§F/§G）

> 主控已授权按 spec 候选值先行最小实现；以下为实现实际采用的值，与 spec §F/§G 候选一致，**需主控复核追认或要求调整**：

| 采用项 | 实现值 | 落点 |
|---|---|---|
| 在线入口 | `run_online_agent_session`（`/api/chat`、`/api/chat/stream` 均已切换）；`run_new_agent_session` 单元路径不受限 | `app/orchestration/assembly.py:185-198`；`app/api/chat.py:20-47`；`app/api/chat_stream.py:26-80` |
| 三条件校验 | `rag_backend=='pgvector'` + `isinstance(vector, PgVectorProvider)` + `dialect_name=='postgresql'`（URL 推导，不建连接） | `app/orchestration/assembly.py:147-169` |
| fail-fast 异常 | `OnlineRAGCompositionError`，`error_code="backend_unavailable"`、`safe_summary="检索服务当前不可用"`；API→503 / SSE→`RAG_BACKEND_UNAVAILABLE` 事件 | `app/orchestration/assembly.py:135-145`；`app/api/chat.py:43-47` |
| 错误码集合 | §G 六码全量落地：`backend_unavailable/db_error/embedding_failed/provider_degraded/invalid_request/timeout`（`embedding_failed` 已定义映射，provider 级细分归类待 Phase 3 观测补强） | `app/agents/retriever.py:30-40` |
| top_k 契约 | 默认 5，上限 10（`TOP_K_MAX`），越界 → invalid-request | `app/agents/retriever.py:24-26,101-122` |
| 受限请求 payload 契约 | `visibility={"user_id": int}`（存在即受限）；受限必须带 `retrieval_id`；`payload.user_id` 与 `visibility.user_id` 不一致按不可信拒绝 | `app/agents/retriever.py:100-122` |

### 窗口 C 建议（供主控参考，不越权决定）

- 默认在线首轮固定 `sources=['vector']`（避免未纳入 visibility 的 OCR/code 经 `sources=None` 旁路）。
- 正式 schema/migration 让 PG/SQLite fixture 消费，替换手工建表（衔接 BLK-008 / I-01）。

---

## 11. 未做事项 / 下一步

### Phase 1C 已完成

- [x] **C-01**：修正 migration 表述（`20260622_vector_chunks` 已存在，fixture 未消费）— 已写入 spec 验证状态表与 §2。
- [x] **C-02**：写清 `RetrievedEvidence/RetrievalFailed → Orchestrator → Tutor` 各分支（spec §C）。
- [x] **C-03**：写清 seed/rule/conductor 的 RetrievalRequest/EvidenceProjection 保真表（spec §A）。
- [x] **C-04**：`retrieval_id` 落点已由 DEC-003 裁决；记录 blast-radius 与三路径保真测试设计（spec §B + §A.2），不再二次裁决。
- [x] **C-05**：写清 global/private visibility 真值表及 PG/SQLite 强制点（spec §D）。
- [x] **C-06**：写清五态归约与 low_score → ok 质量子标记重构（spec §E；`test_retriever.py:84-127` 断言需重构）。
- [x] **C-07**：写清在线 composition 精确代码落点、校验逻辑与诚实失败路径（spec §F）。
- [x] **补充**：错误码集合与安全摘要文案枚举（spec §G）、EvidenceProjection 上限与 citation schema（spec §H）。
- [x] **C-08**：修订后 spec 已提交主控复核（本状态片段 §10 列明待复核项）。

### 主控复核通过后，窗口 C 进入第二轮实现规划

- [x] **C-09**（2026-08-17 完成）：Coordinator `VisibilityContext` + `SearchResult` outcome/provider 失败明细 + 受限路径 vector-only + PgVector/Fake 过滤先于排序/LIMIT。
- **C-10（2026-08-17 完成）**：Retriever 入口校验（invalid-request 不进 provider）+ 五态事件 + `low_score→ok+quality=low` + §G 错误码/安全摘要（无 `str(exc)`）。复审追加：受限请求的 `payload.user_id` 与 `visibility.user_id` 必须同时等于 `WorkspaceState.user_id`；缺失、彼此不一致或共同冒充他人身份均 `invalid-request` 且零 provider 调用。
- [x] **C-11**（2026-08-17 完成）：`run_online_agent_session` 在线 composition 三条件 fail-fast + `/api/chat`、`/api/chat/stream` 接线（503 / SSE 分类错误），单元路径 fake/SQLite 保持可测。
- [ ] Phase 3（C-12~C-17）：默认 seed 检索先行、Orchestrator 路由/EvidenceProjection、Tutor 投影消费、Critic 关联、全链回归与真实 pgvector 冒烟——**均未开始**。

### 当前不做 / 待后续

- [ ] **I-01（待后续）**：PG/SQLite 测试 fixture 仍未消费正式 migration（`alembic/versions/20260622_add_vector_chunks_table.py`），`tests/unit/infrastructure/test_pgvector_provider.py` 与 `tests/integration/test_pgvector_real.py` 仍手工建表。本轮按主控指示**不做** migration consumer 重构；Phase 3 或 BLK-008 处理。
- [ ] provider 级异常细分（`embedding_failed` 的准确归类）目前仅有码位映射，未做异常类型细分；观测补强留待 Phase 3。
- [ ] fail-closed 歧义行的逐行审计日志（spec §D.3 audit 含 retrieval_id）未实现——当前仅过滤 + coordinator 级 warning；Phase 3 引入 retrieval_id 观测后补。
- [ ] 真实 PG（pgvector extension）集成验证未运行（需 Docker PG；`pytest -m integration`）；SQLite 分支与 fake 路径已全覆盖。
- [ ] 不修改主清单，不修改 RAG-A/B/D 状态片段；不新建 RAG，不绕过既有主链。
- [ ] 错误码文案 / EvidenceProjection 上限 / composition 落地的最终值仍以主控追认为准（Phase 2 按 spec 候选值落地，见 §10 追认表）。

---

## 给主控窗口的摘要

- **RAG-C 当前结论**：**Phase 2 C-09/C-10/C-11 最小实现完成（2026-08-17），身份三方锚定复审修复已纳入；全量测试 564 passed / 1 skipped / 8 deselected**；主链与硬约束（Event schema、retrieval_id payload、max_attempts=1、不做 C-12+）全部保持。§F/§G 候选值已落地，待主控追认（§10「Phase 2 实现采用值」表）。
- **本轮变更面**：`app/infrastructure/rag/coordinator.py`（VisibilityContext + outcome 聚合）、`app/infrastructure/rag/store.py`（fake 受限过滤）、`app/infrastructure/rag/pgvector_provider.py`（PG/SQLite visibility 谓词，过滤先于排序/LIMIT）、`app/agents/retriever.py`（入口校验 + 五态 + 安全摘要）、`app/orchestration/assembly.py`（在线 composition + fail-fast）、`app/api/chat.py` / `app/api/chat_stream.py`（在线入口 + 503/SSE 分类错误）。
- **测试**：新增 fake visibility 矩阵、provider 异常 outcome（degraded/failed/timeout）、SQLite visibility + filter-before-limit、Retriever invalid/leak/low-score、在线 composition 校验；`low_score` 断言重构为 `ok+quality=low`；API patch 目标统一切至 `run_online_agent_session`。复审新增受限身份三方锚定测试（缺 `payload.user_id`、payload/visibility 共同冒充其他用户均零 provider 调用）。真实 PG 集成验证未运行（需 Docker）。
- **待主控复核（§F/§G 追认）**：在线入口与三条件校验落点、fail-fast 异常/503 语义、§G 六码错误码与文案、top_k 上限 10、受限 payload 契约——见 §10 追认表。
- **未做**：I-01（fixture 消费正式 migration，按指示留待后续）、provider 异常细分归类、歧义行逐行审计日志、Phase 3 全部（C-12+ seed/路由/投影/Tutor 接线）。
- **当前阻断**：无。等待主控对 §10 追认表复核后进入 Phase 3 规划。
