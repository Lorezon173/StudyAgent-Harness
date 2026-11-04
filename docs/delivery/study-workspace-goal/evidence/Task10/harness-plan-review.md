# Task10 隔离验收辅助服务计划独立审查

结论：**PASS**，无计划层必改阻断。审查对象为 `docs/superpowers/plans/2026-10-27-task10-acceptance-harness.md`，审查前 SHA256 为 `93ccf6b46347650d99f79029668d967c803283202d117ceee484e48f9910b51e`，与派审值相同。本结论仅允许进入辅助代码实施，不代表辅助实现、主产品代码或真实功能验收已通过。

## 事实依据与边界

- Task10 v1.3 实际 SHA256 为 `0d7d3199e975ee44e5d4e979100ed23a7012a296d790eab6535db12505e82c51`；其第三层第6节要求独立代码审查后使用真实浏览器、真实本地后端、隔离非生产账号与数据库，并允许专用服务上的可控故障。本辅助计划保留顺序，dummy ASGI 单元测试不冒充该真实验收。
- `app/main.py` 的 lifespan 先 `init_db()`、创建 `app.state.conversation_service`，退出时 `aclose()`；`app/api/chat.py` 从该真实 state 取服务并使用 disconnect 观察器。计划要求原 ASGI lifespan、receive/disconnect 透传，配置先于 app/database 导入，能够衔接当前架构。
- `app/models/schemas.py` 的 ChatResponse 实际包含 status、persisted、session_id、request_id、attempt、state_version，但不含 request_payload；`app/models/workspace_schemas.py` 的 RequestSnapshot 才包含请求 payload、归属、版本和 response_json。计划只据真实 completed/persisted=true 回包决定人工丢响应，完成事实与消息仍由真实请求查询/读取证明，没有用 ChatResponse 冒充 payload 证明或合成模型成功。
- `app/core/database.py` 在模块导入时创建 engine/sessionmaker；SQLite foreign_keys 必须在 lifespan 首次连接前注册，计划规定配置在导入前且启用 pragma，设计可行。`app/core/config.py` 存在默认 .env 设置，实施需确保强制独立 DATABASE_URL 与 RAG_ENABLED 的进程内优先级真正生效；本计划已明确这一结果契约。

## 逐项结论

1. **三层规划充分。** 已列目标、依赖、仅两新增源码文件的边界、配置和控制职责、计数字段范围、函数输入输出、状态消费、错误及测试。没有要求更改业务 API、模型、前端或共享配置。
2. **专用服务与控制鉴权充分。** 127.0.0.1 独立端口、随机强 token、constant-time 比较、仅本地控制调用、无效凭据不变状态、禁止向浏览器传控制 token 均明确；真实正常业务与非目标路径透传。人工 PATCH 503 在命中故障时不进入业务本身是已声明的故障模拟，不是正常鉴权/保存通过证据。
3. **数据与凭据边界充分。** DB/control 路径 resolve 后限专用 runtime，拒绝外跳和旧数据库；已有库只复用不重置，已有凭据只在校验后复用不覆盖。env 只消费指定模型白名单，不输出密钥、token、原文。当前 .gitignore 已忽略 `.superpowers/`。README 仍由 Task10 主会话按原总计划负责，无需本辅助越权修改。
4. **响应故障语义充分。** 必须等待真实内层执行完成，仅真实成功且 completed/persisted=true 才可消费并替换；真实失败、非持久化、异常均不得制造成功。只缓冲当前目标 chat 响应，最多2MiB，超限完整重放已缓冲分段后透传，不截断；其余响应仍流式透传。
5. **有限计数与并发约束充分。** 有严格字段/类型/大小/body限制；同步原子消费、不跨 await、每请求绑定模式及并发不得误消费是明确实施不变量。chat 消费须在真实成功确定后实施，并发完成仍必须复核可用计数，不能出现负值或多于设定次数的替换。此为既定约束的落地检查点，不新增功能范围。
6. **测试可验证。** RED/GREEN覆盖控制权限、schema/body上限、精确路径方法、消费/恢复、业务未调用、真实内层完成后503与读回、失败不消费、超缓存退化、异常、lifespan/receive、路径拒绝无文件副作用及合法复用；冻结两文件与日志后再独立审查。实现审查应核实这些测试真的驱动 ASGI lifespan（httpx 请求本身不等于已执行 lifespan），并覆盖多分段缓存与并发完成的有限消费。

## 执行限制

本次只读计划与后端契约并写本报告，没有实现辅助代码、修改计划/产品源码、启动服务、调用真实模型或运行浏览器功能验收；没有修改其他执行者的 web 文件。后续仍须辅助实现独立代码审查及 Task10 产品独立代码审查均 PASS 后，才进入真实功能验收。最终报告须把人工注入503、真实模型生成、持久化读回和用户实际收到响应分别记录，不能宣称 Task13 的 PostgreSQL 重启验收已完成。

审查后复核计划 SHA256：`93ccf6b46347650d99f79029668d967c803283202d117ceee484e48f9910b51e`，与审查前一致。
