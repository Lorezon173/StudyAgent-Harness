# Task13 本地收口三层计划

**依据**　[正式验收计划](implementation-plan.md)、[候选审阅覆盖](candidate-review-coverage.md)、[后端回归](final-backend-regression.md)、[前端回归](account-final-web-regression.md)。本文只规划收口，独立计划审查和实际证据门槛均通过后才能准备交付材料。

## 第一层　模块总览

- 当前正式浏览器同 run 已完成 26 项，Python baseline 已通过。应用重启、同卷 PostgreSQL 重启、重启后五资源隔离、独立双标签验证仍以实际运行和独立审计为准。全部通过、最终候选映射闭合且证据独立审计通过，才启动下列收口。届时复核真实应用进程、PostgreSQL postmaster 与同卷同库、见证故障信号、候选指纹、两账号与同一主 run，缺任一门槛即停在现阶段。
- 输出为原约定的验收文档、README 自有更新、资产清单自有追加、两笔本地提交及 status/progress 账本。第一笔先提交产品和验收材料并实核，第二笔才记 DONE 和实际 SHA。保留用户现有 README 162 行和资产清单 34 行差异；保留失败记录与候选 B 的独立边界。第一阶段本地验收与任何推送或部署分开。
- 回归证据分层。默认隔离 pytest 1362 通过；67 为指定 SQLite/PG 混合回归的总数；前端 452 与构建分别记录；正式浏览器 26 按真实与受控分组。Ruff 0.17.1 全量仍退出 1，599 条既有诊断；实际按路径、规则码和诊断消息作多重集对比，旧 605 去掉本轮 6 项后与新 599 完全一致，final-only 为 0。交付记录不将其写为全仓通过。

## 第二层　子模块概述

| 子模块 | 职责与输入输出 | 失败策略 |
| --- | --- | --- |
| A 证据与文档 | 以真实验收、独立双标签及冻结候选映射生成追踪表、交付文档、README 更新与资产条目。 | 缺证据、指纹漂移或独立审计未完成时保持未收口。 |
| B 清单与保护 | 生成逐文件白名单、工作树原字节保护记录及两个混合文件的 HEAD 专用暂存补丁。 | 任一恢复哈希、前缀、差异行、链接或索引不一致即暂停。 |
| C 提交及账本 | 实核第一笔产品提交后，第二笔记录 DONE、真实 SHA 和本地收口核验。 | 任一提交不符清单或保护检查时保留现场，按实际状态汇报。 |

## 第三层　详细实施计划

### A 验收材料

- [ ] 冻结实际最终候选及主 run 的证据索引。确认浏览器正式通过、Python 基线、应用重启、PG 重启、五资源隔离及独立双标签都能追溯各自日志/退出状态。主运行用同一浏览器资源清单核真实模型输入见证、旧题与续答、消息/状态/评分证据、两主题三会话和画像版本。双标签独立核真实阻断、备份及 B 读写。按账号和资源记录拒绝及无副作用。独立审计核追踪、凭据脱敏、阶段顺序和指纹，覆盖映射须包括最终 17 项，继承的整分支审查与增量逐项对应。待下文产出文档后，由独立材料审查补齐文档自有差异的覆盖。
- [ ] 新建 `docs/delivery/2026-10-23-workspace-acceptance.md`。按原需求、入口、通过条件、同 run 标识、实际结果、证据链接、限制编表。分列模型与教学状态、应用/PG 重启、五资源与双标签、真实 PG 受控冲突/保存失败/租约/幂等、SQLite 故障回归、全量与固定 Ruff。保留阶段二、候选 B、已知输入反馈及既有类型/环境等经核限制。README 仅更正已提交知识库鉴权错误的一处短语，并新增 Task13 段说明当前能力、真实入口、API、启动和迁移/恢复边界及验收链接。资产清单只追加 Task13 交付及核心证据索引。

### B 明确清单与选择性暂存

- [ ] 第一笔将下列 17 项与独立审查和运行冻结指纹逐项比对。建立明确文件清单，字段包括路径、状态、暂存方式、SHA256/索引 blob、证据用途及来源。文档和证据另逐条列出完整路径，包括验收文档、本轮计划和独审、候选覆盖、可复查的脱敏运行摘要/日志与必要的历史失败。已有原 raw/核心计划若在 HEAD 中则仅核链接和内容，已有证据仅在需要且脱敏验证通过时列入。禁止用目录或通配符代替路径清单。大批诊断材料按用途和可复查性筛选，保留原件；凭据、原模型提示词/正文、私有探针、截图缓存、与本任务无关的历史差异排除。逐一核对交付链接能落到 HEAD 或明确清单。
  - `app/agents/critic.py`、`app/harness/teaching_context.py`
  - `tests/integration/test_retriever_integration.py`、`tests/integration/test_workspace_resume.py`、`tests/integration/workspace_observer.py`、`tests/unit/orchestration/test_conversation_context.py`
  - `web/e2e/workspace-real.spec.ts`、`web/src/api/client.ts`、`web/src/api/client.test.ts`、`web/src/api/profiles.ts`
  - `web/src/components/knowledge/ResourceDialog.tsx`、`web/src/components/profile/ProfileNodeControls.tsx`
  - `web/src/pages/Knowledge.test.tsx`、`web/src/pages/Profile.tsx`、`web/src/pages/Profile.test.tsx`、`web/src/store/auth.tsx`、`web/src/store/auth.test.tsx`
- [ ] 改文档前，在私有目录保存当前 HEAD、README 与资产清单完整原字节、SHA256 和两文件相对 HEAD 的用户差异有序基线。核 README 162 行和资产 34 行保护对象。README 工作树仅改已提交的一处鉴权旧文和新增 Task13 段，逆向去掉新段并还原唯一旧短语后必须逐字节恢复修改前完整文件。资产清单仅追加，前缀原长与原字节完全一致。保留原编码及换行。用户原文和基线快照留私有目录。
- [ ] 分别以 HEAD blob 构造 README 与资产清单只含本轮自有改动的缓存补丁。README 补丁仅两项，资产补丁仅附加 Task13 段。独立材料审查核明确清单、差异、完整字节保护及脱敏后，确认 HEAD 未变且索引为空，再对两补丁运行 `git apply --cached --check` 并应用到索引。整文件暂存仅用于明确归属 Task13 的其余路径。核实际 staged diff、文件清单、指纹和空白错误，两份混合文件不得整文件暂存。

### C 两笔本地提交与核验

- [ ] 以冻结 HEAD 为直接父提交创建第一笔产品和验收提交。核实际完整 SHA、父提交、路径集、17 项索引/提交内容及 README 和资产清单的自有片段。检查索引为空。以第一笔 HEAD 比较工作树的 README、资产清单用户增删内容和顺序，应与原 162 行、34 行差异一致。复做 README 逆向恢复哈希与资产前缀校验，保留核验结果。
- [ ] 第一笔核验通过后才更新 `docs/delivery/study-workspace-goal/status.json` 和 `progress.md`，写 Task13 DONE、真实第一笔 SHA、证据及范围完成状态。第二笔白名单仅这两项和 Task13 独立提交核验记录，保留账本其它历史及候选 B。独立核对差异后，以第一笔为直接父提交创建第二笔，并实核完整 SHA、父链、白名单、状态引用及空索引。再次确认 README 和资产的用户差异原样保留；报告真实提交及 Ruff 限制。未经另外授权不执行 push、PR 或部署。

