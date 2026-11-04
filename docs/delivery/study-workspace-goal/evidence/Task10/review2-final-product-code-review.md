# Task10 第二轮修复独立代码审查

结论：**Needs changes**。当前快照存在下述阻断；修复后仍须对整个 Task10 独立复审，不能进入真实功能验收。

## Important：历史桥接失败会丢弃独立画像与活动观察

位置：`web/src/store/workspaceController.ts:174-204,337-360`，输入门禁见 `web/src/pages/Chat.tsx:56` 和 `web/src/store/workspaceController.ts:631-632`。

用户已有会话历史，重新加载时服务器 snapshot 含更高画像 revision 和其他请求 running，但最新页与旧页不重叠；取桥接页时网络失败、游标无效或发现消息冲突。`connectSnapshotHistory` 抛出 `HistorySyncFailure`，调用方只保留旧历史、写历史错误并将加载状态改为 ready；此时不会将 snapshot 的画像或活动请求独立合并，也不把原空闲门禁设为待确认。结果是界面继续呈现旧画像及空闲状态，允许编辑和尝试发送。发送准备会再次核查服务器 snapshot，因此这里不能直接断言一定产生第二次 POST；问题是已观测到的活动状态和独立画像被历史失败一起丢弃，违反第二轮 raw 对历史失败保留分页、其他字段独立处理及活动保守门禁的要求。应补真实控制器/路由测试，对照更高画像 revision、running 快照、桥接错误、保留历史前沿及发送门禁，并处理旧观察/账号换代竞态。

## 需业务复现：POST 后请求查询被较新活动观察取代

位置：`web/src/store/workspaceController.ts:163-171,629-635,656-657,666-681`，`web/src/store/workspace.ts:219-224`。

静态路径显示：发送设为 preparing，产生独立 requestId 后不改状态；POST 返回后发起 GET，若用户切回同一会话产生较新 load，GET 因观察序号变化抛 `StaleObservation`，发送流程直接 return。若新 snapshot 已不包含 completed request，load 也不会为它安排 running 轮询；现有 UI 可能继续显示“正在准备”且禁用发送，直到手动查询。该场景属于代码推导，**本审查未执行其交错测试**；需用真实路由和延迟 GET 验证，不将此条表述为已实测故障。修复须保留较新观察，不能以旧 GET 覆盖新状态。

## 已核查项和证据范围

- 原三项：读取重试新增了区分读取/写入及 location key、账号和选择序号核验；linked 清理新增按独立 prepareId 与完整候选核验；返回旧会话新增连续历史桥接与冲突检查。对应 `review2-workspace-retry-green.log`、`review2-linked-green.log`、`review2-history-return-green.log` 的定向测试均显示退出 0。这些结果只覆盖日志所列用例，不等于完整契约通过。
- 阅读了第二轮 raw、计划、独立计划审查 v3 和第一轮审查报告；核查路由恢复、认证票据、恢复副本、活动观察、历史桥接和主要消息写入路径，并比对现有测试。鉴于发现阻断，此轮尚不能宣称全部代码、交错及后端事务契约已完整验证。
- 独立重算 `review2-source-after.json` 中 46 项当前文件哈希，差异为 0；原始 `review2-final-suite.log` 为 11 文件、285 项通过、退出 0，`review2-final-build.log` 退出 0。此审查没有修改产品代码或测试，也没有重新执行全量测试。
- 未进行真实浏览器、真实模型问答、数据库重启或跨账号验收；模拟 fetch、Storage 与构建日志不构成这些验收证据。
