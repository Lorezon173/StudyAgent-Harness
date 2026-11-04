# Task 11 前端实施与测试记录

基线 HEAD：`0bd2d742ac2c34fd24d6d097f4f37bcb5761cb50`；实施计划和 raw SHA256 与独立计划审查一致。源码与测试文件的测试前后 SHA256 记录分别见 `freeze-before.txt`、`freeze-after.txt`，逐行比较无差异。此冻结仅供后续审查，不表示产品验收完成。

## 本轮前端文件

- 修改：`web/src/pages/Knowledge.tsx`、`web/src/pages/Profile.tsx`、`web/src/components/workspace/WorkspaceLayout.tsx`、`web/src/components/workspace/WorkspaceLayout.test.tsx`、`web/src/index.css`。
- 新增：`web/src/pages/Knowledge.test.tsx`、`web/src/pages/Profile.test.tsx`、`web/src/components/knowledge/KnowledgeLibrary.tsx`、`web/src/components/knowledge/ResourceDialog.tsx`、`web/src/components/profile/ProfileDetail.tsx`、`web/src/components/profile/ProfileSummaryCard.tsx`、`web/src/components/profile/ProfileSummaryCard.test.tsx`。
- README、资产清单及其他既有工作区差异由主会话维护。本轮未修改 Chat、后端、API client/types/store 或 Task10 状态算法；未提交、推送或部署。

## 实际验证

- `npm.cmd --prefix web test -- Knowledge Profile ResourceDialog ProfileSummaryCard WorkspaceLayout`：4 个测试文件、45 项通过，退出码 0，见 `targeted-final.log`。
- `npm.cmd --prefix web test`：14 个测试文件、398 项通过，退出码 0，见 `full-test.log`。
- `npm.cmd --prefix web run build`：TypeScript 与 Vite 构建通过，退出码 0，见 `build.log`。存在 React Router future flag 警告，未为消除警告变更业务。
- Knowledge 测试以真实 React 页面和模拟 fetch 验证搜索/详情、创建编辑解绑删除、写入失败保留、创建结果不确定、确认后 GET 失败不重复 POST、列表刷新失败、游标及重复去重、查询和账号迟到、关闭旧弹窗后写入完成、同步防重、长度、对话框焦点与 cancel。Profile 测试覆盖真实 summary、null/0、revision 匹配和有界重读、会话解析、错绑拒绝、主题切换、真实边/来源、分页、404、空列表及账号迟到。导航测试验证当前已核会话/画像参数与原有壳测试。
- 初始真实业务 RED 见 `round1-red.log`：原 Knowledge 缺搜索；原 Profile 缺主题和摘要。导航业务 RED 见 `navigation-red.log`；分页去重与确认后列表刷新提示分别见 `knowledge-dedup-red.log`/`knowledge-refresh-red.log` 及对应 green 日志。其他多个测试在实现后补写并直接通过，不声称逐项经历 RED。`knowledge-focus.log` 的首次失败是测试调用不存在的 API，修正后见 `knowledge-focus-green.log`。导航首次修正后因测试夹具仍为旧画像 API 结构失败，该次原日志被后续运行覆盖，不能作为保留证据；最终真实合同夹具测试见 `navigation-green.log`。

## 未完成或未验证

- 尚未进行完整 OCR preview/rule、逐文件独立审阅；此记录不代表代码审查通过。
- 尚未进行独立测试账号的真实 HTTP CRUD、跨账号拒绝、真实数据画像来源与浏览器操作/视觉/网络故障验收；mock DOM、测试夹具、构建均不替代这些验收。真实模型评估及 PostgreSQL 重启仍属 Task 13。
- 已有自动测试并未逐条覆盖计划矩阵：例如独立的编辑/删除失败保留、名称和说明所有边界、旧错误/finally 与每种弹窗交错、生成中往返导航及多个视口的视觉检查仍未逐项验证。对于未覆盖项不得将现有测试数当作证明。
- 本报告无最终验收结论；后续审查意见须依据生产路径、原任务和证据裁决，完成真实验收后再判断 Task 11 状态。

## M1 审查修复（待独立复审）

审查确认：A 满页、B 搜索失败后旧分页可再次发 A 请求，覆盖 B 错误、重试目标和旧结果提示。按已批准搜索恢复合同，仅在旧结果标为 stale 时禁用加载更多，并在页面分页入口同时核对 `requested` 与 `applied`；未引入新状态框架、接口或后端修改。

先以真实页面及模拟 fetch 建立 A 满页→B 失败→旧分页不可操作→保留错误并重试 B→B 成功并正常分页的测试。首次 `m1-red.log` 为测试使用了不可用断言 API，不是业务 RED；修正断言后 `m1-business-red.log` 的失败确认为旧分页仍可用。修复后 `m1-green.log`：Knowledge 17 项通过，含原有分页/去重、失败保留和旧响应隔离。

修复后 `m1-full-test.log`：14 文件 399 项通过，exit 0；`m1-build.log`：TypeScript 与 Vite 构建通过，exit 0。测试前后 12 个源码/测试文件和 HEAD 的 SHA256 清单 `m1-freeze-before.txt`、`m1-freeze-after.txt` 比较无差异。以上为自动测试证据，不替代完整 OCR 复审、真实 HTTP 或浏览器验收；原报告的未验范围仍有效。
