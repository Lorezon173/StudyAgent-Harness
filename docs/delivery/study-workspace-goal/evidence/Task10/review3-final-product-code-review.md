# Task10 第三轮独立代码审查

结论：**Needs changes**。产品源码与原冻结快照一致，但送审后测试文件发生变化，原全量测试证据不再对应当前完整快照。本轮不得进入真实功能验收。

## Important：较新加载成功后，旧的继续操作仍可写入历史错误

位置：`web/src/store/workspaceController.ts:866-883,902`。

`continueUnassociated` 的桥接页在途时，同会话较新的 `loadSession` 完成并保持同一个 unassociated 请求及 attempt；旧桥接页随后返回 503。`historyTicket` 的 load sequence 已过期，所以 `applySnapshot` 会拒绝旧结果，但异常继续抛到外层 catch，后者只检查 request ID、sequence、attempt 与 association，不检查 load sequence 或活动观察，仍会设置旧 `historySyncError` 和请求错误。较新的历史同步成功后可能出现过期失败提示，违反第三轮计划关于旧加载错误不得覆盖新结果的要求。该路径由源码推导，本次未执行该交错；需按实际路由和网络顺序做业务复现，修复时同时保留请求、账号和活动门禁。

## 待验证：教学版本与 session 版本可能脱节

位置：`web/src/store/workspace.ts:243,267-270,281-283`。

当同一个加载请求仍为最新 load，但其活动观察被较新的活动查询取代（`activityCurrent=false`），而它携带较新的教学 state_version，成功路径保留旧 `session` 却接纳新 `teachingState`、source 和 `teachingStateVersion`；历史失败路径也存在同样组合。因此可能出现 `session.state_version` 与教学版本不同。原第一轮计划要求 session、教学状态、来源与版本成组一致，同时不得覆盖较新的活动锁。此处是静态推导而非已执行的真实交错；应补测试判断可达性，并在必要时将最新教学字段和已有活动字段安全组合，不能简单覆盖较新活动状态。

## 计划测试和冻结证据缺口

- 第三轮 raw/计划明确要求自动重查期间请求被替换、较新 attempt 先完成、另一个 writer 变化等交错。实施记录明确这些组合没有单独覆盖；已有 completed/running/404/503 和基础多 writer 测试不能自动证明这些组合。需逐项补业务测试或提供足以证明不可达的依据。
- 桥接先成功一页后失败并独立更新画像及活动的组合，已由 `Chat.test.tsx:3097-3131` 的参数化测试覆盖；实施记录对此条的“未覆盖”说明已过时，不能将其作为缺口。
- 审查中测试文件增加 `Chat.test.tsx:3300` 的账号/attempt 参数化覆盖，`review3-extra-bridge2.log` 记录该组联合测试 4 项通过，但它发生在原冻结和完整回归之后，不能用原 296 项结果证明新测试文件。且该测试没有覆盖上文较新 load 成功而 request 身份不变的交错。

## 已核查与限制

- 复核第三轮 raw、计划、第二轮审查及主要 controller/store/路由、恢复与消息关联路径；历史桥接失败现在能在仍有效的观察下独立更新画像和运行状态，POST 后旧 GET 淘汰也增加了同一请求的受控重查。`review3-post-red.log` 显示原交错业务测试失败，`review3-post-green2.log` 对应测试通过；不能仅用其证明所有并发分支。
- 审查开始时独立核对 `review3-source-after.json` 的 46 项全部一致；审查期间重新核对，只有 `web/src/pages/Chat.test.tsx` 不一致，产品源码仍一致。`review3-final-suite.log` 为旧冻结 296 项通过，构建退出 0；对新增测试后的当前快照需重新冻结并完整回归。
- 由于上述问题及证据缺口，本报告不宣称 Task10 全部代码、测试矩阵和后端事务已获完整通过；也未进行真实浏览器、模型、PostgreSQL 重启及跨账号验收。真实功能验收必须在最终完整独立审查通过后进行。
