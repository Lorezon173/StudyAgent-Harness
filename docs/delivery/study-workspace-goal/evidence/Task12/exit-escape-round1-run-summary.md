# Task12 退出提示 Escape 修复后 25 项验收（2026-11-04）

`exit-escape-priority-code-review.md` 的三项静态增量 PASS 后，以 spec SHA256 `0941574DD7EB1ED5A586D882E1FDA3C11F3AB201AFAA13DFB8A9A31F6949C3D5` 和 Task12 专用本机后端运行既有 `npm.cmd --prefix web run e2e`；`TASK12_ISOLATED_API` 指向隔离后端。日志、退出码和实际产物在 `playwright-exit-escape-round1/`。trace 关闭，没有覆盖历史或修改源码、测试。

**24 passed、1 failed、0 skipped，退出码 1。** 原22项均通过，包含真实 HTTP A/B 保存、深链及隔离；新增 M2 键盘和 M4 移动抽屉/退出提示均通过。M4 受控 503 不是实际后端故障；`overlay-observations.json` 记录到 dialog open、before escape、after escape，`overlay.png` 实际存在；完整 test 通过表示其现有 Stay、Escape 与草稿断言已执行。

唯一失败为 M3 代表性短高、长内容、两倍实际字号：`web/e2e/workspace-layout.spec.ts:466` 调用 `regions()`，其内部 `read`（429–430行）等待 `.floating-profile-content` 30秒未找到。原因须另行核对，不能仅凭超时认定产品或测试缺陷。此前测试已到达并保留 `long-observations.json` 中的 normal、fonts、before、afterFill、titlePoint、titleScroll、sendHit、menuFonts 和 code；466 行以后的双区域滚动、锚定、截图、链接等断言未完成。`long-content.png` 不存在，不能称已归档。

运行终态实际保留 keyboard trace/焦点 PNG、long observations JSON、overlay observations JSON/PNG、M3 error-context 与失败截图，以及 Playwright 状态 JSON。仅对本轮文本产物作有限 JWT/Bearer/私钥/含口令数据库 URI 模式扫描未命中，不等于完整密钥审计。未自动重跑、修改源码或触碰 Task11 数据库；Task12 不因其他通过项而完成，Task13 未验。
