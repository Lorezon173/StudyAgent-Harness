# Task12 退出提示 Escape 优先级独立 OCR 增量复审

日期：2026-11-04。结论：**PASS（仅本轮三文件静态增量）**。原 `representative-fix-round2-code-review.md` 唯一 Medium 已在源码与测试合同层关闭；未发现有实际依据的新问题。原 Needs changes 报告原样保留。本 PASS 不代表浏览器功能或整个工作区审查通过。

## 唯一 Medium 关闭依据

- `web/src/components/workspace/WorkspaceLayout.tsx:55` 的原前景选择器扩为 `dialog[open], [role="dialog"]`。原 Escape/mobile/mobileOpen 条件、setMobileOpen/focus 分支、effect 依赖与注册/cleanup 保持。退出提示在前景时现 guard 阻止背景分支；不存在前景时原关闭抽屉并还焦入口的合同保留。与既有浮卡 hook 的 role 优先 marker 一致。
- 独立字节比较确认：产品 before 用这一处选择器替换后与当前文件完全相等。没有新监听、状态、effect、函数或焦点框架；退出 role、overlay、autoFocus、三个业务回调、保存/备份/留页数据流均无变化。当前产品源码搜索的非原生 role 仅为 exitError 条件挂载提示，没有已知常驻隐藏 role 引起背景抽屉无法 Escape 的路径，不引入假想插件/完整 Tab 陷阱要求。
- `WorkspaceLayout.test.tsx:60` 增补无前景 Escape 后入口还焦；`:164–186` 新增真实移动会话/草稿/账号菜单/503退出出口，核 Escape 前后留页焦点、提示存在、抽屉保持，留页后路由、登录及草稿保留。没有挂假 role 或直接调用 handler。已读取 RED 日志：旧 guard 实际使 activeElement 变为“打开会话导航”，不是收集失败；目标 GREEN 日志记录20项通过。该组件结果与视觉层级/浏览器结果分开。
- `web/e2e/workspace-layout.spec.ts:491` 观察字段补充 drawerVisible/stayFocused，`:516` 在原 Escape 前后增加留页聚焦及会话导航可见断言。原 dialog 可见、notTrigger、浮卡展开/详情、前景命中/宽度/viewport、真实 touch 留页、路由/草稿及 finally 附件/清理全部保留。前后均522行，仅491和516两行不同，其余24项、M3压力及后段断言无变化；未新增第26场景。

因此原抢焦触发路径已被局部 guard 排除，测试能识别旧错误，不再以 notTrigger 代替前景焦点优先。没有把这一结论扩大为“所有背景 Tab 均被禁止”或完整 modal 合同。

## 来源、上下文与冻结

已完整读取补充三层计划、独立计划审阅 PASS、实施交接、三份精确 increment diff、当前 Layout/测试与 M4 完整上下文，并结合本审阅前轮已完整读取的 E2E 其余内容、原 raw/退出合同、Sidebar/浮卡 hook/store 相关调用关系。tracked 按 HEAD 检查原始 diff；新增 E2E 以完整当前内容及前轮完整审阅/字节不变核对覆盖。前轮已审且本轮未变的 overlay/CSS、M3和其他大机制不重新扩审。

计划 SHA256 实核为 `42BBE2776949736DCD467EFAAE9A79A07669D6B90DDEEE00852320147A704DD6`。三目标完整 after 快照与现源逐字节一致；20项当前哈希全部匹配本轮冻结 after，实际3变/17同，结束记录见 [review-hashes](exit-escape-priority-review-hashes.json)。三目标 SHA256：

| 文件 | SHA256 |
|---|---|
| `web/src/components/workspace/WorkspaceLayout.tsx` | `5D00DFE84C7F5C5F9A9BD626558A80E4875772F68AB3722F7B7985A0A172CEA5` |
| `web/src/components/workspace/WorkspaceLayout.test.tsx` | `5EB94461C9B1E6D35B3C2026721A0080CB9392A6FFB500F63F6A65EDB897D848` |
| `web/e2e/workspace-layout.spec.ts` | `0941574DD7EB1ED5A586D882E1FDA3C11F3AB201AFAA13DFB8A9A31F6949C3D5` |

## OCR 范围与逐项覆盖

新执行 `ocr delegate preview --format json --exclude 'docs/delivery/study-workspace-goal/evidence/**,docs/rag-work/evidence/**,.pytest-tmp*/**'`，沿同一进程61037主动检查至 exit0，没有超时重启。完整结果为 [preview](exit-escape-priority-ocr-preview.json)：mode=`workspace`，repository=`D:/backup/basic_file/Program/LearningAgent/StudyAgent-Harness`，total_files=4252，reviewable_count=98，excluded_count=4154。该版未提供 from/to/commit/merge_base 字段，未臆造引用；tracked 以 HEAD 比较。

完整 `(path,status,exclude_reason)` 排除清单存于 preview；自定义参数仅排除上述明确的非产品证据/临时日志目录。目标测试被 `default_path` 排除的两项显式覆盖：Layout.test modified、E2E added。98 reviewable 加2覆盖目标，全部100路径通过 Python argv 每20路径一批取得 rule，5批均 exit0，完整输出为 `exit-escape-priority-ocr-rules-1.json` 至 `-5.json`。未把路径集合合成一个参数。三目标规则均为系统 TS/React 组，内容与前轮相同；已结合类型/null、hook副作用/cleanup、异常/安全与行为覆盖要求审查，未将既有无变化风格机械升级为发现。

各 `(path,status)` 的 reviewed/skipped、具体理由及规则组映射见 [ledger](exit-escape-priority-ocr-ledger.json)，所有条目都有规则。三目标 reviewed；17项本轮冻结无变产品不重审，其余历史交付材料/状态等不属于本轮三目标增量，逐项注明 skipped。工具 excluded 集合保留4154项，不混入以下100项分母。

| 范围 | total_files | reviewed_files | skipped_files | coverage_rate |
|---|---:|---:|---:|---:|
| 本轮目标增量 | 3 | 3 | 0 | 100% |
| workspace reviewable + 2显式覆盖测试 | 100 | 3 | 97 | 3% |

没有 Critical、High、Medium 或有明确价值的 Low 新发现；本报告不能称 whole workspace PASS。

## 未验证和交接

已查阅实施保留日志：定向20、全量428、build完成、collect25；这些是实施者本轮已执行的静态记录，本审阅未重新运行，不冒称独立新跑。RED为实际焦点行为失败，GREEN为组件语义；collect仍只收集。没有启动服务或执行浏览器功能，M3后段、增强M4实际命中/焦点/Escape/留页以及全部25项仍待隔离HTTP复验，原23项不自动继承。单E2E既有Node类型边界未另加依赖或冒称通过。

受控503/人工两倍字号与真实后端故障/原生缩放分列；L1–L4有限覆盖、Task13和B候选边界保持，Task12仍 IN_PROGRESS。本报告只关闭唯一 Medium，不宣称原raw全部验收完成。

只新增审查报告、OCR范围/规则/ledger与结束hash证据；未修改产品、测试、原失败报告或计划，无功能运行、stage/commit。README已检查，由主会话串行汇总更新。
