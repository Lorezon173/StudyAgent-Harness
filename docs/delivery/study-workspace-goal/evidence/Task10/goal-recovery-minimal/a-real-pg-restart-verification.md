# Task10 A 专用 PostgreSQL 重启前后数据核验（2026-11-03）

范围：仅 `studyagent-goal-test-pg` 和子库 `task10_acceptance_0a18749452c047689fb7e0f95f033323`。主会话事先核验专用 purpose 标签、仅本机 55440 映射、专用卷仅该容器使用；本次再次核验标签、端口、4 个请求均 completed 和客户端。

首次保护检查因容器看到客户端地址 `172.17.0.1` 而非预设地址主动停止，没有执行重启。只读核实本机到 55440 的三个连接均为隔离后端 PID 61032，容器内对应既有空闲 PG backend PID 94、102、126，Docker 网桥来源为 172.17.0.1；再次检查时仅有这三个已核实连接，且自有检查连接已退出后执行重启。

主机 UTC 时间：快照开始 15:43:57.949，指定容器 restart 调用 15:43:58.067–15:43:59.359，`pg_isready` 接受连接后新建连接完成复查 15:43:59.920。容器重启后状态 running；后端 `/health` 和前端代理 `/health` 均 200。健康接口不代替数据库读取。

新连接重启前后以稳定排序的 JSON 对以下字段计算 SHA-256，均为 `c088ef71f050848bed95b891c62de3006077bda8b7388d30f13cf0a09ef58ac5`：A 会话 ID、state_version、next_turn_index、active_request_id；4 个请求的 ID、状态、attempt、base_state_version、完整保存响应；A 和 B 会话所有消息的 ID、会话、角色、轮次、正文；B 视图会话 ID、完整草稿、版本。重启前断言 A 有 4 个 completed 请求、8 条消息、state_version 4 且无 active request，B 无消息且草稿与指定原文完全相等；重启后全字段指纹一致。对比原始数据仅保存在内存，不输出凭据。

应用本人 API 重连读取由主会话通过已登录真实浏览器单独验证，未在本记录中预先声明通过。跨账号 API 结果是在数据库重启之前取得，见 `a-real-cross-account-api.md`，不宣称重启后复测。未重启其他容器、删除库或卷。

## 重启后真实页面观察（主会话）

主会话报告：通过此前已登录的真实浏览器重新加载应用后，A 会话显示原有 8 条消息，B 会话恢复精确草稿。页面证据为 `a-real-after-pg-a.txt` / `a-real-after-pg-a.png` 和 `a-real-after-pg-b.txt` / `a-real-after-pg-b.png`。这是主会话的应用页面观察，与上面的 PostgreSQL 新连接全字段指纹核对分别记录；本人 API 原始响应的独立核对仍待完成。
