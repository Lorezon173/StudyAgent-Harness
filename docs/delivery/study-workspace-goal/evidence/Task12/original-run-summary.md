# Task12 原 21 项 Playwright 首轮结果（2026-11-04）

在独立 Task12 后端健康、4178 端口空闲及已审代码冻结后，设置 `TASK12_ISOLATED_API` 指向本机隔离后端，运行 `npm.cmd --prefix web run e2e -- --output <本轮artifacts目录>`。使用原有 `playwright.config.ts`、冻结的 `workspace-layout.spec.ts` 和系统浏览器；未改产品、测试或配置。完整日志 `playwright-original-round1/run.log`，退出码 `exit-code.txt`，截图和 error-context 保存在同目录 `artifacts/`；未启用 trace。

结果：**21 failed、0 passed、0 skipped，退出码 1**。20 项受控 API 与 1 项真实 HTTP 均执行；真实组非 skip，但未完成该组全部行为断言。不能将测试执行当作验收通过。

首个失败为受控 1440×900：页面等待“输入学习问题…”输入框及原草稿 5 秒未找到；失败截图呈白屏。此时无法单独判定根因为产品、测试夹具或运行环境。14 个视口用例及其他受控用例的完整错误按原始日志和截图保留，不能仅据第一个错误假定其他问题均相同。

真实 HTTP 用例实际完成前置账号/会话创建并进入真实页面；其最早失败是拖动后 5 秒内真实 workspace `progress_y_ratio` 仍为 0.5，不满足非 0.5 断言。截图显示真实会话及浮卡；这与首个受控白屏不是同一个可直接合并的观测。拖动为何未保存需要进一步核对，不能凭此直接断言产品或测试缺陷；后续重登、跨账号和深链断言不能视为已完成。

运行结束后 Playwright 所启动的 4178 前端已退出，专用后端未停止。对本轮文本证据作有限 JWT/Bearer/私钥/带口令数据库 URI 模式扫描，未发现匹配；不等于全面密钥审计。没有自动重跑，未进行 Task13 验收。
