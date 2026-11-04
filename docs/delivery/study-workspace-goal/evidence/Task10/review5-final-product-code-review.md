# Task10 第五轮独立代码审查

结论：**Needs changes**。本审查未改产品源码和测试，也未进行真实功能验收。

## Important：同一请求的并发消息关联中，较旧失败可能回退已匹配状态

位置：`web/src/store/workspaceController.ts:765-782,792-819,834-858`；用户入口 `web/src/pages/Chat.tsx:52`。

一个 completed 请求正在 `confirmCompleted` 中向前读取消息页时，用户从“回复已保存，正在同步”处点击重新查询；`reconcile` 重新取得同一 completed 请求，可再启动一次 `confirmCompleted`，两次消息关联没有单飞或关联操作序号。如果第二次先成功，将该请求标为 `association=matched` 且 UI 请求状态标为 completed，第一次等待的消息页随后返回 503，旧 catch 仅检查请求仍为相同 completed attempt，就会把 `request.status` 改回 `pending_messages`。若旧流程抛出 `AssociationMismatch`，还可能把 matched 改为 inconsistent。此前已清理的本人副本不会因此自动恢复；前一种情况下 `reconcile` 见 matched 会直接返回，页面却仍以 pending_messages 禁用发送，可能持续要求同步。

该顺序可从代码和可点击入口推导，**本审查未执行延迟消息页业务测试**，不能表述为已线上发生。需要先在冻结版用真实 UI、两个受控关联和先成功后失败/冲突的顺序确认实际行为；再为匹配终态、请求身份、关联操作及错误发布增加适当保护，不能忽略有效的当前失败，也不能以放松真实消息验证或删除副本解决。

## 第五轮原审查问题复核

- 旧 continue 桥接失败与较新活动观察：`workspaceController.ts:913-920` 将仍有效的历史失败与请求错误分开；请求错误仅在活动 epoch 和观察序号仍相同时发布。`review5-continue-{red,green}.log` 和 `review5-inflight.log` 分别记录失败、修复及查询在途情况。
- 画像异常：`workspace.ts:14-19` 对已有 session 的可见绑定、profile 的 owner/id、summary node/edge 的 profile_id 和 pending request 身份作核验；没有按当前 session 过滤跨会话 evidence。后端 `app/orchestration/profile_service.py:149-168` 按用户和画像查询并连接证据，允许同画像其他会话来源。DTO 无 evidence 的 owner/profile，客户端不能独立证明这部分归属；模拟测试不等于数据库约束验收。
- 核对第五轮报告所列普通加载、发送、完成关联、继续、重试、活动重查和视图冲突相关身份路径及定向日志；对 null 画像与已有绑定变化按所批准规则保守处理。该核查不保证异常与账号换代等所有组合都已穷举。

## 冻结、范围及限制

- 独立重新计算 `review5-source-after.json` 所列 46 项当前哈希，差异 0；核对 `review5-final-suite.log` 为 11 文件、344 项通过、退出 0，`review5-final-build.log` 退出 0。这些是冻结产品的自动化证据，本审查未重跑全量。
- 阅读原 Task10 计划、此前审查与第五轮 raw/计划/v2 审查，复核最近会话恢复、账号票据、消息分页、请求关联、活动观察和 localStorage 多 writer 的主要路径；由于发现上述待复现阻断风险，不能宣称所有代码、异步交错及后端事务已完整通过。
- 未进行真实浏览器、模型问答、`persisted=true` 联合消息读取、PostgreSQL 重启或跨账号拒绝验收；这些验收仍须在完整独立代码审查通过后进行。
