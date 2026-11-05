# Task12 修订后 22 项 Playwright 首轮（2026-11-04）

在复审 PASS、冻结 spec SHA256 `C28E16933211F94E8EF0B8EAD27F0E80D6565F6DD471A78BE7E8CD7125AD033E` 后，设置 `TASK12_ISOLATED_API` 指向 Task12 独立本机后端，以项目既有 `npm.cmd --prefix web run e2e` 和配置运行全部 22 项，产物目录 `playwright-fix-round1/artifacts`、完整日志 `playwright-fix-round1/run.log`、退出码 `exit-code.txt`。原 21 项首轮证据未覆盖；运行未改产品、测试或配置，trace 未开启。

**终态：19 passed、3 failed、0 skipped，退出码 1。** 真实 HTTP 组已运行但失败；原 14 个受控视口布局用例通过，受控触屏开关、短高弹窗、触屏手柄、短高调整和同账号双会话草稿/阅读位置用例均通过。通过结论仅限对应受控场景，不代替真实持久化。

三项失败的最早位置及观察：

1. 受控鼠标进入/Escape/重新进入，`web/e2e/workspace-layout.spec.ts:131`：按 Escape 后期待 `aria-expanded=false`，实际持续为 `true`，等待 5 秒失败。
2. 受控指针/键盘组合，`web/e2e/workspace-layout.spec.ts:155`：键盘向下后浮卡 y 期待大于 225.25，实际为 214.25；该断言前流程与截图/上下文保留在 artifacts。不能仅凭这条结果断言根因。
3. 真实 HTTP A/B 与深链用例，`web/e2e/workspace-layout.spec.ts:237`：深链 reload 后读取已观测 GET 的 `response.json()` 抛 `Network.getResponseBody` 资源不可用，消息提示导航后响应体不可取。执行已到该行；其后的 B 隔离和重登断言未执行，不能标通过。真实业务是否有缺陷，须结合实际日志与只读诊断裁决。

本轮最终目录保留三项失败截图与 error-context，以及运行日志和 Playwright 状态文件；成功用例附件未见于最终输出目录，不能从未保留附件推断用例失败原因或虚构截图/矩形。仅对实际文本产物进行有限敏感格式扫描，无 JWT/Bearer/私钥/含口令数据库 URI 匹配；不等于完整密钥审计。4178 由 Playwright 启停，运行结束后已无监听；Task12 独立后端保持运行。没有自动重跑或修改源码，Task12 核心验收未完成。
