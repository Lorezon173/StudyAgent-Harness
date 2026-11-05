# Task12 Round1 修订计划独立复审

结论：**PASS（仅计划审查）**。首轮 M1 已在设计、文件职责、实施步骤与验收四处闭合。未发现有实际依据的新增阻断问题；不代表产品实现、测试或真实 HTTP 验收已完成。

## 输入及覆盖

- raw：`superpowers/frontend-ui/2026-11-04-task12-round1-raw.md`，SHA256 `E58574DADBAEFD0C538F047D5D30EE741AB7E01C808147A27502575923FF1323`。
- plan：`docs/superpowers/plans/2026-11-04-task12-round1.md`，SHA256 `DB6B9C59F21DE5E080F0CBB6EAF71B7594E0287E9AF2DFD11635956C3AAA15B6`。
- 本轮重新读取两份全文，核对首轮证据中的正式路由、WorkspaceLayout、useWorkspaceController 与当前 loadWorkspace/lastSession 调用合同。`total_files=2`、`reviewed_files=2`、`skipped_files=0`、`coverage_rate=100%`，仅指两份计划，不是代码审查覆盖率。
- 未改产品代码、未执行产品测试或 OCR；实施后 Task E 的完整 OCR 及独立源码审查仍须执行。

## M1 复核：已解决

1. **入口明确。** raw 第 55、83 行明确由有效账号的 WorkspaceLayout 按 account generation 调用 `ensureWorkspacePreferences(ticket)`，覆盖 `/profile`、`/knowledge`、`/chat`；plan 第 45 行已放入 Layout 允许职责，第 60、70 行列入生产接线。
2. **复用既有机制。** raw 第 55、57、83 行保留 loadWorkspace 的 GET、版本、readSequence、ticket 门禁与同 generation 在途读取；prefs.loaded 只复用本轮既定状态，不新增缓存、版本队列、generation 或初始化框架。forceFresh 的并发语义明确为不绕过同代在途读取，同时保留完成缓存后的重新读取能力。
3. **边界明确。** prefs 入口不调用 lastSession 后导航、不调用 selectSession、不写 last_session_id、不验证/消费/删除候选；既有 loadWorkspace 读取服务器参考值与列出候选的只读行为保留。Chat 原 hook 仍独立消费结果并应用原导航门禁。初读失败、卸载、慢响应与账号换代的处理也已写明。
4. **验证对应真实入口。** plan 第 64–65 行覆盖深链首次挂载、无账号、两种并发调用顺序、无 PATCH、URL/最近会话不被改变、本地先编辑和换代晚结果；第 103 行及 raw 第 93 行增加真实 HTTP 深链刷新与后续 Chat ratio 恢复，同时与受控竞态结论分列。

实施时 plan 第 65 行“候选清单……不因 prefs 入口而改变”应结合 raw 第 55 行解读为“不因偏好动作选择、验证、消费、删除或覆盖既有候选”；原 loadWorkspace 初次列出恢复候选的只读行为仍允许。该上下文已明确，无需为字面上的空清单到已加载清单变化禁用 Task10 原恢复能力。

## 原范围回归复核

- 保留真实同源 A 环形、Chat ready 可见条件、null/0/覆盖数与前三有效节点语义、Task11 默认 SummaryCard 合同、无虚构下一步建议。
- 保留 hover/focus/touch/Escape 可重开、4px 严格阈值、350ms、防误点/capture/取消及幂等清理、方向键 12px。
- 保留真实导航/composer 几何、8px 留白、有限 ratio 0–1、零 travel 与 resize/展开不漂移、短高内部滚动、消息请求/草稿/阅读锚点保护。
- 保留同一 expected_version 单飞 PATCH、recent/prefs dirty 分离、409 不静默覆盖与显式重试、账号隔离、退出等待和仅已确认偏好的强关承诺；新增读取不构成第二写入者。
- 保留默认固定、481–760px 的 170px 双栏、<=480 抽屉、收起取消固定、切会话不自动收起、modal 层级及全部宽度/450px 短高矩阵。
- 保留精确 Playwright 开发依赖、真实 pointer/HTTP/重登 A/B 验收、受控故障分列、完整测试/build/OCR/独审、主会话串行 README/账本及明确文件提交。
- 无后端、B checkpoint、K 规划、新持久化框架、推送/部署扩张；Task13 真实模型与 PG 重启仍未验。

## 后续交接

可按已批准范围开始实施。首次加载去重语义属于本轮必要联接，实施后仍须运行既有 Task10 相关读取、最近会话恢复与冲突测试；不能用本次计划 PASS 替代兼容性证据。真实深链恢复、真实偏好重登及完整浏览器矩阵未完成时，Task12 必须保留未完成项。
