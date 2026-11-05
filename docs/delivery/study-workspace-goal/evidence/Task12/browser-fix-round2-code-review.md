# Task12 浏览器第二轮修复独立 OCR 增量审查

2026-11-04。结论：**PASS（仅本轮冻结三项增量的静态审查）**。未发现有实际依据的问题。允许进入已批准计划的浏览器功能复验，不代表原三项失败已在真实场景解除，更不代表 Task12 DONE。

## 范围与工程证据

已读 AGENTS.md、CLAUDE.md、Open Code Review Delegation Mode skill、Task12 原始三层 raw、本轮计划及计划独审 PASS、前轮诊断/19通过3失败汇总、本轮实施交接、前轮最小修复与补验合同。已完整分段阅读本轮三文件，并核对 FloatingProfile、Chat、WorkspaceLayout、NewSessionDialog、未改纯函数测试及相关调用合同。未扩展为未变产品的整轮重复审查。

新鲜 `browser-fix-round2-ocr-preview.json` 保留完整原始清单：mode=workspace，repository 为本项目；输出未提供 from/to/commit/merge_base，不能编造引用。total_files=3853，reviewable_count=1759，excluded_count=2094。执行沿同一活句柄91509轮询至 exit0，未重启 preview。

规则覆盖1759个可审路径及两个默认排除目标，共1761个唯一路径。最初100项批次中部分因 Windows 命令行过长失败（错误保留 `browser-fix-round2-rules-errors.json`）；随后改为 Python subprocess 参数列表、每批20项，89个 `browser-fix-round2-ocr-rules-valid-*.json` 批次全部 exit0，解析文件组覆盖1761/1761，missing为空；有效错误表为空。未将失败批次当成功。`browser-fix-round2-target-rules.json` 保留三目标对应的系统 TypeScript/React/异步/安全规则。

显式范围覆盖：`FloatingProfile.test.tsx` 与 E2E 被 OCR `default_path` 排除，本审查明确 override 纳入三项目标，已单独取规则并阅读全文；默认排除不构成跳过理由。其他2092项仍保留原排除原因。

| 文件 | preview状态及处理 | 审阅结论 |
|---|---|---|
| web/src/hooks/useFloatingProfile.ts | added；全文、组件/布局调用上下文与旧诊断合同 | reviewed |
| web/src/components/profile/FloatingProfile.test.tsx | added、default_path排除；显式override、全文 | reviewed |
| web/e2e/workspace-layout.spec.ts | added、default_path排除；显式override、全文、同哈希前轮快照增量比较 | reviewed |

三项均为 Git 未跟踪文件，已核 `git --no-pager status --short`；没有可用 HEAD 旧文件 diff，未伪造。E2E 前轮完整快照 `e2e-revision-source-current.txt` SHA256恰为前轮冻结 `C28E16933211F94E8EF0B8EAD27F0E80D6565F6DD471A78BE7E8CD7125AD033E`；逐行增量保存于 `browser-fix-round2-e2e-increment.diff`。hook/组件测试本轮前的完整字节快照未找到，旧分支依据前轮诊断、既有审查与冻结哈希记录核对，不声称恢复了完整旧源码；当前文件完整静态审阅已覆盖。

workspace逐项清单见 `browser-fix-round2-ocr-checklist.json`，以(path,status)为身份。可审工作区统计：**total_files=1759、reviewed_files=1、skipped_files=1758、coverage_rate=0.05685%**；任务外每项明确标记“任务外既有工作区改动，不属本轮冻结三项增量”。本任务显式范围统计：**total_files=3、reviewed_files=3、skipped_files=0、coverage_rate=100%**。两统计分母不同，不宣称整个workspace PASS。

## 分级结果与合同核对

- Critical：无。
- High：无。
- Medium：无有实际依据的问题。
- Low：无值得单列的问题。

1. **Escape产品缺口**：hook第40–53行仅open时注册window冒泡监听，同一个处理器负责关闭，原容器Escape分支已移除。defaultPrevented、isComposing先返回；卡外输入/其他聚焦控件因不属于卡内/BODY/根节点而不被接管；BODY/根节点还须hover或touchLock。现有原生dialog、退出role dialog、非hidden移动侧栏标记与真实布局一致。合格关闭preventDefault、dismissed置位、touchLock清除、open关闭后回入口；onFocus受dismissed保护，避免立即反开，出入/显式点击沿旧合同重开。不调用savePreference。effect按open/sessionId/generation清理，旧会话关闭与卸载无第二监听持有旧trigger。已核调用方没有第二容器Escape绑定。
2. **必要组件测试**：第10–42行补BODY焦点hover→Escape关闭、还焦、出入重开及无保存；覆盖外部输入、组合输入、已阻止事件和三个现有覆盖层DOM；会话/generation切换与卸载检查事件不被旧监听消费。旧聚焦入口/显式重开、拖动取消、12px和350ms测试保留。测试用innerHTML仅为固定覆盖层常量，无外部输入注入。真实事件顺序仍以浏览器复验为准，不以jsdom覆盖层构造替代真实modal验收。
3. **键盘合法前提**：E2E第173–184行先核真实下边界矩形及ratio=1，再断言Down不动/无新增比例PATCH；确认上方≥12px，Up12后Down12恢复原位置及ratio，每步等待受控PATCH/状态变化。容差没有放宽为任意正位移。原4px、capture、cancel、350ms、草稿、snapshot/messages计数保留，并补summary零增量。当前固定场景若不在预期边界会明确失败，不会静默假定成功；不同运行布局是否满足前提由复验确认。
4. **深链观测**：E2E第97–115行在reload前安装局部监听，主frame首次期望path提交后登记GET的Request对象；response必须属于该集合，第一合格响应到达即开始json读取，成功值或错误均保存，无吞错或未处理读取拒绝。第255–276行等待读取结果并严格断言GET200、三偏好、URL、收起DOM、单次导航和零workspace PATCH，再回Chat核ratio；finally清理三个监听。相同URL旧文档早发晚回响应没有登记Request，不能冒充新GET。额外导航由navigations断言失败。前置goto新增GET等待及DOM应用，响应观察不改服务器/产品行为，没有独立GET替代reload应用。

## 冻结、验证与限制

开始及结束核对本轮三项SHA256均一致：

| 文件 | 当前SHA256 |
|---|---|
| useFloatingProfile.ts | 5B102104D093044CCDC8F287132726BD16DD9C4E061882E5C7C1B1F926ED5668 |
| FloatingProfile.test.tsx | E9E3375884371ACCF50B331D79F05D52D28E4AFC95737CC0178E74D91E33DD2D |
| workspace-layout.spec.ts | F8C3C5AD69E56C4E67E5427D2213082B81472F2748763A04766929AC1C0D6275 |

与`round1-review-after-hashes.txt`的19项实核见`browser-fix-round2-hash-check.json`：本轮范围外16项全部未变，未对它们重新宣称完整审查。`useFloatingProfile.test.ts`仍为`FB13F79D2593D863AB25857B558A140238223F8EBCDFD1D2C4EC39828606CCA7`。

本审阅读取现有日志确认16文件/426项通过、构建完成、静态收集22项，与交接相符；未重新运行测试、构建或任何浏览器功能。原RED为BODY hover Escape不能关闭，不是缺导出或收集失败。静态验证不证明真实事件、几何、HTTP保存或A/B隔离闭环。

原真实深链`Network.getResponseBody`底层原因仍未知：新文档关联和立即读体是观测改良，是否解除错误须实际复验。原22项19通过/3失败记录继续有效；后续B保存再回A等后半步骤未验，不能继承为通过。需按计划完整运行本轮22项至终态，分别报告受控与真实结果，Task12仍IN_PROGRESS、Task13 PENDING。

本审查只新增报告及审查证据，未改三项源码/测试、未暂存/提交/推送。已检查README当前Task12段；README/账本由主会话按本报告和后续实际结果串行维护，避免并发覆盖。
