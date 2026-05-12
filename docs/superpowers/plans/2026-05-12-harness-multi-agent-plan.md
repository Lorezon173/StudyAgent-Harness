# LearningAgent Harness 多智能体实施计划

> **面向智能体工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 按任务逐步实施本计划。步骤使用复选框（`- [ ]`）语法进行跟踪。

**目标：** 构建完整的 LearningAgent Harness 系统，包含 LangGraph 编排、LlamaIndex RAG、SQLAlchemy 存储和多智能体 SubGraph 协作。

**架构：** 四层严格单向依赖（API → 编排层 → Harness 层 → 基础设施层）。状态通过 TypedDict 子状态流转，节点是委托给 Harness 组件的薄壳，多智能体使用 LangGraph SubGraph 模式。

**技术栈：** FastAPI、LangGraph、LlamaIndex、SQLAlchemy 2.0 异步、Chroma、ragas、Langfuse、Chainlit、Vue 3 + Vite

---

## 阶段 1：项目骨架 + 状态模型 + 数据库

### 任务 1：使用 uv 初始化项目并创建目录结构

**文件：**
- 创建：`pyproject.toml`
- 创建：`app/__init__.py`
- 创建：`app/core/__init__.py`
- 创建：`app/harness/__init__.py`
- 创建：`app/harness/state/__init__.py`
- 创建：`app/models/__init__.py`
- 创建：`app/agent/__init__.py`
- 创建：`app/agent/nodes/__init__.py`
- 创建：`app/agent/multi_agent/__init__.py`
- 创建：`app/agent/system_eval/__init__.py`
- 创建：`app/infrastructure/__init__.py`
- 创建：`app/infrastructure/rag/__init__.py`
- 创建：`app/infrastructure/storage/__init__.py`
- 创建：`app/infrastructure/external/__init__.py`
- 创建：`app/infrastructure/extraction/__init__.py`
- 创建：`app/api/__init__.py`
- 创建：`app/worker/__init__.py`
- 创建：`app/ui/__init__.py`
- 创建：`tests/__init__.py`
- 创建：`tests/unit/__init__.py`
- 创建：`tests/unit/harness/__init__.py`
- 创建：`tests/unit/infrastructure/__init__.py`
- 创建：`tests/unit/agent/__init__.py`
- 创建：`tests/integration/__init__.py`
- 创建：`tests/api/__init__.py`

- [ ] **第 1 步：初始化 uv 项目并创建 pyproject.toml**

```bash
cd d:/backup/basic_file/Program/LearningAgent/StudyAgent-Harness
uv init --no-readme
```

然后替换 `pyproject.toml` 为：

```toml
[project]
name = "learning-agent-harness"
version = "0.1.0"
description = "LearningAgent Harness - 基于费曼学习法的多智能体学习系统"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "pydantic>=2.10.0",
    "pydantic-settings>=2.6.0",
    "langgraph>=0.2.0",
    "langchain-openai>=0.3.0",
    "langchain-core>=0.3.0",
    "llama-index>=0.12.0",
    "llama-index-vector-stores-chroma>=0.4.0",
    "llama-index-embeddings-openai>=0.3.0",
    "llama-index-postprocessor-sbert>=0.3.0",
    "chromadb>=0.5.0",
    "sqlalchemy[asyncio]>=2.0.0",
    "aiosqlite>=0.20.0",
    "alembic>=1.14.0",
    "langfuse>=2.0.0",
    "ragas>=0.2.0",
    "celery>=5.4.0",
    "redis>=5.2.0",
    "chainlit>=2.0.0",
    "passlib>=1.7.0",
    "python-jose>=3.3.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
    "httpx>=0.28.0",
]
```

- [ ] **第 2 步：安装依赖**

```bash
uv sync
```

预期结果：依赖安装成功。

- [ ] **第 3 步：创建所有 __init__.py 文件**

```bash
mkdir -p app/core app/harness/state app/models app/agent/nodes app/agent/multi_agent app/agent/system_eval app/infrastructure/rag app/infrastructure/storage app/infrastructure/external app/infrastructure/extraction app/api app/worker app/ui tests/unit/harness tests/unit/infrastructure tests/unit/agent tests/integration tests/api
```

然后为每个目录创建空的 `__init__.py`。

- [ ] **第 4 步：验证项目结构**

```bash
uv run python -c "import app; print('OK')"
```

预期结果：`OK`

- [ ] **第 5 步：提交**

```bash
git init
git add pyproject.toml app/ tests/
git commit -m "chore: initialize project with uv and directory structure"
```

---

### 任务 2：创建枚举模块

**文件：**
- 创建：`app/harness/enums.py`
- 测试：`tests/unit/harness/test_enums.py`

- [ ] **第 1 步：编写失败测试**

```python
# tests/unit/harness/test_enums.py
from app.harness.enums import (
    Stage, Intent, GateStatus, MasteryLevel,
    ErrorKind, RecoveryAction, RetrievalMode,
    MemoryScope, AgentRole, EvalMetric,
)

def test_stage_values():
    assert Stage.INIT == "init"
    assert Stage.ROUTING == "routing"
    assert Stage.RETRIEVING == "retrieving"
    assert Stage.DIAGNOSING == "diagnosing"
    assert Stage.EXPLAINING == "explaining"
    assert Stage.RESTATE_CHECK == "restate_check"
    assert Stage.FOLLOWUP == "followup"
    assert Stage.EVALUATING == "evaluating"
    assert Stage.SUMMARIZING == "summarizing"
    assert Stage.RECOVERING == "recovering"
    assert Stage.COMPLETE == "complete"

def test_intent_values():
    assert Intent.TEACH_LOOP == "teach_loop"
    assert Intent.QA_DIRECT == "qa_direct"
    assert Intent.REVIEW == "review"
    assert Intent.REPLAN == "replan"

def test_gate_status_values():
    assert GateStatus.PASS == "pass"
    assert GateStatus.SUPPLEMENT == "supplement"
    assert GateStatus.REJECT == "reject"

def test_mastery_level_values():
    assert MasteryLevel.LOW == "low"
    assert MasteryLevel.MEDIUM == "medium"
    assert MasteryLevel.HIGH == "high"

def test_error_kind_values():
    assert ErrorKind.RAG_TIMEOUT == "rag_timeout"
    assert ErrorKind.RAG_NO_RESULT == "rag_no_result"
    assert ErrorKind.LLM_ERROR == "llm_error"
    assert ErrorKind.TOOL_ERROR == "tool_error"
    assert ErrorKind.INPUT_INVALID == "input_invalid"
    assert ErrorKind.FATAL == "fatal"

def test_recovery_action_values():
    assert RecoveryAction.RETRY == "retry"
    assert RecoveryAction.FALLBACK_LLM == "fallback_llm"
    assert RecoveryAction.SKIP_RETRIEVAL == "skip_retrieval"
    assert RecoveryAction.ABORT == "abort"

def test_retrieval_mode_values():
    assert RetrievalMode.FACT == "fact"
    assert RetrievalMode.FRESHNESS == "freshness"
    assert RetrievalMode.COMPARISON == "comparison"

def test_memory_scope_values():
    assert MemoryScope.WORKING == "working"
    assert MemoryScope.SESSION == "session"
    assert MemoryScope.USER == "user"
    assert MemoryScope.GLOBAL == "global"

def test_agent_role_values():
    assert AgentRole.TEACHING == "teaching"
    assert AgentRole.EVAL == "eval"
    assert AgentRole.RETRIEVAL == "retrieval"
    assert AgentRole.ORCHESTRATOR == "orchestrator"

def test_eval_metric_values():
    assert EvalMetric.FAITHFULNESS == "faithfulness"
    assert EvalMetric.RELEVANCY == "relevancy"
    assert EvalMetric.CONTEXT_PRECISION == "context_precision"
    assert EvalMetric.CONTEXT_RECALL == "context_recall"

def test_enum_is_string():
    assert isinstance(Stage.INIT, str)
    assert isinstance(Intent.TEACH_LOOP, str)
```

- [ ] **第 2 步：运行测试验证失败**

```bash
uv run pytest tests/unit/harness/test_enums.py -v
```

预期结果：失败 — `ModuleNotFoundError: No module named 'app.harness.enums'`

- [ ] **第 3 步：编写实现**

```python
# app/harness/enums.py
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
    """多智能体角色标识"""
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

- [ ] **第 4 步：运行测试验证通过**

```bash
uv run pytest tests/unit/harness/test_enums.py -v
```

预期结果：全部 10 个测试通过

- [ ] **第 5 步：提交**

```bash
git add app/harness/enums.py tests/unit/harness/test_enums.py
git commit -m "feat: add harness enums with StrEnum definitions"
```

---

### 任务 3：创建状态模型（子状态 + LearningState）

**文件：**
- 创建：`app/harness/state/routing.py`
- 创建：`app/harness/state/teaching.py`
- 创建：`app/harness/state/retrieval.py`
- 创建：`app/harness/state/evaluation.py`
- 创建：`app/harness/state/memory.py`
- 创建：`app/harness/state/meta.py`
- 创建：`app/harness/state/__init__.py`
- 测试：`tests/unit/harness/test_state.py`

- [ ] **第 1 步：编写失败测试**

```python
# tests/unit/harness/test_state.py
from app.harness.state import LearningState
from app.harness.state.routing import RoutingState
from app.harness.state.teaching import TeachingState
from app.harness.state.retrieval import RetrievalState
from app.harness.state.evaluation import EvalState
from app.harness.state.memory import MemoryState
from app.harness.state.meta import MetaState

def test_routing_state_is_typed_dict():
    state: RoutingState = {"intent": "teach_loop", "intent_confidence": 0.9}
    assert state["intent"] == "teach_loop"
    assert state["intent_confidence"] == 0.9

def test_teaching_state_is_typed_dict():
    state: TeachingState = {"diagnosis": "基础了解", "explain_loop_count": 0}
    assert state["diagnosis"] == "基础了解"

def test_retrieval_state_has_rag_fields():
    state: RetrievalState = {
        "rag_context": "二分查找是...",
        "rag_found": True,
        "rag_source_count": 3,
        "rag_strategy": "hybrid",
    }
    assert state["rag_found"] is True
    assert state["rag_source_count"] == 3

def test_eval_state_has_ragas_fields():
    state: EvalState = {
        "mastery_score": 65,
        "mastery_level": "medium",
        "ragas_faithfulness": 0.85,
        "ragas_relevancy": 0.90,
    }
    assert state["ragas_faithfulness"] == 0.85

def test_memory_state_is_typed_dict():
    state: MemoryState = {"topic": "二分查找", "has_history": False}
    assert state["topic"] == "二分查找"

def test_meta_state_is_typed_dict():
    state: MetaState = {"session_id": "abc", "stage": "init", "branch_trace": []}
    assert state["stage"] == "init"

def test_learning_state_combines_all():
    state: LearningState = {
        "user_input": "我想学二分查找",
        "routing": {"intent": "teach_loop"},
        "teaching": {},
        "retrieval": {},
        "evaluation": {},
        "memory": {},
        "meta": {"session_id": "test", "stage": "init", "branch_trace": []},
    }
    assert state["user_input"] == "我想学二分查找"
    assert state["routing"]["intent"] == "teach_loop"

def test_learning_state_total_false_allows_partial():
    state: LearningState = {"user_input": "hello"}
    assert state["user_input"] == "hello"
```

- [ ] **第 2 步：运行测试验证失败**

```bash
uv run pytest tests/unit/harness/test_state.py -v
```

预期结果：失败 — `ModuleNotFoundError`

- [ ] **第 3 步：编写所有子状态文件**

按照设计文档第 5.3 节的精确内容创建每个文件：

`app/harness/state/routing.py`:
```python
from typing import TypedDict

class RoutingState(TypedDict, total=False):
    intent: str
    intent_confidence: float
    intent_source: str
    tool_route: dict
    retrieval_strategy: dict
    retrieval_mode: str
```

`app/harness/state/teaching.py`:
```python
from typing import TypedDict

class TeachingState(TypedDict, total=False):
    diagnosis: str
    explanation: str
    restatement_eval: str
    followup_question: str
    summary: str
    reply: str
    explain_loop_count: int
    user_choice: str
    waiting_for_choice: bool
```

`app/harness/state/retrieval.py`:
```python
from typing import TypedDict, List

class RetrievalState(TypedDict, total=False):
    rag_context: str
    rag_citations: List[dict]
    rag_found: bool
    rag_confidence_level: str
    rag_avg_score: float
    rag_source_count: int
    rag_strategy: str
    gate_status: str
    gate_coverage_score: float
    gate_missing_keywords: List[str]
```

`app/harness/state/evaluation.py`:
```python
from typing import TypedDict, List

class EvalState(TypedDict, total=False):
    mastery_score: int
    mastery_level: str
    mastery_rationale: str
    error_labels: List[str]
    answer_template_id: str
    boundary_notice: str
    ragas_faithfulness: float
    ragas_relevancy: float
    ragas_context_precision: float
```

`app/harness/state/memory.py`:
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

`app/harness/state/meta.py`:
```python
from typing import TypedDict, List, Optional

class MetaState(TypedDict, total=False):
    session_id: str
    user_id: Optional[int]
    stage: str
    stream_output: bool
    branch_trace: List[dict]
    next_stage: str
    current_plan: dict
    current_step_index: int
    need_replan: bool
    replan_reason: str
    error_kind: str
    error_detail: str
    recovery_action: str
    fallback_used: bool
    retry_trace: List[dict]
```

`app/harness/state/__init__.py`:
```python
from typing import TypedDict
from .routing import RoutingState
from .teaching import TeachingState
from .retrieval import RetrievalState
from .evaluation import EvalState
from .memory import MemoryState
from .meta import MetaState

class LearningState(TypedDict, total=False):
    """学习智能体总状态 — 所有图节点共享"""
    user_input: str
    routing: RoutingState
    teaching: TeachingState
    retrieval: RetrievalState
    evaluation: EvalState
    memory: MemoryState
    meta: MetaState
```

- [ ] **第 4 步：运行测试验证通过**

```bash
uv run pytest tests/unit/harness/test_state.py -v
```

预期结果：全部 8 个测试通过

- [ ] **第 5 步：验证门禁检查**

```bash
uv run python -c "from app.harness.state import LearningState; print('门禁通过')"
```

预期结果：`门禁通过`

- [ ] **第 6 步：提交**

```bash
git add app/harness/state/ tests/unit/harness/test_state.py
git commit -m "feat: add layered state model with LearningState composition"
```

---

### 任务 4：创建配置和数据库模块

**文件：**
- 创建：`app/core/config.py`
- 创建：`app/core/database.py`
- 创建：`app/models/tables.py`
- 测试：`tests/unit/test_database.py`

- [ ] **第 1 步：编写失败测试**

```python
# tests/unit/test_database.py
import pytest
from sqlalchemy import select
from app.core.database import Base, get_engine
from app.models.tables import UserTable, SessionTable, KnowledgeTable, EvalTable

@pytest.mark.asyncio
async def test_create_tables():
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        result = await session.execute(select(UserTable))
        users = result.scalars().all()
        assert users == []

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()

@pytest.mark.asyncio
async def test_insert_user():
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        user = UserTable(username="testuser", password_hash="hash123")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        assert user.id is not None
        assert user.username == "testuser"

    await engine.dispose()

@pytest.mark.asyncio
async def test_knowledge_table_has_doc_ids():
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        k = KnowledgeTable(scope="global", content="test content", doc_ids=["doc1", "doc2"])
        session.add(k)
        await session.commit()
        await session.refresh(k)
        assert k.doc_ids == ["doc1", "doc2"]

    await engine.dispose()
```

- [ ] **第 2 步：运行测试验证失败**

```bash
uv run pytest tests/unit/test_database.py -v
```

预期结果：失败 — `ModuleNotFoundError`

- [ ] **第 3 步：编写实现**

`app/core/config.py`:
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_name: str = "LearningAgent"
    app_version: str = "0.1.0"
    debug: bool = True
    database_url: str = "sqlite+aiosqlite:///./learning_agent.db"
    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_model: str = "gpt-4o-mini"
    langfuse_enabled: bool = False
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

settings = Settings()
```

`app/core/database.py`:
```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

def get_engine(url: str = "sqlite+aiosqlite:///./learning_agent.db"):
    return create_async_engine(url, echo=False)

engine = get_engine()
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db() -> AsyncSession:
    async with async_session() as session:
        yield session

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

`app/models/tables.py`:
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

- [ ] **第 4 步：运行测试验证通过**

```bash
uv run pytest tests/unit/test_database.py -v
```

预期结果：全部 3 个测试通过

- [ ] **第 5 步：提交**

```bash
git add app/core/config.py app/core/database.py app/models/tables.py tests/unit/test_database.py
git commit -m "feat: add config, database engine, and ORM table definitions"
```

---

### 任务 5：创建 FastAPI 应用入口

**文件：**
- 创建：`app/main.py`
- 测试：`tests/unit/test_main.py`

- [ ] **第 1 步：编写失败测试**

```python
# tests/unit/test_main.py
from httpx import AsyncClient, ASGITransport
import pytest

@pytest.mark.asyncio
async def test_app_starts():
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/docs")
        assert response.status_code == 200
```

- [ ] **第 2 步：运行测试验证失败**

```bash
uv run pytest tests/unit/test_main.py -v
```

预期结果：失败

- [ ] **第 3 步：编写实现**

```python
# app/main.py
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.core.database import init_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield

app = FastAPI(title="LearningAgent", version="0.1.0", lifespan=lifespan)

@app.get("/health")
async def health():
    return {"status": "ok"}

if os.path.exists("web/dist"):
    app.mount("/assets", StaticFiles(directory="web/dist/assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_vue(full_path: str):
        file_path = f"web/dist/{full_path}"
        if os.path.exists(file_path) and not full_path.startswith("api"):
            return FileResponse(file_path)
        return FileResponse("web/dist/index.html")
```

- [ ] **第 4 步：运行测试验证通过**

```bash
uv run pytest tests/unit/test_main.py -v
```

预期结果：通过

- [ ] **第 5 步：提交**

```bash
git add app/main.py tests/unit/test_main.py
git commit -m "feat: add FastAPI application entry with lifespan and health endpoint"
```

---

## 阶段 2：Harness 核心组件（最小集）

### 任务 6：创建可观测性模块

**文件：**
- 创建：`app/harness/observability.py`
- 测试：`tests/unit/harness/test_observability.py`

- [ ] **第 1 步：编写失败测试**

```python
# tests/unit/harness/test_observability.py
import logging
from app.harness.observability import Observability, get_observability

def test_trace_logs_without_error(caplog):
    obs = Observability()
    with caplog.at_level(logging.INFO):
        obs.trace("session1", "diagnose", "start", {"key": "val"})
    assert any("session1" in r.message for r in caplog.records)

def test_metric_logs_without_error(caplog):
    obs = Observability()
    with caplog.at_level(logging.INFO):
        obs.metric("latency_ms", 150.0, {"node": "diagnose"})
    assert any("latency_ms" in r.message for r in caplog.records)

def test_log_outputs_structured(caplog):
    obs = Observability()
    with caplog.at_level(logging.INFO):
        obs.log("info", "test_event", {"detail": "something"})
    assert any("test_event" in r.message for r in caplog.records)

def test_get_observability_returns_singleton():
    obs1 = get_observability()
    obs2 = get_observability()
    assert obs1 is obs2
```

- [ ] **第 2 步：运行测试验证失败**

```bash
uv run pytest tests/unit/harness/test_observability.py -v
```

预期结果：失败

- [ ] **第 3 步：编写实现**

```python
# app/harness/observability.py
import logging
import json

logger = logging.getLogger("learning_agent")

class Observability:
    def trace(self, session_id: str, node: str, event: str,
              data: dict | None = None):
        logger.info(json.dumps({
            "type": "trace", "session_id": session_id,
            "node": node, "event": event, "data": data or {},
        }))

    def metric(self, name: str, value: float, tags: dict | None = None):
        logger.info(json.dumps({
            "type": "metric", "name": name,
            "value": value, "tags": tags or {},
        }))

    def log(self, level: str, event: str, context: dict | None = None):
        log_fn = getattr(logger, level, logger.info)
        log_fn(json.dumps({
            "type": "log", "event": event, "context": context or {},
        }))

_instance: Observability | None = None

def get_observability() -> Observability:
    global _instance
    if _instance is None:
        _instance = Observability()
    return _instance
```

- [ ] **第 4 步：运行测试验证通过**

```bash
uv run pytest tests/unit/harness/test_observability.py -v
```

预期结果：全部 4 个测试通过

- [ ] **第 5 步：提交**

```bash
git add app/harness/observability.py tests/unit/harness/test_observability.py
git commit -m "feat: add Observability module with structured logging"
```

---

### 任务 7：创建错误处理模块

**文件：**
- 创建：`app/harness/error_handler.py`
- 测试：`tests/unit/harness/test_error_handler.py`

- [ ] **第 1 步：编写失败测试**

```python
# tests/unit/harness/test_error_handler.py
from app.harness.error_handler import ErrorHandler, get_error_handler
from app.harness.enums import ErrorKind, RecoveryAction
from app.harness.state import LearningState

def test_rag_timeout():
    handler = ErrorHandler()
    state: LearningState = {"user_input": "", "meta": {"session_id": "t", "stage": "init", "branch_trace": []}}
    result = handler.handle(TimeoutError("RAG query timed out after 30s"), state)
    assert result["meta"]["error_kind"] == ErrorKind.RAG_TIMEOUT
    assert result["meta"]["recovery_action"] == RecoveryAction.RETRY

def test_rag_no_result():
    handler = ErrorHandler()
    state: LearningState = {"user_input": "", "meta": {"session_id": "t", "stage": "init", "branch_trace": []}}
    result = handler.handle(ValueError("no result found"), state)
    assert result["meta"]["error_kind"] == ErrorKind.RAG_NO_RESULT
    assert result["meta"]["recovery_action"] == RecoveryAction.FALLBACK_LLM

def test_llm_rate_limit():
    handler = ErrorHandler()
    state: LearningState = {"user_input": "", "meta": {"session_id": "t", "stage": "init", "branch_trace": []}}
    result = handler.handle(Exception("429 rate limit exceeded"), state)
    assert result["meta"]["error_kind"] == ErrorKind.LLM_ERROR
    assert result["meta"]["recovery_action"] == RecoveryAction.SKIP_RETRIEVAL

def test_fatal():
    handler = ErrorHandler()
    state: LearningState = {"user_input": "", "meta": {"session_id": "t", "stage": "init", "branch_trace": []}}
    result = handler.handle(RuntimeError("unknown crash"), state)
    assert result["meta"]["error_kind"] == ErrorKind.FATAL
    assert result["meta"]["recovery_action"] == RecoveryAction.ABORT

def test_get_error_handler_returns_singleton():
    h1 = get_error_handler()
    h2 = get_error_handler()
    assert h1 is h2
```

- [ ] **第 2 步：运行测试验证失败**

```bash
uv run pytest tests/unit/harness/test_error_handler.py -v
```

预期结果：失败

- [ ] **第 3 步：编写实现**

```python
# app/harness/error_handler.py
from app.harness.enums import ErrorKind, RecoveryAction
from app.harness.state import LearningState

class ErrorHandler:
    def handle(self, error: Exception, state: LearningState) -> dict:
        msg = str(error).lower()
        error_kind = self._classify(msg)
        recovery = self._recovery(error_kind)
        return {
            "meta": {
                "error_kind": error_kind,
                "error_detail": str(error),
                "recovery_action": recovery,
                "fallback_used": False,
            }
        }

    def _classify(self, msg: str) -> str:
        if "timeout" in msg:
            return ErrorKind.RAG_TIMEOUT
        if "no result" in msg or "empty" in msg:
            return ErrorKind.RAG_NO_RESULT
        if "rate" in msg or "429" in msg:
            return ErrorKind.LLM_ERROR
        if "tool" in msg:
            return ErrorKind.TOOL_ERROR
        if "input" in msg and "invalid" in msg:
            return ErrorKind.INPUT_INVALID
        return ErrorKind.FATAL

    def _recovery(self, kind: str) -> str:
        mapping = {
            ErrorKind.RAG_TIMEOUT: RecoveryAction.RETRY,
            ErrorKind.RAG_NO_RESULT: RecoveryAction.FALLBACK_LLM,
            ErrorKind.LLM_ERROR: RecoveryAction.SKIP_RETRIEVAL,
            ErrorKind.TOOL_ERROR: RecoveryAction.FALLBACK_LLM,
            ErrorKind.INPUT_INVALID: RecoveryAction.ABORT,
            ErrorKind.FATAL: RecoveryAction.ABORT,
        }
        return mapping.get(kind, RecoveryAction.ABORT)

_instance: ErrorHandler | None = None

def get_error_handler() -> ErrorHandler:
    global _instance
    if _instance is None:
        _instance = ErrorHandler()
    return _instance
```

- [ ] **第 4 步：运行测试验证通过**

```bash
uv run pytest tests/unit/harness/test_error_handler.py -v
```

预期结果：全部 5 个测试通过

- [ ] **第 5 步：提交**

```bash
git add app/harness/error_handler.py tests/unit/harness/test_error_handler.py
git commit -m "feat: add ErrorHandler with classification and recovery mapping"
```

---

### 任务 8：创建意图路由模块（仅基于规则）

**文件：**
- 创建：`app/harness/intent_router.py`
- 测试：`tests/unit/harness/test_intent_router.py`

- [ ] **第 1 步：编写失败测试**

```python
# tests/unit/harness/test_intent_router.py
from app.harness.intent_router import IntentRouter
from app.harness.enums import Intent

def test_teach_loop_default():
    router = IntentRouter()
    result = router.route("我想学二分查找", None, [])
    assert result["intent"] == Intent.TEACH_LOOP
    assert result["intent_source"] == "fallback"

def test_qa_direct_rule():
    router = IntentRouter()
    result = router.route("二分查找是什么", None, [])
    assert result["intent"] == Intent.QA_DIRECT
    assert result["intent_source"] == "rule"
    assert result["intent_confidence"] >= 0.9

def test_review_rule():
    router = IntentRouter()
    result = router.route("帮我复习二分查找", None, [])
    assert result["intent"] == Intent.REVIEW
    assert result["intent_source"] == "rule"

def test_replan_rule():
    router = IntentRouter()
    result = router.route("换个话题吧", None, [])
    assert result["intent"] == Intent.REPLAN
    assert result["intent_source"] == "rule"

def test_qa_how_to():
    router = IntentRouter()
    result = router.route("怎么用快速排序", None, [])
    assert result["intent"] == Intent.QA_DIRECT

def test_qa_evaluate():
    router = IntentRouter()
    result = router.route("评估一下我的理解程度", None, [])
    assert result["intent"] == Intent.QA_DIRECT
```

- [ ] **第 2 步：运行测试验证失败**

```bash
uv run pytest tests/unit/harness/test_intent_router.py -v
```

预期结果：失败

- [ ] **第 3 步：编写实现**

```python
# app/harness/intent_router.py
from app.harness.enums import Intent
from app.harness.state.routing import RoutingState

RULE_MAP: list[tuple[list[str], str, float]] = [
    (["评估", "理解程度", "是什么", "怎么用"], Intent.QA_DIRECT, 0.95),
    (["复习", "回顾", "再看看"], Intent.REVIEW, 0.95),
    (["换个", "重新", "换方向"], Intent.REPLAN, 0.90),
]

class IntentRouter:
    def route(self, user_input: str, topic: str | None,
              history: list[str]) -> RoutingState:
        for keywords, intent, confidence in RULE_MAP:
            if any(kw in user_input for kw in keywords):
                return RoutingState(
                    intent=intent,
                    intent_confidence=confidence,
                    intent_source="rule",
                )
        return RoutingState(
            intent=Intent.TEACH_LOOP,
            intent_confidence=0.50,
            intent_source="fallback",
        )
```

- [ ] **第 4 步：运行测试验证通过**

```bash
uv run pytest tests/unit/harness/test_intent_router.py -v
```

预期结果：全部 6 个测试通过

- [ ] **第 5 步：验证门禁检查**

```bash
uv run python -c "from app.harness.intent_router import IntentRouter; r = IntentRouter().route('我想学二分查找', None, []); assert r['intent'] == 'teach_loop'; print('门禁通过')"
```

预期结果：`门禁通过`

- [ ] **第 6 步：提交**

```bash
git add app/harness/intent_router.py tests/unit/harness/test_intent_router.py
git commit -m "feat: add IntentRouter with rule-based routing and fallback"
```

---

### 任务 9：创建状态管理器模块

**文件：**
- 创建：`app/harness/state_manager.py`
- 测试：`tests/unit/harness/test_state_manager.py`

- [ ] **第 1 步：编写失败测试**

```python
# tests/unit/harness/test_state_manager.py
from app.harness.state_manager import StateManager
from app.harness.enums import Stage
from app.harness.state import LearningState

def test_transition_merges_sub_state():
    sm = StateManager()
    state: LearningState = {
        "user_input": "", "routing": {}, "teaching": {},
        "retrieval": {}, "evaluation": {}, "memory": {},
        "meta": {"session_id": "t", "stage": Stage.INIT, "branch_trace": []},
    }
    result = sm.transition(state, {"routing": {"intent": "teach_loop", "intent_confidence": 0.9}})
    assert result["routing"]["intent"] == "teach_loop"

def test_transition_top_level_key():
    sm = StateManager()
    state: LearningState = {
        "user_input": "", "routing": {}, "teaching": {},
        "retrieval": {}, "evaluation": {}, "memory": {},
        "meta": {"session_id": "t", "stage": Stage.INIT, "branch_trace": []},
    }
    result = sm.transition(state, {"user_input": "hello"})
    assert result["user_input"] == "hello"

def test_transition_stage_change_appends_trace():
    sm = StateManager()
    state: LearningState = {
        "user_input": "", "routing": {}, "teaching": {},
        "retrieval": {}, "evaluation": {}, "memory": {},
        "meta": {"session_id": "t", "stage": Stage.INIT, "branch_trace": []},
    }
    result = sm.transition(state, {"meta": {"stage": Stage.ROUTING}})
    assert len(result["meta"]["branch_trace"]) == 1
    assert result["meta"]["branch_trace"][0]["from"] == Stage.INIT
    assert result["meta"]["branch_trace"][0]["to"] == Stage.ROUTING

def test_snapshot_and_restore():
    sm = StateManager()
    state: LearningState = {
        "user_input": "test", "routing": {"intent": "teach_loop"}, "teaching": {},
        "retrieval": {}, "evaluation": {}, "memory": {},
        "meta": {"session_id": "t", "stage": Stage.INIT, "branch_trace": []},
    }
    sid = sm.snapshot(state)
    assert sid
    restored = sm.restore(sid)
    assert restored["user_input"] == "test"
    assert restored["routing"]["intent"] == "teach_loop"
```

- [ ] **第 2 步：运行测试验证失败**

```bash
uv run pytest tests/unit/harness/test_state_manager.py -v
```

预期结果：失败

- [ ] **第 3 步：编写实现**

```python
# app/harness/state_manager.py
import copy
import uuid
from app.harness.state import LearningState

class StateManager:
    def __init__(self):
        self._snapshots: dict[str, LearningState] = {}

    def transition(self, state: LearningState, updates: dict) -> LearningState:
        result = copy.deepcopy(state)
        for key, value in updates.items():
            if key in ("user_input",):
                result[key] = value
            elif isinstance(value, dict) and isinstance(result.get(key), dict):
                result[key].update(value)
            else:
                result[key] = value

        if "meta" in updates and "stage" in updates.get("meta", {}):
            old_stage = state.get("meta", {}).get("stage", "")
            new_stage = updates["meta"]["stage"]
            if old_stage != new_stage:
                trace = result.get("meta", {}).get("branch_trace", [])
                trace.append({"from": old_stage, "to": new_stage})
                result["meta"]["branch_trace"] = trace
        return result

    def snapshot(self, state: LearningState) -> str:
        sid = str(uuid.uuid4())
        self._snapshots[sid] = copy.deepcopy(state)
        return sid

    def restore(self, snapshot_id: str) -> LearningState:
        return copy.deepcopy(self._snapshots[snapshot_id])
```

- [ ] **第 4 步：运行测试验证通过**

```bash
uv run pytest tests/unit/harness/test_state_manager.py -v
```

预期结果：全部 4 个测试通过

- [ ] **第 5 步：提交**

```bash
git add app/harness/state_manager.py tests/unit/harness/test_state_manager.py
git commit -m "feat: add StateManager with transition, snapshot, and restore"
```

---

## 阶段 3：基础设施最小集

### 任务 10：创建大语言模型服务

**文件：**
- 创建：`app/infrastructure/llm.py`
- 测试：`tests/unit/infrastructure/test_llm.py`

- [ ] **第 1 步：编写失败测试**

```python
# tests/unit/infrastructure/test_llm.py
from app.infrastructure.llm import LLMService, FakeLLM

def test_fake_llm_invoke():
    llm = FakeLLM()
    result = llm.invoke("system", "请诊断用户理解程度")
    assert "诊断" in result or "基础了解" in result

def test_fake_llm_invoke_json():
    llm = FakeLLM()
    result = llm.invoke_json("system", "请输出意图分类意图")
    assert "intent" in result

def test_fake_llm_default():
    llm = FakeLLM()
    result = llm.invoke("system", "随机问题")
    assert result == "默认测试回复"

def test_llm_service_has_interface():
    assert hasattr(LLMService, 'invoke')
    assert hasattr(LLMService, 'invoke_json')
```

- [ ] **第 2 步：运行测试验证失败**

```bash
uv run pytest tests/unit/infrastructure/test_llm.py -v
```

预期结果：失败

- [ ] **第 3 步：编写实现**

```python
# app/infrastructure/llm.py
import json

class LLMService:
    def __init__(self, api_key: str = "", base_url: str = "", model: str = "gpt-4o-mini"):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

    def invoke(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(
            api_key=self.api_key,
            base_url=self.base_url or None,
            model=self.model,
        )
        from langchain_core.messages import SystemMessage, HumanMessage
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])
        return response.content

    def invoke_json(self, system_prompt: str, user_prompt: str, **kwargs) -> dict:
        text = self.invoke(system_prompt, user_prompt, **kwargs)
        return json.loads(text)


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
```

- [ ] **第 4 步：运行测试验证通过**

```bash
uv run pytest tests/unit/infrastructure/test_llm.py -v
```

预期结果：全部 4 个测试通过

- [ ] **第 5 步：提交**

```bash
git add app/infrastructure/llm.py tests/unit/infrastructure/test_llm.py
git commit -m "feat: add LLMService with langchain-openai and FakeLLM for tests"
```

---

### 任务 11：创建会话存储（SQLAlchemy）

**文件：**
- 创建：`app/infrastructure/storage/session_store.py`
- 创建：`app/infrastructure/storage/user_store.py`
- 测试：`tests/unit/infrastructure/test_stores.py`

- [ ] **第 1 步：编写失败测试**

```python
# tests/unit/infrastructure/test_stores.py
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.database import Base
from app.infrastructure.storage.session_store import SessionStore
from app.infrastructure.storage.user_store import UserStore

@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()

@pytest.mark.asyncio
async def test_session_save_and_get(db):
    store = SessionStore(db)
    await store.save("sess1", {"user_input": "hello"}, user_id=None)
    result = await store.get("sess1")
    assert result is not None
    assert result["user_input"] == "hello"

@pytest.mark.asyncio
async def test_session_delete(db):
    store = SessionStore(db)
    await store.save("sess1", {"user_input": "hello"})
    await store.delete("sess1")
    result = await store.get("sess1")
    assert result is None

@pytest.mark.asyncio
async def test_user_create_and_find(db):
    store = UserStore(db)
    user = await store.create("testuser", "hashed_pw")
    assert user.id is not None
    found = await store.find_by_username("testuser")
    assert found is not None
    assert found.username == "testuser"
```

- [ ] **第 2 步：运行测试验证失败**

```bash
uv run pytest tests/unit/infrastructure/test_stores.py -v
```

预期结果：失败

- [ ] **第 3 步：编写实现**

`app/infrastructure/storage/session_store.py`:
```python
import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.tables import SessionTable

class SessionStore:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get(self, session_id: str) -> dict | None:
        result = await self.db.execute(
            select(SessionTable).where(SessionTable.id == session_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return json.loads(row.state_json)

    async def save(self, session_id: str, state: dict, user_id: int | None = None) -> None:
        result = await self.db.execute(
            select(SessionTable).where(SessionTable.id == session_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = SessionTable(id=session_id, state_json=json.dumps(state), user_id=user_id)
            self.db.add(row)
        else:
            row.state_json = json.dumps(state)
            if user_id is not None:
                row.user_id = user_id
        await self.db.commit()

    async def delete(self, session_id: str) -> None:
        result = await self.db.execute(
            select(SessionTable).where(SessionTable.id == session_id)
        )
        row = result.scalar_one_or_none()
        if row:
            await self.db.delete(row)
            await self.db.commit()

    async def list_by_user(self, user_id: int) -> list[dict]:
        result = await self.db.execute(
            select(SessionTable).where(SessionTable.user_id == user_id)
        )
        return [{"id": r.id, "created_at": str(r.created_at)} for r in result.scalars().all()]
```

`app/infrastructure/storage/user_store.py`:
```python
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.tables import UserTable

class UserStore:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, username: str, password_hash: str) -> UserTable:
        user = UserTable(username=username, password_hash=password_hash)
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def find_by_username(self, username: str) -> UserTable | None:
        result = await self.db.execute(
            select(UserTable).where(UserTable.username == username)
        )
        return result.scalar_one_or_none()
```

- [ ] **第 4 步：运行测试验证通过**

```bash
uv run pytest tests/unit/infrastructure/test_stores.py -v
```

预期结果：全部 3 个测试通过

- [ ] **第 5 步：提交**

```bash
git add app/infrastructure/storage/session_store.py app/infrastructure/storage/user_store.py tests/unit/infrastructure/test_stores.py
git commit -m "feat: add SessionStore and UserStore with SQLAlchemy async"
```

---

## 阶段 4：最小图

### 任务 12：创建 safe_node 包装器和 route_intent 节点

**文件：**
- 创建：`app/agent/node_wrapper.py`
- 创建：`app/agent/nodes/route_intent.py`
- 测试：`tests/unit/agent/test_route_intent.py`

- [ ] **第 1 步：编写失败测试**

```python
# tests/unit/agent/test_route_intent.py
from app.agent.nodes.route_intent import route_intent_node
from app.harness.enums import Intent, Stage
from app.harness.state import LearningState

def test_route_intent_returns_routing_state():
    state: LearningState = {
        "user_input": "帮我复习二分查找",
        "routing": {}, "teaching": {}, "retrieval": {},
        "evaluation": {}, "memory": {},
        "meta": {"session_id": "t", "stage": Stage.INIT, "branch_trace": []},
    }
    result = route_intent_node(state)
    assert result["routing"]["intent"] == Intent.REVIEW
    assert result["routing"]["intent_source"] == "rule"

def test_safe_node_catches_exception():
    from app.agent.node_wrapper import safe_node

    def bad_node(state):
        raise ValueError("test error")

    wrapped = safe_node(bad_node)
    state: LearningState = {
        "user_input": "", "routing": {}, "teaching": {}, "retrieval": {},
        "evaluation": {}, "memory": {},
        "meta": {"session_id": "t", "stage": Stage.INIT, "branch_trace": []},
    }
    result = wrapped(state)
    assert "meta" in result
    assert result["meta"]["error_kind"] is not None
```

- [ ] **第 2 步：运行测试验证失败**

```bash
uv run pytest tests/unit/agent/test_route_intent.py -v
```

预期结果：失败

- [ ] **第 3 步：编写实现**

`app/agent/node_wrapper.py`:
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

`app/agent/nodes/route_intent.py`:
```python
from app.harness.state import LearningState
from app.harness.intent_router import IntentRouter

_router = IntentRouter()

def route_intent_node(state: LearningState) -> dict:
    """意图路由节点：判断用户意图"""
    user_input = state["user_input"]
    topic = state.get("memory", {}).get("topic")
    history = state.get("memory", {}).get("history", [])

    routing = _router.route(user_input, topic, history)
    return {"routing": dict(routing)}
```

- [ ] **第 4 步：运行测试验证通过**

```bash
uv run pytest tests/unit/agent/test_route_intent.py -v
```

预期结果：全部 2 个测试通过

- [ ] **第 5 步：提交**

```bash
git add app/agent/node_wrapper.py app/agent/nodes/route_intent.py tests/unit/agent/test_route_intent.py
git commit -m "feat: add safe_node wrapper and route_intent node"
```

---

### 任务 13：创建诊断和讲解节点 + 最小图

**文件：**
- 创建：`app/agent/nodes/diagnose.py`
- 创建：`app/agent/nodes/explain.py`
- 创建：`app/agent/routers.py`
- 创建：`app/agent/graph.py`
- 测试：`tests/unit/agent/test_minimal_graph.py`

- [ ] **第 1 步：编写失败测试**

```python
# tests/unit/agent/test_minimal_graph.py
import pytest
from app.harness.enums import Intent, Stage
from app.harness.state import LearningState

def test_minimal_graph_route_intent():
    from app.agent.graph import build_learning_graph
    graph = build_learning_graph()
    state: LearningState = {
        "user_input": "我想学二分查找",
        "routing": {}, "teaching": {}, "retrieval": {},
        "evaluation": {}, "memory": {},
        "meta": {"session_id": "test", "stage": Stage.INIT, "branch_trace": []},
    }
    result = graph.invoke(state, config={"configurable": {"thread_id": "test"}})
    assert "routing" in result
    assert result["routing"]["intent"] == Intent.TEACH_LOOP
```

- [ ] **第 2 步：运行测试验证失败**

```bash
uv run pytest tests/unit/agent/test_minimal_graph.py -v
```

预期结果：失败

- [ ] **第 3 步：编写所有节点文件**

`app/agent/nodes/diagnose.py`:
```python
from app.harness.state import LearningState
from app.infrastructure.llm import FakeLLM

_llm = FakeLLM()

def diagnose_node(state: LearningState) -> dict:
    """诊断用户对主题的理解程度"""
    topic = state.get("memory", {}).get("topic", "")
    user_input = state["user_input"]
    result = _llm.invoke("你是学习诊断助手", f"主题：{topic}\n用户：{user_input}\n请诊断")
    return {"teaching": {"diagnosis": result}}
```

`app/agent/nodes/explain.py`:
```python
from app.harness.state import LearningState
from app.infrastructure.llm import FakeLLM

_llm = FakeLLM()

def explain_node(state: LearningState) -> dict:
    """讲解知识点"""
    topic = state.get("memory", {}).get("topic", "")
    diagnosis = state.get("teaching", {}).get("diagnosis", "")
    result = _llm.invoke("你是教学助手", f"主题：{topic}\n诊断：{diagnosis}\n请讲解")
    return {"teaching": {"explanation": result, "reply": result}}
```

`app/agent/routers.py`:
```python
from app.harness.enums import Intent, GateStatus
from app.harness.state import LearningState

def route_by_intent(state: LearningState) -> str:
    intent = state.get("routing", {}).get("intent", Intent.TEACH_LOOP)
    return {
        Intent.TEACH_LOOP: "diagnose",
        Intent.QA_DIRECT: "diagnose",
        Intent.REPLAN: "diagnose",
        Intent.REVIEW: "diagnose",
    }[intent]
```

`app/agent/graph.py`:
```python
from langgraph.graph import END, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from app.harness.state import LearningState
from app.agent.node_wrapper import safe_node
from app.agent.nodes.route_intent import route_intent_node
from app.agent.nodes.diagnose import diagnose_node
from app.agent.nodes.explain import explain_node
from app.agent.routers import route_by_intent

def build_learning_graph():
    graph = StateGraph(LearningState)

    graph.add_node("route_intent", safe_node(route_intent_node))
    graph.add_node("diagnose", safe_node(diagnose_node))
    graph.add_node("explain", safe_node(explain_node))

    graph.set_entry_point("route_intent")

    graph.add_conditional_edges("route_intent", route_by_intent, {
        "diagnose": "diagnose",
    })
    graph.add_edge("diagnose", "explain")
    graph.add_edge("explain", END)

    return graph.compile(checkpointer=MemorySaver())
```

- [ ] **第 4 步：运行测试验证通过**

```bash
uv run pytest tests/unit/agent/test_minimal_graph.py -v
```

预期结果：通过

- [ ] **第 5 步：提交**

```bash
git add app/agent/nodes/diagnose.py app/agent/nodes/explain.py app/agent/routers.py app/agent/graph.py tests/unit/agent/test_minimal_graph.py
git commit -m "feat: add minimal graph with route_intent, diagnose, explain nodes"
```

---

## 后续阶段（第 5-12 步）

相同的测试驱动开发模式将继续用于：

- **阶段 5（第 5 步）：** 完整教学循环 — 添加 history_check、knowledge_retrieval、restate_check、followup、evaluate、summarize 节点；更新路由器以包含完整的条件边
- **阶段 6（第 6 步）：** 直接问答 + 恢复 — 添加 rag_first、evidence_gate、answer_policy、recovery 节点；添加安全边界模块
- **阶段 7（第 7 步）：** 剩余 Harness + RAG — 添加 tool_registry、memory manager、LLM 意图路由、RAG 协调器、重排序器、嵌入、检索策略
- **阶段 8（第 8 步）：** 完整基础设施 — 添加 eval_store、knowledge_store、外部服务、文件提取、Alembic 迁移
- **阶段 9（第 9 步）：** API 层 — 添加所有 API 端点及数据模型
- **阶段 10（第 10 步）：** 多智能体 SubGraph — 添加 MultiAgentState、teaching_graph、eval_graph、retrieval_graph、orchestrator_graph、multi_graph
- **阶段 11（第 11 步）：** 测试 + 用户界面 + 后台任务 — 添加 conftest（含 FakeRAGStore）、Chainlit 集成、Vue 项目初始化、Celery 后台任务
- **阶段 12（第 12 步）：** 收尾 + 文档 — README、依赖验证脚本、pyproject.toml 最终定稿

每个阶段遵循与阶段 1-4 完全相同的测试驱动开发模式：编写失败测试 → 验证失败 → 编写实现 → 验证通过 → 提交。
