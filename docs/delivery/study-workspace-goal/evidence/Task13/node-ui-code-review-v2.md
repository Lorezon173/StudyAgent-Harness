# Task13 手动知识点界面独立代码增量复审

**结论　PASS（两个冻结文件的增量代码审查）。** 未发现需要阻断功能验收的问题。上轮输入丢失和明确拒绝误报已修正。真实浏览器、真实模型和 PostgreSQL 结果待独立功能验收。

依据为 [初次审查](node-ui-code-review.md)、[三层修订计划](review-fix-plan.md) 和 [独立计划审查 PASS](review-fix-plan-review.md)。修订计划 SHA-256 为 `6663B6AC35112157BB80BC5A1BE38106AC598AB624A8E2D62671C66C52629F8A`，与计划审查记录一致。

## 逐项复核

- **输入保护。** `ProfileNodeControls.tsx:21–34,35–48,69–72` 同一写锁覆盖请求发出，字段从 busy 到 pending 期间保持禁用。只在新的权威配对读取确认稳定节点 ID 和版本后清空。明确拒绝、结果未知和回读失败均保留输入。回读失败可点「重新读取」，不会发出 POST。 `Profile.test.tsx:204–211,238–247` 分别检查回读失败保留名称和说明、等待期间字段禁用和 403 后保留内容。
- **明确拒绝与待核实。** `ProfileNodeControls.tsx:43–47,58–65` 按现有 ApiError 的 HTTP 状态及冲突代码区分。创建 409 显示画像已更新，其他明确 4xx 显示拒绝与状态码，选点 busy、版本冲突和 404 使用对应提示。网络故障、408、5xx 或无法验证的成功回包继续走待核实路径。已核对 `web/src/api/client.ts` 的结构化 detail/code 解析与 `app/api/topic_profiles.py:16–29`、`app/api/sessions.py:19–30,103–105` 的服务端映射。前端不直接显示未经筛选的服务端正文。各分支保持 GET 回读且不重放写入。测试覆盖 422 和网络故障的不同反馈、创建 409 经权威版本推进后手动提交，见 `Profile.test.tsx:249–257,276–283`。
- **服务端 busy 与失效节点。** `ProfileNodeControls.tsx:18–22,51–65,74–81` 由权威快照恢复选择，活跃请求继续禁用，失效节点随最新详情候选移除。 `app/orchestration/session_service.py:44–55,234–255` 在写入前核活动请求、版本及节点归属和归档状态。 `Profile.test.tsx:259–267` 模拟服务端 busy 后的 active_request_id，重读恢复可选，再模拟 404 并等待旧选项消失，验证两次用户操作分别只写一次。
- **不同非空节点替换。** `ProfileNodeControls.tsx:19–27,50–57,74–76` 用稳定节点 ID 和读取的 state_version 发出 PATCH，回读成功后才确认。 `Profile.test.tsx:213–218,269–274` 覆盖同名节点 ID、归档/异画像过滤、从 a 替换为 b 的版本 4→5 与最终选项。路由、账号和读序号保护沿用原合同，未改变后端或调用权限。
- **浏览器依赖核对。** 非本增量目标的 `web/e2e/workspace-real.spec.ts:113–160` 已补 S1 浮卡链接及两项身份参数、创建请求和详情/摘要版本，以及返回后 Chat 自己请求快照和浮卡显示当前知识点的断言。这里仅确认上轮 UI 审查指出的验收脚本缺口已有源码覆盖，脚本整体独审与功能执行分别留证。

## 审查发现与限制

Critical、High、Medium 无实际依据的问题。Low 保留上轮测试类型告警。 `web/src/pages/Profile.test.tsx:176` 原 `any[]` 仍在，测试响应无法从类型获知 DTO 字段漂移。计划审查把改用 `ProfileNode[]` 列为可顺带处理。此项与这次行为门槛无关。上轮控件内嵌套三元已改为顺序判断。

定向 26 项通过来自实现者交接。本次独审未重新执行测试、全量构建或正式功能。全量前端和真实验收待放行，整分支 OCR 单列。已核 README 当前任务入口，按修订计划由 Task13 交付收口统一更新。

## OCR 范围和逐文件清单

新运行 `ocr delegate preview --format json --exclude 'docs/delivery/study-workspace-goal/evidence/**,docs/rag-work/evidence/**,.pytest-tmp*/**'`。模式 workspace，仓库为本项目，无 from/to/commit/merge_base 字段。Git HEAD 为 `3c9fae413309731b181e72475cf71c980531e7e4`。预览统计 4255 个工作区变更，91 个 reviewable，4164 个 excluded，其中指定目录 3982 个、不支持扩展 126 个、二进制 53 个、默认路径 3 个。 `Profile.test.tsx` 原因是 `default_path`，按指定范围覆盖纳入。对全部 91 个 reviewable 文件与该测试共 92 个路径分批运行 `ocr delegate rule --format json`，均有规则映射。原始 preview、stderr 和规则位于 `C:/Users/A1985/task13-node-ui-ocr-v2-01a16887/`。

| 文件 | 状态 | SHA-256 |
| --- | --- | --- |
| `web/src/components/profile/ProfileNodeControls.tsx` | added，全文和上轮增量已审，rule-80/system 4 | `F107543368A62D8E5C0D12EA1C40E7069C54E6D504084A16E28779EF75A7912B` |
| `web/src/pages/Profile.test.tsx` | modified，HEAD diff、原正文及修订增量已审，rule-80/system 4 | `FF5655BF6430233AFDFC866BCDC64E9BE904744D7F0BF3918DCBA58672C904A4` |

两份调用方沿用初审，`web/src/api/profiles.ts` 哈希仍为 `69860E6911CA98A36ED4F13077E04F28EF889757363F41AE1953A6355006DA52`，`web/src/pages/Profile.tsx` 仍为 `F0360B07A7157F1BC321FCF9C835674A7079A8F0A2A2600D8DE413A5D32F1AF5`。本次只写报告，未改源文件或暂存区。

增量目标 `total_files=2`、`reviewed_files=2`、`skipped_files=0`、`coverage_rate=100%`。扩展工作区清单 `total_files=92`、`reviewed_files=2`、`skipped_files=90`、`coverage_rate=2.17%`。以下每个 `(path, status)` 跳过的理由均为非本次两个冻结目标，后续整分支审查另行覆盖。

| 路径 | OCR 状态 | 审查状态 |
| --- | --- | --- |
| `docs/delivery/study-workspace-goal/status.json` | modified | 跳过 |
| `web/src/api/profiles.ts` | modified | 跳过 |
| `web/src/pages/Profile.tsx` | modified | 跳过 |
| `docs/delivery/2026-10-20-docker-investigation.html` | added | 跳过 |
| `docs/delivery/2026-10-20-docker-investigation.src.html` | added | 跳过 |
| `docs/delivery/2026-10-20-ruff-investigation.html` | added | 跳过 |
| `docs/delivery/2026-10-20-ruff-investigation.src.html` | added | 跳过 |
| `docs/delivery/2026-10-21-docker-deployment-flow.html` | added | 跳过 |
| `docs/delivery/2026-10-21-docker-deployment-flow.src.html` | added | 跳过 |
| `docs/delivery/2026-10-22-cicd-audit-evidence/artifact-index.json` | added | 跳过 |
| `docs/delivery/2026-10-22-cicd-audit-evidence/diagnostic-auth.json` | added | 跳过 |
| `docs/delivery/2026-10-22-cicd-audit-evidence/formal-auth.json` | added | 跳过 |
| `docs/delivery/2026-10-22-cicd-audit-evidence/identity-checks.json` | added | 跳过 |
| `docs/delivery/2026-10-22-cicd-audit-evidence/main-.github_workflows_ci.yml` | added | 跳过 |
| `docs/delivery/2026-10-22-cicd-audit-evidence/main-.github_workflows_release.yml` | added | 跳过 |
| `docs/delivery/2026-10-22-cicd-audit-evidence/main-Dockerfile` | added | 跳过 |
| `docs/delivery/2026-10-22-cicd-audit-evidence/main-pyproject.toml` | added | 跳过 |
| `docs/delivery/2026-10-22-cicd-audit-evidence/migration.json` | added | 跳过 |
| `docs/delivery/2026-10-22-cicd-audit-evidence/remote-snapshot.json` | added | 跳过 |
| `docs/delivery/2026-10-22-cicd-audit-evidence/ruff-.github_workflows_ci.yml` | added | 跳过 |
| `docs/delivery/2026-10-22-cicd-audit-evidence/ruff-.github_workflows_release.yml` | added | 跳过 |
| `docs/delivery/2026-10-22-cicd-audit-evidence/ruff-Dockerfile` | added | 跳过 |
| `docs/delivery/2026-10-22-cicd-audit-evidence/ruff-local.json` | added | 跳过 |
| `docs/delivery/2026-10-22-cicd-audit-evidence/ruff-pyproject.toml` | added | 跳过 |
| `docs/delivery/2026-10-22-cicd-audit-evidence/startup-comparison.json` | added | 跳过 |
| `docs/delivery/2026-10-22-cicd-audit-evidence/structure.json` | added | 跳过 |
| `docs/delivery/2026-10-22-cicd-audit-evidence/teaching.json` | added | 跳过 |
| `docs/delivery/2026-10-22-cicd-audit-evidence/visual-check.json` | added | 跳过 |
| `docs/delivery/2026-10-22-cicd-remote-and-retry.html` | added | 跳过 |
| `docs/delivery/2026-10-22-cicd-remote-and-retry.src.html` | added | 跳过 |
| `docs/delivery/2026-10-22-main-rollout-evidence/119888448587-annotations.json` | added | 跳过 |
| `docs/delivery/2026-10-22-main-rollout-evidence/39797485520-checks.json` | added | 跳过 |
| `docs/delivery/2026-10-22-main-rollout-evidence/39797485520-final-jobs.json` | added | 跳过 |
| `docs/delivery/2026-10-22-main-rollout-evidence/39797485520-final.json` | added | 跳过 |
| `docs/delivery/2026-10-22-main-rollout-evidence/39797485520-latest.json` | added | 跳过 |
| `docs/delivery/2026-10-22-main-rollout-evidence/39797485520-result.json` | added | 跳过 |
| `docs/delivery/2026-10-22-main-rollout-evidence/39797485520-run.json` | added | 跳过 |
| `docs/delivery/2026-10-22-main-rollout-evidence/39797485576-checks.json` | added | 跳过 |
| `docs/delivery/2026-10-22-main-rollout-evidence/39797485576-final-jobs.json` | added | 跳过 |
| `docs/delivery/2026-10-22-main-rollout-evidence/39797485576-final.json` | added | 跳过 |
| `docs/delivery/2026-10-22-main-rollout-evidence/39797485576-latest.json` | added | 跳过 |
| `docs/delivery/2026-10-22-main-rollout-evidence/39797485576-result.json` | added | 跳过 |
| `docs/delivery/2026-10-22-main-rollout-evidence/39797485576-run.json` | added | 跳过 |
| `docs/delivery/2026-10-22-main-rollout-evidence/ci-jobs-current.json` | added | 跳过 |
| `docs/delivery/2026-10-22-main-rollout-evidence/ci-ruff/diagnostics.json` | added | 跳过 |
| `docs/delivery/2026-10-22-main-rollout-evidence/ci-ruff/diagnostics.raw.json` | added | 跳过 |
| `docs/delivery/2026-10-22-main-rollout-evidence/ci-ruff/files.json` | added | 跳过 |
| `docs/delivery/2026-10-22-main-rollout-evidence/ci-ruff/manifest.json` | added | 跳过 |
| `docs/delivery/2026-10-22-main-rollout-evidence/ci-ruff/stats.json` | added | 跳过 |
| `docs/delivery/2026-10-22-main-rollout-evidence/ci-technical/api-auth/manifest.json` | added | 跳过 |
| `docs/delivery/2026-10-22-main-rollout-evidence/ci-technical/migration/manifest.json` | added | 跳过 |
| `docs/delivery/2026-10-22-main-rollout-evidence/ci-technical/structure/manifest.json` | added | 跳过 |
| `docs/delivery/2026-10-22-main-rollout-evidence/file-hashes.json` | added | 跳过 |
| `docs/delivery/2026-10-22-main-rollout-evidence/release-technical/api-auth/manifest.json` | added | 跳过 |
| `docs/delivery/2026-10-22-main-rollout-evidence/release-technical/migration/manifest.json` | added | 跳过 |
| `docs/delivery/2026-10-22-main-rollout-evidence/release-technical/structure/manifest.json` | added | 跳过 |
| `docs/delivery/2026-10-22-readiness-fix-evidence/39808954693-artifacts.json` | added | 跳过 |
| `docs/delivery/2026-10-22-readiness-fix-evidence/39808954693-final.json` | added | 跳过 |
| `docs/delivery/2026-10-22-readiness-fix-evidence/39808954693-status.json` | added | 跳过 |
| `docs/delivery/2026-10-22-readiness-fix-evidence/39808959842-artifacts.json` | added | 跳过 |
| `docs/delivery/2026-10-22-readiness-fix-evidence/39808959842-final.json` | added | 跳过 |
| `docs/delivery/2026-10-22-readiness-fix-evidence/39808959842-status.json` | added | 跳过 |
| `docs/delivery/2026-10-22-readiness-fix-evidence/ci-technical/api-auth/manifest.json` | added | 跳过 |
| `docs/delivery/2026-10-22-readiness-fix-evidence/ci-technical/api-teaching/manifest.json` | added | 跳过 |
| `docs/delivery/2026-10-22-readiness-fix-evidence/ci-technical/migration/manifest.json` | added | 跳过 |
| `docs/delivery/2026-10-22-readiness-fix-evidence/ci-technical/structure/manifest.json` | added | 跳过 |
| `docs/delivery/2026-10-22-readiness-fix-evidence/fault-result.json` | added | 跳过 |
| `docs/delivery/2026-10-22-readiness-fix-evidence/file-hashes.json` | added | 跳过 |
| `docs/delivery/2026-10-22-readiness-fix-evidence/local-candidate.json` | added | 跳过 |
| `docs/delivery/2026-10-22-readiness-fix-evidence/local-ruff-precommit.json` | added | 跳过 |
| `docs/delivery/2026-10-22-readiness-fix-evidence/local-ruff.json` | added | 跳过 |
| `docs/delivery/2026-10-22-readiness-fix-evidence/local-technical/api-auth/manifest.json` | added | 跳过 |
| `docs/delivery/2026-10-22-readiness-fix-evidence/local-technical/migration/manifest.json` | added | 跳过 |
| `docs/delivery/2026-10-22-readiness-fix-evidence/local-technical/structure/manifest.json` | added | 跳过 |
| `docs/delivery/2026-10-22-readiness-fix-evidence/release-technical/api-auth/manifest.json` | added | 跳过 |
| `docs/delivery/2026-10-22-readiness-fix-evidence/release-technical/api-teaching/manifest.json` | added | 跳过 |
| `docs/delivery/2026-10-22-readiness-fix-evidence/release-technical/migration/manifest.json` | added | 跳过 |
| `docs/delivery/2026-10-22-readiness-fix-evidence/release-technical/structure/manifest.json` | added | 跳过 |
| `docs/delivery/2026-10-22-readiness-fix-evidence/remote-ruff/diagnostics.json` | added | 跳过 |
| `docs/delivery/2026-10-22-readiness-fix-evidence/remote-ruff/diagnostics.raw.json` | added | 跳过 |
| `docs/delivery/2026-10-22-readiness-fix-evidence/remote-ruff/files.json` | added | 跳过 |
| `docs/delivery/2026-10-22-readiness-fix-evidence/remote-ruff/manifest.json` | added | 跳过 |
| `docs/delivery/2026-10-22-readiness-fix-evidence/remote-ruff/stats.json` | added | 跳过 |
| `docs/delivery/2026-10-23-agent-collaboration-check.json` | added | 跳过 |
| `docs/delivery/2026-10-23-agent-collaboration-example.json` | added | 跳过 |
| `docs/delivery/2026-10-23-agent-collaboration.html` | added | 跳过 |
| `docs/delivery/2026-10-23-agent-collaboration.src.html` | added | 跳过 |
| `docs/designs/frontend-ui-options.html` | added | 跳过 |
| `test-results/.last-run.json` | added | 跳过 |
| `tests/integration/workspace_observer.py` | added | 跳过 |
