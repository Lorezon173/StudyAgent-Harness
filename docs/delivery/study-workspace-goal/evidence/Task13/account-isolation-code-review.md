# Task13 双标签账号隔离独立 OCR 代码审查

**结论　PASS（六个冻结文件的增量代码审查）。** 未发现阻断项。原高风险路径在代码中已关闭。对于 A 仍打开知识库、另一标签已完成 B 登录的场景，A 的新受保护请求会在网络发送前被拒绝，备份退出保留 B 的共享凭据。同一真实浏览器上下文的功能验收仍待执行。

依据为 [原分支发现](branch-account-finding.md)、[三层修订计划](isolation-and-lint-fix-plan.md) 和 [修订版计划独审 PASS](isolation-and-lint-fix-plan-review.md)。计划 SHA-256 为 `F9FBC82909B3C701757525A55286CA2D40B50A7554F64436697C99E59C7D8AB2`。

## 正式路径核对

- **发出请求前验证身份。** `web/src/pages/Knowledge.tsx:27–55` 的搜索和 `web/src/components/knowledge/ResourceDialog.tsx:105–145` 的创建与编辑都经 `web/src/api/knowledge.ts:1–11` 进入共同客户端。扫描 `web/src` 生产调用只发现 `web/src/api/client.ts:49` 发 fetch，未见其他业务网络出口或 Authorization 写入。客户端在 `client.ts:34–52` 先捕获本标签 ticket，再各读取一次共享 ID 与 token。必须两者都匹配才用 ticket 的 token 发请求。缺项、空 token、只变 ID 或只变 token 均抛固定 `account_changed`，早于建立计时器及 fetch，没有请求、清凭据、跳转、失效通知或自动重发。真正全匿名保持不带 Bearer。后端 `app/core/security.py:41–57` 验签取用户，`app/api/knowledge.py:13–34` 和 `app/infrastructure/storage/library_store.py:19–39` 据 JWT 用户提交或过滤数据。
- **公开认证、合法 401 与迟到结果。** `web/src/pages/Login.tsx:31–51` 只用精确登录与注册 POST。 `client.ts:38,44,63–73` 为这两条路径省略 Bearer，401 继续由本次登录错误处理。受保护请求的真实 401 必须同时匹配请求 generation、ID/token 和响应时共享 ID/token，当前票据才触发 AuthProvider 清理或无 Provider 的回退。A 请求已发后切 B，线上请求仍带 A 的票据，迟到 401 不清 B；同页切换时本地 generation 守卫仍拦截迟到页面结果。跨页已发出的成功 A 请求没有被重新归属为 B。
- **旧标签页退出。** `web/src/store/workspaceController.ts:12–14,693–708` 检查共享身份，A 失配时保存检查返回 stale。 `web/src/components/workspace/WorkspaceLayout.tsx:63–81,114` 在本地票据仍为 A 时展示退出保存提示，备份按钮先要求原账号备份成功。 `web/src/store/workspace.ts:151–210` 备份键按旧票据 userId 生成，再清本地工作区。 `web/src/store/auth.tsx:46–59` 在清理前捕获原票据，删除共享三键前比较当前共享 ID 和 token。B 或同 ID 的新 token 已写好时保留共享三键，同时清 A 的 React 和工作区登录态。当前账号正常匹配退出与匹配 401 继续清理三键。
- **共享存储边界。** 这里的 ID/token 是两次同步读取，登录也分三个键写入。比较和后续删除不组成跨标签原子事务。请求头始终来自已捕获票据，后续共享值变化不会令已建立的 A 请求改带 B 的 token。审查通过范围是共享凭据已完成替换后的旧标签阻断及退出，未验证两个标签在比较和删除之间交错，亦未验证启动正好读到另一标签半写入组合。该范围与已批准计划一致。

## 回归证据

- `client.test.ts:54–85,102–111,130–159` 覆盖合法请求、纯匿名、共享值缺项、单字段错配及已发 A 请求迟到 401。错配用例断言无 fetch、无失效通知及票据与共享值保留。测试分别验证公开认证 POST 无 Bearer、登录失败 401 和受保护当前 401 的清理行为。
- `Knowledge.test.tsx:338–352` 挂载实际 AuthProvider、Knowledge 和 ResourceDialog，只替换共享存储为 B。真实组件事件分别驱动搜索和新建，断言 fetch 次数没有增长、明确显示未发送、表单输入保留。正对照用匹配 B 的票据，通过页面读写并检查 Bearer。已有离线测试仍检查创建结果不确定的提示。
- `auth.test.tsx:23–74,100–106` 覆盖同页迟到 401、当前 401、正常退出代际变更、失败备份标记、旧 A 退出时共享 B 或同 ID 新 token 保留及按 A 保存草稿。定向认证用例直接调用 AuthProvider 的退出入口。完整退出弹窗和 B 继续真实读写留给同上下文验收。
- 实现者交接的客户端、知识库和认证定向验证共 53 项通过。旧 451 项全量和构建记录早于本次冻结，不计作最终候选验证。本次审查未运行测试、浏览器或功能，不替代整分支审查。已检查根 README，按批准计划由 Task13 统一记录用户可见边界。

## 发现

Critical、High、Medium 未发现有实际依据的问题。Low 有一项维护性问题。 `web/src/components/knowledge/ResourceDialog.tsx:135` 新增嵌套三元，把错配、创建连接失败和其他保存错误压在同一表达式，与适用 TypeScript 规则冲突。三个消息分支当前正确，建议用顺序判断表达优先级，无需改变错误合同。此项不阻断正式功能验收。

## OCR 范围

新执行 `ocr delegate preview --format json --exclude 'docs/delivery/study-workspace-goal/evidence/**,docs/rag-work/evidence/**,.pytest-tmp*/**'`，模式 workspace，Git HEAD `3c9fae413309731b181e72475cf71c980531e7e4`。预览无 from/to/commit/merge_base。统计 4296 个工作区变更，94 个 reviewable，4202 个 excluded（指定目录 4017、二进制 53、不支持扩展 126、默认路径 6）。以下三份测试因 `default_path` 排除，按授权覆盖纳入。对全部 94 个 reviewable 加三个覆盖测试执行分批 `ocr delegate rule --format json`，97 个路径均匹配。原始输出及规则见本机 `C:/Users/A1985/task13-isolation-ocr-01a16887/`。

| 文件 | 状态和规则映射 | SHA-256 |
| --- | --- | --- |
| `web/src/api/client.ts` | modified，已审全文和 HEAD diff，rule-0/system 2 | `1E75D9C7A4D825E376BF79C78BBC73B52BD015639E1D6067FF77A2DD6E606D32` |
| `web/src/components/knowledge/ResourceDialog.tsx` | modified，已审全文和 HEAD diff，rule-0/system 2 | `E9E9351AD9F00BC67D0B793044118BB63E44FBA78CBAAAB1D4B819C6F0E38B95` |
| `web/src/api/client.test.ts` | modified，覆盖默认排除，已审全文和 HEAD diff，rule-80/system 4 | `B67558F8955AE12B21EF0F4AA0FF895C21C901815CFC195BCA4775BF1A0336A8` |
| `web/src/pages/Knowledge.test.tsx` | modified，覆盖默认排除，已审全文和 HEAD diff，rule-80/system 4 | `7483CB2985DAC3AFCB5F50FC0B88E97E09424819F645F0F17D2A1D8843BF9463` |
| `web/src/store/auth.tsx` | modified，已审全文和 HEAD diff，rule-0/system 2 | `F9483AF06B3D3660A73782195F53E070463616479357345793FA6FD6831D7A5F` |
| `web/src/store/auth.test.tsx` | modified，覆盖默认排除，已审全文和 HEAD diff，rule-80/system 4 | `075195BE3720D6BDCDFAF8FB500E61D275E0C24CD5AE11A721A8858DAFC14B9B` |

目标 `total_files=6`、`reviewed_files=6`、`skipped_files=0`、`coverage_rate=100%`。扩展清单 `total_files=97`、`reviewed_files=6`、`skipped_files=91`、`coverage_rate=6.19%`。以下每个 `(path, status)` 均因超出六个冻结目标跳过，由相应子项或整分支审查另行覆盖。本轮仅写审查报告，未改源文件或暂存区。

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
| `web/src/components/profile/ProfileNodeControls.tsx` | added | 跳过 |
