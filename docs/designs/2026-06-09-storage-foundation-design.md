# 子项目① 存储底座：PostgreSQL + pgvector + 会话持久化 · 设计 Spec

> 创建日期：2026-06-09
> 类型：子项目设计 Spec
> 上游分解文档：[`2026-06-09-redesign-decomposition-overview.md`](./2026-06-09-redesign-decomposition-overview.md)
> 状态：已与用户逐节确认 → 已基于源码核验 review 并据此修订（2026-06-09）。§1.2 全部 file:line 断言经 review 逐条核对均准确；M1（建表职责）、C3（落库原子性）经用户确认采纳推荐方案。修订明细见 §8。

## 1. 模块总览

### 1.1 目标

把「双模式已写好但没接上」的持久化层真正接通，新增 PostgreSQL + pgvector 作为生产后端，让会话与对话历史真正落库，支撑需求 2（切走不丢）、需求 5（多会话切换）的后端侧，并为子项目 ②③ 铺好 PG/pgvector 地基。

### 1.2 现状根因（已核实 file:line）

| 断点 | 事实 | 后果 |
|---|---|---|
| `app/core/database.py:9` | engine 硬编码 `sqlite+aiosqlite:///./study_agent.db`，未读 `settings.database_url` | 双模式无法通过 .env 切换 |
| `app/api/auth.py:7`、`app/api/sessions.py:7` | `_store = UserStore()` 模块级实例化、不传 db | 所有 Store 走内存分支，重启即丢 |
| `app/api/chat.py:15-31` | 新栈分支只调 `run_new_agent_session`，完全不碰 SessionStore | 会话和对话历史从不落库（需求 2、5 根因） |
| `app/core/database.py:18` | `init_db()` 用 `Base.metadata.create_all`，未用 Alembic | schema 演进无版本管理 |
| `pyproject.toml` | 未装 asyncpg、pgvector | PG 跑不起来 |

注：`UserStore`、`SessionStore` 已是双模式（db 分支 + 内存分支）；`KnowledgeStore`（`app/infrastructure/storage/knowledge_store.py`）是纯内存，留待子项目③ 改造，本子项目不动。

### 1.3 边界

- ✅ 做：PG 驱动 + pgvector 依赖；engine 读 `database_url` 支持双模式；Store 通过 `Depends(get_db)` 接真实 db；新栈 chat 每轮把会话+对话历史落库；新增「列会话/取历史」API；Docker pgvector；Alembic 初始化迁移；PG 模式装 vector 扩展。
- ❌ 不做：掌握度落库（②）、知识库文件向量化（③）、前端（④）、`KnowledgeStore` 改造（③）、agent 内部状态（WorkspaceState/EventStore）持久化。

### 1.4 架构衔接

严格遵守四层单向依赖（API → Orchestration → Harness → Infrastructure）。Store 属 Infrastructure；API 层通过 FastAPI `Depends(get_db)` 注入 `AsyncSession`——这是 `app/core/database.py:13 get_db()` 已设计好但无人使用的注入点。

## 2. 关键决策（已与用户确认）

| 决策点 | 选择 | 理由 |
|---|---|---|
| 对话历史存哪 | **新建 `messages` 表**（非塞 state_json） | 多会话恢复、画像统计需按消息粒度查询，独立表清晰，符合薄壳规范 |
| 会话标题存哪 | **`SessionTable` 加 `title` 字段** | 列会话高频，冗余存标题避免 N+1，便于未来重命名 |
| `state_json` 处理 | **暂存空 JSON `{}`** | 本子项目聚焦对话历史，state_json 用途留给② |
| PG async 驱动 | **asyncpg** | async 原生、性能好 |
| 写库失败容错 | **失败仅记日志，仍正常返回 reply** | 教学回复是主路径，持久化是旁路，不该因写库失败让用户拿不到回答 |
| 迁移过渡 | **SQLite/PG 双模式共存** | 开发测试用 SQLite，生产用 PG |
| 旧数据 | **不迁移，PG 重建 schema** | 现有 SQLite 几乎无真实数据 |

## 3. 子模块与接口契约

### 3.1 配置与连接层（`core/database.py`）

- engine 从硬编码改为读 `settings.database_url`（该字段 `core/config.py:8` **已存在**，默认 sqlite；本子项目只是让 engine 真正去读它，无需新增配置项）
- 方言判断：`sqlite` 开头用最简参数；`postgresql` 开头附加连接池参数（pool_size、max_overflow、pool_pre_ping 防断连）
- `get_db()`、`async_session` 对外签名与行为不变
- **`init_db()` 按方言分流建表职责（M1 决策：Alembic 为 PG 唯一 schema 真相源）**：
  - **SQLite 模式**：保留 `Base.metadata.create_all`（测试/开发开箱即用，一次性库无需迁移）
  - **PG 模式**：**不** `create_all`，只执行 `CREATE EXTENSION IF NOT EXISTS vector`（为③铺路，本子项目不建向量表）；建表全部交给 `alembic upgrade`，避免 create_all 与 alembic 两套真相源漂移

### 3.2 messages 表、MessageStore 与 SessionStore 契约

**`models/tables.py` 新增 `MessageTable`**：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | Integer PK autoincrement | **历史排序主键**（见下 R2：排序用 id，非 created_at） |
| session_id | String(64) FK→sessions.id, index | 按会话查历史主路径 |
| role | String(16) | 本子项目 writer 仅产 `user` / `assistant`；`error` 为「前端异常消息持久化」预留，本子项目**不写**（避免值域出现无 writer 的取值，落地若不需要可收窄为二者） |
| content | Text | |
| turn_index | Integer | 第几轮（配合②修复后的真实回合数） |
| created_at | DateTime server_default now | 仅作展示/审计，**不**用于排序（见 R2） |

> **R2（排序精度）**：`list_by_session` **按 `id` 升序**，不按 `created_at`。原因：SQLite 的 `func.now()`→`CURRENT_TIMESTAMP` 是**秒级精度**，同一轮 user/assistant 两条毫秒内插入会得到相同 `created_at`，升序无法保证 user 在前；`id`（autoincrement）单调可靠。

**`models/tables.py` 改 `SessionTable`**：加 `title` String(128) default ""。（`created_at`/`updated_at` 字段 `tables.py:19-20` **已存在**，无需新增；其中 `updated_at` 是 `onupdate=func.now()`，但见 R1 的刷新陷阱。）

**新建 `storage/message_store.py`**（双模式，对齐现有写法）：
- `__init__(db: AsyncSession | None = None)`：db 为空走 `_memory: list`
- `add(session_id, role, content, turn_index) -> int`：插一行返回 id。**不自行 commit**（C3：commit 收口到调用方，见 §3.3）；db 模式用 `flush` 拿到自增 id
- `list_by_session(session_id) -> list[dict]`：**按 id 升序**返回 `[{role, content, turn_index, created_at}]`

**改 `storage/session_store.py` 的 `SessionStore`**（C1 补 title 契约 + R1 刷新 updated_at + C3 收口 commit）：
- **`save` 签名加 `title` 形参**：`save(session_id, state, user_id=None, title=None)`——现签名 `session_store.py:23` 无 title，是 §3.4 标题逻辑落地的前提（原 spec §3.2 漏列此契约变更，本次补上）
- **upsert 的 title 语义**：INSERT 分支（新行，`session_store.py:30`）写入 title；UPDATE 分支（已存在行，line 32-34）**不覆盖** title（实现 §3.4「仅首轮写、后续不覆盖」）
- **R1：UPDATE 分支显式 `row.updated_at = func.now()`**，不依赖 `onupdate`——因 state_json 恒为 `{}`、user_id 不变时该行无净变化，SQLAlchemy 可能不 emit UPDATE，`onupdate` 不触发，导致 `updated_at` 停在首轮、§3.5「按 updated_at 降序」失真
- **C3：`save` 不自行 commit**（移除 `session_store.py:36` 的内部 `await self.db.commit()`），改由调用方统一 commit

### 3.3 会话写入接线（`api/chat.py`）

- 模块级 `_store` 改为请求内注入：函数签名加 `db: AsyncSession = Depends(get_db)`，请求内构造 `SessionStore(db)`、`MessageStore(db)`（`get_db()` 已存在于 `database.py:13`，grep 确认**全项目零调用**，本子项目是它的首个消费者）
- 新栈分支跑完 `run_new_agent_session`（同步函数，经 `asyncio.to_thread` 调用；落库代码在其 `await` 之后、回到主协程执行，AsyncSession 绑定主事件循环，安全）后按序落库：
  1. 先算 `turn_index`（见下，两条消息共用同一值）
  2. `SessionStore.save(session_id, state={}, user_id, title=…)`（upsert；首轮用首条用户消息前 24 字算 title）
  3. `MessageStore.add(session_id, "user", req.message, turn_index)`
  4. `MessageStore.add(session_id, "assistant", result.reply, turn_index)`
  5. **统一 `await db.commit()`**（C3：上述 Store 均不自行 commit，三步共享同一 AsyncSession、一次提交）
- **C3 事务原子性**：save + 两次 add 共用一个事务、单次 commit，要么全落要么全不落。消除半落库，从而**也消除 R3**（turn_index 错位）——不会出现「落了 user 没落 assistant 致消息数变奇数、`//2` 持续错位」
- **`turn_index` 来源**：本子项目先用「该会话已有 message 数 // 2」推算，**在两条 add 之前算一次、两条共用**（②修复 turn_count 后对齐真实回合）。前提：单会话串行 + 本轮三步原子（已由 C3 保证）
- **错误处理**：整个「算 turn_index → save → add → commit」用 try/except 包裹，失败 `await db.rollback()` 后仅记 observability 日志，仍正常返回 reply（教学回复是主路径，持久化是旁路）

### 3.4 会话标题

- 首轮写入时生成：首条用户消息 strip 后前 24 字符；空则 "新会话"
- 仅首轮写，后续轮不覆盖

### 3.5 列会话 / 取历史 API（`api/sessions.py`）

- 改造 `GET /api/sessions?user_id=`：返回 `[{session_id, title, updated_at}]`，按 updated_at 降序
  - 需给 `SessionStore.list_by_user` 补返回 title/updated_at
  - **C2（双分支一致）**：现有 `list_by_user` 两分支字段已不一致——db 分支（`session_store.py:61`）只返回 `{session_id, state_json}`（连 user_id 都没有），内存分支（line 63）返回 `{session_id, user_id, state_json}`。改造后**两分支统一**返回 `{session_id, title, updated_at}`。内存分支的 title 来自 §3.2 `save(title=…)` 存入的字段；内存模式无真实时间戳，`updated_at` 用插入/更新序近似（或声明内存模式不保证跨重启时序，仅供测试）
- 新增 `GET /api/sessions/{id}/messages`：调 `MessageStore.list_by_session`，返回历史
- 两端点用 `Depends(get_db)` 注入
- **schema 调整**（`models/schemas.py`）：新增 `SessionSummary`（session_id/title/updated_at）、`MessageItem`（role/content/created_at）响应模型

### 3.6 Docker + Alembic + 依赖

- **pyproject.toml** dependencies 加：`asyncpg`、`pgvector`（Python 绑定，供③）。注：`alembic`、`aiosqlite` **已在 dependencies 中**，本子项目只是首次真正初始化 alembic 环境
- **docker-compose.yml**（当前仓库**无此文件**，新建）：`pgvector/pgvector:pg16` 镜像，映射端口、默认库名/账号密码、数据卷持久化
- **.env.example**：当前已有 `DATABASE_URL=sqlite+...`，补 PG 连接串示例（注释形式，默认仍 sqlite 保持开箱即用）
- **Alembic（M1 决策：PG 唯一建表源）**：初始化环境（当前**无 alembic/ 目录与 alembic.ini**），生成首迁移（建全部表，含 messages 表与 title 字段）。
  - **SQLite 测试/开发**：保留 `init_db` 的 create_all，无需迁移
  - **PG 生产/部署**：`init_db` 不建表（见 §3.1），**启动前置步骤＝先 `alembic upgrade head` 建表，再起服务**；`init_db` 启动时只补 `CREATE EXTENSION`
  - 注意：`main.py:19` lifespan 无条件 `await init_db()`，PG 模式下它只跑 CREATE EXTENSION，不与 alembic 冲突

## 4. 数据流

```
用户发对话 POST /api/chat
  → chat() 注入 db（Depends(get_db)）
  → run_new_agent_session(...) 得 reply/turn_count/...（不变；同步函数经 to_thread）
  → try:
       turn_index = 已有 message 数 // 2                         # 两条 add 共用
       SessionStore(db).save(session_id, {}, user_id, title=…)   # upsert；首轮写 title + 显式刷新 updated_at
       MessageStore(db).add(session_id, "user", message, turn_index)      # 不 commit
       MessageStore(db).add(session_id, "assistant", reply, turn_index)   # 不 commit
       await db.commit()                                         # C3：三步一次提交，原子
     except:
       await db.rollback(); log only                             # 失败整体回滚，仍返回 reply
  → 返回 ChatResponse（不变）

前端列会话 GET /api/sessions?user_id=
  → SessionStore(db).list_by_user → [{session_id, title, updated_at}]

前端恢复历史 GET /api/sessions/{id}/messages
  → MessageStore(db).list_by_session → [{role, content, created_at}]
```

## 5. 测试策略

- **前置基建（N3）**：当前 `tests/conftest.py` 仅有 state/LLM-mock fixture，**无 async db fixture**。需新增：临时 SQLite（`:memory:` 或临时文件）的 async engine + `AsyncSession` fixture，供下列 db 模式测试注入；`tests/api/` 目前仅 `__init__.py`，集成测试落于此
- MessageStore 双模式单测（内存 + SQLite）
- chat 落库集成测试：发对话 → messages 表 2 行、sessions 表 1 行带 title
- 列会话 / 取历史 API 测试
- 容错测试：模拟写库异常，确认 **rollback 后**仍返回 reply（C3：验证整体回滚、不半落库）
- **updated_at 刷新测试（R1）**：同一会话发 ≥2 轮，断言第二轮后 `updated_at` 确实推进（防 onupdate 不触发的回归）
- **注意**：本 harness 跑 pytest 必须 `< /dev/null`（已知 stdin 挂起问题）

## 6. 验收标准

1. `.env` 配 PG 连接串 + Docker 起 pgvector 后，**先 `alembic upgrade head` 建表**，再起后端正常启动，表就绪且 vector 扩展就绪（M1：PG 建表归 alembic，`init_db` 仅补扩展、不 create_all）
2. `.env` 配 sqlite 仍可开箱即用（双模式有效）
3. 发起对话后，PG/SQLite 中 sessions 表有记录带可读 title、messages 表有 user+assistant 两行
4. `GET /api/sessions?user_id=` 返回该用户会话列表（含 title、按 updated_at 倒序）；多轮对话后该会话 updated_at 推进、排序上浮（R1 验证点）
5. `GET /api/sessions/{id}/messages` 返回完整对话历史
6. 写库失败时对话仍正常返回（容错验证）
7. 全部新增测试通过

## 7. 不在本子项目范围（留给后续）

- 掌握度/agent 状态落库、profile 真实数据、turn_count 语义修复 → 子项目②
- 知识库文件上传、pgvector 向量表与检索 → 子项目③
- 前端多会话 UI、会话切换交互 → 子项目④
- **流式接口的落库（衔接点 N2）**：`run_new_agent_session` 另有调用点 `api/chat_stream.py:21`，本子项目**只在 `chat.py` 落库**（前端 `Chat.tsx:29` 走 `/api/chat`，覆盖当前真实流量）。**子项目② 把前端切到 SSE 流式（`/chat/stream`）后，必须把本节落库逻辑迁移/复用到 `chat_stream`，否则需求 2/5 会再次退化**——此处显式标注，防②遗漏

## 8. Review 修订记录（2026-06-09）

本节追溯首版 spec 经源码核验 review 后的修订。review 已逐条核对 §1.2 全部 file:line 断言（`database.py:9/13/18`、`auth.py:7`、`sessions.py:7`、`chat.py:15-31` 等，**均准确**），并核实 `config.py:8` 已有 `database_url`、`SessionTable` 已有 `updated_at`、`get_db` 零调用等事实。以下为发现并已采纳的修订：

| 编号 | 修订点 | 落在 | 决策方式 |
|---|---|---|---|
| M1 | PG 建表职责：Alembic 唯一真相源，init_db 在 PG 不 create_all | §3.1 §3.6 §6① | 用户确认 |
| C1 | `SessionStore.save` 补 `title` 形参与 upsert「首轮写不覆盖」语义 | §3.2 | review 拍板 |
| C2 | `list_by_user` 双分支字段统一、内存分支 title/updated_at 来源 | §3.5 | review 拍板 |
| C3 | 落库三步共用一次事务、Store 不自行 commit、失败 rollback | §3.2 §3.3 §4 | 用户确认 |
| R1 | 显式刷新 `updated_at`（state_json 恒空时 onupdate 可能不触发） | §3.2 §3.3 §5 §6④ | review 拍板 |
| R2 | `list_by_session` 按 id 升序（SQLite created_at 秒级精度不可靠） | §3.2 | review 拍板 |
| R3 | turn_index 错位风险（由 C3 事务原子化消除） | §3.3 | review 拍板 |
| N1 | `role` 值域 error 无 writer，注明预留、可收窄 | §3.2 | review 拍板 |
| N2 | chat_stream 落库衔接点标注（防②遗漏） | §7 | review 拍板 |
| N3 | 测试需新增 async db fixture | §5 | review 拍板 |
