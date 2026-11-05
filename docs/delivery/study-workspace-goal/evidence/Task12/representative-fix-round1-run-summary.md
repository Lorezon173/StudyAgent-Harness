# Task12 代表性局部修复后 25 项复验（2026-11-04）

`representative-round1-fix-code-review.md` 对本轮四文件增量审查 PASS 后，使用 Task12 专用后端设置 `TASK12_ISOLATED_API`，运行既有 `npm.cmd --prefix web run e2e`；spec SHA256 为 `9F26C8C60C00941E62A67BFB80AB0795F99819751E84A7AAE7AD933E7E0CD652`。结果目录 `playwright-representative-fix-round1/` 包含日志、退出码及实际保留产物；没有覆盖此前 21、22 或首次 25 项证据，trace 未开启。

**23 passed、2 failed、0 skipped，退出码 1。** 原 22 项全部通过，包含第19项真实 HTTP A/B 保存、重登和深链；新增代表性 M2 键盘焦点通过，M3 和 M4 失败。受控场景不冒称真实后端故障。

- **M3 代表性短高、长内容、两倍实际字号：失败。** 完整日志记载 `locator.hover('.chat-session-title')` 达到 30 秒测试超时：标题可见稳定、滚动后，展开浮卡内当前知识点段落反复拦截其指针事件。`error-context.md` 只记总超时，不能从它推导精确原因；上面引自实际 Playwright call log。`long-observations.json` 包含 normal/fonts/before/afterFill，后续 `long-content.png` 及该失败之后的滚动、来源跳转断言未完成。对具体合同和根因应另行诊断。
- **M4 代表性移动抽屉、账号菜单与退出提示：失败。** 实际运行已通过原先非精确 locator 处，到 `dialog open` 阶段；`workspace-layout.spec.ts:485` 的命中断言期望 true、实际 false。`overlay-observations.json` 记录该次目标点命中名为“关闭会话导航遮罩”的按钮，不能仅据此解释全部层级关系；后续 Escape 和留页步骤未执行。`overlay.png` 未生成。
- **M2 代表性键盘：通过。** 本轮终态实际保留 `keyboard-trace.json` 和 `keyboard-focus.png`；具体行为以现有测试断言及这些产物为准。

运行终态实际保留 3 个观察 JSON（keyboard、long、overlay）、Playwright 状态 JSON、2 个 error-context、keyboard-focus 与 2 张失败截图。成功用例及未到达步骤的其他截图未出现在产物目录，不声称已归档。对实际文本文件有限 JWT/Bearer/私钥/含口令数据库 URI 模式扫描未命中，不等于完整密钥审计。

本轮未自动重跑、修改产品或断言；Task12 尚不能依据本次结果宣布完成。未进行 Task13 验收。
