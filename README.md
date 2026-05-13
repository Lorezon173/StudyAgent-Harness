# StudyAgent Harness

基于苏格拉底教学法的多 Agent 学习框架。通过诊断→讲解→复述→追问的交互循环，引导用户主动构建知识理解，而非被动接受信息。

## 架构概览

```
┌──────────────────────────────────────────────────────┐
│  API 层 (FastAPI)                                     │
│  认证 / 对话 / 流式 / 多Agent / 评估 / 知识库 / 会话  │
├──────────────────────────────────────────────────────┤
│  编排层 (LangGraph StateGraph)                        │
│  主图 14 节点 + 4 SubGraph + 系统评估图               │
│  意图路由 → 分支执行 → 状态汇聚                       │
├──────────────────────────────────────────────────────┤
│  Harness 层 (业务核心)                                │
│  枚举 / 状态模型 / 意图路由 / 错误处理 /              │
│  可观测性 / 记忆 / 工具注册 / 护栏 / 状态管理         │
├──────────────────────────────────────────────────────┤
│  基础设施层                                           │
│  LLM / RAG / 存储 / 文件提取 / OCR / 搜索 / Redis    │
└──────────────────────────────────────────────────────┘
         ↑ 严格单向依赖，严禁反向引用 ↑
```

## 核心流程

### 教学循环 (teach_loop)

```
用户输入 → 意图路由
  ↓
历史检查 → 诊断 → 知识检索 → 讲解 → 复述检查 ─┐
                                                ├→ 最多3轮
                              ┌─────────────────┘
                              ↓
                    评估(掌握度) → 总结
```

### 直答分支 (qa_direct)

```
用户提问 → RAG检索 → 证据门控 ─┬→ 回答策略 → 评估 → 总结
                                └→ 恢复 → 回答策略
```

### 重规划 / 复习

- **replan**：用户切换主题 → 重新路由
- **review**：直接生成学习总结

## 渐进式规范系统

Agent 的行为约束通过三层规范文件实现**按需加载**，而非一次性灌入全部上下文：

```
层级0 — 根规范 (始终加载, ~200 tokens)
  specs/_root.prompt.md         全局底线规则

层级1 — Agent 角色 (路由后加载, ~300 tokens)
  specs/agents/teaching.prompt.md   苏格拉底式教学原则
  specs/agents/eval.prompt.md       双重评估规则
  specs/agents/retrieval.prompt.md  知识检索与证据门控
  specs/agents/orchestrator.prompt.md 调度策略

层级2 — 节点指令 (执行时加载, ~200 tokens)
  specs/prompts/diagnose.prompt.md  只诊断不讲解
  specs/prompts/explain.prompt.md   针对性讲解
  ...共14个节点
```

**加载流程**：

```python
# SpecLoader 通过意图地图查询当前节点需要的资源
# 同一轮次内，层级0和层级1被缓存，只有层级2增量加载

SpecLoader.compose(intent="teach_loop", node="diagnose")
→ 组装: _root.prompt.md + teaching.prompt.md + diagnose.prompt.md
→ 用 XML 标签分隔: <root_rules> / <agent_role> / <node_instruction>
→ 注入 state["_system_prompt"]
```

**意图地图** (`intent_map.yaml`) 定义了每个意图下各节点需要的资源，一眼可览全局资源分配。

**双文件规范**：每个规范由 `.md`（开发者文档）+ `.prompt.md`（LLM 运行时 Prompt）组成，修改规范时必须同步修改对应 Prompt。

## 状态模型

采用分层 TypedDict，每个子状态对应一个命名空间：

```python
LearningState
  ├── user_input: str           # 用户原始输入
  ├── routing: RoutingState     # 意图、置信度、路由信息
  ├── teaching: TeachingState   # 诊断、讲解、复述、追问、总结
  ├── retrieval: RetrievalState # RAG上下文、门控状态、检索策略
  ├── evaluation: EvalState     # 掌握度、ragas指标
  ├── memory: MemoryState       # 历史、主题、记忆条目
  └── meta: MetaState           # 阶段、会话ID、错误信息
```

节点只写自己所属的命名空间，读取其他命名空间允许，跨命名空间写入被禁止。

## 多 Agent 架构

```
主图 (LearningGraph)
  14个节点 + 4条条件边

SubGraph
  ├── TeachingAgent    诊断→讲解→复述→追问
  ├── EvalAgent        掌握度评估 → RAG质量评估
  ├── RetrievalAgent   知识检索
  └── OrchestratorAgent 调度决策→总结

系统评估图
  教学评估 → 编排评估 → 结果存储
```

## 技术栈

| 类别 | 技术 |
|------|------|
| Web 框架 | FastAPI + Pydantic V2 |
| Agent 编排 | LangGraph StateGraph + MemorySaver |
| LLM 接入 | LangChain OpenAI + 重试/回退/流式/成本追踪 |
| RAG | LlamaIndex + Chroma(开发) / Qdrant(生产) |
| ORM | SQLAlchemy 2.0 async + Alembic |
| 可观测性 | Langfuse（生产）/ Console（开发）+ SessionStats 汇总 |
| 评估 | ragas (faithfulness/relevancy/context_precision) |
| 任务队列 | Celery + Redis (可选) |
| UI | Chainlit (可选) |
| 包管理 | uv |

## 项目结构

```
app/
├── agent/                      # 编排层
│   ├── graph.py                # 主图定义 (14节点)
│   ├── routers.py              # 条件边路由函数
│   ├── node_wrapper.py         # safe_node 装饰器
│   ├── spec_loader.py          # 渐进式规范加载引擎
│   ├── spec_decorator.py       # @with_spec 装饰器
│   ├── specs/                  # 规范仓库
│   │   ├── _root.md / .prompt.md
│   │   ├── intent_map.yaml
│   │   ├── agents/             # Agent 角色规范 (4个)
│   │   └── prompts/            # 节点指令规范 (14个)
│   ├── nodes/                  # 14个薄壳节点
│   ├── multi_agent/            # SubGraph 定义
│   └── system_eval/            # 系统评估图
├── harness/                    # 业务核心层
│   ├── enums.py                # 所有 StrEnum 定义
│   ├── state/                  # 分层状态模型 (7个文件)
│   ├── intent_router.py        # 规则优先 + LLM 兜底路由
│   ├── error_handler.py        # 错误分类与恢复策略
│   ├── observability.py        # Observability ABC + Langfuse/Console/Fake
│   ├── memory.py               # 短期(LRU+TTL) + 长期(SQLite) 双层记忆
│   ├── tool_registry.py        # 工具注册与执行
│   ├── guardrails.py           # 输入/工具/输出护栏
│   └── state_manager.py        # 状态转换/快照/恢复
├── infrastructure/             # 基础设施层
│   ├── llm.py                  # LLMService (重试/回退/流式) + LLMConfig + FakeLLM
│   ├── rag/                    # RAGCoordinator + FakeRAGStore
│   ├── storage/                # 会话/用户/评估/知识库/记忆存储
│   ├── extraction/             # 文件提取 (pdf/txt/md/csv)
│   └── external/               # OCR / Web搜索 / Redis
├── api/                        # API 层 (8个路由模块)
├── core/                       # 配置 / 数据库 / Prompt模板
├── models/                     # Pydantic Schema + ORM Table
├── ui/                         # Chainlit 前端 (存根)
└── worker/                     # Celery 任务 (存根)

tests/                          # 104个单元测试
```

## 快速开始

```bash
# 安装依赖
uv sync

# 安装可选依赖 (按需)
uv sync --extra rag      # RAG 检索
uv sync --extra eval     # ragas 评估
uv sync --extra worker   # Celery 异步任务
uv sync --extra ui       # Chainlit 界面

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入 OPENAI_API_KEY 等

# 启动服务
uv run uvicorn app.main:app --reload

# 运行测试
uv run pytest tests/ -v
```

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/register` | 用户注册 |
| POST | `/api/auth/login` | 用户登录 |
| POST | `/api/chat` | 学习对话 |
| POST | `/api/chat/stream` | 流式对话 |
| POST | `/api/chat/multi` | 多Agent对话 |
| POST | `/api/eval` | 运行评估 |
| GET | `/api/eval/{session_id}` | 查询评估结果 |
| POST | `/api/knowledge` | 创建知识库 |
| GET | `/api/knowledge` | 列出知识库 |
| GET | `/api/sessions` | 列出会话 |
| GET | `/api/profile/{user_id}` | 用户画像 |
| GET | `/health` | 健康检查 |

## 存储双模式

所有 Store 支持两种运行模式，无需真实数据库即可测试：

```python
# 生产模式: SQLAlchemy async
store = SessionStore(db=session)

# 测试模式: 内存 fallback
store = SessionStore(db=None)  # 自动使用内存字典
```

## 关键枚举

所有有限集合使用 StrEnum 定义，确保类型安全：

- `Stage` — 节点执行阶段 (init / routing / diagnosing / explaining / ...)
- `Intent` — 用户意图 (teach_loop / qa_direct / review / replan)
- `GateStatus` — 证据门控 (pass / supplement / reject)
- `MasteryLevel` — 掌握度 (weak / partial / mastered)
- `ErrorKind` — 错误分类 (rag_timeout / llm_error / fatal / ...)
- `RecoveryAction` — 恢复策略 (retry / fallback_llm / skip_retrieval / abort)
- `MemoryScope` — 记忆作用域 (working / episode / session / user / global)
- `AgentRole` — Agent 角色 (teaching / eval / retrieval / orchestrator)

## 测试

```
147 个测试覆盖全部模块

tests/unit/harness/         枚举、状态、路由、错误处理、护栏、记忆、可观测 (58个)
tests/unit/infrastructure/  LLM、RAG、存储、记忆存储 (23个)
tests/unit/agent/           图执行、节点、多Agent、系统评估、SpecLoader (48个)
tests/unit/api/             API 端点 (6个)
```
