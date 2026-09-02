# 在线 RAG 主链 P0 修复规范（RAG-C spec）

> 日期：2026-07-24 创建；**2026-07-29 Phase 1C 修订**
> 状态：**已对齐 DEC-001/003/004/007/008/009；提交主控复核（C-08）。复核通过前不得编码。**
> 唯一写者：RAG-C 窗口；主控回应包：M-03（`docs/rag-work/plans/2026-07-24-rag-foundation-parallel-todolist.md` §9）
> 设计形态：三层文字规划；本文描述目标、契约、代码落点和验收，不提供实现代码。
> 已冻结决策源：`docs/rag-work/plans/2026-07-27-rag-p0-confirmed-decisions.md`

---

## 资产清单与三色血缘

| 名字 | 归属子系统 | 当前功能 | 触发 / 入口 | 位置 | 影响 |
|---|---|---|---|---|---|
| `run_new_agent_session` / `build_new_stack` | 编排层 | 装配 5 Agent + Orchestrator，创建种子事件并跑协作环 | 两个 chat API 共用 | `app/orchestration/assembly.py:100-167` | 🟡 |
| `run_collab_loop` | 编排层 | 优先级队列分发事件、Orchestrator 钩子 | `run_new_agent_session` | `app/orchestration/collab_loop.py:31-78` | 🟢 |
| `Orchestrator.on_event/_on_tick/_translate_conductor_decision` | Harness | 观察→动作路由；当前不消费检索结果 | 协作环钩子 | `app/harness/orchestrator.py:80-223` | 🟡 |
| `RetrieverAgent` | Agent 层 | 消费 `target=retriever` 动作，调 Coordinator，发证据/失败 | `ActionRequested(target=retriever)` | `app/agents/retriever.py:36-101` | 🟡 |
| `TutorAgent` | Agent 层 | 仅消费 `target=tutor` 动作并生成教学文本 | `ActionRequested(target=tutor)` | `app/agents/tutor.py:32-97` | 🟡 |
| `RAGCoordinator` / `IndexProvider` | 基础设施层 | 多源聚合检索；当前 `sources=None` 全搜、异常静默吞 | `RetrieverAgent` 调用 | `app/infrastructure/rag/coordinator.py:46-131` | 🟡 |
| `PgVectorProvider` | 基础设施层 | 索引写 `user_id/scope`，搜索无过滤 | Coordinator 的 pgvector 分支 | `app/infrastructure/rag/pgvector_provider.py:60-187` | 🟡 |
| `vector_chunks` 正式迁移 | 数据库 | 建 `vector_chunks` 表（PG vector(2048) / SQLite TEXT） | `alembic upgrade head` | `alembic/versions/20260622_add_vector_chunks_table.py:21-69` | 🟢 已存在（fixture 未消费） |
| PG/SQLite provider 测试 | 测试 | 当前 fixture 手工建表，未消费正式 migration | pytest | `tests/integration/test_pgvector_real.py:48-82`；`tests/unit/infrastructure/test_pgvector_provider.py:40-72` | 🟡 |
| `Event` / 事件所有权 / 优先级 | Harness | 只有 `parent_id`，无 `retrieval_id` 一等字段 | 协作环 | `app/harness/events.py:18-28,63-94` | 🟢 不改 schema（DEC-003） |
| 新栈 chat E2E 测试 | 测试 | 当前断言 Tutor 首轮路径 | pytest | `tests/unit/api/test_chat_new_stack_e2e.py` | 🟡 |
| Retriever 单测 | 测试 | 当前断言 `low_score` 状态 | pytest | `tests/unit/agents/test_retriever.py:84-127` | 🟡 |
| `settings.rag_backend` | 核心配置 | 默认 `"fake"`，pgvector 需显式切换 | 配置加载 | `app/core/config.py:21` | 🟡 |
| 额外回答器 / Tutor 直连检索 | 不适用 | 不新增 | 不适用 | 不适用 | 🔴 禁止新建 |

---

## 验证状态表（Phase 1C 更新）

| 事实或决策 | 状态 | 依据 / 说明 |
|---|---|---|
| 同步与 SSE chat 入口均进入同一新栈会话函数 | ✅ 已核实 | `app/api/chat.py:34-37`；`app/api/chat_stream.py:47-50` 均 `run_new_agent_session`；SSE 仅多 `cb` 事件透出。 |
| **正式 `vector_chunks` Alembic migration 已存在** | ✅ 已核实（C-01 修正） | `alembic/versions/20260622_add_vector_chunks_table.py:21-69`：PG 用 `CREATE EXTENSION vector` + `vector(2048)` + `ix_vector_chunks_scope`；SQLite 退化 embedding 为 TEXT。**问题是 fixture 手工建表未消费它，不是 migration 缺失。** |
| PG integration fixture 手工建表 | ✅ 已核实 | `tests/integration/test_pgvector_real.py:48-82` 在 fixture 内 `CREATE TABLE IF NOT EXISTS vector_chunks`，未走正式 migration。 |
| SQLite provider fixture 手工建表 | ✅ 已核实 | `tests/unit/infrastructure/test_pgvector_provider.py:40-72` 同样手工建表。 |
| 默认会话初始动作只定向 Tutor，未定向 Retriever | ✅ 已核实 | `app/orchestration/assembly.py:144-154` 种子含 `UserMessage`、`TopicEntered`、`target=tutor` 的 `ActionRequested`，无检索动作。 |
| `retrieval_id` 落点已由 DEC-003 裁决：受控 payload，不改 Event schema | ✅ 已确认（冻结） | `2026-07-27-rag-p0-confirmed-decisions.md` §4；`app/harness/events.py:18-28` Event 仅 `parent_id`/`metadata`，无 `retrieval_id` 一等字段。 |
| Orchestrator 当前不消费 `RETRIEVED_EVIDENCE`/`RETRIEVAL_FAILED` | ✅ 已核实 | `app/harness/orchestrator.py:80-98`：非观察类、非 TICK、非 CONDUCTOR_DECIDED 一律返回 `[]`。 |
| 规则路径 `ActionRequested` 只产 `action/target` | ✅ 已核实 | `app/harness/orchestrator.py:149-154`；`_target_of` 仅按 action 前缀定向（`orchestrator.py:157-163`）。 |
| Conductor 翻译 `ActionRequested` 只产 `action/target/via_conductor/reason` | ✅ 已核实 | `app/harness/orchestrator.py:214-223`。 |
| Retriever 失败分支硬编码 `"timeout"` + `str(exc)` | ✅ 已核实 | `app/agents/retriever.py:54-63`：`payload={"reason": str(exc), "retrieval_status": "timeout", ...}`。 |
| Retriever 当前只有 `empty/low_score/ok` 三态 | ✅ 已核实 | `app/agents/retriever.py:79-85`；无 `degraded/failed/invalid-request`。 |
| 现有 Retriever 单测断言 `low_score` 状态 | ✅ 已核实 | `tests/unit/agents/test_retriever.py:105-128` 用 mock 低分 provider 断言 `retrieval_status == "low_score"`。 |
| Tutor 只消费 `target=tutor` 动作，输入仅 topic/mode | ✅ 已核实 | `app/agents/tutor.py:32-97`；`_ask`/`_explain` 的 LLM 输入为 `主题：{current_topic}`/`主题 + 模式`，不读 evidence。 |
| Coordinator `sources=None` 全搜 provider，异常 `continue` 吞 | ✅ 已核实 | `app/infrastructure/rag/coordinator.py:100-131`。 |
| `IndexProvider.search` / `PgVectorProvider.search` 无 visibility 参数与 SQL 过滤 | ✅ 已核实 | `app/infrastructure/rag/coordinator.py:34-37`；`app/infrastructure/rag/pgvector_provider.py:111-180`。 |
| 默认 `rag_backend="fake"`，pgvector 需显式切换 | ✅ 已核实 | `app/core/config.py:21`；`app/infrastructure/rag/coordinator.py:54-84` 注册分支。 |
| 在线 composition 精确代码落点与校验实现 | ⚠️ 本 spec 定义（C-07），主控复核后冻结 | 见 §F。 |
| 错误码集合与安全摘要文案枚举 | ⚠️ 本 spec 定义（DEC-009 边界已冻结），主控复核 | 见 §G。 |
| EvidenceProjection 上限与 citation schema | ⚠️ 本 spec 定义，主控/产品复核 | 见 §H。 |
| scope 授权矩阵（global/private + 历史歧义 fail closed） | ✅ 已确认（DEC-001 冻结） | `2026-07-27-rag-p0-confirmed-decisions.md` §2；`2026-07-24-rag-foundation-parallel-todolist.md` §4 BLK-001。 |
| outcome 五态 `{ok, empty, degraded, failed, invalid-request}`；low_score→ok 质量子标记 | ✅ 已确认（DEC-008 冻结） | `2026-07-27-rag-p0-confirmed-decisions.md` §9。 |
| 在线 composition 必须 PgVectorProvider + PostgreSQL，不满足 fail-fast | ✅ 已确认（DEC-007 冻结） | `2026-07-27-rag-p0-confirmed-decisions.md` §8。 |
| 安全摘要边界：分类码 + 摘要对外，原始异常对内 | ✅ 已确认（DEC-009 冻结） | `2026-07-27-rag-p0-confirmed-decisions.md` §10。 |

---

# 第一层：模块总览

## 1. 目标

补齐在线默认会话的受控 RAG 数据流，使默认在线课程知识检索遵循唯一主链：

`用户消息 → RetrieverAgent → RAGCoordinator → PgVectorProvider（vector source） → RetrievedEvidence/RetrievalFailed → Orchestrator 检索路由与受控投影 → TutorAgent`

OCR/code 等 provider 不在本 P0 中被删除或重做；DEC-001 的 visibility 仅约束参与受限检索的 provider，`sources=None` 的既有多源语义与回归测试（`tests/integration/test_retriever_integration.py:202-230`）保持不变，但**默认在线首轮固定 `sources=['vector']`**，避免未纳入 visibility 契约的 provider 被自动带入。

完成后，系统应同时满足：

1. 默认会话能以完整、可回放的检索请求启动检索，且该请求在 seed/rule/conductor 三条路径不被裁剪；
2. 检索结果（证据或失败）由 Orchestrator 消费并投影为 evidence-aware 的 Tutor 动作；同一 `retrieval_id` 最多一次最终 Tutor action；
3. 可见性过滤（DEC-001）在所有被允许参与的 provider 的 PostgreSQL 与 SQLite 查询中一致执行，且先于排序/去重/LIMIT/citation/Tutor 输入；
4. 检索结果状态为 DEC-008 五态，且内部失败信息与对外安全摘要分离（DEC-009）；
5. 在线 composition 显式装配 PgVectorProvider + PostgreSQL，不满足则 fail-fast（DEC-007），不静默回退 fake。

## 2. P0 工作范围

- **对齐 DEC-003**：以受控 payload `retrieval_id` 作为一次逻辑检索单元的关联标识，不扩展 `Event` schema；`parent_id` 只表达直接物理因果。
- **对齐 DEC-004**：初始 `attempt=1`、`max_attempts=1`；不自动执行 `retriever_expand_query`；采用检索微回合屏障；同一 retrieval 最多一次最终 Tutor action。
- **默认 seeds 改造**：删除无证据抢跑的最终 Tutor 种子，改为完整 Retriever `ActionRequested`（含 `retrieval_id`、`query`、`top_k`、`purpose`、`sources=['vector']`、可见性上下文）。
- **Orchestrator 检索路由**：消费 `RETRIEVED_EVIDENCE`/`RETRIEVAL_FAILED`，为每个 `retrieval_id` 维护会话内路由状态，并在正确时点生成 evidence-aware 的 `ActionRequested(target=tutor)`。
- **三路径保真**：seed / rule / conductor 三条路径都必须完整保留 RetrievalRequest 或 EvidenceProjection（C-03/C-04）。
- **对齐 DEC-001**：定义 `global/private` 可见性真值表与 PG/SQLite 强制点，过滤先于排序/去重/LIMIT（C-05）。
- **对齐 DEC-008**：`empty/degraded/failed/invalid-request/ok` 五态归约；`low_score` 重构为 `ok + quality=low` 子标记（C-06）。
- **对齐 DEC-007**：在线 composition 入口显式注入 `PgVectorProvider`，校验 `rag_backend=="pgvector"` 且 dialect 为 postgresql；不满足 fail-fast（C-07）。
- **对齐 DEC-009**：payload 只含分类错误码 + 安全摘要；`str(exc)`/SQL/连接串/堆栈只进内部日志；枚举错误码集合与摘要文案（§G）。
- **schema/fixture 收敛**：让 PG/SQLite 测试消费正式 migration 契约，不再各自漂移（衔接 BLK-008 / I-01）。
- 增补单元、协作环、API、真实 pgvector 集成验证，覆盖跨用户隔离、多轮证据隔离与动作 payload 保真。

## 3. 非目标

本 P0 明确不做：

- 不让 Tutor 直接调用 Coordinator、Provider、Embedding 服务或数据库；不另造回答器。
- 不扩展 `Event` schema（DEC-003）；不新增 `ingestion_runs` 表或改 `/api/knowledge`。
- 不自动 query expansion（DEC-004：`max_attempts=1`）；`retriever_expand_query` 不作为首轮入口。
- 不定义 shared/course 授权语义（BLK-011 后置）；不重做离线 ingestion、LightRAG、跨源排序、RAGAS 指标或 LangGraph 骨架。
- 不向客户端暴露 Provider 原始异常、SQL 信息或堆栈（DEC-009 边界已冻结）。
- 不把 benchmark `paragraph_id` 升格为生产 `doc_id/chunk_id`（DEC-005/011 边界）。

---

## 4. 已冻结决策 → 本 spec 落点映射

| 决策 | 冻结内容 | 本 spec 落点 |
|---|---|---|
| DEC-001 | global/private 最小矩阵；历史歧义行 fail closed；visibility 类型化单向传递；过滤在排序/LIMIT 前 | §D（C-05）真值表与强制点 |
| DEC-003 | payload `retrieval_id`，不改 Event schema；parent_id 只管直接因果；Orchestrator 唯一投影边界 | §A/§B（C-03/C-04） |
| DEC-004 | `max_attempts=1`；不自动 expansion；检索微回合屏障；同一 retrieval 最多一次最终 Tutor action | §C（C-02）分支与屏障 |
| DEC-007 | 在线 composition 显式校验 PgVectorProvider + PostgreSQL，fail-fast，不静默 fake | §F（C-07）精确落点 |
| DEC-008 | outcome 五态；low_score→ok 质量子标记 | §E（C-06）归约表 |
| DEC-009 | 分类码 + 安全摘要对外；原始异常/SQL/堆栈对内 | §G 错误码与摘要枚举 |

---

# 第二层：契约与子模块

## A. ActionRequested 保真契约（C-03）

### A.1 RetrievalRequest 字段表（首轮 seed / rule / conductor 统一）

| 字段 | 首轮 seed 来源 | rule/conductor 后续来源 | Retriever 输出 / Tutor 投影用途 | 约束 |
|---|---|---|---|---|
| `retrieval_id` | 初始 Retriever `ActionRequested.id`（DEC-003） | 继承关联原请求 | evidence/failure/Tutor projection 关联 | 一次逻辑检索单元；同 retrieval 最多一次最终 Tutor action |
| `query` | 原始 `user_message` | 仅复制或受控派生关联原请求 | Provider 查询、审计 | 非空；不得由 Tutor/LLM/Conductor 猜测 |
| `top_k` | 冻结后的默认值（上限受保护） | 复制原请求或受限重试值 | Provider 限额 | 必须验证类型与上限 |
| `purpose` | `teaching` | 复制原请求 | Critic 质量评估/降级策略 | 枚举待冻结（P0 仅 `teaching`） |
| `sources` | P0 固定 `['vector']` | 复制原请求 | Coordinator 选择 provider | 默认在线不得回退为未受限 `sources=None` 全搜 |
| `user_id` | 受信任会话上下文（`get_current_user` 验签） | 不可由 rule/conductor/LLM/用户文本改写 | VisibilityContext | 不得来自 `ChatRequest.user_id` 或 query |
| `visibility` | 受信任会话上下文派生（global + 当前 user 私有） | 复制原请求 | Provider 授权过滤 | 具体 scope 集合见 §D |
| `attempt` | 初始 `1` | 仅 Orchestrator 维护 | 审计 / 重试上限 | `max_attempts=1`；Conductor/LLM 不得改写 |

### A.2 三路径保真规则

| 产生路径 | 当前行为（已核实） | P0 必须满足 |
|---|---|---|
| **seed path** | 只放 `action/target`，且是 tutor 动作（`assembly.py:144-154`） | 删除无证据 tutor 种子；改为完整 Retriever `ActionRequested`，携带 A.1 全部字段 |
| **rule path** | `_on_tick` 只产 `action/target`（`orchestrator.py:149-154`） | 若 target=retriever：完整复制关联 RetrievalRequest；若 target=tutor：完整携带 EvidenceProjection（§C/§H）。缺字段不得静默裁剪后继续 |
| **conductor path** | `_translate_conductor_decision` 只产 `action/target/via_conductor/reason`（`orchestrator.py:214-223`） | 同样保真；不得因转译丢失 `retrieval_id`、query、visibility 或 evidence 投影 |

## B. `retrieval_id` 与 `parent_id`（C-04，DEC-003）

- `parent_id` 继续表达“此事件直接由哪一个事件触发”的事件树因果（`events.py:25`）。
- `retrieval_id` 表达“这条检索请求及其所有证据、重试与 Tutor 投影属于哪个逻辑检索单元”，**只存在于受控 payload**，不新增 `Event` 一等字段（DEC-003）。
- 初始 Retriever `ActionRequested.id` 即本次 `retrieval_id`；`RetrievedEvidence`、`RetrievalFailed`、未来 retry 与 Tutor projection 都在各自 payload 携带该值。
- 一个 `retrieval_id` 可产生零到多个 evidence/failure 事件，它们可有不同 `parent_id`，但必须拥有同一 `retrieval_id`。
- `attempt` 只由 Orchestrator 维护；P0 `max_attempts=1`，不自动派生重试。
- **blast-radius（DEC-003 生效后）**：
  - `assembly.py` 种子：首次创建 `retrieval_id`；
  - `retriever.py` 输出：evidence/failure payload 携带 `retrieval_id`；
  - `orchestrator.py`：为每个 `retrieval_id` 维护路由状态，并把 `retrieval_id` 写进 Tutor 动作 payload；
  - `tutor.py`：从动作 payload 读取 `retrieval_id` 与 EvidenceProjection（不改其订阅集）；
  - `critic.py`：`RAGQualityAssessed` 需携带 `retrieval_id`（P0 内 quality 仅作低分降级标记，不驱动第二轮检索）。
  - **不生效**：`events.py` 的 `Event` dataclass、`EVENT_PRIORITY`、`EVENT_OWNERSHIP`（不改）。

## C. `RetrievedEvidence`/`RetrievalFailed → Orchestrator → Tutor` 分支（C-02，DEC-004）

### C.1 Orchestrator 检索路由状态（每 `retrieval_id`）

Orchestrator 为每个会话内的 `retrieval_id` 维护会话内路由状态，至少包含：

| 字段 | 含义 |
|---|---|
| `request` | 原始 RetrievalRequest（保真快照） |
| `result` | 最近一次检索结果（evidence 或 failure 摘要） |
| `attempt` | 当前尝试数（P0 固定 1） |
| `quality` | Critic 的 quality observation（可 unavailable） |
| `direct_parent` | 直接因果 ID |
| `final_tutor_action_emitted` | 是否已发出最终 Tutor 动作（同一 retrieval 只发一次） |

### C.2 各结果分支 → Tutor 动作

| 分支（DEC-008 状态） | Orchestrator 行为 | Tutor 动作 payload（EvidenceProjection） |
|---|---|---|
| **ok**（含 `quality=low` 子标记） | 构造有证据投影的 Tutor 动作 | `retrieval_id`、`retrieval_status="ok"`、`quality`、已授权 chunks、citations、`sources_used`、`safe_summary` |
| **empty** | 构造无证据降级 Tutor 动作 | `retrieval_id`、`retrieval_status="empty"`、chunks=[]、`safe_summary`（“未找到可用课程证据”） |
| **degraded** | 构造部分证据 + 降级标记 Tutor 动作 | `retrieval_id`、`retrieval_status="degraded"`、成功来源的已授权 chunks、`provider_errors` 摘要、`safe_summary` |
| **failed** | 构造失败说明 Tutor 动作 | `retrieval_id`、`retrieval_status="failed"`、chunks=[]、分类错误码、`safe_summary` |
| **invalid-request** | 检索入口拦截，不进入 provider；直接产生受控失败 Tutor 动作 | `retrieval_id`、`retrieval_status="invalid-request"`、分类错误码、`safe_summary` |

> 所有分支都必须产出一份受控 Tutor 回复，不得落入 `_EMPTY_REPLY_FALLBACK`（`assembly.py:63`）空回复 fallback（DEC-004 验收）。

### C.3 检索微回合屏障（DEC-004）

- `RetrievedEvidence`/`RetrievalFailed` 到达后，Critic 的 `RAGQualityAssessed`（quality observation，priority=10，`events.py:48`）优先于 barrier tick 处理。
- Orchestrator 在 Tick 弹出时基于完整观察集做**唯一一次**最终 Tutor action 路由。
- Critic 没有输出 quality 时，不得卡死：按机械检索状态（ok/empty/degraded/failed）继续，并标记 `quality=unavailable`。
- 重复 evidence、迟到 quality、重复 tick 不得产生第二份最终回复（由 `final_tutor_action_emitted` 保证）。

## D. visibility 真值表与强制点（C-05，DEC-001）

### D.1 已确认授权矩阵（DEC-001）

| 存储行 | 已认证请求用户 | P0 行为 | 说明 |
|---|---|---|---|
| `scope=global, user_id=NULL` | 任意已认证用户 | **可见** | 唯一规范公共形态 |
| `scope=private, user_id=当前用户` | 同一用户 | **可见** | 唯一规范私有形态 |
| `scope=private, user_id=其他用户` | 其他用户 | **不可见** | 防止跨用户泄漏 |
| `scope=private, user_id=NULL` | 任意 | **不可见 + 审计** | 所有者缺失，fail closed |
| `scope=global, user_id≠NULL` | 任意 | **不可见 + 审计** | 历史组合语义歧义，fail closed |
| 未知/缺失 scope | 任意 | **不可见 + 审计** | 禁止猜测未知授权语义 |
| 任意受限行 | 缺失认证身份 | **invalid-request，不检索** | 可信身份不得从请求体/用户文本/LLM 补猜 |

### D.2 冻结边界

1. P0 RAG scope 仅支持 `global` 与 `private`；不复用语义不同的 `MemoryScope`（`enums.py:68-74`）。
2. 可信身份只来自 `get_current_user` 的 JWT 验签及用户存在性校验；不得使用 `ChatRequest.user_id`、用户文本或 LLM 输出。
3. visibility 使用类型化上下文沿 API → 编排 → Retriever → Coordinator → Provider **单向传递**；Provider 不反向依赖 API、WorkspaceState 或 Orchestration。
4. 过滤必须在排序、去重、`LIMIT`、citation、Tutor 输入**之前**执行。

### D.3 PG/SQLite 强制点

- **PostgreSQL 查询**（`pgvector_provider.py:131-157`）：`WHERE (scope='global' AND user_id IS NULL) OR (scope='private' AND user_id=:uid)`，且 `uid` 来自受信任会话上下文；`LIMIT :top_k` 在过滤后执行。
- **SQLite 降级分支**（`pgvector_provider.py:159-180`）：同样执行同一可见性谓词，保证测试语义与 PG 一致。
- **强制点次序**：Provider 先过滤 → 再 embedding 距离/字符匹配排序 → 再 `LIMIT`/去重；未授权高相似 chunk 不得抢占 top-k。
- **去重契约**（`coordinator.py:119-123`）：只对已通过授权过滤的结果去重；不把不同 scope/source 的未授权结果纳入去重候选。
- **audit**：被 fail-closed 拦截的歧义行（`private+NULL`、`global+owner`、未知 scope）写入内部日志（含 `retrieval_id`），不含内容原文（DEC-009）。

## E. outcome 五态归约（C-06，DEC-008）

### E.1 五态定义与归约

| 状态 | 触发条件（Provider/Aggregate 归约） |
|---|---|
| `ok` | 真实 provider 正常返回且有结果；`quality=low` 是质量子标记，不是独立状态（原 `low_score` 重构） |
| `empty` | 真实 provider 正常返回但无结果（真没数据） |
| `degraded` | 多 provider 部分失败 / SQLite 字符匹配降级 / embedding 降级但仍可用 |
| `failed` | 全部 provider 失败或基础设施异常（DB 连不上、embedding 服务挂） |
| `invalid-request` | 缺认证身份 / 无授权 scope / 无效 query；在检索入口拦截，不进入 provider 调用 |

### E.2 归约规则（Coordinator 聚合）

| Provider 结果组合 | 聚合 outcome | `sources_used` / 内部日志 |
|---|---|---|
| 至少一个 provider 成功且有结果，其余成功无结果 | `ok` | `sources_used` 含成功来源 |
| 至少一个成功且无失败，但部分 provider 返回空 | `empty`（如全部空）或 `ok`（如有一个非空） | 空来源如实记录 |
| 至少一个成功，至少一个异常 | `degraded` | `sources_used` 仅含成功来源；失败 provider 进内部日志 |
| 全部异常 | `failed` | 失败 provider 与异常进内部日志 |
| 缺身份 / 无授权 scope / 空 query | `invalid-request` | 在入口拦截，不调用 provider |

### E.3 现状重构点（已核实）

- `retriever.py:79-85` 当前 `empty/low_score/ok` 三态判定 → 重构为五态判定：`max_score < LOW_SCORE_THRESHOLD` 不再产出独立 `low_score` 状态，改为 `ok + quality="low"`。
- `retriever.py:54-63` 异常分支硬编码 `"timeout"` + `str(exc)` → 由 Coordinator 结构化失败（degraded/failed）驱动，payload 只含分类错误码 + 安全摘要（DEC-009）。
- `test_retriever.py:105-128` 断言 `retrieval_status == "low_score"` → 改为断言 `ok` + `quality=="low"`。
- `coordinator.py:111-117` 的 `except Exception: continue` → 记录失败 provider（内部日志）并据此判定 degraded/failed，不再静默吞没。

## F. 在线 composition 精确落点与 fail-fast（C-07，DEC-007）

### F.1 精确代码落点

在线 composition 的检索链装配点即 `build_new_stack` 内 `RetrieverAgent()` 的构造处（`assembly.py:121`）。当前 `RetrieverAgent()` 默认构造 `RAGCoordinator()`，后者 `_register_default_vector_provider` 依据 `settings.rag_backend`（`config.py:21` 默认 `"fake"`）选择 pgvector 或 fake 包装（`coordinator.py:54-84`）。

**落点判定**：必须在在线装配路径显式注入 `RAGCoordinator(store=..., vector_provider=...)`（或等价依赖注入），使 vector provider 实际为 `PgVectorProvider`，并校验：

1. `settings.rag_backend == "pgvector"`；
2. 装配得到的 vector provider 的 class 为 `PgVectorProvider`；
3. 运行时 DB dialect 为 `postgresql`。

### F.2 校验实现位置（候选，主控复核）

- **首选**：`assembly.py:build_new_stack` 在创建 `RetrieverAgent` 前显式构造在线 `RAGCoordinator`；对 `settings.rag_backend`、provider class、dialect 三条件校验，任一不满足立即抛出明确异常（fail-fast）。
- **诚实失败路径**：不满足时不进入检索；错误信息经内部日志记录（含 trace/session），API 层收到的是可识别的 `backend_unavailable` 类分类错误（DEC-009），不静默回退 fake。
- 默认配置 `rag_backend="fake"` 可保留给本地/测试（`config.py:21` 不改），但在线 composition 不得依赖该默认值静默通过；**非在线路径**（单元/集成测试、离线 bench）仍可使用 fake/SQLite，不受本决策限制。

### F.3 校验时机

- 在线请求进入 `run_new_agent_session` 后、种子创建前完成校验；校验失败即 fail-fast，不进入协作环。
- 提供可测试的校验函数（可单测），供 BLK-007 admission gate 第 1–3 项直接消费（DEC-010）。

## G. 错误码集合与安全摘要（DEC-009）

### G.1 分类错误码枚举（本 spec 定义，主控复核）

| 错误码 | 适用状态 | 含义 | 摘要（对外安全文案示例） |
|---|---|---|---|
| `backend_unavailable` | `failed` | 在线 composition 校验失败（非 pgvector / 非 PG dialect） | “检索服务当前不可用” |
| `db_error` | `failed` | Provider 数据库连接/查询异常 | “知识库服务暂时不可用” |
| `embedding_failed` | `failed`/`degraded` | embedding 服务调用失败 | “知识索引服务暂时不可用” |
| `provider_degraded` | `degraded` | 多 provider 部分失败 | “部分知识来源不可用” |
| `invalid_request` | `invalid-request` | 缺认证身份 / 无授权 scope / 无效 query | “当前请求无法检索知识” |
| `timeout` | `failed` | 检索超时（保留原语义，但不再被所有异常复用） | “检索超时，请稍后重试” |

### G.2 边界约束

- `RetrievalFailed` / `EvidenceProjection.safe_summary` / API 响应**只允许**出现上表分类错误码与安全摘要；禁止 `str(exc)`、SQL、连接串、堆栈。
- 原始异常、SQL、连接串、堆栈只进**结构化内部日志**，且带 `trace_id` / `retrieval_id` 关联。
- `retriever.py:58` 的 `"reason": str(exc)` 必须移除，替换为分类错误码 + 安全摘要。
- 错误码集合与摘要文案枚举提交主控复核后方可落地（DEC-009 §10.3）。

## H. EvidenceProjection 上限与 citation schema（本 spec 定义，主控/产品复核）

### H.1 字段结构

```text
EvidenceProjection = {
  retrieval_id: str,
  retrieval_status: "ok" | "empty" | "degraded" | "failed" | "invalid-request",
  attempt: int,
  quality: "high" | "low" | "acceptable" | "unavailable",   # DEC-008 质量子标记
  chunks: [ChunkProjection],
  citations: [Citation],
  sources_used: list[str],
  safe_summary: str,          # 安全摘要（DEC-009）
}
ChunkProjection = { content: str, source: str, score: float }
Citation = { content: str, source: str, score: float }
```

### H.2 上限（建议默认，待主控/产品冻结）

| 上限 | 建议值 | 理由 |
|---|---|---|
| 最大 chunk 数（进 Tutor 投影） | ≤ 5（= 默认 top_k） | 与检索限额一致，控制上下文膨胀 |
| 单 chunk 最大字符数 | ≤ 2000 | 防单块过长淹没 prompt |
| 总投影字符数上限 | ≤ 6000 | 防止 evidence 总长击穿 LLM 上下文 |
| citation 数 | ≤ 5 | 与 chunk 数一致 |
| `content` 禁止字段 | 原始异常 / SQL / 连接串 / 堆栈 | DEC-009 |

### H.3 消费边界

- Tutor 只从 `ActionRequested(target=tutor)` payload 读取 EvidenceProjection；不持有 Coordinator/Provider/Embedding 引用，不读未关联的 `evidence_pool`（`workspace_state.py:20` 保持非权威观测缓存，需单独定义 writer 与生命周期）。
- 投影必须与 `retrieval_id` 关联校验；第二轮请求不得消费第一轮证据。

## I. 验证与可观测性

- **可观测**：内部日志带 `retrieval_id`、`attempt`、outcome、provider 失败明细；`sources_used` 如实反映成功来源。
- **测试**：显式区分 fake 与 pgvector 配置；真实 pgvector 验证不能由 fake 测试代替；PG/SQLite 测试消费正式 migration 契约（BLK-008 / I-01）。
- **失败语义**：测试中的 Provider 故障必须观察到 `degraded`/`failed` 语义，不接受“返回空结果即通过”。

---

# 第三层：详细实施计划（文字设计）

## 1. 先冻结的契约（本 spec 已定义，主控复核通过即冻结）

1. **ActionRequested 保真契约**（§A）：三路径字段表与保真规则。
2. **关联契约**（§B）：`retrieval_id` 落点与 `parent_id` 分工（DEC-003）。
3. **检索路由与分支**（§C）：evidence/failure 各分支 → Tutor 动作；微回合屏障；同 retrieval 一次最终回复（DEC-004）。
4. **visibility 真值表与强制点**（§D，DEC-001）。
5. **outcome 五态归约**（§E，DEC-008）与 **错误码/摘要枚举**（§G，DEC-009）。
6. **composition 落点与 fail-fast**（§F，DEC-007）与 **EvidenceProjection 上限/citation**（§H）。

## 2. 实施默认会话检索先行时序（对齐 DEC-004）

- 删除 `assembly.py:150-153` 的无证据最终 Tutor 种子；改为完整 Retriever `ActionRequested`（含 `retrieval_id`=本事件 id、`query`=user_message、`top_k`、`purpose="teaching"`、`sources=["vector"]`、`user_id`、`visibility`、`attempt=1`）。
- Retriever 的成功/空/降级/失败结果都成为 Orchestrator 可识别的完成信号；evidence/failure 与请求共享 `retrieval_id`。
- Orchestrator 为每个 `retrieval_id` 维护路由状态（§C.1），在 Tick 时生成一次 evidence-aware Tutor 动作。
- 规则/Conductor 产生的 retriever 动作只能复制/受控派生关联原请求；不得凭 action 名或最近消息推断 query、visibility、retrieval_id。
- `retriever_expand_query` 不作为 P0 入口（DEC-004 `max_attempts=1`）。

## 3. 实施 schema/fixture 收敛与 visibility 过滤

- **schema/fixture（C-01 + BLK-008/I-01）**：让 PG/SQLite provider 测试消费正式 migration 契约（`alembic/versions/20260622_add_vector_chunks_table.py`），替换 fixture 手工建表；不另建 schema 副本。
- **visibility（C-05，DEC-001）**：扩展检索协议使 Coordinator 与 Provider 接收类型化 VisibilityContext；PG/SQLite 查询按 §D.3 谓词过滤，先于排序/去重/LIMIT。
- **outcome（C-06，DEC-008）**：Coordinator 汇总成功/失败；Retriever 按五态归约输出；移除 `str(exc)`，改分类错误码 + 安全摘要（DEC-009）。

## 4. 实施 Tutor 受控证据消费

- 扩展 Tutor 目标动作负载接受 EvidenceProjection（§H）；Tutor 教学输入注入证据正文与来源，严格按上限/`retrieval_id` 关联校验。
- 按冻结的 empty/degraded/failed 策略生成不同教学行为；任何路径不虚构来源、不读旧轮证据、不暴露后端细节。
- `workspace_state.evidence_pool` 不作为主数据通道。

## 5. 实施 composition 校验（C-07，DEC-007）

- `assembly.py:build_new_stack` 显式构造在线 RAGCoordinator（vector=pgvector），三条件校验（backend/provider/dialect），fail-fast，不静默 fake。
- 提供可单测的校验函数供 BLK-007 gate 第 1–3 项消费。

## 6. 按层推进验证

1. 契约单测：RetrievalRequest/EvidenceProjection/`retrieval_id` 保真（三路径）；
2. Provider 过滤与五态归约单测；失败摘要不含 `str(exc)`；
3. 协作环事件顺序、`retrieval_id` 关联、多轮隔离测试；
4. Tutor 输入边界与 evidence 截断测试；
5. 同步 API、SSE API、真实 pgvector 环境端到端验证；
6. 若真实环境未启用 pgvector，记录为未通过的 happy-path，不以 fake 结果替代。

---

## 实施依赖与并行计划

| 阶段 | 工作项 | 串行 / 并行 | 前置条件 | 交付物 |
|---|---|---|---|---|
| 0 | 本 spec 主控复核（C-08） | 串行 | 主控确认 §A–§H 契约 | 冻结契约 + 测试矩阵 |
| 1 | schema/fixture 收敛（C-01） | 串行起点 | 阶段 0 | PG/SQLite 测试消费正式 migration |
| 2A | visibility 过滤（C-09） | 可并行 | 阶段 0、1 | VisibilityContext + PG/SQLite 过滤测试 |
| 2B | 默认检索启动边 + 三路径保真（C-12） | 可并行 | 阶段 0 | 默认可达 Retriever 请求 + payload 保真 |
| 2C | outcome 五态 + 安全摘要（C-10） | 可并行 | 阶段 0、1 | 五态归约、错误码、摘要测试 |
| 3 | Orchestrator 检索路由 + evidence 投影（C-13/14/15） | 串行 | 2A、2B、2C | 微回合屏障 + evidence-aware Tutor 动作 |
| 4 | composition 校验（C-11） | 可与 2 并行 | 阶段 0 | fail-fast 校验 + gate 消费 |
| 5 | 全链回归、HTTP/SSE、真实 pgvector 冒烟（C-16/17） | 串行收尾 | 2A、2B、2C、3、4 | P0 验收报告 |

**为什么 2A/2B/2C/4 可并行**：它们共享本 spec 冻结的字段契约，但分别解决过滤、启动边/保真、结果语义与后端真实性；三者不得各自发明不同 request/status/visibility 结构。

---

## 验收标准

### 降级路径

- 无效检索请求（缺 query / 越界 top_k / 缺认证身份 / 无授权 scope）→ `invalid-request`，不进入 provider，不执行空查询，不回读最近消息。
- 正常空结果 → `empty`；多 provider 部分失败 → `degraded`（`sources_used` 仅含成功来源）；全部失败 → `failed`；四类事件与日志语义可区分。
- 任一分支都产出一份受控 Tutor 回复，不落入 `_EMPTY_REPLY_FALLBACK`。
- 同一 `retrieval_id` 至多一次最终 Tutor action；重复 evidence / 迟到 quality / 重复 tick 不产生第二份回复。
- Tutor 在 empty/failed 情况下不伪造来源、不读取上一轮证据；prompt 不含未授权 chunk。
- payload 全文不含 `str(exc)`、SQL、连接串、堆栈（有测试证明）；内部日志含完整异常且可关联 `retrieval_id`。
- 在线 composition 误配 fake 或 dialect 非 postgresql → fail-fast，有测试证明不进入检索。
- 未授权用户无法从 PostgreSQL、SQLite 或任何被允许参与的 provider 获得其他用户私有内容；歧义行被拒绝且可审计。
- rule/conductor/seed 路径缺 query/visibility/`retrieval_id`/evidence 投影字段时显式失败或拒绝该动作，不能静默裁剪后继续。

### Happy-path

- 默认同步 chat 与 SSE chat 都可观察到：完整 RetrievalRequest → `RetrieverAgent` → `RAGCoordinator` → `PgVectorProvider`（vector source）→ 关联 `RetrievedEvidence` → evidence-aware Tutor 动作 → Tutor 输出。
- 初始 action → evidence/failure → Tutor action → Tutor output 的 `parent_id` 链正确，全链 `retrieval_id` 一致。
- 用含唯一标记的 chunk 驱动一轮测试时，最终 Tutor 输入包含该标记与来源（sentinel 证明）。
- 连续两轮不同 query 使用不同证据时，第二轮 Tutor 输入不包含第一轮未经关联的证据。
- PG/SQLite 对同一授权矩阵结果一致；过滤后执行 `LIMIT`；跨用户隔离矩阵（global / 当前 user 私有 / 其他 user 私有 / 未授权 scope）通过。
- 默认在线 `sources=['vector']`；测试证明 OCR/code 不会因 `sources=None` 被悄然纳入首轮。
- 在线 composition 三条件校验通过且可被 BLK-007 gate 消费。
- 现有 Retriever、RAG Coordinator、chat 新栈相关回归测试通过（含 `low_score` 断言重构），并新增覆盖以上事件、schema、边界与数据库行为的测试。

---

## 风险与开放问题

1. **scope 语义**：DEC-001 已冻结 global/private + 歧义 fail closed；shared/course 明确后置（BLK-011）。存量数据 `NULL user_id` / 缺省 scope / 非规范 scope 的审计迁移策略仍需在实施前抽样核验。
2. **首轮策略范围**：本 spec 假定默认教学首轮需要检索；若产品允许某些意图直答，需另定义可靠分类和不检索的用户可见语义，不由 Retriever 自行猜测。
3. **动作负载透传成本**：rule/conductor 路径需重写为保真（当前 `orchestrator.py:149-154,214-223` 只产 action/target 等）；这不是“加几个字段”，需同步重写测试基线。
4. **Critic 质量关联**：`RAGQualityAssessed` 需携带 `retrieval_id` 且不驱动第二轮检索（DEC-004 `max_attempts=1`）；P0 内 quality 仅作低分降级标记。
5. **多源 Provider 一致性**：默认在线 `sources=['vector']` 已冻结；若未来允许 OCR/code 参与，必须同契约支持 visibility 或显式失败（后置）。
6. **schema/fixture 漂移**：测试消费正式 migration 契约是 P0 必要工作（BLK-008 / I-01），防止真实 pgvector 验收假阳性。
7. **真实后端依赖**：pgvector、DB 连接、embedding 可用性不能由 fake 证明；真实集成测试是 happy-path 必要条件。
8. **composition 校验副效应**：在线装配点 fail-fast 会改变本地开发体验（默认 fake）；需确认错误码与 API 语义，避免把“未配置生产后端”误报为用户可见的检索失败。

---

## 提交主控复核门（C-08）

请主控复核以下本 spec 定义项，复核通过后本 spec 达到可编码状态：

- [ ] **C-01**：migration 事实修正已写入（`20260622_vector_chunks` 存在，fixture 未消费）。
- [ ] **C-02**：evidence/failure → Orchestrator → Tutor 各分支已写清（§C）。
- [ ] **C-03**：seed/rule/conductor 三路径保真表已写清（§A）。
- [ ] **C-04**：`retrieval_id` 落点与 blast-radius 已记录，不二次裁决（DEC-003）。
- [ ] **C-05**：global/private 真值表及 PG/SQLite 强制点已写清（§D）。
- [ ] **C-06**：五态归约与 `low_score→ok` 重构已写清（§E）。
- [ ] **C-07**：在线 composition 精确落点、校验逻辑与诚实失败路径已写清（§F）。
- [ ] **补充**：错误码集合与安全摘要文案枚举（§G）、EvidenceProjection 上限与 citation schema（§H）已定义，待主控/产品复核。
- [ ] 验收标准区分降级路径与 happy-path，且覆盖 §A–§H 全部契约。

---

## 影响传播与自检

| 修订点 | 已同步的下游计划 / 验收 |
|---|---|
| migration 事实修正（C-01） | 验证状态表、工作范围、实施计划 §3、阶段 1 |
| evidence 路由分支（C-02） | §C、验收、阶段 3（C-13/14/15） |
| 三路径保真（C-03/C-04） | §A/§B、验收三路径专项测试、阶段 2B（C-12） |
| visibility 真值表与强制点（C-05） | §D、验收、阶段 2A（C-09） |
| 五态归约 + low_score 重构（C-06） | §E、`test_retriever.py:84-127` 重构、阶段 2C（C-10） |
| composition 落点（C-07） | §F、`assembly.py:121`、阶段 4（C-11）、BLK-007 gate |
| 错误码/摘要（DEC-009） | §G、`retriever.py:54-63` 移除 `str(exc)` |
| EvidenceProjection 上限/citation | §H、Tutor 输入边界、验收截断测试 |

**提交 review 前自检**：本 spec 中所有路径、签名、配置默认值与现有行为均已在验证状态表标记事实来源（file:line）或标注为“本 spec 定义待主控复核”；未将 scope 业务语义、migration 路径、composition 落点、错误码枚举等未裁决项伪造为已确认事实；已区分降级路径与 happy-path。
