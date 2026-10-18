# RAG 推进规划子代理审阅

日期：2026-10-13。审阅对象：`2026-10-13-progress-and-todolist.md`。方式：子代理只读对照交接、主清单、DEC、spec、状态与必要代码，主会话核实关键依据。未运行测试，未修改生产代码或原规划。

## 结论

阶段状态与交接基本一致，整体推进顺序可以保留。本文适合作为总规划；各执行包补齐下述契约与验收项并经用户确认后，才能作为直接编码依据。

## 执行前需要补齐

1. **P2：多 k 指标明确列为实施任务。** 规划 D-10 仍使用“核对 evaluator 是否支持”的表述，但 `app/agents/retriever.py` 当前只接受单个 top_k、返回单个 recall_at_k；`rag_d.py` 每题调用一次 evaluator，不能从现有聚合指标还原 Recall@1/3/5。应在 D-08 前确认向后兼容的多 k 输出设计，用同一次 top-5 检索按排名前缀派生指标，保留旧指标和 proxy 口径，不另开检索或旁路 evaluator。

2. **P2：权限对抗数据与正式基线索引分开。** F-05 将创建两用户、公共/私有及歧义行测试样本，Phase 5 又要求本书产物隔离。现有 gate 只机械核对 isolation.mode/verified，不能自动证明实际库内无污染。建议独立权限测试库和纯本书基线库，保存目标标识、产物数量与隔离证明；不能在混入样本后仅声明 verified=true。

3. **P2：完整定义版本化 attestation 与 runner 执行包。** DEC-002 §3.4 与 `rag_d.py` required fields 要求 ingestion_run_id、source_sha256、source_format、doc_id、normalizer_version、chunking_version、planned_chunk_count、written_chunk_count、backend、dialect、scope、owner；冻结决策还要求版本化 JSON、安全错误码和摘要。规划需要明确版本字段、run ID 生成、字段类型/来源/必填条件、产品 runner 文件与输出位置、失败记录与成功证明区别。仅在成功且真实写入核验通过时产出成功证明。

4. **补齐冻结原子性要求的真实验收。** DEC-002 §3.3 要求单次 run 全有或全无，写入失败整体 rollback。虽然 provider 已有 commit/rollback 代码，规划应明确真实 PG 中途失败后无本轮残留行的对抗验收，安排在正式摄入前的独立测试资源中执行。另需检查 embedding 数量与 docs 数量不一致的情况：provider.index 当前 zip 两组输入后返回 len(docs)，不足以单独证明实际写入数；该路径列入核验与必要修复规划，不在本次直接修改代码。

## 其他改进

- 将 P2-03 的既有审计要求与可选错误分类扩展分开。在线 spec 已要求歧义行内部审计和异常关联检索日志，先核查当前满足情况；新增枚举或统一重构才需要新增设计决策。
- 原规划的总览和阶段拆分可以保留；runner 落点、具体字段和投影/citation 等细节需在对应执行包中确认，不应将总规划的通过理解为全部实施细节已获批准。

## 保留的判断

- 没有把真实 PG、在线 grounded answer 或正式 baseline 错写为已完成。
- EvidenceProjection 候选上限明确标为待确认，没有擅自冻结。
- Phase 3 和 Phase 5 可独立推进，Phase 5 等待真实摄入与准入条件，依赖顺序成立。
- 历史测试记录与本次验证结果区分明确。

建议下一步先修订总规划的上述任务，并为 I-01/F-01～F-06 与多 k 指标分别形成完整执行包；不直接开始编码。
