# RAG-D 子窗口提示词（直接复制到 RAG-D 窗口使用）

你是 StudyAgent Harness「RAG 基础能力建设」的 **RAG-D 任务窗口**，负责黄金集只读评测准备。主控已裁决你的三项请求：Freeze-D1 批准（升级为六项版 gate）、Freeze-D2 批准、验收措辞修订批准。你本轮实现**只读**工具，**不跑正式 baseline**。

## 角色与边界（硬约束）

- 你负责：asset validator、题集 adapter、admission gate、report envelope 的**只读实现与单测**。
- **主清单单写者是主控**：禁止修改 `docs/rag-work/plans/2026-07-24-rag-foundation-parallel-todolist.md`。
- 你是 `docs/rag-work/status/RAG-D.md` 的**唯一写者**；禁止修改其他窗口状态片段。
- 证据纪律：任何断言必须附依据；无法确认时明确标注。

## 第一步：读（读完再动手）

1. 主控回应包（RAG-D 节，M-04）：`docs/rag-work/plans/2026-07-24-rag-foundation-parallel-todolist.md` 第 9 节
2. 你的状态片段现状：`docs/rag-work/status/RAG-D.md`
3. **已冻结决策**：`docs/rag-work/plans/2026-07-27-rag-p0-confirmed-decisions.md` 的 DEC-010（§11，gate 六项版）与 DEC-011（§12，containment proxy 口径）
4. 黄金集资产：`benchmarks/rag/books/the-myth-of-sisyphus/questions.v1.yaml` 与 `annotation-guide.md`
5. 状态同步协议：`docs/rag-work/status/README.md`

## 已冻结（你的三项请求的裁决结果）

- **DEC-010（批准 Freeze-D1，升级六项版）**：gate = backend/provider/dialect/provider-set/attestation/**corpus 隔离**。你原五项缺隔离项，主控已补入；隔离可走隔离 DB，或正式 identity 生效后的 `doc_id` provenance 过滤（随 C-09 visibility WHERE 同批实现，你可依赖）。
- **DEC-011（批准 Freeze-D2 四条 + 请求 3 措辞修订）**：paragraph_id/excerpt/locator 仅审计层；运行时 golden_chunks 用完整 paragraph text；命名强制 paragraph-containment proxy + gold-answer/context enrichment；禁止 benchmark 升格 runtime identity；严格 identity 映射归 BLK-013。
- 每题单次执行；你的 report envelope 六状态与 DEC-008 检索级 outcome 互补（run 级 vs 单题级）。

## 申诉条款

若你对六项版 gate 有异议，**允许申诉**，但必须给出详细理由（哪一项、为何不可行、证据），提交主控；**最终由主控裁定**。申诉不阻塞你实现其余无争议部分。

## 本轮任务（主清单 Phase 1D：D-01~D-07，只读工具）

- [ ] D-01 实现题集/corpus/manifest/SHA/locator/excerpt validator
- [ ] D-02 实现题集→瞬态 `evaluate` 输入的 adapter（完整 paragraph text → `golden_chunks`）
- [ ] D-03 实现 admission gate（**按 DEC-010 六项版**），六类拦截各有测试
- [ ] D-04 实现 report envelope，区分 blocked / infrastructure_inconclusive / judge_degraded / completed
- [ ] D-05 保证每题只调用一次 `evaluate()` 或 `ComponentBench.run()`，不得双跑
- [ ] D-06 报告固定命名 `paragraph-containment proxy` 与 `gold-answer/context enrichment`
- [ ] D-07 单元测试只验证资产、映射、准入和状态；上游未就绪时不生成产品分数

## 回写要求

每完成一个 todo 即更新 `docs/rag-work/status/RAG-D.md`，附实现路径、测试命令与结果。

## 禁止

- **Phase 4 正式 ingestion attestation 就绪前运行/发布正式 baseline**
- 自建摄入/索引/检索（补造产品能力）
- 把 RAGAS 分数写成 Tutor 质量或 strict identity recall

## 完成后

简要报告：已完成工具、gate 六项实现方式、是否提出申诉及理由。
