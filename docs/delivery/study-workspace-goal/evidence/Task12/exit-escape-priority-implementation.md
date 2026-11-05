# Task12 退出提示 Escape 优先级补修实施交接

## 已实施与证据

依据 `exit-escape-priority-plan.md`（SHA256 `42BBE2776949736DCD467EFAAE9A79A07669D6B90DDEEE00852320147A704DD6`）及独立计划审阅 PASS，仅扩展现有移动 Escape guard，识别 `dialog[open], [role="dialog"]`；未新增监听、状态、effect 或焦点框架。对比产品文件前后字节，除这一选择器替换外完全一致，因此三项退出回调及其他业务逻辑未变。原 M4 增加 Escape 前后抽屉可见与留页焦点断言及观察字段，未新增场景。

真实组件路径的受控保存失败测试在改 guard 前实际 RED：Escape 将焦点从留页按钮转至“打开会话导航”，日志 `exit-escape-priority-red.log`，退出 1。修改后该测试通过，验证提示存在、焦点保留、抽屉保持打开，留页后路由、登录及草稿保留；既有无前景测试增加入口还焦断言，验证 Escape 关闭抽屉并焦点回入口。此为 jsdom 组件行为，不代表浏览器前景层级验收。

## 实际进程终态

- `npm.cmd --prefix web test -- --run src/components/workspace/WorkspaceLayout.test.tsx`：退出 0，20 项通过，`exit-escape-priority-target.log`。
- `npm.cmd --prefix web test`：退出 0，16 文件、428 项通过，`exit-escape-priority-web-test.log`；日志含 React Router future flag 警告。
- `npm.cmd --prefix web run build`：退出 0，`exit-escape-priority-build.log`。
- `npm.cmd --prefix web run e2e -- --list`：退出 0，收集 25 项，`exit-escape-priority-collect.log`；仅收集，未执行浏览器功能。

## 冻结与哈希

20 项基线均与上轮独审最终哈希匹配；本轮 3 项变更、17 项未变。全部完整字节快照为 `exit-escape-priority-before-*.txt`、`exit-escape-priority-after-*.txt`，3 份精确增量为 `exit-escape-priority-increment-*.diff`，全部前后哈希见 `exit-escape-priority-hash-check.json`。未覆盖既有证据。

| 文件 | 前 SHA256 | 后 SHA256 |
|---|---|---|
| `web/e2e/workspace-layout.spec.ts` | `A67F42D795FCF6D44E78E7C9222EB744E8630D7A53967EFC12A74DDAF7D8D55D` | `0941574DD7EB1ED5A586D882E1FDA3C11F3AB201AFAA13DFB8A9A31F6949C3D5` |
| `web/src/components/workspace/WorkspaceLayout.test.tsx` | `4DC92BD2561B33342A3798D44155EFB526E9EBC81054BBE08FD82C6E0C2BA886` | `5EB94461C9B1E6D35B3C2026721A0080CB9392A6FFB500F63F6A65EDB897D848` |
| `web/src/components/workspace/WorkspaceLayout.tsx` | `665210FF9E5B1D952F52F38FED23465DA775D020E54E300E59CF74ADDEB007FF` | `5D00DFE84C7F5C5F9A9BD626558A80E4875772F68AB3722F7B7985A0A172CEA5` |

## 未验证

本轮未启动服务或运行浏览器功能；25 项收集不证明 M3 后段、增强 M4 或原有 23 项通过。受控 503 不代表真实后端事故。应先独立 OCR 增量复审，再按计划运行隔离 HTTP 的全部 25 项并核实际附件。Task12 仍进行中，Task13、B 候选和 L1–L4 限制保留；未 stage、commit，README/status 交主会话负责。
