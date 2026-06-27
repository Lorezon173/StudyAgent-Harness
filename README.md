# StudyAgent Harness

基于苏格拉底教学法的多 Agent 学习框架。系统不直接灌输答案，而是通过诊断 → 讲解 → 复述 → 追问的交互循环，引导学习者主动构建理解，并在过程中持续评估掌握度、维护知识图谱画像。

## 双栈现状（先读这一节）

项目当前**两套实现并存**，由环境变量 `FEATURE_USE_NEW_AGENT_GRAPH` 在运行时切换：

| | 新栈（推荐） | 老栈（默认回退） |
|---|---|---|
| 位置 | `app/` | `app_old/`（2026-06-02 归档） |
| 范式 | 事件驱动 5-Agent 协作环 | LangGraph StateGraph（14+ 节点主图） |
| LLM | 调真实 LLM，有真实教学能力 | 全节点用 `FakeLLM` 返回固定假数据，仅演示流程 |
| 启用 | `FEATURE_USE_NEW_AGENT_GRAPH=true` | flag 未设 / 其他值 |
| 落库 | `/chat`、`/chat/stream` 持久化落库 + 回填 turn_count | 不落库 |

flag 在**每个请求处理函数内实时读取**（`app/core/feature_flags.py`），支持热切换、一键回退。新栈对 `app_old.*` 零依赖；老栈仍是 flag 关闭时 `/chat`、`/chat/stream` 的活路径，但靠 FakeLLM，**手动体验真实教学请开新栈**。

本 README 以下内容除「老栈」小节外，均描述**新栈（`app/`）**。

## 架构概览

新栈遵循四层单向依赖，严禁反向引用：

```
┌────────────────────────────────────────────────────────────┐
│  API 层 (FastAPI)                                           │
│  auth / chat / chat-stream(SSE) / eval / knowledge /        │
│  sessions / profile（全部挂在 /api 前缀下）                 │
├────────────────────────────────────────────────────────────┤
│  编排层 (Orchestration)                                     │
│  collab_loop 事件循环 + LangGraph 主图骨架 +                │
│  assembly 装配线 + orchestrator_rules.yaml 规则 DSL         │
├────────────────────────────────────────────────────────────┤
│  Harness 层 (业务核心)                                      │
│  事件契约(events/eventbus) + 共享状态(workspace_state) +    │
│  路由器(orchestrator) + 教学状态机(teaching_policy) +       │
│  画像记忆(mastery_graph/user_profile) + 枚举 + 可观测性     │
├────────────────────────────────────────────────────────────┤
│  基础设施层 (Infrastructure)                                │
│  LLM / RAG(多Provider) / 存储 / 文件提取 / OCR / 代码索引   │
└────────────────────────────────────────────────────────────┘
         ↑ 严格单向依赖 ↑
```

核心范式是**事件驱动多 Agent 协作环**：各 Agent 通过 `EventBus` 收发带「所有权白名单」校验的 `Event`，由单线程优先级队列循环 `run_collab_loop` 驱动，`Orchestrator` 用回合屏障 + 规则 DSL 做路由裁决。

## 五个 Agent 与职能正交

系统装配 5 个 Agent（`EventSource` 共 7 个角色，另两个 `user` / `orchestrator` 不是 Agent 类）。核心原则是**职能正交**——每个 Agent 只发自己专业领域的事件，越权由 EventBus 在 `publish` 时按白名单运行时拦截（`EmitViolationError`）。

| Agent | source | 订阅 | 可发事件 | 职责 |
|---|---|---|---|---|
| **Tutor** | tutor | `ActionRequested`（target=tutor） | `TutorAsked` / `TutorExplained` / `TutorRequestedRecap` / `TutorOfferedAnalogy` | 只生成教学内容（提问/讲解/复述/类比），按 action 分派；不评判 |
| **Critic** | critic | `UserMessage` / `RetrievedEvidence` | `MasteryAssessed` / `ConfusionDetected` / `ContradictionDetected` / `LowConfidenceDetected` / `RAGQualityAssessed` | 只判文本语义层；单次 LLM 调用产 JSON 拆多条 emit；RAG 质量仅 teaching 场景评（省成本） |
| **Retriever** | retriever | `ActionRequested`（target=retriever） | `RetrievedEvidence` / `RetrievalFailed` | 机械层检索，委托 `RAGCoordinator.search`；按 `max_score<0.3` 机械判检索状态；不评语义质量 |
| **Conductor** | conductor | `ConductorRequested` | `ConductorDecided` | LLM 决策兜底；只在已有观察上路由，观察不足时请求补观察；不直接发 ActionRequested（由 Orchestrator 转译） |
| **Curator** | curator | `MasteryAssessed` / `TopicEntered` | `ProfileUpdated` / `GraphNodeStrengthened` / `GraphPrereqWeakDetected` | 只判结构层（图谱 PREREQ 边 + 前置掌握度）；双时机：实测(observed) / 历史画像(historical) |

所有 Agent 继承 `AgentBase`（`app/agents/base.py`），统一契约：声明 `source` / `subscriptions` / `emittable_types` 三个类属性，实现 `handle(event, ws)`，可选实现 `evaluate(test_case)` 供部件级评估。硬约束：Agent 之间不互相直接调用、不直接写 DB/LLM、不写 `WorkspaceState`。

## 协作环工作机制

```
种子事件: UserMessage + TopicEntered + ActionRequested(tutor_ask)
  ↓
run_collab_loop（单线程优先级队列）
  ├─ 每个事件先经 EventBus.publish（白名单校验 + 持久化）→ on_event 钩子 → 入队
  ├─ 出队分发给订阅该事件的 Agent.handle，产出新事件再入队
  └─ Orchestrator.on_event 做回合屏障裁决：
        观察类事件进缓冲 → micro-turn 内注入 OrchestratorTick(优先级最低，最后出队)
        Tick 出队时对完整观察集裁决一次 → 规则引擎匹配 → TeachingPolicy 决定模式切换
        → 发 ActionRequested（继续教学）或 LoopExit（出环，唯一退出信号）
  ↓
从事件流提取 reply / mastery_score(0-100) / mode_path / cost → persist_turn 落库
```

**事件优先级**：`LoopExit(5) < Observation(10) < Default(20) < Tick(100)`，配 `heapq` + 入队序号实现确定性回放。**事件 ID** 用「13 位毫秒时间戳 + 12 位随机 hex」（ULID 语义，字典序即时序，无第三方依赖）。

**Orchestrator 规则 DSL**（`app/orchestration/orchestrator_rules.yaml`，priority 大者优先）：

```yaml
prereq_weak_observed   when: {prereq_weak: true, prereq_basis: observed}  → regress_to_prereq      (100)
contradiction          when: {contradiction: true}                        → tutor_correct          (90)
confusion              when: {confusion: true}                            → tutor_offer_analogy    (80)
weak_within_repeat     when: {mastery: weak, repeat_lt: 2}                 → tutor_re_explain       (70)
partial                when: {mastery: partial}                           → tutor_request_recap    (60)
mastered_topic_complete when: {mastery: mastered, topic_complete: true}   → loop_exit              (50)
rag_quality_low        when: {rag_quality_low: true}                      → retriever_expand_query (40)
default                when: {}                                           → conductor_decide       (0)
```

规则全不命中时落到 `conductor_decide`，交给 Conductor 做 LLM 兜底决策。`TeachingPolicy`（`app/harness/teaching_policy.py`）是纯状态机，按当前教学模式（Socratic / Feynman / Analogy / Regress）和观察集决定下一步模式与动作。

## 知识图谱画像（Mastery Graph）

`app/harness/mastery_graph.py` 维护每个用户的掌握度图谱：

- **节点** `MasteryNode`：topic_id / topic_name / **mastery（0-100 整数）** / practice_count / confusion_with / rationale（评估理由）
- **边** `MasteryEdge`：PREREQ（前置）/ RELATED（相关）/ CONFLICT（冲突）三类，带 weight + confidence
- **边来源置信度**：INTERACTION(0.8) > DOC_ORDER(0.5) > LLM_INFER(0.3)，支持冷启动建图
- **前置薄弱检测** `find_weak_prereqs`：阈值 50，低置信度的边采用更严格的调整阈值 `threshold/(1+(1-conf)*0.5)`

`UserProfile`（`app/harness/user_profile.py`）维护偏好（讲解风格 / 节奏 / 深度）、活跃与已掌握主题、学习连续天数、会话总数。

> 注：存在两套掌握度持久化——`MasteryGraphStore`（aiosqlite，旧，节点表无 rationale 列）与 `SQLAlchemyMasteryStore`（PG/SQLite 双模，含 rationale）。**生产 chat 流程用后者**。

## 渐进式规范系统（specs）

Agent 的行为约束通过分层规范文件**按需加载**，避免一次性灌入全部上下文。`app/specs/` 下每个 Agent 一对双文件：`.md`（开发者规范）+ `.prompt.md`（LLM 运行时 Prompt），修改时必须同步。

```
app/specs/
  _root.md / _root.prompt.md                     层级0 全局底线规则（始终加载）
  agents/{tutor,critic,conductor,curator,retriever}.md + .prompt.md   层级1 角色定义
  event_map.yaml                                 事件→Agent→产出映射（规范文档）
  loader.py                                       SpecLoader
```

`SpecLoader.compose(agent, intent)` 三层组装：层级0 根规范 + 层级1 角色定义 + 层级2 从角色文件中按 `### <intent>` 标题抽取的子段落（合并标题 `### a / b / c` 让相近 intent 共享指令段），用 `---` 分隔拼接，注入 system prompt。当前 Tutor / Critic / Conductor 在 handle 内调用它注入 prompt。

> **诚实标注**：`event_map.yaml` 目前**没有运行时消费者**——实际事件订阅是各 Agent 类的 `subscriptions` 类属性 + `assembly.py` 里 `bus.subscribe(agent, agent.subscriptions)` 装配的。`event_map.yaml` 是规范/文档产物，不是运行时配置源。真正驱动运行时决策的配置是 `orchestrator_rules.yaml`。

## 评估体系（旁路 L2）

`app/eval/` 是一套**离线旁路**评估子系统：不在请求热路径上，而是消费 `EventStore.replay()` 回放的事件链做分析。四层基准：

| 模块 | 层级 | 职责 |
|---|---|---|
| `component_bench.py` | §5.2 部件级 | 对各 Agent 的 `evaluate()` 跑黄金用例，按阈值比对 |
| `system_bench.py` | §5.3 系统级 | 从场景 YAML 加载，对 trace 做结果断言（mastery/max_turns）+ 过程断言（mode_path / must_contain / must_not_contain） |
| `collaboration_bench.py` | §5.4 协作级 | 消费 `parent_id` 因果链算六维：职能正交违约率（应恒 0）/ 协作效率 / 决策稳定 / 冲突消解 / 因果链质量 / 轨迹偏离 |
| `ab_controller.py` | §5.5 A/B & 消融 | 参数 A/B + 组件消融（`StubAgent` 禁用某 Agent），回答「架构本身值多少增益」 |
| `selection_reporter.py` | §5.6 选型报告 | 聚合四层结果产出 Markdown |
| `kernel.py` | — | 薄编排层，统一委托各 bench |
| `judge.py` | §5.1.1 | Judge 适配层：构造 OpenAI judge 并强制与被评 Agent **不同族**（anthropic ≠ openai），同族 / 无 key / unknown 一律返回 `None` 触发降级 |

**RAGAS 集成**：`RetrieverAgent.evaluate()` 在有 golden 数据时调用 `ragas.evaluate`（faithfulness / answer_relevancy / context_precision，对齐 RAGAS 0.4.3 API），RAGAS 不可用或无 key 时优雅降级回启发式分数。配套设计见 [混合评估 spec（RAGAS + DeepEval）](docs/designs/2026-06-22-hybrid-evaluation-ragas-deepeval.md)。

> **诚实标注**：评估框架已实现并有测试覆盖，但**尚未接到在线 API 或 CLI**——`/api/eval` 端点只读 `EvalStore`，不调用任何 bench；benches 当前仅由 `tests/eval/` 驱动。

## RAG 检索

`RAGCoordinator`（`app/infrastructure/rag/coordinator.py`）是多 Provider 协调器：`IndexProvider` 协议 + `Chunk` / `SearchResult` 数据结构 + 多源去重排序聚合。按 `settings.rag_backend` 选后端：

- **`fake`（默认）**：内存 `FakeRAGStore`，字符重叠计分，保证测试无需外部依赖
- **`pgvector`（生产真向量）**：`PgVectorProvider` + `EmbeddingService`（OpenAI embedding），PG 用 `<=>` 余弦距离近邻检索，SQLite 降级为字符匹配

其他 Provider：`OCRProvider`（图片文本提取，懒依赖 pytesseract+PIL）、`CodeIndexProvider`（Python AST 按函数/类粒度切片）、`extractors/`（PDF/DOCX/TXT 提取，所有重依赖惰性 import + 优雅降级）。

> 这些惰性依赖（pdfplumber / PyPDF2 / python-docx / pytesseract / Pillow）**不在任何 extra 里声明**，缺失时对应解析路径降级，不阻断启动。

## 技术栈

| 类别 | 技术 |
|---|---|
| Web 框架 | FastAPI ≥0.115 + Pydantic V2 |
| ASGI | uvicorn[standard] ≥0.32 |
| 编排（新栈） | 自研事件驱动协作环 + LangGraph ≥0.2 主图骨架 |
| LLM 接入 | langchain-openai ≥0.3（重试 / fallback 模型 / 流式 / 成本追踪） |
| RAG | 自研多 Provider 协调器；pgvector ≥0.3 真向量；可选 LlamaIndex + Chroma（`--extra rag`） |
| ORM | SQLAlchemy 2.0 async + Alembic；PG 用 asyncpg，开发用 aiosqlite |
| 可观测性 | Langfuse ≥2.0（生产）/ Console（开发）+ SessionStats |
| 评估 | ragas 0.4.3（faithfulness / answer_relevancy / context_precision / context_recall）+ 不同族 judge 校验 |
| 认证 | passlib + python-jose |
| 任务队列 | Celery + Redis（可选 `--extra worker`，当前为桩） |
| UI | Chainlit（可选 `--extra ui`，当前为桩）；Web 前端用 React |
| 前端 | React 18 + Vite 5 + TypeScript 5 + react-router |
| 包管理 | uv（Python ≥3.11） |

## 项目结构

```
app/                            # 事件驱动新栈（主体）
├── agents/                     # AgentBase + 5 Agent（tutor/critic/retriever/conductor/curator）
├── orchestration/
│   ├── collab_loop.py          # 单线程事件循环 + 优先级队列 + 回合屏障 + on_event 钩子
│   ├── graph.py                # LangGraph 主图骨架（ingest→route→collab_loop→wrap_up）
│   ├── assembly.py             # 端到端装配线（build_new_stack / run_new_agent_session）
│   ├── routers.py              # 主图条件边
│   └── orchestrator_rules.yaml # 规则 DSL（运行时配置）
├── harness/                    # 业务核心 + 契约
│   ├── enums.py                # 全部 StrEnum（EventType/EventSource/ActionKind/TeachingMode...）
│   ├── events.py / eventbus.py / workspace_state.py   # 事件契约 + 共享状态
│   ├── orchestrator.py         # 路由器（规则引擎 + 回合屏障，物理在 harness）
│   ├── teaching_policy.py      # 教学模式状态机
│   ├── mastery_graph.py / user_profile.py             # L3 画像记忆
│   └── observability.py        # Console / Fake / Langfuse 三实现
├── infrastructure/
│   ├── llm.py                  # LLMService（重试/fallback/流式/成本）+ FakeLLM
│   ├── rag/                    # coordinator + embedding + pgvector_provider + ocr + code_index + extractors
│   └── storage/                # event_store + mastery（aiosqlite + SQLAlchemy 双版）+ message/session/user/eval/knowledge store
├── eval/                       # 旁路评估子系统（component/system/collaboration/ab + judge + kernel）
├── specs/                      # 渐进式 Prompt 体系（_root + 5 Agent 双文件 + loader）
├── api/                        # auth/chat/chat_stream/chat_multi/eval/knowledge/sessions/profile + _persist + _sse_projection
├── models/                     # tables.py(8 张表) + schemas.py(Pydantic)
├── core/                       # config / database / feature_flags / prompts
└── ui/ · worker/               # Chainlit / Celery（均为可选桩）

app_old/                        # 📦 归档老栈（2026-06-02 迁移，flag 关闭时仍是 /chat 活路径）
├── agent/                      # 旧 LangGraph 栈：graph/routers/nodes(15)/multi_agent(7)/system_eval(5)/specs(34)
├── harness/                    # 旧分层 state(6) + state_manager/intent_router/error_handler/memory/guardrails/tool_registry
└── infrastructure/             # memory_store + external(ocr/redis/web_search) + extraction(file_extract)

web/                            # React 18 + Vite 前端（pages: Chat/Knowledge/Login/Profile）
alembic/versions/               # 3 个迁移：init → vector_chunks → ragas_context_recall
tests/                          # 572 收集 / 564 通过 / 8 deselected
docker-compose.yml              # pgvector/pgvector:pg16（PG 开发/生产用）
```

> 详见 [docs/app_old_migration_plan.md](docs/app_old_migration_plan.md)。新栈对老栈零依赖；必留在 `app/` 的旧依赖闭包仅 `llm.py` / `observability.py` / `rag.store` / `rag.coordinator` / `enums.py` 等少数共用文件。

## 快速开始

```bash
# 1. 安装依赖
uv sync

# 可选 extras（按需）
uv sync --extra rag      # LlamaIndex + Chroma 检索
uv sync --extra eval     # ragas 评估
uv sync --extra worker   # Celery 异步任务
uv sync --extra ui       # Chainlit 界面

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 填入真实 OPENAI_API_KEY（用第三方网关再填 OPENAI_BASE_URL / OPENAI_MODEL）
# 启用新栈（真实教学能力）：FEATURE_USE_NEW_AGENT_GRAPH=true

# 3. 数据库迁移（首次或拉新代码后）
uv run alembic upgrade head

# 4. 启动 PostgreSQL（可选；开发默认 sqlite 开箱即用，无需此步）
docker compose up -d
# 然后在 .env 中启用 PG 连接串：
# DATABASE_URL=postgresql+asyncpg://studyagent:studyagent@localhost:5432/studyagent
# 并设 rag_backend=pgvector 启用真向量检索

# 5. 启动服务（新栈需先把 .env 导出为环境变量，否则 flag 读不到、会回退老栈）
set -a && source .env && set +a
uv run uvicorn app.main:app --reload   # 默认 http://127.0.0.1:8000

# —— 前端（React，可选）——
cd web && npm install
npm run dev          # 开发：localhost:5173，proxy 转发 /api、/health 到后端 8000
# 后端不在 8000 时：VITE_API_TARGET=http://127.0.0.1:8001 npm run dev
npm run build        # 生产：产物落 web/dist，由 FastAPI 同源伺服（重启后端加载）
cd ..

# 6. 运行测试
uv run pytest tests/ -v                # 默认排除 integration（564 通过）
uv run pytest -m integration           # 集成测试，需 Docker PG + OpenAI key
```

## API 端点

所有端点挂在 `/api` 前缀下（`/health` 例外）。

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/auth/register` | 用户注册（用户名重复 → 409） |
| POST | `/api/auth/login` | 用户登录 ⚠️ 当前不校验密码，仅查用户名 |
| POST | `/api/chat` | 学习对话（按 flag 走新/老栈） |
| POST | `/api/chat/stream` | 流式对话（SSE，新栈逐事件投影 + final） |
| POST | `/api/chat/multi` | 多 Agent 对话（桩，未实现） |
| GET | `/api/eval/{session_id}` | 查询评估结果（读 EvalStore） |
| POST | `/api/eval/{session_id}/rerun` | 重跑评估（桩，返回全 0） |
| POST | `/api/knowledge` | 创建知识库 |
| GET | `/api/knowledge` | 列出知识库 |
| DELETE | `/api/knowledge/{id}` | 删除知识库（不存在 → 404） |
| GET | `/api/sessions` | 列出会话（按 user_id，含 title，updated_at 倒序） |
| GET | `/api/sessions/{id}` | 获取单个会话 |
| GET | `/api/sessions/{id}/messages` | 获取会话对话历史 |
| GET | `/api/profile/{user_id}` | 用户画像（会话数 + 平均掌握度 0-100 整数） |
| GET | `/health` | 健康检查 |

### 流式实现（新栈 SSE）

`/chat/stream` 新栈为真流式：协作环在 `asyncio.to_thread` 工作线程跑，`on_event` 回调经 `loop.call_soon_threadsafe` 跨线程投递到 `asyncio.Queue`，主协程逐事件经 `project_event`（15 个语义事件白名单）投影成 SSE 下发，工作线程结束后再发 `final` 事件（含落库后的 turn_count）。自开独立 DB session 贯穿整个流，避免 StreamingResponse 提前关 session。落库由共享的 `persist_turn`（会话 + 两条消息 + 可选图谱，单次原子 commit）完成。

## 数据模型与存储

`app/models/tables.py` 定义 8 张 SQLAlchemy 表：`users` / `sessions` / `messages` / `knowledge` / `evals`（含 ragas 四指标列）/ `mastery_nodes`（含 rationale）/ `mastery_edges` / `vector_chunks`（embedding 列 PG 用 `Vector(1536)`，sqlite 退化 JSON）。

存储层多数 Store 支持**双模式**——传入 `db` session 走 SQLAlchemy 生产模式，传 `None` 用内存 fallback，便于测试：

```python
# 生产模式：调用方负责 commit（约定 C3：save 不内部 commit）
store = SessionStore(db=session)
await store.save("sid", state, user_id=1, title="学习会话")
await session.commit()

# 测试模式：内存字典
store = SessionStore(db=None)
```

`SessionStore` 契约：`title` 首写生效（first-write-wins）；`save()` 不内部 commit；`list_by_user()` 统一返回 `{session_id, title, updated_at}`，按 updated_at 降序。

迁移链（`alembic/versions/`）：`d48d7137f57f`（初始 5 表）→ `20260622_vector_chunks`（向量表，PG 建 vector 扩展）→ `20260623_ragas_context_recall`（evals 加 context_recall 列）。

## 关键枚举

有限集合统一用 StrEnum（`app/harness/enums.py`）确保类型安全，节选：

- `EventType`（24 个）— UserMessage / TutorAsked / RetrievedEvidence / MasteryAssessed / ActionRequested / LoopExit / OrchestratorTick ...
- `EventSource`（7 个）— user / tutor / retriever / critic / curator / conductor / orchestrator
- `ActionKind`（14 个）— tutor_ask / tutor_explain / tutor_re_explain / regress_to_prereq / retriever_expand_query / conductor_decide / loop_exit ...
- `TeachingMode` — Socratic / Feynman / Analogy / Regress
- `MasteryLevel` — weak / partial / mastered
- `EvalMetric` — faithfulness / relevancy / context_precision / context_recall
- `GateStatus` — pass / supplement / reject
- `ErrorKind` / `RecoveryAction` / `MemoryScope` / `Intent` / `Stage` ...

## 测试

```
572 收集 / 564 通过 / 8 deselected（实测全绿）

tests/unit/harness/         事件系统、枚举、可观测性、画像图谱、教学策略、编排器
tests/unit/agents/          5 Agent 契约与行为 + AgentBase
tests/unit/orchestration/   协作环、主图、路由、装配线
tests/unit/specs/           SpecLoader 渐进式加载
tests/unit/infrastructure/  LLM、RAG、embedding、pgvector、事件存储、掌握度存储
tests/unit/api · core · models · storage/   API flag 分支、feature_flags、表、store
tests/unit/agent/           老栈（app_old）LangGraph 图执行、节点、SpecLoader
tests/eval/                 ComponentBench / SystemBench / CollaborationBench / ABController / Judge
tests/golden/               黄金集 + Cohen's κ 一致性
tests/api/                  实时流 SSE、persist_turn、profile、sse_projection
tests/integration/          pgvector 真检索、端到端场景、新旧栈对齐（默认 deselect）
```

> 集成测试用 `integration` marker 标记，默认不跑（`pyproject.toml` 里 `addopts = "-m 'not integration'"`），它们依赖真实 Docker PostgreSQL + OpenAI API key。手动跑：`uv run pytest -m integration`。

## 已知限制（诚实清单）

- `/api/chat/multi`、`/api/eval/{id}/rerun` 是桩，未实现真实逻辑。
- `/api/auth/login` 当前**不校验密码**，仅按用户名查找，属安全缺陷，勿用于真实部署。
- `ui/`（Chainlit）、`worker/`（Celery）为可选桩。
- 评估 benches 已实现但未接在线 API/CLI，仅测试驱动。
- 老栈默认启用且用 FakeLLM，真实教学需开 `FEATURE_USE_NEW_AGENT_GRAPH=true`。
