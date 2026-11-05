# Task13 教学与评价边界独立 OCR 代码复审

**结论　PASS（四份冻结文件的增量代码审查）。** 未发现阻断项。正式教学等级边界和最新待答题引用的两处缺口已在源码中关闭。旧评价测试继续从真实评价入口验证原机械指标及数值断言，评分依赖使用测试作用域内的受控替身。

依据为 [整分支审查 Medium](branch-ocr-review.md#medium)、[检索环境与无 judge 诊断](pytest-environment-diagnosis.md)、[三层修订计划](teaching-and-evaluator-boundary-plan.md) 和 [计划独审 PASS](teaching-and-evaluator-boundary-plan-review.md)。计划 SHA-256 为 `1EBE5FB2B1E7FC18B579251A75356E00A9173D1FEFB502374852EF5806389D80`。

## 核对结果

- **掌握等级。** `app/infrastructure/llm.py:168–178` 解析模型 JSON，正式会话经 `app/orchestration/conversation_service.py:281–286` 构造上下文并进入线上 runner。 `app/agents/critic.py:51–79` 在原有待答题、活跃节点与合法分数的前提下，先要求等级为字符串，再查 `MasteryLevel`，数组、对象和非法字符串不会产生 `MasteryAssessed`，后续 confusion、contradiction 与低置信度仍走原分支。缺少正式上下文的兼容分支保留。 `app/orchestration/assembly.py:270–298` 仍只依据合法当前节点的评分事件生成 delta，`app/orchestration/turn_commit.py:198–230` 仍核已持久化的最近助手待答题与本轮回答，然后提交评分。修订未调整评分范围、授权、持久化或事件字段。 `tests/unit/orchestration/test_conversation_context.py:410–430` 以正式上下文进入真实协作环、使用受控 LLM，非法等级时观察仍出现、无评分和 delta、练习次数不增，合法 partial 正对照保留题目 ID 和节点关联。
- **待答题引用与预算。** `app/harness/teaching_context.py:105–118,187–204,221–246` 先验证并排序历史，以最近助手、正文相同且阶段 awaiting_response 确定题目 ID，始终保留最近真实用户与助手项。 `teaching_context.py:267–311` 现要求保留历史项的 ID、助手角色和真实题干同时匹配，找不到则保留原有 1000 字的文本回退。摘要预算、历史项目上限和 12000 字历史预算仍由原布局计算，最终输入的 4000 字上限不变。 `test_conversation_context.py:433–453` 保证两条同文助手消息都进入 prompt，但只引用已核较新 ID；最新助手题干不匹配时明确回退原文。原多 Agent 提示词、受保护消息及摘要边界用例未删除。
- **评价数值与 unavailable。** `tests/integration/test_retriever_integration.py:179–247` 仅在旧数值用例内显式设置 fake 检索，monkeypatch 可用 judge、三个指标和 Dataset/RAGAS。测试实际建索引并调用 `RetrieverAgent.evaluate`。 `app/agents/retriever.py:348–476` 仍执行真实 coordinator.search、机械指标、Dataset 组装和评分归一。保留原召回、冗余、延迟、三项数值范围断言，另核 0.71/0.82/0.93、实际检索上下文、模型和向量句柄、指标列表及唯一调用。测试不会在生产 catch 内吞掉自己的断言。评价器产品逻辑未改，`tests/unit/agents/test_retriever.py:313–327,899–924` 的 None、unavailable、机械 proxy 与异常脱敏合同保持。环境记录分别证明 Fake 修复旧检索配置的影响、无 judge 单项确实返回 None。受控新测试仅证可用 judge 接线及归一，不代表真实 judge 或真实 pgvector 通过。

## 发现与验证限制

Critical、High、Medium 未发现有实际依据的问题。Low 一项测试证据局限。 `tests/unit/orchestration/test_conversation_context.py:423` 只断言 reply 非空，而 `app/orchestration/assembly.py:65,291` 在没有 Tutor 输出时也会返回固定占位。受控测试的 Confusion 断言独立证明后续观察和协作环仍运行，建议用 Tutor 回复事件或受控正文锁定教学回复。这项局限没有显示生产路径仍有缺陷。

135 项定向通过为实现交接中的受控测试，未在本次复审重跑，不算真实模型、judge、数据库或浏览器验收。Ruff 34 项按交接是目标文件现有对应行的诊断，未在本次独立执行或据此宣称全仓检查通过。默认 pytest 隔离全量、最终 Ruff 对账和真实链结果分别留证。已检查根 README，交付入口和结果按计划由 Task13 收口更新。此次只写复审报告。

## OCR 范围

新执行 `ocr delegate preview --format json --exclude 'docs/delivery/study-workspace-goal/evidence/**,docs/rag-work/evidence/**,.pytest-tmp*/**'`。模式 workspace，Git HEAD 为 `3c9fae413309731b181e72475cf71c980531e7e4`，无 from/to/commit/merge_base。4311 个工作区变更中 96 个 reviewable，4215 个 excluded（指定目录 4028、二进制 53、不支持扩展 126、默认路径 8）。两份目标测试的 `default_path` 排除按授权覆盖纳入。对全部 96 个 reviewable 和两个覆盖目标执行分批 `ocr delegate rule --format json`，98 个路径均匹配。原始预览和规则见 `C:/Users/A1985/task13-teaching-ocr-01a16887/`。

| 文件 | 状态和规则映射 | SHA-256 |
| --- | --- | --- |
| `app/agents/critic.py` | modified，已审全文和 HEAD diff，rule-0/system 1 | `69300F96F40C7A93D3087E186DF29FA5214EF0739EF7AAA753741E684DD65331` |
| `app/harness/teaching_context.py` | modified，已审全文和 HEAD diff，rule-0/system 1 | `A7332C997F3490C0699BD6C9DC38892A4AE8E41C0EFE3F70927D10C9FE632796` |
| `tests/unit/orchestration/test_conversation_context.py` | modified，覆盖默认排除，已审全文和 HEAD diff，rule-80/system 3 | `27C7045A12F37B3C3D9EFBB78A3009288A3FD20D487928138CC16BB3B260F33C` |
| `tests/integration/test_retriever_integration.py` | modified，覆盖默认排除，已审全文和 HEAD diff，rule-80/system 3 | `B6A8937167836DE1C31C50CFD09670658FC63C3C03C9ED94E6D9481AC5028C4B` |

目标 `total_files=4`、`reviewed_files=4`、`skipped_files=0`、`coverage_rate=100%`。扩展清单 `total_files=98`、`reviewed_files=4`、`skipped_files=94`、`coverage_rate=4.08%`。以下每个 `(path, status)` 均因超出四个冻结目标跳过，由其他子项或整分支审查另行覆盖。

| 路径 | OCR 状态 | 审查状态 |
| --- | --- | --- |
| `docs/delivery/study-workspace-goal/status.json` | modified | 跳过 |
| `web/src/api/client.ts` | modified | 跳过 |
| `web/src/api/profiles.ts` | modified | 跳过 |
| `web/src/components/knowledge/ResourceDialog.tsx` | modified | 跳过 |
| `web/src/pages/Profile.tsx` | modified | 跳过 |
| `web/src/store/auth.tsx` | modified | 跳过 |
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
