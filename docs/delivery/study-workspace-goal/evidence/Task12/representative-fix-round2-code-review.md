# Task12 代表性第二轮修复独立 OCR 增量审查

日期：2026-11-04。结论：**Needs changes**。四目标增量完整覆盖；发现一项有源码依据的 Medium 焦点优先缺口。没有 Critical、High 或额外 Low 发现。本结论不是全工作区审查，也不是浏览器验收结果。

## Medium：退出提示仍在前景时，Escape 把焦点送到其背后的抽屉入口

- **位置**：`web/src/components/workspace/WorkspaceLayout.tsx:55`（既有 Escape handler），与本轮 `:114` 的 fixed 退出提示/留页 autoFocus 相交；遗漏的行为断言在 `web/e2e/workspace-layout.spec.ts:516`。
- **真实支持路径与触发**：<=480px，抽屉仍打开；从其账号菜单请求退出，保存失败后挂载 `role="dialog"` 的退出提示，初始焦点在“留在页面”；此时按 Escape。M4 已明确构造该真实产品入口；503 仅用于受控触发保存失败，不是外部攻击或真实后端事故。
- **源码证据**：移动 handler 只检查 `dialog[open]`。当前退出节点是普通 div 的 role，因此 guard 不生效；随后同步执行 `setMobileOpen(false)` 和 `openButton.current?.focus()`。移动入口始终挂载在 main 的 topbar，退出提示没有 inert/原生 modal 机制阻止程序 focus；本轮 z60 fixed overlay 仍在前景，既有入口在其后。浮卡 hook 的 Escape guard 已识别 `[role="dialog"]`，不能替移动 handler 阻止这次焦点转移。无需假设 listener 顺序：退出 role 在整个按键期间保持挂载，浮卡 guard 会返回。
- **实际影响**：退出提示没有关闭，但键盘焦点离开其安全留页动作，落到被前景遮罩覆盖的导航入口，同时改变背景抽屉状态。用户接续键盘操作不再从正在处理的退出提示开始。这是确定的局部按键处理结果；没有声称已在本轮浏览器复现，也没有声称草稿丢失、越权或完整 Tab 陷阱缺陷。
- **是否新引入及本轮关系**：handler 本身是既有代码，不能包装成本轮新增安全回归；但它直接破坏本轮新加留页初始焦点与既定 M4“焦点优先、Escape 不偷焦”的完成条件。计划第二层 B 的初始聚焦不是“一次 focus 就完成”的承诺，第三层明确仍须验证 Escape；保留原 handler 不等于批准让它抢走前景提示焦点。故分类为**本轮必要局部修复**，不是扩展通用 modal 的后续任务。计划白名单原先要求不改 mobileOpen 逻辑，主会话应记录这一最小范围修订后实施，审查不擅自修改。
- **最小建议**：仅让现有移动 Escape handler 的前景 guard 同时识别既有非原生退出 role（可与已存在浮卡 role guard 对齐）；没有前景提示时保留原抽屉 Escape 行为。增强原 M4 的 Escape 后断言，核“留在页面”仍聚焦、抽屉仍开，再进行原真实留页及草稿检查。现 `:516` 只断言浮卡 trigger 未聚焦，openButton 抢焦仍会被放过。无需新 state、effect、全局监听、原生 dialog、焦点返回协议或完整 focus trap。

## 已审内容与边界

已读 AGENTS/CLAUDE、OCR Delegation skill、原 raw `superpowers/frontend-ui/2026-11-04-task12-round1-raw.md`、第二轮计划及计划审阅 PASS、第一轮运行汇总/诊断和第二轮实施交接。计划 SHA256 实测为 `6114708169FE479C751C4B7C3CB433AC1A84499DC360DA4A495468C9D9631ADB`。

四目标现源均完整读取；结合 HEAD diff（tracked）/新增 E2E 全文及本轮四份 increment diff、完整 before/after 快照审查，并追踪 Sidebar 账号入口、浮卡组件和 hook、workspace 的 mobileOpen/exitPending 与 flushAll 相关调用合同。静态 wrapper/class/autoFocus 未改变 requestLogout、logoutWithBackup、三个业务回调或保存数据通道；CSS fixed/z60 脱离 flex，panel 有界且支持内部滚动。M3 的有限候选点只读命中检查、真实 move/wheel 保留，未 force、隐藏浮卡、程序关闭、减字体或删原压力数据；原25项及 M3 后续正文/独立滚动、M4 命中/留页语义断言保留。除上述 Escape 缺口外，未发现有实际依据的问题。

新增留页测试核初始焦点、留页不登出及草稿；jsdom 不证明 CSS 层级。原 M4 初始焦点已在 stay 时有界 Tab 循环自然为零步，符合计划“不能为走 Tab 而主动移走焦点”；这不构成完整 Tab 陷阱证明，也不要求扩大为完整陷阱测试。

## OCR 范围与覆盖

执行参数：`ocr delegate preview --format json --exclude 'docs/delivery/study-workspace-goal/evidence/**,docs/rag-work/evidence/**,.pytest-tmp*/**'`，mode=`workspace`，repository 为本项目；本版 preview 未提供 from/to/commit/merge_base 字段，未臆造引用，tracked 按 HEAD 比较。首次 preview 沿同一进程 21257 轮询至 exit0；其输出超出工具展示上限，随后另做一次完整写盘 preview（进程 41088，exit0），不是超时重启。正式完整结果见 [preview](representative-fix-round2-ocr-preview.json)：total_files=4190、reviewable=98、excluded=4092；两次间证据文件增加1项，reviewable 清单不变。

完整 excluded 的 `(path,status,exclude_reason)` 保留在 preview。自定义 exclude 仅针对明确的非产品证据/临时产物；测试的 `default_path` 排除被显式覆盖：`WorkspaceLayout.test.tsx` modified、`web/e2e/workspace-layout.spec.ts` added 均纳入本轮目标。98 个 reviewable 与2个覆盖目标全部经 Python argv 每批20路径调用 rule，5批均 exit0，保留 `representative-fix-round2-ocr-rules-1.json` 至 `-5.json`；未把20路径合成单参数。Layout/测试/E2E 采用 TS/React rule；CSS 采用 default correctness/security/performance/test rule。所有文件的规则组映射、逐项审查或具体跳过理由见 [ledger](representative-fix-round2-ocr-ledger.json)。

| 统计范围 | total_files | reviewed_files | skipped_files | coverage_rate |
|---|---:|---:|---:|---:|
| 本轮4目标增量 | 4 | 4 | 0 | 100% |
| workspace reviewable + 2显式覆盖测试 | 100 | 4 | 96 | 4% |

96项逐项 skipped：前轮冻结而本轮未变的产品文件不重复审查；其余历史交付证据/状态等不属于已确认四目标增量，不审其内容。不能据本报告宣称 whole workspace PASS。OCR 排除的4092项属于工具排除集合，不混入上述100项分母；完整清单可回查。

四目标为 E2E、WorkspaceLayout.test.tsx、WorkspaceLayout.tsx、index.css。结束实测20项全部匹配本轮冻结 after，实际4变/16同；快照与当前四源逐字节相等。结束哈希详见 [hashes](representative-fix-round2-review-hashes.json)，四目标分别为 `A67F42D795FCF6D44E78E7C9222EB744E8630D7A53967EFC12A74DDAF7D8D55D`、`4DC92BD2561B33342A3798D44155EFB526E9EBC81054BBE08FD82C6E0C2BA886`、`665210FF9E5B1D952F52F38FED23465DA775D020E54E300E59CF74ADDEB007FF`、`143DBA3B50F158B52BA6D2062134DD1FDEC0555BABB0F98D42F6A2B96F009E9D`。

## 未验证与交接

本审阅没有运行功能、浏览器、服务或新测试；实施交接所记定向19/全量427/build exit0/collect25仅是已有静态记录，不是本审阅新跑，更不证明 M3 后段或 M4 浏览器命中、Escape、焦点及真实留页通过。单E2E的既有 Node 类型边界未新增依赖解决、未冒称类型检查通过。受控503和人工两倍字号不等于真实故障或原生缩放；原23通过不能自动继承。Task12仍 IN_PROGRESS，Task13、B候选与L1–L4限制保持。

仅新增本报告、OCR证据/ledger与结束hash记录；不改产品代码、既有测试、计划或原失败报告，无 stage/commit。README已检查，主会话负责串行汇总本报告及下一步，避免并发改写。
