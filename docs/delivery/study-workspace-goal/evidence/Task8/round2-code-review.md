### Spec Compliance

- **原 I1：ADDRESSED。** app/api/sessions.py:126 使用共享 observe_http_disconnect，:129 将同一事件传给 retry_turn；app/orchestration/conversation_service.py:226 原样传入 run_claim。生成中真实断连、生成前已断及真实 PG 两种锁胜负均有代码和原始日志支持。
- **本轮整体：❌ Needs fixes。** 新增 helper 的首次同步探测会在确定的取消交错下吞掉 handler 的外部 CancelledError，并进入业务体（R2-N1）。违反 round2 brief A/B 的“取消继续传播、不转换成成功”要求，是本轮新增代码风险，不重开上一轮已接受的 300 秒边界。
- 范围：仅复审 round2 包中的 7 个允许文件，以及原 I1 关闭证据。未重审未改 Store、turn_commit、SSE、schema 或原事务设计；未重跑套件。

### Strengths

- app/api/_disconnect.py:10 与 :22 提供唯一观察实现，chat.py:26 和 sessions.py:126 共用；没有把 Request 或 API helper 反向导入 Service。retry 原五个必需参数不变，只增加可选事件。
- app/orchestration/conversation_service.py:218–245 把 PreparedTurn 构造后的管理 commit 与 run_claim 纳入取消边界；先退出原事务，再独立连接核 owner、running、原 attempt、active_request，随后复用 cancel_owned 的锁下重验。tests/api/test_conversation_transactions.py:729、:762、:945 覆盖入口前取消、管理 commit 实际前后和读取后已 completed/new attempt 的竞态。
- tests/api/test_conversation_transactions.py:652 在释放工作线程之前确认 interrupted4、active=None、原业务快照逐值不变；释放后再次核数据并检查晚 callback。:707 对已断开准入要求 runner 零调用。没有用 task.cancel 取代这两项真实 ASGI disconnect 测试。
- tests/integration/test_workspace_concurrency.py:273、:452 保留原 HTTP/SSE 变体并新增 retry；PG 原日志含 blocker1163、waiter1165 与 granted=false，提交先胜为 completed3/persisted=true，生成中中断先胜为 interrupted4/消息2。
- tests/unit/api/test_workspace_sessions_api.py:434 保留原 owner/503/409、事务释放及精确参数断言，只增加同一 Event 校验；tests/api/test_conversation_transactions.py:903 要求失败预检不启动 runner 或 observer，:1163 保留 Service 重验竞争后的 409 并核 watcher 已退出。
- app/api/_disconnect.py:34 先设置退出事件再 cancel/await，确实解决了 watcher 自身在 Starlette 内部取消域里丢失单次 cancel 导致的收尾挂起；:804 的 normal/error/cancel 有界测试先观察、失败后才救援，没有用救援事件伪造绿灯。此结论不覆盖首次探测的 handler 取消，见 R2-N1。

### Issues

#### Critical

- 无。

#### Important

**R2-N1 — [P2] 首次断连探测在 handler 内吞掉外部取消，随后仍进入教学业务。**

- **位置：app/api/_disconnect.py:25**（首次 await request.is_disconnected）；调用方 app/api/chat.py:26、app/api/sessions.py:126。
- **原因：** 首次探测直接运行在请求 handler 自身。当前 Starlette 的 Request.is_disconnected 内部先 cancel 一个 AnyIO CancelScope 再 await receive；外部 task.cancel 若与这个内部取消在同一检查点交错，内部取消域可吞掉异常，但外部取消计数仍保留。helper 随后创建 watcher 并 yield，业务体继续执行。finally 设置退出 event 只解决 watcher 的退出，不能补救已经被吞的 handler 取消。
- **本次最小实测（1 秒有界，无 DB）：** 使用已安装的真实 Starlette Request 和当前真实 helper，先正常消费完整 body；首次断连探测的 receive 在等待空事件前，以事件循环 callback 请求取消当前 handler。没有 mock helper/Request.is_disconnected、没有改取消计数。结果：
  - REVIEW_INITIAL_OBSERVE_CANCEL RETURNED: business body ran body_entered True cancel_requests [True] cancelling 1
  - 外部 cancel 返回 True，handler 却正常返回且业务体已进入，未传播 CancelledError。
- **影响：** 本轮把同步首次探测加到普通 /chat 与 retry 的请求协程，因而两入口都可能在外部取消后继续服务委托。已经实测的是“取消被吞且业务体运行”；本次没有再执行业务数据库提交，不把它表述成已实测消息落库。代码中该业务体分别调用 submit_turn/retry_turn，因此不能将当前 helper 宣称为保持 handler 取消语义。
- **为何现有绿灯未覆盖：** tests/api/test_conversation_transactions.py:804 的 cancel 分支等三次观察后，才取消正在 yield 业务体内等待的 work；:729、:762 则在更晚的管理提交/入口屏障取消。它们都不在首次 is_disconnected 的内部取消域期间取消 handler。
- **修复建议：** 保证首次探测也不会消耗 handler 的外部取消。例如由唯一 watcher 承担首次探测，handler 等待“首次观察完成”的独立就绪事件，再允许业务开始；创建任务和等待就绪也必须置于同一 try/finally 清理边界。也可采用能明确区分并传播外部取消的等效最小方案。保留单 receive、已断开时零 runner、normal/error/cancel 必须 await watcher 的契约；不要仅对 watcher 再次 cancel。
- **补充回归：** 在首次探测的 receive 检查点精确请求 handler.cancel，断言 CancelledError 传播、业务体/runner 零调用、无 watcher 遗留。原真实 ASGI disconnect、管理领取取消和 PG 胜负测试继续保留。

最小复现的关键交错（其余为普通 Request/body 初始化与有界任务等待）：

```python
async def receive():
    nonlocal calls
    calls += 1
    if calls == 1:
        return {"type": "http.request", "body": b"{}", "more_body": False}
    if calls == 2:  # body已消费，此次是helper首次is_disconnected
        handler = asyncio.current_task()
        asyncio.get_running_loop().call_soon(handler.cancel)
    await never.wait()

async def handler():
    async with observe_http_disconnect(request):
        body_entered.append(True)
        return "business body ran"
```

#### Minor

- 无新增修饰性要求。旧 Starlette warning、旧 retriever 失败仍按上一轮范围排除。

### 证据核验

- 已单遍读取 task8-round2-review-package.diff（全部 7 文件）、task8-round2-brief.md v1.1、manifest 及 task8-report.md 的完整 Round2 小节。brief 指定 SHA 为 74d5dadc6fba3906412a98be86799e9254cf58160f5a99c92b6ecb755fa463c5；冻结源哈希一致性由主会话独立核验，本复审核对清单与差异范围。
- 实读 docs/delivery/study-workspace-goal/evidence/Task8/round2-red.log：4 failed/1 passed，失败为真实状态断言；round2-green.log：5 passed，含 interrupted4 与未提交仍 failed2 对照。
- 实读 round2-observer-red.log：normal/error/cancel 三项明确因“需要救援才退出”失败；没有把挂起的首个主要组当成通过。原挂起/单次授权 Ctrl+C 的经过按 round2-commands.md 和实施报告保留，不要求重跑。
- 实读 round2-affected-primary-final.log：97 passed/50.53s；含 interrupted4、管理提交前后对照、completed3/new attempt5 保护、三个 watcher_done=True/single_receive1 记录。
- 实读 round2-affected-routes.log：12 passed/7.71s、1 个既有 warning；实读 round2-pg.log：20 passed/45.92s，retry 真实锁胜负数据与报告一致。
- 实读 round2-final-verification.log：7 文件编译通过、限定 diff-check exit0、剩余自建 Task8 库为空、26 文件冻结记录；未把这些日志当作本审查重新执行的结果。
- 唯一差异外代码读取：为命名风险“首次同步探测吞外部取消”，读取已安装 Starlette requests.py 的 is_disconnected 窄函数。唯一新增执行是 R2-N1 的无 DB、有界 helper 探针；没有 pytest 套件、真实模型、网络部署或产品/测试变更。
- 300 秒为教学预算/最终提交准入、DB 等待不受独立绝对响应时限约束的上一轮裁决保持不变。README 仍由主会话在修复通过后维护；本复审只写本报告。

### Assessment

**I1: ADDRESSED**

**Task quality: Needs fixes**

**Reasoning:** 原 retry 断连接线及领取取消清理已被实际代码和原始测试证明修复。新增同步首次探测存在已最小复现的外部取消吞没，应修复 R2-N1 并覆盖该精确检查点后再通过。
