# StudyAgent Harness — 项目基础知识（CLAUDE.md）

> 本文件是 Claude **每会话自动加载**的项目入口。定位：**薄、准、指向明确**——只放会话首要地标 + 时效性提醒 + 载体路标。
> 详细事实不在本文件重复，去各自载体查（见末尾「细节去哪查」）。
> 维护原则：代码/架构变更后同步更新「时效性地标」；事实性细节改对应载体，不堆进这里。

## 项目是什么

基于苏格拉底 / 费曼教学法的多 Agent 学习框架。不灌输答案，通过「诊断 → 讲解 → 复述 → 追问」交互循环引导学习者主动构建理解，过程中持续评估掌握度、维护知识图谱画像。

- 技术栈：FastAPI + Pydantic V2 / 自研事件驱动协作环 / SQLAlchemy 2.0 async / pgvector / langchain-openai / ragas 评估
- 包管理：**uv**，Python ≥ 3.11（[pyproject.toml](pyproject.toml)）
- 前端：React 18 + Vite（`web/`）

## 单栈方向（最重要的一条地标）

**项目已完成单栈化：新栈 `app/` 是唯一主体。所有新功能一律在新栈落地。**

| | 新栈（`app/`，唯一主体） |
|---|---|
| 范式 | 事件驱动 5-Agent 协作环 |
| LLM | 调真实 LLM，有真实教学能力 |
| 状态 | **活跃开发** |


## 四层架构（单向依赖，严禁反向）

```
API 层 (app/api/) → 编排层 (app/orchestration/) → Harness 层 (app/harness/) → 基础设施层 (app/infrastructure/)
```

核心范式：**事件驱动多 Agent 协作环**——Agent 之间不互调，只通过 `EventBus` 收发带「所有权白名单」校验的 `Event`；单线程优先级队列 `run_collab_loop` 驱动；`Orchestrator` 用回合屏障 + 规则 DSL（`orchestrator_rules.yaml`）做路由裁决。

## 关键目录地图（新栈 `app/`）

| 目录 | 职责 |
|---|---|
| [app/agents/](app/agents/) | 5 Agent（tutor/critic/retriever/conductor/curator）+ `AgentBase` / `CuratorBase` |
| [app/harness/](app/harness/) | 业务核心契约：`events` / `eventbus` / `workspace_state` + `orchestrator`（路由）+ `teaching_policy`（教学模式状态机）+ `mastery_graph` / `user_profile`（画像记忆）+ `enums` + `observability` |
| [app/orchestration/](app/orchestration/) | `collab_loop`（事件循环）+ `graph`（LangGraph 骨架）+ `assembly`（端到端装配线）+ `orchestrator_rules.yaml`（规则 DSL，**运行时配置**） |
| [app/infrastructure/](app/infrastructure/) | `llm`（LLMService + FakeLLM 测试替身）+ `rag`（多 Provider 协调器）+ `storage`（各 Store） |
| [app/eval/](app/eval/) | 旁路评估（component / system / collaboration / ab + judge + kernel），不在请求热路径 |
| [app/specs/](app/specs/) | 渐进式 Prompt 体系：`.md`（开发规范）+ `.prompt.md`（运行时），**成对修改** |
| [app/api/](app/api/) | FastAPI 端点（auth / chat / chat_stream / eval / knowledge / sessions / profile，挂在 `/api` 前缀） |
| [app/models/](app/models/) | `tables.py`（SQLAlchemy 表）+ `schemas.py`（Pydantic） |
| [app/core/](app/core/) | `config` / `database` / `prompts` |

## 五 Agent 职能正交（只点名，细节见 README）

Tutor=**生成层**（教学主体，只生成不评判）·Critic=**语义评估层**·Retriever=**机械检索层**·Conductor=**LLM 路由兜底**·Curator=**结构层**（掌握度图谱维护，只判结构不生成，不调 LLM）。
边界铁律：每个 Agent 只发自己领域的事件，越权由 EventBus 在 `publish` 时拦截抛 `EmitViolationError`。

## 运行 / 测试（最低必要，完整版见 README）

```bash
uv sync                                    # 装依赖（按需 --extra rag/eval/worker/ui）
cp .env.example .env                       # 填 OPENAI_API_KEY
uv run alembic upgrade head                # 迁移
set -a && source .env && set +a            # 导出环境变量
uv run uvicorn app.main:app --reload       # 启动，默认 http://127.0.0.1:8000
uv run pytest tests/ -v                    # 测试（默认排除 integration）
uv run pytest -m integration               # 集成测试，需 Docker PG + OpenAI key
```

## 时效性地标（易踩坑，随代码变更同步）

- **桩端点**：`/api/chat/multi`、`/api/eval/{id}/rerun` 未实现真实逻辑。
- **测试默认 deselect integration**：[pyproject.toml](pyproject.toml) 里 `addopts = "-m 'not integration'"`。
- **惰性重依赖**：pdfplumber / PyPDF2 / python-docx / pytesseract / Pillow 不在任何 extra 里声明，缺失时对应解析路径降级，不阻断启动。
- **掌握度持久化双套**：`MasteryGraphStore`（aiosqlite，旧）/ `SQLAlchemyMasteryStore`（PG/SQLite 双模）。**生产 chat 流程用后者**。
- **`app/specs/event_map.yaml` 无运行时消费者**：实际事件订阅是各 Agent 类的 `subscriptions` + `assembly.py` 装配；它是规范文档产物，不是运行时配置源。真正驱动运行时决策的是 `orchestrator_rules.yaml`。

## 细节去哪查（不在本文件重复）

| 想知道 | 去哪 |
|---|---|
| 架构全貌 / Agent 细节 / 协作环机制 / API 端点表 / 数据模型 / 枚举 / 测试结构 / 已知限制 | [README.md](README.md) |
| 资产清单（产物归属 + 位置 + 三色血缘） | [docs/asset-inventory.md](docs/asset-inventory.md) |
| 工作方式规范（语言 / 命令执行 / README 维护 / 模块三层规划 / 方案呈现 / 学习文档落地） | [.claude/rules/](.claude/rules/) |
| 多 Agent 架构梳理（七角色 / 事件总线 / 回合屏障 / Curator vs Critic 边界 / 完整回合时序） | [Learned/2026-07-14-StudyAgent多Agent协作架构.md](Learned/2026-07-14-StudyAgent多Agent协作架构.md) |
| 学习沉淀（QA 式） | [Learned/](Learned/) |
| 设计 spec / 规划文档 | [docs/designs/](docs/designs/)、[docs/superpowers/](docs/superpowers/) |
