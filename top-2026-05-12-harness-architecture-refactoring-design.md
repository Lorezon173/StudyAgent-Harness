# Agent Harness 框架设计与构建指南

> **用途**：从零构建 LearningAgent 项目的完整参考文档
> **日期**：2026-05-12
> **分支**：`feature/harness`（独立分支，不影响主线）

---

## 1. 项目定位

LearningAgent 是一个面向学习场景的 Agent 系统，以费曼学习法为主线，核心流程：

1. **诊断**：识别用户已有认知水平
2. **讲解**：用更易理解的方式讲解知识点
3. **复述检测**：要求用户复述并评估理解程度
4. **追问**：针对错误点追问与补救
5. **评估总结**：输出掌握度评分与复习建议

系统不是单轮聊天助手，而是**可沉淀学习轨迹、具备检索能力、带安全边界的编排系统**。

本项目的架构核心是 **Harness 框架**——包裹在 Agent 业务逻辑之外的基础设施层，负责编排、上下文、约束与可观测。

---

## 2. 四层架构

```
┌─────────────────────────────────────────────────────┐
│                  API Layer（入口层）                   │
│  职责：请求校验、认证、响应格式化                       │
│  目录：app/api/                                      │
│  约束：零编排逻辑，不构造状态、不调用 LLM、不做路由     │
├─────────────────────────────────────────────────────┤
│            Orchestration Layer（编排层）               │
│  职责：图定义、节点编排、流程控制                      │
│  目录：app/agent/                                    │
│  约束：节点是薄壳，只读状态→委托 harness→写状态        │
├─────────────────────────────────────────────────────┤
│              Harness Layer（框架层）                   │
│  职责：状态管理、意图路由、工具注册、记忆管理、         │
│       安全边界、错误处理、可观测性                     │
│  目录：app/harness/                                  │
│  约束：不依赖编排层，只被编排层调用                     │
├─────────────────────────────────────────────────────┤
│          Infrastructure Layer（基础设施层）            │
│  职责：LLM 调用、RAG 实现、存储引擎、外部服务集成      │
│  目录：app/infrastructure/                           │
│  约束：不依赖 Harness 层，只被 Harness 层调用          │
└─────────────────────────────────────────────────────┘
```

**依赖方向**：API → Orchestration → Harness → Infrastructure，**严格单向，禁止反向依赖**。

**如何验证依赖方向**：每个模块的 import 只能指向本层或下层。如果 `harness/` 中的文件 import 了 `agent/`，就是违规。

---

## 3. 完整目录结构

```
app/
├── main.py                       # FastAPI 应用入口
│
├── core/                         # 全局配置
│   ├── config.py                 # Settings（Pydantic BaseSettings）
│   └── prompts.py                # 所有 Prompt 模板
│
├── models/                       # 数据模型
│   └── schemas.py                # API 请求/响应 Pydantic 模型
│
├── api/                          # 入口层
│   ├── __init__.py
│   ├── auth.py                   # POST /auth/register, /auth/login
│   ├── chat.py                   # POST /chat
│   ├── chat_stream.py            # POST /chat/stream
│   ├── chat_multi.py             # POST /chat/multi
│   ├── eval.py                   # GET /eval/{id}, POST /eval/{id}/rerun
│   ├── knowledge.py              # 知识库 CRUD
│   ├── profile.py                # 学习档案
│   ├── sessions.py               # 会话管理
│   └── errors.py                 # 统一错误响应格式
│
├── agent/                        # 编排层
│   ├── __init__.py
│   ├── graph.py                  # 主 LangGraph 图构建
│   ├── node_wrapper.py           # safe_node 装饰器
│   ├── routers.py                # 图条件边路由函数
│   ├── nodes/                    # 节点实现（每个文件一个节点）
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
│   ├── multi_agent/              # Multi-Agent 协作
│   │   ├── __init__.py
│   │   ├── state.py              # MultiAgentState
│   │   ├── orchestrator.py
│   │   ├── teaching_agent.py
│   │   ├── eval_agent.py
│   │   ├── retrieval_agent.py
│   │   ├── graph.py              # Multi-Agent 图
│   │   └── routers.py
│   └── system_eval/              # 系统评估
│       ├── __init__.py
│       ├── teaching_eval.py
│       ├── orchestrator_eval.py
│       ├── eval_store.py
│       └── eval_graph.py
│
├── harness/                      # 框架层
│   ├── __init__.py
│   ├── enums.py                  # 所有 StrEnum 定义
│   ├── state/                    # 分层状态模型
│   │   ├── __init__.py           # LearningState 组合定义
│   │   ├── routing.py
│   │   ├── teaching.py
│   │   ├── retrieval.py
│   │   ├── evaluation.py
│   │   ├── memory.py
│   │   └── meta.py
│   ├── state_manager.py          # 状态管理器
│   ├── intent_router.py          # 意图路由器
│   ├── tool_registry.py          # 工具注册与选择
│   ├── memory.py                 # 统一记忆层
│   ├── guardrails.py             # 安全边界
│   ├── error_handler.py          # 统一错误处理
│   └── observability.py          # 可观测性
│
├── infrastructure/               # 基础设施层
│   ├── __init__.py
│   ├── llm.py                    # LLM 调用封装
│   ├── rag/                      # RAG 实现
│   │   ├── __init__.py
│   │   ├── coordinator.py        # RAG 协调器
│   │   ├── store.py              # 知识库存储（global + personal，scope 参数区分）
│   │   ├── reranker.py           # 重排器
│   │   ├── embedding.py          # 向量嵌入
│   │   └── strategies.py         # 检索策略
│   ├── storage/                  # 存储引擎
│   │   ├── __init__.py
│   │   ├── session_store.py      # 会话存储
│   │   ├── user_store.py         # 用户存储
│   │   ├── eval_store.py         # 评估存储
│   │   └── knowledge_store.py    # 知识库 CRUD
│   ├── external/                 # 外部服务集成
│   │   ├── __init__.py
│   │   ├── redis_pubsub.py
│   │   ├── web_search.py
│   │   └── ocr.py
│   └── extraction/               # 文件提取
│       ├── __init__.py
│       └── file_extract.py
│
├── worker/                       # 异步任务
│   ├── __init__.py
│   ├── celery_app.py
│   └── tasks.py
│
├── ui/                           # 前端交互
│   ├── __init__.py
│   ├── chainlit_app.py           # Chainlit 对话界面（对话专用）
│   └── chainlit_backend.py
│
└── web/                          # Vue 3 + Vite 前端（管理界面）
    ├── package.json
    ├── vite.config.ts
    ├── tsconfig.json
    ├── index.html
    ├── src/
    │   ├── main.ts               # 入口
    │   ├── App.vue               # 根组件
    │   ├── router.ts             # Vue Router
    │   ├── api/                  # API 调用封装
    │   │   ├── auth.ts
    │   │   ├── knowledge.ts
    │   │   ├── sessions.ts
    │   │   ├── profile.ts
    │   │   └── eval.ts
    │   ├── views/                # 页面组件
    │   │   ├── LoginView.vue
    │   │   ├── KnowledgeView.vue
    │   │   ├── SessionsView.vue
    │   │   ├── ProfileView.vue
    │   │   └── EvalDashboardView.vue
    │   ├── components/           # 通用组件
    │   │   ├── KnowledgeUpload.vue
    │   │   ├── EvalChart.vue
    │   │   └── SessionList.vue
    │   └── styles/
    │       └── main.css
    └── dist/                     # 构建产物，由 FastAPI StaticFiles 托管
```

---

## 4. 状态模型

### 4.1 设计原则

- **分层嵌套**：`state["routing"]["intent"]` 而非 `state["intent"]`
- **枚举约束**：所有有限集合用 `StrEnum`，编译期校验
- **子状态独立**：每个子状态一个文件，职责清晰
- **LangGraph 兼容**：保留 `total=False`，支持增量更新

### 4.2 枚举定义

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
    TEACH_LOOP = "teach_loop"       # 学习新知识
    QA_DIRECT = "qa_direct"         # 直接问答
    REVIEW = "review"               # 复习已学内容
    REPLAN = "replan"               # 换方向/重规划

class GateStatus(StrEnum):
    """证据守门状态"""
    PASS = "pass"                   # 证据充分
    SUPPLEMENT = "supplement"       # 证据需补充
    REJECT = "reject"               # 证据不足

class MasteryLevel(StrEnum):
    """掌握度等级"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class ErrorKind(StrEnum):
    """错误分类"""
    RAG_TIMEOUT = "rag_timeout"     # RAG 超时
    RAG_NO_RESULT = "rag_no_result" # RAG 无结果
    LLM_ERROR = "llm_error"         # LLM 调用失败
    TOOL_ERROR = "tool_error"       # 工具执行失败
    INPUT_INVALID = "input_invalid" # 输入不合法
    FATAL = "fatal"                 # 致命错误

class RecoveryAction(StrEnum):
    """恢复策略"""
    RETRY = "retry"                         # 重试
    FALLBACK_LLM = "fallback_llm"           # 降级到纯 LLM
    SKIP_RETRIEVAL = "skip_retrieval"       # 跳过检索
    ABORT = "abort"                         # 终止

class RetrievalMode(StrEnum):
    """检索模式"""
    FACT = "fact"                   # 事实查询
    FRESHNESS = "freshness"         # 时效性查询
    COMPARISON = "comparison"       # 对比查询

class MemoryScope(StrEnum):
    """记忆作用域"""
    WORKING = "working"             # 当前请求
    SESSION = "session"             # 当前会话
    USER = "user"                   # 用户级别
    GLOBAL = "global"               # 全局知识库
```

### 4.3 分层子状态

文件：`app/harness/state/routing.py`

```python
from typing import TypedDict

class RoutingState(TypedDict, total=False):
    """路由决策状态 — 由 IntentRouter 写入"""
    intent: str                          # Intent 枚举值
    intent_confidence: float             # 0.0 - 1.0
    intent_source: str                   # "rule" | "llm" | "fallback"
    tool_route: dict                     # 工具路由结果
    retrieval_strategy: dict             # 检索策略配置
    retrieval_mode: str                  # RetrievalMode 枚举值
```

文件：`app/harness/state/teaching.py`

```python
from typing import TypedDict, List

class TeachingState(TypedDict, total=False):
    """教学业务数据 — 由 teach 分支节点写入"""
    diagnosis: str
    explanation: str
    restatement_eval: str
    followup_question: str
    summary: str
    reply: str
    explain_loop_count: int              # 最大 3，防止无限循环
    user_choice: str                     # "review" | "continue"
    waiting_for_choice: bool
```

文件：`app/harness/state/retrieval.py`

```python
from typing import TypedDict, List

class RetrievalState(TypedDict, total=False):
    """检索中间结果 — 由检索节点和 evidence_gate 写入"""
    rag_context: str
    rag_citations: List[dict]
    rag_found: bool
    rag_confidence_level: str            # "high" | "medium" | "low"
    rag_avg_score: float
    gate_status: str                     # GateStatus 枚举值
    gate_coverage_score: float
    gate_missing_keywords: List[str]
```

文件：`app/harness/state/evaluation.py`

```python
from typing import TypedDict, List

class EvalState(TypedDict, total=False):
    """评估结果 — 由 evaluate 节点写入"""
    mastery_score: int                   # 0-100
    mastery_level: str                   # MasteryLevel 枚举值
    mastery_rationale: str
    error_labels: List[str]
    answer_template_id: str
    boundary_notice: str
```

文件：`app/harness/state/memory.py`

```python
from typing import TypedDict, List, Optional

class MemoryState(TypedDict, total=False):
    """记忆与上下文 — 由 history_check、MemoryManager 写入"""
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

文件：`app/harness/state/meta.py`

```python
from typing import TypedDict, List, Optional

class MetaState(TypedDict, total=False):
    """元信息与追踪 — 由 StateManager、ErrorHandler 写入"""
    session_id: str
    user_id: Optional[int]
    stage: str                           # Stage 枚举值
    stream_output: bool
    branch_trace: List[dict]
    next_stage: str                      # Stage 枚举值
    current_plan: dict
    current_step_index: int
    need_replan: bool
    replan_reason: str
    error_kind: str                      # ErrorKind 枚举值
    error_detail: str
    recovery_action: str                 # RecoveryAction 枚举值
    fallback_used: bool
    retry_trace: List[dict]
```

### 4.4 顶层组合

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
    user_input: str                      # 唯一的"通行"字段

    routing: RoutingState                # 路由决策
    teaching: TeachingState              # 教学数据
    retrieval: RetrievalState            # 检索结果
    evaluation: EvalState                # 评估结果
    memory: MemoryState                  # 记忆上下文
    meta: MetaState                      # 元信息追踪
```

### 4.5 状态访问规范

| 谁读 | 谁写 | 示例 |
|------|------|------|
| 图路由函数 | IntentRouter | `state["routing"]["intent"]` |
| teach 分支节点 | diagnose, explain 等 | `state["teaching"]["diagnosis"]` |
| 检索节点 | knowledge_retrieval, evidence_gate | `state["retrieval"]["rag_found"]` |
| evaluate 节点 | evaluate | `state["evaluation"]["mastery_score"]` |
| history_check | MemoryManager | `state["memory"]["has_history"]` |
| 所有节点 | StateManager | `state["meta"]["stage"]` |
| ErrorHandler | ErrorHandler | `state["meta"]["error_kind"]` |

---

## 5. Harness 核心组件

### 5.1 IntentRouter — 意图路由器

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
    def route(self, user_input: str, topic: str | None, history: list[str]) -> RoutingState:
        """返回路由决策结果，写入 state["routing"]"""
        ...
```

**规则路由关键词映射**：

| 意图 | 触发关键词 | 置信度 |
|------|-----------|--------|
| `QA_DIRECT` | "评估", "理解程度", "是什么", "怎么用" | 0.95 |
| `REVIEW` | "复习", "回顾", "再看看" | 0.95 |
| `REPLAN` | "换个", "重新", "换方向" | 0.90 |
| `TEACH_LOOP` | 默认 | 0.50 |

**审计字段**：`intent_source` 记录 "rule" | "llm" | "fallback"，可追溯路由依据。

---

### 5.2 StateManager — 状态管理器

文件：`app/harness/state_manager.py`

**职责**：集中状态变更、快照恢复、变更审计

**接口**：

```python
class StateManager:
    def transition(self, state: LearningState, updates: dict) -> LearningState:
        """应用状态更新。自动检测 stage 变化并记录到 branch_trace。"""
        ...

    def snapshot(self, state: LearningState) -> str:
        """创建快照，返回快照 ID。用于中断恢复。"""
        ...

    def restore(self, snapshot_id: str) -> LearningState:
        """从快照恢复状态。"""
        ...
```

**更新规则**：

- `updates` 中的 key 为子状态名（"routing", "teaching" 等），值合并写入对应子状态
- 顶层 key（如 "user_input"）直接写入
- `meta.stage` 变化时自动追加 `branch_trace` 条目

---

### 5.3 ToolRegistry — 工具注册与选择

文件：`app/harness/tool_registry.py`

**职责**：工具的注册、选择、执行统一入口

**数据模型**：

```python
@dataclass
class ToolSchema:
    name: str                           # 工具名
    description: str                    # 功能描述
    parameters: dict                    # 参数 JSON Schema
    returns: dict                       # 返回值 JSON Schema
    timeout: float = 30.0               # 超时秒数
    risky: bool = False                 # 是否需要额外权限

@dataclass
class ToolResult:
    success: bool
    output: any
    error: str | None = None
    metadata: dict | None = None
```

**接口**：

```python
class ToolRegistry:
    def register(self, schema: ToolSchema, executor: Callable):
        """注册工具"""
        ...

    def select(self, user_input: str, state: LearningState) -> list[str]:
        """根据意图和状态选择工具列表"""
        ...

    def execute(self, tool_name: str, params: dict) -> ToolResult:
        """执行工具，统一错误处理"""
        ...
```

**初始工具**：

| 工具名 | 职责 | 意图映射 |
|--------|------|---------|
| `search_local_textbook` | 检索全局知识库 | teach_loop, qa_direct |
| `search_personal_memory` | 检索用户私域记忆 | teach_loop, qa_direct, review |
| `search_web` | 网页搜索 | qa_direct |

---

### 5.4 MemoryManager — 统一记忆层

文件：`app/harness/memory.py`

**职责**：统一所有记忆的读写入口，封装 RAG、会话、用户画像等底层调用

**数据模型**：

```python
@dataclass
class MemoryItem:
    content: str
    source: str                         # 来源标识
    scope: MemoryScope                  # 作用域
    score: float = 0.0                  # 相关度分数
    metadata: dict | None = None
```

**接口**：

```python
class MemoryManager:
    def recall(self, query: str, user_id: int | None,
               scopes: list[MemoryScope]) -> list[MemoryItem]:
        """按作用域检索记忆，返回按 score 降序排列"""
        ...

    def memorize(self, content: str, scope: MemoryScope,
                 user_id: int | None = None, metadata: dict | None = None) -> str:
        """存储记忆，返回记忆 ID"""
        ...
```

**作用域与底层映射**：

| MemoryScope | 底层实现 | user_id 要求 |
|-------------|---------|-------------|
| `GLOBAL` | `infrastructure/rag/store.py`（scope="global"） | 不需要 |
| `USER` | `infrastructure/rag/store.py`（scope="personal"） | **强制**，缺少则返回空 |
| `SESSION` | `infrastructure/storage/session_store.py` | 不需要 |
| `WORKING` | 当前请求内存 | 不需要 |

---

### 5.5 Guardrails — 安全边界

文件：`app/harness/guardrails.py`

**职责**：三道安全关卡，确保输入合法、工具结果可信、输出安全

**数据模型**：

```python
@dataclass
class GuardResult:
    passed: bool
    reason: str | None = None
    corrected: str | None = None        # 修正后的内容
```

**接口**：

```python
class Guardrails:
    def check_input(self, user_input: str) -> GuardResult:
        """输入守门：长度上限 10000、注入检测、偏题检测"""
        ...

    def check_tool_result(self, tool_name: str, result: ToolResult) -> GuardResult:
        """工具结果守门：空结果语义、参数合法性"""
        ...

    def check_output(self, reply: str, citations: list[dict]) -> GuardResult:
        """输出守门：无引用时添加不确定性声明"""
        ...
```

---

### 5.6 ErrorHandler — 统一错误处理

文件：`app/harness/error_handler.py`

**职责**：统一错误分类、决定恢复策略、消除所有 silent failure

**接口**：

```python
class ErrorHandler:
    def handle(self, error: Exception, state: LearningState) -> dict:
        """分类错误，返回状态更新指令（写入 state["meta"]）"""
        ...
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

**返回格式**：

```python
{
    "meta": {
        "error_kind": ErrorKind.RAG_TIMEOUT,
        "error_detail": "RAG query timed out after 30s",
        "recovery_action": RecoveryAction.RETRY,
        "fallback_used": False,
    }
}
```

---

### 5.7 Observability — 可观测性

文件：`app/harness/observability.py`

**职责**：日志、追踪、指标统一入口

**接口**：

```python
class Observability:
    def trace(self, session_id: str, node: str, event: str,
              data: dict | None = None):
        """记录追踪事件（节点进入/退出/错误）"""
        ...

    def metric(self, name: str, value: float, tags: dict | None = None):
        """记录指标（延迟、命中率、评分等）"""
        ...

    def log(self, level: str, event: str, context: dict | None = None):
        """结构化日志"""
        ...
```

**底层集成**：委托 Langfuse（当 `LANGFUSE_ENABLED=true`），否则输出到标准日志。

---

### 5.8 组件依赖关系

```
IntentRouter ──→ 读 user_input, history
                    │
                    ▼
StateManager ──→ 读写 LearningState
    │               │
    │               ▼
    │           ToolRegistry ──→ 执行工具
    │               │
    │               ▼
    │           MemoryManager ──→ 检索/存储记忆
    │               │
    ▼               ▼
ErrorHandler ←── Guardrails ──→ 安全检查
                    │
                    ▼
              Observability ──→ 记录一切
```

**核心规则**：
- 所有组件通过 `Observability` 记录事件
- 所有异常通过 `ErrorHandler` 处理
- 所有外部数据通过 `MemoryManager` 访问
- 所有工具通过 `ToolRegistry` 执行

---

## 6. 编排层 — LangGraph 图设计

### 6.1 设计原则

1. **节点是薄壳**：只做"读状态 → 委托 harness 组件 → 写子状态"
2. **路由由枚举驱动**：条件边只读 `routing.intent` 等枚举值，不有关键词匹配
3. **错误统一走 safe_node**：节点不自己 try/catch
4. **每个节点只写自己负责的子状态**

### 6.2 图结构

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

### 6.3 safe_node 装饰器

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

### 6.4 节点实现模式

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

**示例 — diagnose 节点**：

```python
def diagnose_node(state: LearningState) -> dict:
    """诊断用户对主题的理解程度"""
    memory = get_memory_manager()
    llm = get_llm_service()

    topic = state.get("memory", {}).get("topic", "")
    user_input = state["user_input"]
    user_id = state.get("meta", {}).get("user_id")

    items = memory.recall(user_input, user_id, [MemoryScope.GLOBAL, MemoryScope.USER])
    result = llm.invoke(DIAGNOSE_SYSTEM, f"主题：{topic}\n用户：{user_input}\n参考：{items}")

    return {"teaching": {"diagnosis": result}}
```

### 6.5 路由函数

文件：`app/agent/routers.py`

所有路由函数只读枚举值，**不做关键词匹配**：

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

### 6.6 图构建

文件：`app/agent/graph.py`

```python
from langgraph.graph import END, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from app.harness.state import LearningState
from app.agent.node_wrapper import safe_node
from app.agent.nodes.route_intent import route_intent_node
from app.agent.nodes.diagnose import diagnose_node
# ... 其他节点导入
from app.agent.routers import route_by_intent, route_after_history, route_after_restate, route_after_gate

def build_learning_graph():
    graph = StateGraph(LearningState)

    # 添加节点（全部 safe_node 包装）
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

    # 入口
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

    return graph.compile(checkpointer=MemorySaver())
```

---

## 7. Infrastructure 层接口规范

### 7.1 LLM 调用

文件：`app/infrastructure/llm.py`

```python
class LLMService:
    def invoke(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        """同步调用 LLM，返回文本"""
        ...

    def invoke_json(self, system_prompt: str, user_prompt: str, **kwargs) -> dict:
        """调用 LLM 并解析 JSON 响应"""
        ...
```

### 7.2 RAG 存储

文件：`app/infrastructure/rag/store.py`

```python
class RAGStore:
    def retrieve(self, query: str, scope: str,
                 user_id: int | None = None, top_k: int = 5) -> list[dict]:
        """检索知识。scope: "global" | "personal"（personal 强制 user_id）"""
        ...

    def index(self, content: str, source: str, scope: str,
              user_id: int | None = None) -> str:
        """入库知识，返回条目 ID"""
        ...
```

### 7.3 会话存储

文件：`app/infrastructure/storage/session_store.py`

```python
class SessionStore:
    def get(self, session_id: str) -> dict | None:
        ...

    def save(self, session_id: str, state: dict) -> None:
        ...

    def delete(self, session_id: str) -> None:
        ...

    def list_by_user(self, user_id: int) -> list[dict]:
        ...
```

---

## 8. API 层规范

### 8.1 三件事原则

每个 API 端点只做：
1. **参数校验**：Pydantic model 验证
2. **委托执行**：调用图或 harness 组件
3. **格式化响应**：返回标准 response model

### 8.2 路由清单

| 端点 | 方法 | 委托目标 |
|------|------|---------|
| `/chat` | POST | `agent/graph.py` 主图 |
| `/chat/stream` | POST | `agent/graph.py` 主图 astream |
| `/chat/multi` | POST | `agent/multi_agent/graph.py` |
| `/auth/register` | POST | `infrastructure/storage/user_store.py` |
| `/auth/login` | POST | `infrastructure/storage/user_store.py` |
| `/eval/{session_id}` | GET | `agent/system_eval/eval_store.py` |
| `/eval/{session_id}/rerun` | POST | `agent/system_eval/eval_graph.py` |
| `/eval/stats/overview` | GET | `agent/system_eval/eval_store.py` |
| `/knowledge/*` | CRUD | `infrastructure/storage/knowledge_store.py` |
| `/sessions/*` | CRUD | `infrastructure/storage/session_store.py` |
| `/profile/*` | GET | `infrastructure/storage/` + `harness/memory.py` |

### 8.3 统一错误响应

文件：`app/api/errors.py`

```python
from app.harness.enums import ErrorKind

ERROR_HTTP_MAP = {
    ErrorKind.INPUT_INVALID: 400,
    ErrorKind.RAG_TIMEOUT: 504,
    ErrorKind.RAG_NO_RESULT: 200,       # 不是错误，返回低置信答案
    ErrorKind.LLM_ERROR: 503,
    ErrorKind.TOOL_ERROR: 500,
    ErrorKind.FATAL: 500,
}

# 响应格式：{"error": "error_kind", "detail": "...", "session_id": "..."}
```

---

## 9. 测试规范

### 9.1 目录结构

```
tests/
├── conftest.py                  # 全局 fixtures + 状态工厂 + FakeLLM
│
├── unit/                        # 单元测试（Mock 所有外部依赖）
│   ├── harness/
│   │   ├── test_intent_router.py
│   │   ├── test_state_manager.py
│   │   ├── test_tool_registry.py
│   │   ├── test_memory.py
│   │   ├── test_guardrails.py
│   │   ├── test_error_handler.py
│   │   └── test_observability.py
│   ├── infrastructure/
│   │   ├── test_llm.py
│   │   ├── test_rag_store.py
│   │   ├── test_session_store.py
│   │   └── test_web_search.py
│   └── agent/
│       ├── test_route_intent.py
│       ├── test_diagnose.py
│       ├── test_explain.py
│       ├── test_restate_check.py
│       ├── test_knowledge_retrieval.py
│       └── test_routers.py
│
├── integration/                 # 集成测试（只 Mock LLM）
│   ├── test_teach_loop_flow.py
│   ├── test_qa_direct_flow.py
│   ├── test_replan_flow.py
│   ├── test_recovery_flow.py
│   └── test_multi_agent_flow.py
│
├── api/                         # API 端到端测试（只 Mock LLM）
│   ├── test_chat_api.py
│   ├── test_auth_api.py
│   ├── test_knowledge_api.py
│   └── test_eval_api.py
│
└── scenarios/                   # 场景驱动测试数据
    ├── teach_loop.json
    ├── qa_direct.json
    ├── replan.json
    └── recovery.json
```

### 9.2 测试工厂

文件：`tests/conftest.py`

```python
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
```

### 9.3 FakeLLM

```python
class FakeLLM:
    """测试用 LLM mock，按关键词返回预设响应"""
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
```

### 9.4 测试分层规则

| 层 | 数量占比 | Mock 范围 | 运行频率 |
|----|---------|----------|---------|
| `unit/` | 70% | 所有外部依赖（LLM、存储、RAG） | 每次提交 |
| `integration/` | 20% | 只 Mock LLM | PR 合并前 |
| `api/` | 10% | 只 Mock LLM | 发布前 |

---

## 10. 前端架构

### 10.1 双轨前端策略

前端分为两个独立系统，各司其职：

```
FastAPI (uvicorn)
    ├── /api/*          → REST API
    ├── /chat/*         → Chainlit 对话界面（对话专用）
    └── /*              → Vue 构建产物 (web/dist/)
```

| 系统 | 技术 | 职责 | 入口 |
|------|------|------|------|
| **Chainlit** | Python | 对话交互（流式输出、多轮会话、学习闭环） | `uv run chainlit run app/ui/chainlit_app.py --port 2554` |
| **Vue 3 + Vite** | TypeScript | 管理界面（知识库、会话、档案、评估大屏） | FastAPI `StaticFiles` 托管 `web/dist/` |

### 10.2 为什么是 Vue 3 + Vite

1. **中文生态优先**：Element Plus（表格、表单、上传、对话框）开箱即用
2. **构建产物为纯静态文件**：`vite build` 输出到 `web/dist/`，FastAPI 直接 `StaticFiles` 托管，**不需要额外 Node 服务**
3. **Vite 开发体验**：HMR 秒级热更新，`vite dev` 时通过 proxy 转发 `/api/*` 到 FastAPI
4. **ECharts 集成**：`vue-echarts` 封装成熟，评估大屏开发快
5. **组件化**：知识库管理、文件上传等复杂交互用 SFC 组织，维护性强

### 10.3 Chainlit — 对话专用

保留 Chainlit 负责对话交互，原因：

- 与 LangGraph 原生集成，流式输出零配置
- 支持多轮会话、用户认证、文件上传
- 对话 UI 不需要自定义，Chainlit 默认体验足够好

**Chainlit 不做的事**：
- 知识库管理页面 → Vue
- 评估可视化大屏 → Vue
- 学习档案页面 → Vue
- 会话列表管理 → Vue

### 10.4 Vue 页面规划

| 页面 | 路由 | 核心组件 | 数据来源 |
|------|------|---------|---------|
| 登录/注册 | `/login` | LoginForm | `/auth/*` |
| 知识库管理 | `/knowledge` | KnowledgeUpload, KnowledgeList | `/knowledge/*` |
| 会话列表 | `/sessions` | SessionList | `/sessions/*` |
| 学习档案 | `/profile` | ProfileCard, TopicTimeline | `/profile/*` |
| 评估大屏 | `/eval` | EvalChart, ScoreTrend, IntentAccuracy | `/eval/stats/overview` |

### 10.5 Vite 开发配置

```typescript
// web/vite.config.ts
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:1900',   // FastAPI 后端
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
```

**开发流程**：

```bash
# 终端 1：FastAPI 后端
PYTHONPATH=. uv run uvicorn app.main:app --port 1900

# 终端 2：Vite 开发服务器（HMR + API 代理）
cd web && npm run dev

# 终端 3：Chainlit 对话（独立端口）
uv run chainlit run app/ui/chainlit_app.py --port 2554
```

**生产部署**：

```bash
# 构建 Vue 静态文件
cd web && npm run build

# FastAPI 托管全部（API + Vue 静态 + Chainlit）
PYTHONPATH=. uv run uvicorn app.main:app --port 1900
```

### 10.6 FastAPI 静态文件挂载

```python
# app/main.py

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# API 路由
app.include_router(auth_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
# ...

# Vue 静态文件（生产模式）
if os.path.exists("web/dist"):
    app.mount("/assets", StaticFiles(directory="web/dist/assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_vue(full_path: str):
        """Vue SPA fallback：所有非 API 路径返回 index.html"""
        file_path = f"web/dist/{full_path}"
        if os.path.exists(file_path) and not full_path.startswith("api"):
            return FileResponse(file_path)
        return FileResponse("web/dist/index.html")
```

---

## 11. 构建顺序

从零构建的实施顺序，每步有明确的门禁：

### Step 1：项目骨架 + 状态模型

**构建内容**：
- `app/harness/enums.py`
- `app/harness/state/` 全部文件
- `app/harness/__init__.py`
- `app/core/config.py`（最小 Settings）
- `app/main.py`（FastAPI 空壳）

**门禁**：`python -c "from app.harness.state import LearningState"` 无报错

### Step 2：Harness 核心组件（最小版）

**构建内容**：
- `app/harness/state_manager.py`
- `app/harness/intent_router.py`（规则路由即可）
- `app/harness/error_handler.py`
- `app/harness/observability.py`（标准日志版）

**门禁**：`IntentRouter.route("我想学二分查找", None, [])` 返回 `intent="teach_loop"`

### Step 3：Infrastructure 最小集

**构建内容**：
- `app/infrastructure/llm.py`
- `app/infrastructure/rag/store.py`（内存版）
- `app/infrastructure/storage/session_store.py`（内存版）

**门禁**：`LLMService.invoke("system", "hello")` 返回字符串

### Step 4：最小图

**构建内容**：
- `app/agent/node_wrapper.py`
- `app/agent/routers.py`
- `app/agent/nodes/route_intent.py`
- `app/agent/nodes/diagnose.py`
- `app/agent/nodes/explain.py`
- `app/agent/graph.py`（最小图：route_intent → diagnose → explain → END）

**门禁**：`graph.invoke({"user_input": "我想学二分查找", ...})` 返回 `teaching.explanation`

### Step 5：完整 teach_loop 分支

**构建内容**：
- `app/agent/nodes/history_check.py`
- `app/agent/nodes/knowledge_retrieval.py`
- `app/agent/nodes/restate_check.py`
- `app/agent/nodes/followup.py`
- `app/agent/nodes/evaluate.py`
- `app/agent/nodes/summarize.py`
- 补全图中 teach_loop 的所有边

**门禁**：teach_loop 全流程可走通

### Step 6：qa_direct + recovery 分支

**构建内容**：
- `app/agent/nodes/rag_first.py`
- `app/agent/nodes/evidence_gate.py`
- `app/agent/nodes/answer_policy.py`
- `app/agent/nodes/recovery.py`
- `app/harness/guardrails.py`

**门禁**：qa_direct 和 recovery 分支可走通

### Step 7：剩余 Harness 组件

**构建内容**：
- `app/harness/tool_registry.py`
- `app/harness/memory.py`
- `app/harness/intent_router.py`（补全 LLM 路由）

**门禁**：`MemoryManager.recall("二分查找", None, [MemoryScope.GLOBAL])` 返回记忆

### Step 8：完整 Infrastructure

**构建内容**：
- `app/infrastructure/rag/` 全部文件
- `app/infrastructure/storage/` 全部文件
- `app/infrastructure/external/` 全部文件
- `app/infrastructure/extraction/`

**门禁**：真实 RAG 入库 + 检索可走通

### Step 9：API 层

**构建内容**：
- `app/api/` 全部文件
- `app/models/schemas.py`

**门禁**：`curl POST /chat` 返回 200

### Step 10：Multi-Agent + System Eval

**构建内容**：
- `app/agent/multi_agent/` 全部文件
- `app/agent/system_eval/` 全部文件

**门禁**：`curl POST /chat/multi` 返回 200

### Step 11：测试 + UI + 前端 + Worker

**构建内容**：
- `tests/` 全部文件
- `app/ui/chainlit_app.py`、`app/ui/chainlit_backend.py`
- `app/worker/`
- `web/` Vue 3 + Vite 项目初始化
- `web/src/views/` 核心页面（LoginView、KnowledgeView、EvalDashboardView）
- `web/vite.config.ts` + FastAPI 静态文件挂载

**门禁**：全量测试 100% 通过 + Vue 页面可访问 + Chainlit 对话可用

### 12：清理 + 文档

**构建内容**：
- 更新 README.md
- 更新 docs/
- 更新 pyproject.toml

**门禁**：门禁验收全部通过

### 构建依赖

```
Step 1 (骨架+状态)
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
Step 7 (剩余 Harness) ──→ Step 8 (完整 Infrastructure)  [可并行]
    │                              │
    ▼                              ▼
Step 9 (API) ←─────────────────────┘
    │
    ▼
Step 10 (Multi-Agent)
    │
    ▼
Step 11 (测试+UI+Worker)
    │
    ▼
Step 12 (清理+文档)
```

---

## 12. 技术栈

| 层级 | 技术 |
|------|------|
| API | FastAPI + Uvicorn |
| 编排 | LangGraph |
| LLM | langchain-openai（兼容 OpenAI 协议） |
| 数据模型 | Pydantic + TypedDict |
| 检索 | BM25 + Dense + RRF + rerank |
| 可观测 | Langfuse |
| 异步 | Celery + Redis |
| 前端-对话 | Chainlit |
| 前端-管理 | Vue 3 + Vite + Element Plus + vue-echarts |
| 存储 | SQLite |
| 包管理 | uv（后端）+ npm（前端） |

---

## 13. 门禁验收标准

| 类别 | 指标 | 阈值 |
|------|------|------|
| 功能 | teach_loop 全流程 | 可走通 |
| 功能 | qa_direct 全流程 | 可走通 |
| 功能 | replan 分支 | 可走通 |
| 功能 | recovery 分支 | 可走通 |
| 功能 | Multi-Agent 协作 | 可走通 |
| 功能 | System Eval | 可走通 |
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
| 前端 | Vue 构建产物 | FastAPI StaticFiles 正常托管 |
| 前端 | 开发模式 | Vite proxy 到 FastAPI 正常 |
