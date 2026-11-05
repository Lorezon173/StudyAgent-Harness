# Task12 验收补充计划独立复审 v2

日期：2026-11-04。结论：**PASS（仅计划）**。原审阅报告 `acceptance-supplement-plan-review.md` 保留。

复审版本：`acceptance-supplement-plan.md` SHA256 `17EAC1F1AA58102D7AAA15A529EDCD557D445EB888B56961CD47876133DF5DE7`，复审前后两次只读核对一致。完整重读修订计划，并对照前轮已读 raw/round1/handoff、测试配置与源码上下文；重点重新核实移动抽屉和正常退出实现。

## M1 已在计划中解决

- A 在 1440×900 保存收起、未固定、非默认 ratio 后，明确切至 390×844，通过正式“打开会话导航”按钮打开抽屉，再通过账号菜单正常退出。
- 该移动入口调用 `setMobileOpen(true)`（`web/src/components/workspace/WorkspaceLayout.tsx:104`）；`web/src/store/workspace.ts:418` 仅更新局部 sidebar.mobileOpen，不调用写偏好的 expandSidebar。与桌面展开写 collapsed=false 的入口（同文件 :415）已正确区分。
- 计划要求抽屉打开后、退出前及正常退出完成后独立 GET，三偏好保持保存快照；不以动作名称推断未写偏好。正常退出仍走 `flushAll` 后才 logout（`WorkspaceLayout.tsx:63–71`），保留正常保存等待合同。
- 退出后改为 1024×900，重登先验证收起 DOM，再按实测几何验证 ratio；此后为操作桌面账号菜单而展开时，等待保存并更新确认基线，B 写后返回 A 比较最新确认值，不再误用首次 collapsed=true。
- 深链每页另以收起、未固定、非默认 ratio 的已确认基线开始；菜单展开后先 UI 收起并等待保存，再执行 reload。计划已说明这一前置恢复，和 A/B 的最新确认基线不冲突。

## 范围及执行门禁

未发现新增有实际依据的计划问题。三层文字设计、真实 A/B 与受控双会话边界、锚点/草稿/ratio 的可观察断言、分段 GET、reload 无 PATCH/无导航及 Task13 排除项维持前轮结论。仅更改验收序列，无新增产品机制。

补验编码仍须等待原 21 项执行到终态；当前 PASS 不代表原用例或补充用例通过。实施只在批准单文件内补测试，失败先保留证据和分类诊断，不自动修改产品或放宽旧断言。主会话串行维护 README、账本和最终证据。

本复审未修改计划、产品源码或测试，未运行功能、未提交；仅新增本报告。真实浏览器、真实偏好持久化、产品代码及 Task12 完成状态仍以之后实际验收与独立代码审查为准。
