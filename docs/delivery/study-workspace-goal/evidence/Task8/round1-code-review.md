### Spec Compliance

- ❌ Issues found：HTTP 显式 retry 缺少断连通知接线，生成阶段已断开时仍可能完成并保存；位置 app/api/sessions.py:125、app/orchestration/conversation_service.py:223。对应 brief 的共享生命周期、HTTP 断连中断规则，详见 Important I1。
- ✅ 其余本任务可见实现符合：普通 HTTP/SSE 共用 prepare/claim/snapshot/run/commit；严格 JWT owner；旧 payload 重放；180/30/300 栅栏；原子提交与同节点增量；摘要与缩减元数据保存重放；切点清待答及 legacy 首轮不误评；DirtyFlag 唯一状态。证据见下文各路径和测试。
- ⚠️ 本结论是 Task8 范围审查。未验真实模型效果、公网部署、Task9 前端、完整 MVP；受控最低层 client 不作为这些项目的证明。原始完整套件发生于最终栅栏补充前，最终受影响范围和 PG 范围已另有日志。
- ⚠️ 300 秒实际是教学预算/最终提交准入检查，不是所有数据库故障下的绝对 HTTP 响应时限。该边界已专门评估，见“边界裁决”。

### Strengths

- app/orchestration/conversation_service.py:187 按保存的 profile/node/base 填补旧客户端省略项，同时比较 payload 与 hash；completed 重放无需重新规范化当前状态。tests/api/test_conversation_transactions.py:252 的两轮后切点、HTTP/SSE 重放和调用数断言覆盖这一风险。
- app/orchestration/conversation_service.py:225 使用短事务加载快照、全量消息和独立内存图，并在 :255 rollback 后退出连接；:258 才构造真实摘要/context。tests/api/test_conversation_transactions.py:306 的全量历史摘要及 checkout/checkin 断言，和 tests/integration/test_workspace_concurrency.py:83 的第三物理连接 NOWAIT 锁验证，比仅检查代码中的 async with 更有说服力。
- app/orchestration/turn_commit.py:178 按 session→profile 顺序锁定与复核；:204 校验候选状态计数，:210 校验旧题归属，:217 起父 flush 后写消息，:236 再经过 Store 的原 attempt/running/lease 栅栏。app/orchestration/conversation_service.py:310 持有唯一业务 commit。tests/api/test_conversation_transactions.py:375 在六个边界失败后重开连接检查完整回滚。
- app/infrastructure/storage/profile_mastery_store.py:141 在最新 profile/node 值上应用本轮去重 delta，:174 递增当前 count、:181 一批只增加一次 profile revision；不整图覆盖。真实 PG 的并发测试核对两次增量、两条证据与其他节点逐列不变。
- app/orchestration/conversation_service.py:284 的中断仅影响仍匹配的 running attempt；:399 在未知提交异常后优先用新事务确认 completed。tests/integration/test_workspace_concurrency.py:273、:321、:395 分别覆盖真实锁下提交先胜、实际 commit 前后抛错、旧取消不能破坏新 attempt。
- app/api/chat_stream.py:25 与 :94 在响应层及生成器 finally 清理，并使用 AnyIO shield；首 yield 前断连、重复 running 订阅无取消权和晚事件丢弃已有实际 ASGI 测试。该评价限普通 /chat 与 /chat/stream；retry 漏接见 I1。
- app/orchestration/session_service.py:247 清待答与 stage；app/orchestration/conversation_service.py:261 对 legacy 上下文保守关闭待答。tests/api/test_conversation_transactions.py:279、:730 证实不误给 B 节点/旧题打分而仍保存成功教学回合。
- app/orchestration/turn_commit.py:50 先核 owner，再由 :159 拒绝绑定 profile、任意 schema_version 键及坏 JSON；app/api/_persist.py:12 保持旧包装单向委托。app/infrastructure/storage/dirty_flag.py:11 持唯一 tuple-key 字典与锁，API 仅同对象 reexport；无 infra 反导 API/harness 的新增依赖。

### Issues

#### Critical (Must Fix)

- 无。

#### Important (Should Fix)

**I1 — [P2] 显式重试 HTTP 没有接入断连生命周期。**

- 位置：app/api/sessions.py:125；app/orchestration/conversation_service.py:216–223（建议改动定位 :223）。对照普通入口 app/api/chat.py:37–39 已建立 watch_disconnect 并传入 disconnect_event。
- 问题：retry 路由直接等待 retry_turn，retry_turn 又无 disconnect_event 调用 run_claim。普通 ASGI HTTP 的 http.disconnect 不会自动取消正在执行的 handler，因此用户在重试生成中断开时没有人消费并通知该事件；服务持续续租、生成并最终保存。不是“提交已先拿锁”的允许例外。
- 实际复现：使用项目真实 app、JWT、Service、SQLite NullPool/FK ON 和现有 candidate runner，仅把生成停在显式线程屏障。先制造一次 failed/attempt2；POST /api/sessions/s/requests/retry-disconnect/retry 领取 attempt3；线程启动后、尚未进行业务提交时发送真实 http.disconnect；持续真实 DB 轮询 0.5 秒，观察仍 running/attempt3 且 handler 未完成；放行线程后，真实 DB 为 completed/attempt3、persisted=true、消息从 2 增至 4。
- 本次唯一最小复现输出：
  - REVIEW_RETRY_AFTER_DISCONNECT_BEFORE_GENERATION_RELEASE {"status": "running", "attempt": 3} handler_done False
  - REVIEW_RETRY_AFTER_DISCONNECT_FINAL {"status": "completed", "attempt": 3, "persisted": true, "message_count": 4}
- 影响：同一教学操作首次发送与显式重试具有不同取消语义；用户中断重试后仍可能改变消息、状态版本和掌握度，与已批准的共享生命周期不符。
- 建议：让 retry 路由复用 HTTP 的断连观察与 finally watcher 清理，将通知透传至 retry_turn/run_claim（可新增内部可选关键字，不改变必需参数），仍由共享 Service 的 session 锁与 attempt 栅栏决定中断/提交胜负。补真实 ASGI retry 对照：生成屏障中断先胜无新业务消息；最终提交已持锁则 completed 可保留；不要把 handler.cancel 当作真实 disconnect 的替代。
- 现有测试为何遗漏：tests/api/test_conversation_transactions.py:625 与 tests/integration/test_workspace_concurrency.py:445 的断连参数只有 /api/chat、/api/chat/stream；retry 测试验证 payload、CAS、归属和旧 attempt，没有传输断连。

#### Minor (Nice to Have)

- 无另行要求的修饰性改动。旧 warning 与旧 retriever 失败不作为本次新缺陷。

### 旧测试迁移核对

| 原断言组 | 核对结论及位置 |
| --- | --- |
| persist_turn int/None、一次 commit、父 flush、graph、rollback、owner 重验、日志 | tests/api/test_persist_turn.py 的改动仅实现内部 patch owner 迁移至 turn_commit；原断言未放宽。新 workspace/bad JSON 零写保护在 tests/api/test_conversation_transactions.py:96、:1010。 |
| HTTP 首轮 reply/title/owner、两消息角色内容和 turn0 | tests/unit/api/test_chat_persist.py:15 同名测试以真实 JWT/DB 保留逐值断言。 |
| 第二轮四消息、0/0/1/1、原文与标题不变 | tests/unit/api/test_chat_persist.py:31 同名测试保留，并增加 persisted 检查。 |
| 第二消息失败、200/persisted=false、零消息 | tests/unit/api/test_chat_persist.py:47 改为真实第二条 INSERT 故障并检查回滚；原“失败仍返回生成 reply”按批准新契约明确改为空 reply/status=failed，不是隐藏删减。 |
| 教学 count1 不等于内部 loop11 | tests/unit/api/test_chat_persist.py:68 保留；异常旧历史索引另由 tests/api/test_conversation_transactions.py:730 覆盖。 |
| NULL/异主 403、精确 detail、模型零调用、零消息、SSE 前拒绝 | tests/unit/api/test_chat_session_ownership.py:7 共享真实 fixture 保留三原测试名和全部这些断言。 |
| anonymous 401、graph 不构造、无消息 | tests/unit/api/test_chat_anonymous.py 只迁移真实 graph patch owner/不再使用的旧路由工厂；核心断言保留。 |
| new-stack 55 分、RAG fail-fast、默认 session、真实 Agent 路径 | HTTP/SSE e2e 差异仅装配真实 Service 和合法绑定节点/待答 fixture；原结果断言保留。 |
| SSE incremental/error 事件、回复、count、无 final | tests/api/test_chat_stream_realtime.py:7、test_chat_stream_error.py:6 保留，新增 persisted/status 断言。 |
| DirtyFlag TTL/清理/旧入口 | tests/api/test_dirty_flag.py 仅 patch 到唯一状态 owner；同类/同字典/同锁与画像隔离另由 tests/api/test_conversation_transactions.py:29 验证。 |
| Task6 snapshot/retry | tests/unit/api/test_workspace_sessions_api.py 仍核 owner 前置、结束注入事务、参数与业务状态不变；过期 running 按新增恢复契约改为 interrupted，不再把永久 running mock 当作正常。 |

### 边界裁决与未扩展事项

- **DB 锁等待没有独立 timeout**：app/orchestration/conversation_service.py:350、:372 的 DB 等待和 :284 的中断清理都可能超过 300 秒；定时检查会等待它们返回，甚至延迟关闭事件入口。:313、:319 的最终提交准入与 Store 在实际查询后的当前 UTC lease 检查仍阻止已过期/超预算业务结果保存。结合 brief 允许提交先持锁胜出、要求未知 commit 先确认的语义，本审查不凭空把“任何 DB 故障下 300 秒必响应”扩成独立合并阻断；但当前实现不能这样对用户或部署验收宣称。若将来要求严格响应/清理时限，须专门设计数据库等待和未知提交恢复策略，不能只加无差别取消。
- **线程无法物理中止**：未作为新缺陷。brief 已明确 to_thread 取消不等于线程停止，当前安全承诺是事件关闭、attempt 栅栏和不提交晚结果。
- **Task9、真实模型、完整线上 MVP**：不在本次范围；未据此扣分，也未据此宣称已完成。
- **旧全套失败与 warning**：按主会话提供的 Task0 基准归因排除；实读日志确为 retriever context_precision=None 的 TypeError 和既有 StarletteDeprecationWarning，不建议借 Task8 顺手修复。
- **README**：遵从本任务明确分工，本审查不修改 README；修复通过后由主会话更新能力及已知边界。

### 核验证据和审查边界

- 基线：75be6015c331185dea34dc8910e5646c6663f29e；审查包 task8-review-package.diff。已实核 manifest 的 20 修改+5 新增文件 SHA256 全部匹配冻结清单。
- 差异按片段单遍审阅；最初工具输出截断时只补齐未显示部分，后把同一包缓存分段显示。没有重新生成 git diff、遍历全库或修改产品/测试、index、HEAD。
- 差异外命名风险检查：为确认“租约是否在真实等待后取当前时间、锁序及 attempt 原子性”，只补齐 ChatRequestStore._session/get/_running/renew/complete；为确认“legacy 清题是否真正关闭评估准入”，只查看 TeachingContext.has_pending_question 属性。未扩大到无关模块。
- 已实读 docs/delivery/study-workspace-goal/evidence/Task8/final-affected.log：268 passed，1 既有 warning，44.06s。
- 已实读 final-pg.log：18 passed，34.90s；日志含独立 backend PID、pg_blocking_pids、pg_locks 的 granted=false，及同节点 count2/node_revision2、两证据记录。
- 已实读 restart-verify-second.log：postmaster 时间从 2026-10-25 16:42:54.729894+00 变为 18:46:38.336214+00；重启后 messages4/persisted true、expired interrupted、unexpired running、foreign user403；自建测试库删除记录存在。24h lease 仅为跨审批重启夹具，不是生产租约。
- 已实读 full-suite.log 尾部：1325 passed、1 已知失败、67 deselected、1 旧 warning；不称“最终完整套件全绿”。
- 没有重跑套件。唯一新增执行是 I1 的最小真实 ASGI 复现，系统临时 SQLite、未触生产库；其首轮故意抛错用于建立 failed 状态，不误报为新产品异常。

### Assessment

**Task quality: Needs fixes**

**Reasoning:** 主事务、幂等与并发实现有可信代码和真实数据库证据，旧测试关键断言迁移完整。显式 retry 漏接 HTTP 断连已实际复现，应接入同一取消状态机并做针对性回归后再通过 Task8。
