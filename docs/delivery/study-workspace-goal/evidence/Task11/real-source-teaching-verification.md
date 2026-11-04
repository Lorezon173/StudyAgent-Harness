# Task11 两轮真实教学来源准备（2026-11-04）

在 Task11 专用 PostgreSQL 数据库及隔离后端，仅通过公开教学接口对会话 A `540992e2-b031-4990-a8f9-46ddf86773f0` 执行两轮真实模型教学；未直接写入评分、边或证据，没有第三轮。脱敏响应和快照见 `real-source-turn1.json`、`real-source-turn2.json`，不保存认证数据。

初始画像 revision=1，会话 state_version=0，活动节点 `ab28edbc-5443-43e4-8c13-8359ccc336a7`，无来源。第一轮 request `5d9ee04f-4abb-4a1a-82c2-758d6ff023d6` completed、persisted=true、state_version=1，消息 ID 1、2；真实回复询问一张披萨平均分4份吃1份的分数，snapshot 确认为 awaiting_response。第二轮根据实际问题回答四分之一及理由；request `b91db917-d9b2-4d99-807f-af9a62140f83` completed、persisted=true、state_version=2，新增用户消息 ID 3、助手消息 ID 4。

第二轮真实 summary profile_revision=2、recent_evidence 1条：`065d178e-b2a1-436f-a24f-a7b3201e17d7`，关联上述会话、第二轮请求、用户消息 ID 3 和活动节点，真实评估 score=100。专用 PG 只读 join 确认关联消息角色 user、请求 completed、画像 revision=2；会话 B `565df716-fef4-4efb-8966-7158964f1b27` 仍为同画像、state_version=0、无活动节点。

该数据可用于主会话从 B 画像点击真实来源回 A；此处尚未声称页面跳转已通过。未产生非空关系边，不能将来源或评分结果替代非空边验收。模型输出为实际该次结果，不保证每次产生评分。

后续故障注入预检：Vite PID 81464 监听本机 50531，命令匹配原项目入口与端口；代理 health=200，后端 PID 50868。可按原 VITE_API_TARGET 指向本机50530重启 Vite；预检未停止任何进程。
