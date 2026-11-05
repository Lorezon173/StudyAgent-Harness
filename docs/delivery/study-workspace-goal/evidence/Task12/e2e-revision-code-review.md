# Task12 E2E 修订独立 OCR 增量审查

日期：2026-11-04。结论：**PASS（仅冻结单文件静态增量审查）**。未发现有实际依据的问题；不代表浏览器用例或 Task12 验收通过。

## 范围与冻结

- 唯一审查目标：`web/e2e/workspace-layout.spec.ts`，完整阅读 330 物理行。审查开始、结束 SHA256 均为 `C28E16933211F94E8EF0B8EAD27F0E80D6565F6DD471A78BE7E8CD7125AD033E`。
- 对照 `round1-review-after-hashes.txt` 独立复核 19 项：仅该 E2E 文件变化，其余 18 项一致，见 `e2e-revision-hash-check.json`。未重新对未变 18 项作完整独立审查。
- 旧冻结哈希为 `BCEA7D592917A871A91D4969496F1FC4A4AFE0A6AE673C51F58E64057F264AE0`。该文件仍为未跟踪文件，`git diff HEAD` 没有旧源码，`git ls-files --error-unmatch` 明确未命中，不能据空 diff 判定无变化。
- 从保留的原 21 项 `error-context.md` 提取旧源码行 1–161，行号连续、各现场重叠内容无冲突，保存为 `e2e-revision-old-source-evidence.json` 并生成 `e2e-revision-source-comparison.diff`。这是现场展示源码对照，重建字节哈希不等于旧冻结哈希，**不冒称原旧文件逐字节备份**。本次正文完整快照为 `e2e-revision-source-current.txt`。
- 依据：修复计划及其 PASS、补验计划及 v2 PASS、交接、原失败诊断/汇总，以及前轮静态审查；追踪当前 FloatingProfile/useFloatingProfile、Chat 阅读位置记录/恢复、WorkspaceLayout/SessionSidebar、workspaceController 保存与加载、DTO 与现有 Playwright 配置。

## 新执行的 OCR 与覆盖

`ocr delegate preview --format json` 已在本次执行；活句柄 90740 持续轮询至 exit 0，未重启同一 preview。完整结果见 `e2e-revision-ocr-preview.json`：mode=`workspace`，from/to/commit/merge_base 均未提供（null），工作区比较基准为 HEAD。原始排除清单及原因完整保留。

| 口径 | total_files | reviewed_files | skipped_files | coverage_rate |
|---|---:|---:|---:|---:|
| 本次确认的单文件增量 | 1 | 1 | 0 | 100% |
| OCR 默认可审条目（均任务外） | 1674 | 0 | 1674 | 0% |

Preview 总条目 3746，其中 2072 被 OCR 排除，另有 1674 可审条目。目标 E2E 被 OCR 以 `default_path` 默认排除，本次依据用户明确指定范围覆盖该默认排除，另取单文件规则并完整审查；此范围覆盖不改写原 preview。逐 `(path,status)` 状态、任务外跳过原因、规则组对应与原始排除原因和 `explicit_scope_override` 见 `e2e-revision-ocr-checklist.json`；不宣称整个工作区审查通过。新 raw/plan/hash/运行证据等属于任务外文档或证据，其他产品改动属于本轮未变/其他任务范围。

所有 1674 个可审路径均已重新取规则并核集合覆盖，缺失 0、额外 0；有效结果是 `e2e-revision-ocr-rules-correct-*.json`，目标单文件规则另存 `e2e-revision-target-rules.json`。最初 PowerShell 数组传参生成的 `e2e-revision-ocr-rules-*.json` 将多路径合成单参数，**不作为规则覆盖证据**；后改为 Python subprocess 逐参数传入。80 路径批次在 560 处遇 Windows 命令长度限制，余下改 20 路径批次完成；不是隐藏失败或冒称该失败批次成功。

## 核对结论

1. **路由边界**（20–44行）：在解析 body 和记录 calls 前检查 pathname，`/src/api/client.ts` 正常 continue；实际未知 `/api/` 仍 404。双会话复用同一边界，没有再引入过宽模块拦截。
2. **手势与旧断言**（59–84、134–157、260–277行）：先 hover 展开、轮询 rect，再核中心命中；每次重新准备，mouse capture 在 down 后验证，完成手势有实际位移检查及释放检查。触摸使用实际 pointerdown 捕获的 id。原 4px 零保存、正常一次保存、350ms 前后点击、合成取消不保存、键盘位移、草稿与消息请求断言保留。合成 cancel 和 hover 准备后的 CDP 触摸没有冒充原生取消或纯触屏完整路径；独立 tap 开关仍保留。
3. **真实保存闭环**（174–255行）：真实组无 route mock、无伪造认证；正式登录，UI PATCH 200 加独立认证 GET；拖动先核可用空间，再核位移和几何比例。A 保存收起后用移动抽屉正常退出，抽屉打开/账号菜单/退出后核三偏好；1024×900 重登检查收起 DOM 和比例。桌面展开后更新 A 确认基线，B 默认、B 实际保存、B 读 A snapshot 的 403、再回 A 的三偏好与可见比例断言完整。
4. **深链**（226–240行）：每页 goto 和 reload 分开观察；reload 前监听 GET，收到 200、三偏好一致、URL 与收起 DOM 应用后结束窗口，核无 workspace PATCH，再回 Chat 测 ratio。未以短时间无请求直接替代加载完成，也未把进入 Chat 的正常选择写入混进深链窗口。它是顺序初始化验收，不是同代并发/晚响应竞态测试。
5. **受控双会话**（11–46、287–327行）：按 sessionId 保存独立草稿、锚点和 version，multi PATCH 校验 expected_version，snapshot 返回相应会话状态；共同账号 workspace 偏好独立于 view-state。通过正式输入、滚动与侧栏导航建立 s1→s2→s1，断言中段非空锚点、DOM 消息/偏移、新草稿、s2 自有草稿/消息、共同 ratio 及无教学 POST。请求按交互/切换分段，未错误要求合法切换零 GET，也未把准备阶段藏到新基线前。生产 flush 当前同时发送 draft/reading_anchor，与该局部 fixture 消费合同相符；此 fixture 不是后端通用部分 PATCH 实现或真实持久化证明。

## 严重度与未验证边界

Critical：无。High：无。Medium：无。Low：无有明确价值的新增问题。

本次未执行任何浏览器功能、真实 HTTP 持久化、完整 web test/build、真实模型或 PostgreSQL 重启。交接所述 22 项收集 exit 0 仅为收集证据；独立 tsc 的 TS2580 缺既有 Node 类型仍为失败，未重新运行或改称通过。原 21 项 0 passed / 21 failed / 0 skipped 完整保留，新断言尚未证明实际可通过。

首次 hover 引起手柄位置变化按已批准 raw 的展开重测几何合同和主会话范围裁决保留为待浏览器验证交互限制，不据此自动要求产品重构。实际运行仍须确认手柄稳定后的命中/capture/位移、默认视口连续手势与键盘剩余空间、真实 GET/PATCH、深链窗口及双会话恢复；失败时须另存现场，不将静态 PASS 升级为功能完成。真实拖动附件在断言成功后生成，若提前失败，应由运行阶段额外保留其事件/几何/请求现场，不能仅凭缺少成功附件推断原因。

仅新增本审查报告及审查证据，未修改产品/测试/配置，未功能运行、暂存或提交。已检查 README 的 Task12 状态仍为验收未通过；其“补验尚未编码”描述需由主会话按批准分工串行更新，本审查子任务不越界改 README/账本。
