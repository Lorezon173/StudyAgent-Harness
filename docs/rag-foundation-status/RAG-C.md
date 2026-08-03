# RAG-C 状态：在线 RAG P0 接线修复

> **任务目的**：修复默认在线会话中“检索未启动 / 检索证据未进入 Tutor / 向量检索未按用户与范围隔离”的 P0 断点，同时坚持既有主链：`EmbeddingService → PgVectorProvider → RAGCoordinator → RetrieverAgent → Tutor`。  
> **唯一写者**：窗口 C  
> **主清单（只读）**：[`../designs/2026-07-24-rag-foundation-parallel-todolist.md`](../designs/2026-07-24-rag-foundation-parallel-todolist.md)  
> **相关正式 spec**：[`../designs/2026-07-24-online-rag-p0-repair-spec.md`](../designs/2026-07-24-online-rag-p0-repair-spec.md)  
> **当前状态**：🟡 **第二轮隔离 review：有条件通过**。方向、范围和主要改动面已收敛；仍有 4 项必须由 RAG-C spec 补齐的内部实现契约，另有若干共享/产品契约等待主控或用户冻结。**尚未编码。**

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

### 1.3 第二轮隔离评审结论

- **首轮检索、默认 `sources=['vector']`、动作负载保真、request_id、schema/migration 进入 P0 范围的方向被认可。**
- **第二轮结论为“有条件通过”而不是“通过”**：spec 已从第一轮的“不可编码”提升为“补齐内部契约后可编码”。
- 不应因为 `request_id` 最终落在 Event 一等字段还是受控 payload 尚待主控冻结而否决；这是合理的共享决策。
- 但下列内部约束必须在编码前写成可实现的 spec：
  1. `RETRIEVED_EVIDENCE / RETRIEVAL_FAILED → Orchestrator → Tutor` 的事件路由与投影/注入点；
  2. VisibilityContext 的可执行授权真值表及各 provider 强制点；
  3. `empty / degraded / failed` 的 SearchResult/Provider outcome/安全摘要归约；
  4. 默认在线 composition 如何**实际保证**使用 `PgVectorProvider`，而不是默认 fake vector。

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
| PG 与 SQLite pgvector 测试在 fixture 手工建 `vector_chunks` | `tests/integration/test_pgvector_real.py:48-82`；`tests/unit/infrastructure/test_pgvector_provider.py:40-72` | fixture 是当前显式建表点；正式 migration 唯一来源尚未在本窗口核实 | schema / 测试 |
| 现有 Retriever 协作测试覆盖 ok / empty | `tests/integration/test_retriever_integration.py:113-160`；`tests/unit/agents/test_retriever.py:59-69` | 现有测试仅覆盖当前 ok/empty，不证明安全 visibility 或 provider outcome 语义 | 测试现状 |

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

### 3.5 共享 / 产品阻断：请求关联字段最终落点

**可选方案**：

| 方案 | 做法 | 收益 | 代价 |
|---|---|---|---|
| A：Event 一等字段 | 给 Event 增加 `request_id` / `correlation_id` | 类型显式、所有事件可统一校验 | 影响 Event 构造点与回放测试范围大 |
| B：受控 payload 字段 | 仅在检索相关 payload 内保存 request_id | 改动集中 | 每个生产/消费路径都必须手工保真，遗漏风险高 |

**已确认的共同规则**：
- `parent_id` 表示直接事件因果；
- request/correlation 表示一个逻辑检索单元；
- 一条请求可产生零到多个 evidence/failure 事件；
- 任何 retriever retry/expand 都需可追踪到原请求关系。

**状态**：🟡 需主控冻结；窗口 C 不擅自选择 A/B。

### 3.6 共享 / 产品阻断：scope 授权语义与用户可见降级

需主控或用户冻结：
- global 是否对所有已认证用户可见；
- 私有 scope 的规范值；
- shared/course 是否纳入 P0；
- 缺失 user_id/visibility 的请求是拒绝、匿名公共范围还是系统身份；
- empty/degraded/failed 的 Tutor 文案与 API 安全摘要；
- top_k 默认值与上限、EvidenceProjection 的最大 chunk/字符数。

**状态**：🟡 外部裁决项。窗口 C 已提供候选语义，不应越权冻结。

---

## 4. 拟修改资产

| 文件/资产 | 当前职责 | RAG-C 拟修改内容 | 三色 | 影响 / 协作 |
|---|---|---|---|---|
| `docs/designs/2026-07-24-online-rag-p0-repair-spec.md` | RAG-C 正式设计 | 补 §3.1–§3.4 的四项内部 blocker：事件路由、visibility 真值表、outcome、online composition | 🟡 | 窗口 C；主控审阅 |
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
| 正式 migration 是否已有 vector_chunks 权威来源 | ⏳ 未核实 | 需在实施前单独核验 alembic / production DDL |
| scope 真值表 / 默认 top_k / projection 上限 / 用户可见降级文案 | ⏳ 待主控/用户冻结 | 代码无法推出产品规则 |

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

## 10. 请求主控冻结 / 修订

### C-Freeze-1：ActionRequested 与 EvidenceProjection 标准字段

请主控冻结：
- retriever action 的必填字段及不可改写字段；
- tutor action 的 EvidenceProjection 字段、citation 表示、长度上限；
- seed/rule/conductor 三路径的保真责任；
- `RETRIEVED_EVIDENCE / RETRIEVAL_FAILED` 到 Tutor action 的路由分支和 ActionKind。

### C-Freeze-2：request/correlation 落点

请主控在以下中裁决：
- Event 一等字段；或
- 受控检索 payload 字段。

并冻结：与 parent_id 分工、首次创建、扩展检索的继承/派生规则。

### C-Freeze-3：VisibilityContext 与 scope 真值表

请主控冻结：
- global / private / shared / course 的 P0 范围；
- current user、其他 user、缺失 user_id、缺失 visibility 的行为；
- fake/OCR/code provider 在受限请求下是实现同语义、显式拒绝，还是不允许参与；
- 默认 online 是否固定 `sources=['vector']`（窗口 C 建议：是）。

### C-Freeze-4：ProviderOutcome 与对外安全摘要

请主控冻结：
- empty/degraded/failed/invalid-request 的稳定状态名与错误码；
- attempted/succeeded/failed provider 的事件/日志表现；
- Tutor 与 API 对用户的安全摘要；
- 原始异常、SQL、连接串与堆栈的禁止暴露边界。

### C-Freeze-5：在线 PgVector composition 与 schema 权威来源

请主控冻结 / 指定：
- online production composition 如何强制 `rag_backend='pgvector'` 或等效依赖注入；
- pgvector 不可用时 fail/degrade 的行为，禁止静默 fake fallback；
- `vector_chunks` 正式 migration/DDL 权威来源、fixture 消费路径、历史数据策略；
- 真实 pgvector 跨用户隔离是否作为 P0 终验门槛（窗口 C 建议：是）。

---

## 11. 未做事项 / 下一步

### 窗口 C 可在主控冻结后继续完成

- [ ] 将 §3.1–§3.4 的四项内部 blocker 细化回正式 spec，形成可编码接口与事件路由定义。
- [ ] 核实正式 alembic / migration / production DDL 是否已存在 `vector_chunks` 权威来源；若发现该问题牵出非 RAG-C 任务范围，停止并向主控报告。
- [ ] 核对 chat_stream 现有 SSE 测试断言，评估检索先行时序影响。
- [ ] 在冻结后的字段契约下，制定按文件拆分的第二轮实现计划与测试先行顺序。

### 当前不做

- [ ] 不开始编码，直到 C-Freeze-1 至 C-Freeze-5 中相关契约被主控裁决。
- [ ] 不修改主清单，不修改 RAG-A/B/D 状态片段。
- [ ] 不新建 RAG，不绕过既有 `EmbeddingService / PgVectorProvider / RAGCoordinator / RetrieverAgent / RetrieverAgent.evaluate` 主链。
- [ ] 不替主控决定 scope、request 字段落点、用户可见降级语义或 migration 权威来源。

---

## 给主控窗口的摘要

- **RAG-C 当前结论**：第二轮独立 review 为“有条件通过”；可继续收敛 spec，但不能进入编码。
- **最关键事实**：默认在线 seeds 只发 Tutor；Coordinator 默认 fake 且 `sources=None` 全搜；Orchestrator 不消费 evidence/failure；Tutor 不读 action payload；PgVector 查询不按 scope/user 过滤；Coordinator 吞 provider 异常。
- **窗口 C 推荐方案**：检索先行、vector-only 默认 source、Orchestrator EvidenceProjection、端到端 visibility、结构化 outcome、线上显式 pgvector composition、正式 schema/migration 作为验收前提。
- **需主控冻结**：payload/projection、request/correlation 落点、scope 真值表与默认 sources、outcome/安全摘要、online pgvector composition 与 schema 权威来源。
- **当前 blocker**：§3.1–§3.4 是 RAG-C spec 内部需要继续补齐的内容；§3.5–§3.6 是共享/产品裁决项。主控冻结后，窗口 C 应先补可编码 spec，再进入第二轮实现计划。
