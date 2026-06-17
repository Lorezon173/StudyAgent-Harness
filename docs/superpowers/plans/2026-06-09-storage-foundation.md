# 子项目① 存储底座：PostgreSQL + pgvector + 会话持久化 · 三层实施规划

> 创建日期：2026-06-09
> 类型：三层详细规划（文字描述，**不含代码**；经用户确认后方可进入编码）
> 对应 spec：[`docs/designs/2026-06-09-storage-foundation-design.md`](../../designs/2026-06-09-storage-foundation-design.md)
> raw 材料：[`superpowers/2026-06-09-redesign-persistence-raw.md`](../../../superpowers/2026-06-09-redesign-persistence-raw.md)
> 规划体例：遵循项目 `.claude/rules/dev-standards.md`「模块开发规划三层 + 第 3 层禁止给代码」硬约束。

---

## 源码核验记录（规划前已逐条核对，全部命中）

写本规划前已读真实源码并核对 spec §1.2 全部 file:line 断言，**均准确**；此外新查得三条降风险事实：

| 核验项 | 结论 | 对规划的意义 |
|---|---|---|
| `database.py:9` engine 硬编码 sqlite | 属实 | §3.1 改读 `settings.database_url` |
| `database.py:13` `get_db()` 定义 | 属实，且**全项目零调用** | 本子项目是其首个消费者，注入无存量冲突 |
| `chat.py:15-31` 新栈只调 `run_new_agent_session`、不碰 Store | 属实 | §3.3 接线落库 |
| `config.py:8` `database_url` 字段 | **已存在**（默认 sqlite） | 无需新增配置项 |
| `tables.py:14-20` `SessionTable` 有 `created_at`/`updated_at` | 属实，`updated_at` 带 `onupdate=func.now()` | 仅新增 `title`；R1 仍需显式刷新 |
| `session_store.py:23` `save(session_id, state, user_id=None)` | 属实，无 `title` 形参；line 36 内部 `await self.db.commit()` | C1 补 `title`、C3 移除内部 commit |
| `session_store.py:56-65` `list_by_user` 双分支字段不一致 | 属实（db 分支无 user_id、无 title） | C2 统一两分支 |
| **`SessionStore.save()` 当前调用方** | **零**（grep 仅命中其他 store 的 save_*） | C3 移除内部 commit **无回归面** |
| **`eval_store.py:1` `import SessionStore`** | **死导入**（全文件未使用） | C3 改动不波及 EvalStore |
| `alembic.ini` / `alembic/` 目录 | **不存在** | §3.6 首次初始化 alembic 环境 |
| `docker-compose.yml` | **不存在** | §3.6 新建 |
| `chat_stream.py:17,21` 也调 `run_new_agent_session` | 属实 | N2：本子项目**不**在 stream 落库，仅标注留给② |
| `tests/conftest.py` | 仅 state/LLM-mock fixture，**无 async db fixture** | N3：需新增 db fixture |
| `tests/api/` | 仅空 `__init__.py` | 集成测试落于此 |
| `main.py:19` lifespan 无条件 `await init_db()` | 属实 | PG 模式下 `init_db` 只跑 CREATE EXTENSION，不与 alembic 冲突 |
| **全项目 async 测试范式（review 补查）** | **清一色 `asyncio.run(_test())` / `run_until_complete`，零 `@pytest.mark.asyncio`**；`pyproject`/`conftest` **无 `asyncio_mode` 配置**（pytest-asyncio 默认 strict） | **P1：G 子模块 fixture/测试沿用 `asyncio.run` 范式，不动全局 asyncio_mode**（用户已定）。否则裸写 `async def test_*` 会被 strict 模式**静默 skip → 假绿** |
| **`tests/unit/api/test_api.py`（review 补查，计划原漏列）** | 存在；`TestClient(app)` 直跑全 app，含 `test_sessions_empty`（GET /api/sessions 无 user_id → 200）、`test_auth_register_and_login` 等 | **P2：E 子模块改 `sessions`/`chat` 注入 `Depends(get_db)` 会冲击此文件**，须保证响应模型变更不破坏既有断言、且集成测试用 override 不污染真实库 |

---

## 第 1 层：模块总览

### 1.1 目标边界

**做什么**：把「双模式已写好但没接上」的持久化层真正接通——
- 让 `engine` 读 `settings.database_url`，支持 SQLite/PG 双模式经 `.env` 切换；
- 让 API 层经 `Depends(get_db)` 把真实 `AsyncSession` 注入 Store（首个消费者）；
- 新建 `messages` 表 + `MessageStore`，让新栈 `/api/chat` 每轮把会话与对话历史落库；
- 给 `SessionTable` 加 `title`，`SessionStore` 补 title 契约、修 updated_at 刷新、收口 commit；
- 新增「列会话 / 取历史」两个 API；
- 引入 PG 驱动 + pgvector 依赖、Docker pgvector、Alembic 初始化迁移、PG 装 vector 扩展。

**不做什么**（边界外，留给后续子项目）：
- 掌握度/agent 内部状态（WorkspaceState/EventStore）落库、turn_count 语义修复 → ②
- 知识库文件向量化、`KnowledgeStore` 改造、pgvector 向量表与检索 → ③
- 前端多会话 UI → ④
- **流式接口 `chat_stream.py` 的落库** → 本子项目只在 `chat.py` 落库（覆盖当前真实流量，前端走 `/api/chat`）；②切 SSE 后须迁移，此处显式标注防遗漏。

### 1.2 技术选型

| 选型 | 决策 | 理由 |
|---|---|---|
| PG async 驱动 | **asyncpg** | async 原生、性能好 |
| 对话历史存储 | **独立 `messages` 表**（非塞 state_json） | 按消息粒度查询、符合薄壳规范 |
| 会话标题 | **`SessionTable.title` 冗余字段** | 列会话高频，避免 N+1 |
| PG schema 真相源 | **Alembic 唯一**（M1） | 避免 create_all 与 alembic 两套真相源漂移 |
| 写库失败容错 | **rollback + 仅记日志，仍返回 reply** | 教学回复是主路径，持久化是旁路 |
| 历史排序键 | **`id` 升序**（R2，非 created_at） | SQLite `CURRENT_TIMESTAMP` 秒级精度不可靠 |
| 落库事务 | **save+2×add 共用一次 commit**（C3） | 原子、消除半落库与 turn_index 错位（R3） |

### 1.3 依赖关系与架构衔接

严格遵守四层单向依赖 **API → Orchestration → Harness → Infrastructure**：
- `MessageStore`/`SessionStore` 属 **Infrastructure**；
- `chat.py`/`sessions.py` 属 **API**，经 FastAPI `Depends(get_db)` 注入 `AsyncSession`——即 `database.py:13` 已设计好但无人用的注入点；
- 落库代码在 `run_new_agent_session`（同步、经 `asyncio.to_thread`）`await` 之后、回到主协程执行，`AsyncSession` 绑定主事件循环，安全；
- 不反向依赖、不在节点/API 内写业务逻辑。

### 1.4 与现有架构的衔接点清单

| 衔接点 | 现状 | 本子项目动作 |
|---|---|---|
| `core/database.py` engine | 硬编码 sqlite | 改读 config + 方言分流 |
| `core/database.py` `init_db` | 无条件 create_all | 方言分流：sqlite create_all / PG 仅 CREATE EXTENSION |
| `api/chat.py` | 无 db 注入 | 加 `Depends(get_db)` + 落库三步 |
| `api/sessions.py` | 模块级 `_store`、内存分支 | 改 `Depends(get_db)`、改造列会话、新增取历史 |
| `models/tables.py` | 无 messages 表、无 title | 新增 `MessageTable`、`SessionTable.title` |
| `models/schemas.py` | 无会话/消息响应模型 | 新增 `SessionSummary`、`MessageItem` |
| `pyproject.toml` | 无 asyncpg/pgvector | 加依赖 |
| 仓库根 | 无 docker-compose/alembic | 新建 |

---

## 第 2 层：子模块概述

本子项目拆为 7 个子模块，按依赖顺序排列（前者为后者前提）。

### 子模块 A：配置与连接层（`core/database.py`）

- **职责**：engine 读 `settings.database_url`；按方言（sqlite / postgresql）分流连接参数与建表职责。
- **接口契约**：`get_db()`、`async_session` 对外签名与行为**不变**（已有消费者为零，但保持稳定）；新增方言判断逻辑内置于模块加载期。
- **数据流**：模块导入时构造 engine → 启动期 `init_db()` 按方言决定 create_all（sqlite）或仅 CREATE EXTENSION（PG）。
- **状态管理**：engine、async_session 为模块级单例（与现状一致）。
- **错误处理**：PG 连接失败由 SQLAlchemy 抛出，启动期 fail-fast（符合预期，不吞）；CREATE EXTENSION 需 PG 超级权限，权限不足时抛错提示。

### 子模块 B：数据模型（`models/tables.py`）

- **职责**：新增 `MessageTable`；给 `SessionTable` 加 `title`。
- **接口契约**：ORM 模型字段即契约（见第 3 层字段表）；`messages.session_id` 外键指向 `sessions.id`。
- **数据流**：被 Store 读写、被 Alembic 迁移与 sqlite create_all 建表。
- **状态管理**：无（纯声明）。
- **错误处理**：无（声明式）。

### 子模块 C：MessageStore（`storage/message_store.py`，新建）

- **职责**：消息行的双模式（db / 内存）增查。
- **接口契约**：`__init__(db=None)`；`add(session_id, role, content, turn_index) -> int`（**不自行 commit**，db 模式 flush 拿 id）；`list_by_session(session_id) -> list[dict]`（**按 id 升序**）。
- **数据流**：被 `chat.py` 写、被 `sessions.py` 取历史读。
- **状态管理**：db 模式无本地态；内存模式持 `_memory` 列表 + `_next_id`。
- **错误处理**：自身不捕获，异常上抛给调用方统一 rollback（C3）。

### 子模块 D：SessionStore 改造（`storage/session_store.py`）

- **职责**：在现有双模式基础上补 title 契约、修 updated_at 刷新、收口 commit、统一 list_by_user 双分支。
- **接口契约变更**：
  - `save(session_id, state, user_id=None, title=None)`——**加 title 形参**；
  - upsert 语义：INSERT 写 title，UPDATE **不覆盖** title；
  - **移除内部 `await self.db.commit()`**（C3）；
  - UPDATE 分支**显式** `row.updated_at = func.now()`（R1）；
  - `list_by_user` 两分支统一返回 `{session_id, title, updated_at}`（C2）。
- **数据流**：被 `chat.py` 写、被 `sessions.py` 列会话读。
- **状态管理**：db 模式无本地态；内存模式 `_memory` dict（需补 title、近似 updated_at）。
- **错误处理**：不自行 commit/rollback，交调用方（C3）。
- **回归面**：`save()` 当前零调用、`eval_store.py` 死导入 → 改动安全。

### 子模块 E：API 接线（`api/chat.py`、`api/sessions.py`、`models/schemas.py`）

- **职责**：chat 落库三步原子提交 + 容错；sessions 改造列会话、新增取历史；新增两个响应模型。
- **接口契约**：
  - `POST /api/chat`：函数签名加 `db: AsyncSession = Depends(get_db)`，响应模型**不变**；
  - `GET /api/sessions?user_id=` → `list[SessionSummary]`，按 updated_at 降序；
  - `GET /api/sessions/{id}/messages` → `list[MessageItem]`；
  - 新增 `SessionSummary{session_id,title,updated_at}`、`MessageItem{role,content,created_at}`。
- **数据流**：见 spec §4 数据流图。
- **状态管理**：Store 改为**请求内构造**（不再模块级 `_store`）。
- **错误处理**：chat 落库整体 try/except，失败 `await db.rollback()` + 仅记 observability 日志，仍正常返回 reply。

### 子模块 F：基建（依赖 / Docker / Alembic / .env）

- **职责**：`pyproject.toml` 加 asyncpg+pgvector；新建 `docker-compose.yml`（pgvector/pgvector:pg16）；初始化 alembic 环境 + 生成首迁移（建全表含 messages、title）；`.env.example` 补 PG 连接串示例（注释形式，默认仍 sqlite）。
- **接口契约**：alembic 首迁移须与 ORM 模型一致；PG 启动前置＝`alembic upgrade head` 再起服务。
- **错误处理**：迁移失败 fail-fast；CREATE EXTENSION 需权限。

### 子模块 G：测试（`tests/conftest.py`、`tests/api/`、`tests/infrastructure/`）

- **职责**：新增 async db fixture（临时 SQLite）；MessageStore 双模式单测；chat 落库集成测试；列会话/取历史 API 测试；容错测试；updated_at 刷新测试（R1）。
- **错误处理约定**：pytest 必须 `< /dev/null`（已知 stdin 挂起问题）。

### 子模块依赖序

```
A(连接层) ─┬─> B(模型) ─┬─> C(MessageStore) ─┐
           │            └─> D(SessionStore) ─┼─> E(API 接线) ─> G(测试)
           └─────────────────────────────────┘
F(基建) 与 A/B 并行，但 alembic 首迁移须在 B 完成后生成
```

---

## 第 3 层：子模块详细实施计划（文字描述，不给代码）

> 体例：每个子模块说明「要改/建哪些函数、各自作用与输入输出、要完成哪些功能、字段与变量怎么设计、关键数据结构」。代码留待规划确认后编写。

### A. 配置与连接层 `core/database.py`

**要完成的功能**

1. **engine 从硬编码改为读配置**：导入 `from app.core.config import settings`，engine 构造时用 `settings.database_url` 取代字面量 `"sqlite+aiosqlite:///..."`。
2. **方言分流连接参数**：新增一个模块级辅助逻辑（可为一个内部函数 `_make_engine(url)`），判断 url 前缀：
   - 以 `sqlite` 开头：用最简参数构造（保持现状 `echo=False`，不传连接池参数——SQLite 不需要）。
   - 以 `postgresql` 开头：附加连接池参数 `pool_size`、`max_overflow`、`pool_pre_ping=True`（防长连接断连）。具体数值取保守默认（如 pool_size=5、max_overflow=10），写成模块内常量便于调整。
   - 其他前缀：不特殊处理，按最简参数构造（兜底）。
3. **`init_db()` 按方言分流建表职责**（M1 核心）：
   - 取当前 engine 的方言名（`engine.dialect.name`，sqlite 为 `"sqlite"`，PG 为 `"postgresql"`）。
   - **sqlite 分支**：保留现状 `await conn.run_sync(Base.metadata.create_all)`（开发/测试开箱即用）。
   - **postgresql 分支**：**不** create_all；改为执行一条原生 SQL `CREATE EXTENSION IF NOT EXISTS vector`（为③铺路）。建表交给 alembic。
   - 注意 `Base.metadata.create_all` 需要 `tables.py` 的模型已被 import 注册到 `Base.metadata`——确认 `init_db` 调用前模型模块已加载（现状经 main.py import 链已满足；若分流后仅 sqlite 用 create_all，仍需保证 import）。

**函数清单**

| 函数 | 作用 | 输入 | 输出 |
|---|---|---|---|
| `_make_engine(url)`（新增内部） | 按方言构造 engine | `url: str` | `AsyncEngine` |
| `init_db()`（改） | 按方言建表/装扩展 | 无 | `None`（副作用：建表或装扩展） |
| `get_db()`（不变） | yield 一个 AsyncSession | 无 | `AsyncGenerator[AsyncSession]` |

**变量/常量设计**：`_PG_POOL_SIZE`、`_PG_MAX_OVERFLOW` 模块级常量；`engine`、`async_session` 仍模块级单例。

**关键数据结构**：无新增；沿用 SQLAlchemy `AsyncEngine` / `async_sessionmaker`。

---

### B. 数据模型 `models/tables.py`

**要完成的功能**

1. **新增 `MessageTable`**（表名 `messages`）：
   - `id`：Integer 主键 autoincrement——**历史排序主键**（R2，排序用它非 created_at）。
   - `session_id`：String(64)，外键 `ForeignKey("sessions.id")`，加 `index=True`（按会话查历史是主路径）。
   - `role`：String(16)。本子项目 writer 仅产 `user`/`assistant`；`error` 为前端异常消息预留、本子项目不写（值域注释说明，落地若不需要可收窄为二者）。
   - `content`：Text。
   - `turn_index`：Integer（第几轮，配合②修复后的真实回合数）。
   - `created_at`：DateTime，`server_default=func.now()`——仅作展示/审计，**不**用于排序（R2）。
2. **改 `SessionTable`**：新增 `title` 字段，String(128)，`default=""`。`created_at`/`updated_at` 已存在，不动声明（但 R1 的刷新在 Store 层做）。

**字段设计要点**

- messages 的 `id` 用 autoincrement 整数而非 UUID——因为要靠它单调排序，且 SQLite/PG 都原生支持。
- `session_id` 长度 64 与 `SessionTable.id` 一致。
- 外键关系不强制配 `relationship()`（本子项目 Store 用显式 select，不依赖 ORM 关系导航；保持薄壳、避免 N+1 隐患）。

**关键数据结构**：两张表的 ORM 声明；无 Python 侧复合结构。

---

### C. MessageStore `storage/message_store.py`（新建，对齐 UserStore/SessionStore 双模式写法）

**要完成的功能**：消息行的增（落库或入内存）与查（按会话取历史）。

**函数清单**

| 函数 | 作用 | 输入 | 输出 |
|---|---|---|---|
| `__init__(db=None)` | 双模式选择；db 为空走内存 | `db: AsyncSession \| None` | — |
| `add(session_id, role, content, turn_index)` | 插一行消息，返回自增 id | 4 个字段 | `int`（新行 id） |
| `list_by_session(session_id)` | 按 id 升序取该会话全部消息 | `session_id: str` | `list[dict]` |

**`add` 实现要点**

- **db 模式**：构造 `MessageTable` 行 → `self.db.add(row)` → `await self.db.flush()`（**用 flush 而非 commit**，C3：commit 收口到调用方；flush 已能拿到自增 `row.id`）→ 返回 `row.id`。
- **内存模式**：把 `{id, session_id, role, content, turn_index, created_at}` 追加进 `self._memory` 列表，`id` 取 `self._next_id` 并自增；`created_at` 用 `datetime.utcnow()` 近似；返回该 id。

**`list_by_session` 实现要点**

- **db 模式**：`select(MessageTable).where(session_id==...).order_by(MessageTable.id.asc())`（**按 id 升序**，R2）；映射为 `[{role, content, turn_index, created_at}]`。
- **内存模式**：过滤 `self._memory` 中 `session_id` 匹配项，按 `id` 升序，映射同字段。

**字段/变量设计**

- `self.db`：注入的 session 或 None。
- `self._memory: list[dict]`：内存模式存储（**用 list 不用 dict**，因要保留插入序且 id 自增）。
- `self._next_id: int`：内存模式自增计数器，初值 1。

**关键数据结构**：返回的 dict 形状统一为 `{role, content, turn_index, created_at}`（list_by_session）；`add` 仅返回 int id。两模式形状必须一致（测试要交叉验证）。

**错误处理**：`add`/`list` 自身不 try/except；db 异常上抛，由 `chat.py` 调用方统一 rollback（C3）。

---

### D. SessionStore 改造 `storage/session_store.py`

**要完成的功能**：在现有双模式上落实 C1（title 契约）、C2（list_by_user 双分支统一）、C3（移除内部 commit）、R1（显式刷新 updated_at）。

**函数级改动**

1. **`save(session_id, state, user_id=None, title=None)`**（C1 加 title 形参）：
   - **db 模式 INSERT 分支**（`session_store.py:30` 现状，行不存在时）：构造 `SessionTable` 时**写入 title**（None 时落 `""` 或不传走 default）。
   - **db 模式 UPDATE 分支**（行已存在）：
     - 维持 `row.state_json = json.dumps(state)`；`user_id is not None` 时更新 user_id；
     - **不覆盖 title**（实现 §3.4「仅首轮写、后续不覆盖」）——即 UPDATE 分支完全不碰 `row.title`；
     - **R1：显式 `row.updated_at = func.now()`**——因 state_json 恒 `{}`、user_id 不变时该行可能无净变化，SQLAlchemy 不 emit UPDATE，`onupdate` 不触发；显式赋值强制刷新。
   - **C3：移除分支末尾的 `await self.db.commit()`**（现 `session_store.py:36`）——改由调用方统一提交。
   - **内存模式**：`_memory[session_id]` 字典补 `title` 字段；并补一个近似时间戳（见下变量设计），以支撑 list_by_user 排序。
2. **`list_by_user(user_id)`**（C2 统一双分支）：
   - **db 分支**（现 line 57-61 只返回 `{session_id, state_json}`）：改为 `select(...).order_by(SessionTable.updated_at.desc())`，映射 `[{session_id, title, updated_at}]`。
   - **内存分支**（现 line 62-65）：改为同样返回 `[{session_id, title, updated_at}]`，按近似 updated_at 降序。
   - 两分支字段对齐：`{session_id, title, updated_at}`。
3. **`get`/`delete` 不在本子项目改动范围**（保持现状；注意 `delete` 仍自带 commit，与 save 不同——本子项目不动它，因无 chat 路径调用 delete）。

**字段/变量设计**

- 内存模式 `_memory[session_id]` 字典扩为 `{session_id, user_id, state_json, title, _updated_seq}`。
- `_updated_seq`：内存模式近似时间戳。设一个实例级单调计数器 `self._seq`（初值 0），每次 save 自增并写入该会话的 `_updated_seq`，list_by_user 按它降序。**声明**：内存模式不保证跨重启时序，仅供测试（与 spec §3.5 一致）。

**关键数据结构**：内存 dict 形状变更如上；db 模式无本地结构。

**回归确认**：`save()` 当前零调用、`eval_store.py` 死导入 → 移除内部 commit 不破坏任何现有路径。新的 commit 责任落在 `chat.py`（子模块 E）。

---

### E. API 接线（`api/chat.py`、`api/sessions.py`、`models/schemas.py`）

#### E.1 `models/schemas.py` 新增响应模型

| 模型 | 字段 | 用途 |
|---|---|---|
| `SessionSummary` | `session_id: str`、`title: str`、`updated_at: datetime \| None` | 列会话响应 |
| `MessageItem` | `role: str`、`content: str`、`created_at: datetime \| None` | 取历史响应 |

- `updated_at`/`created_at` 用 `datetime \| None`（内存模式可能无真实时间戳）；Pydantic v2 默认能序列化 datetime。
- 保留现有 `SessionResponse`（`get_session` 单会话详情仍用它，不动）。

#### E.2 `api/chat.py` 落库接线

**函数级改动**：`chat(req)` 签名加 `db: AsyncSession = Depends(get_db)`（import `get_db`、`AsyncSession`、`Depends`）。

**新栈分支落库流程**（在 `await asyncio.to_thread(run_new_agent_session, ...)` 拿到 `result` **之后**、`return ChatResponse` **之前**插入）：

1. **算 turn_index**：用 `MessageStore(db).list_by_session(req.session_id)` 取已有消息数，`len // 2` 即本轮序号；**在两条 add 之前算一次、两条共用**（R3 由 C3 原子性消除错位）。注：这是每轮一次按 session_id 过滤的额外 select（P4），量级可忽略，不做缓存优化。
2. **构造 title**：仅首轮需要——`req.message.strip()[:24]`，空则 `"新会话"`。是否首轮可由「已有消息数 == 0」判断；非首轮传 `title=None`（save 的 UPDATE 分支本就不覆盖 title，传不传都安全，但传 None 更明确）。
3. **save 会话**：`await SessionStore(db).save(req.session_id, {}, user_id, title=...)`（state 暂存空 dict）。`user_id` 取 `req.user_id`（int 或 None）。
4. **add 两条消息**：`await MessageStore(db).add(session_id, "user", req.message, turn_index)`；再 `add(session_id, "assistant", result.reply, turn_index)`。
5. **统一提交**：`await db.commit()`（C3：上述 save+2×add 均不自行 commit，三步共享同一 session 一次提交）。

**容错包裹**（§3.3）：步骤 1-5 整体置于 `try/except Exception`：
- except 内 `await db.rollback()`；
- 经 observability 记一条错误日志（**仅记日志、不抛**，import 方式参考 assembly.py:93 的延迟 import `get_observability()`，避免模块加载期初始化）；
- 无论落库成败，**照常 `return ChatResponse(...)`**（教学回复是主路径）。

**注意**：`db` 由 `Depends(get_db)` 提供，`get_db` 的 `async with async_session()` 会在请求结束自动 close；本处只管 commit/rollback，不手动 close。

**函数清单（chat.py）**

| 函数 | 改动 | 输入新增 | 输出 |
|---|---|---|---|
| `chat(req)` | 加 db 注入 + 落库块 + 容错 | `db: AsyncSession = Depends(get_db)` | `ChatResponse`（不变） |

#### E.3 `api/sessions.py` 改造列会话 + 新增取历史

**改动**：
- **移除模块级 `_store = SessionStore()`**（line 7）——改为各端点内 `SessionStore(db)` / `MessageStore(db)`。
- **`get_session`**（line 10）：加 `db: AsyncSession = Depends(get_db)`，内部 `SessionStore(db).get(...)`；响应仍 `SessionResponse`（不变）。
- **`list_sessions`**（line 23）：加 `db` 注入；`response_model=list[SessionSummary]`；`user_id` 为空时返回 `[]`，否则 `SessionStore(db).list_by_user(user_id)` 映射为 `SessionSummary`。
- **新增 `get_session_messages`**：路由 `GET /{session_id}/messages`，`response_model=list[MessageItem]`，`db` 注入，内部 `MessageStore(db).list_by_session(session_id)` 映射为 `MessageItem`。

**函数清单（sessions.py）**

| 函数 | 改动 | 输入 | 输出 |
|---|---|---|---|
| `get_session(session_id, db)` | 加 db 注入 | path + db | `SessionResponse` |
| `list_sessions(user_id, db)` | 加 db + 改响应模型 | query + db | `list[SessionSummary]` |
| `get_session_messages(session_id, db)`（新增） | 取历史 | path + db | `list[MessageItem]` |

**路由顺序注意**：`/{session_id}` 与 `/{session_id}/messages` 不冲突（后者路径更长，FastAPI 精确匹配）；但确保 `/{session_id}` 不会贪婪吞掉 `/messages`——FastAPI 按声明顺序与路径段数匹配，两者段数不同，安全。

---

### F. 基建（依赖 / Docker / Alembic / .env）

#### F.1 `pyproject.toml` 依赖

- 在 `dependencies` 数组加 `"asyncpg>=0.30.0"`（运行时 async 驱动）、`"pgvector>=0.3.0"`（Python 绑定，供③用）。
- **同步 PG 驱动 `"psycopg[binary]>=3.2.0"`**——因 alembic 迁移走同步 engine（待确认 #1 已定），而当前 pyproject **未装任何同步 PG 驱动**（已 grep 确认）；不补则 PG 模式 `alembic upgrade` 报缺驱动。SQLite 迁移用内置 `sqlite3`，无需额外。
- `alembic`、`aiosqlite` 已在 dependencies，无需加。
- 加完用 `uv sync` 或 `pip install -e .` 安装（命令在执行计划阶段定，禁用 sleep、轮询确认）。

#### F.2 `docker-compose.yml`（仓库根新建）

- service `db`：镜像 `pgvector/pgvector:pg16`。
- 环境变量：`POSTGRES_DB`、`POSTGRES_USER`、`POSTGRES_PASSWORD`（取项目默认，如 studyagent / studyagent / 一个开发密码）。
- 端口映射 `5432:5432`。
- 数据卷 `pgdata:/var/lib/postgresql/data`（持久化）。
- 顶层 `volumes: pgdata:`。

#### F.3 Alembic 初始化（M1：PG 唯一建表源）

- 初始化环境：`alembic init alembic`（生成 `alembic.ini` + `alembic/` 目录）。
- 配置 `alembic/env.py`：
  - `target_metadata = Base.metadata`（import `app.core.database.Base` 与 `app.models.tables` 以注册全部表）；
  - sqlalchemy url 从 `settings.database_url` 读（不写死在 ini）；
  - 因项目运行时用 async engine，但**迁移走同步 engine**（待确认事项 #1 已定同步）：env.py 内用 `settings.database_url` 构造一个**同步** engine（把 `postgresql+asyncpg` 换成 `postgresql+psycopg`/`psycopg2`，或 sqlite 去掉 aiosqlite）跑 `run_migrations_online`。理由：迁移是一次性启动期操作、不在请求热路径，同步模板避开 async 的 greenlet/autogenerate 坑，且与运行时 async engine 互不影响。
- 生成首迁移：`alembic revision --autogenerate -m "init schema with messages and session title"`，覆盖全部表（users/sessions[含 title]/messages/knowledge/evals）。
- **校验**：autogenerate 后人工核对迁移文件确实含 `messages` 表与 `sessions.title`，再 `alembic upgrade head`。

#### F.4 `.env.example`

- 在现有 `DATABASE_URL=sqlite+...`（line 14）下方，补一行**注释形式**的 PG 示例：
  `# DATABASE_URL=postgresql+asyncpg://studyagent:password@localhost:5432/studyagent`
- 默认仍 sqlite，保持开箱即用。

#### F.5 启动顺序文档（写入 README，见子模块 G 后的收尾）

- **SQLite**：直接起服务，`init_db` 的 create_all 自动建表。
- **PG**：① `docker compose up -d db` → ② `alembic upgrade head` 建表 → ③ 起 uvicorn（lifespan 的 `init_db` 只跑 CREATE EXTENSION）。

---

### G. 测试（`tests/conftest.py`、`tests/infrastructure/`、`tests/api/`）

> 全程 pytest 命令必须 `< /dev/null`（已知 stdin 挂起）。

#### G.1 conftest 新增 async db 基建（N3 前置基建 · P1：对齐项目 asyncio.run 范式）

- **范式定调（P1，用户已确认）**：全项目 async 测试均为 `asyncio.run(_test())` / `run_until_complete`，**无一例** `@pytest.mark.asyncio`，且无 `asyncio_mode` 配置。故本子项目测试**沿用同款范式**：把每条 async 测试逻辑包成内部 `async def _test()`，末尾 `asyncio.run(_test())` 调用。**不引入** `@pytest.mark.asyncio`、**不改** pyproject 的 `asyncio_mode`（避免波及存量 30+ 测试文件 + 防 strict 模式静默 skip 假绿）。
- 因为不走 pytest-asyncio 的 async fixture，db 基建**不做成 yield-async-fixture**，而是提供一个**普通同步 helper**（如 `make_sqlite_engine(tmp_path) -> (engine, async_session_maker)`），在各 `_test()` 内部 `async with` 取 session：
  - 用**临时文件 SQLite**（`sqlite+aiosqlite:///{tmp_path}/test.db`），**不用裸 `:memory:`**（`:memory:` 每连接独立，建表连接与查询连接不共享 → 查不到表）；
  - helper 内 `run_sync(Base.metadata.create_all)` 建表；
  - 测试结束 `await engine.dispose()`。
- 该 helper 可放 `tests/conftest.py`（作普通函数 import）或 `tests/infrastructure/_db.py` 工具模块。

#### G.2 测试清单（每条对应 spec §5 / 验收 §6）

| 测试 | 落点 | 验证 | 对应验收 |
|---|---|---|---|
| MessageStore 内存模式 add/list | `tests/infrastructure/test_message_store.py` | add 返回递增 id；list 按 id 升序、字段形状 | §6.5 |
| MessageStore SQLite 模式 add/list | 同上 | db 模式 flush 拿 id、不 commit 也能 list（同 session 内）；按 id 升序 | §6.5 |
| SessionStore title INSERT/UPDATE | `tests/infrastructure/test_session_store.py` | 首轮写 title；二轮 save 不覆盖 title | §6.3 |
| **updated_at 刷新（R1）** | 同上 | 同会话连发 2 次 save（state 恒 `{}`），断言第二次后 updated_at 推进 | §6.4 |
| list_by_user 双分支字段一致（C2） | 同上 | 内存与 db 两模式返回 `{session_id,title,updated_at}`、按 updated_at 降序 | §6.4 |
| chat 落库集成 | `tests/api/test_chat_persist.py` | 发对话 → messages 表 2 行（user+assistant 同 turn_index）、sessions 表 1 行带可读 title；mock run_new_agent_session 避免真 LLM | §6.3 |
| 列会话 API | `tests/api/test_sessions_api.py` | `GET /api/sessions?user_id=` 返回含 title、按 updated_at 倒序 | §6.4 |
| 取历史 API | 同上 | `GET /api/sessions/{id}/messages` 返回完整历史、顺序正确 | §6.5 |
| **容错（C3）** | `tests/api/test_chat_persist.py` | 模拟 MessageStore.add 抛异常 → 断言 db.rollback 调用、messages 表 0 行（不半落库）、HTTP 仍 200 且返回 reply | §6.6 |

#### G.3 测试技术要点

- **async 范式（P1）**：所有 Store 单测与 API 集成测试的 async 逻辑包成 `async def _test()` + `asyncio.run(_test())`，与 `test_stores.py`/`test_memory_store.py` 一致；不加 mark、不改 asyncio_mode。
- **chat 集成测试**用 FastAPI `TestClient` 或 httpx `AsyncClient` + `app.dependency_overrides[get_db]` 注入测试 session；并 monkeypatch `run_new_agent_session` 返回固定 `NewStackResult`（避免真 LLM、对齐 conftest 既有 mock 思路）。
- **P2/P3：不污染真实库**——集成测试**必须**用 `app.dependency_overrides[get_db]` 指向 G.1 的临时库 helper，绝不让注入的 `get_db` 连到 `database.py` 模块级 engine（真实 `study_agent.db` 文件）。补充事实：现存 `test_api.py` 用 `TestClient(app)`（非 context-manager 形式）**不触发 lifespan**，故现存测试未跑 `init_db`、靠 Store 内存分支；本子项目新增 chat 落库后，一旦注入真实 `get_db` 就会写真实文件——override 是硬要求。
- **P2：保护现存 `test_api.py`**——E.3 把 `list_sessions` 响应模型由 `list[SessionResponse]` 改为 `list[SessionSummary]`，`test_sessions_empty`（空列表）仍能过；但执行后须**重跑 `test_api.py` 全量**确认无回归（响应模型变更属隐性契约变更）。
- **容错测试**用 monkeypatch 让 `MessageStore.add` 第二次调用抛异常，验证整体回滚（messages 表行数为 0）与 HTTP 200。
- **turn_index 共用**：集成测试断言两条消息 turn_index 相等（同一轮）。

---

## 构建顺序（执行阶段的推进次序）

1. **F.1 依赖** → 装 asyncpg/pgvector（先让环境就绪）。
2. **A 连接层** → engine 读配置 + init_db 分流。
3. **B 模型** → MessageTable + title。
4. **C MessageStore** + 其单测（TDD：先测后实现）。
5. **D SessionStore 改造** + 其单测。
6. **G.1 conftest db fixture**（C/D 测试的前置，可提前到第 4 步前）。
7. **E.1 schemas** → **E.3 sessions API** → **E.2 chat 落库**（schemas 是 API 前提）。
8. **E 的 API 集成测试 + 容错测试**。
9. **F.2/F.3/F.4 Docker/Alembic/.env**（PG 路径，可独立验证）。
10. **README 更新**（启动顺序、双模式说明）。
11. 全量跑测试 `pytest -q < /dev/null` 绿。

> 频繁提交：每个子模块（含其测试）绿后单独 commit，只 `git add <明确文件>`，不用 `git add -A`、不 `--amend`。

---

## 验收标准映射（spec §6 全覆盖核对）

| spec §6 验收项 | 本规划落点 | 测试 |
|---|---|---|
| ①PG + alembic upgrade 后启动、表+扩展就绪 | A(init_db 分流) + F.3 | 手动（PG 环境）+ F.5 文档 |
| ②sqlite 开箱即用 | A(sqlite 分支保留 create_all) | conftest 起即验证 |
| ③对话后 sessions 带 title、messages 两行 | E.2 落库 | chat 落库集成 |
| ④列会话含 title、按 updated_at 倒序、多轮上浮 | D(C2+R1) + E.3 | 列会话 API + R1 刷新测试 |
| ⑤取历史返回完整 | C + E.3 | 取历史 API |
| ⑥写库失败仍返回 reply | E.2 容错块 | 容错测试 |
| ⑦全部新增测试通过 | G 全部 | `pytest < /dev/null` |

---

## 风险与盲点自查

| 风险 | 缓解 |
|---|---|
| `:memory:` SQLite 多连接不共享建表 | G.1 用临时文件 fixture，不用裸 `:memory:` |
| flush 后未 commit，同 session 内能否 list 到 | 能（同事务可见）；测试在**同一 session** 内验证 |
| `Depends(get_db)` 自动 close 与手动 commit 冲突 | get_db 只 close 不 commit；本处显式 commit/rollback，职责清晰 |
| alembic env.py 配置踩坑 | 用**同步** engine 跑迁移（#1 已定）；autogenerate 后人工核对迁移内容再 upgrade |
| `func.now()` 在内存模式不可用 | 内存模式用 `_seq` 计数器近似，不调 func.now |
| chat_stream 未落库致需求 2/5 在②退化 | §1.1/spec §7 已显式标注 N2，留给② |
| role 值域 error 无 writer | B 注释说明预留、可收窄为 user/assistant |
| **P1：pytest-asyncio strict 模式静默 skip 假绿** | 全项目无 `asyncio_mode`，裸 `async def test_*` 会被 skip。G 沿用 `asyncio.run(_test())` 范式，不加 mark、不改全局配置 |
| **P2：E 改 `get_db` 注入冲击现存 `test_api.py` + 集成测试写真实库** | 集成测试一律 `dependency_overrides[get_db]` 指向临时库；执行后重跑 `test_api.py` 全量验回归 |
| **P4：turn_index 每轮多一次 `list_by_session` 全表 select** | 量级可忽略（按 session_id 过滤、单会话消息少），接受这次额外查询，不做缓存优化 |

---

## 待确认事项（进入编码前请用户拍板）

> 已定（review 阶段拍板，无需再问）：
> - **P1 async 测试范式 = `asyncio.run(_test())`**，不改全局 asyncio_mode（用户已确认）。
> - **#1 alembic env.py = 同步 engine 跑迁移**（review 改定）——迁移是一次性启动期操作、不在请求热路径，同步更简单稳妥、避开 async 模板 autogenerate 的 greenlet 坑；与运行时用 async engine 不冲突（两者独立）。

1. **docker-compose 默认账号/密码/库名**——建议 `studyagent`/`studyagent`/`studyagent`（开发用），生产经 .env 覆盖。
2. **PG 连接池数值**（pool_size=5、max_overflow=10）是否合适，或先用 SQLAlchemy 默认。
3. 是否需要在本子项目就给 `messages.session_id` 配 ORM `relationship`（当前规划为否，保持薄壳）。

---

> **本规划仅文字描述，未含实现代码。经用户确认后，方按「构建顺序」进入编码（TDD：先测后实现，频繁提交）。**
