# Task11 真实画像评分与来源跳转（2026-11-04）

## 主会话真实浏览器观察

主会话从会话 B 点击画像，页面携带 B 的 session 参数；实际显示 REV2、已评估平均 100%、覆盖 1/2（50%），一个节点 100、练习 1 次，另一节点待评估，关系为空。页面显示真实来源消息 3 和对应请求，链接指向会话 A（`browser-profile-scored.png`）。点击来源后回到 A，看到两轮真实教学的四条消息（`browser-source-jump.txt` / `.png`）。

## HTTP 和 PostgreSQL 核对

真实本人 API 重新读取画像 summary 和 B snapshot 均 HTTP 200；B 绑定目标画像，summary revision=2、mastery_score=100、assessed_count=1、total_count=2、assessment_coverage=0.5、edges=[]。来源指向 A `540992e2-b031-4990-a8f9-46ddf86773f0`、请求 `b91db917-d9b2-4d99-807f-af9a62140f83`、消息 ID 3。此前两轮 HTTP 响应 `real-source-turn2.json` 显示 detail/summary 同 revision，评分节点 mastery=100、practice_count=1，另一节点 mastery=null、practice_count=0，A 消息 ID 1–4。

专用 PostgreSQL 只读 join 确认来源 ID `065d178e-b2a1-436f-a24f-a7b3201e17d7` 关联该 session/request/message/node，消息角色 user、请求 completed、画像 revision=2；详见 `real-source-teaching-verification.md`。来源由两轮真实模型教学生成，未直接向数据库写入评分。

本次确认真实空关系展示与来源跳转，不证明非空关系展示。浏览器其他尺寸和故障场景分别记录。
