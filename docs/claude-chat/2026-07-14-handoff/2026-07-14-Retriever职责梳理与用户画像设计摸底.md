# 工作交接：Retriever职责梳理与用户画像设计摸底

> 创建：2026-07-14
> 会话目标：快速摸清当前项目（`app/` 新栈）中 Retriever 的真实职责边界，以及用户画像/记忆系统的实现现状，为后续继续讨论检索改进、教学增强、长期记忆方案提供上下文。
> 状态：✅ 已完成现状梳理；无代码改动；可直接接续到方案讨论或进一步源码核查
> 说明：本文件用于让新窗口快速接手，不重复阅读整段历史对话；涉及设计/研究文档时仅保留索引位置，不复制原文。

---

## 任务 1：搞清楚 Retriever 担任哪些职责，具体负责哪些工作

### 触发

用户提问："告诉我当前项目 retriever 担任哪些职责，具体负责哪些工作"

### 探索过程

1. **定位 retriever 相关文件**：用 `find` + `grep` 在全球搜索，区分了三类产物：
   - 新栈（`app/`）：`app/agents/retriever.py`、`app/specs/agents/retriever.md`、`app/specs/agents/retriever.prompt.md`
   - 旧栈（`app_old/`）：`app_old/agent/multi_agent/retrieval_graph.py`、`app_old/agent/nodes/knowledge_retrieval.py` 等——确认为**已废弃**
   - `.venv/` 中的 langchain 第三方 retriever（不相关）

2. **读取核心实现**（并行 4 文件）：
   - `app/agents/retriever.py`：RetrieverAgent 完整实现（266 行）
   - `app/specs/agents/retriever.md`：开发者规范
   - `app/specs/agents/retriever.prompt.md`：运行时 prompt（内容为"本 Agent 当前不使用 LLM，此文件仅作角色声明留存"）
   - `app/harness/enums.py`：EventType / ActionKind / EventSource / RetrievalMode 等全部枚举

3. **读取依赖与编排**（并行 4 文件）：
   - `app/infrastructure/rag/coordinator.py`：RAGCoordinator 多源聚合逻辑、IndexProvider 协议、Chunk/SearchResult 数据结构
   - `app/orchestration/graph.py`：主图骨架，Plan C 只装配 Tutor/Critic/Conductor，Retriever 由 Plan D 补齐
   - `app/orchestration/assembly.py`：`build_new_stack` 中 5 Agent（含 RetrieverAgent()）注册到 EventBus
   - `app/agents/base.py`：AgentBase 契约（source/subscriptions/emittable_types/emit）

4. **追踪事件流**（并行 3 文件 + 多次 grep）：
   - `app/orchestration/collab_loop.py`：PriorityEventQueue 驱动的事件循环，`max_turns=50` 熔断
   - `app/harness/orchestrator.py`：RuleEngine 读 `orchestrator_rules.yaml` 匹配规则，`_target_of(action)` 按前缀映射 action → target agent
   - `app/agents/critic.py`：Critic 订阅 `RetrievedEvidence`，`purpose=="teaching"` 时调 LLM 产出 `RAGQualityAssessed`
   - `app/orchestration/orchestrator_rules.yaml`：仅一条 retriever 相关规则（`rag_quality_low` → `retriever_expand_query`，priority 40）
   - `app/api/_sse_projection.py`：retriever 事件通过 `_RETRIEVER` 元组透出到前端 SSE

5. **查看 RAG 基础设施**：
   - `app/infrastructure/rag/` 目录：`store.py`（FakeRAGStore）、`pgvector_provider.py`（真向量检索）、`embedding.py`（embedding 服务）、`ocr.py`、`code_index.py`、`extractors/`（PDF/DOCX/Text）
   - `app/core/config.py:21`：`rag_backend: str = "fake"`（默认 fake，可切 pgvector）

### 发现的关键事实

**RetrieverAgent 是一个事件驱动的 Agent**，继承 AgentBase（`app/agents/retriever.py:24`）：

- **类属性声明**：
  - `source = EventSource.RETRIEVER`
  - `subscriptions = [EventType.ACTION_REQUESTED]`——只订阅这一种事件
  - `emittable_types = {EventType.RETRIEVED_EVIDENCE, EventType.RETRIEVAL_FAILED}`

- **handle 方法**（`:36-63`）：从 `ActionRequested` payload 中过滤 `target == "retriever"` 的事件，提取 `query / top_k / sources / purpose` 字段，调用 `_do_retrieve_and_emit`。异常时 emit `RetrievalFailed`（`retrieval_status="timeout"`）。

- **_do_retrieve_and_emit**（`:67-101`）：委托 `RAGCoordinator.search()` 做实际检索 → 计时 latency_ms → 从返回的 chunks 提取 scores → 用 `LOW_SCORE_THRESHOLD = 0.3` 做三分类（empty / low_score / ok）→ 组装 payload → emit `RetrievedEvidence`。

- **evaluate 方法**（`:105-265`）：部件级评估接口，供 Plan E 的 `ComponentBench` 调用。返回 6 个指标：
  1. `recall_at_k`：golden_chunks 命中率（启发式，子串匹配）
  2. `context_precision`：检索结果中与 golden 相关的比例（启发式）
  3. `redundancy`：multiset Jaccard > 0.8 的相似 chunk 对比例
  4-6. `faithfulness / answer_relevancy / context_precision`（RAGAS）：需 judge 可用且有 golden_answer，否则降级
  - 降级路径有三档：judge 不可用、无 golden_answer、RAGAS 未安装或评估异常——每档保留启发式指标并标注 `degraded: True` + 原因

**RAGCoordinator 是多源聚合层**（`app/infrastructure/rag/coordinator.py:46`）：

- 管理多个 `IndexProvider` 实例（字典 `_providers`），默认注册一个 vector provider
- vector provider 根据 `settings.rag_backend` 选择：`pgvector` → `PgVectorProvider`（`pgvector_provider.py:22`），否则包装 `FakeRAGStore`
- `search()` 方法（`:100-131`）：遍历所有/specified provider → 每个调 `provider.search(query, top_k)` → 全量收集 → 按 content 去重（同 content 保留最高 score）→ 按 score 降序 → 截取 top_k
- 保留旧接口 `retrieve()`（`:141-175`）：仅 vector 源的 dict 格式返回，含自适应置信度（avg_score > 0.6 → high, > 0.3 → medium, 否则 low）

**事件流全链路**：

```
Critic emit RAGQualityAssessed
  → Orchestrator.on_event 缓冲到 _pending_obs（orchestrator.py:81-82）
  → OrchestratorTick 哨兵入队（priority=100，最低）
  → Tick 被弹出时 _on_tick 收集观察集、匹配规则（:100-155）
  → 规则 rag_quality_low → retriever_expand_query（orchestrator_rules.yaml:50-54）
  → emit ActionRequested(action="retriever_expand_query", target="retriever")（orchestrator.py:149-154）
  → EventBus 分发给 RetrieverAgent.handle（订阅了 ActionRequested）
  → handle 过滤 target=="retriever" → 调 _do_retrieve_and_emit
  → emit RetrievedEvidence
  → Critic.handle 收到 → purpose=="teaching" 时调 LLM 评 RAG 质量 → emit RAGQualityAssessed
  → 形成闭环（若质量仍低，再次触发 expand_query）
```

**_sse_projection 对前端的透出**（`app/api/_sse_projection.py:11`）：

```python
_RETRIEVER = (EventType.RETRIEVED_EVIDENCE, EventType.RETRIEVAL_FAILED)
```
前端收到的 content 字段 = `payload.get("summary", "")` 或 `str(payload.get("count", ""))`，不直接传输 chunks 全文（`:40`）。

### 标注的问题

1. **`retriever_search` 动作已定义但无规则触发**：`ActionKind.RETRIEVER_SEARCH`（`enums.py:147`）和 `ActionKind.RETRIEVER_EXPAND_QUERY`（`:148`）都存在，但 `orchestrator_rules.yaml` 里只有 `rag_quality_low → retriever_expand_query` 这一条 retriever 规则。`retriever_search` 仅出现在 `tests/unit/agents/test_tutor.py:32` 作为测试 fixture。意味着**当前生产路径里，retriever 只在 RAG 质量低时被触发扩展查询，没有"首次进入主题主动检索"的初始触发规则**。

2. **两种 action 在 handle 中无差异化处理**：`RetrieverAgent.handle`（`:36-63`）只看 `payload.target == "retriever"`，不区分 action 是 search 还是 expand_query——两者走完全相同的检索路径。"扩展查询"的语义（如改写 query、增加 synonyms）当前未在 RetrieverAgent 内实现。推测应由上游在 payload 中带扩展后的 query，但在代码中未找到显式实现——**这一点不确定**。

3. **retriever 与旧栈的关系**：`app_old/agent/multi_agent/retrieval_graph.py` 和 `app_old/agent/nodes/knowledge_retrieval.py` 是旧栈的检索实现（LangGraph 节点式），当前项目使用 `app/agents/retriever.py`（事件驱动 Agent 式），双栈由 `feature_flags` 灰度切换。

4. **LightRAG 双检索演进**：`docs/designs/2026-07-03-phase-b1-lightrag-dual-retrieval-spec.md` 设计了 LightRAG 的 dual retrieval（local + global 模式）接入方案，尚未落地实现。

---

## 任务 2：搞清楚用户画像是如何设计的，用了什么框架，为什么这样选，还有哪些欠缺

### 触发

用户提问："检索当前代码和 spec 设计，告诉我当前用户画像是如何设计的，使用了什么框架，为什么要这样选择，还有哪些欠缺，从一个求职者回答问题的角度回答我"

### 探索过程

1. **全局搜索画像相关文件**：用 `find + grep` 搜索 `profile / curator / mastery_graph / learning_path / user_model / student_model / knowledge_graph / skill_graph`，定位到大量文件。

2. **读取核心实现**（并行 6 文件）：
   - `app/harness/user_profile.py`（67 行）：UserProfile dataclass，含 preferences / topics_active / topics_mastered / learning_streak / total_sessions
   - `app/harness/mastery_graph.py`（206 行）：MasteryGraph 图谱引擎，含 MasteryNode / MasteryEdge 数据类、EdgeType / EdgeSource 枚举、add_node / add_edge / update_mastery / find_weak_prereqs / 冷启动建图三方法 / persist
   - `app/agents/curator.py`（157 行）：Curator Agent（继承 CuratorBase），双时机 subscription、handle 分发、_on_mastery_assessed（observed）、_on_topic_entered（historical）、evaluate
   - `app/api/profile.py`（27 行）：FastAPI router GET /profile/，从 SessionTable count + MasteryNodeTable avg 返回
   - `app/models/tables.py`（112 行）：MasteryNodeTable（复合主键 user_id+topic_id）、MasteryEdgeTable（含 UniqueConstraint）
   - `app/models/schemas.py`（78 行）：Pydantic models（ChatRequest/Response、Auth 等），无 Profile 专用 schema

3. **读取存储层与 spec**（并行 4 文件）：
   - `app/infrastructure/storage/mastery_graph_store.py`（155 行）：aiosqlite 持久化，三表（mastery_nodes / mastery_edges / user_profile_l3），init 建表 + save/load CRUD
   - `app/specs/agents/curator.md`：开发者规范（"当前不调 LLM，仅留存"）
   - `app/specs/agents/curator.prompt.md`：运行时 prompt（"本 Agent 当前不使用 LLM"）
   - `docs/superpowers/plans/2026-06-01-plan-b-memory-profile.md`（1721 行）：Plan B 完整实现计划，含 Task 1-5 的 TDD 步骤、代码示例、验收 checklist

4. **读取设计文档与决策报告**（并行 2 文件）：
   - `docs/designs/2026-07-03-phase-b2-mastery-temporal-review-spec.md`（382 行）：Phase B-② 掌握度时序衰减 + 复习触发 spec（已设计、待编码），含 MasteryDecayService / ReviewTriggerService / Curator 增强 / API 端点设计
   - `docs/research/2026-06-16-current-vs-frameworks-decision-report.md`（截取 100 行）：7 框架对比决策报告，结论为"借鉴设计、自研嫁接"

5. **补充查阅**：
   - `app/harness/memory.py`：**文件不存在**——新栈没有独立的 memory.py，记忆功能分散在 MasteryGraph + UserProfile 中
   - `app_old/harness/memory.py`、`app_old/harness/state/memory.py`、`app_old/infrastructure/storage/memory_store.py`：旧栈的记忆系统（FTS5 trigram + summaries + profiles），**新栈不用**
   - `app/harness/enums.py`：MemoryScope 5 级（WORKING / EPISODE / SESSION / USER / GLOBAL），`:68`

### 发现的关键事实

**总体架构**：用户画像不是单一实体，而是 **MasteryGraph（知识点掌握度图谱）+ UserProfile（学习偏好画像）** 两个并列的 Harness 层组件，由 Curator Agent 自动维护。

**MasteryGraph（`app/harness/mastery_graph.py`）**：

- **MasteryNode 字段**（`:22-31`）：
  - `topic_id`：知识点标识
  - `mastery`：掌握度，**百分制 0-100**（注意：Plan B 设计文档中为 0-1，实际实现已改为 0-100）
  - `last_practiced_at`：epoch seconds，记录最后练习时间
  - `practice_count`：练习次数
  - `confusion_with`：易混淆的概念对列表
  - `rationale`：最近一次评分依据（来自 Critic）

- **MasteryEdge 字段**（`:34-42`）：
  - `from_topic / to_topic`：有向边
  - `type`：PREREQ / RELATED / CONFLICT（EdgeType 枚举，`:8-11`）
  - `weight`：边权重（默认 1.0）
  - `confidence`：边的置信度（0-1），是前置薄弱检测的核心参数
  - `source`：边来源——DOC_ORDER（教材章节顺序，0.5）/ LLM_INFER（LLM 推断，0.3）/ INTERACTION（实际交互验证，0.8）（EdgeSource 枚举，`:14-18`）

- **前置薄弱检测核心算法** `find_weak_prereqs`（`:129-156`）：
  ```
  adjusted = mastery_threshold / (1.0 + (1.0 - edge.confidence) * 0.5)
  ```
  - confidence=0.8(INTERACTION) → adjusted=45.45（宽松，前置 mastery < 45.45 才触发）
  - confidence=0.5(DOC_ORDER) → adjusted=40（中等）
  - confidence=0.3(LLM_INFER) → adjusted≈37.04（严格，只有 mastery < 37.04 才触发）
  - 逻辑方向：低置信边应该更难触发（因为 LLM 推断的依赖关系本身不确定），所以 adjusted 门槛更低

- **冷启动建图三方法**（`:97-125`）：
  - `add_doc_order_edge`：confidence=0.5
  - `add_llm_infer_edge`：confidence=0.3
  - `strengthen_edge_by_interaction`：已有边 → 升级为 INTERACTION(0.8)；无边 → 新建高置信边

- **边置信度演化路径**：DOC_ORDER(0.5) 或 LLM_INFER(0.3) → 经实际交互验证 → INTERACTION(0.8)——图谱随使用逐渐变可靠

**UserProfile（`app/harness/user_profile.py`）**：

- **DEFAULT_PREFERENCES**（`:6-10`）：
  ```python
  explanation_style: "verbal"   # visual | verbal | mathematical
  pace: "normal"                # slow | normal | fast
  depth: "standard"             # shallow | standard | deep
  ```
- **字段**：preferences / topics_active / topics_mastered / learning_streak / total_sessions
- `sync_from_mastery(mastery_snapshot, mastered_threshold=0.8)`：从 MasteryGraph 快照同步 mastered topics
- `increment_session()`：每次 +1，**不做日期校验**（注释标注"精确 streak 需日期计算，后续迭代"）
- 持久化：`save()` / `load()` 通过 MasteryGraphStore 的 `user_profile_l3` 表

**Curator Agent（`app/agents/curator.py`）**：

- 继承 `CuratorBase`（`app/agents/base.py:50`）而非 `AgentBase`——CuratorBase 有一个 `__init_subclass__` 钩子（PEP 487）强制 handle 必须为同步方法，防止 async handle 被静默未 await
- **双时机触发**：
  - **TopicEntered → historical**（`:100-136`）：开局/切主题时，基于历史画像数据检查前置。渐进启用：无 PREREQ 边或所有前置节点无 mastery 数据 → 不发事件（冷启动克制）
  - **MasteryAssessed → observed**（`:46-96`）：回合中 Critic 评分后，更新图谱 + 检查前置。总是 update_mastery + emit GraphNodeStrengthened + ProfileUpdated；有 PREREQ 边时才额外 emit GraphPrereqWeakDetected
- **不调 LLM**：`curator.prompt.md` 标注"本 Agent 当前不使用 LLM（冷启动 LLM_INFER 建图待后续启用）"
- **不判文本语义**：结构层（图谱前置关系 + mastery 数值）归 Curator，文本语义（confusion/contradiction）归 Critic——正交分工

**存储层 MasteryGraphStore（`app/infrastructure/storage/mastery_graph_store.py`）**：

- aiosqlite 三表：`mastery_nodes`（复合主键 user_id+topic_id）、`mastery_edges`（含索引 idx_edges_user_from / idx_edges_user_to）、`user_profile_l3`（user_id 主键）
- 同时有 SQLAlchemy 表定义（`app/models/tables.py:58-89`）——**正在做双轨迁移**（aiosqlite → SQLAlchemy），尚未完成统一

**Profile API（`app/api/profile.py`）**：

- 仅一个端点：`GET /profile/`，JWT 认证
- 返回 `{user_id, stats: {sessions, avg_mastery}}`——sessions 从 `SessionTable` count，avg_mastery 从 `MasteryNodeTable` avg
- `UserProfile` 里的 preferences / learning_streak / topics_active / topics_mastered **全部未暴露**——存了但读不出来

**框架选择理由**（对照 `docs/research/2026-06-16-current-vs-frameworks-decision-report.md`）：

- 项目在 2026-06-16 做了系统性的 7 框架调研（mem0 / letta / cognee / graphiti / LightRAG / ragflow / Dify），结论是"借鉴设计、自研嫁接"
- **mem0**：User/Session/Agent 三层分层是通用记忆模型，而 MasteryGraph 是以**知识点为粒度**的有向图（含前置依赖），两者的数据模型不对齐，引入需要在上层写适配层
- **graphiti**：时序上下文图谱的设计（事实带有效时间窗 + Episode 溯源）被 Phase B-② spec 借鉴，但 graphiti 依赖 Neo4j 存储，用户已决策不引入 Neo4j（运维成本考量）
- **letta**：整套 agent 内存运行时，而 StudyAgent 已有自己的四层单向依赖架构（API→Orchestration→Harness→Infrastructure）和事件驱动协作环，letta 侵入性太大
- **核心逻辑**：MasteryGraph + Curator + MasteryGraphStore 三层已成型，自研的边际成本低于引入外部框架再写适配层的成本

### 标注的问题

1. **知识内容侧记忆几乎空白**：MasteryGraph 存的是"学习者对知识点的掌握程度"（状态），不是"知识内容本身"（本体）。`KnowledgeStore`（`app/infrastructure/storage/knowledge_store.py`）是内存 dict 假实现。项目能告诉你"用户对 Transformer 的掌握度是 45 分"，但没有任何机制把"上次教学对话中对 Self-Attention 的精彩解释"沉淀成可语义检索的长期记忆。这是决策报告明确指出的最大缺口。

2. **掌握度不带时间衰减**：`MasteryNode.mastery` 是静态分数，一旦 Critic 判了 80 就是 80。`last_practiced_at` 字段已经存在但未被任何衰减函数消费。Phase B-② spec（`docs/designs/2026-07-03-phase-b2-mastery-temporal-review-spec.md`）已完整设计了三种衰减曲线（艾宾浩斯指数/线性/阶梯）、ReviewTriggerService（阈值/间隔/混合三种策略）、用户可开关的复习触发、API 端点 `/review/trigger` + `/review/preferences`——**设计已完成，代码未实现**。

3. **Profile API 极简**：`GET /profile/` 只返 sessions 总数和 mastery 均值，preferences（解释风格/节奏/深度）、learning_streak、topics_active 全在 `user_profile_l3` 表里存着但没有 API 端点暴露。前端如果要做偏好设置页或学习统计页，需要新增端点。

4. **Curator 不调 LLM，冷启动建图受限**：`EdgeSource.LLM_INFER` 定义了接口（confidence=0.3），但 Curator 当前不调 LLM，意味着知识图谱的前置依赖关系需要人工标注或从教材目录结构（DOC_ORDER）导入——不能从教学对话中自动提取"这个知识点依赖那个知识点"。

5. **confusion_with 字段有定义但永不写入**：`MasteryNode.confusion_with` 字段存在（`:27`），Critic 能 emit `CONFUSION_DETECTED`（`app/agents/critic.py:59-67`），但 Curator 的 subscriptions 只有 `[MasteryAssessed, TopicEntered]`——**没订阅 ConfusionDetected**。混淆数据永远进不了图谱节点。

6. **learning_streak 简化实现**：`UserProfile.increment_session()` 每次调用 +1（`user_profile.py:45`），不做日期差计算。同日多次登录会被错误计为多天连续学习。注释坦白"精确 streak 需日期计算，后续迭代"。

7. **user_id 类型不一致**：Plan B 设计文档中 `user_id` 是 `str`，实际实现的 MasteryGraphStore 里也是 `INTEGER` 和 `TEXT` 混用——`mastery_nodes` 的 `user_id` 是 `INTEGER`，但 Plan B 文档中 SQL 声明为 `TEXT`。实际代码（`mastery_graph_store.py:24`）建表语句中是 `INTEGER`。

---

## 本次窗口的产出物

- 无代码改动（两个任务均为纯阅读分析）
- 本次交接文档：`docs/claude-chat/2026-07-14-handoff/2026-07-14-工作内容.md`
