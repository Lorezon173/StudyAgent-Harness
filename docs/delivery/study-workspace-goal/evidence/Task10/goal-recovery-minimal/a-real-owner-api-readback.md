# Task10 A 重启后本人 API 读取核验（2026-11-03）

以本轮专用测试账号在隔离服务通过实际 auth/login 登录，认证信息只在调用进程内，进程结束后不保留；业务原始 JSON 见 `a-real-owner-api-responses.json`，不包含登录响应或认证字段。首次检查脚本因误把画像详情的嵌套 profile 当作顶层而出现 KeyError，未生成证据；核接口结构后重新只读请求，以下是成功一轮的结果。

重启后：A session、snapshot、messages，A 的 4 个独立 request，B snapshot，以及绑定 profile 实际 HTTP 均 200。对照专用 PostgreSQL 新连接读取：

- A session 和 snapshot 的 session ID 与目标一致，snapshot state_version=4。
- messages 和 snapshot 中 8 条消息的 ID、角色、轮次及完整正文逐条与数据库一致。
- 4 个请求的 request_id、status、attempt、base_state_version 和完整 response_json 与数据库逐项一致。
- B snapshot 的草稿及版本与数据库一致，B 消息列表为空；profile ID 一致。

上述请求发生于 PostgreSQL 重启后，是本人的真实应用 API 重连读取；与先前数据库新连接指纹及主会话页面观察分别记录。跨账号 API 检查仍仅在重启前进行。没有发送模型问题或重启服务。
