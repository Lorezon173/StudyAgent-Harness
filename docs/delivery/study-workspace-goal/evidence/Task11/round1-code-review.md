# Task11 round1 独立完整代码审查

日期：2026-11-04。结论：**Needs changes**。Task11 冻结的 12 个源码及测试文件已全部审查，发现 1 项与原搜索失败恢复合同直接相关的 Medium 问题。没有修改产品或测试，没有执行提交、推送、部署。此结论不表示整个工作区通过，也不表示 Task11 真实 HTTP / 浏览器验收完成。

## 基线、冻结和证据

当前 HEAD 为 `0bd2d742ac2c34fd24d6d097f4f37bcb5761cb50`，与实施记录一致。计划所承接的 Task10 产品基线为 `4fff6e1fb250112c9faaa05a914f84164f7f96e9`；实际 Task10 本地提交记录及只读恢复合同已核对，没有将历史验收迁用为本轮证据。

完整阅读 Task11 raw、实施计划、`round1-plan-review.md`、`implementation-report.md`、12 文件冻结清单和最终测试/构建日志。`freeze-before.txt` 与 `freeze-after.txt` 完全相同；本次逐文件 SHA256 与冻结值 12/12 一致，差异 0，见 `review-source-hashes.json`。初次 PowerShell 汇总误将属性名当比较字面值，随后使用属性值比较复核，最终差异确为 0；原始逐文件哈希始终一致。

已加载 `open-code-review-delegate` 技能及项目 AGENTS。实际运行 OCR，而非人工冒充其结果：

- `ocr delegate preview --format json`：workspace 模式；from/to/commit/merge_base 均 null；完整结果保留于 `ocr-preview.json`。首次工具回传过长被截断，之后重新完整落盘，未依赖截断输出编造清单。
- preview：total_files=3618，reviewable_count=1645，excluded_count=1973。
- 全部 1645 个可审路径，另加 4 个被排除的本轮测试，按每批 80 路径调用 `ocr delegate rule --format json`，21 批全部退出 0，原始结果为 `ocr-rules-0.json` 至 `ocr-rules-1600.json`；可审路径规则缺失数为 0。
- `ocr-file-rules.json` 为逐路径规则映射；所有 TS/TSX 使用 system `**/*.{ts,js,tsx,jsx,mjs,cjs}` 规则，CSS 使用 system default；范围外还解析了 YAML/JSON 规则，不因此宣称已审其内容。
- `ocr-checklist.csv` 完整保留全部 3618 个 `(path,status)`、OCR 类型、排除原因、reviewed/skipped 及具体理由。Task11 之外的既有临时测试产物与其他工作区差异明确跳过，没有删除或修改。
- Git 使用 `git --no-pager` 和 `--no-ext-diff --no-textconv --no-color`；workspace 受跟踪文件比较 HEAD，新增文件读全文。受跟踪 diff 另存 `review-task11-tracked.diff`。源码及测试分段阅读，未以输出截断替代覆盖。

## 覆盖统计及逐文件结论

OCR 可审全集：**total_files=1645，reviewed_files=8，skipped_files=1637，coverage_rate=0.486%**。1973 个 OCR excluded 不进入该分母，其中 4 个 Task11 测试已补规则和全文审查。其余排除原因原样保留，未隐去任务外路径。此为明确限定范围的审查，不是全工作区 PASS。

Task11 实际源码测试全集：**total_files=12，reviewed_files=12，skipped_files=0，coverage_rate=100%**。

| path | status | OCR | 审查结果及内容 |
|---|---|---|---|
| web/src/pages/Knowledge.tsx | modified | reviewable | reviewed；完整 diff/源码；查询、分页、账号票据、保存后刷新；发现 M1 |
| web/src/pages/Knowledge.test.tsx | added | excluded/default_path | reviewed（补规则）；16 项全文，断言及模拟 fetch 边界；未覆盖 M1 交错 |
| web/src/pages/Profile.tsx | modified | reviewable | reviewed；完整 diff/源码；默认定位、绑定校验、两请求 revision、分页/迟到 |
| web/src/pages/Profile.test.tsx | added | excluded/default_path | reviewed（补规则）；15 项全文，包括默认会话/版本/来源/账号错误及 finally |
| web/src/components/workspace/WorkspaceLayout.tsx | modified | reviewable | reviewed；完整 diff/源码；仅导航增加本人已核会话/画像参数，恢复逻辑未改 |
| web/src/components/workspace/WorkspaceLayout.test.tsx | modified | excluded/default_path | reviewed（补规则）；完整 diff/源码；现有壳和恢复断言保留，新断言仅验证 href |
| web/src/index.css | modified | reviewable | reviewed；完整 diff/源码；纸感局部样式、窄屏单列/正文换行/dialog 内滚动；视觉效果尚未实测 |
| web/src/components/knowledge/KnowledgeLibrary.tsx | added | reviewable | reviewed；全文；卡片、搜索、错误/旧结果提示、分页；与 M1 共同触发 |
| web/src/components/knowledge/ResourceDialog.tsx | added | reviewable | reviewed；全文；详情/表单/确认删除、独立请求、busyRef、原生 dialog 与焦点 |
| web/src/components/profile/ProfileDetail.tsx | added | reviewable | reviewed；全文；summary 真实节点、边、归档证据与编码的来源会话链接 |
| web/src/components/profile/ProfileSummaryCard.tsx | added | reviewable | reviewed；全文；纯 props 展示、null/0/覆盖率/revision，不提前实施 Task12 |
| web/src/components/profile/ProfileSummaryCard.test.tsx | added | excluded/default_path | reviewed（补规则）；全文；80、0、null、0/0 和 revision 合同 |

额外上下文核对：`api/knowledge.ts`、`api/profiles.ts`、`api/sessions.ts`、`api/workspace.ts`、`api/client.ts`、`types.ts`、`store/auth.tsx`、`App.tsx` 全文；`store/workspace.ts` 的账号代际/票据/路由选择和 `workspaceController.ts` 的选择/flush/最近会话路径；后端 `app/api/knowledge.py`、`LibraryStore`、`app/api/topic_profiles.py`、`ProfileService` 全文及 `workspace_schemas.py` 字段合同。后端 JWT owner 校验、ID 倒序/长度限制、单请求一致快照、summary 有效节点/真实边/已归档证据均与本轮边界相符。

## Critical

无有实际依据的问题。

## High

无有实际依据的问题。

## Medium

### M1：新搜索失败后，旧查询的“加载更多”会抹掉失败和重试目标

- **位置**：`web/src/pages/Knowledge.tsx:80`；共同触发 `web/src/components/knowledge/KnowledgeLibrary.tsx:53`；状态更新证据 `Knowledge.tsx:30–33、49–51、81`。
- **实际入口与触发**：生产 `/knowledge` 页面已成功加载查询 A 的满 50 条结果，因此 hasMore=true。随后用户搜索 B，B 请求失败，页面按合同保留 A、显示“仍显示上次结果”和“重试加载”。失败结束后 loading=false，旧 hasMore 仍 true，因此“加载更多”可以点击。
- **代码证据与结果**：该按钮调用 `load(applied, minId)`，applied 仍为 A。load 一开始把 requested.current 从 B 改成 A、清掉 B 错误；成功后又 setStale(false)。搜索框仍为 B，但列表实际为 A 及 A 下一页，“仍显示上次结果”也消失。B 的可见失败和重试目标被覆盖；即使 A 下一页也失败，“重试加载”已改为 A。
- **用户影响**：搜索失败恢复期间误把不属于新查询的资料当作当前结果，无法沿原错误入口重试 B。不是越权或数据库丢失；本次新增分页与失败保留交互引入，直接影响原 raw A 的“只将本次成功结果标为当前搜索”及“失败保留并可重试”完成条件。
- **验证层级**：完整代码和调用链静态推导，尚未运行专门 DOM 复现或真实浏览器复现；已有 16 项 Knowledge 测试分别覆盖失败保留和分页，但没有覆盖两者相遇。触发无需异常服务对象、恶意插件或新威胁模型，仅一次正常查询网络失败。
- **最小修复**：旧结果标为 stale 时暂禁用/隐藏“加载更多”，并在容器 onMore 加同样局部条件，或以等效局部检查保证当前请求目标与成功列表查询相同才分页。保留 B 错误与 requested，不新增状态机、后端协议或全局框架。
- **必要回归**：先建立 A 满 50 条→B 失败→尝试旧分页的业务 RED，断言 B 错误和旧态未被清掉、没有请求 A 下一页；点击重试实际请求 B，B 成功后清旧态且显示 B。继续保留现有正常分页/去重测试。发现先交主会话裁决，不在审查中擅自修复。

## Low

无有明确价值的独立问题。不以格式、嵌套三元或缺少性能优化凑数量。

## 已核行为、覆盖不足与未验证范围

1. Knowledge 使用既有类型化 CRUD；正文 React 文本渲染，说明/正文清空及 profile_id=null 可发送；保存确认后只 GET 重试，POST 连接失败提示可能重复创建；busyRef 防同步重入，弹窗卸载和账号票据阻止旧续体填入新窗口。未发现实际依据证明跨账号正文泄露。原生 dialog、标签、cancel、返回焦点有 mock DOM 覆盖，不能因此宣称原生浏览器焦点及短视口可用性完成。
2. Profile 从 URL 或服务端最近会话只读定位；session/profile/owner 不一致报错，显式 404 不回退冒充成功；切换主题仅 URL/GET，不调用写绑定、active-node 或 applySnapshot。detail.profile.revision、detail.profile_revision、summary.profile_revision 三者匹配才原子发布，最多两对；正文和卡传同一个 summary，目标不同不混旧标题和正文。同主题旧对保留/错误提示有受控测试证据。
3. null 与 0 保留，均值及覆盖分开，total_count=0 为空态；真实 edges 为空不画伪线；证据链接使用实际 session_id，归档节点不伪造活动标题。Card 无 fetch/存储/拖动，符合 Task12 复用边界。代码中没有上传/PDF/伪页数/自动检索入口。
4. CSS 静态核对保留纸色/墨绿/宋体标题、资料卡与画像双区，既有壳断点未变；窄屏列数和 dialog max-height 有规则。**纸感终稿视觉相似度、1440/481/390 宽和 450px 短高均未在本审查中用真实浏览器确认**。
5. 日志实际为定向 4 文件/45 项、全量 14 文件/398 项、构建退出 0；本审查读取既有冻结日志，没有无故重跑。ResourceDialog.test.tsx 未新增，其对话框焦点、cancel、表单保留及关闭迟到测试整合在 Knowledge.test.tsx；按实质覆盖评估，不要求机械复制同构测试。
6. 实施报告已如实注明编辑失败/删除失败、名称/说明全部边界、部分旧错误/finally 与弹窗交错，以及生成中往返导航尚未逐项验证。导航新增测试只断言 href，没有实际点击→画像→来源返回的端到端证明。上述是原计划的补证缺口，不能以 398 通过抹去，也不据此扩成任意全组合异常矩阵或断言已有缺陷。
7. **真实 HTTP CRUD/重载、跨账号资源和画像拒绝、真实来源会话跳转、真实浏览器 CRUD/焦点/网络故障仍未验收**。本报告不以静态推导、mock DOM、夹具或 build 代替它们；真实模型、PG 重启仍 Task13。Task10 原有限制保留，Task12/13 不宣称完成。

下一步仅建议落实 M1 的既有搜索恢复合同与原计划必要补证。README 与任务账本由主会话串行收口，本审查没有覆盖共享文档。修复后须核新哈希，并针对该局部改动复审，不沿用本次冻结结论宣称新版本已通过。
