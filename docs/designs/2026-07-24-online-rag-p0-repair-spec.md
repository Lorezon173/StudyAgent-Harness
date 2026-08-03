# 在线 RAG 主链 P0 修复规范

> 日期：2026-07-24  
> 状态：**待确认，未进入编码**  
> 设计形态：三层文字规划；本文描述目标、契约和验收，不提供实现代码。  
> 事实依据：本轮对在线默认会话、协作环、Retriever、Coordinator、PgVector 与相关测试进行了代码核验；运行时 `rag_backend` 的实际部署值及 scope 的业务授权语义尚未核验。

---

## 资产清单与三色血缘

| 名字 | 归属子系统 | 当前功能 | 触发 / 入口 | 位置 | 影响 |
|---|---|---|---|---|---|
| `run_new_agent_session` | 编排层 | 装配单会话协作环并创建种子事件 | 两个 chat API 共用入口 | `app/orchestration/assembly.py` | 🟡 |
| `run_collab_loop` | 编排层 | 发布、分发事件并让编排器观察 | `run_new_agent_session` | `app/orchestration/collab_loop.py` | 🟢 |
| `Orchestrator` 与规则 DSL | Harness / 编排层 | 将观察事件转换为后续动作 | 协作环事件观察 | `app/harness/orchestrator.py`、`app/orchestration/orchestrator_rules.yaml` | 🟡 |
| `RetrieverAgent` | Agent 层 | 接收定向检索动作，经协调器检索并发证据事件 | `ActionRequested(target=retriever)` | `app/agents/retriever.py` | 🟡 |
| `TutorAgent` | Agent 层 | 仅消费定向 Tutor 动作并生成教学文本 | `ActionRequested(target=tutor)` | `app/agents/tutor.py` | 🟡 |
| `RAGCoordinator` / `IndexProvider` | 基础设施层 | 选择 Provider、聚合搜索结果 | Retriever 调用 | `app/infrastructure/rag/coordinator.py` | 🟡 |
| `PgVectorProvider` | 基础设施层 | 索引并搜索向量 chunk | `RAGCoordinator` 的 pgvector 分支 | `app/infrastructure/rag/pgvector_provider.py` | 🟡 |
| RAG 事件与动作负载契约 | Harness 层 | 定义 `ActionRequested`、`RetrievedEvidence` 与失败事件的边界数据 | 协作环 | `app/harness/events.py` 及相关事件消费者 | 🟡 |
| 在线 RAG 协作回归测试 | 测试 | 覆盖 Retriever、协调器、真实 pgvector 与 chat 新栈 | `pytest` | `tests/unit/agents/`、`tests/unit/infrastructure/`、`tests/integration/`、`tests/unit/api/` | 🟡 |
| 额外回答器或 Tutor 直连检索 | 不适用 | 不新增 | 不适用 | 不适用 | 🔴 禁止新建 |

---

## 验证状态表

| 事实或决策 | 状态 | 依据 / 说明 |
|---|---|---|
| 同步与 SSE chat 入口均进入同一新栈会话函数 | ✅ 已核实 | 两个 API 入口均调用 `run_new_agent_session`；不需要新建第二条在线链路。 |
| 默认会话初始动作只定向 Tutor，未定向 Retriever | ✅ 已核实 | 会话种子含用户消息、主题进入和 Tutor 动作，不含检索动作。 |
| 规则命中生成的 `ActionRequested` 当前只含 `action/target` | ✅ 已核实 | `app/harness/orchestrator.py:149-154` 的规则路径会裁掉 query、visibility 与证据投影字段。 |
| Conductor 翻译生成的 `ActionRequested` 当前只含 `action/target/via_conductor/reason` | ✅ 已核实 | `app/harness/orchestrator.py:214-223` 的 conductor 路径同样不会保留检索请求参数。 |
| Retriever 的检索输入来自定向动作负载 | ✅ 已核实 | 当前实现从动作负载读取 query、top_k、sources、purpose。 |
| `Event` 当前只有 `parent_id`，没有稳定 `request_id/correlation_id` | ✅ 已核实 | `app/harness/events.py:19-35` 只能表达简单父子关系，尚不足以稳定表示一对多 evidence 与扩展检索关联。 |
| 现有扩展检索规则不能充当首轮入口 | ✅ 已核实 | 它依赖已有检索质量观察；该观察又依赖先前证据，且当前后续动作会丢失检索参数。 |
| Tutor 当前不读取检索证据 | ✅ 已核实 | Tutor 只消费定向动作；提示词输入不含证据。 |
| PgVector 写入 user_id/scope，但查询及上游协议未传递或过滤它们 | ✅ 已核实 | PostgreSQL 与 SQLite 查询分支均无可见性过滤。 |
| `IndexProvider.search` / `PgVectorProvider.search` 当前签名无法承载 visibility | ✅ 已核实 | 现有检索协议只有 `(query, top_k)`，无法表达搜索期过滤上下文。 |
| pgvector 真实/单元测试当前依赖测试内手工建表 `vector_chunks` | ✅ 已核实 | `tests/integration/test_pgvector_real.py` 与 `tests/unit/infrastructure/test_pgvector_provider.py` 都在 fixture 内显式建表，尚未体现统一正式 schema 契约。 |
| `settings.rag_backend` 默认值是 `fake` | ✅ 已核实 | `app/core/config.py:20-23` 默认 `rag_backend='fake'`；真实 pgvector happy-path 需显式切换环境。 |
| Coordinator 将 Provider 异常静默降为继续搜索 | ✅ 已核实 | 当前异常与正常空结果不可可靠区分。 |
| global、用户私有、共享等 scope 的业务可见性规则 | ⚠️ 待产品 / 安全确认 | 代码证明字段存在，不证明授权集合。 |
| 在线 RAG 成功的用户可见定义与无证据降级文案 | ⚠️ 待确认 | P0 需要冻结 Tutor 在 empty / failed / degraded 情形下的行为。 |
| 默认在线首轮是否固定 `sources=['vector']` | ⚠️ 待主控冻结 | 不冻结则 `sources=None` 会让 Coordinator 自动带入 OCR/code 等多源 provider，形成受限搜索语义冲突。 |

---

# 第一层：模块总览

## 1. 目标

补齐在线默认会话的受控 RAG 数据流；这里的“主链”仅指**默认在线课程知识检索**，不否定 `RAGCoordinator` 既有的多源扩展能力。P0 默认路径在主控冻结 source 语义后遵守：

`用户消息 → RetrieverAgent → RAGCoordinator → PgVectorProvider（vector source） → RetrievedEvidence → Orchestrator 的受控证据投影 → TutorAgent`

OCR/code 等 provider 不在本 P0 中被删除或重做；在主控未冻结它们的受限搜索兼容语义前，它们不得因 `sources=None` 被默认在线首轮自动纳入。

完成后，系统应同时满足：

1. 默认会话能以明确、可回放的检索请求启动检索；
2. 检索请求携带受信任的身份与范围上下文，并在所有检索后端一致执行；
3. Tutor 只接收当前检索动作关联的、尺寸受限且可溯源的证据投影；
4. 空结果、部分 Provider 失败和全部失败具有不同的事件语义；
5. 同步和 SSE 两个在线入口共享同一核心事件因果链。

## 2. P0 工作范围

- 定义统一的检索请求负载契约，并在首轮、规则路由和 Conductor 翻译路径中保留该契约。
- 明确 `ActionRequested` 的标准 payload 字段表与跨路径保真规则，覆盖 seed path、rule path、conductor path。
- 明确检索请求与证据事件的稳定关联标识（`request_id/correlation_id` 与 `parent_id` 的关系），以支撑多轮与一对多 evidence 隔离。
- 将默认会话从“先 Tutor”改成“先检索、证据完成后再触发 Tutor”。
- 让 Orchestrator 把当前回合的 `RetrievedEvidence` 投影为 evidence-aware 的 Tutor 动作。
- 为 `IndexProvider`、`RAGCoordinator` 与所有参与在线搜索的 Provider 增加显式检索可见性上下文；PgVector 的 PostgreSQL 与 SQLite 查询实施一致过滤。
- 明确默认在线首轮的 source 语义；若 P0 不要求所有 provider 同步受限搜索契约，则默认首轮需固定为 `sources=['vector']`。
- 将 `vector_chunks` 的正式 schema / migration / fixture 更新路径纳入范围，避免真实 pgvector 隔离验收仅依赖测试内手工建表。
- 将 Provider 的正常空结果、部分失败和全部失败转换为可观测且不混淆的 Retriever 输出，并同步收紧对外失败摘要字段。
- 增补单元、协作环、API、真实 pgvector 集成验证，并覆盖跨用户隔离、多轮证据隔离与动作 payload 保真。

## 3. 非目标

本 P0 明确不做：

- 不让 Tutor 直接调用 Coordinator、Provider、Embedding 服务或数据库。
- 不新建另一套简单回答器、平行 API 路由或独立 RAG 会话链。
- 不重做离线 ingestion、LightRAG、跨源排序、RAGAS 指标或 LangGraph 骨架。
- 不重构跨会话记忆、授权系统模型或历史消息回填。
- 不向客户端直接暴露 Provider 原始异常、SQL 信息或堆栈。
- 不把 `retriever_expand_query` 作为 P0 首轮入口；它只可作为有明确前序请求和低质结果的后续能力。

## 4. 核心决策与判据

### 4.1 首轮检索的触发方式

|  | 采用：检索先行、证据后触发 Tutor | 备选：首轮同时发 Tutor 与 Retriever |
|---|---|---|
| 做法 | 首轮只创建完整的 Retriever 请求；证据或明确失败事件到达后，由编排器创建 Tutor 动作 | 将原 Tutor 种子保留，同时异步检索 |
| 收益 | 事件顺序能证明最终回复有机会使用当前回合证据 | 改动看似较小 |
| 代价 | 需要定义 empty/failed 的教学降级路径 | Tutor 可能先生成无证据回复，无法满足在线 RAG 闭环 |

**选择理由**：P0 的目标是让默认回复使用受控检索结果；并发首轮 Tutor 不能提供这个保证。

### 4.2 证据传递方式

|  | 采用：Orchestrator 生成带证据投影的 Tutor 动作 | 备选：Tutor 直接订阅证据 / 共享状态读取 |
|---|---|---|
| 做法 | 编排器将与当前检索请求关联的内容、来源、分数和状态封装为受限负载 | Tutor 直接消费 `RetrievedEvidence`，或从 `evidence_pool` 读取 |
| 收益 | 保持“编排器路由、Tutor 生成”的边界；可按 parent/correlation 隔离回合 | 快速接线，但会产生 Agent 间耦合或跨回合共享状态污染 |
| 代价 | 要新增证据投影的大小、来源和关联约束 | 破坏现有协作边界，且当前共享证据字段没有稳定生命周期 |

**选择理由**：Tutor 应只看到回答所需的证据快照，而不是获得检索能力或全局事件历史。

### 4.3 可见性过滤的落点

|  | 采用：检索协议端到端显式携带受信任上下文 | 备选：只在 PgVector SQL 临时加过滤 |
|---|---|---|
| 做法 | 检索请求、Retriever、Coordinator、Provider 都显式接收同一身份/范围上下文 | 仅在生产 SQL 中硬编码条件 |
| 收益 | PostgreSQL、SQLite、Fake/其他 Provider 都不会绕过同一安全契约 | 修改面表面较小 |
| 代价 | 需要同步 Provider 协议和测试替身 | 上游仍无授权语义；降级和多源路径可能绕过过滤 |

**选择理由**：索引侧已有 user_id/scope，查询侧必须以同一语义消费它们；安全边界不能只存在于单一方言 SQL。

### 4.5 动作负载保真与关联标识

|  | 采用：标准化 ActionRequested payload + `request_id` | 备选：依赖现有 `parent_id` 或由下游回读状态 |
|---|---|---|
| 做法 | 为 retriever / tutor 动作定义允许字段、必填字段和 seed/rule/conductor 三条路径的保真规则；请求、证据、投影共享稳定 `request_id` | 仅沿用父子事件关系，或让 Retriever/Tutor 从最近消息、全局状态猜字段 |
| 收益 | 可对一对多 evidence、多轮扩展、失败分支进行确定性关联和回放；避免动作路径裁掉请求/投影 | 表面改动小 |
| 代价 | 需要扩展事件/动作契约、编排器翻译和相关测试 | `parent_id` 无法独立表达跨步骤请求关联；回读共享状态会引入跨轮污染和不可回放行为 |

**选择理由**：当前 rule path 与 conductor path 都会裁剪动作负载，因此此项是证据投影和扩展检索的前置契约，不是实现细节。具体字段落点（新增 Event 字段或 payload 字段）由主控冻结，本文不擅自决定。

### 4.6 默认在线 source 语义

|  | 采用：P0 默认首轮固定 `sources=['vector']` | 备选：保持 `sources=None`，默认聚合所有 provider |
|---|---|---|
| 做法 | 默认在线课程知识检索只请求已纳入 P0 visibility 契约的 vector source | 继续让 Coordinator 将 OCR/code/fake 等注册 provider 自动加入搜索 |
| 收益 | 防止未实现受限搜索的 provider 成为跨范围读取旁路；不移除既有多源能力 | 表面保持既有默认行为 |
| 代价 | P0 首轮暂不利用 OCR/code；后续需单独冻结它们的 capability | 需同时让所有 provider 支持相同 visibility，否则无法证明隔离 |

**选择理由**：`RAGCoordinator.search` 在 `sources=None` 时全搜 provider；在未核验 OCR/code 的受限搜索语义前，固定 vector 是安全且范围最小的默认路径。该默认值请求主控冻结。

### 4.7 向量 schema 与验收路径

|  | 采用：将正式 schema/migration 与 fixture 同步纳入 P0 | 备选：只在测试内手工建表后验证过滤 |
|---|---|---|
| 做法 | 定义 `vector_chunks` 正式 schema 来源，更新迁移/DDL 与 PG、SQLite fixture，使过滤测试复用同一字段契约 | 继续由每个测试 fixture 自行 `CREATE TABLE` |
| 收益 | 真实 pgvector 跨用户验收对应生产可部署表结构；减少 fixture 漂移 | 初期改动少 |
| 代价 | 需核实并更新现有 migration/DDL 路径；处理存量空值兼容 | 测试可能通过而正式环境无对应 schema 保证 |

**选择理由**：真实 pgvector 隔离是 P0 完成门槛时，schema 不能继续是测试隐含前提。正式迁移位置尚待核实，本 spec 将其列为实施前核验项而不臆造路径。

### 4.8 Provider 失败语义

|  | 采用：结构化区分 empty、部分成功、全部失败 | 备选：继续吞异常并按空结果处理 |
|---|---|---|
| 做法 | Coordinator 保留成功来源和失败诊断；Retriever 发空证据、降级证据或失败事件，并将内部异常转换为安全摘要 | 所有异常 `continue`，最终给空 chunks |
| 收益 | 可观测、可测试；不会将断连与零命中混为一谈，也避免对外透传原始异常 | 实现改动更少 |
| 代价 | 需要定义内部错误类别、Retriever 映射和 Tutor 的降级行为 | 故障无法定位，可能生成误导性的“未检索到”回复或泄露 `str(exc)` |

**选择理由**：P0 需要在真实 pgvector 环境中可验收，静默失败会使验收失真；Coordinator 与 Retriever 两侧都必须纳入失败摘要契约。

---

## A. 动作负载、关联与投影契约（P0 前置）

> 本节定义 P0 需要的字段语义，但**不擅自冻结最终字段落点**：主控应裁决 `request_id` 是 Event 一等字段还是受控 payload 字段。无论落点如何，三条动作产生路径必须保真，且下游不得从最近消息或全局状态推断缺字段。

### A.1 RetrievalRequest 与路径映射

| 字段 | 首轮 seed 来源 | rule / conductor 后续来源 | Retriever 输出 / Tutor 投影用途 | 约束 |
|---|---|---|---|---|
| `query` | 原始 `user_message` | 仅复制或受控派生关联原请求 | Provider 查询、审计 | 非空；不得由 Tutor/LLM 猜测 |
| `top_k` | 冻结后的默认值 | 复制原请求或受限重试值 | Provider 限额 | 必须验证类型与上限 |
| `purpose` | `teaching` | 复制原请求 | Critic/降级策略 | 枚举待冻结 |
| `sources` | P0 建议 `['vector']` | 复制原请求 | Coordinator 选择 provider | 不得默认回退为未受限的全搜 |
| `user_id` | 受信任会话上下文 | 不可由 rule/conductor/LLM 改写 | VisibilityContext | 不得来自用户文本 |
| `visibility` | 受信任会话上下文 | 复制原请求 | Provider 授权过滤 | 具体 scope 集合待冻结 |
| `request_id` | 首轮创建 | 继承或为受控重试派生并保留 origin | evidence / Tutor 投影关联 | 必须可跨一对多结果与多轮区分 |

### A.2 ActionRequested 保真规则

| 产生路径 | 当前行为 | P0 必须满足 |
|---|---|---|
| seed path | 只放 `action/target` | Retriever seed 必须携带完整 RetrievalRequest；不得同时排入无证据的最终 Tutor 动作 |
| rule path | 当前规则命中后只放 `action/target` | 若 target 为 retriever，完整复制关联请求；若 target 为 tutor，完整携带已裁剪 EvidenceProjection |
| conductor path | 当前翻译只放 action/target/via_conductor/reason | 同样保真；不得因转译丢失 query、visibility、request_id 或 evidence 投影 |

### A.3 `request_id` 与 `parent_id`

- `parent_id` 继续表达“此事件直接由哪一个事件触发”的事件树因果关系。
- `request_id` 表达“这条检索请求及其所有证据、重试和 Tutor 投影属于哪个逻辑检索单元”。
- 一个 RetrievalRequest 可产生零到多个 evidence / failure 事件；它们可有不同 `parent_id`，但必须拥有同一 `request_id`。
- 扩展检索必须显式保存原 `request_id` 关系；其是同一逻辑请求的重试还是新请求，需由主控冻结，P0 不可隐式猜测。

### A.4 EvidenceProjection

- 仅由 Orchestrator 为当前关联请求构造，并作为 target=tutor 的 ActionRequested 负载。
- 至少含 `request_id`、`chunks`、`citations`、`retrieval_status`；每个 chunk 至少含 `content/source/score`。
- 定义最大 chunk 数、单 chunk 字符数与总输入长度；具体数值待主控/产品冻结。
- Tutor 只能消费该投影；不得持有或构造 Coordinator、Provider、EmbeddingService 引用，也不得读未关联的 `evidence_pool`。

---

# 第二层：子模块概述

## A. 检索请求与因果关联边界

**职责**：为所有 `target=retriever` 动作建立可验证的最小请求契约，并使检索结果可精确关联回触发动作。

**数据流**：
- 首轮从受信任会话上下文派生 query、身份和范围；
- 后续检索只从已关联的前序请求复制或受控派生参数；
- Retriever 输出证据或失败，并保留与请求的父子/关联关系；
- 编排器仅消费当前回合关联的结果。

**状态与边界**：
- query、top_k、purpose、sources 与可见性上下文不得由 Tutor 猜测；
- user_id 与可见性范围必须来自受信任会话上下文，不能由用户文本或模型自由覆盖；
- 缺失、空白或越界参数属于无效检索请求，不能回退为“读取最近消息”。

**错误策略**：生成可分类的无效请求/检索失败，而不是空查询或静默回退。

## B. 默认会话编排与二次检索生命周期

**职责**：调整默认种子和规则输出，使首轮检索可达，并确保扩展检索不是循环依赖。

**数据流**：
- 默认会话产生 Retriever 请求而非无证据 Tutor 请求；
- `RetrievedEvidence` 或失败结果到达后，编排器创建对应 Tutor 动作；
- 低质量后的扩展检索只能复制其明确关联的原请求参数，并受次数上限约束。

**状态与边界**：
- 需记录/传播请求关联标识，以防第二轮复用第一轮证据；
- P0 不定义新的 query-rewrite 算法；若现有扩展无法安全携参，则暂不启用扩展。

**错误策略**：空结果与失败均结束首轮检索等待并进入预先定义的 Tutor 降级动作，避免无限循环。

## C. 检索协议、可见性、schema 与 Provider 实现

**职责**：将身份/范围过滤与故障语义贯通 IndexProvider、Coordinator、PgVector、正式 schema 和测试后端。

**数据流**：
- Retriever 把已验证的 RetrievalRequest 交给 Coordinator；
- Coordinator 只向已被请求 source 选中的 Provider 转发一致的 VisibilityContext；
- Provider 先完成授权过滤，再按过滤后的候选集执行排序、LIMIT 和去重；
- Coordinator 汇总成功、空结果和失败状态；
- Retriever 将其映射为证据、降级证据或失败事件。

**schema / migration 边界**：
- `vector_chunks` 的 `user_id` 与 `scope` 是查询过滤的正式依赖字段；本 P0 要先核实其生产 DDL / migration 唯一来源，再同步更新正式 DDL、PostgreSQL/SQLite fixture 和集成环境初始化。
- 若没有既有正式来源，新增正式 schema/migration 属于本 P0 的必要工作，而不是测试附带工作；但具体 migration 文件路径在实施前必须核验，本文不臆造。
- 需定义既有 `NULL user_id`、缺省 scope 或非规范 scope 值的兼容/回填策略；未裁决前不得写最终 WHERE 谓词。

**状态与边界**：
- PostgreSQL 与 SQLite 的可见性谓词必须语义一致；
- P0 默认在线首轮建议 `sources=['vector']`，避免 `sources=None` 自动带入尚未支持受限搜索的 OCR/code provider；
- 未支持受限搜索的 Provider 不能悄悄忽略过滤；若后续被允许参与，必须实现同语义过滤或显式失败；
- 去重必须只作用于已通过授权过滤的结果。

**错误策略**：保留内部可观测诊断；Coordinator 不再静默吞异常；Retriever 把内部异常映射为安全摘要，前端只收到产品规定的安全信息。

## D. Tutor 证据投影与教学降级

**职责**：让 Tutor 在不拥有检索能力的前提下，接收当前动作的有限证据上下文。

**数据流**：
- 编排器从当前 `RetrievedEvidence` 构造受限投影；
- Tutor 将内容、来源、分数和检索状态纳入教学提示；
- 对 empty、degraded、failed 使用冻结的降级策略。

**状态与边界**：
- 投影仅属于当前检索请求；
- 设置最大 chunk 数、每 chunk 文本上限、总字符/Token 上限；
- 保留可展示/可审计的来源标识；
- 禁止读取旧 `evidence_pool` 作为主链。

**错误策略**：无可用证据时不得捏造引用；失败时不泄露后端细节。

## E. 验证与可观测性

**职责**：证明主链、隔离、降级与两个 API 入口都真实生效。

**数据流**：单元契约 → 协作环事件顺序 → Provider/数据库集成 → HTTP 与 SSE 端到端 → 部署冒烟。

**状态与边界**：测试必须显式区分 fake 与 pgvector 配置；真实 pgvector 验证不能由 fake 测试代替。

**错误策略**：测试中的 Provider 故障必须观察到失败/降级语义，不接受“返回空结果即通过”。

---

# 第三层：详细实施计划（文字设计）

## 1. 先冻结五个跨层契约

在改动任何 Agent、Provider 或 SQL 前，形成并评审以下文字契约：

1. **ActionRequested 保真契约**：RetrievalRequest / EvidenceProjection 在 seed、rule、conductor 三条路径的必填字段、允许字段、复制规则与不可改写字段。
2. **关联契约**：`request_id` 的字段落点、生成方式、与 `parent_id` 的分工，以及重试/扩展时的继承或派生规则。
3. **RetrievalRequest**：非空 query、受限 top_k、purpose、受信任 user_id、visibility、固定/允许的 sources、request_id。
4. **EvidenceProjection / RetrievalOutcome**：证据上限与 citation 字段；区分 empty、degraded、failed 与 invalid-request；内部诊断与客户端摘要分离。
5. **VisibilityContext 与 schema 契约**：global、用户私有及其他 scope 的授权规则；`vector_chunks` 正式 DDL/migration 来源；缺省身份/范围与存量空值的策略。

**实施前需用户或主控确认的推荐默认值**：
- 首轮 query 使用原始 user_message；当前 topic 只作为 Tutor 的教学主题，不替代检索 query。
- 首轮使用一个固定且受上限保护的 top_k；具体值在现有材料中未核实，不在本文固定。
- global 对已认证用户可见、用户私有仅对同 user_id 可见；共享/课程 scope 暂不在 P0 扩展，除非已有授权规则可核验。
- 默认在线首轮固定 `sources=['vector']`；OCR/code provider 不经 `sources=None` 自动参与，直至它们受限搜索 capability 被单独冻结。
- 检索 empty 时继续教学但明确“未找到可用课程证据”；全部 failed 时使用安全的降级说明；部分成功可继续教学并标记为降级。

## 2. 实施默认会话的检索先行时序

- 取消默认首轮中无证据的 Tutor 动作作为最终回复入口。
- 改为创建一条完整的 Retriever 动作，保证它具备已冻结的 RetrievalRequest 全部字段与 request_id。
- 让 Retriever 的成功、空结果、降级结果或失败结果都成为编排器可识别的完成信号；每个结果须保留 request_id 与直接 parent_id。
- 由编排器创建后续 Tutor 动作；不得让 Retriever 直接调用 Tutor，也不得让 Tutor 自行拉取证据。
- 规则与 Conductor 产生的 retriever 动作只能复制/受控派生关联原请求；它们不得凭 action 名或最近消息推断 query、visibility 或 request_id。
- 对扩展检索增加明确前提：已有关联的低质量/空结果、可重用的原请求、有限重试次数；主控冻结其 request_id 继承/派生规则前不启用。

## 3. 实施正式 schema、端到端可见性过滤与结果语义

- 首先核实 `vector_chunks` 的正式 schema / migration 来源；把该来源、SQLite 降级 DDL 与测试 fixture 收敛为同一字段契约。
- 如现有正式 migration 不存在或不涵盖该表，新增/修订正式 migration 是 P0 必要工作；在核实路径前不得假定 migration 文件名。
- 扩展检索协议，使 Coordinator 与 Provider 都接收同一 VisibilityContext 与 request_id；先同步 vector/fake test double 的行为，再决定其他 provider 的 capability。
- 在 PgVector 的 PostgreSQL 与 SQLite 查询路径中执行同一可见性规则，并确保过滤先于排序、LIMIT 和去重。
- 使 Coordinator 汇总已选 Provider 的成功和失败，而不是吞掉异常；定义“全部失败”“部分成功”“正常空结果”的可观测结果。
- 让 Retriever 基于 Outcome 产生对应的证据或失败事件，保留 request_id，并将底层异常转为安全摘要而非透传 `str(exc)`。

## 4. 实施 Tutor 的受控证据消费

- 扩展 Tutor 目标动作的负载，使其接受 EvidenceProjection 而非 Provider/Coordinator 引用。
- 在 Tutor 的教学输入中加入证据正文与来源，但严格执行投影上限、request_id 关联校验与 citation 约束。
- 根据冻结的 empty/degraded/failed 策略生成不同教学行为；任何路径都不得虚构来源或使用旧轮证据。
- 不以 `WorkspaceState.evidence_pool` 作为主数据通道；如保留，只能作为非权威观测缓存，并需单独定义写入者与生命周期。

## 5. 按层推进验证

- 先写请求、关联与动作负载保真测试，以及正式 schema / fixture 一致性测试；
- 再写 Provider 过滤、Outcome 和安全失败摘要单测；
- 再写协作环的事件顺序、request_id 关联与多轮隔离测试；
- 再写 Tutor 输入边界和 evidence 投影截断测试；
- 最后在同步 API、SSE API、真实 pgvector 环境做端到端验证；
- 若真实环境未启用 pgvector，必须记录为未通过的 happy-path，不得以 fake 结果替代。

---

## 实施依赖与并行计划

| 阶段 | 工作项 | 串行 / 并行 | 前置条件 | 交付物 |
|---|---|---|---|---|
| 0 | 冻结五个跨层契约及产品降级语义 | 串行 | 用户 / 主控确认本 spec 的开放决策 | ActionRequested/request_id/schema/source/降级语义契约 + 测试矩阵 |
| 1 | 正式 schema / migration / fixture 契约核实与收敛 | 串行起点 | 阶段 0 中与 schema、visibility 相关的冻结项 | 统一的 `vector_chunks` 契约来源与测试初始化路径 |
| 2A | 可见性协议与 vector/fake provider 过滤 | 可并行 | 阶段 0、1 | 一致的 VisibilityContext 与过滤测试 |
| 2B | 首轮检索启动边、动作负载保真与 request_id 传播 | 可并行 | 阶段 0 | 默认可达 Retriever 请求 + 三路径 payload 保真 |
| 2C | Coordinator / Retriever 的 empty / degraded / failed 结果语义与安全摘要 | 可并行 | 阶段 0、1 | 可观测 Outcome、失败摘要与对外字段约束 |
| 3 | EvidenceProjection 与 Tutor 动作 | 串行 | 2A、2B；建议同时纳入 2C 的失败语义 | 证据驱动的 Tutor 输入 |
| 4 | 全链回归、HTTP/SSE、真实 pgvector 冒烟 | 串行收尾 | 2A、2B、2C、3 | P0 验收报告 |

**为什么阶段 2A / 2B / 2C 可以并行**：它们共享同一冻结后的字段契约，但分别解决过滤、动作保真和结果语义；三者不应各自发明不同 request/source/status 结构。

---

## 验收标准

### 降级路径

- 无效检索请求不会回读最近消息或执行空查询；会产生明确的受控失败结果。
- 正常空结果、部分 Provider 失败、全部 Provider 失败在事件、内部诊断和安全对外摘要上可区分；不得透传原始 `str(exc)`、SQL 或堆栈。
- empty / failed / degraded 都会完成当前回合，且不会造成无限扩展检索循环。
- Tutor 在 empty / failed 情况下不伪造来源，也不读取上一轮证据。
- 未授权用户无法从 PostgreSQL、SQLite 或任何**被允许参与当前受限请求**的 Provider 获得其他用户私有内容。
- rule path、conductor path 与 seed path 在缺 query、visibility、request_id 或 evidence 投影字段时必须显式失败或拒绝该动作，不能静默裁剪后继续。

### Happy-path

- 默认同步 chat 与 SSE chat 都可观察到：完整 RetrievalRequest → `RetrieverAgent` → `RAGCoordinator` → `PgVectorProvider`（vector source）→ 与请求关联的 `RetrievedEvidence` → evidence-aware Tutor 动作 → Tutor 输出。
- 对 seed path、rule path、conductor path 分别断言 retriever action 保留 query/top_k/purpose/sources/user_id/visibility/request_id，Tutor action 保留关联 EvidenceProjection。
- 用含唯一标记和来源的 chunk 驱动一轮测试时，最终 Tutor 输入包含该标记与来源；这证明证据真实进入生成边界。
- 连续两轮不同 query 使用不同证据时，第二轮 Tutor 输入不包含第一轮未经关联的证据；request_id 与 parent_id 的断言能区分直接因果和逻辑检索单元。
- `vector_chunks` 正式 schema/migration 与 PG、SQLite fixture 使用同一字段契约；真实 pgvector 集成环境中，为 global、当前用户私有、另一用户私有与未授权 scope 建立数据后，查询只返回被授权集合，且 top_k 在过滤后生效。
- 默认 online source 语义按冻结值执行；若固定 `sources=['vector']`，测试必须证明 OCR/code 不会因 `sources=None` 被悄然纳入首轮。
- 同步与 SSE 入口共享相同核心事件顺序；SSE 仅额外验证事件投递，不拥有不同的检索逻辑。
- 现有 Retriever、RAG Coordinator、chat 新栈相关回归测试通过，并新增覆盖以上事件、schema、边界与数据库行为的测试。

---

## 风险与开放问题

1. **scope 语义未冻结**：当前代码证明字段存在但未定义 global、个人、课程或共享范围的业务规则。若未确认，不应写最终 SQL 谓词。
2. **首轮策略范围**：本 spec 假定默认教学首轮需要检索；若产品允许某些意图直答，需先定义可靠分类和不检索的用户可见语义，不能由 Retriever 自行猜测。
3. **动作负载透传成本真实存在**：当前 rule path 与 conductor path 都会裁掉动作字段；若主控最终选择“标准 payload 保真”，需同步重写这些路径及其测试基线，不能低估为“只加几个字段”。
4. **证据尺寸与提示注入**：EvidenceProjection 需有内容和来源白名单、长度上限，并在实现评审时核验 Prompt 构造边界。
5. **多源 Provider 一致性**：若不冻结默认 `sources=['vector']`，任何不支持受限搜索的 Provider 都可能成为隔离旁路；实现必须显式处理。
6. **schema / fixture 漂移风险**：若正式 `vector_chunks` schema 与测试内建表继续分叉，真实 pgvector 验收会成为假阳性；因此 migration/DDL 不能留在 P0 之外。
7. **历史数据兼容**：已有向量记录的 `scope`、`user_id` 为空或取值不统一时，需要在实施前抽样核验并决定迁移/回填策略。
8. **真实后端依赖**：pgvector、数据库连接与 embedding 可用性均不能由 fake 测试证明；真实集成测试是 P0 happy-path 的必要条件。
9. **对外失败语义收口**：Retriever 当前失败分支若继续沿用原始异常字符串，会与“前端不暴露底层异常”目标冲突；需在实现前冻结安全摘要字段。

---

## 用户确认门

确认下列决策后，才能进入编码：

- [ ] 默认首轮采用“检索先行、证据后 Tutor”，而不是并发 Tutor。
- [ ] 首轮检索 query 采用原始 user_message；top_k 具体默认值与上限在实现前冻结。
- [ ] ActionRequested 标准 payload、seed/rule/conductor 三路径字段保真，以及检索/证据/Tutor 投影的字段边界已冻结。
- [ ] `request_id/correlation_id` 的字段落点、生成/继承规则与 `parent_id` 的分工已冻结。
- [ ] P0 scope 暂定为“global + 当前 user_id 私有”，其他 scope 明确不进入本次范围，除非现有授权规则被补充核验。
- [ ] 默认在线首轮的 source 语义已冻结；推荐 `sources=['vector']`，OCR/code/fake provider 不会被未受限的默认多源搜索自动纳入。
- [ ] `vector_chunks` 的正式 schema / migration / fixture 维护路径、以及历史空值兼容策略已核实并纳入实施范围。
- [ ] empty / degraded / failed 的 Tutor 降级语义、API 安全摘要和“不得暴露原始异常”边界已确认。
- [ ] `retriever_expand_query` 不作为首轮入口；若本 P0 保留，必须具备关联原请求、request_id 规则与重试上限。
- [ ] 真实 pgvector 跨用户隔离测试是 P0 完成门槛，不能以 fake 后端替代。

---

## 本次修订的影响传播与自检

| 修订点 | 已同步的下游计划 / 验收 |
|---|---|
| ActionRequested 保真 | §A.2、第三层 §1/§2、验证标准中的三路径专项测试 |
| request_id 与 parent_id 分工 | §A.3、EvidenceProjection、事件顺序/多轮隔离验收 |
| schema / migration 范围 | 工作范围、子模块 C、第三层 §3、阶段 1、真实 pgvector 验收 |
| 默认 source 语义 | 目标定义、决策 §4.6、子模块 C、验收与用户确认门 |
| Retriever 安全失败摘要 | 决策 §4.8、第三层 §3、降级验收与风险项 |

**提交 review 前自检**：本次新增的路径、签名与配置默认值均已在验证状态表中标记事实来源；scope、关联字段最终落点、schema migration 位置与用户可见降级语义仍明确标记为待主控/用户冻结或实施前核验，没有伪造为已确认事实。