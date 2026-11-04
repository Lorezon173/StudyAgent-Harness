# Task10 第五轮实施与验证报告

## 当前状态

第五轮按批准计划完成已复现问题修复与冻结回归，**尚未通过全范围独立代码审查，真实功能及数据库验收未执行，不能认定 Task10 完成。** 本轮未改后端、API、依赖或本地恢复存储格式；检查根 README 后认为本轮为已有恢复流程缺陷修复，无新增使用步骤或 API，保留用户既有 README/asset 改动。

## 实测与修复

- 原未关联 continue 的桥接页失败，较新活动重查已经完成但 load/request 身份不变时，旧失败覆盖请求提示：`review5-continue-red.log` exit 1。现仅在活动观察仍有效时写该请求错误，同时仍保留有效历史失败与画像独立更新；`review5-continue-green.log` exit 0。`review5-inflight.log` 覆盖较新活动查询仍在途时历史错误可见、请求错误和 checking 状态保留。
- 真实路由模拟同用户异常 p1→p2 快照，在新画像 revision 低、相同和高的三组中 session 均被错误改为 p2：`review5-profile-red.log` exit 1。客户端按已知 session 绑定及可见 DTO 身份校验，拒绝不兼容快照并提供保守重查；`review5-profile-green.log` 9 项通过，含同画像 A/B evidence 保留正例。当前页面没有渲染 evidence，本测试只证明路由可加载且 store 未过滤两条记录。
- `review5-dto-red.log` 中跨画像 node/edge 和跨用户/画像/会话 pending request 五组可见身份异常失败，跨会话 evidence 正例通过；`review5-profile-green.log` 包含上述修复后验证。summary/evidence 本身不含 owner/profile 字段，其归属依赖已认证后端查询与实际启用的数据库约束，不能声称客户端独立证明。证据节点无须存在于只包含未归档节点的 summary.nodes。
- p1 会话发送准备读取 p2 快照仍发 POST（`review5-send-red.log`）；p1 请求完成关联读取 p2 快照时误匹配消息并删除风险副本（`review5-confirm-red.log`）；修复后 `review5-confirm-green.log` 两项通过。未关联继续也会混入 p2（`review5-continue-profile-red.log`），修复后 `review5-continue-profile-green.log` 两项通过。
- 不兼容快照时活动重查错误解除门禁（`review5-recheck-red.log`），现连续冲突保持门禁、原画像有效结果可重查恢复（`review5-recheck-green.log`）。初次 null、空 summary、已有 null→p1 与 p1→null 四组 `review5-null-profile.log` 通过；迁移可以补绑定并不证明运行时支持自动改绑。
- 保存视图冲突的读取路径误展示 p2 草稿（`review5-view-red.log`）；阻止污染后又发现用户无保存重试出口（`review5-view-retry-red.log`）；`review5-view-retry-green.log` 检查原草稿、出口及正常冲突保留，exit 0。
- 原请求重试和 linked 重发读取含跨用户 pending 的快照仍继续：`review5-retry-red.log` 与 `review5-resend-red.log`；对应 green 日志均 exit 0，保留请求和原备份。本机最近会话候选的异常画像验证失败已用控制器调用复现并修复，`review5-workspace-green.log` 包含正常候选回归。
- 旧不兼容快照晚于新活动查询失败时覆盖新错误（`review5-late-activity-red.log`），修复后 `review5-late-activity-green.log` 包括新 load 成功时旧响应丢弃，两项通过。

## 冻结及限制

`review5-source-before.json` 和 `review5-source-after.json` 共 46 项，前后差异 0；`review5-final-suite.log` 11 个文件、344 项通过、exit 0；`review5-final-build.log` exit 0。所有原始失败与通过日志保留。阶段全量 `review5-interim-suite.log` 为 337 项通过，但之后有改动，不作为最终快照证据。

本轮正例和异常使用模拟 fetch/Storage；未执行真实模型、浏览器、跨账号服务端拒绝、`persisted=true` 及真实消息读回、PostgreSQL 重启验证。没有对所有交错做笛卡尔积测试：例如不同画像异常与 401、继续桥接和用户换代的组合未逐一新增测试；已有各单独账号与旧响应保护不能外推为所有组合已证明。最近会话候选测试直接调用控制器，不声称它是完整用户点击验收。请独立审查整个 Task10 的身份异常、错误时序、进入恢复及其他 writer 边界，再决定是否补测。全范围审查通过后才能进行真实验收。
