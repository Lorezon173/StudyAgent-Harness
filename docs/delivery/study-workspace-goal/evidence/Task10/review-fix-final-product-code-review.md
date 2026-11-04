# Task10 修复后独立代码审查

结论：**Needs changes**。以下问题阻断本轮批准；此报告不是功能验收或 Task10 完成结论。

## Important 1：最近会话首次加载失败后，重试成功不会恢复页面

位置：`web/src/hooks/useWorkspaceController.ts:10-19`、`web/src/store/workspaceController.ts:216-218,269-272`、`web/src/components/workspace/WorkspaceLayout.tsx:88-89`。

用户停留 `/chat` 时第一次 workspace GET 失败，`lastSession` 返回 null，恢复 effect 结束；用户点击界面的重试后，`retryWorkspace` 成功重新读取并写入 `workspace.lastSessionId`，但该 effect 不依赖该状态，也没有接收重试成功的结果重新导航。页面仍显示“开始学习”，用户的服务端最近会话不会自动打开。错误文案还将加载错误称为“最近会话未保存”。这与 Task10 原计划要求加载失败提供重试并恢复最近会话不符。需以实际路由测试首次失败、重试成功与用户在重试期间主动导航两个分支。

## Important 2：失败后查询原请求无法清理本页 linked 准备副本

位置：`web/src/store/workspaceController.ts:397-406,469-470,490-501,619-626`，`web/src/pages/Chat.tsx:36,50`。

发送时 `prepared` 以独立 `prepareId` 为键，linked 项包含另一个 `requestId`；当 POST 结果未知、之后用户通过 request 副本按原 ID 查询完成时，`recheckCandidate` 以 `candidate.itemId`（即 requestId）索引 `local.prepared`，不会取得对应的 prepareId 项。正常发送路径对 linked 副本的清理也因先前异常没有执行；完成关联只清理 request 副本。linked 候选仍使发送保持阻塞，且再次查询已 matched 请求提前返回，无法清掉它。需按完整 writer、prepareId、requestId、payload 与基线精确处理本页候选，并验证其他 writer 候选不会被删除；覆盖丢响应、原 ID 查询完成、消息关联及可继续输入的完整交错。

## Important 3：普通会话重新加载覆盖已加载的历史页

位置：`web/src/store/workspace.ts:202-204,229-233`；路由加载见 `web/src/hooks/useWorkspaceController.ts:10-11`。

用户在会话 A 上翻加载多个历史页，切到 B 后再返回 A；每次路由进入都会加载 A 的 snapshot。只要教学版本未回退，`applySnapshot` 无条件以最新一页替换已加载的全部消息，并重置 cursor 和 visited 页。较早消息从界面消失，必须重新翻页；该路径也没有验证已有消息与 snapshot 中相同 ID 的内容冲突。修复计划要求保留分页和同 ID 冲突保护，当前仅在上翻与部分完成/继续路径检测不足以覆盖此入口。应以真实路由和分页测试核实返回后的消息及游标，并测试普通 snapshot 的 ID 冲突。不能声称此问题已导致持久化丢失：本审查只证明客户端桶替换。

## 证据与边界

- 复核当前源码对 `review-fix-source-after-v3.json` 所列文件的 SHA256，未发现不匹配；独立运行的检查未改动产品源码或测试。原记录显示 46 个文件及测试前后零差异。
- 核对已有 `review-fix-freeze-suite-v3.log`：11 个文件、237 项测试通过，退出码 0；`review-fix-freeze-build-v3.log` 构建退出码 0。该证据只适用于其冻结快照，也不证明上述未覆盖交错正确。
- 已审阅原 Task10 计划、修复计划审查结论、前次代码审查及主要工作区、认证、页面、恢复和控制器路径，结合已有测试和覆盖报告检查。由于已发现阻断问题，尚不能宣称所有新增/变更代码、全部交错和后端 DTO 已逐项完整通过；修复后需按用户要求重新规划、独立审查计划、实施并重新进行最终全范围独立代码审查。
- 未执行真实浏览器、模型代理、真实数据库重启或跨账号验收；模拟测试及成功构建均不构成上述验收证据。
