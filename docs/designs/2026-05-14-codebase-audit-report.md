# StudyAgent Harness 代码框架审查报告

> 审查日期：2026-05-14
> 审查范围：`app/` 全部 Python 源码 + `tests/` 全部测试
> 当前分支：`feat/core-redesign-observability-memory-llm`（已合并至 master）

---

## 第一部分：项目概览与总体实现

### 1.1 项目定位

StudyAgent Harness 是一个**基于苏格拉底教学法的多 Agent 学习框架**。核心交互模式为"诊断→讲解→复述→追问"循环，引导用户主动构建知识，而非被动接受信息。

### 1.2 四层单向架构

```
┌─────────────────────────────────────────────────────┐
│  API 层 (FastAPI)                                    │  ← HTTP 入口，认证/对话/流式/评估/知识库/会话
├─────────────────────────────────────────────────────┤
│  编排层 (LangGraph StateGraph)                       │  ← 14节点主图 + 4 SubGraph + 系统评估图
├─────────────────────────────────────────────────────┤
│  Harness 层 (业务核心)                               │  ← 枚举/状态/路由/错误/可观测/记忆/工具/护栏/状态管理
├─────────────────────────────────────────────────────┤
│  基础设施层                                          │  ← LLM/RAG/存储/文件提取/OCR/搜索/Redis
└─────────────────────────────────────────────────────┘
         ↑ 严格单向依赖：上层调用下层，严禁反向引用 ↑
```

**依赖方向**：`api/ → agent/ → harness/ → infrastructure/`。`core/` 和 `models/` 作为横切层被各层引用。

### 1.3 技术栈

| 类别 | 技术 | 当前状态 |
|------|------|----------|
| Web 框架 | FastAPI + Pydantic V2 | ✅ 已实现 |
| Agent 编排 | LangGraph StateGraph + MemorySaver | ✅ 已实现 |
| LLM 接入 | LangChain ChatOpenAI + 重试/回退/流式/成本追踪 | ✅ 已实现 |
| RAG | LlamaIndex + Chroma/Qdrant (生产) / FakeRAGStore (测试) | ⚠️ 生产存根 |
| ORM | SQLAlchemy 2.0 async + Alembic | ✅ 已实现 |
| 可观测性 | Observability ABC → Langfuse / Console / Fake | ✅ 已实现 |
| 评估 | ragas (faithfulness/relevancy/context_precision) | ⚠️ 骨架 |
| 任务队列 | Celery + Redis | ⚠️ 存根 |
| UI | Chainlit | ⚠️ 存根 |
| 包管理 | uv | ✅ 已配置 |

### 1.4 核心数据流

#### 教学循环 (teach_loop)

```
用户输入 → route_intent → history_check → diagnose → knowledge_retrieval
    → explain → restate_check ─┬→ followup（追问，最多3轮）
                                ├→ explain（重讲，最多3轮）
                                └→ evaluate → summarize → END
```

#### 直答分支 (qa_direct)

```
用户提问 → rag_first → evidence_gate ─┬→ answer_policy → evaluate → summarize → END
                                        └→ recovery → answer_policy → ...
```

#### 重规划 / 复习

- **replan**：用户切换主题 → `route_intent`（重新路由，形成循环）
- **review**：直接调用 `summarize` 生成学习总结

### 1.5 渐进式规范系统

Agent 行为约束通过三层规范文件**按需加载**，避免一次性灌入全部上下文：

```
层级0 — _root.prompt.md        始终加载 (~200 tokens)
层级1 — agents/<name>.prompt.md 路由后加载 (~300 tokens)
层级2 — prompts/<name>.prompt.md 节点执行时加载 (~200 tokens)
```

`SpecLoader` 通过 `intent_map.yaml` 查询意图→资源映射，用 XML 标签 `<root_rules>/<agent_role>/<node_instruction>` 分隔后注入 `state["_system_prompt"]`。

### 1.6 状态模型

采用分层 TypedDict，每个子状态对应一个命名空间：

```
LearningState
  ├── user_input: str           # 用户原始输入
  ├── _system_prompt: str       # @with_spec 注入的临时字段
  ├── routing: RoutingState     # 意图、置信度
  ├── teaching: TeachingState   # 诊断、讲解、复述、追问、总结
  ├── retrieval: RetrievalState # RAG上下文、门控状态
  ├── evaluation: EvalState     # 掌握度、ragas指标
  ├── memory: MemoryState       # 历史、主题、记忆条目
  └── meta: MetaState           # 阶段、会话ID、错误信息
```

**命名空间隔离**：节点只写自己所属的 sub-state，跨命名空间写入被禁止。

### 1.7 实现完成度总览

| 模块 | 完成度 | 说明 |
|------|--------|------|
| API 层 (8个路由) | 90% | `/chat/multi` 和 `/profile` 为存根 |
| 编排层 (主图+SubGraph) | 95% | 主图完整，orchestrator_graph 有 import bug |
| Harness 层 (9个模块) | 100% | 枚举/状态/路由/错误/可观测/记忆/工具/护栏/状态管理均完成 |
| 基础设施层 | 70% | LLM 完整；RAG 生产存根；OCR/Web搜索/Redis 为空壳 |
| 测试 | 100% | 147个测试覆盖全部模块 |
| UI (Chainlit) | 5% | 空壳存根 |
| Worker (Celery) | 5% | 空壳存根 |

---

## 第二部分：逐文件夹与逐脚本功能分析

### 2.1 `app/agent/` — 编排层

职责：定义 LangGraph 图结构、节点执行逻辑、规范加载、多 Agent 编排。

#### `app/agent/graph.py`

**功能**：主图定义，是整个框架的核心编排入口。

**关键实现**：
- 构建 `LearningGraph`（14个节点 + 4条条件边）
- 节点：`route_intent`, `history_check`, `diagnose`, `knowledge_retrieval`, `explain`, `restate_check`, `followup`, `evaluate`, `summarize`, `rag_first`, `evidence_gate`, `answer_policy`, `recovery`, `replan`
- 条件边（来自 `routers.py`）：
  - `route_by_intent`：teach_loop / qa_direct / replan / review
  - `route_after_history`：有历史→跳过诊断；无历史→诊断
  - `route_after_restate`：通过→evaluate；未通过且 <3轮→followup/explain；≥3轮→evaluate
  - `route_after_gate`：pass→answer_policy；其他→recovery
- 编译时挂载 `MemorySaver` 作为 checkpointer
- 提供 `invoke_graph()` 辅助函数，供 API 层调用

**联动关系**：
- 引用 `app.agent.nodes.*`（14个节点函数）
- 引用 `app.agent.routers`（4个路由函数）
- 引用 `app.harness.state.LearningState`（状态类型）
- 被 `app.api.chat`, `app.api.chat_stream` 调用

#### `app/agent/routers.py`

**功能**：4个条件边路由函数，基于关键字匹配决定图的执行路径。

**关键实现**：
- `route_by_intent(state)`：读取 `state["routing"]["intent"]`，返回意图字符串
- `route_after_history(state)`：检查 `state["teaching"]["diagnosis"]` 是否存在
- `route_after_restate(state)`：检查 `explain_loop_count` 和复述评估结果
- `route_after_gate(state)`：读取 `state["retrieval"]["gate_status"]`

**联动关系**：
- 被 `graph.py` 的 `add_conditional_edges()` 调用
- 依赖 `app.harness.enums`（Intent, GateStatus 等）

#### `app/agent/node_wrapper.py`

**功能**：`safe_node` 装饰器，为所有节点提供统一的错误处理和可观测性埋点。

**关键实现**：
- 包装节点函数，在执行前后调用 `observability.trace_span()`
- 异常时调用 `ErrorHandler.handle()` 获取恢复策略
- 将错误信息写入 `state["meta"]["error"]`

**联动关系**：
- 引用 `app.harness.observability.get_observability()`
- 引用 `app.harness.error_handler.ErrorHandler`
- 被 `graph.py` 中所有节点注册时使用

#### `app/agent/spec_loader.py`

**功能**：渐进式规范加载引擎，按意图和节点动态组装 system_prompt。

**关键实现**：
- `SpecLoader` 类，维护 `.prompt.md` 文件缓存
- `compose(intent, node)` 方法：读取 `intent_map.yaml` → 加载层级0/1/2 → 用 XML 标签拼接
- 文件缓存避免重复 I/O

**联动关系**：
- 读取 `app/agent/specs/` 目录下的所有规范文件
- 被 `spec_decorator.py` 调用

#### `app/agent/spec_decorator.py`

**功能**：`@with_spec(intent, node)` 装饰器，在节点执行前自动注入 system_prompt。

**关键实现**：
- 调用 `SpecLoader.compose(intent, node)` 获取组合后的 prompt
- 将结果写入 `state["_system_prompt"]`
- 节点函数通过 `state["_system_prompt"]` 读取，不再硬编码 prompt

**联动关系**：
- 引用 `spec_loader.py`
- 被 `app/agent/nodes/` 下所有节点使用

#### `app/agent/specs/` — 规范仓库

**功能**：存储 Agent 运行时行为规范（双文件制：`.md` + `.prompt.md`）。

**结构**：
- `_root.md` / `_root.prompt.md`：全局底线规则（层级0，始终加载）
- `intent_map.yaml`：意图→资源映射表，定义每个意图下各节点需要加载哪些规范
- `agents/`：4个 Agent 角色规范（teaching, eval, retrieval, orchestrator），层级1
- `prompts/`：14个节点指令规范（diagnose, explain, followup 等），层级2

**联动关系**：
- 被 `spec_loader.py` 按需读取
- 修改时必须 `.md` 和 `.prompt.md` 同步修改

#### `app/agent/nodes/` — 14个薄壳节点

所有节点遵循统一模式：`@with_spec` → 读取 state → 委托 LLM/harness → 写入 sub-state。

| 节点文件 | 意图 | 读取 | 写入 | 功能 |
|----------|------|------|------|------|
| `route_intent.py` | 通用 | user_input | routing, meta | 意图识别，调用 IntentRouter |
| `history_check.py` | teach_loop | memory.history, teaching.diagnosis | teaching, meta | 检查是否有历史诊断结果 |
| `diagnose.py` | teach_loop | user_input | teaching.diagnosis, meta | 诊断用户知识盲区 |
| `knowledge_retrieval.py` | teach_loop | teaching.diagnosis | retrieval.rag_context, meta | RAG 检索相关知识 |
| `explain.py` | teach_loop | teaching.diagnosis, retrieval.rag_context | teaching.explanation, meta | 针对性讲解 |
| `restate_check.py` | teach_loop | teaching.explanation, user_input | teaching.restatement_eval, meta | 检测用户复述理解程度 |
| `followup.py` | teach_loop | teaching.explanation | teaching.followup_question, meta | 生成追问问题 |
| `evaluate.py` | teach_loop | teaching.diagnosis, teaching.restatement_eval | evaluation.mastery_*, meta | 评估掌握程度（JSON输出） |
| `summarize.py` | teach_loop | memory.topic, evaluation.* | teaching.summary, meta | 生成学习总结 |
| `rag_first.py` | qa_direct | user_input | retrieval.rag_context, meta | RAG 优先检索 |
| `evidence_gate.py` | qa_direct | retrieval.rag_context | retrieval.gate_status, meta | 证据门控（pass/supplement/reject） |
| `answer_policy.py` | qa_direct | retrieval.rag_context, user_input | teaching.reply, meta | 根据证据和策略生成回答 |
| `recovery.py` | qa_direct | meta.error | teaching.reply, meta | 错误恢复后生成回答 |
| `replan.py` | replan | user_input | routing.intent, meta | 重新路由意图 |

**联动关系**：
- 全部通过 `_llm.invoke(session_id=..., node=..., intent=...)` 调用 LLM
- 全部通过 `state["_system_prompt"]` 获取规范
- 被 `graph.py` 注册为主图节点

#### `app/agent/multi_agent/` — 4个 SubGraph

| 文件 | 子图名 | 节点 | 功能 |
|------|--------|------|------|
| `state.py` | MultiAgentState | — | 扩展 LearningState，增加 agent_messages, current_agent, agent_trace |
| `teaching_graph.py` | TeachingAgent | diagnose→explain→restate_check→followup | 教学子图 |
| `eval_graph.py` | EvalAgent | evaluate_mastery→evaluate_ragas | 双重评估子图 |
| `retrieval_graph.py` | RetrievalAgent | knowledge_retrieval | 单节点检索子图 |
| `orchestrator_graph.py` | OrchestratorAgent | orchestrate→summarize | 调度子图 |

**已知问题**：`orchestrator_graph.py` 有 import bug — `from agent.node_wrapper` 应为 `from app.agent.node_wrapper`。

**联动关系**：
- 引用 `app/agent/nodes/` 中的节点函数
- 引用 `app.harness.state` 中的状态类型
- 被 `graph.py` 或未来 API 调用

#### `app/agent/system_eval/` — 系统评估图

| 文件 | 功能 |
|------|------|
| `eval_graph.py` | 系统评估主图：teaching_eval → orchestrator_eval |
| `teaching_eval.py` | 计算讲解长度、掌握分数、教学质量指标 |
| `orchestrator_eval.py` | 检查分支轨迹的流程正确性 |
| `eval_store.py` | 内存字典存储评估结果 |

**联动关系**：
- 读取 `LearningState` 中的 evaluation 和 teaching 数据
- 独立于主图运行，用于离线质量评估

---

### 2.2 `app/harness/` — 业务核心层

职责：提供框架级基础设施（枚举、状态、路由、错误处理、可观测性、记忆、工具、护栏、状态管理），不依赖任何上层模块。

#### `app/harness/enums.py`

**功能**：定义所有 StrEnum，确保有限集合的类型安全。

| 枚举 | 值 | 用途 |
|------|-----|------|
| `Stage` | INIT, ROUTING, DIAGNOSING, EXPLAINING, ... | 节点执行阶段标记 |
| `Intent` | TEACH_LOOP, QA_DIRECT, REVIEW, REPLAN | 用户意图分类 |
| `GateStatus` | PASS, SUPPLEMENT, REJECT | 证据门控结果 |
| `MasteryLevel` | WEAK, PARTIAL, MASTERED | 掌握度等级 |
| `ErrorKind` | RAG_TIMEOUT, LLM_ERROR, FATAL, ... | 错误分类 |
| `RecoveryAction` | RETRY, FALLBACK_LLM, SKIP_RETRIEVAL, ABORT | 恢复策略 |
| `MemoryScope` | WORKING, EPISODE, SESSION, USER, GLOBAL | 记忆作用域（5级） |
| `AgentRole` | TEACHING, EVAL, RETRIEVAL, ORCHESTRATOR | Agent 角色 |
| `RetrievalMode` | HYBRID, KEYWORD, SEMANTIC | 检索模式 |
| `EvalMetric` | FAITHFULNESS, RELEVANCY, CONTEXT_PRECISION | 评估指标 |

**联动关系**：被所有其他模块引用，是整个框架的"共享词汇表"。

#### `app/harness/state/` — 分层状态模型

7个文件，每个定义一个 TypedDict 子状态：

| 文件 | 子状态 | 关键字段 |
|------|--------|----------|
| `__init__.py` | LearningState | 聚合所有子状态 + user_input, _system_prompt |
| `routing.py` | RoutingState | intent, confidence, branch_trace |
| `teaching.py` | TeachingState | diagnosis, explanation, restatement_eval, followup_question, reply, summary, explain_loop_count |
| `retrieval.py` | RetrievalState | rag_context, gate_status, retrieval_mode |
| `evaluation.py` | EvalState | mastery_score, mastery_level, mastery_rationale, ragas_metrics |
| `memory.py` | MemoryState | history, topic, memory_entries, short_term_ids, long_term_context, user_profile_summary, mastery_history |
| `meta.py` | MetaState | stage, session_id, error, turn_count |

**联动关系**：
- 被 `app/agent/` 所有节点读取/写入
- 被 `app/agent/routers.py` 作为路由判断依据
- 被 `app/harness/state_manager.py` 管理快照/恢复

#### `app/harness/intent_router.py`

**功能**：规则优先 + LLM 兜底的用户意图路由器。

**关键实现**：
- `RULE_MAP`：关键字→Intent 的映射表（如"提问"、"是什么"→QA_DIRECT）
- `IntentRouter.route(text)`：先匹配规则，未命中时返回 TEACH_LOOP 默认意图
- LLM 兜底路由暂未实现（预留接口）

**联动关系**：
- 被 `app/agent/nodes/route_intent.py` 调用
- 输出 `Intent` 枚举值写入 `state["routing"]["intent"]`

#### `app/harness/error_handler.py`

**功能**：错误分类与恢复策略映射。

**关键实现**：
- `_classify(error)`：根据异常类型/消息分类为 `ErrorKind`
- `_recovery_map`：ErrorKind → RecoveryAction 的映射
- `handle(error)`：返回分类结果和恢复建议

**联动关系**：
- 被 `node_wrapper.py` 的 `safe_node` 调用
- 被 `app/infrastructure/llm.py` 的重试逻辑参考

#### `app/harness/observability.py`

**功能**：可观测性抽象层，提供 LLM 调用追踪、Token 统计、成本计算。

**关键实现**：
- `LLMSpan`：数据类，记录单次 LLM 调用（model, input_tokens, output_tokens, cost, latency_ms）
- `SessionStats`：按会话聚合 LLMSpan，提供 `add_span()` / `summary()`
- `Observability`：ABC，定义 7 个抽象方法（trace_span, log_event, flush 等）
- 3 个实现：
  - `ConsoleObservability`：控制台输出
  - `FakeObservability`：测试替身，记录调用历史
  - `_LangfuseObservability`：生产级 Langfuse 集成
- `get_observability()`：工厂函数，根据环境变量选择实现

**联动关系**：
- 被 `node_wrapper.py` 调用（每个节点的 trace_span）
- 被 `app/infrastructure/llm.py` 调用（记录 LLM 调用指标）
- `SessionStats` 被 API 层用于返回会话统计

#### `app/harness/memory.py`

**功能**：双层记忆系统（短期 LRU + 长期 SQLite）。

**关键实现**：
- `MemoryItem`：统一数据模型，含 content, scope, tags, ttl, access_count, is_expired 属性
- `ShortTermStore`：基于 OrderedDict 的 LRU 缓存，按 scope 设置不同 TTL
  - WORKING: 60s, EPISODE: 600s, SESSION: 3600s
  - `recall(keyword, tags)`：关键字+标签匹配
  - `items_to_persist()`：返回可持久化的条目（SESSION 级别以上）
- `LongTermStore`：异步 SQLite 持久化（委托 `memory_store.py`）
  - `store()`, `search()`, `compress()` (LLM 压缩摘要)
- `MemoryManager`：门面类，路由短期/长期存储
  - `remember()` → 短期存储
  - `recall()` → 短期查询
  - `persist()` → 批量写入长期存储
  - `forget()` → 从短期移除

**联动关系**：
- 被 `history_check.py` 节点读取历史记忆
- `LongTermStore` 委托 `app/infrastructure/storage/memory_store.py`
- MemoryScope 枚举来自 `enums.py`

#### `app/harness/guardrails.py`

**功能**：输入/输出安全护栏。

**关键实现**：
- 输入护栏：长度检查（>500字截断）、注入模式检测（SQL/系统提示注入）
- 输出护栏：引用检查（确保回答引用了知识源）
- 工具护栏：参数验证

**联动关系**：
- 可被节点或 API 层在处理用户输入前调用
- 当前未被显式集成到主流程中（预留接口）

#### `app/harness/tool_registry.py`

**功能**：工具注册与执行框架。

**关键实现**：
- `ToolSchema`：工具元数据（name, description, parameters）
- `ToolResult`：执行结果（output, error）
- `register(schema, handler)`：注册工具
- `execute(name, params)`：执行工具
- `select(task_description)`：根据描述选择合适工具
- `list_tools()`：列出所有已注册工具

**联动关系**：
- 预留为未来 Agent 工具调用能力的基础
- 当前无工具注册

#### `app/harness/state_manager.py`

**功能**：状态转换、快照、恢复。

**关键实现**：
- `transition(state, updates)`：深拷贝 state + 合并更新
- `snapshot(state)`：序列化为 JSON 字符串
- `restore(snapshot_json)`：从 JSON 恢复状态

**联动关系**：
- 被 `graph.py` 用于状态管理
- 可被错误恢复流程使用

---

### 2.3 `app/infrastructure/` — 基础设施层

职责：提供外部服务接入（LLM、RAG、数据库、文件提取、OCR、搜索），所有 I/O 操作在此层完成。

#### `app/infrastructure/llm.py`

**功能**：LLM 服务封装，提供重试、回退、流式、成本追踪。

**关键实现**：
- `LLMConfig`：dataclass，配置主模型/回退模型/重试次数/Token预算/温度/超时
- `TokenBudgetExceeded`：自定义异常
- `FakeLLM`：测试替身
  - `invoke()` / `invoke_json()` / `stream()`
  - `call_history`：记录所有调用
  - `assert_called_with()`：断言辅助
  - `summarize_memories()`：记忆压缩摘要
- `LLMService`：生产级 LLM 服务
  - 延迟初始化 `ChatOpenAI` 实例
  - `invoke()`：带指数退避重试 + 模型回退
  - `invoke_json()`：调用 + JSON 解析（含 Markdown 代码块清理）
  - `stream()`：生成器，逐 token 输出
  - `_calc_cost()`：静态方法，按模型定价表计算成本
  - Token 预算检查

**联动关系**：
- 被 `app/agent/nodes/` 下所有节点调用（通过 `_llm.invoke(session_id=..., node=..., intent=...)`）
- 被 `app/harness/memory.py` 的 `LongTermStore.compress()` 调用
- 调用 `app/harness/observability.py` 记录 LLMSpan

#### `app/infrastructure/rag/` — RAG 检索

| 文件 | 功能 |
|------|------|
| `store.py` | `FakeRAGStore`（内存+字符级评分）和 `RAGStore`（生产存根） |
| `coordinator.py` | `RAGCoordinator`：组装 store + retrieve，计算置信度分数 |

**联动关系**：
- 被 `knowledge_retrieval.py` 和 `rag_first.py` 节点调用
- 生产模式需要配置 LlamaIndex + 向量数据库

#### `app/infrastructure/storage/` — 存储层

| 文件 | 功能 | 双模式 |
|------|------|--------|
| `session_store.py` | 会话 CRUD | SQLAlchemy async / 内存字典 |
| `user_store.py` | 用户 CRUD + 按用户名查询 | SQLAlchemy async / 内存字典 |
| `knowledge_store.py` | 知识库 CRUD | 仅内存 |
| `eval_store.py` | 评估结果存储 | 仅内存 |
| `memory_store.py` | 长期记忆 SQLite 持久化 | SQLite async |

**关键实现**：
- `session_store.py` 和 `user_store.py` 支持 `db=None` 时自动回退到内存字典
- `memory_store.py` 使用 LIKE 搜索（非 FTS5 MATCH），兼容中文字符
- 表结构：memory_entries, memory_fts, memory_summaries, user_profiles

**联动关系**：
- 被 `app/api/` 路由模块调用
- `memory_store.py` 被 `app/harness/memory.py` 的 `LongTermStore` 调用
- `session_store.py` 被 `app/api/sessions.py` 和 `app/api/chat.py` 使用

#### `app/infrastructure/extraction/`

**功能**：文件内容提取。

| 格式 | 实现 |
|------|------|
| txt | 直接读取 |
| md | 直接读取 |
| csv | csv.reader 解析 |
| pdf | 存根（返回 "PDF extraction not implemented"） |

**联动关系**：被 `app/api/knowledge.py` 在上传知识文件时调用。

#### `app/infrastructure/external/`

| 文件 | 功能 | 状态 |
|------|------|------|
| `ocr.py` | OCR 服务 | 空壳 |
| `web_search.py` | Web 搜索 | 空壳（返回 []） |
| `redis_pubsub.py` | Redis 发布/订阅 | pass 方法（空实现） |

---

### 2.4 `app/api/` — API 层

职责：HTTP 入口，参数验证，调用编排层，返回结果。

| 文件 | 端点 | 功能 | 状态 |
|------|------|------|------|
| `auth.py` | POST /auth/register, POST /auth/login | 用户注册/登录 | ✅ |
| `chat.py` | POST /chat | 同步学习对话 | ✅ |
| `chat_stream.py` | POST /chat/stream | SSE 流式对话 | ✅ |
| `chat_multi.py` | POST /chat/multi | 多 Agent 对话 | ⚠️ 存根 |
| `eval.py` | GET/POST /eval | 评估查询/重跑 | ✅ |
| `knowledge.py` | POST/GET /knowledge | 知识库 CRUD | ✅ |
| `sessions.py` | GET /sessions | 会话列表/详情 | ✅ |
| `profile.py` | GET /profile/{user_id} | 用户画像 | ⚠️ 存根 |
| `errors.py` | — | 全局异常处理器 | ✅ |

**联动关系**：
- `chat.py` → `app/agent/graph.invoke_graph()` → 主图执行
- `chat_stream.py` → `graph.astream_events()` → SSE 流式
- `auth.py` → `app/infrastructure/storage/user_store.py`
- `knowledge.py` → `app/infrastructure/storage/knowledge_store.py` + `extraction/file_extract.py`
- `sessions.py` → `app/infrastructure/storage/session_store.py`
- `eval.py` → `app/infrastructure/storage/eval_store.py`

---

### 2.5 `app/core/` — 横切配置层

| 文件 | 功能 |
|------|------|
| `config.py` | Pydantic Settings，管理所有环境变量（OpenAI key, Langfuse key, DB URL, Redis URL 等） |
| `database.py` | SQLAlchemy async engine + sessionmaker + `init_db()` 建表 |
| `prompts.py` | 用户侧 Prompt 模板（DIAGNOSE_USER, EXPLAIN_USER 等） |

**联动关系**：
- `config.py` 被几乎所有模块引用（通过 `from app.core.config import settings`）
- `database.py` 被 `app/main.py` 的 lifespan 调用（启动时建表）
- `prompts.py` 被节点函数引用（构造 LLM 用户消息）

---

### 2.6 `app/models/` — 数据模型层

| 文件 | 功能 |
|------|------|
| `schemas.py` | Pydantic V2 请求/响应模型（ChatRequest, ChatResponse, AuthRequest, EvalResponse 等） |
| `tables.py` | SQLAlchemy ORM 表定义（UserTable, SessionTable, KnowledgeTable, EvalTable） |

**联动关系**：
- `schemas.py` 被 `app/api/` 用于请求验证和响应序列化
- `tables.py` 被 `app/core/database.py` 的 `init_db()` 创建表
- `tables.py` 被 `app/infrastructure/storage/` 的 Store 类操作

---

### 2.7 `app/main.py`

**功能**：FastAPI 应用入口。

**关键实现**：
- `lifespan` 异步上下文管理器：启动时调用 `init_db()`
- 挂载 7 个路由模块
- `/health` 健康检查端点
- 可选的 Vue SPA 静态文件服务

**联动关系**：
- 聚合所有 `app/api/` 路由
- 调用 `app/core/database.init_db()`

---

### 2.8 `app/ui/` — Chainlit 前端

| 文件 | 功能 | 状态 |
|------|------|------|
| `chainlit_app.py` | Chainlit 消息处理器 | 空壳 |
| `chainlit_backend.py` | Chainlit 后端接口 | 空壳 |

---

### 2.9 `app/worker/` — Celery 任务

| 文件 | 功能 | 状态 |
|------|------|------|
| `celery_app.py` | Celery 应用实例 | 空壳（需额外依赖） |
| `tasks.py` | 异步任务定义 | 空壳 |

---

### 2.10 `tests/` — 测试套件

147 个测试，按层分布：

| 目录 | 测试数 | 覆盖范围 |
|------|--------|----------|
| `tests/unit/harness/` | 58 | 枚举、状态、路由、错误处理、护栏、记忆、可观测 |
| `tests/unit/infrastructure/` | 28 | LLM、RAG、存储、记忆存储 |
| `tests/unit/agent/` | 48 | 图执行、节点、多Agent、系统评估、SpecLoader |
| `tests/unit/api/` | 6 | API 端点 |
| `tests/unit/core/` | 7 | 配置、数据库 |

**已知问题**：`tests/unit/infrastructure/test_stores.py` 有 4 个测试使用已废弃的 `asyncio.get_event_loop().run_until_complete()` 模式，在 Python 3.12+ 下会报 RuntimeError（非本次修改引入）。

---

### 2.11 模块间联动全景图

```
app/main.py
  ├── app/core/config.py ←─ 所有模块读取配置
  ├── app/core/database.py ←─ init_db() 建表
  │
  ├── app/api/auth.py ──→ app/infrastructure/storage/user_store.py
  ├── app/api/chat.py ──→ app/agent/graph.py ──→ app/agent/nodes/*.py
  ├── app/api/chat_stream.py ──→ app/agent/graph.py
  ├── app/api/knowledge.py ──→ app/infrastructure/storage/knowledge_store.py
  │                          └→ app/infrastructure/extraction/file_extract.py
  ├── app/api/sessions.py ──→ app/infrastructure/storage/session_store.py
  ├── app/api/eval.py ──→ app/infrastructure/storage/eval_store.py
  │
  └── app/agent/graph.py
        ├── app/agent/routers.py ──→ app/harness/enums.py
        ├── app/agent/node_wrapper.py ──→ app/harness/observability.py
        │                              └→ app/harness/error_handler.py
        ├── app/agent/spec_decorator.py ──→ app/agent/spec_loader.py ──→ app/agent/specs/
        │
        ├── app/agent/nodes/route_intent.py ──→ app/harness/intent_router.py
        ├── app/agent/nodes/diagnose.py ──→ app/infrastructure/llm.py
        ├── app/agent/nodes/explain.py ──→ app/infrastructure/llm.py
        ├── app/agent/nodes/knowledge_retrieval.py ──→ app/infrastructure/rag/coordinator.py
        ├── app/agent/nodes/evaluate.py ──→ app/infrastructure/llm.py (invoke_json)
        ├── ... (其他节点同理)
        │
        └── app/agent/multi_agent/ ──→ 复用 app/agent/nodes/ 中的节点
```

---

## 第三部分：问题与建议

### 3.1 已知 Bug

1. **`orchestrator_graph.py` import 错误**：`from agent.node_wrapper` 应为 `from app.agent.node_wrapper`，会导致运行时 ImportError
2. **`test_stores.py` 异步测试模式过时**：4个测试使用 `asyncio.get_event_loop().run_until_complete()`，Python 3.12+ 报错

### 3.2 存根模块（待实现）

| 模块 | 优先级 | 说明 |
|------|--------|------|
| `app/api/chat_multi.py` | 高 | 多 Agent 对话，当前返回固定字符串 |
| `app/api/profile.py` | 中 | 用户画像，需对接长期记忆数据 |
| `app/infrastructure/extraction/file_extract.py` (PDF) | 中 | PDF 提取未实现 |
| `app/infrastructure/external/ocr.py` | 低 | OCR 空壳 |
| `app/infrastructure/external/web_search.py` | 低 | Web 搜索空壳 |
| `app/ui/` | 低 | Chainlit 前端空壳 |
| `app/worker/` | 低 | Celery 异步任务空壳 |

### 3.3 架构改进建议

1. **护栏集成**：`guardrails.py` 已实现但未集成到主流程，建议在 `node_wrapper.py` 或 `graph.py` 入口处添加输入/输出检查
2. **工具注册**：`tool_registry.py` 已实现但无工具注册，建议先注册基础工具（知识查询、记忆检索等）
3. **LLM 兜底路由**：`intent_router.py` 的 LLM 兜底逻辑未实现，当规则匹配失败时固定返回 TEACH_LOOP
4. **RAG 生产实现**：`RAGStore` 为存根，生产环境需要实现 LlamaIndex + Chroma/Qdrant 集成
5. **错误恢复闭环**：`recovery.py` 节点存在但恢复逻辑较简单，建议增强 RecoveryAction 的具体执行策略
