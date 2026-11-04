# Task10 审查修复：续做记录与覆盖边界

本文仅记录实现和自动化证据，不是独立代码审查或真实功能验收结论。设计依据为 `superpowers/frontend-ui/task10-review-fix-round1-raw.md`、`docs/superpowers/plans/2026-10-28-task10-review-fix-round1.md`，以及 `review-fix-round1-plan-review-v6.md`。

## 本续轮工作

- 核实中断前日志：两个隔离 controller 的共享存储交错、存储读回失败、401 和账号切换备份、发送准备期间活动锁等均已有定向结果；这些结果不能代替全计划验证。
- 发现旧 retry 查询和旧原请求重发查询被较新观察取代后仍回写错误：`review-fix-stale-retry-{red,green}.log`、`review-fix-stale-resend-{red,green}.log`。
- 发现原 ID 重发及失败请求 retry 的快照被较新观察取代后仍调用接口：`review-fix-resend-snapshot-{red,green}.log`、`review-fix-retry-snapshot-{red2,green}.log`。另验证 retry 当前快照已有活动请求时不发起重试：`review-fix-retry-busy-{red,green}.log`。
- 发现重查被较新普通加载取代后永久停在 checking：`review-fix-recheck-superseded-{red,green}.log`。
- 发现本机请求副本或旧版准备副本在 GET 期间发生变化时，旧结果仍被接受；原 ID 重发快照等待期间副本变化仍发送：`review-fix-candidate-lookup-{red,green}.log`、`review-fix-legacy-candidate-{red,green}.log`、`review-fix-candidate-resend-{red,green}.log`。
- 中断后首次全量回归 `review-fix-resume-full-suite.log` 为 46 项失败：两个旧测试的直接恢复期待与已批准的风险知情契约冲突，另外连续超时可用假定时器测试及相邻测试复现。隔离实验 `review-fix-timer-isolation-red.log`、`review-fix-timer-diagnostic.log` 和 `review-fix-timer-isolation-green3.log` 表明 spy 与假定时器恢复顺序污染后续测试；改为检查换代后真实不会再发轮询，未调大超时。旧测试改为检查风险提示和可证明取消后的恢复，见 `review-fix-old-recovery-contract.log`。
- 使用两个独立加载的真实 AuthProvider 和 App，共享 localStorage：A 完成并关联后 B 的旧缓存不能静默复制；A 的 linked 写入失败但仍 POST 时 B 看到重复风险并须明确复制。`review-fix-two-providers-completed.log` 为两项通过。模拟 fetch 响应不是后端真实验收。
- 补真实路由经知识库/学习画像离开后返回时的准备取消（`review-fix-navigation-pages.log`），以及 busy、首次 404、另一客户端完成原 ID 后重新查询关联的交错（`review-fix-busy-other-completed.log`）。
- 补浏览器历史返回（`review-fix-navigation-history.log`）、发送后切换会话（`review-fix-post-switch.log`）、同 ID 多 writer 的 payload/base/node/turn 不一致（`review-fix-multiwriter-matrix.log`）。这些测试使用内存路由及模拟传输，并非真实浏览器和后端验收。
- 以重新挂载后的实际 Storage 状态测试纯 prepared、linked、request 三种中断后恢复（`review-fix-recovery-phase-matrix.log`），分别测试三种写入失败与三种读回不一致：`review-fix-write-failure-matrix.log`、`review-fix-write-failure-matrix-green.log`、`review-fix-readback-matrix.log`、`review-fix-readback-matrix-green.log`。这些测试模拟中断点和存储故障，不等同对操作系统进程强制终止或物理断电的验证。
- 补本人写失败并伴随其他 writer 新副本、包含损坏项的部分读取和明确操作时读取失败：`review-fix-own-failure-other-{red,green}.log`、`review-fix-partial-read-{red,green}.log`、`review-fix-unreadable-retention-{red,green}.log`、`review-fix-explicit-read-retention-{red,green}.log`。保留已知和可读出的其他候选，并阻止已知冲突情况下误发。
- 补关联历史等待期间 attempt 和账号代次变化（`review-fix-confirm-identity-green.log`）；补同 ID 多 writer 的 profile 差异（`review-fix-multiwriter-matrix2.log`），补完成确认遇缺失画像 revision 时保留已知 revision（`review-fix-null-revision.log`）。
- 补默认 `/chat` 恢复原会话时的旧准备取消（`review-fix-default-route.log`），以及 A 的旧准备与 B 已提交的新请求交错（`review-fix-overlap-preparations.log`）。

## 需继续核查

- 本计划的所有测试矩阵尚未逐格形成完整覆盖证明，包括真实进程中断恢复、同 ID 多 writer 账号/session 等身份字段组合。已有相关测试不能自动证明这些组合。准备请求在途时返回原会话，界面仍将其显示为 preparing；已测 A 的旧准备与 B 新请求交错，但旧准备结束前同一会话能否出现第二个准备需基于实际交互和设计约束判断，不能以人为改写 store 冒充真实路由行为。
- 双 Provider 中 A 成功完成与写入失败两条路径已覆盖，但没有证明跨浏览器/进程的真实存储事务或真实后端并发排他。客户端设计本身也不宣称能够证明这种排他性。
- 最终源码全范围独立审查、真实浏览器和真实模型代理验收、真实 PostgreSQL 重启及跨账号检查均未由本文完成。须由主会话按计划推进，不得将本轮自动化结果称为 Task10 或整体目标完成。

## 全量回归

本轮冻结回归 `review-fix-freeze-suite-v3.log`：11 个文件、237 个测试通过，退出码 0；构建 `review-fix-freeze-build-v3.log` 退出码 0。`review-fix-source-before-v3.json` 与 `review-fix-source-after-v3.json` 对原清单 46 个文件逐一核对，差异为 0。任何后续源码变化均使该快照失效，必须重跑。该结果不替代独立代码审查及真实验收。
