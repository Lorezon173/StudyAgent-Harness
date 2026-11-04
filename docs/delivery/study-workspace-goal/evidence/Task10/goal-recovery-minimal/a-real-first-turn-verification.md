# Task10 A 首轮真实问答的隔离数据库核验（2026-11-03）

只读范围：专用库 `task10_acceptance_0a18749452c047689fb7e0f95f033323` 的指定会话及本次隔离后端日志，未访问其他库，未更改或重启服务。

- 会话 `0f93cb37-296e-4bea-a2e0-642ece744116`：`state_version=1`、`next_turn_index=1`，`active_request_id` 为空。
- 请求 `59e1f6cb-90ac-480a-8fe2-0e2ae18d811f`：`status=completed`、`attempt=1`、`base_state_version=0`；保存响应 `persisted=true`、`status=completed`、`state_version=1`。
- 消息 ID 1、角色 user、turn 0：`请先用生活例子说明分数的分子和分母分别是什么，不要先考我。`
- 消息 ID 2、角色 assistant、turn 0：`想象把一张披萨平均分成 4 块，拿走其中 1 块：你觉得“4”表示什么，“1”表示什么？`
- 数据库 SQL 比较确认保存响应的 reply 与消息 ID 2 正文完全相等、响应 session_id 与消息所属会话相同。页面的精确显示与数据库正文是否一致须由浏览器截图另核对，本记录不代替浏览器截图或真实 API 读取。
- 隔离后端日志有 `gpt-6-luna` 的 critic 与 tutor 两条 LLM 记录，分别耗时约 4.61 秒和 6.56 秒。用户要求“不要先考我”，回复仍提出问题；这是教学质量限制，不应掩盖。

只读命令（脱敏）：`docker exec studyagent-goal-test-pg psql -U goal_test -d <专用库> -X -v ON_ERROR_STOP=1`，按会话 ID 查询 sessions、chat_requests、messages，并将 response_json 的 reply、session_id 与消息比较；隔离服务日志仅提取 LLM 模型、节点及耗时。此结果不证明 PG 重启后持久化或跨账号拒绝。

主会话随后核对 CUA 截图 `a-real-first-reply.png`，确认页面正文与上述数据库助手正文完全一致。
