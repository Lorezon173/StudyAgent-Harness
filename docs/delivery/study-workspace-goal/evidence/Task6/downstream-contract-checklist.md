# Task6 后续衔接验收清单

本清单记录已审计划的跨任务依赖，不表示实现或验证通过。

| 生产方 → 消费方 | 契约 | 后续完成证据 |
|---|---|---|
| Task6 → Task7 | 新会话 schema_version=1 初值；旧无schema字典保留 legacy_state；未知/坏状态明确冲突 | Task7恢复/序列化测试，旧历史兼容而非重置 |
| Task6 → Task8 | snapshot session→profile 共享锁；教学写事务保持同方向；生成阶段不持DB锁 | Task8真实PG并发/故障注入 |
| Task6 → Task8 | conversation_service.retry_turn(user_id, session_id, request_id, expected_attempt, expected_state_version)；当前缺能力503且不改请求 | Task8实际装配服务、真实claim/attempt/结果重放/过期与晚到栅栏验证 |
| Task6 → Task8 | retry precheck 仅读，必须结束路由事务再委托，服务短事务重验 | Task8请求期间无长锁、竞争冲突、断连恢复验证 |
| Task6 → Task10 | group cursor与session cursor独立；消息items正序、next_cursor向更旧页；pending原文独立 | 前端真实分页/恢复/失败重试显示验收 |
| Task6 → Task10/12 | view version与teaching state_version独立；workspace比例纵向位置/默认固定 | 前端退出恢复、冲突保护、拖动位置持久化验收 |

所有后续证据在对应Task完成前均PENDING；Task6局部通过不能替代真实教学或总Goal验收。
