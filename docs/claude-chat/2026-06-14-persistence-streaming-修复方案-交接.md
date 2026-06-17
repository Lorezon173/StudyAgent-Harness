# 会话交接文档：persistence + streaming 七项问题修复方案

> 生成时间：2026-06-14
> 用途：跨窗口接续任务。新窗口读此文档 + 设计文档即可无缝继续。
> 设计文档：`docs/designs/2026-06-14-fix-persistence-streaming-issues.md`（spec 主体，已四轮评审）

---

## 一、当前进度（读这段就知道走到哪了）

**所处阶段**：brainstorming（设计）阶段尾声，spec 已经过**四轮隔离评审**，正在收口最后 2 个待定点，之后进 writing-plans（实现计划）。

**流程位置**：
```
✅ 探索项目上下文
✅ 写 spec（docs/designs/2026-06-14-fix-persistence-streaming-issues.md）
✅ 五项决策逐个 brainstorming 确认
✅ 四轮隔离评审（reviewing-plans-isolated skill）
🔄 收口最后 2 个待定点 ← 现在在这
⬜ User Review Gate（用户最终 review spec）
⬜ 进 writing-plans 生成实现计划
⬜ 编码（批次一 → 二 → 三）
```

**还差什么才能进 writing-plans**：2 个待定点（见第四节），其中 1 个等用户最终拍板。

---

## 二、问题背景（修什么）

经正向 + 反向双组 code review，发现 persistence + streaming 模块七项问题：

**阻断级 P0：**
1. **落库静默失败**：`persist_turn` 全异常吞掉返回 None，调用方照常返回 200，用户无感丢数据
2. **连接池耗尽 DoS**：DB 连接被整个 LLM 协作环（数十秒）占用，PG pool=15，~15 并发即耗尽
3. **IDOR 越权**：全链路无鉴权，user_id 客户端可控，任意传 user_id 即可读写他人数据

**重要级 P1：**
4. SSE 中途异常截断流、无 error 事件、不落库
5. turn_index = len(existing)//2 的 read-modify-write 竞态（无唯一约束）
6. 匿名用户共享同一张 "anonymous" 图谱，互相覆盖
7. 跨线程传 db-bound graph（当前不崩，靠隐含契约）

---

## 三、五项已确认决策（brainstorming 逐个定的）

| # | 事项 | 最终决策 | 关键理由 |
|---|---|---|---|
| 1 | P0-③ JWT 排序 | **维持批次三**（不提前） | 核查确认 API 仅内网 dev（但见 M1：此前提未被仓库证据证实） |
| 2 | 匿名 mastery | **匿名不写 mastery**（N2 降级） | 原选 session_id 作 key，评审指出批次三 JWT 后变死代码、ROI 不足，降级为最简 |
| 3 | P0-⑦ 固化契约 | **`__init_subclass__` 运行时断言**，加在 Curator 专属基类 | 文档约束靠人记不住；断言 import 时即崩，零开销 |
| 4 | 故障恢复 trade-off | **容忍单次 graph 变更丢失**（A）+ 基础失误率监测 | persist 失败罕见，掌握度可恢复；监测让"丢失可观测" |
| 5 | 并发隔离 trade-off | **容忍并发高峰部分 persisted=false**（A） | 同 session 并发是罕见边缘场景，唯一约束保证数据正确性 |

**另：JWT breaking change 已写入 spec** —— JWT 上线必须前后端同步，否则前端还传明文 user_id、不带 token，全量用户 401 中断。前端改造单一出口在 `web/src/api/client.ts` 的 `request()`。

---

## 四、★ 待定点（新窗口接续要做的）

### 待定点 1：dirty-flag 存哪里（等用户拍板"生产规划"）

**背景**：决策4 的故障恢复用 dirty-flag——persist 失败时标记 user_id 脏了，下次 load 强制从 DB 重读、丢弃脏内存。问题是 flag 存哪：

| 选项 | 适用 | 代价 |
|---|---|---|
| C 内存 Set | 单进程 | 零依赖零 IO，多进程下失效（跨进程读不到） |
| B DB 字段 | 单/多进程都行 | 每轮 persist 多一次 DB UPDATE |
| A Redis | 单/多进程 | 引入 Redis 依赖 |

**已查证的事实**：
- 仓库**只有单进程证据**：README:270 唯一启动方式 `uv run uvicorn app.main:app --reload`（单 worker）
- 无 Dockerfile、无 gunicorn、无 workers=、无 K8s manifest
- 负载性质：**IO 密集**（每请求数十秒等 LLM，`collab_loop.py:9` MAX_TURNS=50），**非 CPU 密集**；阻塞 LLM 调用已用 `chat.py:27` `asyncio.to_thread` 正确移出事件循环
- **多进程连锁影响**：SQLite（当前默认）扛不住多进程写（文件锁）→ 多进程≈必须上 PG；连接池要按 worker 数重算；dirty-flag 必须进程外

**等用户回答的问题**（用户上一条已被问，尚未答）：生产规划是？
- **A. 内网/小规模/演示，无高并发计划** → 单进程 + dirty-flag 选 C（最简，PG 不强求）
- **B. 计划上规模生产（几十+并发）** → PG + dirty-flag 选 B（DB字段），避免将来踩 SQLite 锁 + dirty 静默失效
- **C. 还不确定，留余地** → dirty-flag 选 B（保守，单/多进程都能用）

**Claude 的建议**：当前阶段单进程 + 选 C（依据：IO 密集负载单进程 async 本就够、现状内网 dev、多进程是一套连锁成本不划算 YAGNI）。dirty-flag 抽象成小接口 `mark_dirty`/`is_dirty`，将来要换实现不动调用方。**但最终取决于用户的生产规划。**

### 待定点 2：Gap-2 流式端口 persist 失败感知 —— ✅ 用户已选 A

**已定**：流式端口（chat_stream.py）的 `final` 事件加 `persisted` 字段，与非流式对齐。

**背景（缝隙）**：P0-① 的"失败可感知"只在非流式 chat.py 做了（返回 `persisted=false`），流式 chat_stream.py 漏了——persist 失败时仍发 `type:"final"`，只是 turn_count 悄悄变 None，客户端无感。P1-④ 的 error 事件只覆盖"工作线程异常"，不覆盖"task 成功但 persist 失败"。

**修法（已定 A）**：流式 final 事件带 `"persisted": turn_index is not None`。不用 error 事件（因为 reply 已成功发出，persist 失败≠对话失败，发 error 会误导"整轮失败"）。

### 待定点 3：批次一估时拆细（评审第四轮 N3 建议）

批次一现含：连接窗口重构（两端点 + B2 re-bind）+ persisted 标志 + dirty 恢复 + `__init_subclass__` + 唯一约束 + alembic 迁移 + 脏数据清洗。原标"2-3天"偏乐观，writing-plans 阶段需拆开估时。

---

## 五、四轮评审的关键发现（防止新窗口重复踩坑）

评审用的是 `reviewing-plans-isolated` skill（隔离 subagent 评审，切断作者辩护链）。**关键教训：前两轮喂摘要只发现"补充类"问题，第三轮起给评审者源码访问权，立刻挖出源码级硬伤。**

| 轮次 | 关键发现 | 状态 |
|---|---|---|
| 一 | P-R1/2/3：Curator纯内存需验证、决策3需补备选、缺测试计划 | ✅ 已修 |
| 二 | P-NEW-1（备选C session校验无效，攻击者可伪造session的user_id）、P-NEW-2（故障恢复路径缺失） | ✅ 已修 |
| 三 | B1/B2/B3/B4 + M1 + N2（见下） | ✅ 已修 |
| 四 | 6项修订经源码核实**全部真闭环**，无硬阻断；剩 Gap-2/Gap-4 + 批次一偏重 | 🔄 收口中 |

**第三轮的 6 项修订（已落地，源码已验证可行）**：
- **B1**：P1-⑤ 唯一约束从批次二**提到批次一**（与 P0-② 同批）。否则批次间窗口期 Lost Update 暴露面打开但无约束兜底 → 并发静默双写
- **B2**：chat_stream 当前是**单 async with 包全程**（含 await task，非"同理"）；分段后 persist 段 `graph.save()` **必须 re-bind store 到新 session**（`graph._store = SQLAlchemyMasteryStore(db2)`，已验证 `_store` 是纯属性可外部替换，mastery_graph.py:55-57）
- **B3**：`__init_subclass__` 加 **Curator 专属基类**（只有它带 store 进线程，assembly.py:118-124 验证），不污染其它 4 Agent；已验证无元类冲突、未覆写 handle 子类不误报
- **B4**：监测埋点从 `metric()` 改走 `log()`——因 `_LangfuseObservability.metric` 是 **no-op（pass）**（observability.py:215-216），否则"dev 绿、生产瞎"。另：`_persist.py:33` 调的 `log_event` 在接口里**不存在**（只有 log），当前必抛 AttributeError 被吞 → persist 失败彻底静默，此 bug 在修复范围
- **N2**：匿名图谱从 session_id 作 key **降级为匿名不写 mastery**（`if user_id is None: graph=None`，`_persist.py:25` 已有 `if graph is not None` 跳过 save，无需改 _persist）
- **M1**：docker-compose 只定义 db 服务、无 app 服务 → "仅内网 dev"前提**无仓库证据**，已诚实标注。决策1（JWT 排序）依赖此前提，需用户以仓库外证据确认部署拓扑

---

## 六、批次划分（当前 spec 状态）

| 批次 | 含问题 | 工期 | 内容 |
|---|---|---|---|
| 批次一 | P0-①②⑦ + P1-⑤ | 2-3天（偏乐观，待拆） | 连接窗口 + 失败可感知 + 监测 + 纯内存断言 + 故障恢复 + 唯一约束 |
| 批次二 | P1-④⑥ | 1-2天 | SSE 异常事件 + 匿名不写 mastery |
| 批次三 | P0-③ | JWT简化版 5天 | JWT 签发+校验+过期（不含刷新/撤销，留 phase 2）+ 前后端同步改造 |

---

## 七、关键文件地图（新窗口快速定位）

| 文件 | 作用 | 本方案改动 |
|---|---|---|
| `app/api/_persist.py` | persist_turn 原子落库 | 失败不再静默 + 修 log_event bug + 失误率监测 |
| `app/api/chat.py` | 非流式端点 | 连接分三段 + persisted 字段 + store re-bind |
| `app/api/chat_stream.py` | 流式端点 | 拆单 async with 为两段 + final 加 persisted（Gap-2）+ SSE error 事件 |
| `app/api/profile.py` | 用户统计 | JWT 鉴权（批次三） |
| `app/agents/curator.py` | 掌握图谱维护 | 加 CuratorBase + __init_subclass__ 断言 |
| `app/agents/base.py` | AgentBase（ABC） | CuratorBase 继承此 |
| `app/harness/observability.py` | 可观测性抽象 | 复用 log()（metric 是 no-op 别用） |
| `app/harness/mastery_graph.py` | MasteryGraph | 加 _dirty 标志 + dirty-flag 接口 |
| `app/orchestration/assembly.py` | 协作环装配 | build_new_stack 已支持 graph 参数 |
| `app/models/tables.py` | MessageTable | 加 UniqueConstraint(session_id, turn_index, role) + alembic 迁移 |
| `web/src/api/client.ts` | 前端请求单一出口 | JWT 时注入 Authorization header |
| `web/src/store/auth.tsx` | 前端登录态 | JWT 时存 token（当前只存 user_id） |

---

## 八、新窗口接续指引

1. **先读** 本文档 + `docs/designs/2026-06-14-fix-persistence-streaming-issues.md`（spec 主体）
2. **问用户** 待定点 1 的生产规划（A/B/C），据此定 dirty-flag 方案
3. **补 spec**：把 dirty-flag 决策 + Gap-2（已定A）+ 批次一估时拆细写进 spec
4. **可选**：再跑一轮 reviewing-plans-isolated 验证收口（给评审者源码访问权）
5. **User Review Gate**：请用户最终 review spec
6. **进 writing-plans** skill 生成实现计划
7. **编码**：批次一 → 二 → 三

**注意事项**：
- 项目有 Stop hook 每轮提醒检查根 README（设计文档改动通常无需更新 README，一句话说明即可）
- 项目有 karpathy-code-gate：写代码前需载入 `andrej-karpathy-skills:karpathy-guidelines` skill
- spec 路径用了项目惯例 `docs/designs/`（非 superpowers 默认的 `docs/superpowers/specs/`）
