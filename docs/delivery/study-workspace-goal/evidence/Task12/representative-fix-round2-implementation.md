# Task12 代表性第二轮修复实施交接

## 范围和状态

依据 `representative-fix-round2-plan.md`（SHA256 `6114708169FE479C751C4B7C3CB433AC1A84499DC360DA4A495468C9D9631ADB`）及独立计划审阅 PASS 实施。修改退出错误提示的局部静态固定遮罩、panel 和留页初始焦点；M3 只调整真实未遮标题点的指针输入并记录观察；M4 添加宽度、位置和焦点观察。保留已有长内容、双倍实际字体和后续断言。

M4 原受控 503 实测已证明原有 panel 挤压 main 且留页按钮被遮罩拦截，作为布局 RED；新增焦点语义测试在修改前以 activeElement 为 body 而非留页按钮失败（`representative-fix-round2-red.log`，退出 1），修改后通过。经前后文本比较，`requestLogout` 与 `logoutWithBackup` 函数完全相同；退出条件内容去除新增 wrapper、class 和 autoFocus 后与原文完全相同，包括三个按钮回调。未修改 mobileOpen 或其处理逻辑。

## 实际进程终态

- `npm.cmd --prefix web test -- --run src/components/workspace/WorkspaceLayout.test.tsx`：退出 0，19 项通过，`representative-fix-round2-target.log`。
- `npm.cmd --prefix web test`：退出 0，16 文件、427 项通过，`representative-fix-round2-web-test.log`；日志包含 React Router future flag 警告。
- `npm.cmd --prefix web run build`：退出 0，`representative-fix-round2-build.log`。
- `npm.cmd --prefix web run e2e -- --list`：退出 0，收集 25 项，`representative-fix-round2-collect.log`。仅收集，未执行浏览器功能。

## 冻结清单及哈希

20 项在开始前全部与前轮 after 哈希匹配。以下 4 项实际改变，另 16 项前后哈希一致，详见 `representative-fix-round2-hash-check.json`。全部 20 项的 `representative-fix-round2-before-*.txt`、`representative-fix-round2-after-*.txt` 为完整字节快照，4 个 `representative-fix-round2-increment-*.diff` 为本轮增量；未覆盖前轮证据。

| 文件 | 前 SHA256 | 后 SHA256 |
|---|---|---|
| `web/e2e/workspace-layout.spec.ts` | `9F26C8C60C00941E62A67BFB80AB0795F99819751E84A7AAE7AD933E7E0CD652` | `A67F42D795FCF6D44E78E7C9222EB744E8630D7A53967EFC12A74DDAF7D8D55D` |
| `web/src/components/workspace/WorkspaceLayout.test.tsx` | `EB7A69E714461295BD6F553B4966813F831F73A4926FE2D2D5F6BA46341539BB` | `4DC92BD2561B33342A3798D44155EFB526E9EBC81054BBE08FD82C6E0C2BA886` |
| `web/src/components/workspace/WorkspaceLayout.tsx` | `91938A21ECC0A9AD8F10791CEE9F33A07C159749E0B22F966CC026CBF9F55CF8` | `665210FF9E5B1D952F52F38FED23465DA775D020E54E300E59CF74ADDEB007FF` |
| `web/src/index.css` | `6962089ED491BD4A07433423B92C1FE531D986F0C7D0194BE72D302876C46884` | `143DBA3B50F158B52BA6D2062134DD1FDEC0555BABB0F98D42F6A2B96F009E9D` |

## 未验证与交接

未运行浏览器功能、不曾启动服务；本轮静态结果不证明 M3 后续操作或 M4 前景命中、Escape 和留页在浏览器通过。前轮 23 项通过不能继承为本轮通过。原有移动端 Escape 处理检查原生 `dialog[open]`，当前退出提示为非原生 role；Escape 是否关闭抽屉及焦点实际去向须在原测试链核实，不据静态测试声称符合完整 modal/focus trap。受控 503 与人工字体压力不等于真实后端故障或原生浏览器缩放。独立 OCR 增量审阅通过后才按计划复验全部 25 项。Task12 保持进行中；Task13、B 候选和 L1–L4 限制未验。未 stage 或 commit；README 与状态账本由主会话负责。
