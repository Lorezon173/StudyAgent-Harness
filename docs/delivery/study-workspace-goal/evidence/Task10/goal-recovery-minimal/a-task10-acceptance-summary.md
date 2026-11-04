# Task10 / A 最终分类验收汇总

验收执行：2026-11-03；文档收口：2026-11-04。**验收通过，待明确本地提交；Task10 仍为 IN_PROGRESS / VERIFIED_UNCOMMITTED，commit=null。** 依据[独立最终证据审计](a-task10-acceptance-audit.md)收口；本文整理既有执行证据，没有重新运行测试、模型、浏览器或 SQL。Task11 尚未开始，Task12/13 仍 PENDING；Task13 整体验收未因本次有限结果完成。B 仍是 TODO 中 DEC-SESSION-001 的独立候选，未实施。

## 行为与证据分类矩阵

| 验收项 | 结果与证据类型 | 证据及边界 |
| --- | --- | --- |
| 已有冲突下，新可信冲突阻止旧成功覆盖与清副本 | 通过：RTL、静态审阅、真实浏览器受控网络 | [实施记录](a-implementation-report.md)、[产品 OCR](a-ocr-code-review.md)、[final-02](browser-controlled/20261103-a-browser-final-02/report.json) conflict；保留本人/另一 writer 精确副本、禁发、POST=1，后续真实按钮主动重查恢复 |
| 新网络/游标失败后旧有效消息可恢复 | 通过：真实浏览器＋合成网络 | final-02 network/cursor-loop 各 pass。先正确答案＋活动待确认＋禁发，再实际“重新查询会话状态”后 enabled；另一 writer 副本完整、POST=1。消息 matched 不等于活动门禁已 clear，不绕过既有门禁 |
| 已有 inconsistent 的双候选 source 组合 | 不适用：支持入口不可达 | [产品 OCR](a-ocr-code-review.md)及[审计](a-task10-acceptance-audit.md)：主重查不带 source，候选入口遇已有 inconsistent 退出。相邻可达 source 场景证明来源变化警告、其他副本保留和 POST=0，不冒充该组合通过 |
| 全前端回归与构建 | 通过：技术验证 | [365 项/11 文件日志](a-final-suite.log)、[构建日志](a-final-build.log) exit=0；前后 46 项冻结哈希一致。不能替代真实行为验收 |
| 独立审阅 | 通过：限定范围静态审查 | 产品 OCR 46/46；[设施 v3](a-browser-script-review-v3.md)及既有 v1/v2、计划审阅保留。不宣称整个工作区已审 |
| 注册/登录、创建、草稿、真实问答及权威读取 | 通过：真实页面、真实模型、PG、本人 HTTP | [首次问答](a-real-first-turn-verification.md)、[重启后本人 API](a-real-owner-api-readback.md)及[原始响应](a-real-owner-api-responses.json)：4 请求 completed/persisted=true，8 消息逐字段与 PG 一致；B 同画像独立会话、精确草稿、无消息。创建选择框未专门截图，按实际操作及日志/身份核对支持 |
| 刷新、正常退出保存及同账号重登恢复 | 通过：真实页面操作＋持久化 | [退出恢复](a-real-refresh-logout-verification.md)、a-real-logout-resume.png；精确草稿、view version=3、最近会话及历史恢复。无时间戳访问日志只作辅助，不伪造某 PATCH 与点击的毫秒关联 |
| 真实模型在途 A→B→A，结果按桶归位 | 通过：真实页面时钟＋PG＋页面后态 | [第四轮时序](a-real-fourth-turn-time-verification.md)、a-real-fourth-switch-time.json、a-real-fourth-a-after.txt/png、a-real-fourth-b-after.png：切 B 结束后约 5.33 秒的完成事务时间支持请求仍在途；A 精确回复归 A，B 已编辑草稿保持且无 A 消息 |
| 失败/冲突及恢复 | 通过：受控浏览器分类观察 | final-02 的矛盾消息、503、游标回环及真实按钮恢复；这些是合成网络，不称真实模型失败或草稿 409，也不把 503 称断网 |
| 实际连接关闭与恢复保存 | 通过：真实代理连接故障＋页面＋HTTP/PG | [连接故障恢复](a-real-connection-failure-recovery.md)、失败/恢复 txt/png：专用 Vite 停止，错误可见、原文和本机副本保留、重试出口可见；恢复后 HMR reload，用户实际选择恢复本机草稿，最终 API/PG 精确草稿、version 2→3、消息=0。不是 browser offline，也不是无刷新手动 retry；客户端总尝试次数不可据无关联日志确定 |
| PostgreSQL 重启后原数据与应用可读 | 通过：专用 PG 实际重启、新连接指纹＋真实页面＋本人 HTTP | [PG 重启](a-real-pg-restart-verification.md)、[本人 API](a-real-owner-api-readback.md)：稳定排序全字段指纹一致，4 请求/8 消息/B 草稿保持；健康 200 仅辅助 |
| 跨账号拒绝 | 通过：实际 API 与实际 UI，分别执行 | [跨账号 API](a-real-cross-account-api.md)：session/request/messages 403、profile 404；a-real-cross-account-ui.png：另一个 UI 测试账号自有空列表、直访无权，无 A 内容。API 与 UI 使用不同隔离账号，不拼接为同一次登录；API“不含标记”不等于任意字段泄漏审计 |
| Task8 HTTP/SSE 对照 | 通过：同冻结历史实测＋本次哈希复核 | 审计核 Task8/round3-code-freeze-manifest.json 的 26 项当前 SHA 无差异、app/tests 相对 Task8 提交无 diff；引用 Task8 的 round3-affected-primary.log 100 passed、round3-affected-routes.log 12 passed（含 stream_error/realtime）、round3-pg.log 20 passed。未本轮重跑，不称当前真模型 SSE 验收 |

## 原始失败与可接受边界

- final-01 的 network/cursor-loop 原失败及所有证据原样保留。根因是验收遗漏既有活动重查步骤，补步骤后仍保留最终 enabled 断言；没有修改产品解锁或降级通过条件。
- final-02 原 report.status=failed，source-change=blocked，三核心各 pass；原始报告、退出结果和截图不改写。业务汇总对不可达组合裁决为 N/A，不称脚本整轮全绿。
- 浏览器等待为精确 Request/状态/正文/requestfinished，再独立任务与双帧观察；不等于业务函数退出的规范级证明。确定性交错由 RTL 另证，合成 persisted=true 不证明保存。
- 首轮用户要求“不要先考我”，真实回复仍反问，是教学质量限制。本次接线与持久化验收不等于教学策略质量通过，相关意图路由仍属独立工作。
- PG now() 为事务时间，主机/容器未独立校时；第四轮支持常规在途切换证据，不声称精确提交时间或切换后的五秒窗口内又完成新编辑。
- 私有服务日志无时间戳/关联标识，不补造精确请求先后/尝试次数；认证、密码、JWT、数据库连接串和私有运行配置不纳入交付。

## 提交与后续

[精确提交清单](a-task10-local-commit-manifest.json)和[选择性暂存方案](a-task10-local-commit-plan.md)供执行者使用；本文不执行 Git 写入，也不生成不存在的 commit。文档/清单复核并完成实际本地提交后，由主会话记录真实 SHA 再决定 Task10 DONE；不推送、不部署。下一任务为 Task11 的独立规划，尚未开始。