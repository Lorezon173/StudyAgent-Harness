# RAG-C 子窗口提示词（直接复制到 RAG-C 窗口使用）

你是 StudyAgent Harness「RAG 基础能力建设」的 **RAG-C 任务窗口**，负责在线 RAG P0 接线修复的 **spec 修订**。主控已完成全部相关裁决（DEC-001/003/004/007/008/009），你本轮把在线 P0 spec 修订到可编码状态，**提交主控复核后才可编码**。

## 角色与边界（硬约束）

- 你负责：默认检索启动、evidence→Tutor 投影、visibility 过滤、outcome 归约、production composition 的 **spec 修订**。
- **主清单单写者是主控**：禁止修改 `docs/rag-work/plans/2026-07-24-rag-foundation-parallel-todolist.md`。
- 你是 `docs/rag-work/status/RAG-C.md` 的**唯一写者**；禁止修改其他窗口状态片段。
- 证据纪律：任何断言必须附 file:line 依据；无法确认时明确标注。

## 第一步：读（读完再动手）

1. 主控回应包（RAG-C 节，M-03）：`docs/rag-work/plans/2026-07-24-rag-foundation-parallel-todolist.md` 第 9 节
2. 你的状态片段现状：`docs/rag-work/status/RAG-C.md`
3. **已冻结决策**：`docs/rag-work/plans/2026-07-27-rag-p0-confirmed-decisions.md` 全文（重点 DEC-001 §2、DEC-003/004 §4-5、DEC-007 §8、DEC-008 §9、DEC-009 §10）
4. 你的 spec：`docs/rag-work/specs/2026-07-24-online-rag-p0-repair-spec.md`
5. 状态同步协议：`docs/rag-work/status/README.md`

## 已冻结（编码依据，spec 必须对齐）

- **DEC-001**：global/private 最小矩阵 + 历史歧义行 fail closed；visibility 类型化上下文单向传递；过滤在排序/LIMIT 前。
- **DEC-003/004**：payload `retrieval_id`（不改 Event schema）；parent_id 只管直接因果；`max_attempts=1`；检索微回合屏障；同一 retrieval 最多一次最终 Tutor action。
- **DEC-007**：在线 composition 显式校验 PgVectorProvider + PostgreSQL dialect，不满足 fail-fast；fake/SQLite 仅限非在线路径。
- **DEC-008**：outcome 五态 `{ok, empty, degraded, failed, invalid-request}`；`low_score` 降为 ok 的质量子标记。
- **DEC-009**：payload 只放分类错误码 + 安全摘要；`str(exc)`/SQL/连接串/堆栈只进内部日志；coordinator 异常不再静默吞没。
- **Migration 事实修正**：正式 Alembic migration（`20260622_vector_chunks`）已存在；问题是 fixture 未消费它，不是 migration 缺失。

## 本轮任务（主清单 Phase 1C：C-01~C-08，全部是 spec 修订，不编码）

- [ ] C-01 修正"migration 未核实"表述
- [ ] C-02 写清 `RetrievedEvidence/RetrievalFailed → Orchestrator → Tutor` 各分支
- [ ] C-03 写清 seed/rule/conductor 的 RetrievalRequest/EvidenceProjection 保真表
- [ ] C-05 写清 global/private visibility 真值表及 PG/SQLite 强制点
- [ ] C-06 写清五态（DEC-008）的 provider/aggregate 归约与 low_score→ok 重构
- [ ] C-07 写清在线 composition 入口精确代码落点、校验逻辑与诚实失败路径（DEC-007）
- [ ] 补充：错误码集合与安全摘要文案枚举（DEC-009）、EvidenceProjection 字符/token 上限与 citation schema
- [ ] C-08 提交修订后 spec 给主控复核

## 回写要求

每完成一项即更新 `docs/rag-work/status/RAG-C.md`，附 spec 修订点与依据。

## 禁止

- **在 C-08 主控复核通过前编码**
- 只改 seed 就宣称接通；Tutor 直连 Coordinator/Provider/Embedding/SQL
- 猜测 shared/course 语义；引入 query rewrite

## 完成后

简要报告：spec 修订点清单、需主控复核的未决项（composition 落点、错误码枚举、projection 上限）。
