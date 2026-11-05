# Task12 M3 测量修订后完整 25 项验收（2026-11-04）

`m3-baseline-state-code-review.md` PASS 后，以冻结 spec SHA256 `FE14E88333F6A4B11B72132F12580A717E7527010BD224F027D0E98DE99FB5FD`，在 Task12 专用后端运行既有 `npm.cmd --prefix web run e2e` 并明确设置 `TASK12_ISOLATED_API`。完整日志、退出码及产物保留在 `playwright-m3-baseline-round1/`；未覆盖此前失败证据，trace 关闭。

**25 passed、0 failed、0 skipped，退出码 0，约 56.7 秒。** 原22项及新增 M2/M3/M4 均在本轮实际执行并通过；第19项真实 HTTP A/B 偏好保存、重登、深链和隔离组通过，其余24项为受控 API 用例，结果不能冒称真实数据库或真实后端故障。

- M3 在 600×450 使用测试脚本手动将实际字号设为约两倍，完成长标题键盘/滚轮、发送控件命中、账号菜单、长代码块、区域滚动及锚定、来源链接与目标画像/节点等现有断言。`long-observations.json` 实记标题滚动 668→0、发送点命中 true、代码块 scrollWidth 4926/clientWidth 269 且 white-space=pre，并包含 baseline/reopened 字号、区域及动效数据；这些是指定测试环境结果，不泛化为所有字号或设备。
- M4 的受控视图保存 503 场景完成移动抽屉、菜单、退出提示的现有断言；`overlay-observations.json` 记录 Escape 前后浮卡展开、详情与抽屉可见、Stay 仍获焦点。整项通过表示测试继续执行了实际 Stay 和草稿断言；该受控 503 不是真实网络故障。
- M2 键盘焦点/关闭详情的现有断言通过。

终态已逐一检查，`artifacts/` 实际保留 `keyboard-trace.json`、`keyboard-focus.png`、`long-observations.json`、`long-content.png`、`overlay-observations.json`、`overlay.png` 和 Playwright 状态 JSON。三个代表性场景路径均为目录内各自命名的 `workspace-layout-受控-API-·-代表性…/`；文件均非空。其余成功用例未保留的附件不称已归档。

对本轮实际文本产物有限 JWT/Bearer/私钥/含口令数据库 URI 扫描未命中，不等于完整密钥审计。此次是浏览器功能执行，不冒充独立 TypeScript 检查；既有428项前端测试和构建只按相应源码冻结证据引用。没有改产品或重跑，Task13 未验；Task12 最终状态由主会话综合验收裁决。

