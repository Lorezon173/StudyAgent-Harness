# 子项目② 实时协作流：Agent 事件级 SSE + 掌握度落库 + 回合数修复 · 设计 Spec

> 创建日期：2026-06-11
> 类型：子项目设计 Spec
> 上游分解文档：[`2026-06-09-redesign-decomposition-overview.md`](./2026-06-09-redesign-decomposition-overview.md)
> 上游 raw 材料：[`superpowers/2026-06-09-redesign-persistence-raw.md`](../../superpowers/2026-06-09-redesign-persistence-raw.md)
> 前置子项目：[`2026-06-09-storage-foundation-design.md`](./2026-06-09-storage-foundation-design.md)（① 已完成，提供 PG/SQLite 双模 + `Depends(get_db)` + 会话/消息落库）
> 状态：已与用户逐节确认（三层规划）+ 第 2 节经源码核验 review 修订（P1/P2/P3 + Q1/Q2/Q3）。修订明细见 §8。

## 1. 模块总览

### 1.1 目标

把子项目② 的四件事做完，让前端真正能看到「逐 Agent 思考过程 + 真实学习数据 + 正确回合数」：

1. **真流式**：`/chat/stream` 从假流式（整体跑完才一次性 yield）改成逐 Agent 事件实时 SSE 推送（撑需求 6）
2. **掌握度落库**：`MasteryGraph` 从「`:memory:` 永不 save/load」改成统一进 SQLAlchemy/PG 持久化（撑需求 4 的真实数据来源）
3. **回合数修复**：`turn_count` 从「事件循环 pop 次数」改成「教学回合数 = 一问一答」（修需求 7）
4. **profile 读真实数据**：`GET /profile/{user_id}` 从写死 `{sessions:0, avg_mastery:0}` 改成读真实会话数与平均掌握度（撑需求 4）

### 1.2 现状根因（已核实 file:line）

| 断点 | 事实 | 后果 |
|---|---|---|
| `app/api/chat_stream.py:19-27` | `generate_new` 用 `await asyncio.to_thread(run_new_agent_session,...)` 整体跑完才一次 yield reply | 假流式（需求 6 根因） |
| `app/orchestration/collab_loop.py:41-44` | `_publish_and_enqueue` 在循环内逐个 publish，但无任何对外实时回调 | 事件实时性无法透出 |
| `app/orchestration/assembly.py:110/114-115` | `EventStore(":memory:")` + `MasteryGraph(store=mg_store=":memory:")`，且全程**未调** `graph.load()` / `graph.save()` | 掌握度每会话从空开始、跑完即丢（需求 4 根因） |
| `app/orchestration/collab_loop.py:74` | `ws.turn_count = turn`（turn 是 while 迭代次数，注释自承「比真实回合数多 1」） | 回合数恒显 11（需求 7 根因） |
| `app/api/profile.py:8` | 直接 `return {"sessions":0, "avg_mastery":0}` | 画像永远是 0（需求 4 根因） |
| `app/api/chat_stream.py` 新栈分支 | 完全不碰 SessionStore / MessageStore | 切到 SSE 后会话+消息不落库（子项目① N2 衔接点，会让需求 2/5 退化） |

注：子项目① 已让 `/chat`（`app/api/chat.py:29-62`）原子落库会话+消息；`MasteryGraph.save/load`（`mastery_graph.py:163-199`）已存在但**无人调用**；`MasteryGraphStore`（aiosqlite）有 4 个测试消费者。

### 1.3 边界

- ✅ 做：collab_loop 加事件回调钩子；chat_stream 真流式 SSE（线程安全队列桥接）；掌握度统一进 SQLAlchemy/PG 落库+读取（新增并行 store）；assembly 接 load/save 透传；turn_count 语义修复；profile 读真实数据；抽共享落库函数让 chat + chat_stream 复用（含掌握度落库）。
- ❌ 不做：知识库文件上传/向量化（③）；前端 UI（思考抽屉、手动保存按钮、多会话切换交互）（④）；profile 手动保存**写**接口（④）；agent 内部 prompt / 教学策略调整；删除或改写旧 `MasteryGraphStore`（仅并行新增）。

### 1.4 架构衔接

严格遵守四层单向依赖（API → Orchestration → Harness → Infrastructure）。

- 事件回调钩子加在 `collab_loop`（Orchestration 层），Agent 不直接对外 I/O（薄壳约束）。
- 掌握度落库走子项目① 已建立的 `Depends(get_db)` + SQLAlchemy 双模式，**在 API 层（主协程）** 调用 `graph.load()`/`graph.save()`，不在工作线程内跑 async。
- 新增的 SQLAlchemy 掌握度 store 属 Infrastructure 层，复刻旧 store 的 4 方法契约。

## 2. 关键决策（已与用户确认 + review 拍板）

| 决策点 | 选择 | 理由 |
|---|---|---|
| 流式桥接机制 | **回调 + 线程安全队列**（`loop.call_soon_threadsafe` + `asyncio.Queue` + 哨兵） | 不破坏「协作环对外是一次同步调用」的冻结契约（§3.5.4），改动最小；备选「改 async 生成器」面大回归高，「轮询 EventStore」竞态+跨线程可见性不可靠 |
| SSE 事件范围 | **只推语义事件**（Tutor/Critic/Retriever/Curator/Conductor/PolicyTransition） | 抽屉看到的都是有意义的 agent 动作；过滤 Tick/LoopExit/ActionRequested 等纯控制信号，降噪 |
| 掌握度落库时序 | **主协程 load/save**，工作线程只读写内存 graph | MasteryGraph.save/load 是 async、协作环是同步在工作线程；Curator.handle 只调 graph 同步方法不触 store（assembly.py:106 注释已确认） |
| 掌握度存储后端 | **统一进 SQLAlchemy/PG**（新增并行 store，不删旧） | 与子项目① 业务持久化同一体系，为③ pgvector 铺路；旧 aiosqlite store 保留供现有测试 |
| 回合数语义 | **教学回合 = 一问一答**（`turn_index + 1`） | 与用户直觉一致；事件循环次数仅留灰度调试 |
| chat_stream 落库 | **复用落库到 chat_stream**（抽共享函数，两端复用） | 防子项目① N2 标注的「需求 2/5 退化」 |
| 掌握度落库路径（Q1） | **chat + stream 都接** | 否则④ 前 profile 仍空，违反「每个子项目可独立验证」 |
| avg_mastery 口径（Q2，**已修正**） | **0-100 整数**（`round(avg(mastery))`，**不乘 100**） | `mastery` 字段本就是 0-100 百分制（`mastery_graph.py:27` 注释 + `update_mastery` `min(100.0,...)`），与 `mastery_score` 同口径；**×100 会得 0-10000，是 review 修正前的错误** |
| SSE 格式变更（Q3） | **结构化 JSON SSE**，前端解析错位是已知过渡态 | 思考抽屉需 agent/type 字段；前端解析由④ 收口 |

## 3. 子模块与接口契约

整个子项目拆成 7 个子模块（A→G）。先给清单与三色血缘，再逐一展开。

### 3.0 子模块清单 + 三色血缘

| # | 子模块 | 类型 | 落点（file） | 职责 |
|---|---|---|---|---|
| A | collab_loop 事件回调钩子 | 🟡 改动 | `app/orchestration/collab_loop.py` | 循环内每 publish 一个事件，回调透出 |
| B | assembly 透传 graph/on_event | 🟡 改动 | `app/orchestration/assembly.py` | `run_new_agent_session`/`build_new_stack` 加可选参数 |
| C | SSE 事件投影函数 | 🔴 新建 | `app/api/_sse_projection.py` | 语义事件白名单过滤 + 转前端友好 payload |
| D | 掌握度 SQLAlchemy 表 + store | 🔴 新建 | `app/models/tables.py` + `app/infrastructure/storage/sqlalchemy_mastery_store.py` | mastery_nodes/edges 上 SQLAlchemy，PG/SQLite 双模 |
| E | chat_stream 真流式 + 共享落库 | 🟡 改动 | `app/api/chat_stream.py` + `app/api/chat.py` + 新 `app/api/_persist.py` | 队列桥接逐事件 SSE + 流末复用会话/消息/掌握度落库 |
| F | turn_count 修复 | 🟡 改动 | `app/api/chat.py` / `chat_stream.py` | 改成「教学回合=一问一答」语义 |
| G | profile 读真实数据 | 🟡 改动 | `app/api/profile.py` | 读 sessions 计数 + mastery_nodes 均值 |

🟢 保持现状（用但不改）：`EventBus`、`EventStore`、`MasteryGraph`（仅放宽 store 类型标注）、`Curator`、`Orchestrator`、旧 `MasteryGraphStore`（P2：4 个测试还在用，不删不改）。

### 3.1 子模块 A · collab_loop 事件回调钩子

- **`run_collab_loop` 加形参** `on_event: Callable[[Event], None] | None = None`，置于 `max_turns` 之后（现有位置参数不动）。
- **`_publish_and_enqueue(ev)` 内**：在 `bus.publish(ev)` 之后增加 `if on_event is not None: on_event(ev)`。位置选在 publish 之后——只透出「已通过白名单校验并落库」的合法事件。
- **行为契约**：`on_event=None` 时与现状逐字节一致（保护 chat.py 非流式 + 所有现有 collab_loop 测试）。
- **回调异常不吞**：桥接侧 `call_soon_threadsafe` + 无界队列 `put_nowait` 基本不抛；若抛应冒泡暴露桥接故障，不静默。

### 3.2 子模块 B · assembly（run_new_agent_session / build_new_stack）

- **`build_new_stack(user_id, graph=None)`**：加可选 `graph` 形参。
  - `graph is None` → 维持现状：自造 `MasteryGraphStore(":memory:")` + `MasteryGraph`（保护非流式早期 + test_assembly）。
  - `graph` 传入 → 用传入 graph 及其自带 store 构造 Curator，不再自造。
- **`run_new_agent_session(session_id, user_id, user_message, current_topic=None, graph=None, on_event=None)`**：P3 向后兼容，新增两参默认 None；`graph` 透传 `build_new_stack`，`on_event` 透传 `run_collab_loop`。`NewStackResult` 不变。

### 3.3 子模块 C · SSE 事件投影函数（新建 `app/api/_sse_projection.py`）

- **`project_event(ev: Event) -> dict | None`**：
  - 白名单 = {Tutor 四类（ASKED/EXPLAINED/REQUESTED_RECAP/OFFERED_ANALOGY）、MASTERY_ASSESSED、CONFUSION_DETECTED、CONTRADICTION_DETECTED、LOW_CONFIDENCE_DETECTED、RAG_QUALITY_ASSESSED、RETRIEVED_EVIDENCE、RETRIEVAL_FAILED、GRAPH_NODE_STRENGTHENED、GRAPH_PREREQ_WEAK_DETECTED、CONDUCTOR_DECIDED、POLICY_TRANSITION}。不在白名单 → 返回 `None`（生成器跳过）。
  - 命中 → 返回 `{"type":"agent_event", "agent":<ev.source 字符串>, "event":<ev.type 字符串>, "content":<可读内容>, "eval":<可选评估字段>}`。
- **content 提取规则**用一张 `EventType → 字段提取` 映射字典维护（避免散落 if）：Tutor 类取 `payload["content"]`；MasteryAssessed 取 `score`+`level`；Curator 取 `topic_id`+`mastery`；Retriever 取证据摘要/条数；PolicyTransition 取 `to`；其余取 payload 可读字段。

### 3.4 子模块 D · 掌握度 SQLAlchemy 表 + store（新建）

**`tables.py` 新增两表**（对齐旧 aiosqlite schema 字段，用 SQLAlchemy Column）：

| 表 | 字段 |
|---|---|
| `MasteryNodeTable` | `(user_id String(64), topic_id String(128))` 复合主键、`topic_name String(128)`、`mastery Float default 0`、`last_practiced_at Float default 0`、`practice_count Integer default 0`、`confusion_with JSON default list`、`rationale Text default ""` |
| `MasteryEdgeTable` | `id Integer PK autoincrement`、`user_id String(64) index`、`from_topic`/`to_topic String(128)`、`type String(16) default "PREREQ"`、`weight Float default 1`、`confidence Float default 0.5`、`source String(16) default "LLM_INFER"`、`UniqueConstraint(user_id, from_topic, to_topic, type)` |

**新建 `storage/sqlalchemy_mastery_store.py`**（P1：复刻契约而非替代）：

- `__init__(db: AsyncSession)`。
- `save_nodes(user_id: str, nodes: list[dict]) -> None`：逐条 upsert（select 存在则 update，否则 add）。**不自行 commit**（对齐① C3，commit 收口到 API 层）。
- `load_nodes(user_id: str) -> dict[str, dict]`：返回 `{topic_id: {...}}`，字段与旧 store 一致。
- `save_edges(user_id: str, edges: list[dict]) -> None`：按 unique key upsert，不 commit。
- `load_edges(user_id: str) -> list[dict]`。
- **4 个方法签名逐字对齐旧 `MasteryGraphStore`**，使 `MasteryGraph.save/load`（mastery_graph.py:163-199）内部调用无需改。
- **`rationale` 字段处理（review 核实）**：当前 `MasteryGraph.save()` 传的 nodes_data **含 `rationale`**（mastery_graph.py:31 字段 + save 拼入），但旧 aiosqlite store 用 `n.get(...)` 静默忽略它（旧行为 = rationale 不持久化）。新表已加 `rationale` 列（见上），新 store 的 `save_nodes`/`load_nodes` **应真正读写 rationale**（比旧行为更完整，不丢 Critic 评分依据）；`load_nodes` 返回 dict 补 `rationale` 键，`MasteryGraph.load` 已能接收（dataclass 有该字段）。

**新旧表同名 → 库必须隔离（review 提示）**：新 SQLAlchemy 表与旧 aiosqlite store 表**同名** `mastery_nodes`/`mastery_edges`（mastery_graph_store.py:24/34）。二者走不同库（新=业务 PG/SQLite，旧=独立 aiosqlite）本不冲突；但**测试时严禁让新表与旧 store 指向同一 SQLite 文件**，否则 schema 冲突。测试用独立临时库隔离。

**`MasteryGraph.__init__` 类型标注放宽**：`store: MasteryGraphStore` → 去硬标注（无标注或定义 `MasteryStoreProtocol` 含 4 方法）。Curator/UserProfile 标注本子项目不动（运行时鸭子类型成立）。

**Alembic 迁移**：新增一版 migration 建这两张表（PG 侧）；SQLite 走 `init_db` 的 `create_all` 自动包含。

### 3.5 子模块 E · chat_stream 真流式 + 共享落库

**抽共享落库函数 `persist_turn(...)`**（新建 `app/api/_persist.py`）：

- 把 `chat.py:29-62` 现有「算 turn_index → save session → add user/assistant message → commit」逻辑抽出。
- 参数含可选 `graph=None`；若 `graph is not None`，在同一 try 块内 `await graph.save()`，与消息落库**同一次 commit**（原子）。
- 失败 `rollback` + observability 记日志，仍返回（对齐① 容错）。
- **chat.py 改为调用此共享函数**（P2/Q1：非流式路径也接掌握度）。

**`chat_stream.chat_stream` 签名加 db 注入**（review 修正）：当前 `async def chat_stream(req: ChatRequest)`（chat_stream.py:15）**无 db 参数**，本子项目须改为 `async def chat_stream(req: ChatRequest, db: AsyncSession = Depends(get_db))`，与 chat.py:18 对齐——否则 graph load/save 与 persist_turn 无 db 可用。

**`chat_stream.generate_new` 重写为真流式**（数据流见 §4）：

1. `queue = asyncio.Queue()`；`loop = asyncio.get_running_loop()`。
2. 主协程构造 `graph = MasteryGraph(user_id=<uid_str>, store=SQLAlchemyMasteryStore(db))`；`await graph.load()`。
3. 定义 `cb(ev)`（工作线程内执行）：`loop.call_soon_threadsafe(queue.put_nowait, ev)`。
4. `task = asyncio.create_task(asyncio.to_thread(run_new_agent_session, ..., graph=graph, on_event=cb))`。
5. `task.add_done_callback(lambda _: loop.call_soon_threadsafe(queue.put_nowait, SENTINEL))`——保证正常/异常都投哨兵。
6. `while True: item = await queue.get()`；`item is SENTINEL` → break；否则 `sse = project_event(item)`，非 None 则 `yield f"data: {json.dumps(sse)}\n\n"`。
7. `result = await task` 拿 `NewStackResult`（同时让工作线程异常在此 re-raise）。
8. `await persist_turn(db, ..., reply=result.reply, graph=graph)`。
9. `yield` 最终事件 `data: {json.dumps({"type":"final","reply":...,"turn_count":<教学回合数>,"mastery_score":...,"mode_path":...})}`。

**user_id 处理**：与 chat.py 一致 `str(req.user_id) if not None else "anonymous"`，graph key 用此字符串（Q1 对齐 profile 读取）。

**⚠ db 会话生命周期（review pre-mortem，实现时必测）**：`StreamingResponse` 下，`Depends(get_db)` 的 yield 型依赖在生成器迭代期间必须保持有效。graph.load（步骤2）和 persist_turn（步骤8）分别在流的**头尾**用同一个 `db`——须实测整个流期间 session 不被提前关闭。这是 FastAPI StreamingResponse + 依赖注入的已知易错点，是本子项目**最可能崩的点**。若实测发现 session 提前关，退路：在 generate_new 内自行用 `async_session()` 上下文管理器开独立 session，不依赖 `Depends(get_db)` 的生命周期。

### 3.6 子模块 F · turn_count 修复

- **教学回合数 = `turn_index + 1`**，`turn_index = len(existing_messages) // 2`（落库前查到的本会话已有消息数；与① chat.py:31-32 同源）。
- chat.py / chat_stream 返回给前端的 `turn_count` 填此值（覆盖 `result.turn_count` 的事件循环次数）。
- `ws.turn_count`（事件循环次数）保留在 `NewStackResult` 仅作灰度调试，不透传前端。
- 前端 `TeachingStatus.tsx:49` 读的 `last.turn_count` 自然变成教学回合数，无需改前端。

### 3.7 子模块 G · profile 读真实数据

- **`GET /profile/{user_id}` 注入 `db: AsyncSession = Depends(get_db)`**。
- `sessions = SELECT count(*) FROM sessions WHERE user_id = :uid`（int）。
- `avg_mastery`：`SELECT round(coalesce(avg(mastery), 0)) FROM mastery_nodes WHERE user_id = :uid_str`（**`str(user_id)`**，Q1 对齐 graph key）。`mastery` 本就是 0-100 百分制（`mastery_graph.py:27`），**直接取整、不乘 100**（Q2 修正）；无节点时 `coalesce` 返回 0。
- 返回结构不变 `{"user_id":..., "stats":{"sessions":int,"avg_mastery":int}}`，前端 Profile.tsx 无需改。

## 4. 数据流

### 4.1 真流式桥接（核心）

```
主协程 (chat_stream.generate_new)              工作线程 (asyncio.to_thread)
─────────────────────────────────              ──────────────────────────────
queue = asyncio.Queue()
loop  = get_running_loop()
graph = MasteryGraph(SQLAlchemyMasteryStore(db))
await graph.load()            ← 先加载历史掌握度
task = create_task(
   to_thread(run_new_agent_session,
      ..., graph=graph, on_event=cb)) ─────────▶ run_collab_loop(... on_event=cb)
task.add_done_callback(→投SENTINEL)                每 _publish_and_enqueue(ev):
                                                      bus.publish(ev)
   def cb(ev):  # 工作线程执行                          on_event(ev)  ← 子模块A
     loop.call_soon_threadsafe(  ◀──────────────       └ cb(ev) 投队列
        queue.put_nowait, ev)
while True:                                        ...循环结束...
   item = await queue.get()    ◀──────────────── done_callback: call_soon_threadsafe(
   if item is SENTINEL: break                        queue.put_nowait, SENTINEL)
   sse = project_event(item)   ← 子模块C投影/过滤
   if sse: yield f"data:{json}\n\n"
result = await task           ← 拿 NewStackResult（异常在此 re-raise）
await persist_turn(db, ..., reply=result.reply, graph=graph)  ← 流末原子落库
yield data:{type:final, reply, turn_count, mastery_score, mode_path}
```

### 4.2 非流式 /chat（Q1：也接掌握度）

```
POST /api/chat → chat() 注入 db
  → graph = MasteryGraph(SQLAlchemyMasteryStore(db)); await graph.load()
  → result = to_thread(run_new_agent_session, ..., graph=graph)   # on_event=None
  → await persist_turn(db, ..., reply=result.reply, graph=graph)  # 会话+消息+掌握度一次commit
  → return ChatResponse(turn_count=教学回合数, ...)
```

### 4.3 profile 读

```
GET /api/profile/{user_id} → 注入 db
  → sessions   = count(sessions WHERE user_id=:uid)
  → avg_mastery= round(coalesce(avg(mastery_nodes.mastery WHERE user_id=str(uid)), 0))  # 已是0-100，不×100
  → {"user_id":uid, "stats":{"sessions":..., "avg_mastery":...}}
```

## 5. 测试策略

- **前置基建**：复用子项目① 的 async db fixture（`tests/conftest.py`）；新增掌握度落库需要的 SQLAlchemy 临时库。
- **子模块 A**：collab_loop 加 `on_event` 后，回调收到的事件序列 == 现有 `ws.event_ids` 顺序；`on_event=None` 时所有现有 collab_loop 测试不变。
- **子模块 C**：`project_event` 单测——语义事件命中返回 dict、控制事件（Tick/LoopExit/ActionRequested）返回 None；各 agent 的 content 提取正确。
- **子模块 D**：`SQLAlchemyMasteryStore` 双模（SQLite）save/load 往返一致；与旧 `MasteryGraphStore` 同 4 方法契约对照（同输入同输出结构）。
- **掌握度落库集成**：`/chat` 发对话 → mastery_nodes 表有该 user（`str(user_id)`）节点；第二轮 mastery 更新落库（practice_count 递增）。
- **真流式集成**：`/chat/stream` 用 httpx/StreamingResponse 测试客户端，断言收到**多个** `agent_event` 分批到达（非一次性）+ 末尾 `final` 事件；且流末 messages 表落库 2 行（复用落库验证，防 N2 退化）。
- **turn_count**：单会话发 2 轮，断言第 1 轮 `turn_count==1`、第 2 轮 `==2`（非 11）。
- **profile**：落库掌握度后 `GET /profile/{uid}` 返回真实 sessions 数 + avg_mastery（0-100），无数据时返回 0。
- **容错**：掌握度 save 抛异常 → rollback 后仍返回 reply（对齐① 容错；验证不半落库）。
- **回归保护（P2/P3）**：旧 `MasteryGraphStore` 的 4 个测试、`test_assembly` 全绿（向后兼容验证）。
- **注意**：本 harness 跑 pytest 必须 `< /dev/null`（已知 stdin 挂起问题）。

## 6. 验收标准

1. `/chat/stream` curl 能看到逐 Agent `agent_event` 分批到达（非整体一次性），末尾收到 `final` 事件含正确 `turn_count`。
2. 发起对话后，mastery_nodes 表有该用户（`str(user_id)`）的掌握度节点；多轮后 mastery/practice_count 更新落库。
3. `GET /profile/{user_id}` 返回真实会话数 + 平均掌握度（0-100 整数），无数据返回 0。
4. 同一会话发 2 轮，`turn_count` 依次为 1、2（不再恒显 11）。
5. `/chat/stream` 跑完后，sessions 表有记录、messages 表有 user+assistant 两行（N2 防退化验证）。
6. 掌握度写库失败时对话仍正常返回（容错）。
7. `on_event=None` 路径（chat.py 非流式）与所有现有测试（含旧 MasteryGraphStore 4 测试、test_assembly）全绿。
8. 全部新增测试通过。

## 7. 不在本子项目范围（留给后续）

- 知识库文件上传、pgvector 向量表与检索 → 子项目③（本子项目新增的 SQLAlchemy store 与③ 的 pgvector 同一 PG 体系，但不建向量表）。
- 前端思考抽屉 UI、SSE 结构化解析、多会话切换交互、画像手动保存按钮 → 子项目④。
- **SSE 格式过渡态**：本子项目交付后到④ 之前，`/chat/stream` 返回结构化 JSON SSE，但前端 `Chat.tsx` 仍按纯文本解析且仍走 `/chat`（非流式）。这是**已知过渡态**，非 bug——前端切 SSE 解析由④ 收口。本子项目流式正确性用 curl/测试验证，不依赖前端。
- UserProfile（L3 偏好画像）的落库与读取 → 暂不接（本子项目 profile 只读 sessions 计数 + mastery 均值；偏好/streak 留后续）。

## 8. Review 修订记录（2026-06-11）

第 2 节经源码核验 review，发现并修订如下（均已吸收进 §2/§3）：

| 编号 | 修订点 | 落在 | 决策方式 |
|---|---|---|---|
| P1 | 掌握度新 store 是**复刻** save_nodes/load_nodes/save_edges/load_edges 四方法契约（非"替代"），MasteryGraph 类型标注放宽 | §3.4 | review 拍板 |
| P2 | 旧 `MasteryGraphStore` 不删不改（4 个测试在用），仅并行新增 | §1.3 §3.0 §5 | review 拍板（核实 4 消费者） |
| P3 | `run_new_agent_session`/`build_new_stack` 新增 graph/on_event **可选默认 None**，保护非流式 + test_assembly | §3.2 | review 拍板（核实 3 调用点） |
| Q1 | 掌握度落库 **chat + stream 都接**（否则④ 前 profile 仍空，违反可独立验证） | §2 §3.5 §4.2 | 用户确认 |
| Q2 | `avg_mastery` 返回 **0-100 整数**（×100 取整） | §2 §3.7 | 用户确认 |
| Q3 | SSE 结构化 JSON，前端解析错位是**已知过渡态**，④ 收口 | §2 §7 | 用户确认 |

review 已核实的源码事实：`MasteryGraphStore` 3 个类型标注消费者（mastery_graph.py:54 / curator.py:33 / user_profile.py:22）+ 4 个测试构造点；`run_new_agent_session` 3 类调用点（chat.py:22 / chat_stream.py:21 / test_assembly.py）；Curator.handle 尾部只调 `self.graph` 同步方法、不碰 `self._store`（curator.py 全文核实）；chat_stream 当前 yield 纯文本 `data: {reply}`（chat_stream.py:27）。

### 8.1 隔离式独立评审修订（2026-06-11，subagent 评审）

进编码前用全新上下文 subagent 做隔离评审（reviewing-plans-isolated），抓出并已修正：

| 编号 | 问题 | 核实 | 落在 |
|---|---|---|---|
| R-A | **avg_mastery ×100 错误** | `mastery` 是 0-100 百分制（mastery_graph.py:27 注释 + `update_mastery` `min(100.0,...)` line 88 + `extract_mastery_score` 0-100，assembly.py:45）；×100 得 0-10000。**首版 spec 误称「0-1 float」是探索读错源码** | §2 §3.7 §4.3 |
| R-B | **chat_stream 缺 db 注入** | 当前 `async def chat_stream(req: ChatRequest)`（chat_stream.py:15）无 db；graph/persist_turn 需 db | §3.5 |
| R-C | **rationale 字段** | `MasteryGraph.save()` 传 rationale（mastery_graph.py:31 字段），旧 aiosqlite store `n.get` 静默忽略（旧行为=不持久化）；新表补 `rationale` 列、新 store 真正读写 | §3.4 |
| R-D | **新旧表同名库隔离** | 新 SQLAlchemy 表与旧 store 表同名 `mastery_nodes/edges`；测试须独立库隔离 | §3.4 |
| R-E | **StreamingResponse + get_db 生命周期** | evaluator pre-mortem 标为最可能崩点；流头尾共用 db，须实测 session 不提前关，附退路 | §3.5 |

评审者独立复算确认：决策 1（回调+队列）、3（主协程 load/save，Curator 不触 store 前提成立）、5（turn_index+1）、6（共享 persist_turn）均成立。SSE 白名单 12 个事件名经 enums.py 逐条核对存在（评审者盲区已排除）。
