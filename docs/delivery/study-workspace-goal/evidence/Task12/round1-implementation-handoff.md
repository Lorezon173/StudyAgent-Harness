# Task12 Round1 实施交接（独立审查前）

基线 HEAD `a6117c48c1ff7e8877806d0862e69ff0e42f13f4`；raw 与 plan SHA 分别为 `E58574DADBAEFD0C538F047D5D30EE741AB7E01C808147A27502575923FF1323`、`DB6B9C59F21DE5E080F0CBB6EAF71B7594E0287E9AF2DFD11635956C3AAA15B6`，复审 v2 仅计划 PASS。README 原 162 行及 asset-inventory 原 34 行工作区差异保留。

## 已实施及证据

- workspace 同代读取复用和偏好/recent 单版本单飞写入；侧栏本地操作、ratio、失败/显式重试、账号换代与退出等待。深链业务 RED/GREEN：`workspace-deeplink-red3.log` / `workspace-deeplink-green.log`；侧栏纯偏好 PATCH：`sidebar-save-red.log` / `sidebar-save-green.log`；交错顺序：`workspace-interleave.log`、`workspace-recent-first.log`；慢 GET 和 409：`workspace-late-conflict.log`；换代旧成功/失败及正常退出等待：`workspace-exit-generation.log`；未确认退出：`workspace-logout-red.log` / `workspace-logout-green.log`；初读失败重试：`prefs-load-red.log` / `prefs-load-green.log`。
- 同代在途 GET 合并与旧测试原先要求并发第三个 GET 的合同不同；保留的用户合同是选择 B 后旧读取不能导航 A 或丢失 B 写入。首次适配发现确实会错误导航 A，`workspace-coalesced-navigation-red2.log` 复现；lastSession 最小增加 recent dirty/conflict/序列校验后 `workspace-coalesced-navigation-green.log` 通过。后续发现同一 A 仍 dirty 时过严阻止恢复，`workspace-targeted2.log` 复现；只在本地目标与服务器不同时阻止，`workspace-navigation-green2.log` 同时验证两个场景。该门禁属于保持原 Task10 用户行为，不重写候选算法。
- Chat 挂载真实同源 summary、host/topbar/composer 测量 refs；`chat-profile-red.log` / `chat-profile-green.log` 验证真实指标、展开不新增消息/summary 读取。FloatingProfile/hook 与 CSS 已接入；其独立组件测试结果包含在最终全量日志。原图像交互和几何仍需浏览器实际验收。
- `web/vite.config.ts` 保留 Vitest 默认排除并追加 `e2e/**`，避免收集 Playwright 用例；Playwright 精确开发依赖、配置和独立用例由并行实现者提供。计划中的真实浏览器验收需在独立 OCR 后执行。
- `final-full-test.log`：`npm.cmd --prefix web test`，退出码 0，16 文件、423 测试通过；`final-build2.log`：`npm.cmd --prefix web run build`，退出码 0。日志中 React Router future 警告保留。`final-before-hashes.txt` / `final-after-hashes.txt` 和 `final-hash-comparison.txt`：完整 19 项在全量重验及构建前后一致。首次清单误写 hook 测试扩展名并收到不存在错误，该轮不作为完整冻结证据，日志保留。

## 未完成或未验证

- 完整 OCR preview/rule 覆盖与新鲜独立源码审查尚未执行；上述测试与计划审查不替代独立审查。
- 正式 HTTP 浏览器完整视口/短高/真实 pointer、触摸、拖动、Escape、失焦、缩放、reduced-motion、modal 层级、网络请求与真实 A/B 账号重登偏好闭环尚未由本实施者完成验收。尤其 B 写后再回 A、重登后新尺寸位置、跨会话草稿和阅读锚点仍未验证。
- 受控 GET 交错已测试常见顺序及旧成功/失败；完整真实网络时序、真实 PostgreSQL 重启与 Task13 真实模型教学未验证。原始日志存在夹具错误或中间失败的均原样保留，不将其计作通过。
- 未改后端、Task10 请求/恢复算法、README 或账本，未提交、推送、部署。独立审查结论及后续浏览器证据决定 Task12 是否完成。
