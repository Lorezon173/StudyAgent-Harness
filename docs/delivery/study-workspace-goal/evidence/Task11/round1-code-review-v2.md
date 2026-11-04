# Task11 round1 修复后全范围独立代码复审

日期：2026-11-04。结论：**PASS（仅限下述冻结的 Task11 源码/测试审查）**。已复审完整 12 文件，M1 已解决，**未发现有实际依据的问题**。这不是全工作区 PASS，不表示 Task11 真实 HTTP、浏览器或交付验收完成；Task12/13 仍不在本次完成结论内。

## 冻结与执行证据

沿用已加载的 `open-code-review-delegate` 技能和项目 AGENTS，按真实生产入口、已批 raw/plan 和原报告记载的 API/后端/Task10 合同复审，没有重新扩大威胁模型。当前 HEAD 为 `0bd2d742ac2c34fd24d6d097f4f37bcb5761cb50`。

已读取 `implementation-report.md` 的 M1 追加记录、`m1-business-red.log`、`m1-green.log`、`m1-full-test.log`、`m1-build.log` 和 `m1-freeze-before.txt` / `m1-freeze-after.txt`。两份冻结文件完全相同；当前 12 文件 SHA256 全部与 M1 冻结一致，差异 0，见 `review-v2-source-hashes.json`。相对上次审查仅三文件发生变化：Knowledge.tsx、KnowledgeLibrary.tsx、Knowledge.test.tsx，其余九文件哈希不变。本复审仍逐文件核完整代码/测试和 HEAD diff，没有只审核 M1 几行。

重新执行完整 OCR：

- `ocr delegate preview --format json` 成功，完整保存 `ocr-preview-v2.json`；workspace 模式，from/to/commit/merge_base 均 null；total_files=3653、reviewable_count=1670、excluded_count=1983。与上轮数量差异包含上轮新生成的规则、索引等证据，不据此推断产品新增。
- 全部 1670 个可审路径，加 4 个 OCR 排除的本轮测试，分 21 批获取规则，均成功退出 0；原始证据 `ocr-v2-rules-0.json` 至 `ocr-v2-rules-1600.json`。全部可审路径规则缺失数 0，逐路径映射为 `ocr-v2-file-rules.json`。TS/TSX 使用 system JavaScript/TypeScript/React/异步/安全规则，CSS 使用 system default。
- `ocr-v2-checklist.csv` 对全部 3653 个 `(path,status)` 逐项保留 reviewable/excluded、exclude_reason、reviewed/skipped 和具体理由。历史临时测试产物、其他既有变更、审查生成索引等本轮产品范围外内容明确跳过；没有称它们已通过。
- Git 全程使用 `git --no-pager`，diff 使用 `--no-ext-diff --no-textconv --no-color`；tracked 比较 HEAD、新增读全文，当前完整 tracked diff 保存于 `review-v2-task11-tracked.diff`。较长回传发生截断的部分另作分段补读，没有以截断结果代替覆盖。

本代理未修改产品/测试，没有运行提交、推送或部署；没有无故重跑已终止的完整测试。下列测试结果来自已读取且与冻结匹配的实施日志。

## 完整覆盖和逐文件清单

OCR 可审全集：**total_files=1670，reviewed_files=8，skipped_files=1662，coverage_rate=0.479%**。另有 OCR excluded 1983，其中 4 个 Task11 测试补规则、补全文审查，其余保留排除原因。任务外清单完整记账不等于内容全审。

Task11 实际源码/测试全集：**total_files=12，reviewed_files=12，skipped_files=0，coverage_rate=100%**。

| path | status | OCR | 本次结果及复核重点 |
|---|---|---|---|
| web/src/pages/Knowledge.tsx | modified | reviewable | reviewed；查询/分页资格、错误与重试目标、票据/序号、保存刷新 |
| web/src/pages/Knowledge.test.tsx | added | excluded/default_path | reviewed（补规则）；原16项及新增M1业务回归，全文 |
| web/src/pages/Profile.tsx | modified | reviewable | reviewed；默认会话、只读绑定、同revision发布、旧结果/错误隔离 |
| web/src/pages/Profile.test.tsx | added | excluded/default_path | reviewed（补规则）；15项全文，目标/revision/来源/分页/账号 |
| web/src/components/workspace/WorkspaceLayout.tsx | modified | reviewable | reviewed；本人当前会话导航定位，既有恢复/flush不改 |
| web/src/components/workspace/WorkspaceLayout.test.tsx | modified | excluded/default_path | reviewed（补规则）；完整旧合同与新增href测试 |
| web/src/index.css | modified | reviewable | reviewed；完整局部纸感样式与既有壳上下文，窄屏/短高静态规则 |
| web/src/components/knowledge/KnowledgeLibrary.tsx | added | reviewable | reviewed；全文，旧态禁分页、错误/卡片/空态 |
| web/src/components/knowledge/ResourceDialog.tsx | added | reviewable | reviewed；全文，CRUD/表单保留/未知POST/关闭迟到/原生dialog |
| web/src/components/profile/ProfileDetail.tsx | added | reviewable | reviewed；全文，真实summary节点/边/归档证据和来源链接 |
| web/src/components/profile/ProfileSummaryCard.tsx | added | reviewable | reviewed；全文，null/0/覆盖率及纯props接口 |
| web/src/components/profile/ProfileSummaryCard.test.tsx | added | excluded/default_path | reviewed（补规则）；全文，分数/覆盖/revision |

## M1 关闭依据

原问题：A 满页后 B 搜索失败，旧 A 的分页可改写 requested、清 B 错误与旧态。当前 `KnowledgeLibrary.tsx:53` 在 loading 或 stale 时禁用分页；`Knowledge.tsx:80–84` 的容器入口另要求非 stale、requested.current===applied 和非空列表。没有新增状态、框架、后端接口或协议。

因此 B 失败时 A 只作为已标记旧结果保留，分页不再触发 load(A)，不会清掉 B 错误或把重试目标换回 A；点击“重试加载”仍读取 B。B 成功后原 load 将 applied=B、stale=false，保留原 hasMore 和 before_id 行为，正常 B 分页可继续。

`Knowledge.test.tsx:301–338` 新测试验证完整用户行为：A 满50→B 503→分页disabled且点击不发任何 before_id→B错误与“仍显示上次结果”仍在→重试B→B结果替换A且清旧态→B按before_id=151加载续页。原正常分页和重叠去重断言未被删除或降级。

证据层级明确：`m1-business-red.log` 在原实现出现 `more.disabled` 预期 true / 实际 false 的业务失败，exit 1；此前 `m1-red.log` 使用不存在断言 API 的失败不算业务 RED。修复后 `m1-green.log` 为 Knowledge 17项通过、exit 0；`m1-full-test.log` 为14文件399项通过、exit 0；`m1-build.log` 为 TypeScript/Vite 构建通过、exit 0。此为真实React页面+模拟fetch的受控测试，不是浏览器/真实服务实测。

## 原范围合同复核

- **Knowledge**：既有搜索、50条/id游标、去重、详情及完整文本CRUD路径保留；确认写成功后的GET失败与未确认写失败区分，POST连接失败保留表单并提示主动重发风险；原busyRef、弹窗卸载和账号generation/票据约束没有被M1改动绕过。正文仍是React文本，未增加HTML注入、伪上传或自动检索宣称。
- **Profile**：URL或最近会话默认定位、会话/profile/owner校验、404不冒充其他画像、选择主题仅URL/GET且不改会话绑定均保留；detail内外revision与summary一致才配对发布，最多两对，正文/卡共用summary；不同目标不混标题/内容，同主题失败可保留旧对并提示。
- **数据含义**：null/0、已评估均值、覆盖n/m、0/0空态、真实edges与来源session链接继续忠实DTO；已归档来源不冒充有效节点。ProfileSummaryCard仍仅props渲染，无fetch/状态存储/拖动副作用，Task12挂载交互未提前实施。
- **导航与Task10**：WorkspaceLayout只新增已核本人当前session/profile的画像链接，离开聊天的原flush/选择清理以及返回真实来源路由继续走既有实现；未修改Chat、API client/types/store或后端。现有导航新增测试主要证明href，不将其当作生成中往返的完整浏览器验收。
- **终稿与文本限制**：纸色/墨绿/宋体标题、资料卡/画像双区、窄屏单列、长正文折行和dialog最大高度规则存在；没有固定分数、假关系、伪PDF页数或样式切换脚本。视觉实物是否达到终稿，仍需真实浏览器按原视口验证。

## 严重程度及未验证范围

Critical：无。High：无。Medium：无。Low：无有明确价值的问题。原M1已关闭，未新增修复项。

PASS仅是冻结源码及现有测试的完整范围代码审查结论。原报告已公开的缺测继续保留：独立编辑/删除失败、全部名称/说明边界、部分旧错误/finally/弹窗组合、生成中往返等尚未逐项补证；不以399通过替代它们，也不扩为任意全组合异常矩阵。ResourceDialog测试整合于Knowledge.test.tsx，不要求机械新建同构文件。

真实HTTP A创建→搜索→详情→编辑→重载→删除、B跨账号拒绝、真实来源跳回、浏览器登录/CRUD/焦点/Escape/网络恢复、纸感视觉与1440/481/390宽及450px短高仍**未由本审查验证**；Task11不得仅凭本PASS宣布DONE。真实模型与PostgreSQL重启仍属Task13。README、资产及状态账本由主会话串行维护；本审查不修改共享文档或全局规则。
