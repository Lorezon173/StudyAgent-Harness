# 阶段 B-②：掌握度时序化 + 用户主动复习 Spec

> 创建日期：2026-07-03  
> 修订日期：2026-07-15  
> 前置依赖：阶段 A（真向量检索）已完成；新栈掌握度已通过 SQLAlchemy 持久化  
> 来源追溯：`docs/designs/2026-06-16-rag-phase-a-plan.md` §“下阶段 ②”；其中记录用户决定“复习须可选、可调、可主动调用，不能强制自动触发”  
> 状态：⏳ 待用户确认，确认后方可编码  
> **用户硬要求（不可推翻）**：复习机制必须用户可开关、参数可调、可主动调用；本阶段不得强制或隐式自动触发。

---

## 修订摘要（2026-07-13）

本次修订以当前在线数据路径为准，消除旧版 spec 的事实错误和范围冲突：

- 掌握度读写统一以 SQLAlchemy 新栈为准：聊天 API 在加载阶段以 `SQLAlchemyMasteryStore` 建立 `MasteryGraph`，并在持久化阶段通过 `persist_turn()` 写回 `mastery_nodes` / `mastery_edges`；B-② 不读取旧 aiosqlite `MasteryGraphStore`。
- 本阶段**严格限定新栈**：仅当 `FEATURE_USE_NEW_AGENT_GRAPH=true` 时，Review API 才视为可用；legacy 路径不补桥接、不做迁移、不伪装成“可用但无建议”。
- 复习偏好不写旧 `user_profile_l3.preferences_json`。该表只存在于旧 aiosqlite store，不能被 FastAPI 的 `AsyncSession` 数据路径读取；本阶段新建 SQLAlchemy `review_preferences` 表。
- 历史 `mastery_nodes` / `mastery_edges` 的 Alembic 迁移链修复是本阶段的明确交付，不再只是“先检查再决定”的 gate。`review_preferences` 迁移只能建立在修复后的 Alembic head 之上。
- MVP 只提供**用户主动**的 API 查询和偏好配置；不引入 Celery、定时任务、自动推送、`MASTERY_DECAYED` / `REVIEW_RECOMMENDED` 事件或 Curator 改动。
- 衰减是请求时的只读投影：不调用 `MasteryGraph.update_mastery()`，不写回 `mastery_nodes.mastery`，因此不会伪造练习时间或把多次查询的衰减重复累积。
- 指数曲线改为真正的半衰期公式：`initial × 2 ** (-t / half_life)`；参数名“半衰期”与验收例一致。

### 验证状态表

| 事实 / 契约 | 验证状态 | 依据 |
|---|---|---|
| 新栈聊天请求加载并保存 SQLAlchemy 掌握图 | ✅ 源码深读 | `app/api/chat.py:26-46`；流式路径同样使用 SQLAlchemy store |
| `FEATURE_USE_NEW_AGENT_GRAPH` 未设置时默认走 legacy 路径 | ✅ 源码深读 + 单测 | `app/core/feature_flags.py:13-17` 默认 `False`；`tests/unit/api/test_chat_feature_flag.py:20-29`、`tests/unit/api/test_chat_stream_feature_flag.py:20-27` 覆盖关 flag 路径 |
| Review 仅可服务新栈历史，不补 legacy 桥接 | ✅ 用户决策 + 现状验证 | 仅新栈 chat/chat_stream 写 SQLAlchemy mastery；legacy 分支不写，且本阶段明确“不动旧栈” |
| `MasteryNodeTable` 含掌握度与最后练习时间 | ✅ 源码深读 | `app/models/tables.py:64-73`：`mastery` 为 0–100，`last_practiced_at` 为 epoch seconds |
| 节点 / 边 store 已按用户全量读取 | ✅ 源码深读 | `app/infrastructure/storage/sqlalchemy_mastery_store.py:38-53,79-88` |
| `update_mastery()` 会更新练习时间与次数 | ✅ 源码深读 | `app/harness/mastery_graph.py:82-93`；故不能用于被动衰减 |
| 现有 API 使用 JWT + `AsyncSession` | ✅ 源码深读 | `app/api/sessions.py:13-55`、`app/core/database.py:34-36`、`app/core/security.py:41-58` |
| 旧画像表属于独立 aiosqlite 路径 | ✅ 源码深读 | `app/infrastructure/storage/mastery_graph_store.py:7-18,47-55,123-155` |
| Celery 可选依赖存在但项目未有可运行任务 | ✅ 源码深读 | `pyproject.toml:43-46`；`app/worker/celery_app.py:1-4` 仅为空壳 |
| 历史 mastery 表迁移链在干净 PG 上当前必然失败 | ✅ 源码深读 | `alembic/versions/d48d7137f57f_init_schema_with_messages_and_session_.py` 未创建 mastery 两表；`m3_unify_user_id_type.py` 先查询它们；PG 启动不 `create_all()` |
| 历史 mastery 表迁移链修复后，`review_preferences` 迁移才能成为新 head | ⏳ 本阶段明确交付 | 先补齐 mastery 两表历史迁移并在空 PG 验证，再新增 review 偏好表迁移 |

---

## 第一层：模块总览

### 1.1 目标边界

**做什么**：为每个已练习的 `MasteryNode` 在用户请求时计算“当前投影掌握度”，按用户配置筛选并排序复习建议；用户可读取、修改和关闭其复习配置。

**新栈可用性前提**：本阶段的 Review API 仅面向新栈。只有当 `FEATURE_USE_NEW_AGENT_GRAPH=true` 时，`/api/review/*` 才视为可用；flag 未开启时必须返回明确的“当前未启用新栈掌握度路径”受控错误，不能把 legacy 路径的空历史伪装成“当前无建议”。

**本阶段明确交付**：

1. **历史 mastery 表迁移链修复**：补齐 `mastery_nodes` / `mastery_edges` 在 Alembic 历史链中的创建责任，并在干净 PostgreSQL 验证升级结果与 ORM 一致。
2. 三种可配置衰减曲线（指数半衰期、线性、阶梯），纯计算且不写数据库。
3. 阈值、间隔、混合三种主动复习筛选策略。
4. 每用户、持久化的复习偏好。
5. 仅面向新栈的已鉴权 `GET/PUT /api/review/preferences` 和 `POST /api/review/trigger`，含 Feature Flag 可用性检查。
6. 单元、存储、API 集成测试；其中包含真实 SQLAlchemy 数据构造的 happy-path 与干净 PostgreSQL Alembic 验证。

**本阶段明确不做**：

- ❌ 自动调度、Celery Beat、后台 worker、推送或通知。
- ❌ 掌握度衰减的定时写回、`last_decay_date`、历史衰减快照。
- ❌ `MASTERY_DECAYED` / `REVIEW_RECOMMENDED` 事件、`EventType` / `EVENT_OWNERSHIP` 改动、Curator 订阅或同步/异步边界改动。
- ❌ 复习题目/内容生成、复习完成后的效果评估、单知识点独立衰减参数、UI 卡片/日历。
- ❌ 修改、迁移、桥接或回填旧 aiosqlite `MasteryGraphStore`、`user_profile_l3`、legacy chat 路径或 `app_old` 图。
- ❌ 在未启用新栈时，以空建议代替明确的功能不可用响应。

### 1.2 用户控制语义

| 用户动作 | 系统行为 | 不会发生的行为 |
|---|---|---|
| 新栈 flag 未开启时访问任一 `/api/review/*` | 在读取偏好、掌握图或计算建议前返回明确的受控错误 | 不读取 legacy 数据、不返回伪装成正常结果的空数组、不修改 legacy |
| `GET /api/review/preferences` | 在新栈可用前提下返回已保存配置；未配置用户返回默认值 | 不创建任务、不触发推荐 |
| `PUT /api/review/preferences` | 在新栈可用前提下校验并持久化用户配置 | 不自动查询或推送复习建议 |
| `POST /api/review/trigger` | 在新栈可用前提下以本次请求的统一 `now` 计算并返回建议 | 不写回衰减 mastery、不改练习时间、不创建后台任务 |
| 配置 `review_enabled=false` | 新栈可用时，主动 trigger 返回空建议 | 不删除掌握图、不改变用户其他偏好 |

`review_enabled` 默认 `true` 的含义仅为“用户手动调用 trigger 时允许返回建议”，**不是**开启后台自动触发；本阶段不存在自动触发路径。Feature Flag 可用性检查优先于此偏好检查。

### 1.3 技术选型：SQLAlchemy 持久化 + 请求时只读投影

| | 本方案（选它） | 备选 1：沿用旧 aiosqlite `user_profile_l3` | 备选 2：查询时将衰减写回 mastery |
|---|---|---|---|
| 做法 | 新建 `review_preferences` SQLAlchemy 表；服务读 `mastery_nodes` / `mastery_edges` 后计算投影 | 向 `data/mastery_graph.db` 的 `preferences_json` 写 `review` 子键 | 每次 trigger 后更新 `mastery_nodes.mastery` |
| 与在线路径 | ✅ FastAPI、聊天落库、掌握图均使用 `AsyncSession` / SQLAlchemy | ❌ 与在线 API 和聊天持久化是两套数据库 | ⚠️ 与 SQLAlchemy 兼容，但改变掌握度语义 |
| 正确性 | ✅ 同一用户、同一数据库；重复查询结果稳定 | ❌ API 可能读不到聊天实际写入的掌握图 | ❌ 多次查询会重复衰减；若调 `update_mastery()` 还会伪造练习 |
| 成本 | 新模型、store、迁移、测试 | 表面少写代码，实际需跨库桥接与数据同步 | 需基线/衰减时间戳设计，超出 MVP |

**选择理由**：新栈聊天 API 已将 `MasteryGraph` 持久化到 SQLAlchemy 表，复习 API 必须读取同一事实源。请求时只读投影避免把“查看建议”误记为“发生练习”，也避免衰减随查询次数叠加。

### 1.4 四层架构与数据流

```text
API
  ├─ 新栈可用性检查（FEATURE_USE_NEW_AGENT_GRAPH）
  ├─ GET  /api/review/preferences
  ├─ PUT  /api/review/preferences
  └─ POST /api/review/trigger
       ↓  Depends(get_db) + Depends(get_current_user)
Orchestration
  └─ 本 MVP 无新增节点、无事件订阅、无后台调度
Harness
  ├─ MasteryDecayService（纯函数，计算投影 mastery）
  └─ ReviewTriggerService（读取图、筛选、排序，编排但不写 mastery）
       ↓
Infrastructure / Models
  ├─ SQLAlchemyMasteryStore（保持，读取 mastery_nodes / mastery_edges）
  ├─ ReviewPreferenceStore（新建，读写 review_preferences）
  ├─ 历史 mastery 表迁移链修复（新建，先于 review 偏好迁移）
  ├─ ReviewPreferenceTable（新建）
  └─ Alembic migrations（在修复后的 head 上新增）
```

### 1.5 数据流映射

| 来源 | 中间结构 | API 响应 | 转换位置 |
|---|---|---|---|
| `MasteryNodeTable.mastery` | `original_mastery` | `original_mastery` | `ReviewTriggerService` 构造 recommendation |
| `last_practiced_at` + 本次 `now` | `days_since_last_practice` | 同名字段 | `MasteryDecayService` / service 编排 |
| 曲线计算结果 | `projected_mastery` | `current_mastery` | service 构造 recommendation |
| 触发命中原因集合 | `reasons: list[str]` | 同名字段 | service 合并 threshold / interval / 前置原因 |
| `priority_score`（小者优先） | 排序键 | `priority_score` | service 计算并按 `(priority_score, topic_id)` 排序 |

---

## 第二层：子模块概述

### 2.1 历史 mastery 表迁移链修复（新建，阻断性交付）

- **职责**：修复 Alembic 历史链缺口，使空 PostgreSQL 上的 `alembic upgrade head` 能在任何 alter 发生前创建 `mastery_nodes` / `mastery_edges`。
- **交付契约**：该交付至少要明确：
  1. 当前已验证的 revision 链与 head；
  2. 被修复的确切缺口：现有链未在 `m3_unify_user_id_type` 之前创建 mastery 两表；
  3. 修复后的不变量：空 PostgreSQL 升级到 head 时，两表必须先被创建，再允许后续修改其 `user_id`/外键；
  4. 受影响 revision 的范围与顺序；
  5. 通过证据：空 PostgreSQL 上执行 Alembic upgrade 成功，并验证结构与当前 ORM 一致；
  6. downgrade / rollback 预期；
  7. 非目标：该交付只修复 Alembic 链正确性，不在此 spec 中预设某一种具体迁移技巧。
- **验收边界**：不得以 SQLite `Base.metadata.create_all()` 成功替代该交付验收；不得把旧 aiosqlite `MasteryGraphStore` 里的同名建表 SQL 视为 Alembic 修复的一部分。

### 2.2 ReviewPreferenceTable + Alembic 迁移（新建）

- **职责**：在 API 主数据库中按用户持久化复习配置。
- **表契约**：`review_preferences` 以 `user_id: Integer` 为主键并外键引用 `users.id`；`config_json: JSON` 非空，`created_at` / `updated_at` 使用数据库时间戳。
- **配置 JSON 允许的键**：`review_enabled`、`strategy_type`、`threshold`、`interval_days`、`decay_curve`、`decay_half_life`、`decay_rate`、`decay_step_size`、`decay_step_interval`。
- **迁移前置**：只有在“历史 mastery 表迁移链修复”通过空 PostgreSQL 验证后，才能新建本表迁移；其 `down_revision` 必须指向修复后的 Alembic head。
- **错误处理**：配置 JSON 不合法或字段超界由 API schema 在入库前返回 422；数据库异常由端点 rollback 后返回既有错误语义。

### 2.3 ReviewPreferenceStore（新建）

- **职责**：封装 `ReviewPreferenceTable` 的查询与 upsert，不拥有事务。
- **接口契约**：
  - `get_or_default(user_id: int) -> ReviewPreferences`：不存在记录时返回完整默认值，**不因 GET 而写库**。
  - `upsert(user_id: int, preferences: ReviewPreferences) -> ReviewPreferences`：新增或覆盖该用户配置；新增行先 `flush()` 再按需 `refresh()`，不调用 `commit()`。
- **数据流**：上游为 review router；下游为 `AsyncSession`。
- **状态管理**：无内存缓存；事务由端点统一 `commit()` / `rollback()`。

### 2.4 MasteryDecayService（新建）

- **职责**：纯函数计算节点的当前投影掌握度。
- **接口契约**：`compute(node: MasteryNode, preferences: ReviewPreferences, now: float) -> float`，返回 `[0, 100]` 的浮点数。
- **输入适配契约**：`SQLAlchemyMasteryStore.load_nodes()` 返回 `dict[str, dict]`；`ReviewTriggerService` 必须先将每条记录显式物化为 `MasteryNode`，再调用本 service。router、store 与 decay service 不隐式共享裸 dict。
- **状态管理**：无状态；调用方每个请求捕获一次 epoch-seconds `now`，同一响应内所有节点共享该值，保证排序和测试可复现。
- **时间契约**：`t_days = max(0, (now - last_practiced_at) / 86400)`。
- **曲线**：
  - 指数（真半衰期）：`original × 2 ** (-t_days / half_life)`。
  - 线性：`max(0, original - decay_rate × t_days)`。
  - 阶梯：`max(0, original - step_size × floor(t_days / step_interval))`。
- **未练习节点**：`last_practiced_at <= 0` 时返回原 mastery；是否纳入推荐由 `ReviewTriggerService` 统一排除，避免新用户被冷启动节点淹没。
- **参数校验**：`half_life > 0`、`decay_rate >= 0`、`step_size >= 0`、`step_interval > 0`；非法值在 API schema 层拒绝，service 同时防御性抛 `ValueError`。
- **写入边界**：绝不调用 `MasteryGraph.update_mastery()`，绝不写 `mastery_nodes`。

### 2.5 ReviewTriggerService（新建）

- **职责**：读出同一用户的节点和边，计算投影掌握度，按偏好筛选并生成稳定排序的建议。
- **接口契约**：`async get_review_recommendations(user_id: int, preferences: ReviewPreferences, now: float) -> list[ReviewRecommendation]`。
- **依赖**：`SQLAlchemyMasteryStore` + `MasteryDecayService`；不依赖 Curator、EventBus、旧 `MasteryGraphStore` 或后台 worker。
- **输入过滤**：
  1. `review_enabled=false` → 立即返回 `[]`。
  2. 无节点 → `[]`。
  3. `last_practiced_at <= 0` 的冷启动节点不参与 threshold、interval、hybrid 推荐；它们应由教学冷启动流程处理，而非被伪装成“逾期复习”。
- **策略**：
  - `threshold`：`projected_mastery < threshold`。
  - `interval`：`days_since_last_practice > interval_days`；**恰好等于 `interval_days` 时不命中**。
  - `hybrid`：上述任一条件成立；若二者均命中，保留两条原因。
- **前置关系处理**：先为所有可练习节点计算投影掌握度；将 store 返回的边 `type` 显式规范化后仅接受 `PREREQ`。若候选节点存在 `PREREQ` 入边，且任一**已练习且存在于图中**的前置节点投影 mastery `< threshold`，为该候选建议追加“前置知识薄弱”原因，并降低其 `priority_score` 10 分。缺失、未练习或未知类型前置边均跳过。
- **优先级契约**：`priority_score: float`，**数值越小越优先**：
  `projected_mastery - days_since_last_practice × 0.5 - prerequisite_penalty`，其中 `prerequisite_penalty` 为 0 或 10。按 `(priority_score, topic_id)` 升序排序，`topic_id` 是稳定 tie-breaker。
- **重要边界**：服务只返回建议，不持久化 recommendation，也不修改节点、边、练习时间或次数。

### 2.6 API Schema、路由与新栈可用性（新建 / 改动）

- **Pydantic 模型**：
  - `ReviewPreferences`：上述配置字段；枚举值为 `strategy_type ∈ {threshold, interval, hybrid}`、`decay_curve ∈ {exponential, linear, step}`；数值范围由 Field 校验。
  - `ReviewRecommendationResponse`：`topic_id`、`topic_name`、`current_mastery`、`original_mastery`、`days_since_last_practice`、`priority_score`、`reasons: list[str]`。
- **端点**：
  - `GET /api/review/preferences`：仅当 `FEATURE_USE_NEW_AGENT_GRAPH=true` 时可用；返回当前用户保存的偏好或默认偏好。
  - `PUT /api/review/preferences`：仅当 `FEATURE_USE_NEW_AGENT_GRAPH=true` 时可用；校验、upsert、单次 commit，返回保存值。
  - `POST /api/review/trigger`：仅当 `FEATURE_USE_NEW_AGENT_GRAPH=true` 时可用；读取偏好和该用户掌握图，返回 `list[ReviewRecommendationResponse]`；关闭、无节点或无已练习节点时返回 `[]`。
- **新栈可用性契约**：router 在执行任何 review 业务前先检查 `use_new_agent_graph()`。若 flag 未启用，则返回明确、稳定、可测试的“当前未启用新栈掌握度路径”错误；不读取 legacy 数据，不以空数组伪装成功，也不修改任何 legacy 行为。
- **鉴权 / 隔离**：三个端点均注入 `Depends(get_current_user)`；`user_id` 仅取 `current_user["user_id"]`，不接受客户端提供的 user id。
- **事务**：GET / POST 不写库；PUT 由端点在成功时 `commit()`，存储异常时 `rollback()`。store 不自行 commit。
- **路由注册**：新建 `app/api/review.py` 的 `APIRouter(prefix="/review", tags=["review"])`，并在 `app/main.py` 以 `prefix="/api"` 注册。

### 2.7 不改动的协作层

`build_new_stack()` 当前只构造内存 `MasteryGraphStore` 供同步 Curator 在会话内修改图对象；实际 API 在会话前后以 `SQLAlchemyMasteryStore` 加载和保存图。由于本 MVP 的复习服务是请求内异步 SQLAlchemy 读路径，**不改 Curator、`CuratorBase`、EventType、EventBus 或 assembly**。这避免让同步 `Curator.handle()` 直接等待异步数据库调用的契约冲突。

### 2.8 测试兼容与新增覆盖

- **保持既有契约**：`tests/unit/harness/test_mastery_graph.py`、`tests/unit/agents/test_curator.py`、`tests/agents/test_curator_assertion.py`、`tests/unit/infrastructure/test_sqlalchemy_mastery_store.py` 均应保持通过；本期不改 Curator 的 `subscriptions` / `emittable_types`。
- **新增单元测试**：
  - 指数、线性、阶梯曲线；`t=0`、`t=365`、负时间差、`last_practiced_at=0` 与非法参数。
  - 真半衰期 happy-path：`original=80, t=7, half_life=7` 结果约为 `40`。
  - threshold / interval / hybrid、关闭开关、冷启动节点排除、同分 tie-break、前置弱项权重与缺失前置节点。
- **新增持久化测试**：默认偏好不写库、JSON 缺键与默认值合并、upsert 覆盖、不同用户隔离；真实 `AsyncSession` + `create_all` 的 SQLite 测试用于模型/类型传递。
- **新增 API 测试**：401、JWT 用户隔离、flag 关闭时三个 review 端点均返回明确的新栈不可用错误且不读取/写入 legacy、flag 开启时 GET 默认值、PUT 后跨请求 GET 持久化、PUT 校验失败、PUT 数据库异常 rollback、关闭偏好后 trigger 空列表、真实节点/边构造后的 trigger happy-path。
- **新增迁移链测试**：空 PostgreSQL 从基线执行 `alembic upgrade head`，验证 mastery 两表在任何 alter 前已存在且与 ORM 结构一致；随后验证 review 偏好写入和 trigger happy-path。不得仅跑 SQLite 单测。

---

## 第三层：子模块详细实施计划（文字描述，不含代码）

### 3.1 历史 mastery 表迁移链修复

1. 先记录并审核当前 Alembic revision 图、head 以及 `m3_unify_user_id_type` 对 mastery 两表的前置假设。
2. 设计一个与现有 revision 链顺序兼容的修复，使 `mastery_nodes` / `mastery_edges` 在任何既有 revision 对其读取或 alter 前被创建；计划文字不预设“插入旧 revision”或“重写现有 revision”等具体技术手段，实际方案须同时说明已有部署兼容和 downgrade 行为。
3. 创建后的表结构必须与当前 ORM 的列、复合主键、外键、边唯一约束和索引语义一致；不复用旧 aiosqlite store 的直接 SQL 建表定义。
4. 在生产等价 PostgreSQL URL 上，从空库执行 `alembic upgrade head`，验证修复后的链能完成，且两张 mastery 表在 M3 前置操作前已创建。
5. 该修复验收通过后，才允许创建 `review_preferences` 表迁移；该新迁移的 `down_revision` 指向修复后的 head。

### 3.2 数据模型与 review 偏好迁移

1. 在 `app/models/tables.py` 新增 `ReviewPreferenceTable`，定义每用户一行的主键和外键、JSON 配置列与时间戳列。
2. 新建 review 偏好 Alembic 迁移，建立在已修复并验证的 mastery 迁移 head 上；downgrade 删除 review 偏好表。
3. 不在旧 `user_profile_l3` 加列，不添加 `last_decay_date`，不修改旧 aiosqlite store。

### 3.3 偏好模型与存储

1. 在领域 schema 中定义带默认值的 `ReviewPreferences`；默认值：`review_enabled=true`、`strategy_type="threshold"`、`threshold=60.0`、`interval_days=7`、`decay_curve="exponential"`、`decay_half_life=7.0`、`decay_rate=2.0`、`decay_step_size=10.0`、`decay_step_interval=7.0`。
2. 将枚举与数值范围放在 Pydantic schema；存储层只处理已验证对象和 JSON 序列化。
3. `ReviewPreferenceStore.get_or_default` 查询一行并与默认值合并，兼容未来 JSON 缺键；不得在查询时创建行。
4. `upsert` 通过 `AsyncSession.get` 或等价的用户主键查询更新/新增行，刷新后返回领域对象；不调用 commit。

### 3.4 衰减计算

1. `MasteryDecayService.compute` 先钳制原 mastery 到 `[0,100]`，以注入的 `now` 计算非负天数。
2. 根据 `decay_curve` 分发三种公式；所有结果再钳制到 `[0,100]`。
3. `last_practiced_at <= 0` 返回原 mastery，不把 0 当作 Unix epoch，也不据此计算数万天的衰减。
4. service 不接收数据库 session、不保存节点，确保公式单测无需数据库。

### 3.5 推荐计算

1. 端点创建 `SQLAlchemyMasteryStore(db)` 和 `ReviewPreferenceStore(db)`，读取一次偏好并记录一次 `now`。
2. `ReviewTriggerService` 通过 `load_nodes(user_id)`、`load_edges(user_id)` 取得该用户全部掌握图数据；不新增重复的 `load_all_nodes` 接口。
3. 先对可练习节点建立 `topic_id → projected_mastery` 映射，再按策略筛选候选，确保前置判断使用同一时间点的值。
4. 每个候选累积可解释 `reasons`；hybrid 若同时命中阈值和间隔，应保留两个原因而非丢失其中之一。间隔恰好等于 `interval_days` 时不命中。
5. 基于规范化后的 `PREREQ` 入边检查前置薄弱；缺失、冷启动或未知 type 的前置边不加权，其他弱前置项计算固定 10 分 penalty；排序只使用明确的 `priority_score` 和 `topic_id`。
6. 不调用 `graph.save()`、`update_mastery()` 或任何 EventBus API。

### 3.6 API、新栈可用性与错误处理

1. 新 review router 遵循既有 API 的认证注入与 `/api` 挂载模式。
2. 在进入任何偏好读取、掌握图读取或推荐计算前，统一调用 `use_new_agent_graph()`；若结果为 false，则三个 review 端点都返回明确、稳定且可测试的新栈不可用错误。
3. GET、POST 只读；PUT 成功后单次 commit，数据库异常 rollback 并由项目既有错误处理返回失败响应。
4. 所有响应由 Pydantic response model 序列化，避免直接泄漏 ORM / JSON 内部字段。
5. 不接受 user id、存储路径、`now` 或 curve 参数以外的未验证控制字段；时间由服务端生成。
6. 不读取 legacy 图、不桥接旧库、不修改 `app_old` 路径，也不以空数组掩盖“新栈未启用”的状态。

### 3.7 验证目标（Goal-Driven）

```text
1. 指数公式确为半衰期
   verify: original=80, t=7d, half_life=7d => approximately 40

2. 同一时刻的同一节点查询不改变持久化掌握度或练习元数据
   verify: trigger 前后 mastery / last_practiced_at / practice_count 相等

3. 手动触发严格尊重用户配置与新栈可用性
   verify: threshold / interval / hybrid 分别命中预期；review_enabled=false => []；flag=false 时三个 review 端点均返回明确的新栈不可用错误

4. 冷启动节点不会被误判为逾期复习
   verify: last_practiced_at=0 的节点不出现在任何 MVP recommendation

5. 推荐排序可解释且确定
   verify: priority_score 小者在前；同分按 topic_id；弱前置项得到 -10 penalty 和原因

6. 多用户隔离与认证生效
   verify: 无 JWT => 401；用户 A 的偏好和节点绝不出现在用户 B 响应

7. 历史 mastery 表迁移链修复后，数据库迁移不是 SQLite 假阳性
   verify: 干净 PostgreSQL 上从空库执行 `alembic upgrade head` 成功；mastery 两表在任何 alter 前已创建，结构与 ORM 一致；随后 review 偏好写入 + trigger happy-path 成功

8. 旧协作契约与 legacy 路径未被破坏
   verify: mastery graph、Curator、SQLAlchemy store 的既有测试全绿；feature flag 关闭时 chat/chat_stream 仍走 legacy 测试契约
```

---

## 第四层：决策待定项（不阻断 MVP）

### 4.1 阈值策略如何处理从未练习节点

本 spec 已决定 MVP 将 `last_practiced_at <= 0` 的节点全部排除，以免冷启动内容被伪装成“逾期复习”。后续若要推荐未学内容，应单独定义“学习建议 / 冷启动”机制，而不是改变复习语义。

### 4.2 默认指数半衰期是否按主题细分

MVP 使用用户全局 `decay_half_life=7` 天。后续可评估按知识类型、题型或用户反馈设独立参数，但这需要新增配置粒度、迁移和解释 UI，不在本阶段。

### 4.3 复习建议的呈现与执行闭环

MVP 仅返回 JSON 列表。前端列表、卡片、日历、提醒推送、基于历史 chunk 生成复习材料，以及复习前后效果追踪均留待后续阶段；这些能力不得反向扩大本 spec 的 API / 数据模型范围。

### 4.4 自动提醒

如果未来确有需求，应单独提出“调度与通知” spec，先验证 Celery/Redis worker 的部署、所有权事件模型、幂等与可观测性。本 spec 不以“已有配置项 / optional dependency”推断该能力已可复用。

---

## 资产清单 + 三色（本阶段 B-②）

| 名字 | 归属子系统 | 功能（本阶段） | 触发 / 入口 | 位置 | 三色 |
|---|---|---|---|---|---|
| `MasteryNodeTable` / `MasteryEdgeTable` | Models | 已持久化的掌握节点与前置边，作为复习读取事实源 | Chat 新栈加载 / 保存；ReviewTriggerService 读取 | `app/models/tables.py:64-89` | 🟢 保持 |
| 历史 mastery 表迁移链修复 | Migration | 修复 Alembic 历史链，使空 PG 上先创建 mastery 两表再允许后续修改 | Alembic upgrade / PG 部署 gate | `alembic/versions/`（新/改） | 🔴 新建 |
| `SQLAlchemyMasteryStore` | Infrastructure | 按用户全量读取节点和边 | chat / chat_stream；ReviewTriggerService | `app/infrastructure/storage/sqlalchemy_mastery_store.py:7-88` | 🟢 保持 |
| `MasteryGraph` | Harness | 教学交互期间更新掌握图；本阶段仅复用节点数据语义 | chat 加载、协作环、persist_turn | `app/harness/mastery_graph.py:45-205` | 🟢 保持 |
| `ReviewPreferenceTable` | Models | 每用户复习配置 | ReviewPreferenceStore | `app/models/tables.py`（新） | 🔴 新建 |
| B-② review 偏好迁移 | Migration | 在修复后的 head 上创建 review 偏好表 | `alembic upgrade head` | `alembic/versions/`（新） | 🔴 新建 |
| `ReviewPreferenceStore` | Infrastructure | 读默认值、upsert 偏好 | review API | `app/infrastructure/storage/review_preference_store.py`（新） | 🔴 新建 |
| `MasteryDecayService` | Harness | 计算只读投影 mastery | ReviewTriggerService | `app/harness/mastery_decay.py`（新） | 🔴 新建 |
| `ReviewTriggerService` | Harness | 策略筛选、原因生成、确定性排序 | `POST /api/review/trigger` | `app/harness/review_trigger.py`（新） | 🔴 新建 |
| Review Pydantic schemas | API Models | 请求校验与响应序列化 | review router | `app/models/schemas.py`（改动） | 🟡 改动 |
| review router | API | 偏好 GET/PUT 与主动 trigger | `app/main.py` 挂载 `/api` | `app/api/review.py`（新） | 🔴 新建 |
| `app/main.py` | API 装配 | 注册 review router | FastAPI startup | `app/main.py:13-32` | 🟡 改动 |
| `MasteryGraphStore` + `user_profile_l3` | Legacy Infrastructure | 旧 aiosqlite 图谱/画像路径 | 旧测试及旧 UserProfile | `app/infrastructure/storage/mastery_graph_store.py:7-155` | 🟢 保持，不接入 |
| `FEATURE_USE_NEW_AGENT_GRAPH` | Runtime Flag | 仅当其为 true 时，Review API 才可用 | `use_new_agent_graph()` / `/api/chat` / `/api/chat/stream` / `/api/review/*` | `app/core/feature_flags.py:1-17` | 🟡 改动（新增 review 可用性约束） |
| Curator / EventBus / EventType | 协作流 | 本 MVP 不通过事件发起或消费复习 | 协作环 | `app/agents/curator.py`、`app/harness/events.py`、`app/harness/enums.py` | 🟢 保持 |
| Celery worker | Worker | 不在本阶段启用 | 无 | `app/worker/celery_app.py:1-4` | 🟢 保持，不接入 |

---

## 影响传播检查（本次修订）

| 修订定义 | 受影响点 | 处理结论 |
|---|---|---|
| 数据源从旧 aiosqlite 改为 SQLAlchemy | API DI、偏好表、store、测试 | 全部使用 `AsyncSession`；不再引用 `user_profile_l3` |
| 仅支持新栈 review | feature flag、review 路由、测试、rollout 说明 | flag=false 时显式拒绝；不桥接、不改 legacy、不伪装成空建议 |
| 衰减改为只读投影 | `MasteryGraph.update_mastery`、持久化、测试 | 不调用 update/save；新增“trigger 前后持久化字段不变”测试 |
| 移除自动任务和事件 | Curator、EventType、Celery、幂等字段 | 均列为保持现状；既有 Curator 严格契约无需更新 |
| 优先级统一为小者优先的 float score | schema、排序、验收 | 使用 `priority_score`；固定 tie-break；前置 penalty 使用 -10 |
| 冷启动节点排除 | 策略过滤、验收、用户预期 | 明确划归未来“学习建议”，不混入复习 |
| 历史 mastery 表迁移链修复入 scope | 模型、Alembic、PG 部署 gate、资产清单、验收 | 从“条件 gate”升级为阻断性交付；先修链再建 review 偏好迁移 |
| 新增偏好表 | 模型、迁移、API、PG 部署 | review 偏好迁移建立在修复后的 head 上 |
| Store dict 到衰减输入 | store、ReviewTriggerService、MasteryDecayService | service 显式物化 `MasteryNode`，禁止层间裸 dict 假设 |
| 边界策略与前置边数据 | interval、hybrid、排序、理由 | 明确 interval 等号不命中；未知 / 缺失 / 冷启动前置边跳过 |
