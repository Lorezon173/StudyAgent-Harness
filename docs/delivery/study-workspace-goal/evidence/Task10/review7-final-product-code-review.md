# Task10 第七轮独立代码审查

结论：**Needs changes**。以下并发路径尚需业务测试复现，不能将模拟测试称为真实功能验收。

## Important：已有冲突时，两次重查仍可使旧成功覆盖新冲突

位置：`web/src/store/workspaceController.ts:766-777,794-815,840-866`；界面重查入口 `web/src/pages/Chat.tsx:52`。

请求已经是 `inconsistent` 后，用户连续两次点击“重新查询”，两次 `confirmCompleted` 捕获的 `initial.association` 都是 inconsistent；第一次历史页延迟，第二次先获得可信的消息内容矛盾并继续记录 inconsistent。此后第一次返回与旧快照匹配的消息时，`associationCurrent` 中仅拒绝“当前 inconsistent 而启动时非 inconsistent”，所以该检查仍通过，成功分支可将请求改成 matched 并触发本页副本清理。第七轮已覆盖“启动时尚无冲突，较新操作首先发布冲突”，不能证明两个重查均在已有冲突状态启动时的顺序安全。该场景直接涉及已批准的“新可信冲突优先于旧成功”，同时必须保留较新 503 后旧成功可恢复的规则。

这是一条基于 UI 与代码的可达路径推导，**本审查未运行该交错**；应先用真实页面、两个受控消息页和完整候选身份记录实测，分别验证较新可信冲突、网络失败及来源失效，避免用简单“只允许最新成功”掩盖有效恢复。

## 待核对：空结果与可证明内容冲突的分类

`workspaceController.ts:840-842,867-873` 将目标回合 user/assistant 数量为零、重复或内容不符统一归为 `AssociationMismatch`。第七轮 raw 明确将空结果与可验证内容矛盾区分；但用户可见后果及后端已持久化记录完全缺失时原计划期望的语义仍需结合服务端一致性和实际响应确认。本审查未运行该场景，不据此断言发生数据丢失或另行扩大阻断。

## 已核查证据及限制

- `review7-conflict-red.log` 记录原实现的旧成功覆盖新冲突，`review7-conflict-green.log`、`review7-revalidate.log` 及 `review7-cursor-green.log` 覆盖相应修复、用户顺序重查与游标/网络失败对照。第七轮新增冲突重查入口保留原请求查询，不自动重复 POST。
- `review7-writer-characterization.log` 在一个真实页面用两个不同 writer 候选验证新来源消失后有可见警告和可点击的剩余来源重查；它未穷举读取失败、覆盖和不同 payload/baseline 的所有组合，也不证明跨浏览器存储原子性。前轮双 Provider 测试是模拟 Storage 证据。
- 对照 Task10 原计划与既有审查，复核账号代次、最近会话、历史、画像、关联状态、恢复副本和活动门禁主要实现；发现上述阻断后，不宣称其余所有行为和后端事务均已完整证明。
- 独立重算 `review7-source-after.json` 中 46 项当前哈希，差异 0；核对 `review7-final-suite.log`：11 文件、362 项通过、退出 0，`review7-final-build.log` 构建退出 0。本审查未重跑全量测试。
- 真实浏览器、模型问答、persisted=true 与消息读取、PostgreSQL 重启及跨账号拒绝仍须在最终完整独立审查通过后单独验收。
