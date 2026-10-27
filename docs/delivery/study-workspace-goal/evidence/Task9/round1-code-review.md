# Task9 独立代码审查（续审）

结论：**Needs changes**。一个已复现的 P2 问题；未证实的静态风险不列为缺陷。

## 范围与证据

- 审查依据：task9-brief.md v1.3、task9-report.md、task9-review-manifest.json、冻结源码、既有全量独立审查交接。
- 本续审聚焦原审查留下的 Login/关闭生命周期问题；没有重复全量测试或扩大至 Task10。
- 38 个冻结文件 SHA256 全部与 manifest 一致（复现前后均检查，mismatches=0）。原 final-test.log 为 8 文件 62/62；final-build.log 为 TypeScript/Vite通过。这些通过不覆盖下面发现的场景。
- 最小探针实际命令：npm.cmd --prefix web test -- src/review-temporary.test.tsx。原会话 38656 终态 exit 1：2 tests，1 failed / 1 passed。未重启。
- 探针源码归档 task9-review-probes.tsx（保留原 web/src 路径的相对 imports，重放需临时放回该路径）；web 临时副本已移除。没有修改产品源码、现有测试、依赖、README、账本或Git索引。

## R9-I1 [P2] 账号换代后仍挂载的登录页会永久停在提交中

位置：web/src/pages/Login.tsx:28–41；关联 useLayoutEffect:17–20。

真实可发生顺序：已登录 A 时进入 /login（路由允许），此前受保护请求仍在途；用户提交 B 登录；A 的当前受保护请求返回401，AuthProvider清认证并推进 workspace generation。此时浏览器已经在 /login，client 不作硬跳转，Login 组件仍挂载。B 的登录回复随后到达。

current() 将整个成功、catch、finally 都绑定到旧 generation。换代后它们都被丢弃是正确的账号隔离，但此页没有订阅 generation 变化来结束本地 busy/busyRef，且只在卸载时递增本地票据。最终账号保持失效，按钮及输入框永久 disabled，用户无法重试。

最小真实组件复现使用 AuthProvider + MemoryRouter + Login + 真实 apiGet/client/workspaceStore，仅 mock 最下游 fetch：预置A认证，发保护请求和登录请求；先释放保护请求401，再释放登录成功。断言“提交中…”按钮已消失失败，实际仍为 `<button class="primary-button" disabled="" type="submit">提交中…</button>`。测试失败位于 review-temporary.test.tsx:20。没有 mock current()/generation 或内部busy。

要求：对仍挂载的 Login 在身份代际失效时，主动终止属于旧代际的本地提交/忙状态，并使旧续体不再影响后续新提交。保持有效自有login成功的清busy→login→navigate顺序；不能简单允许旧finally清新提交busy。增加真实组件延迟fetch回归，至少证明当前401失效后可重试、旧成功/失败不改新认证及新busy。

## 不列为阻断：Dialog关闭后晚profile

最小真实 NewSessionDialog + controlled open + AuthProvider 测试：新画像POST pending → 同账号点击关闭 → 放行profile成功。实际 PASS：总POST仍1，未继续createSession，onCreated未调用。普通用户关闭路径的passive cleanup已及时失效票据。本次未证实原静态风险，不能仅因没有同步close epoch就要求修复。若后续出现不同明确可复现顺序，再按新证据处理，不将猜测变成当前阻断。

## 范围边界

/chat/:sessionId只选中并显示内容暂不可用、Task10恢复/发送未接入、Task11旧业务内容保留、Task12浏览器视觉验收，均是已批准边界，不作为本轮缺陷。未宣称真实后端JWT/数据库或浏览器几何验收完成。

本报告仅证明本轮新增发现与关闭探针结果；原审查已完成的DTO/整体包复核沿用交接，不冒称本续审再次逐行阅读整个230885字节包。需要修复轮三层计划及独立PASS后执行，修复后范围复审R9-I1及相关新破坏。
