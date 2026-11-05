# Task12 代表性补证首轮 25 项结果（2026-11-04）

复审 `representative-code-review-v2.md` PASS 且冻结 spec SHA256 `294B268A46EDC19726D04DEF3C2E46E38A72757E56BEB836C477205DD1BB87E0` 后，在 Task12 独立后端运行既有 `npm.cmd --prefix web run e2e`，设置 `TASK12_ISOLATED_API`。日志、退出码及原始产物在 `playwright-representative-round1/`；未覆盖原21项及修订22项历史结果，trace关闭，未改源码/测试。

**22 passed、3 failed、0 skipped，退出码 1。** 原22项本次均通过，包括真实 HTTP 账号/偏好/深链组；新增3项均失败，后续步骤不能按通过记。

- **M2 键盘焦点**，`web/e2e/workspace-layout.spec.ts:384`：关闭状态反向 Shift+Tab 到达手柄，trace 显示 `inDetails=false`、`expanded=true`，失败于要求 expanded 为 false 的第二个断言；不是观察到详情被Tab进入。是否与原“重新聚焦可打开”合同冲突须主会话裁决。
- **M3 短高/长内容/两倍字号**，`workspace-layout.spec.ts:436–437` 的 `hit(send)`：元素中心命中期望 true、实际 false。`long-observations.json` 的 before 记录 600×450 条件下 composer.y=898、footer.y=498、高200、sidebar.height=0、messages.scrollWidth=4169 而 clientWidth=430；这些为实际记录，不能单凭它们概括所有根因。后续滚动、截图与链接断言未执行。
- **M4 移动抽屉和退出提示**，`workspace-layout.spec.ts:477`：`getByRole` 的非精确名称同时匹配关闭遮罩与关闭导航按钮，Playwright strict mode 抛两个匹配；日志中的 phase 到 `menu reopened`，之后抽屉关闭、受控503退出提示等步骤未执行。不能据此判定退出提示层级或产品缺陷。

运行终态 artifacts 实际保留：3 个 `error-context.md`、`keyboard-trace.json`、`long-observations.json`、`overlay-observations.json`、Playwright 状态 JSON、`keyboard-focus.png` 与 3 张失败截图。其他原计划截图及后续步骤附件未生成或未保留，不将其描述为存在。测试中的受控响应/503不是真实后端故障；真实 HTTP 组与受控组分别记。文本产物有限 JWT/Bearer/私钥/含口令数据库 URI 扫描无匹配，不等于完整密钥审计。

Playwright 自启的 4178 端口已退出，独立后端保持运行；未自动重跑、改产品或弱化断言。Task12 尚不能仅凭本次结果宣布完成。
