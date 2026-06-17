# 修复方案：persistence + streaming 七项问题

> 创建时间：2026-06-14  
> 状态：✅ 5项决策已确认（见末尾决策记录），ready 进 writing-plans  
> 基于：正向 + 反向双组 code review 发现（最近 5 提交 e15a9d8^..HEAD）

## 资产清单 + 三色血缘

| 名字 | 归属 | 功能 | 位置 | 本方案影响 |
|---|---|---|---|---|
| `persist_turn` | API 落库 | 原子落库一轮 | `app/api/_persist.py` | 🟡 改：失败不再静默 |
| `chat` 端点 | API | 非流式对话 | `app/api/chat.py:19` | 🟡 改：连接窗口+失败感知 |
| `chat_stream` 端点 | API | 流式对话 | `app/api/chat_stream.py:23` | 🟡 改：连接窗口+异常事件 |
| `get_profile` | API | 用户统计 | `app/api/profile.py:12` | 🟡 改：鉴权（依赖前置） |
| `ChatResponse` | schema | 响应模型 | `app/models/schemas.py:12` | 🟡 改：加 `persisted` 字段 |
| `MessageTable` | 表 | 消息表 | `app/models/tables.py:24` | 🔴 加唯一约束（问题5）|
| `get_db`/`async_session` | DB | 连接工厂 | `app/core/database.py:31-36` | 🟢 用，不改 |
| `Curator.handle` | Agent | 掌握图谱维护 | `app/agents/curator.py:37-136` | 🟢 验证纯内存（见附录A） |
| 认证体系 | — | **不存在** | `auth.py` 无 token | 🔴 **新建（问题3 前置）** |

---

## 问题清单（code review 发现）

### 阻断级（P0）

1. **落库失败被全异常吞掉 → 业务成功但静默丢库，仍返回 200**  
   `persist_turn` 全异常捕获返回 None，调用方据此设 turn_count=None 照常 200，用户无感。
   
2. **DB 连接被整个 LLM 协作环占用 → 低并发即连接池耗尽 DoS**  
   连接从请求进入握到 persist 结束（含数十秒 LLM 协作环），PG pool=15，约 15 个并发慢请求占满池。
   
3. **全链路无鉴权 + user_id 客户端可控 → IDOR 横向越权**  
   端点无 auth 依赖，user_id 全来自客户端（body/路径），任意传 user_id=7 即可写他人图谱、读他人统计。

### 重要级（P1）

4. **SSE 中途异常（服务端故障/客户端断连）→ 截断流、无 error 事件、不落库**
5. **turn_index = len(existing)//2 的 read-modify-write 竞态**：并发重复 turn_index，MessageTable 无唯一约束。
6. **匿名用户共享同一张 "anonymous" 图谱 + 双标识割裂**：所有匿名用户 mastery 互相覆盖。
7. **跨线程传 db-bound graph（当前不崩，但靠隐含契约）**：Curator 行为变更可能触发跨 loop AsyncSession。

---

## 优先级分组 + 批次划分

> **B1 修订（评审命中的时序漏洞）**：P1-⑤（唯一约束）从批次二**提到批次一**。原因：P0-②（连接窗口，批次一）的并发安全**依赖** P1-⑤ 唯一约束兜底 Lost Update。若 P1-⑤ 留在批次二，则"批次一上线→批次二上线"的窗口期内 P0-② 已打开 Lost Update 暴露面、但兜底约束未落地 → 并发写同 turn_index 不报错而**静默双写**，比改造前更糟。故二者必须同批。

| 批次 | 包含问题 | 特征 | 预计工期 |
|---|---|---|---|
| 批次一（P0-①②⑦ + P1-⑤） | 1/2/7/5 | 局部小手术 + 唯一约束迁移（与 P0-② 同批，B1） | 2-3天 |
| 批次二（P1-④⑥） | 4/6 | SSE 改造 + 匿名修复 | 1-2天 |
| 批次三（P0-③） | 3 | 独立 feature，安全敏感 | JWT简化版 5天（phase 1） |

---

## P0-① 落库静默失败 → 让失败可感知

**决策：响应加显式 `persisted: bool` 字段，失败时 false。**

| | 本方案（显式标志位） | 备选A（失败抛500） | 备选B（维持静默） |
|---|---|---|---|
| 做法 | persist_turn 失败 → 响应 persisted=false | 落库失败整个请求 500 | 不动 |
| 代价 | 客户端需读新字段 | LLM 已生成 reply（已花钱）被 500 吞掉 | 数据悄悄丢，排障地狱 |
| 收益 | reply 不浪费，客户端可感知重试 | 无（双输） | 无（当前状态就是问题） |

**选择理由**：reply 已生成（成本已付），因落库失败而 500 是双输。显式标志位让客户端能感知"这轮没存上"，同时不浪费已生成内容。

**改动**：
- `app/models/schemas.py`：`ChatResponse` 加 `persisted: bool = True`
- `app/api/chat.py` / `chat_stream.py`：按 `turn_index is not None` 回填
- `app/api/_persist.py`：预期内冲突（如问题5的唯一约束冲突）和非预期异常分别处理，但都返回明确 None

**旧客户端兼容**（评审建议 S-1）：响应加 `X-API-Version: 2` 头，旧客户端若不认该版本则降级返回 500（宁可失败也不给假象）。

**故障恢复路径**（评审P-NEW-2要求补充）：
- **问题**：persist_turn 失败时，内存 graph 已被 Curator 修改（如 mastery+=0.1），若不清理下次 load 会不一致。
- **方案**：内存 graph 不回滚，记录 dirty flag。persist 成功时清除 flag；失败时保留 flag，下次该 user_id 的请求 load 时跳过 cache、强制从 DB 重建干净 graph。
- **实现**：
  - `MasteryGraph` 加 `_dirty: bool` 标志，协作环修改后设为 True
  - `persist_turn` 成功时清除 `graph._dirty = False`
  - 失败时不清除，响应 `persisted=false`
  - **多进程部署方案**（评审B-NEW-1）：dirty flag 需跨进程共享
    - 选项A（若已有Redis）：dirty flag 存 Redis `SET dirty_users:<user_id> 1 EX 3600`，所有进程共享
    - 选项B（无Redis）：graph 表加 `dirty: bool` 字段，persist 成功时 UPDATE 清除
    - 选项C（单进程部署）：内存缓存 `_dirty_users: Set[str]` 即可
    - **部署假设**：默认多进程（uvicorn workers=4 或 K8s replicas≥2），建议选B（DB字段）。若确认单进程部署可选C简化。
  - 下次请求 `graph.load()` 时检查 dirty（从 Redis/DB 读），若 dirty 则强制重新 load
- **trade-off**：容忍单次请求的 graph 变更丢失（用户视角：这轮对话"没被记住"，下次重新教），换取简单的恢复机制。若要零丢失，需实现内存 graph 的回滚（复杂度高）。

**失误率监测（选A：基础埋点，brainstorming 已定）**

> "容忍丢失"的前提是丢失可被观测。复用现有 `app/harness/observability.py` 的 Observability 抽象（已有 `metric()` / `log()` / `session_summary()`），不新造监测框架。目的：积累失误率数据，为"后续是否升级到零丢失回滚方案"提供数据驱动依据。

- **⚠️ 先修现存 bug（前置）**：`_persist.py:33` 调用了 `get_observability().log_event(...)`，但 `Observability` 接口（observability.py:62-86）**没有 `log_event` 方法**，只有 `log(level, event, context)`。当前这行会抛 AttributeError，被外层 `except Exception: pass`（_persist.py:35）吞掉——**导致 persist 失败目前彻底静默，连日志都没记**。必须改成 `obs.log("error", "persist_error", {...})`，否则监测代码自身是坏的。
- **⚠️ B4 修订：埋点必须走 `log()` 而非 `metric()`**。原因：`_LangfuseObservability.metric`（observability.py:215-216）函数体是 `pass`（no-op），生产配 Langfuse 时所有 `metric()` 调用**静默丢弃**；只有 `log()` 在三个实现里都非 no-op。若埋点走 metric()，会出现"dev（Console）监测正常、生产（Langfuse）失误率无数据"的最危险情形。故关键计数一律走 `log()`。
- **埋点清单（基础 A，全部走 log）**：
  1. persist 成功：`obs.log("info", "persist_success", {"endpoint": "chat"|"chat_stream", "session_id": ...})`
  2. persist 失败：`obs.log("error", "persist_failure", {"reason": "integrity_conflict"|"db_error"|"other", "session_id": ..., "error": ...})`
  3. dirty 恢复：下次 load 检测到 dirty 强制重建时，`obs.log("warn", "graph_dirty_recovered", {"user_id": ..., "session_id": ...})` —— 记录"丢了一轮变更"的事件
- **可回答的问题**（通过日志聚合）：失误率 = persist_failure 条数 / (persist_success + persist_failure)；失败构成（reason tag）；丢失轮数（graph_dirty_recovered 计数）
- **不做（留给数据证明必要后）**：每次 graph 变更量、丢失的具体 mastery delta、按用户聚合（方案B，需改 graph 核心结构，YAGNI）
- **告警阈值**（呼应监控章节）：基于日志聚合的 persist_failure 比例 > 5% 告警
- **遗留提示**：`metric()` 在 Langfuse 实现里是 no-op 属现存设施缺陷，本方案绕开（用 log），不在本次范围修；若后续要用 metric 做指标，需先补 `_LangfuseObservability.metric` 实现。

---

## P0-② 连接池耗尽 → 缩短连接持有窗口

**决策：把"持有 DB 连接"和"跑 LLM 协作环"在时间上分开——协作环期间不占连接。**

**根因核实**（评审要求）：连接从请求进入一直握到 persist 结束，中间数十秒 LLM 协作环纯属空握。PG pool_size=5+max_overflow=10=15，15 个并发慢请求占满池。

| | 本方案（分段持有） | 备选（扩大连接池） |
|---|---|---|
| 做法 | load 用短连接释放；协作环不持连接；persist 新开短连接 | pool_size 调大 |
| 代价 | chat.py 改掉 `Depends(get_db)` 长持有；依赖 Curator 纯内存操作（见附录A验证） | 并发再高仍耗尽，PG 后端连接数有上限 |
| 收益 | 连接占用时长从"整个协作环（数十秒）"降到"两次毫秒级 DB 操作" | 治标，把崩溃点后移 |

**选择理由**：同样连接池能扛的并发量提升几个数量级。扩池只是后移崩溃点，不解决"空握"根本浪费。

**分段改造细节（B2 修订，补现状描述 + store re-bind）**

两个端点当前状态不同，改造方式不同：

- **chat.py 现状**：用 `Depends(get_db)` 注入一个请求级 db，从进入握到 persist 结束全程持有。
- **chat_stream.py 现状**：`generate_new` 内**一个** `async with async_session() as db:` 包裹了**整个流主体**——含 `await task`（数十秒协作环，chat_stream.py:55）。注释自承"自开独立 session，生命周期贯穿整个流"。改造不是"同理"，而是要把**一个 async with 拆成两个**（load 段、persist 段），中间 `await task` 不在任何 session 上下文内。

- **chat.py 改造**：分三段
  ```python
  async with async_session() as db1:
      graph = MasteryGraph(user_id=key, store=SQLAlchemyMasteryStore(db1))
      await graph.load()
  # 出 with → db1 已释放，graph 是纯内存对象
  result = await asyncio.to_thread(run_new_agent_session, ..., graph)
  async with async_session() as db2:
      graph._store = SQLAlchemyMasteryStore(db2)   # ⚠️ B2: 必须 re-bind 到新 session
      await persist_turn(db2, ..., graph=graph)
  ```
- **chat_stream.py 改造**：把单个 `async with` 拆成 load 段 + persist 段，`await task` 在两段之间裸跑（不持连接）。persist 段同样 re-bind store。
- **⚠️ B2 核心坑（两端点都踩）**：graph 在 load 段用 db1 构造（`store=SQLAlchemyMasteryStore(db1)`），但 db1 出 with 即关闭。persist 段 `graph.save()` 若仍用 graph 内的旧 store（绑 db1），会在已关闭连接上操作 → 报错或静默失败。**必须在 persist 段把 `graph._store` 替换为绑定 db2 的新 store**。这一步是分段方案的必踩坑，writing-plans 阶段须落实。

**改动**：（见上方分段改造，含 B2 的 re-bind 步骤）
- **与问题7联动**：graph load 出来后在协作环（工作线程）用，但连接已释放。依赖 Curator 纯内存操作（附录A已验证），load 完释放连接、graph 作为纯内存对象进线程安全。

**性能基准对比**（评审建议 S-2）：实施前压测对比——当前(长连接) vs 改后(短连接) 在 100QPS/500QPS 下 P99 延迟。若短连接劣化>20%，考虑混合策略（关键路径短连接 + pool 扩到20）。

**并发隔离性保证**（评审P-NEW-2要求补充）：
- **问题**：load 和 persist 分两次短连接，中间窗口（协作环跑 20 秒）若有并发请求写入，persist 时可能基于过期数据（Lost Update）。
- **验证 PG 隔离级别**：
  - 当前默认 READ COMMITTED（PostgreSQL 标准）
  - load session: `SELECT * FROM messages WHERE session_id=X` 读到 turn_index=5
  - 协作环跑 20 秒期间，并发请求写入 turn_index=6
  - persist session: `INSERT messages (turn_index=6)` → 与刚写入的冲突
- **解决方案**：依赖问题5的唯一约束（`UniqueConstraint(session_id, turn_index, role)`）。
  - 并发写相同 turn_index 会触发 IntegrityError
  - `persist_turn` 捕获后返回 None → 响应 `persisted=false`
  - 客户端可选重试（此时 load 会读到最新 turn_index）
- **trade-off**：容忍并发高峰时部分请求 `persisted=false`（需客户端重试），换取无需分布式锁的简单架构。若要零冲突，需引入 Redis 分布式锁或乐观锁（version 字段）。
- **监控指标**（配合问题1）：`persisted=false` 比例 > 5% 告警，若持续高说明并发冲突频繁，需考虑扩池或乐观锁。

---

## P0-③ 无鉴权 IDOR → JWT 简化版（5天快速方案）

**前置事实**：`auth.py:19-24` login 不签发 token，项目无任何识别请求者的机制。

**决策（二次修订）：JWT 简化版（仅签发+校验，不含刷新/撤销），5天可上线。**

### 三选项对照（二次修订后）

| | 备选A'（JWT简化版）⭐ | 备选A（JWT全套） | ~~备选C（session校验）~~ |
|---|---|---|---|
| 做法 | login 签 JWT(仅 exp+user_id) + `get_current_user` 依赖校验，端点加 Depends | login 签 JWT + 刷新/撤销/密钥轮换 | ~~端点内查 session.user_id == body.user_id~~ |
| 工期 | **5天可上线** | 10+天（含刷新token机制+blacklist） | ~~3天~~ |
| 阻断越权 | ✓ 真阻断（基于不可伪造JWT） | ✓ | ~~✗ 无效（攻击者可伪造session的user_id）~~ |
| 长期可维护性 | ✓ 可迭代（后续加刷新/撤销为phase 2） | ✓ 标准方案 | ~~✗ 推倒重来~~ |

**选择理由（二次修订）**：
- **备选C已被证伪无效**：隔离评审P-NEW-1指出——攻击者可在创建session时伪造user_id（chat端点调persist_turn时若session不存在会创建，user_id来自请求body），"用session.user_id校验req.user_id"等于"用客户端可控字段A校验A的副本"，无安全价值。
- **备选A'（JWT简化版）是有效+快速的折中**：去掉JWT全套的复杂部分（刷新token、撤销blacklist、密钥轮换），仅实现核心（签发+校验+过期），工期从10+天压缩到5天，强于备选C的"3天假修复"。

**JWT简化版范围明确**（评审建议S-NEW-4）：
- **包含**：
  - login 端点签发 JWT（payload含 user_id + exp，HS256签名）
  - `get_current_user` 依赖函数：验签 + 检查过期 + 提取 user_id
  - chat/profile 端点加 `Depends(get_current_user)`，用 token 里的 user_id 覆盖 body 里的
  - 密钥配置（env变量 JWT_SECRET_KEY）
- **不包含（留给 phase 2）**：
  - 刷新 token（refresh_token）
  - 撤销 blacklist（远程登出）
  - 密钥轮换
- **理由**：phase 1 目标是"阻断当前IDOR越权"，最小集即可上线。刷新/撤销是用户体验增强，不影响"能否阻断越权"。

**阶段拆分**：
- **phase 1（JWT简化版，5天）**：签发+校验，阻断越权
- **phase 2（后续独立feature）**：刷新token、撤销、密钥轮换

**改动（phase 1）**：
- `app/api/auth.py`：login 端点增加 JWT 签发逻辑（`jwt.encode({"user_id": ..., "exp": ...}, SECRET)`），回填 `AuthResponse.token`
- 新建 `app/core/security.py`：`get_current_user(token: str = Depends(oauth2_scheme))` 依赖函数，验签+提取user_id
- `app/api/chat.py` / `chat_stream.py` / `profile.py`：端点签名加 `current_user: dict = Depends(get_current_user)`，用 `current_user["user_id"]` 覆盖请求里的 user_id
- `app/core/config.py`：加 `JWT_SECRET_KEY` 环境变量（开发用随机值，生产从 secrets manager 读）

**⚠️ 硬约束：JWT 是前后端协同的 breaking change，必须同步上线**（评审追加）

> **背景**：当前是"假登录"——`auth.py` login 不签发 token（`types.ts:22` 证实 token 字段恒 null），前端仅把 user_id 数字存入 localStorage（`auth.tsx:30`），chat 调用时把明文 user_id 放进 body（`Chat.tsx:30`），后端无条件信任。这正是 P0-③ IDOR 的根源。

- **真实影响（不是"匿名用户"小问题）**：JWT 上线后端口会 401 拒绝所有无有效 token 的请求。**若后端上了 JWT 而前端没同步改，所有已登录用户的 chat/profile 立即全量 401 中断**——因为前端还在传明文 user_id、不带 token。
- **正常前端流程本就强制登录**：`App.tsx:18` 的 `RequireAuth` 已要求 `userId !== null` 才能进 chat 页，所以"匿名用户"在正常前端流程里不存在，只来自绕过前端的直接 API 调用。
- **前端改造清单（phase 1 必须同步完成）**：
  1. `web/src/store/auth.tsx`：login 时存后端返回的 token（不再只存 user_id）；logout 清除 token
  2. `web/src/api/client.ts`：`request()` 是所有请求的单一出口（已确认），在此统一注入 `Authorization: Bearer <token>` header
  3. `web/src/types.ts`：`AuthResponse.token` 已有字段（恒 null），改为实际使用
  4. 401 处理：`client.ts` 捕获 401 → 清除本地 token → 跳转 `/login`（token 过期场景）
- **上线策略（避免全量中断）**：
  - 方案1（推荐，dev 环境）：前后端同一次部署，原子切换。dev 环境无外部用户（已确认），可接受短暂不一致。
  - 方案2（若将来有外部用户）：后端灰度——`get_current_user` 先做成"有 token 验签、无 token 回退到 body user_id 并记 warn"的过渡期依赖，前端全量升级后再切成强制。
- **既有测试改造**：所有调 chat/profile 的 `tests/` 需补 token fixture（签发测试 token 或 mock `get_current_user`）。

**当前暴露面判断**（已确认）：核查 docker-compose/部署配置确认 API 仅内网 dev、无外部用户，越权暴露面极小，故 P0-③ 维持批次三排序（不提前）。上线用方案1（前后端原子切换）。

**可接受的替代方案**（若项目方拒绝JWT，评审B-NEW-2要求补充判据）：

| | JWT简化版⭐ | IP白名单 | VPN隔离 | 临时API Key |
|---|---|---|---|---|
| 工期 | 5天 | 0.5天（nginx配置） | 1天（若已有VPN） | 2天（生成+校验逻辑） |
| 阻断IDOR | ✓ 真阻断 | ✓（仅内网可访问） | ✓（仅VPN用户可访问） | ✓ 真阻断 |
| 可迭代性 | ✓ phase 2扩展刷新/撤销 | ✗ 长期方案需推翻 | ✗ 长期方案需推翻 | △ 可迁移到JWT |
| 适用场景 | 所有（内外网） | **仅内网dev** | **仅内部员工** | 内部测试+少量beta |
| 选择条件 | 团队有FastAPI+JWT经验 | API确认不对外暴露 | 用户都是公司员工 | 用户<20且可控 |

**选择指南**：
- 若API已有/计划有外部用户 → 只能选JWT简化版或临时API Key
- 若API仅内网dev → IP白名单最快（0.5天）
- 若API仅内部员工 → VPN隔离（假设已有VPN）
- 若团队无JWT经验 → 临时API Key（2天，后续可迁移到JWT）

---

## P1-④ SSE 中途异常 → yield error 事件

**决策：`generate_new` 内 try/except 包 `await task`，捕获后 yield error 事件。**

| | 本方案（yield error） | 备选（维持截断） |
|---|---|---|
| 做法 | try/except 包 await task，捕获后 yield `{"type":"error"}` 事件再正常结束 | 让异常直接截断流 |
| 代价 | 客户端需处理 error 事件类型 | 客户端无法区分正常/崩溃，且不落库 |

**改动**：
- `app/api/chat_stream.py`：`generate_new` 内 `try/except` 包 `await task` 及之后，捕获后 yield `{"type": "error", "code": "...", "message": "...", "retryable": false}`
- `finally` 确保工作线程结果被消费（客户端断连场景）

**error 事件 schema**（评审建议 S-5）：
```json
{"type": "error", "code": "PERSIST_FAILED"|"AGENT_ERROR"|"...", "message": "...", "retryable": false}
```

---

## P1-⑤ turn_index 竞态 → 唯一约束 + func.count()

**决策：MessageTable 加 UniqueConstraint + persist_turn 计数改 func.count()。**

| | 本方案（唯一约束） | 备选（分布式锁） |
|---|---|---|
| 做法 | 表加 UniqueConstraint(session_id, turn_index, role) + 计数改 func.count() | Redis/分布式锁 |
| 代价 | 需 alembic 迁移；冲突后回 persisted=false 语义（需问题1先落地） | 引入 Redis 依赖，复杂度高 |

**改动**：
- `app/models/tables.py`：`MessageTable.__table_args__` 加 `UniqueConstraint("session_id", "turn_index", "role")`
- `app/api/_persist.py`：计数改 `await db.scalar(select(func.count()).where(MessageTable.session_id==...))`，不再 `SELECT *` 整表
- **迁移前脏数据检查**（评审建议 S-3）：
  ```sql
  SELECT session_id, turn_index, role, COUNT(*) as cnt
  FROM messages
  GROUP BY session_id, turn_index, role
  HAVING COUNT(*) > 1;
  ```
  若有结果，先人工清洗（如保留最新 created_at 的记录）

**冲突重试策略**（评审要求明确）：IntegrityError 捕获后立刻返回 persisted=false，不重试（因为 turn_index 已被占，重试无意义）。

---

## P1-⑥ 匿名用户图谱共享 → 匿名不写 mastery（N2 降级）

**决策（N2 修订，从 session_id 作 key 降级）：匿名请求不写 mastery。**

| | 本方案（匿名不写）⭐ | 原选择（session_id作key，已弃） |
|---|---|---|
| 做法 | `if req.user_id is None: graph=None`，不构造 MasteryGraph、不 save | `f"anon:{session_id}"` 作图谱 key |
| 修 P1-⑥ bug | ✓ 根本不写，无从污染 | ✓ 每 session 独立 key |
| 实现成本 | 一行判断 | 图谱 key 逻辑 + 测试 + 孤儿清理 backlog |
| 收益寿命 | — | 匿名单 session 跟踪，但**批次三 JWT 后变死代码** |
| 遗留负债 | 零 | 孤儿数据 + 批次三后一坨死代码 |

**N2 降级理由（全局视角）**：
- 决策1（JWT，批次三）上线后无 token 一律 401，"匿名用户"概念在系统里消失——session_id 作 key 产出的匿名图谱逻辑从那刻起永不执行（spec 原行已自认"死代码"）。
- 两方案**都修了 P1-⑥ 的共享污染 bug**（必须项），降级不损失安全性。
- session_id 方案真正服务的对象，仅是"批次二→批次三过渡期内、绕过前端直接调 API 且不传 user_id"的边缘请求（正常前端 `App.tsx:18` RequireAuth 已强制登录，无匿名）。为又窄又边缘且 3 天寿命的能力投入图谱逻辑+测试+孤儿清理，ROI 不足（YAGNI）。

**改动**：
- `app/api/chat.py` / `chat_stream.py`：`if req.user_id is None: graph = None`，跳过 MasteryGraph 构造；`persist_turn` 也不传 graph（graph=None 时 persist_turn 内 `if graph is not None` 已跳过 save，无需改 _persist.py）
- **关键**：消除"所有匿名用户共享同一张 anonymous 图谱"的污染——匿名干脆不碰图谱
- 无孤儿数据、无死代码、无 backlog

---

## P1-⑦ 跨线程传 db-bound graph → 固化纯内存契约

**与问题2联动后天然改善**：load 完释放连接，graph 进线程时已是纯内存。

**附加改动（评审建议 P-R1-②，已定方案：运行时断言；B3 已定影响半径）**：

**加在 Curator 专属基类**（B3）——不加在 AgentBase。判据：只有 Curator 携带 db-graph 进工作线程跑协作环，其它 4 个 Agent（Tutor/Critic/Retriever/Conductor）构造时不带 store、不进线程（assembly.py:118-124 已验证）。若加在 AgentBase 会过度约束无关 Agent。`__init_subclass__` 在子类定义（import）时检查 `handle` 不是 `async def`：

```python
# Curator 专属基类（或在 Curator 定义处用 __init_subclass__ 钩子）
import inspect

class CuratorBase(AgentBase):   # Curator 继承此类
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if inspect.iscoroutinefunction(cls.handle):
            raise TypeError(
                f"{cls.__name__}.handle 必须是同步方法（不能 async def）——"
                f"它会被传入工作线程跑协作环，async+db 会跨事件循环崩溃。"
                f"db 操作请放在主循环的 load()/save()。"
            )
```

- **选择理由**：相比文档约束（靠人/AI 记得 review），`__init_subclass__` 在 import 时即检查、零运行时开销、违反者立刻崩溃。这是"沉默杀手"型隐患（违反后偶发难复现崩溃），值得用代码强制。
- **已知局限（诚实标注）**：① 只能拦"把 handle 直接改成 async def"，拦不住"同步 handle 里调内部同步方法、而它间接触发 db"；② writing-plans 阶段需验证 Curator 当前继承结构能否插入 CuratorBase 这一层，以及对"未覆写 handle 的子类"行为（评审 B3 盲区，需 5 行脚本实证 TypeError 真的抛）。

---

## 测试计划大纲（评审要求 P-R3）

### 批次一（P0-①②⑦ + P1-⑤）

| 测试目标 | 策略 | 工具 |
|---|---|---|
| P0-①：persisted 字段正确回填 | 单元测试：模拟 persist_turn 返回 None，验证响应 persisted=false | pytest |
| P0-①：失误率监测埋点 | 单元测试：persist 成功/失败时验证 `obs.log` 被调用（FakeObservability 断言）；确认走 log 非 metric | pytest + FakeObservability |
| P0-②：连接池不耗尽 | 并发压测：locust 100并发持续1分钟，验证无 pool timeout | locust + PG `pg_stat_activity` |
| P0-②：graph store re-bind（B2）| 单元测试：分段后 persist 段 graph.save() 用新 session 成功（不在已关闭连接上操作） | pytest |
| P0-⑦：Curator 纯内存不触 db | `__init_subclass__` 断言（已定）：定义 async def handle 的子类应在 import 时 raise TypeError | pytest |
| P1-⑤：竞态 UniqueConstraint（与 P0-② 同批，B1）| 并发测试：pytest-xdist 并发写同 session_id，验证 IntegrityError → persisted=false | pytest-xdist |

### 批次二（P1-④⑥）

| 测试目标 | 策略 | 工具 |
|---|---|---|
| P1-④：SSE error 事件 | 单元测试：mock 工作线程抛异常，验证 yield error 事件 | pytest + SSE client |
| P1-⑥：匿名不写 mastery（N2）| 单元测试：user_id=None 时验证 graph=None、不调 save、不污染任何图谱 | pytest |

### 批次三（P0-③）

| 测试目标 | 策略 | 工具 |
|---|---|---|
| JWT简化版：签发+校验 | 单元测试：mock user_id=7 签发token，另一请求带该token验证提取出user_id=7 | pytest + TestClient |
| JWT简化版：过期token被拒 | 单元测试：签发exp=now-1小时的token，验证get_current_user抛401 | pytest |
| JWT简化版：伪造token被拒 | 单元测试：用错误密钥签token，验证get_current_user抛401 | pytest |
| 端点鉴权接线 | 集成测试：不带token调chat/profile验证401；带user_id=7的token访问验证只能写该user的数据 | pytest + TestClient |
| 既有tests改造 | 既有tests/需补token fixture（mock get_current_user或签发测试token） | pytest |

---

## 落地顺序建议

1. **批次一（P0-①②⑦ + P1-⑤）**：2-3天。连接窗口 + 失败可感知 + 失误率监测 + 固化纯内存契约 + 故障恢复路径 + **唯一约束（与 P0-② 同批，消除 B1 时序漏洞）**。
2. **批次二（P1-④⑥）**：1-2天，SSE 异常事件 + 匿名不写 mastery。
3. **批次三（P0-③）**：
   - **phase 1（JWT简化版）**：5天可上线，阻断越权（仅签发+校验+过期，不含刷新/撤销）
   - phase 2（JWT增强）：独立 feature，后续迭代（刷新token、撤销blacklist、密钥轮换）

---

## 附录A：Curator.handle 纯内存验证报告（P-R1）

**验证范围**：`app/agents/curator.py:37-136`（handle + _on_mastery_assessed + _on_topic_entered）

| 行范围 | 方法 | 是否有 await | 依据 |
|---|---|---|---|
| 37-42 | handle | ❌ 无 | 纯分派逻辑，if/return，无 await 关键字 |
| 46-96 | _on_mastery_assessed | ❌ 无 | 全是同步操作：self.graph.* + self.emit + 列表。无 await |
| 100-136 | _on_topic_entered | ❌ 无 | 同上，全是 self.graph.* + self.emit。无 await |

**关键观察**：
1. 函数签名都是 `def`，不是 `async def`（37行、46行、100行）
2. 全部操作只涉及 `self.graph`（MasteryGraph 内存对象）和 `self.emit`（同步方法）
3. `self._store`（MasteryGraphStore，唯一持有 AsyncSession）**在这三个方法里从未被调用**

**结论**：✅ Curator.handle 及其调用链确认为**纯内存同步操作，无 await**。前提1成立。

---

## 监控/可观测性补充（评审建议 S-6 + S-NEW-1，B4 修订后）

> 全部走 `obs.log()`（生产 Langfuse 下 `metric()` 是 no-op，见 B4）。告警基于日志聚合。

- persist 成功/失败：`obs.log` 记 `persist_success`/`persist_failure`（含 reason），**失误率 = failure/(success+failure) 比例 > 5% 告警**
- 连接池：`pg_stat_activity` 侧监控（DB 层，非应用 metric），使用率 > 80% 告警
- SSE 中断：`obs.log("error", ...)` 记 error 事件，QPS > 平时 10 倍告警
- graph dirty 恢复：`graph_dirty_recovered` 日志计数 = 丢失轮数

---

**决策记录**（brainstorming 逐项确认）：

| # | 事项 | 决策 | 状态 |
|---|---|---|---|
| 1 | P0-③（JWT）是否提到批次一 | **维持原排序**（批次三）。核查确认 API 仅内网 dev、无外部用户，越权暴露面极小 | ✅ 已定 |
| 2 | 匿名用户 mastery 处理 | **匿名不写 mastery**（N2 降级）。原选 session_id 作 key，第三轮评审 N2 指出其产出物批次三 JWT 后变死代码、ROI 不足，降级为最简方案。两方案都修了共享污染 bug | ✅ 已定（N2 修订） |
| 3 | P0-⑦ 固化方案 | **运行时断言**（`__init_subclass__`，加在 **Curator 专属基类**，见 P1-⑦ 章节 B3） | ✅ 已定 |
| 4 | 故障恢复 trade-off | **容忍单次 graph 变更丢失**（A），**配套基础失误率监测**（复用 Observability，**埋点走 log() 非 metric()**，B4）。附带修复 `_persist.py:33` log_event bug | ✅ 已定 |
| 5 | 并发隔离 trade-off | **容忍并发高峰部分 `persisted=false`**（A），唯一约束（**提到批次一，B1**）保证数据正确性，冲突频率由 `persist_failure{reason=integrity_conflict}` 日志观测。同 session 并发罕见，不引入 Redis 锁 | ✅ 已定 |

**第三轮评审（读真实源码）修订记录**：
- **B1（时序漏洞，评审命中）**：P1-⑤ 唯一约束从批次二**提到批次一**，与 P0-② 同批——否则批次间窗口期 Lost Update 暴露面打开但无约束兜底，并发静默双写。
- **B2（源码矛盾）**：chat_stream 当前是单 `async with` 包全程（非"同理"）；分段后 persist 段 graph.save() **必须 re-bind store 到新 session**（两端点都踩的坑）。
- **B3（影响半径未定）**：`__init_subclass__` 断言加在 **Curator 专属基类**（只有它进工作线程跑 db-graph），不污染其它 Agent。
- **B4（生产监测断裂）**：`_LangfuseObservability.metric` 是 no-op，监测埋点改走 `log()`（三实现均非 no-op），避免"dev 绿、生产瞎"。
- **M1（前提存疑）**：docker-compose 只暴露 DB 端口、**未定义 app 服务**，无法从仓库证实"仅内网 dev"。决策1 的排序基于此前提——若实际部署拓扑不同（外网可达），P0-③ 应紧急提前。**部署拓扑需项目方以仓库外证据确认**，当前按"内网 dev"假设但标注未证实。

**JWT breaking change** ✅ 已写入 P0-③ 章节（前后端必须同步上线，否则全量 401 中断）。


