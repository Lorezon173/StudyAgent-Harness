# Task10 第一轮主产品代码审查

结论：**Needs changes**。本报告基于尚未提交的工作区快照；以下两项均阻断批准。审查没有覆盖所有要求，不能将未列问题视为已通过。

## Important 1：离开后返回原会话，已取消的发送仍会执行

位置：`web/src/store/workspaceController.ts:373-398`，`web/src/store/workspace.ts:156-159`。

触发：在 A 输入并发送，暂停准备 snapshot；切到 B，再在 snapshot 返回前切回 A。`setActiveSession` 只更新当前 ID，没有使准备序号失效；snapshot 返回后 `send` 只检查当前 ID 是否为 A，未检查中途离开或捕获的 request/prepare sequence，因此继续创建请求并 POST。用户已离开该准备过程，返回 A 后可能看到原文仍在而请求却被发送，违背 v1.2 的切走即取消约束。`web/src/pages/Chat.test.tsx:865` 覆盖在 B 时释放响应，不覆盖 A→B→A。应让路由变化使准备票据永久失效，并以真实 Provider 的延迟请求测试此交错。

## Important 2：消息关联覆盖较新的会话及教学状态

位置：`web/src/store/workspaceController.ts:480-503`，另见 `:518-525`。

触发：完成请求的关联流程读取版本 N 的 snapshot，等待后续消息分页时，同一会话另一加载先应用版本 N+1；分页返回后，第 503 行无比较地用旧 snapshot 覆盖 session、teachingState、profileSummary、teachingStateVersion。它还没有同步更新 teachingStateSource，可能使来源与内容不一致。较新的教学进度、画像摘要和活动会话状态可被回退。继续未关联请求的第 525 行同样直接覆盖 snapshot 数据，缺少与当前版本的比较。应分别按教学版本及画像 revision 合并，并测试延迟分页与并发新 snapshot 的顺序。

## 证据与规格符合性

- HEAD 为 `6d5829303f639e50ca15b11a9c8f79ee093caff1`；检查过 Git 状态与变更概况，并识别未跟踪的 hooks、Chat 测试、localRecovery 和 controller。计划文件 SHA256 为 `0d7d3199e975ee44e5d4e979100ed23a7012a296d790eab6535db12505e82c51`。
- 清单 SHA256 为 `03e86a90e145c63d9868d027c1fe8e38d3800af7b9c463613c376ea1a0dd979f`；审前及审后分别对其列出的 46 个文件计算 SHA256，均无不符。审查未修改源码和测试。
- 原始前端日志记录 11 文件、151/151 通过，构建日志显示类型检查和构建成功，两个退出码文件均为 0；后端原始日志记录 84 passed、pytest_exit=0。它们是技术证据，不是本次重新执行的结果，也不是浏览器、真实模型或 PostgreSQL 验收。
- 实施报告承认最后续轮先修改产品再补测试，偏离先 RED 后实现；原始 `round2-contract-final-green.log` 实际为 71 通过、2 失败，后续 `green2` 为 73 通过。不可将首份日志的文件名视为通过证据。
- 已抽查账号过渡备份、请求状态合并、完成关联、发送准备、部分分页和技术日志；上述两项明确不符合批准的计划。不能据此断言其余条目符合。

## 未判断项与限制

尚未逐行完成所有新增文件、完整 tracked diff、所有测试和后端 DTO/事务契约的独立复核；账号与多 writer 隔离、所有三源交错、存储异常和退出全项门禁、阅读位置、跨页游标的全组合及 UI 可用性均未作完整结论。未运行真实模型、浏览器或数据库验收。修复后需针对最终冻结清单重新完成独立代码审查，包括上述未判断项，再进行独立真实验收。README 更新由主会话在交付阶段处理。
