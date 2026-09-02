# RAG-D 第二轮提示词（直接复制到 RAG-D 窗口）

你是 StudyAgent Harness「RAG 基础能力建设」的 **RAG-D 任务窗口**。主控已确认：DEC-010/011 已冻结，**你进入 Phase 1D 只读工具实现**。

## 已冻结（你的实现依据）

- **DEC-010**：准入 gate 六项版 = backend/provider/dialect/provider-set/attestation/**corpus 隔离**。你原五项缺隔离项，主控已补入；隔离可走隔离 DB，或正式 identity 生效后的 `doc_id` provenance 过滤（随 C-09 visibility WHERE 同批实现，你可依赖）。
- **DEC-011**：paragraph-containment proxy + gold-answer/context enrichment 口径；paragraph_id/excerpt/locator 仅审计层；运行时 golden_chunks 用完整 paragraph text；禁止 benchmark 升格 runtime identity；严格 identity 映射归 BLK-013。
- 每题单次执行；report envelope 六状态与 DEC-008 检索级 outcome 互补（run 级 vs 单题级）。

## 配套裁决（影响你）

- **stable-ID 评测收敛**（DEC-012 §13.4）：扩展（`golden_chunk_ids`/`golden_source_locators` + 命中优先级 + `evaluation_alignment`）作为 `RetrieverAgent.evaluate` 向后兼容扩展实现，**归你设计**（BLK-013 前）；禁止旁路评测。当前 Phase 1D 仍按 DEC-011 用 containment proxy。

## 申诉条款

若你对六项版 gate 有异议，允许申诉，但必须给出详细理由（哪一项、为何不可行、证据），提交主控；最终由主控裁定。申诉不阻塞你实现其余无争议部分。

## 本轮任务（Phase 1D：D-01~D-07，只读工具）

- [ ] **D-01** 实现题集/corpus/manifest/SHA/locator/excerpt validator
- [ ] **D-02** 实现题集->瞬态 `evaluate` 输入的 adapter（完整 paragraph text -> `golden_chunks`）
- [ ] **D-03** 实现 admission gate（按 DEC-010 六项版），六类拦截各有测试（fake/SQLite/多源/无 attestation/混源/dialect 不符）
- [ ] **D-04** 实现 report envelope，区分 blocked / infrastructure_inconclusive / judge_degraded / completed
- [ ] **D-05** 保证每题只调用一次 `evaluate()` 或 `ComponentBench.run()`，不得双跑
- [ ] **D-06** 报告固定命名 `paragraph-containment proxy` 与 `gold-answer/context enrichment`
- [ ] **D-07** 单元测试只验证资产、映射、准入和状态；上游未就绪时不生成产品分数
- [ ] 可选预备：设计 `RetrieverAgent.evaluate` 的 stable-ID 扩展（`golden_chunk_ids` 等），提交主控复核（BLK-013 前的设计稿）

## 回写要求

每完成一个 todo 即更新 `docs/rag-work/status/RAG-D.md`，附实现路径、测试命令与运行结果。

## 禁止

- **Phase 4 正式 ingestion attestation 就绪前运行/发布正式 baseline**
- 自建摄入/索引/检索（补造产品能力）
- 把 RAGAS 分数写成 Tutor 质量或 strict identity recall

## 完成后

简要报告：已完成工具、gate 六项实现方式、是否提出申诉及理由、stable-ID 扩展设计稿（若有）。
