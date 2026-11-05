# Task13 当前候选整分支审阅覆盖映射

静态审阅映射已核对。基线及实际 merge base 为 `d0584d993b8293a2333acc35f3f5753a08068230`，当前 HEAD 为 `3c9fae413309731b181e72475cf71c980531e7e4`。当前候选包含 HEAD 和本报告记录的未提交增量。真实运行与最终交付另行验收。

## 文件覆盖

不可变范围共 1,492 个路径，136 个候选已审，1,356 个历史证据与过程材料等逐项记录跳过理由。全路径分母下覆盖为 9.12%。该范围及跳过理由保持原记录。 [不可变范围报告](branch-ocr-review.md) · [逐路径清单](branch-ocr-checklist.json)

当前候选对 136 个旧审阅路径、13 个跟踪的产品与测试改动、4 个新增产品与测试文件做并集。13 个跟踪改动中，`tests/integration/test_retriever_integration.py` 是新进入分支审阅范围的路径，其余 12 个已有旧路径记录。因此并集为 141 个路径。

| 映射状态 | 路径数 | 依据 |
| --- | ---: | --- |
| 沿用已提交范围审阅 | 122 | 实算当前 Git 规范化 blob 与旧清单目标 blob 相同，另实算当前工作区字节 SHA-256。 |
| Task13 独立增量已审 | 17 | 每个文件当前字节 SHA-256 与最新独立代码审阅记录精确匹配。 |
| 收口文档待定稿核对 | 2 | `README.md` 和状态账本相对已审提交均发生变化。均记录当前哈希，最终文档校验另行完成。 |

139 个正式映射路径覆盖率为 100%，工作区实际 17 项产品与测试增量无缺失或指纹漂移。沿用各增量报告实际执行的 workspace OCR preview、规则映射和手工补入的默认排除测试。本轮没有需要再次执行 OCR 的未映射产品或测试增量。资产清单、进度账本及新增交付材料属于文档收口。浏览器生成的测试报告、截图和调试材料属于运行产物。 [当前路径与指纹](candidate-review-coverage.json)

| 最新审阅证据 | 当前文件 |
| --- | --- |
| [知识点界面 v2](node-ui-code-review-v2.md) | `web/src/api/profiles.ts`、`web/src/pages/Profile.tsx` 沿用初审冻结值，`web/src/components/profile/ProfileNodeControls.tsx`、`web/src/pages/Profile.test.tsx` 为 v2 冻结值。 |
| [双标签账号隔离](account-isolation-code-review.md) | `web/src/api/client.ts`、`web/src/api/client.test.ts`、`web/src/store/auth.tsx`、`web/src/store/auth.test.tsx`、`web/src/components/knowledge/ResourceDialog.tsx`、`web/src/pages/Knowledge.test.tsx`。 |
| [教学与评价边界](teaching-boundary-code-review.md) | `app/agents/critic.py`、`app/harness/teaching_context.py`、`tests/unit/orchestration/test_conversation_context.py`、`tests/integration/test_retriever_integration.py`。 |
| [Python Ruff 修订](python-lint-code-review.md) | `tests/integration/test_workspace_resume.py`、`tests/integration/workspace_observer.py`，沿用前两轮 Python 审阅并核对本轮变更。 |
| [浏览器选项断言修订](real-browser-option-code-review.md) | `web/e2e/workspace-real.spec.ts`，继承浏览器脚本 v1–v3 的审阅证据。 |

## 原分支发现裁决

- **H1 双标签读写串号及退出清除共享凭据。** 在当前冻结候选的增量代码中已关闭，并通过前端受控回归。不可变 HEAD 仍保留原发现。真实双标签首轮停在 `block-a`，后续 A 备份退出、B 实际读写验证须以新的正式运行证据确认。 [账号隔离复审](account-isolation-code-review.md) · [首轮真实运行](real-browser-first-run-summary.md)
- **M1 模型返回数组或对象等级会中止续答，M2 重复题干引用较早消息。** 当前冻结候选通过独立增量复审。受控模型回归验证新增边界。真实模型续答、评分与持久化归正式验收。 [教学边界复审](teaching-boundary-code-review.md) · [后端回归](final-backend-regression.md)
- **L1 超过 4000 字的发送反馈。** 计划明确留待另行处理，当前候选仍保留该已知限制。 [计划审查](teaching-and-evaluator-boundary-plan-review.md)
- **README 知识库鉴权说明。** 当前文件第 467 行仍称 knowledge 不需鉴权，与当前 API 及 Task4 段矛盾。列入收口文档待更正项。当前哈希仅证明文件版本，不表示文档问题已关闭。

## 独立证据边界

私有双标签探针位于 ignored 目录，单独审核。当前探针的哈希与私有探针 v2 报告冻结值不同，本报告不继承 v2 的 PASS 到新哈希。诊断计划已审，当前私有脚本须单独完成代码审阅及真实验收。 [诊断计划审阅](two-tab-probe-diagnostics-plan-review.md)

已有记录确认默认 pytest 1,362 项通过，指定 SQLite 与 PostgreSQL 参数化回归合计 67 项通过，前端 452 项通过且构建通过。全量 Ruff 仍为 exit 1，599 条诊断。首次浏览器 25 项通过、真实 Task13 组失败，随后选项断言已通过代码复审。第二轮真实浏览器教学、模型见证、应用重启、PostgreSQL 重启、真实账号隔离矩阵和双标签探针结果以本次覆盖映射之后的正式证据为准。 [后端回归](final-backend-regression.md) · [前端回归](account-final-web-regression.md) · [首轮真实运行](real-browser-first-run-summary.md)
