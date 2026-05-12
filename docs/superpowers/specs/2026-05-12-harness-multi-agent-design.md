# LearningAgent Harness Multi-Agent 项目设计方案

> **日期**：2026-05-12
> **基于**：`top-2026-05-12-harness-architecture-refactoring-design.md` 升级
> **分支**：`feature/harness`

---

## 1. 项目定位

LearningAgent 是一个面向学习场景的 Agent 系统，以费曼学习法为主线，核心流程：

1. **诊断**：识别用户已有认知水平
2. **讲解**：用更易理解的方式讲解知识点
3. **复述检测**：要求用户复述并评估理解程度
4. **追问**：针对错误点追问与补救
5. **评估总结**：输出掌握度评分与复习建议

系统不是单轮聊天助手，而是**可沉淀学习轨迹、具备检索能力、带安全边界的编排系统**。

架构核心是 **Harness 框架**——包裹在 Agent 业务逻辑之外的基础设施层，负责编排、上下文、约束与可观测。

---

## 2. 四层架构

```
┌─────────────────────────────────────────────────────────┐
│                  API Layer（入口层）                      │
│  FastAPI + Pydantic V2                                  │
│  职责：请求校验、认证、响应格式化                          │
│  约束：零编排逻辑，不构造状态、不调用 LLM、不做路由        │
├─────────────────────────────────────────────────────────┤
│          Orchestration Layer（编排层）                    │
│  LangGraph StateGraph + SubGraph                        │
│  职责：图定义、节点编排、流程控制、Multi-Agent 协作        │
│  约束：节点是薄壳，只读状态→委托 harness→写状态           │
├─────────────────────────────────────────────────────────┤
│            Harness Layer（框架层）                        │
│  自建：State / Router / Tool / Memory / Guard / Error    │
│  职责：状态管理、意图路由、工具注册、记忆管理、            │
│       安全边界、错误处理、可观测性                        │
│  约束：不依赖编排层，只被编排层调用                        │
├─────────────────────────────────────────────────────────┤
│        Infrastructure Layer（基础设施层）                 │
│  LlamaIndex(RAG) + SQLAlchemy(ORM) + langchain-openai   │
│  职责：LLM 调用、RAG 实现、存储引擎、外部服务集成         │
│  约束：不依赖 Harness 层，只被 Harness 层调用             │
└─────────────────────────────────────────────────────────┘
```

**依赖方向**：API → Orchestration → Harness → Infrastructure，**严格单向，禁止反向依赖**。

**验证方法**：每个模块的 import 只能指向本层或下层。如果 `harness/` 中的文件 import 了 `agent/`，就是违规。LlamaIndex 调用封装在 Infrastructure 层，Harness 不直接 import llama_index。

---

## 3. 目录结构

```
app/
├── main.py                          # FastAPI 应用入口
│
├── core/                            # 全局配置
│   ├── config.py                    # Settings（Pydantic BaseSettings）
│   ├── prompts.py                   # 所有 Prompt 模板
│   └── database.py                  # SQLAlchemy 引擎 + Session 工厂 + Base
│
├── models/                          # 数据模型
│   ├── schemas.py                   # API 请求/响应 Pydantic 模型
│   └── tables.py                    # SQLAlchemy ORM 表定义
│
├── api/                             # 入口层
│   ├── __init__.py
│   ├── auth.py                      # POST /auth/register, /auth/login
│   ├── chat.py                      # POST /chat
│   ├── chat_stream.py              # POST /chat/stream
│   ├── chat_multi.py               # POST /chat/multi
│   ├── eval.py                      # GET /eval/{id}, POST /eval/{id}/rerun
│   ├── knowledge.py                 # 知识库 CRUD
│   ├── profile.py                   # 学习档案
│   ├── sessions.py                  # 会话管理
│   └── errors.py                    # 统一错误响应格式
│
├── agent/                           # 编排层
│   ├── __init__.py
│   ├── graph.py                     # 主 LangGraph 图构建
│   ├── node_wrapper.py             # safe_node 装饰器
│   ├── routers.py                   # 图条件边路由函数
│   ├── nodes/                       # 节点实现（每个文件一个节点）
│   │   ├── __init__.py
│   │   ├── route_intent.py
│   │   ├── history_check.py
│   │   ├── knowledge_retrieval.py
│   │   ├── diagnose.py
│   │   ├── explain.py
│   │   ├── restate_check.py
│   │   ├── followup.py
│   │   ├── rag_first.py
│   │   ├── evidence_gate.py
│   │   ├── answer_policy.py
│   │   ├── evaluate.py
│   │   ├── summarize.py
│   │   ├── replan.py
│   │   └── recovery.py
│   ├── multi_agent/                 # Multi-Agent 协作（SubGraph 模式）
│   │   ├── __init__.py
│   │   ├── state.py                 # MultiAgentState（扩展 LearningState）
│   │   ├── orchestrator_graph.py    # 编排器 SubGraph
│   │   ├── teaching_graph.py        # 教学 Agent SubGraph
│   │   ├── eval_graph.py            # 评估 Agent SubGraph
│   │   ├── retrieval_graph.py       # 检索 Agent SubGraph
│   │   ├── multi_graph.py           # 顶层 Multi-Agent 图（组装 SubGraph）
│   │   └── routers.py               # Multi-Agent 路由函数
│   └── system_eval/                 # 系统评估
│       ├── __init__.py
│       ├── teaching_eval.py         # ragas 评估集成
│       ├── orchestrator_eval.py
│       ├── eval_store.py
│       └── eval_graph.py
│
├── harness/                         # 框架层
│   ├── __init__.py
│   ├── enums.py                     # 所有 StrEnum 定义
│   ├── state/                       # 分层状态模型
│   │   ├── __init__.py              # LearningState 组合定义
│   │   ├── routing.py
│   │   ├── teaching.py
│   │   ├── retrieval.py
│   │   ├── evaluation.py
│   │   ├── memory.py
│   │   └── meta.py
│   ├── state_manager.py             # 状态管理器
│   ├── intent_router.py             # 意图路由器
│   ├── tool_registry.py             # 工具注册与选择
│   ├── memory.py                    # 统一记忆层
│   ├── guardrails.py                # 安全边界
│   ├── error_handler.py             # 统一错误处理
│   └── observability.py             # 可观测性
│
├── infrastructure/                  # 基础设施层
│   ├── __init__.py
│   ├── llm.py                       # LLM 调用封装（langchain-openai）
│   ├── rag/                         # RAG 实现（LlamaIndex 底座）
│   │   ├── __init__.py
│   │   ├── coordinator.py           # RAG 协调器（组装 LlamaIndex 组件）
│   │   ├── store.py                 # LlamaIndex VectorStoreIndex 封装
│   │   ├── reranker.py              # LlamaIndex Reranker 封装
│   │   ├── embedding.py             # LlamaIndex Embedding 配置
│   │   └── strategies.py            # 检索策略（RRF 融合等）
│   ├── storage/                     # 存储引擎（SQLAlchemy ORM）
│   │   ├── __init__.py
│   │   ├── session_store.py         # 会话存储
│   │   ├── user_store.py            # 用户存储
│   │   ├── eval_store.py            # 评估存储
│   │   └── knowledge_store.py       # 知识库 CRUD
│   ├── external/                    # 外部服务集成
│   │   ├── __init__.py
│   │   ├── redis_pubsub.py
│   │   ├── web_search.py
│   │   └── ocr.py
│   └── extraction/                  # 文件提取
│       ├── __init__.py
│       └── file_extract.py
│
├── worker/                          # 异步任务
│   ├── __init__.py
│   ├── celery_app.py
│   └── tasks.py
│
├── ui/                              # 前端交互
│   ├── __init__.py
│   ├── chainlit_app.py              # Chainlit 对话界面
│   └── chainlit_backend.py
│
└── web/                             # Vue 3 + Vite 前端
    ├── package.json
    ├── vite.config.ts
    ├── tsconfig.json
    ├── index.html
    ├── src/
    │   ├── main.ts
    │   ├── App.vue
    │   ├── router.ts
    │   ├── api/
    │   │   ├── auth.ts
    │   │   ├── knowledge.ts
    │   │   ├── sessions.ts
    │   │   ├── profile.ts
    │   │   └── eval.ts
    │   ├── views/
    │   │   ├── LoginView.vue
    │   │   ├── KnowledgeView.vue
    │   │   ├── SessionsView.vue
    │   │   ├── ProfileView.vue
    │   │   └── EvalDashboardView.vue
    │   ├── components/
    │   │   ├── KnowledgeUpload.vue
    │   │   ├── EvalChart.vue
    │   │   └── SessionList.vue
    │   └── styles/
    │       └── main.css
    └── dist/

migrations/                          # Alembic 迁移脚本
├── env.py
├── versions/
│   └── 001_initial.py

tests/                               # 测试
├── conftest.py
├── unit/
│   ├── harness/
│   ├── infrastructure/
│   └── agent/
├── integration/
├── api/
└── scenarios/
```

---

## 4. 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| API | FastAPI + Uvicorn | 入口层 |
| 编排 | LangGraph + SubGraph | 状态图 + Multi-Agent |
| LLM | langchain-openai | 兼容 OpenAI 协议 |
| RAG | LlamaIndex | 向量检索 + reranker + embedding 底座 |
| 向量库 | Chroma(开发) / Qdrant(生产) | LlamaIndex 统一抽象 |
| ORM | SQLAlchemy 2.0 async | 持久化 + 迁移管理 |
| 迁移 | Alembic | schema 版本管理 |
| 数据库 | SQLite(开发) / PostgreSQL(生产) | 改连接串即切换 |
| 评估 | ragas | faithfulness/relevancy/context_precision |
| 可观测 | Langfuse | 追踪 + ragas 指标上报 |
| 异步 | Celery + Redis | 后台任务 |
| 前端-对话 | Chainlit | LangGraph 原生集成 |
| 前端-管理 | Vue 3 + Vite + Element Plus + vue-echarts | 中文生态好 |
| 包管理 | uv(后端) + npm(前端) | — |

---

## 5. 状态模型

### 5.1 设计原则

- **分层嵌套**：`state["routing"]["intent"]` 而非 `state["intent"]`
- **枚举约束**：所有有限集合用 `StrEnum`，编译期校验
- **子状态独立**：每个子状态一个文件，职责清晰
- **LangGraph 兼容**：保留 `total=False`，支持增量更新

### 5.2 枚举定义

文件：`app/harness/enums.py`

```python
from enum import StrEnum

class Stage(StrEnum):
    """节点执行阶段"""
    INIT = "init"
    ROUTING = "routing"
    RETRIEVING = "retrieving"
    DIAGNOSING = "diagnosing"
    EXPLAINING = "explaining"
    RESTATE_CHECK = "restate_check"
    FOLLOWUP = "followup"
    EVALUATING = "evaluating"
    SUMMARIZING = "summarizing"
    RECOVERING = "recovering"
    COMPLETE = "complete"

class Intent(StrEnum):
    """用户意图分类"""
    TEACH_LOOP = "teach_loop"
    QA_DIRECT = "qa_direct"
    REVIEW = "review"
    REPLAN = "replan"

class GateStatus(StrEnum):
    """证据守门状态"""
    PASS = "pass"
    SUPPLEMENT = "supplement"
    REJECT = "reject"

class MasteryLevel(StrEnum):
    """掌握度等级"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class ErrorKind(StrEnum):
    """错误分类"""
    RAG_TIMEOUT = "rag_timeout"
    RAG_NO_RESULT = "rag_no_result"
    LLM_ERROR = "llm_error"
    TOOL_ERROR = "tool_error"
    INPUT_INVALID = "input_invalid"
    FATAL = "fatal"

class RecoveryAction(StrEnum):
    """恢复策略"""
    RETRY = "retry"
    FALLBACK_LLM = "fallback_llm"
    SKIP_RETRIEVAL = "skip_retrieval"
    ABORT = "abort"

class RetrievalMode(StrEnum):
    """检索模式"""
    FACT = "fact"
    FRESHNESS = "freshness"
    COMPARISON = "comparison"

class MemoryScope(StrEnum):
    """记忆作用域"""
    WORKING = "working"
    SESSION = "session"
    USER = "user"
    GLOBAL = "global"

class AgentRole(StrEnum):
    """Multi-Agent 角色标识"""
    TEACHING = "teaching"
    EVAL = "eval"
    RETRIEVAL = "retrieval"
    ORCHESTRATOR = "orchestrator"

class EvalMetric(StrEnum):
    """ragas 评估指标"""
    FAITHFULNESS = "faithfulness"
    RELEVANCY = "relevancy"
    CONTEXT_PRECISION = "context_precision"
    CONTEXT_RECALL = "context_recall"
```

### 5.3 分层子状态

#### RoutingState

文件：`app/harness/state/routing.py`

```python
from typing import TypedDict

class RoutingState(TypedDict, total=False):
    intent: str
    intent_confidence: float
    intent_source: str                   # "rule" | "llm" | "fallback"
    tool_route: dict
    retrieval_strategy: dict
    retrieval_mode: str
```

#### TeachingState

文件：`app/harness/state/teaching.py`

```python
from typing import TypedDict, List

class TeachingState(TypedDict, total=False):
    diagnosis: str
    explanation: str
    restatement_eval: str
    followup_question: str
    summary: str
    reply: str
    explain_loop_count: int             # 最大 3，防止无限循环
    user_choice: str                    # "review" | "continue"
    waiting_for_choice: bool
```

#### RetrievalState

文件：`app/harness/state/retrieval.py`

```python
from typing import TypedDict, List

class RetrievalState(TypedDict, total=False):
    rag_context: str
    rag_citations: List[dict]
    rag_found: bool
    rag_confidence_level: str           # "high" | "medium" | "low"
    rag_avg_score: float
    rag_source_count: int               # 命中文档数
    rag_strategy: str                   # 实际使用的检索策略名
    gate_status: str                    # GateStatus 枚举值
    gate_coverage_score: float
    gate_missing_keywords: List[str]
```

#### EvalState

文件：`app/harness/state/evaluation.py`

```python
from typing import TypedDict, List

class EvalState(TypedDict, total=False):
    mastery_score: int                  # 0-100
    mastery_level: str                  # MasteryLevel 枚举值
    mastery_rationale: str
    error_labels: List[str]
    answer_template_id: str
    boundary_notice: str
    ragas_faithfulness: float           # ragas faithfulness 分数
    ragas_relevancy: float              # ragas relevancy 分数
    ragas_context_precision: float      # ragas context_precision 分数
```

#### MemoryState

文件：`app/harness/state/memory.py`

```python
from typing import TypedDict, List, Optional

class MemoryState(TypedDict, total=False):
    topic: Optional[str]
    topic_confidence: float
    topic_changed: bool
    topic_reason: str
    topic_context: str
    topic_segments: List[dict]
    comparison_mode: bool
    history: List[str]
    has_history: bool
    history_summary: str
    history_mastery: str
```

#### MetaState

文件：`app/harness/state/meta.py`

```python
from typing import TypedDict, List, Optional

class MetaState(TypedDict, total=False):
    session_id: str
    user_id: Optional[int]
    stage: str                          # Stage 枚举值
    stream_output: bool
    branch_trace: List[dict]
    next_stage: str
    current_plan: dict
    current_step_index: int
    need_replan: bool
    replan_reason: str
    error_kind: str                     # ErrorKind 枚举值
    error_detail: str
    recovery_action: str                # RecoveryAction 枚举值
    fallback_used: bool
    retry_trace: List[dict]
```

### 5.4 顶层组合

文件：`app/harness/state/__init__.py`

```python
from typing import TypedDict
from .routing import RoutingState
from .teaching import TeachingState
from .retrieval import RetrievalState
from .evaluation import EvalState
from .memory import MemoryState
from .meta import MetaState

class LearningState(TypedDict, total=False):
    """学习 Agent 总状态 — 所有图节点共享"""
    user_input: str

    routing: RoutingState
    teaching: TeachingState
    retrieval: RetrievalState
    evaluation: EvalState
    memory: MemoryState
    meta: MetaState
```

### 5.5 Multi-Agent 状态扩展

文件：`app/agent/multi_agent/state.py`

```python
from typing import TypedDict, List
from app.harness.state.routing import RoutingState
from app.harness.state.teaching import TeachingState
from app.harness.state.retrieval import RetrievalState
from app.harness.state.evaluation import EvalState
from app.harness.state.memory import MemoryState
from app.harness.state.meta import MetaState

class MultiAgentState(TypedDict, total=False):
    """Multi-Agent 协作状态 — 扩展 LearningState"""
    user_input: str
    routing: RoutingState
    teaching: TeachingState
    retrieval: RetrievalState
    evaluation: EvalState
    memory: MemoryState
    meta: MetaState

    # Multi-Agent 专有字段
    active_agent: str                   # AgentRole 枚举值
    agent_messages: List[dict]          # Agent 间传递的消息列表
    agent_trace: List[dict]             # Agent 调用链追踪
    handoff_reason: str                 # Agent 切换原因
```

### 5.6 状态访问规范

| 谁读 | 谁写 | 示例 |
|------|------|------|
| 图路由函数 | IntentRouter | `state["routing"]["intent"]` |
| teach 分支节点 | diagnose, explain 等 | `state["teaching"]["diagnosis"]` |
| 检索节点 | knowledge_retrieval, evidence_gate | `state["retrieval"]["rag_found"]` |
| evaluate 节点 | evaluate | `state["evaluation"]["mastery_score"]` |
| history_check | MemoryManager | `state["memory"]["has_history"]` |
| 所有节点 | StateManager | `state["meta"]["stage"]` |
| ErrorHandler | ErrorHandler | `state["meta"]["error_kind"]` |
| retrieval SubGraph | LlamaIndex coordinator | `state["retrieval"]["rag_strategy"]` |
| eval SubGraph | ragas 评估器 | `state["evaluation"]["ragas_faithfulness"]` |
| orchestrator SubGraph | Multi-Agent 路由 | `state["active_agent"]` |

---

## 6. Harness 核心组件

### 6.1 IntentRouter — 意图路由器

文件：`app/harness/intent_router.py`

**职责**：根据用户输入判断意图（teach_loop / qa_direct / review / replan）

**路由策略**：规则优先 + LLM 兜底

```
用户输入
    │
    ├─ 规则匹配（确定性、低延迟）→ 置信度 ≥ 0.9 → 直接采用
    │
    ├─ LLM 语义路由（处理边界情况）→ 置信度 ≥ 0.7 → 采用
    │
    └─ 兜底：默认 teach_loop + 标记 intent_source="fallback"
```

**接口**：

```python
class IntentRouter:
    def route(self, user_input: str, topic: str | None,
              history: list[str]) -> RoutingState:
        """返回路由决策结果，写入 state["routing"]"""
```

**规则路由关键词映射**：

| 意图 | 触发关键词 | 置信度 |
|------|-----------|--------|
| `QA_DIRECT` | "评估", "理解程度", "是什么", "怎么用" | 0.95 |
| `REVIEW` | "复习", "回顾", "再看看" | 0.95 |
| `REPLAN` | "换个", "重新", "换方向" | 0.90 |
| `TEACH_LOOP` | 默认 | 0.50 |

审计字段：`intent_source` 记录 "rule" | "llm" | "fallback"。

### 6.2 StateManager — 状态管理器

文件：`app/harness/state_manager.py`

```python
class StateManager:
    def transition(self, state: LearningState, updates: dict) -> LearningState:
        """应用状态更新。自动检测 stage 变化并记录到 branch_trace。"""

    def snapshot(self, state: LearningState) -> str:
        """创建快照，返回快照 ID。用于中断恢复。"""

    def restore(self, snapshot_id: str) -> LearningState:
        """从快照恢复状态。"""
```

**更新规则**：
- `updates` 中的 key 为子状态名（"routing", "teaching" 等），值合并写入对应子状态
- 顶层 key（如 "user_input"）直接写入
- `meta.stage` 变化时自动追加 `branch_trace` 条目

### 6.3 ToolRegistry — 工具注册与选择

文件：`app/harness/tool_registry.py`

```python
@dataclass
class ToolSchema:
    name: str
    description: str
    parameters: dict
    returns: dict
    timeout: float = 30.0
    risky: bool = False

@dataclass
class ToolResult:
    success: bool
    output: any
    error: str | None = None
    metadata: dict | None = None

class ToolRegistry:
    def register(self, schema: ToolSchema, executor: Callable): ...
    def select(self, user_input: str, state: LearningState) -> list[str]: ...
    def execute(self, tool_name: str, params: dict) -> ToolResult: ...
```

**初始工具映射**：

| 工具名 | 底层实现 | 意图映射 |
|--------|---------|---------|
| `search_local_textbook` | LlamaIndex VectorStoreIndex（scope="global"） | teach_loop, qa_direct |
| `search_personal_memory` | LlamaIndex VectorStoreIndex（scope="personal"） | teach_loop, qa_direct, review |
| `search_web` | `infrastructure/external/web_search.py` | qa_direct |

### 6.4 MemoryManager — 统一记忆层

文件：`app/harness/memory.py`

```python
@dataclass
class MemoryItem:
    content: str
    source: str
    scope: MemoryScope
    score: float = 0.0
    metadata: dict | None = None

class MemoryManager:
    def recall(self, query: str, user_id: int | None,
               scopes: list[MemoryScope]) -> list[MemoryItem]:
        """按作用域检索记忆，返回按 score 降序排列"""

    def memorize(self, content: str, scope: MemoryScope,
                 user_id: int | None = None, metadata: dict | None = None) -> str:
        """存储记忆，返回记忆 ID"""
```

**作用域与底层映射**：

| MemoryScope | 底层实现 | user_id 要求 |
|-------------|---------|-------------|
| `GLOBAL` | `infrastructure/rag/store.py` → LlamaIndex VectorStoreIndex（scope="global"） | 不需要 |
| `USER` | `infrastructure/rag/store.py` → LlamaIndex VectorStoreIndex（scope="personal"） | **强制** |
| `SESSION` | `infrastructure/storage/session_store.py` → SQLAlchemy 查询 | 不需要 |
| `WORKING` | 当前请求内存 | 不需要 |

### 6.5 Guardrails — 安全边界

文件：`app/harness/guardrails.py`

```python
@dataclass
class GuardResult:
    passed: bool
    reason: str | None = None
    corrected: str | None = None

class Guardrails:
    def check_input(self, user_input: str) -> GuardResult:
        """输入守门：长度上限 10000、注入检测、偏题检测"""

    def check_tool_result(self, tool_name: str, result: ToolResult) -> GuardResult:
        """工具结果守门：空结果语义、参数合法性"""

    def check_output(self, reply: str, citations: list[dict]) -> GuardResult:
        """输出守门：无引用时添加不确定性声明"""
```

### 6.6 ErrorHandler — 统一错误处理

文件：`app/harness/error_handler.py`

```python
class ErrorHandler:
    def handle(self, error: Exception, state: LearningState) -> dict:
        """分类错误，返回状态更新指令（写入 state["meta"]）"""
```

**分类与策略映射**：

| ErrorKind | 判断依据 | RecoveryAction |
|-----------|---------|----------------|
| `RAG_TIMEOUT` | "timeout" in error msg | RETRY（1 次重试） |
| `RAG_NO_RESULT` | "no result" / "empty" | FALLBACK_LLM |
| `LLM_ERROR` | "rate" / "429" | SKIP_RETRIEVAL |
| `TOOL_ERROR` | 工具执行异常 | FALLBACK_LLM |
| `INPUT_INVALID` | Guardrails 拦截 | ABORT |
| `FATAL` | 其他 | ABORT |

### 6.7 Observability — 可观测性

文件：`app/harness/observability.py`

```python
class Observability:
    def trace(self, session_id: str, node: str, event: str,
              data: dict | None = None): ...

    def metric(self, name: str, value: float, tags: dict | None = None): ...

    def log(self, level: str, event: str, context: dict | None = None): ...
```

底层集成：委托 Langfuse（当 `LANGFUSE_ENABLED=true`），否则输出到标准日志。ragas 评估结果通过 `metric()` 上报，tag 标记指标类型。

### 6.8 组件依赖关系

```
IntentRouter ──→ 读 user_input, history
                    │
                    ▼
StateManager ──→ 读写 LearningState
    │               │
    │               ▼
    │           ToolRegistry ──→ LlamaIndex / 外部服务
    │               │
    │               ▼
    │           MemoryManager ──→ LlamaIndex(GLOBAL/USER) / SQLAlchemy(SESSION)
    │               │
    ▼               ▼
ErrorHandler ←── Guardrails ──→ 安全检查
                    │
                    ▼
              Observability ──→ Langfuse + ragas 指标
```

---

## 7. 编排层 — LangGraph 图设计

### 7.1 设计原则

1. **节点是薄壳**：只做"读状态 → 委托 harness 组件 → 写子状态"
2. **路由由枚举驱动**：条件边只读枚举值，不有关键词匹配
3. **错误统一走 safe_node**：节点不自己 try/catch
4. **每个节点只写自己负责的子状态**
5. **SubGraph 即 Agent**：Multi-Agent 中每个 Agent 是一个 SubGraph

### 7.2 主图结构

```
                          ┌─────────┐
                          │  init   │
                          └────┬────┘
                               │
                               ▼
                        ┌────────────┐
                        │route_intent│ ← IntentRouter
                        └─────┬──────┘
                              │
           ┌──────────────────┼──────────────────┐
           │                  │                  │
           ▼                  ▼                  ▼
    ┌────────────┐     ┌────────────┐      ┌──────────┐
    │ teach_loop │     │ qa_direct  │      │  replan  │
    └─────┬──────┘     └─────┬──────┘      └────┬─────┘
          │                  │                  │
          ▼                  ▼                  │
   ┌─────────────┐   ┌────────────┐            │
   │history_check│   │ rag_first  │            │
   └──────┬──────┘   └──────┬─────┘            │
          │                  │                  │
          ▼                  ▼                  │
   ┌──────────────┐  ┌────────────┐            │
   │ knowledge_   │  │ evidence_  │            │
   │ retrieval    │  │ gate       │            │
   └──────┬───────┘  └──────┬─────┘            │
          │                  │                  │
          ▼                  ▼                  │
   ┌─────────────┐   ┌────────────┐            │
   │  diagnose   │   │ answer_    │            │
   └──────┬──────┘   │ policy     │            │
          │          └──────┬─────┘            │
          ▼                 │                  │
   ┌─────────────┐          │                  │
   │  explain    │          │                  │
   └──────┬──────┘          │                  │
          │                 │                  │
          ▼                 │                  │
   ┌─────────────┐          │                  │
   │ restate_    │          │                  │
   │ check       │          │                  │
   └──────┬──────┘          │                  │
          │                 │                  │
          ▼                 │                  │
   ┌─────────────┐          │                  │
   │  followup   │          │                  │
   └──────┬──────┘          │                  │
          │                 │                  │
          ▼                 ▼                  ▼
       ┌──────────────────────────────────────────┐
       │              evaluate                     │
       └──────────────────┬───────────────────────┘
                          │
                          ▼
                   ┌────────────┐
                   │ summarize  │
                   └──────┬─────┘
                          │
                          ▼
                       ┌─────┐
                       │ END │
                       └─────┘

         ┌────────────────────────────┐
         │ recovery（任何节点出错进入）│
         └─────────────┬──────────────┘
                       │
                       ▼
                ┌────────────┐
                │answer_policy│
                └────────────┘

   review 意图 → 直接到 summarize
   replan 意图 → 回到 route_intent（循环）
```

### 7.3 图构建

文件：`app/agent/graph.py`

```python
from langgraph.graph import END, StateGraph
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.harness.state import LearningState
from app.agent.node_wrapper import safe_node
from app.agent.nodes.route_intent import route_intent_node
from app.agent.nodes.diagnose import diagnose_node
# ... 其他节点导入
from app.agent.routers import (
    route_by_intent, route_after_history,
    route_after_restate, route_after_gate,
)

def build_learning_graph():
    graph = StateGraph(LearningState)

    graph.add_node("route_intent", safe_node(route_intent_node))
    graph.add_node("history_check", safe_node(history_check_node))
    graph.add_node("knowledge_retrieval", safe_node(knowledge_retrieval_node))
    graph.add_node("diagnose", safe_node(diagnose_node))
    graph.add_node("explain", safe_node(explain_node))
    graph.add_node("restate_check", safe_node(restate_check_node))
    graph.add_node("followup", safe_node(followup_node))
    graph.add_node("rag_first", safe_node(rag_first_node))
    graph.add_node("evidence_gate", safe_node(evidence_gate_node))
    graph.add_node("answer_policy", safe_node(answer_policy_node))
    graph.add_node("evaluate", safe_node(evaluate_node))
    graph.add_node("summarize", safe_node(summarize_node))
    graph.add_node("replan", safe_node(replan_node))
    graph.add_node("recovery", safe_node(recovery_node))

    graph.set_entry_point("route_intent")

    # 条件边
    graph.add_conditional_edges("route_intent", route_by_intent, {
        "history_check": "history_check",
        "rag_first": "rag_first",
        "replan": "replan",
        "summarize": "summarize",
    })

    # teach_loop 分支
    graph.add_conditional_edges("history_check", route_after_history, {
        "ask_choice": "ask_choice_node",
        "diagnose": "diagnose",
    })
    graph.add_edge("diagnose", "knowledge_retrieval")
    graph.add_edge("knowledge_retrieval", "explain")
    graph.add_edge("explain", "restate_check")
    graph.add_conditional_edges("restate_check", route_after_restate, {
        "followup": "followup",
        "explain": "explain",
        "summarize": "summarize",
    })
    graph.add_edge("followup", "evaluate")

    # qa_direct 分支
    graph.add_edge("rag_first", "evidence_gate")
    graph.add_conditional_edges("evidence_gate", route_after_gate, {
        "answer_policy": "answer_policy",
        "recovery": "recovery",
    })
    graph.add_edge("answer_policy", "evaluate")

    # 汇合
    graph.add_edge("evaluate", "summarize")
    graph.add_edge("summarize", END)
    graph.add_edge("replan", "route_intent")
    graph.add_edge("recovery", "answer_policy")

    # SQLAlchemy 兼容的 checkpointer
    checkpointer = AsyncSqliteSaver.from_conn_string("./checkpoints.db")
    return graph.compile(checkpointer=checkpointer)
```

### 7.4 safe_node 装饰器

文件：`app/agent/node_wrapper.py`

```python
from app.harness.error_handler import get_error_handler
from app.harness.observability import get_observability
from app.harness.state import LearningState

def safe_node(func):
    """节点安全包装器：统一错误处理 + 可观测性追踪"""
    def wrapper(state: LearningState) -> dict:
        obs = get_observability()
        handler = get_error_handler()
        session_id = state.get("meta", {}).get("session_id", "")
        try:
            obs.trace(session_id, func.__name__, "start")
            result = func(state)
            obs.trace(session_id, func.__name__, "end")
            return result
        except Exception as e:
            obs.trace(session_id, func.__name__, "error", {"error": str(e)})
            return handler.handle(e, state)
    wrapper.__name__ = func.__name__
    return wrapper
```

### 7.5 节点实现模式

每个节点遵循统一模式：

```python
# app/agent/nodes/<name>.py

from app.harness.state import LearningState

def <name>_node(state: LearningState) -> dict:
    """节点职责的一句话说明"""

    # 1. 读取所需子状态
    xxx = state.get("<sub_state>", {}).get("<field>", <default>)

    # 2. 委托 harness 组件或 infrastructure
    result = <component>.<method>(...)

    # 3. 返回子状态更新（只写自己负责的子状态）
    return {"<sub_state>": {<field>: result}}
```

### 7.6 路由函数

文件：`app/agent/routers.py`

```python
from app.harness.enums import Intent, GateStatus
from app.harness.state import LearningState

def route_by_intent(state: LearningState) -> str:
    intent = state.get("routing", {}).get("intent", Intent.TEACH_LOOP)
    return {
        Intent.TEACH_LOOP: "history_check",
        Intent.QA_DIRECT: "rag_first",
        Intent.REPLAN: "replan",
        Intent.REVIEW: "summarize",
    }[intent]

def route_after_history(state: LearningState) -> str:
    if state.get("memory", {}).get("has_history", False):
        return "ask_choice"
    return "diagnose"

def route_after_restate(state: LearningState) -> str:
    loops = state.get("teaching", {}).get("explain_loop_count", 0)
    eval_text = state.get("teaching", {}).get("restatement_eval", "")
    if any(k in eval_text for k in ("已理解", "准确", "完整")):
        return "summarize"
    if any(k in eval_text for k in ("错误", "混淆", "误解")) and loops < 3:
        return "explain"
    return "followup"

def route_after_gate(state: LearningState) -> str:
    if state.get("retrieval", {}).get("gate_status") == GateStatus.REJECT:
        return "recovery"
    return "answer_policy"
```

---

## 8. Multi-Agent SubGraph 设计

### 8.1 架构

```
                    ┌──────────────────────┐
                    │  orchestrator_graph  │
                    │  (编排器 SubGraph)    │
                    │                      │
                    │  route_to_agent ─────┼──→ teaching_graph
                    │       │              │      (教学 Agent)
                    │       │              │
                    │       ├──→ eval_graph│
                    │       │   (评估Agent) │
                    │       │              │
                    │       └──→ retrieval_graph
                    │           (检索Agent) │
                    └──────────────────────┘
```

### 8.2 teaching_graph

文件：`app/agent/multi_agent/teaching_graph.py`

```python
def build_teaching_agent():
    graph = StateGraph(MultiAgentState)

    graph.add_node("diagnose", safe_node(diagnose_node))
    graph.add_node("explain", safe_node(explain_node))
    graph.add_node("restate_check", safe_node(restate_check_node))
    graph.add_node("followup", safe_node(followup_node))

    graph.set_entry_point("diagnose")
    graph.add_edge("diagnose", "explain")
    graph.add_edge("explain", "restate_check")
    graph.add_conditional_edges("restate_check", route_after_restate, {
        "followup": "followup",
        "explain": "explain",
        "done": "__end__",
    })
    graph.add_edge("followup", "__end__")

    return graph.compile()
```

### 8.3 eval_graph

文件：`app/agent/multi_agent/eval_graph.py`

```python
def build_eval_agent():
    graph = StateGraph(MultiAgentState)

    graph.add_node("evaluate_mastery", safe_node(evaluate_mastery_node))
    graph.add_node("evaluate_ragas", safe_node(evaluate_ragas_node))

    graph.set_entry_point("evaluate_mastery")
    graph.add_edge("evaluate_mastery", "evaluate_ragas")
    graph.add_edge("evaluate_ragas", "__end__")

    return graph.compile()
```

**evaluate_ragas_node**：

```python
def evaluate_ragas_node(state: MultiAgentState) -> dict:
    from ragas import evaluate
    from ragas.metrics import faithfulness, relevancy, context_precision

    rag_context = state.get("retrieval", {}).get("rag_context", "")
    user_input = state["user_input"]

    if not rag_context:
        return {"evaluation": {
            "ragas_faithfulness": 0.0,
            "ragas_relevancy": 0.0,
            "ragas_context_precision": 0.0,
        }}

    result = evaluate(
        dataset={"question": [user_input], "contexts": [[rag_context]]},
        metrics=[faithfulness, relevancy, context_precision],
    )

    return {"evaluation": {
        "ragas_faithfulness": result["faithfulness"],
        "ragas_relevancy": result["relevancy"],
        "ragas_context_precision": result["context_precision"],
    }}
```

### 8.4 retrieval_graph

文件：`app/agent/multi_agent/retrieval_graph.py`

```python
def build_retrieval_agent():
    graph = StateGraph(MultiAgentState)

    graph.add_node("retrieve", safe_node(knowledge_retrieval_node))
    graph.add_node("evidence_gate", safe_node(evidence_gate_node))

    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "evidence_gate")
    graph.add_edge("evidence_gate", "__end__")

    return graph.compile()
```

### 8.5 orchestrator_graph

文件：`app/agent/multi_agent/orchestrator_graph.py`

```python
def build_orchestrator():
    graph = StateGraph(MultiAgentState)

    graph.add_node("route_agent", safe_node(route_agent_node))
    graph.add_node("teaching", build_teaching_agent())
    graph.add_node("eval", build_eval_agent())
    graph.add_node("retrieval", build_retrieval_agent())

    graph.set_entry_point("route_agent")
    graph.add_conditional_edges("route_agent", route_to_agent, {
        AgentRole.TEACHING: "teaching",
        AgentRole.EVAL: "eval",
        AgentRole.RETRIEVAL: "retrieval",
        "done": "__end__",
    })
    graph.add_edge("teaching", "route_agent")
    graph.add_edge("eval", "__end__")
    graph.add_edge("retrieval", "route_agent")

    return graph.compile()
```

### 8.6 Multi-Agent 路由

文件：`app/agent/multi_agent/routers.py`

```python
from app.harness.enums import Intent, AgentRole
from app.agent.multi_agent.state import MultiAgentState

def route_to_agent(state: MultiAgentState) -> str:
    intent = state.get("routing", {}).get("intent", Intent.TEACH_LOOP)
    active = state.get("active_agent")

    if active == AgentRole.TEACHING:
        eval_text = state.get("teaching", {}).get("restatement_eval", "")
        if not any(k in eval_text for k in ("已理解", "准确", "完整")):
            return AgentRole.TEACHING

    if intent == Intent.TEACH_LOOP:
        return AgentRole.RETRIEVAL
    elif intent == Intent.QA_DIRECT:
        return AgentRole.RETRIEVAL
    else:
        return "done"
```

### 8.7 顶层 Multi-Agent 图

文件：`app/agent/multi_agent/multi_graph.py`

```python
def build_multi_agent_graph():
    graph = StateGraph(MultiAgentState)
    graph.add_node("orchestrator", build_orchestrator())
    graph.add_node("summarize", safe_node(summarize_node))

    graph.set_entry_point("orchestrator")
    graph.add_edge("orchestrator", "summarize")
    graph.add_edge("summarize", END)

    checkpointer = AsyncSqliteSaver.from_conn_string("./checkpoints.db")
    return graph.compile(checkpointer=checkpointer)
```

---

## 9. Infrastructure 层

### 9.1 LLM 调用

文件：`app/infrastructure/llm.py`

```python
class LLMService:
    def invoke(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        """同步调用 LLM，返回文本"""

    def invoke_json(self, system_prompt: str, user_prompt: str, **kwargs) -> dict:
        """调用 LLM 并解析 JSON 响应"""
```

底层用 `langchain-openai` 的 `ChatOpenAI`。

### 9.2 RAG 实现（LlamaIndex 底座）

#### coordinator.py

文件：`app/infrastructure/rag/coordinator.py`

```python
class RAGCoordinator:
    def __init__(self, store: RAGStore, reranker: RerankerService,
                 embedding: EmbeddingService): ...

    def query(self, query: str, scope: str,
              user_id: int | None = None,
              strategy: str = "hybrid",
              top_k: int = 5) -> list[dict]:
        """
        完整检索流程：query → retrieve → rerank → 返回

        strategy: "hybrid" | "dense" | "bm25"
        """

    def index_documents(self, documents: list[str], scope: str,
                        user_id: int | None = None,
                        source: str = "") -> list[str]:
        """入库文档，返回条目 ID 列表"""
```

#### store.py

文件：`app/infrastructure/rag/store.py`

```python
from llama_index.core import VectorStoreIndex, StorageContext, Document
from llama_index.vector_stores.chroma import ChromaVectorStore

class RAGStore:
    def _get_or_create_index(self, scope: str, user_id: int | None = None) -> VectorStoreIndex: ...

    def vector_query(self, query: str, scope: str,
                     user_id: int | None = None, top_k: int = 10) -> list[dict]: ...

    def bm25_query(self, query: str, scope: str,
                   user_id: int | None = None, top_k: int = 10) -> list[dict]: ...

    def hybrid_query(self, query: str, scope: str,
                     user_id: int | None = None, top_k: int = 10) -> list[dict]:
        """Dense + BM25 → RRF 融合"""

    def index(self, documents: list[str], scope: str,
              user_id: int | None = None, source: str = "") -> list[str]: ...

    def _rrf_fuse(self, vector_results: list[dict],
                  bm25_results: list[dict], top_k: int = 5) -> list[dict]:
        """RRF (Reciprocal Rank Fusion) 融合"""

    @staticmethod
    def _format_results(response) -> list[dict]: ...
```

#### reranker.py

文件：`app/infrastructure/rag/reranker.py`

```python
from llama_index.core.postprocessor import SentenceTransformerRerank

class RerankerService:
    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-2-v2"): ...

    def rerank(self, query: str, results: list[dict], top_k: int = 5) -> list[dict]: ...
```

#### embedding.py

文件：`app/infrastructure/rag/embedding.py`

```python
from llama_index.embeddings.openai import OpenAIEmbedding

class EmbeddingService:
    def __init__(self, provider: str = "openai", model: str = "text-embedding-3-small"): ...

    @property
    def embed_model(self): ...
```

#### strategies.py

文件：`app/infrastructure/rag/strategies.py`

```python
class RetrievalStrategies:
    STRATEGY_MAP = {
        RetrievalMode.FACT: "hybrid",
        RetrievalMode.FRESHNESS: "dense",
        RetrievalMode.COMPARISON: "hybrid",
    }

    @classmethod
    def get_strategy(cls, mode: str) -> str: ...

    @classmethod
    def get_top_k(cls, mode: str) -> int: ...
```

### 9.3 存储引擎（SQLAlchemy ORM）

#### database.py

文件：`app/core/database.py`

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

engine = create_async_engine("sqlite+aiosqlite:///./learning_agent.db", echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db() -> AsyncSession:
    async with async_session() as session:
        yield session

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

#### tables.py

文件：`app/models/tables.py`

```python
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, JSON, ForeignKey
from sqlalchemy.sql import func
from app.core.database import Base

class UserTable(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(256), nullable=False)
    created_at = Column(DateTime, server_default=func.now())

class SessionTable(Base):
    __tablename__ = "sessions"
    id = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    state_json = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

class KnowledgeTable(Base):
    __tablename__ = "knowledge"
    id = Column(Integer, primary_key=True, autoincrement=True)
    scope = Column(String(16), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    content = Column(Text, nullable=False)
    source = Column(String(256), default="")
    doc_ids = Column(JSON, default=list)
    created_at = Column(DateTime, server_default=func.now())

class EvalTable(Base):
    __tablename__ = "evals"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), ForeignKey("sessions.id"), nullable=False)
    mastery_score = Column(Integer, default=0)
    mastery_level = Column(String(16), default="")
    ragas_faithfulness = Column(Float, nullable=True)
    ragas_relevancy = Column(Float, nullable=True)
    ragas_context_precision = Column(Float, nullable=True)
    eval_data = Column(JSON, default=dict)
    created_at = Column(DateTime, server_default=func.now())
```

#### session_store.py

文件：`app/infrastructure/storage/session_store.py`

```python
class SessionStore:
    async def get(self, session_id: str) -> dict | None: ...
    async def save(self, session_id: str, state: dict, user_id: int | None = None) -> None: ...
    async def delete(self, session_id: str) -> None: ...
    async def list_by_user(self, user_id: int) -> list[dict]: ...
```

底层用 SQLAlchemy `AsyncSession` 操作 `SessionTable`。

#### user_store.py / eval_store.py / knowledge_store.py

同样模式：SQLAlchemy AsyncSession + 对应 Table。

### 9.4 外部服务与文件提取

- `external/redis_pubsub.py` — Redis 发布订阅
- `external/web_search.py` — 网页搜索
- `external/ocr.py` — OCR 服务
- `extraction/file_extract.py` — 文件提取

### 9.5 Infrastructure 依赖图

```
LLMService (langchain-openai)
    │
RAGCoordinator
    ├── RAGStore (LlamaIndex + Chroma/Qdrant)
    ├── RerankerService (LlamaIndex SentenceTransformerRerank)
    ├── EmbeddingService (LlamaIndex Embedding)
    └── RetrievalStrategies
    │
SessionStore ──→ SQLAlchemy AsyncSession ──→ SQLite / PostgreSQL
UserStore ──────→ SQLAlchemy AsyncSession
EvalStore ──────→ SQLAlchemy AsyncSession
KnowledgeStore ─→ SQLAlchemy AsyncSession + RAGStore
```

---

## 10. API 层

### 10.1 三件事原则

每个 API 端点只做：
1. 参数校验（Pydantic model 验证）
2. 委托执行（调用图或 harness 组件）
3. 格式化响应（返回标准 response model）

### 10.2 FastAPI 应用入口

文件：`app/main.py`

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.core.database import init_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield

app = FastAPI(title="LearningAgent", version="0.1.0", lifespan=lifespan)

# API 路由
app.include_router(auth_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(chat_stream_router, prefix="/api")
app.include_router(chat_multi_router, prefix="/api")
app.include_router(eval_router, prefix="/api")
app.include_router(knowledge_router, prefix="/api")
app.include_router(sessions_router, prefix="/api")
app.include_router(profile_router, prefix="/api")

# Vue 静态文件（生产模式）
if os.path.exists("web/dist"):
    app.mount("/assets", StaticFiles(directory="web/dist/assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_vue(full_path: str):
        file_path = f"web/dist/{full_path}"
        if os.path.exists(file_path) and not full_path.startswith("api"):
            return FileResponse(file_path)
        return FileResponse("web/dist/index.html")
```

### 10.3 路由清单

| 端点 | 方法 | 委托目标 |
|------|------|---------|
| `/chat` | POST | `agent/graph.py` 主图 |
| `/chat/stream` | POST | `agent/graph.py` 主图 astream |
| `/chat/multi` | POST | `agent/multi_agent/multi_graph.py` |
| `/auth/register` | POST | `infrastructure/storage/user_store.py` |
| `/auth/login` | POST | `infrastructure/storage/user_store.py` |
| `/eval/{session_id}` | GET | `infrastructure/storage/eval_store.py` |
| `/eval/{session_id}/rerun` | POST | `agent/system_eval/eval_graph.py` |
| `/eval/stats/overview` | GET | `infrastructure/storage/eval_store.py` |
| `/knowledge/*` | CRUD | `infrastructure/storage/knowledge_store.py` |
| `/sessions/*` | CRUD | `infrastructure/storage/session_store.py` |
| `/profile/*` | GET | `infrastructure/storage/` + `harness/memory.py` |

### 10.4 端点示例 — chat

```python
@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, db: AsyncSession = Depends(get_db)):
    config = {"configurable": {"thread_id": req.session_id}}
    result = await graph.ainvoke(
        {"user_input": req.message, "meta": {"session_id": req.session_id, "user_id": req.user_id}},
        config=config,
    )
    return ChatResponse(
        reply=result.get("teaching", {}).get("reply", ""),
        session_id=req.session_id,
        mastery_score=result.get("evaluation", {}).get("mastery_score"),
    )
```

### 10.5 端点示例 — knowledge 上传

```python
@router.post("/knowledge/upload")
async def upload_knowledge(req: KnowledgeUploadRequest, db: AsyncSession = Depends(get_db)):
    store = KnowledgeStore(db)
    record = await store.create(scope=req.scope, user_id=req.user_id,
                                 content=req.content, source=req.source)
    rag_store = get_rag_store()
    doc_ids = rag_store.index([req.content], scope=req.scope,
                               user_id=req.user_id, source=req.source)
    await store.update_doc_ids(record.id, doc_ids)
    return {"id": record.id, "doc_ids": doc_ids}
```

### 10.6 统一错误响应

```python
ERROR_HTTP_MAP = {
    ErrorKind.INPUT_INVALID: 400,
    ErrorKind.RAG_TIMEOUT: 504,
    ErrorKind.RAG_NO_RESULT: 200,
    ErrorKind.LLM_ERROR: 503,
    ErrorKind.TOOL_ERROR: 500,
    ErrorKind.FATAL: 500,
}
```

---

## 11. 测试规范

### 11.1 conftest.py

```python
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.database import Base

@pytest.fixture
async def test_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()

@pytest.fixture
def blank_state() -> LearningState:
    return {
        "user_input": "",
        "routing": {},
        "teaching": {},
        "retrieval": {},
        "evaluation": {},
        "memory": {},
        "meta": {"session_id": "test", "stage": Stage.INIT, "branch_trace": []},
    }

@pytest.fixture
def teach_state(blank_state) -> LearningState:
    state = blank_state.copy()
    state.update({
        "user_input": "我想学二分查找",
        "routing": {"intent": Intent.TEACH_LOOP, "intent_confidence": 0.9, "intent_source": "rule"},
        "memory": {"topic": "二分查找", "history": []},
    })
    return state

class FakeLLM:
    RESPONSES = {
        "诊断": "用户对主题有基础了解，需要补充细节",
        "讲解": "知识点讲解内容...",
        "评估": '{"mastery_score": 65, "mastery_level": "medium"}',
        "意图": '{"intent": "teach_loop", "confidence": 0.9}',
    }

    def invoke(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        for keyword, response in self.RESPONSES.items():
            if keyword in user_prompt:
                return response
        return "默认测试回复"

    def invoke_json(self, system_prompt: str, user_prompt: str, **kwargs) -> dict:
        return json.loads(self.invoke(system_prompt, user_prompt))

class FakeRAGStore:
    DOCUMENTS = {
        "二分查找": [{"content": "二分查找是一种在有序数组中查找目标的算法...", "score": 0.92, "source": "算法导论"}],
        "排序": [{"content": "排序算法包括冒泡、插入、快排等...", "score": 0.88, "source": "数据结构教材"}],
    }

    def vector_query(self, query, scope, user_id=None, top_k=5):
        for keyword, docs in self.DOCUMENTS.items():
            if keyword in query:
                return docs[:top_k]
        return []

    def hybrid_query(self, query, scope, user_id=None, top_k=5):
        return self.vector_query(query, scope, user_id, top_k)

    def bm25_query(self, query, scope, user_id=None, top_k=5):
        return self.vector_query(query, scope, user_id, top_k)

    def index(self, documents, scope, user_id=None, source=""):
        return [f"fake_doc_{i}" for i in range(len(documents))]
```

### 11.2 测试分层

| 层 | 数量占比 | Mock 范围 | 运行频率 |
|----|---------|----------|---------|
| `unit/` | 70% | LLM、存储、RAG（FakeLLM + FakeRAGStore + test_db） | 每次提交 |
| `integration/` | 20% | 只 Mock LLM | PR 合并前 |
| `api/` | 10% | 只 Mock LLM | 发布前 |

### 11.3 新增测试文件

| 文件 | 说明 |
|------|------|
| `unit/infrastructure/test_rag_coordinator.py` | RAG 协调器单元测试 |
| `unit/infrastructure/test_reranker.py` | Reranker 单元测试 |
| `unit/agent/test_multi_agent_graph.py` | SubGraph 协作测试 |
| `integration/test_ragas_eval.py` | ragas 评估集成测试 |

---

## 12. 前端

### 12.1 双轨策略

| 系统 | 技术 | 职责 | 入口 |
|------|------|------|------|
| **Chainlit** | Python | 对话交互（流式输出、多轮会话） | `uv run chainlit run app/ui/chainlit_app.py --port 2554` |
| **Vue 3 + Vite** | TypeScript | 管理界面（知识库、会话、档案、评估大屏） | FastAPI StaticFiles 托管 web/dist/ |

### 12.2 Vue 页面规划

| 页面 | 路由 | 核心组件 | 数据来源 |
|------|------|---------|---------|
| 登录/注册 | `/login` | LoginForm | `/auth/*` |
| 知识库管理 | `/knowledge` | KnowledgeUpload, KnowledgeList | `/knowledge/*` |
| 会话列表 | `/sessions` | SessionList | `/sessions/*` |
| 学习档案 | `/profile` | ProfileCard, TopicTimeline | `/profile/*` |
| 评估大屏 | `/eval` | EvalChart, ScoreTrend, IntentAccuracy | `/eval/stats/overview` |

### 12.3 开发流程

```bash
# 终端 1：FastAPI 后端
PYTHONPATH=. uv run uvicorn app.main:app --port 1900

# 终端 2：Vite 开发服务器
cd web && npm run dev

# 终端 3：Chainlit 对话
uv run chainlit run app/ui/chainlit_app.py --port 2554
```

### 12.4 Vite 配置

```typescript
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 3000,
    proxy: {
      '/api': { target: 'http://127.0.0.1:1900', changeOrigin: true },
    },
  },
  build: { outDir: 'dist', emptyOutDir: true },
})
```

---

## 13. 构建顺序

### Step 1：项目骨架 + 状态模型 + 数据库

- `app/harness/enums.py`
- `app/harness/state/` 全部文件
- `app/harness/__init__.py`
- `app/core/config.py`
- `app/core/database.py`
- `app/models/tables.py`
- `app/main.py`

**门禁**：`python -c "from app.harness.state import LearningState"` 无报错 + SQLite 表自动创建

### Step 2：Harness 核心组件（最小版）

- `app/harness/state_manager.py`
- `app/harness/intent_router.py`（规则路由）
- `app/harness/error_handler.py`
- `app/harness/observability.py`（标准日志版）

**门禁**：`IntentRouter.route("我想学二分查找", None, [])` 返回 `intent="teach_loop"`

### Step 3：Infrastructure 最小集

- `app/infrastructure/llm.py`
- `app/infrastructure/rag/store.py`（LlamaIndex + Chroma 内存模式）
- `app/infrastructure/storage/session_store.py`（SQLAlchemy）
- `app/infrastructure/storage/user_store.py`

**门禁**：`LLMService.invoke("system", "hello")` 返回字符串 + SessionStore 可走通

### Step 4：最小图

- `app/agent/node_wrapper.py`
- `app/agent/routers.py`
- `app/agent/nodes/route_intent.py`
- `app/agent/nodes/diagnose.py`
- `app/agent/nodes/explain.py`
- `app/agent/graph.py`（最小图 + SQLAlchemy checkpointer）

**门禁**：`graph.ainvoke({"user_input": "我想学二分查找", ...})` 返回 `teaching.explanation`

### Step 5：完整 teach_loop 分支

- `app/agent/nodes/history_check.py`
- `app/agent/nodes/knowledge_retrieval.py`
- `app/agent/nodes/restate_check.py`
- `app/agent/nodes/followup.py`
- `app/agent/nodes/evaluate.py`
- `app/agent/nodes/summarize.py`
- 补全 teach_loop 所有边

**门禁**：teach_loop 全流程可走通

### Step 6：qa_direct + recovery 分支

- `app/agent/nodes/rag_first.py`
- `app/agent/nodes/evidence_gate.py`
- `app/agent/nodes/answer_policy.py`
- `app/agent/nodes/recovery.py`
- `app/harness/guardrails.py`

**门禁**：qa_direct 和 recovery 分支可走通

### Step 7：剩余 Harness 组件 + RAG 完整实现

- `app/harness/tool_registry.py`
- `app/harness/memory.py`
- `app/harness/intent_router.py`（补全 LLM 路由）
- `app/infrastructure/rag/coordinator.py`
- `app/infrastructure/rag/reranker.py`
- `app/infrastructure/rag/embedding.py`
- `app/infrastructure/rag/strategies.py`

**门禁**：`MemoryManager.recall("二分查找", None, [MemoryScope.GLOBAL])` 返回记忆 + RAG coordinator 可走通

### Step 8：完整 Infrastructure

- `app/infrastructure/storage/` 剩余文件
- `app/infrastructure/external/` 全部文件
- `app/infrastructure/extraction/`
- `migrations/` Alembic 初始化

**门禁**：知识库上传+检索可走通 + `alembic upgrade head` 无报错

### Step 9：API 层

- `app/api/` 全部文件
- `app/models/schemas.py`

**门禁**：`curl POST /chat` 返回 200

### Step 10：Multi-Agent + System Eval

- `app/agent/multi_agent/` 全部 SubGraph 文件
- `app/agent/system_eval/` 全部文件（含 ragas 集成）

**门禁**：`curl POST /chat/multi` 返回 200 + ragas 指标可采集

### Step 11：测试 + UI + 前端 + Worker

- `tests/` 全部文件
- `app/ui/` Chainlit
- `app/worker/`
- `web/` Vue 3 + Vite

**门禁**：全量测试 100% 通过 + Vue 页面可访问 + Chainlit 对话可用

### Step 12：清理 + 文档

- README.md, docs/, pyproject.toml
- 依赖方向验证脚本

**门禁**：门禁验收全部通过

### 构建依赖图

```
Step 1 (骨架+状态+数据库)
    │
    ▼
Step 2 (Harness 核心) ──→ Step 3 (Infrastructure)  [可并行]
    │                              │
    ▼                              ▼
Step 4 (最小图) ←──────────────────┘
    │
    ▼
Step 5 (teach_loop)
    │
    ▼
Step 6 (qa_direct + recovery)
    │
    ▼
Step 7 (剩余 Harness + RAG) ──→ Step 8 (完整 Infrastructure)  [可并行]
    │                                  │
    ▼                                  ▼
Step 9 (API) ←─────────────────────────┘
    │
    ▼
Step 10 (Multi-Agent + ragas)
    │
    ▼
Step 11 (测试+UI+Worker)
    │
    ▼
Step 12 (清理+文档)
```

---

## 14. 门禁验收标准

| 类别 | 指标 | 阈值 |
|------|------|------|
| 功能 | teach_loop 全流程 | 可走通 |
| 功能 | qa_direct 全流程 | 可走通 |
| 功能 | replan 分支 | 可走通 |
| 功能 | recovery 分支 | 可走通 |
| 功能 | Multi-Agent SubGraph 协作 | 可走通 |
| 功能 | ragas 评估指标采集 | faithfulness/relevancy 可输出 |
| 功能 | Chainlit 对话 | 流式输出正常 |
| 功能 | Vue 知识库管理 | 上传/列表/删除可用 |
| 功能 | Vue 评估大屏 | 图表渲染正常 |
| 质量 | 全量测试 | 100% 通过，0 skip |
| 质量 | route 命中率 | ≥ 90% |
| 质量 | silent failure | 0% |
| 质量 | personal 隔离违规 | 0 |
| 架构 | 依赖方向 | API → Agent → Harness → Infra，无反向 |
| 架构 | 上帝服务 | 不存在 |
| 架构 | 扁平状态 | 不存在 |
| 架构 | silent catch | 不存在 |
| 架构 | LlamaIndex 调用封装在 Infra 层 | Harness 不直接 import llama_index |
| 迁移 | Alembic 迁移 | `alembic upgrade head` 无报错 |
| 前端 | Vue 构建产物 | FastAPI StaticFiles 正常托管 |
| 前端 | 开发模式 | Vite proxy 到 FastAPI 正常 |
