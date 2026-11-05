# Task12 Round1 独立代码审查

结论：**PASS（本轮冻结产品、测试及配置的静态代码审查）**。未发现有实际依据的问题。此结论允许进入计划中的正式浏览器验收，不代表 Task12 已完成；真实交互、几何与账号偏好闭环仍须验收。

## 范围、规则与冻结证据

- 基线 HEAD：`a6117c48c1ff7e8877806d0862e69ff0e42f13f4`。已读取项目 AGENTS/CLAUDE、OCR delegation skill、Task12 三层 raw、实施 plan、计划复审 v2、实施 handoff，以及 Task10 的请求关联、恢复副本、账号换代、导航和退出合同与 Task11 Summary DTO。
- `round1-ocr-preview.json` 保留完整 preview：`mode=workspace`；from/to/commit/merge_base 均未指定，受跟踪文件按 HEAD 比较。完整原始排除项也保留。首次输出保存误用了不存在的根目录 Task12 路径，因此没有取得落盘证据；随后已保存到本目录，未将首次输出冒充完整证据。
- 对全部 1648 条可审路径及 8 条补充路径合计 1656 个唯一路径，按每批 100 项运行 rule，17 个成功批次见 `round1-ocr-rules-*.json`；目标文件对应规则见 `round1-target-rules.json`。测试、E2E 与 lock 被默认排除的项已补规则；`workspace.test.ts` 为冻结范围内未变上下文，也补取规则。
- 完整 workspace 清单以 `(path,status)` 为身份，见 `round1-ocr-checklist.json`。`total_files=1648, reviewed_files=11, skipped_files=1637, coverage_rate=0.6675%`；每条任务外路径均明确标记“任务外既有工作区文件；不属 Task12 冻结19文件”。**不宣称整个工作区完整通过。** 2003 条 OCR excluded 项保留原始原因，不计入可审分母。
- 本任务冻结范围：`total_files=19, reviewed_files=19, skipped_files=0, coverage_rate=100%`。包含 OCR 默认排除及未变上下文；完整表见下。逐文件差异见 `round1-diff-*.txt`，新文件读取全文；审阅结合完整生产源码、测试及调用上下文，而非仅判断新增差异。lock 以完整 JSON 结构解析并与 HEAD 的全部既有 package 对象比较。
- 已核 `final-before-hashes.txt` / `final-after-hashes.txt` / `final-hash-comparison.txt`：19 项、changed=0。审阅结束重新核对的19项也全部匹配，见 `round1-review-after-hashes.txt`。本审查未改产品代码、测试或配置。

| 文件 | 状态/处理 | 结论 |
|---|---|---|
| web/e2e/workspace-layout.spec.ts | added，OCR default_path 排除，补规则/全文 | reviewed |
| web/package-lock.json | modified，OCR default_path 排除，补规则/结构比较 | reviewed |
| web/package.json | modified，HEAD diff/全文 | reviewed |
| web/playwright.config.ts | added，全文 | reviewed |
| web/src/components/profile/FloatingProfile.test.tsx | added，OCR default_path 排除，补规则/全文 | reviewed |
| web/src/components/profile/FloatingProfile.tsx | added，全文 | reviewed |
| web/src/components/profile/ProfileSummaryCard.test.tsx | modified，OCR default_path 排除，补规则/diff/全文 | reviewed |
| web/src/components/profile/ProfileSummaryCard.tsx | modified，diff/全文 | reviewed |
| web/src/components/workspace/WorkspaceLayout.test.tsx | modified，OCR default_path 排除，补规则/diff/全文 | reviewed |
| web/src/components/workspace/WorkspaceLayout.tsx | modified，diff/全文 | reviewed |
| web/src/hooks/useFloatingProfile.test.ts | added，OCR default_path 排除，补规则/全文 | reviewed |
| web/src/hooks/useFloatingProfile.ts | added，全文 | reviewed |
| web/src/index.css | modified，diff/全文及既有断点 | reviewed |
| web/src/pages/Chat.test.tsx | modified，OCR default_path 排除，补规则/diff/分段上下文 | reviewed |
| web/src/pages/Chat.tsx | modified，diff/全文及相关 hooks | reviewed |
| web/src/store/workspace.test.ts | HEAD 未变，补规则/全文上下文 | reviewed |
| web/src/store/workspace.ts | modified，diff/全文 | reviewed |
| web/src/store/workspaceController.ts | modified，diff/分段完整生产上下文 | reviewed |
| web/vite.config.ts | modified，diff/全文 | reviewed |

## 分级结果

- Critical：无。
- High：无。
- Medium：无有实际证据的产品缺陷。
- Low：无值得单列的问题；不将自动规则的格式偏好升级为本轮功能阻断。

## 关键合同复核

1. **账号偏好与最近会话共用版本。** `workspaceController.ts:230–311` 复用 workspaceLoads/workspaceSaves；forceFresh 不绕过同代在途 GET。PATCH 只带当前 dirty 字段；纯偏好不带 last_session_id，recent sequence 与 prefs dirty 分离；响应须确认版本递增及本轮提交值。保存中较新值保留 dirty，由原单飞循环继续写入。GET 沿原 readSequence/version/ticket 门禁，dirty 偏好字段保留本地值。409 重读版本后保留本地待保存值，最近会话冲突继续显式选择；纯偏好冲突提供重试，不导航或消费候选。
2. **深链及导航合同。** Layout 按有效 account generation 初读；profile/knowledge 初读不调用 selectSession。lastSession 新门禁阻止共享旧读取把用户新选 B 导回 A，且允许本地目标与服务器相同的有效恢复。旧测试取消“必须并发第三个 GET”的设施假设，保留 B 写入及不加载旧 A 的用户断言；handoff 已记录业务 RED/GREEN，不据此放宽 Task10 导航合同。
3. **退出与换代。** flushAll 等待同一 workspace 队列，单独报告 preferences；旧账号成功、错误及队列清理由 ticket/generation 保护。偏好强关仅承诺服务端确认值，未新增本机偏好恢复协议；保留原草稿/请求逐项备份与未知请求门禁。
4. **真实指标。** Chat ready 且 session/profile owner 关联有效后挂载；浮卡复核 revision，null 与0分不同，沿 Summary DTO 的 mastery_score、coverage、前三个非归档节点显示；默认 SummaryCard 合同保留。无自行 GET 或伪造下一步教学建议；完整画像链接包含本会话与画像 ID。模型/用户文本继续由 React 文本或既有 Markdown 路径处理，无新增 HTML 注入。
5. **局部交互。** hook 中连续容器、hover/focus/touchLock、Escape dismissed 门禁、显式重开、严格大于4px阈值、350ms click抑制、主 pointer/左键、capture清理、cancel不提交、12px方向键及有限0–1比例均有对应分支。会话/账号/隐藏/卸载清理局部拖动。正常结束才保存位置，pointermove不调用消息或摘要API。真实事件和浏览器默认焦点顺序仍属下一步验收。
6. **几何与层级。** 使用 host/topbar/composer/card 真 rect、8px留白和零travel保比例；展开/resize只重新测量，不保存夹取后的比例。CSS保留481–760的170px双栏及<=480抽屉，浮卡限制主区宽度、详情内部scroll，移动遮罩/导航高于浮卡，reduced-motion关闭动画。极短可用高度、200%字号、输入/账号可达及非原生退出提示的实际层级不能由静态审查证明，须浏览器记录。

## 依赖与验证证据

- 已读取最终全量日志：`final-full-test.log` 为16文件/423测试通过、EXIT_CODE=0；`final-build2.log` 为TypeScript及Vite构建通过、EXIT_CODE=0。此处核查现有冻结日志，未冒称本审查再次运行全量测试。
- `playwright-collect.log` 仅证明21用例可收集。配置使用系统Chrome/Edge、loopback HTTP与独立Vite端口，reuseExistingServer=false，未自动下载浏览器。真实后端用例在无 TASK12_ISOLATED_API 时明确skip，不能当作真实持久化通过。
- package.json精确固定 @playwright/test 1.64.1为devDependency；lock仅新增 @playwright/test、playwright、playwright-core 三个1.64.1 dev包，所有既有package对象零变化。新增包要求Node>=20；安装debug记录Node24.11.0，兼容当前环境。Vite/Vitest默认排除保留并追加e2e/**。
- 原安装摘要报告13 vulnerabilities（6 moderate、5 high、2 critical）。已读取原 `playwright-install-npm-debug.log` 的成功bulk响应：命中既有 @vitest/mocker、baseline-browser-mapping、browserslist、esbuild、nanoid、postcss、react-router/dom、source-map-js、tinypool、vite等，新增三个Playwright包不在该bulk报告中；结合lock零既有版本变化，不能把13项归咎于本次新增依赖。开发构建/测试工具的可达影响与真实线上路径须另评估；React Router属于既有运行时依赖，其告警也不能泛称全为开发依赖或已修复。本轮不自动升级整树。
- 新鲜 `npm audit --json` 请求因 `ENOTFOUND registry.npmjs.org` 失败，已保存 `round1-audit-current.json`。上述归属判断基于原成功bulk及完整lock比较，**不是新鲜联网审计通过**。

## 必须保留的未验范围与后续

- 本审查未启动真实浏览器，未执行正式HTTP账号偏好闭环，也未实测新增静态交互分支；所有交互判断为源码分析。此前423项受控DOM测试与构建不代替浏览器验收。
- 下一步按原计划运行正式React HTTP：完整14个宽高组合、真实mouse/focus/Tab/Escape重开、触摸与capture/cancel、350ms、12px、展开resize短高内部滚动、200%字号/长链接/reduced-motion、账号/输入/导航可操作、原生及非原生modal层级。
- E2E现有真实HTTP用例包含A保存/重登、B默认及跨账号拒绝；尚未完整表达“B保存后再回A”、新尺寸下UI实际ratio位置、同账号跨会话草稿/阅读锚点保持等所有计划合同。后续须补实际验收证据或最小测试断言，不能仅运行现21用例就宣称全部合同通过；新增测试改动可独立增量审查，不因此重启未变的19项审查。
- 深链reload需分别记录GET、sidebar状态、ratio缓存、URL不变、无PATCH，再进Chat复用ratio；受控并发与真实HTTP记录分开。
- Task13真实模型连续教学与真实PostgreSQL重启等尚未在本轮验证，不据本报告宣称完成或上线。
- 已检查根README目前仍为Task11历史状态；README/账本按主会话既定串行职责，在浏览器实际结论后更新Task12能力与未验边界。本独审不并发改写README，不提交、推送、部署。
