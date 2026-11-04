# Task10 A 真实在途切换核验（2026-11-03）

主会话通过真实页面发送第四轮问题，并在切换前看到正在准备；CUA 记录切换区间为 15:39:34.961–15:39:35.034 UTC（`a-real-fourth-switch-time.json`）。页面准备状态本身不证明后端已接收。

专用 PostgreSQL 的实际请求 `336ae87e-8b21-4e31-88c5-a6852b3fee77` 保存相同第四轮问题，完成记录事务的 `updated_at` 为 15:39:40.362393 UTC，晚于切换结束约 5.33 秒，支持切换时该真实请求尚未完成。查询时该请求 completed、attempt=1、persisted=true、state_version=4。`created_at` 是数据库事务时间，不是精确接收时刻；`updated_at` 也不是精确 commit 时刻。数据库查询和 CUA 时钟来自同一测试主机与本机容器，记录未独立校准时钟。

A 会话 `0f93cb37-296e-4bea-a2e0-642ece744116` 中消息 ID 7 为用户问题、ID 8 为助手回复；SQL 比较 ID 8 正文与请求保存 response.reply 完全相同、会话 ID 相同。主会话完成后在 B 页面观察草稿精确不变且无 A 消息（`a-real-fourth-b-after.png`），回 A 后显示第四轮回复、输入可用（`a-real-fourth-a-after.txt` 与同名 PNG）。对该 AX 文本与数据库 ID 8 正文做精确包含比对，结果为 true。

B 会话 `1793fae3-b7e5-425b-9435-554b5348b243` 在数据库查询时无消息，草稿保持原文、版本 2 未变。该结果不证明数据库重启或跨账号拒绝。未重复发送、修改数据库或重启服务。
