# Task12 第二轮 22 项 Playwright 功能复验（2026-11-04）

产品增量 OCR 审查 `browser-fix-round2-code-review.md` PASS 后，在 Task12 专用数据库与仅本机后端运行既有 `npm.cmd --prefix web run e2e`，设置 `TASK12_ISOLATED_API` 指向隔离后端；完整日志 `playwright-fix-round2/run.log`、退出码 `exit-code.txt`。本轮没有修改产品、测试或配置，trace 关闭，未覆盖原 21 项或第一轮 22 项失败证据。

结果：**22 passed、0 failed、0 skipped，退出码 0**，总耗时约 29.4 秒。第 19 项真实 HTTP 组实际运行且通过；其他 21 项为受控 API 组，不能将受控响应描述为真实持久化。

受控场景包括 14 组视口、鼠标进入/Escape/重开、指针阈值与捕获/取消、边界及键盘上下移动、触屏显式开关与拖动、短高/层级、同账号双会话草稿及阅读位置隔离等。通过范围以实际 spec 断言为准，并不隐含所有设备或未列场景均已验证。

真实组通过的现有断言涵盖 A 浮卡实际拖动与服务端偏好读取、收起状态、退出及同账号重登；`/profile` 与 `/knowledge` 新文档 GET 观察和 reload 后偏好、URL 与零 PATCH；B 默认偏好、跨账号拒绝、独立拖动及切回 A 后原偏好。真实组通过代表其代码中这些断言执行完成；未推断无关场景或 Task13 数据库重启。

`artifacts/` 最终只保留 Playwright 状态 JSON；成功用例中附加的截图、矩形或请求附件未出现在最终输出目录，因此此处不声称这些文件已归档，也不据此推断用例失败。对本轮实际文本产物执行有限 JWT/Bearer/私钥/含口令数据库 URI 模式扫描未命中，不等于全面密钥审计。运行后 Playwright 自启 4178 已退出；Task12 后端保持运行。Task12 是否完成由主会话综合原始计划、其他验收证据与本记录裁决。
