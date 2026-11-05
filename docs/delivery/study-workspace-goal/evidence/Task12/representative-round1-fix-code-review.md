# Task12 代表性首轮局部修复：独立 OCR 增量审查

日期：2026-11-04。结论：**PASS（仅本轮四文件静态增量审查）**。未发现有实际依据的问题；本结论不代表 25 项浏览器功能已通过，Task12 仍为进行中。

## 输入与冻结边界

已读取 AGENTS.md、CLAUDE.md 和 `C:/Users/A1985/.agents/skills/open-code-review-delegate/SKILL.md`，应用 Open Code Review Delegation Mode。OCR 负责范围和规则，当前独立审阅 Agent 负责源码分析。审查输入为局部修复计划、计划独审 PASS、首轮运行汇总/诊断与实施交接。计划 SHA256 复核为 `F55DEC17511648F07E956166ECA8954D614AC148744E3C05648E0A891185460C`。

HEAD 复核为 `a6117c48c1ff7e8877806d0862e69ff0e42f13f4`。已查看 workspace 模式要求的三份 tracked 文件 HEAD diff；未跟踪 E2E 直接完整读取。HEAD diff 包含历史 Task12 实现，**本轮判断以四份 `representative-round1-fix-increment-*.diff` 及对应 before/after 全文为准**，没有把历史浮卡/恢复实现混成本轮新增。

本轮四个目标文件完整源码均已读完，E2E 分段覆盖至文件结尾；结合 MessageBubble、ChatComposer、WorkspaceLayout、FloatingProfile、useFloatingProfile 调用上下文复核。冻结清单共 20 项：实际 4 项改变、16 项不变；所有当前文件和 before/after 快照 SHA256 均与实施清单一致。最终独立结果见 `representative-round1-fix-review-final-hashes.json`。

| 本轮目标 | after SHA256 | 结果 |
|---|---|---|
| `web/src/index.css` | `6962089ED491BD4A07433423B92C1FE531D986F0C7D0194BE72D302876C46884` | reviewed |
| `web/src/pages/Chat.tsx` | `51E84FF4FD50A56B04D3C020BE54282184F0B4B36A18380CE0D215181377F2F4` | reviewed |
| `web/src/components/workspace/SessionSidebar.tsx` | `DA327ED887FB090501209360D1613E8ECCD2BEFF6619A167C978569E7A3871F5` | reviewed |
| `web/e2e/workspace-layout.spec.ts` | `9F26C8C60C00941E62A67BFB80AB0795F99819751E84A7AAE7AD933E7E0CD652` | reviewed，显式覆盖 default_path 排除 |

## OCR 工程证据与覆盖

实际执行参数为：

```text
ocr.cmd delegate preview --format json --exclude docs/delivery/study-workspace-goal/evidence/**,docs/rag-work/evidence/**,.pytest-tmp*/**
```

仅明确排除上述日志/证据目录，没有添加产品或测试排除。该进程活句柄为 3408，持续轮询同一句柄直至退出 0，没有超时重启。新原始输出完整保存在 `representative-round1-fix-ocr-preview.json`，stderr 文件为空。metadata：schema_version=1、mode=workspace、repository=`D:/backup/basic_file/Program/LearningAgent/StudyAgent-Harness`、total_files=4103、reviewable_count=98、excluded_count=4005、total_insertions=463250、total_deletions=68。输出未提供 from/to/commit/merge_base 字段，不臆造引用。

完整 4005 项 excluded 的 `(path,status,exclude_reason)` 原样保留于 preview；其中目标 `web/e2e/workspace-layout.spec.ts` 为 added、503 insertions、0 deletions、`exclude_reason=default_path`，本审查显式覆盖该排除并审阅全文及本轮差异。

规则通过 Python subprocess 的 argv 列表，以最多 20 路径为一批执行 `ocr.cmd delegate rule --format json <独立路径参数...>`。98 个 preview 路径与上述 E2E 共 99 路径全部取规则，五批退出码均为 0；没有把多路径拼成一个参数。完整规则保存在 `representative-round1-fix-ocr-rules-{0,20,40,60,80}.json`，对应 stderr 均为空；所有分组已阅读。目标 TSX/E2E 使用 system 的 JS/TS/React 规则，CSS 使用 system default 的正确性、安全、性能、可维护性与测试规则。

逐文件 `(path,status)` 清单、规则文件/组映射、reviewed 或具体 skipped 原因见 `representative-round1-fix-ocr-checklist.json`。未修改的冻结文件只核 hash，不重审其历史行为；范围外既有交付、日志及产品文件逐项标明跳过，不宣称整工作区通过。

| 口径 | total_files | reviewed_files | skipped_files | coverage_rate |
|---|---:|---:|---:|---:|
| OCR 原始 reviewable | 98 | 3 | 95 | 3.06% |
| 加入显式 E2E override 后完整清单 | 99 | 4 | 95 | 4.04% |
| 本次批准的增量范围 | 4 | 4 | 0 | 100% |

## 增量审阅判断

- **Chat/CSS**：Chat 本轮仅标题 class/tabIndex、原消息 scroller class 与原 composer ref 容器 class 改动；恢复 useLayoutEffect、scrollRef/hostRef/composerRef 所在元素、message id、草稿/锚点与发送算法未变。标题限高 `min(25%,96px)`、全文纵滚及 focus-visible 保留全文读取入口；消息 min-height/min-width、composer 不收缩及表单 flex 对应原结构。普通文本/URL anywhere 与 pre/code 的保留空白/内部横滚规则在现有 MessageBubble 外 flex/内 bubble DOM 上可达，没有新增 Markdown 解析或信任边界变更。
- **Sidebar/CSS**：仅新增顶部静态 wrapper，列表与账号 footer 仍是兄弟；顶部 35% 有界滚动、列表最低 48px、footer 不进入滚动 wrapper，aside 未新增 overflow 裁剪。账号菜单既有定位追加 z-index 45，高于浮卡 5；移动 aside 原 40 保持。没有新增状态、回调、队列或测量框架。
- **M2**：`workspace-layout.spec.ts:384–386,405` 将重新到达目标手柄与关闭期间分开，仍断言所有步骤焦点不在详情，非目标关闭步骤仍要求 expanded=false；Escape、内部 Tab 关闭、详情 DOM 不存在与离开后重新 focus 可开断言均保留，后续鼠标链保留。与原 hook 的 blur 后重入合同相符。
- **M3**：原 600×450、长主题/标题、24 会话、30 消息与长 URL、逐元素真实 computed 字号乘二、reduce 和正文/末尾链接均保留；只在首条消息附加代码块。`workspace-layout.spec.ts:438–446` 在 fill 后保存真实区域、消息/列表正高度、可视范围、标题预算与键盘/滚轮滚读断言；命中前没有 scrollIntoView。`448–457` 保留发送/账号命中、代码块内部横滚、列表/消息独立滚动及横向无外溢；锚定 baseline 移至相同保存行/字体状态后，没有删除状态提示以腾空间。静态上未发现断言绕过已知缺口。
- **M4**：`workspace-layout.spec.ts:491,498` 的关闭导航均精确匹配；真实 touch、展开前提、命中、Tab/Escape、留页草稿与 context finally 保留。没有预先修改尚未实测的退出提示层级，也没有先关抽屉绕过其后段。

未在本轮差异发现新增空值访问、资源泄漏、异步清理错误、XSS/注入、数据写入或越权路径。未变的后端/API、状态机制与恢复合同不扩大审查。

## 问题与未验证范围

Critical：无。High：无。Medium：无。Low：无。**未发现有实际依据的问题。**

已核实施日志所载定向 301/full 426 通过、build 退出 0、collect 25；这是实施阶段已有记录，本审阅没有重新执行功能或测试。collect 仅证明收集，不证明行为。

本次尚未运行修复后的真实浏览器 25 项，不能静态保证标题/顶部 End 滚动、600×450 双倍字体实际几何与命中、URL/pre 内滚、原 core22、M2 后段、M4 受控 503 退出提示及真实账号组均通过。退出 role 提示是否可命中仍待实测；没有将既有可疑层级猜测列为本轮回归或放宽测试。人工两倍字号不等于原生浏览器缩放；L1–L4、Task13 和既有有限覆盖边界保持。

本次只新增审查报告、OCR 证据/清单与独立 hash 核对；未修源、未 stage/commit。README/status 依交接由主会话维护。后续应按已批准计划运行完整 25 项至终态，保留真实成功/失败证据；本 PASS 仅解除该静态增量审查门禁。
