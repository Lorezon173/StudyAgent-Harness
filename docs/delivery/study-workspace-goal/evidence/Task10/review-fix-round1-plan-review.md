# Task10 修复计划独立审查

**结论：NEEDS REVISION，禁止按当前计划编码。** 本次仅审查计划与相关实现及 DTO，未修改产品代码、测试或计划文件，未运行功能验收。原首轮产品审查明确尚未完成全量审查；本结论也不代表其余实现已通过。

## 阻断项

1. **教学版本不能判定活动请求的新旧。** 计划第 29、31、34、58–60 行及 raw 的教学字段成组规则允许相等版本接纳整个 `session`。但 `app/infrastructure/storage/chat_request_store.py:75-83` 领取请求只设置 `active_request_id`，不递增 `state_version`。旧空闲快照可与新运行快照具有相同教学版本；延迟的 `confirmCompleted` 或 `continueUnassociated` 因相等版本覆盖 `session.active_request_id`，可能擦掉新活动真值。仅检查 pendingRequests 也不能证明活动真值，因为它和 session 可经不同请求更新。须明确活动请求独立的接纳与保守门禁规则，覆盖相同教学版本的新活动与旧空闲及完成、查询交错，确保旧出口不能解除新请求的发送门禁；不能假设相等教学版本的整个 session 可互换。

2. **同版本分页会丢历史消息和游标。** 计划第 56–60 行仅要求教学快照较旧时保留消息与游标；但 `web/src/store/workspaceController.ts:197-211` 的上翻会更新消息、游标和已访问游标，且不改变教学版本。继续操作 snapshot 等待期间上翻成功，旧 snapshot 即使版本相等也会按计划的安全接纳替换消息页和游标，丢掉刚加载历史并破坏分页进度。须设计独立的消息及分页变化票据或明确安全合并规则，连同 visitedMessageCursors、在途页及重复 ID 冲突处理；以真实延迟 snapshot 与同版本上翻交错验证消息、游标单调和后续分页可用。

3. **确认关联与现有消息冲突未定义。** 计划第 31、34 行要求去重排序并保留冲突 ID 语义，但 `workspaceController.ts:489-493` 只检查本次获取的 found 内冲突，`:502` 则用旧结果覆盖当前桶同 ID 消息。并发新 snapshot 或分页可能先接纳同 ID 不同内容，旧确认会覆盖而仍标记匹配。须在最终原子合并中同时校验当前桶与找到消息的同 ID 内容，冲突时保留现有数据、不得错误匹配或清除副本，并以可观察行为测试该交错。

## 其他审查结果和边界

- `WorkspaceLayout.tsx:33-40` 对会话、`/chat` 和其他路径均经 `syncRouteSelection`（`workspace.ts:293` 别名）更新选择；计划第 41–45 行的 epoch 思路可覆盖已提交的路由变化，但测试应明确包含离开聊天到画像/知识库、浏览器历史、默认路由和同账号 generation，并验证多个连续准备与异常分支不影响新请求。不得只测 A→B→A。
- `web/src/types.ts:75,86` 显示 session 教学版本、活动请求 ID 与 request attempt 独立；画像 revision 来自 summary/profile，计划的独立比较方向合理，但同版本完整 session 等价假设已被阻断项 1 推翻。
- 计划保留真实 fetch/MemoryRouter 与先 RED 后 GREEN 的方向；修订后需针对以上每种业务交错验证旧代码实际 RED，再验证修复 GREEN，不用直接写 store 状态代替真实路径。相关错误与副本清理也需在原 request/attempt 仍匹配时受保护。
- 计划第 61 行要求最终冻结清单完成完整独立代码审查，与原代码审查的未判断项一致；只有该审查 PASS 后才可执行原计划真实浏览器、后端和持久化验收。当前不作真实验收。

## 文件完整性

审前和审后 SHA256 相同：raw `fc93c165744e8ca43e62eb57a64f01c3fcd109c63353c463863f354ccc602a81`；实施计划 `9d3d086f6e2fb6f441cba8e6382346a8f8cbb84c1984d15d84addcb758a3f453`。本报告仅覆盖上述关键交错与相关路径，未声称对完整产品实现或 DTO 完成全量代码审查。
