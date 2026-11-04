# Task10 测试迁移增补计划独立审查

结论：**PASS（计划层）**。审查对象 `docs/superpowers/plans/2026-10-27-task10-regression-test-amendment.md`，审查前 SHA256 为 `040466bbc2a43ec56923499d2ca6cdc77864f25c19527e9398fb2af82b05badd`，与派审值一致。此结论只允许按计划进入实现，不证明测试或真实功能通过。

## 核对依据与结果

- `round1-interim-full-test.log` 确为 11 文件、114 项、7 失败：NewSessionDialog 1 项（状态 error 而非 idle）、SessionSidebar 1 项（加载中错误出现空态）、WorkspaceLayout 5 项（固定/选中、退出、两种账号代际、选中历史）。计划明确先逐项核查、不预判七项均已过时，真实 DTO 后如仍存在跨账号更新、丢数据、意外 POST 或错误 UI 则按产品缺陷处理；不得仅删除失败断言。
- 原 Task10 v1.3 计划及其 PASS 审查允许更新 `WorkspaceLayout.test.tsx`，本增补仅额外纳入 `NewSessionDialog.test.tsx` 和 `SessionSidebar.test.tsx`，未扩产品代码或冻结依赖白名单。
- 对照两文件源码，计划要求保留创建 body、单次提交、403、部分成功绑定、账号换代和旧结果、关闭焦点；保留同名分组、并发分页、去重、顺序、游标隔离、加载/失败/重试/空态、未分组及无障碍。选中新会话应使用真实 ID 验证 snapshot、消息与可见状态，原断言须保留或等价加强，并记录迁移前后数量与理由。
- 计划要求 NewSessionDialog 和 SessionSidebar 的底层 fetch 按 URL/方法区分 workspace、分组、画像、创建、snapshot 和保存，异常或未知路径不得静默成功；必须使用真实 DTO，不能依赖全局请求顺序。WorkspaceLayout 在既有白名单内迁移占位和固定次数，账号代际、侧栏、导航、退出守卫须保留，全部测试的原有效断言适用等价保留要求。
- 计划要求独立计划审查 PASS 后实现，随后独立代码审查三个测试 diff，最后进行真实功能验收；与主计划要求一致。主计划真实浏览器、隔离账号和真实后端等验收条件未被替代或撤销。

## 执行审查关注

当前 `WorkspaceLayout.test.tsx` 已与中途日志所展示的旧版本不同，不能仅据旧日志认定当前五项仍失败或已修复；代码审查须对照修改前基线、实际 DTO 和最终 diff，逐项验证账号隔离、分页、错态、导航、创建保护及真实 session 消息归属，特别检查 logout 失败的实际原因与未知请求。定向及全量测试应等待真实终态并留存退出码；验收须在独立代码审查通过后进行。

本次未修改计划、产品源码或现有测试，未运行功能验收。
`n报告写入后复核计划 SHA256 仍为 `040466bbc2a43ec56923499d2ca6cdc77864f25c19527e9398fb2af82b05badd`。
