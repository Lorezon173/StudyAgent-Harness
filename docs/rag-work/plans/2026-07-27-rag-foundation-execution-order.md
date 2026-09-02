# RAG Foundation 下一阶段任务执行顺序

> 日期：2026-07-27  
> 状态：执行顺序文档；用于安排下一阶段工作批次、并行关系、等待条件与复核触发。  
> 事实与 blocker 总账本见：[RAG Foundation 主清单](2026-07-24-rag-foundation-parallel-todolist.md)。

---

## 1. 执行总原则

下一阶段按以下顺序推进：

```text
先冻结 P0 边界
→ 再补共享契约与只读工具
→ 再实现产品链核心能力
→ 再跑正式摄入
→ 再跑黄金集 baseline
→ 最后验证在线 grounded answer
```

四条硬约束：

1. **先边界，后实现**：未冻结的共享契约不得由任务窗口自行假定。
2. **先真实性，后体验**：先防止 fake/fallback/混源/越权访问被误报为真实能力。
3. **先产品主链，后 benchmark 分数**：benchmark 不得补造摄入、切块、索引或检索。
4. **先离线正式索引，后在线 grounded answer**：Tutor 证据消费必须在正式产品索引存在后验证。

---

## 2. 分阶段执行顺序

## Phase 0：已确认 P0 决策落盘与窗口回执（当前阶段）

### 目标
把已确认裁决固化为唯一事实源，并要求各窗口按裁决回写自己的状态片段。

### 任务
- [ ] 主控向 RAG-A/B/C/D 发回应包
- [ ] RAG-A 回写 extractor-only 边界
- [ ] RAG-B 回写 stable-ID/provenance 待补证边界
- [ ] RAG-C 回写 retrieval_id、max_attempts=1 与 migration 事实修正
- [ ] RAG-D 回写 gold-answer/context enrichment 与 admission gate 边界
- [ ] 主控复核四份回执，只在主清单合流共享冲突

### 并行关系
- 四个窗口可并行回写各自状态片段。
- 主控必须等四份回执后再推进下一次共享裁决。

---

## Phase 1：只读准备与协议补证（可并行）

### 1A — RAG-A：EPUB extractor-only

**目标**：让 `.epub` 正式进入 Extractor 主链，但不宣称摄入完成。

- [ ] 新建 `EpubExtractor`
- [ ] 注册 `.epub/.EPUB`
- [ ] 补 happy-path 与 degraded-path 单测
- [ ] 同步 README 的 extractor 描述
- [ ] 去重 asset inventory 中重复 `EpubExtractor` 条目

**输出物**：
- 代码与单测证据
- README 同步
- `RAG-A.md` 回写

### 1B — RAG-B：stable-ID 与 provenance 补证

**目标**：在不编码正式 production ID 的前提下，补齐可复算协议证据。

- [ ] 提交 canonical doc bytes 规范
- [ ] 提交 canonical chunk bytes / range 规范
- [ ] 给出 Unicode/CRLF/空白/range 测试向量
- [ ] 收紧 Gate 0 文案：唯一入口只限新文档摄入
- [ ] 设计 provider provenance round-trip 测试壳

**输出物**：
- bytes 协议补证稿
- 测试向量
- RAG-B spec 修订稿

### 1C — RAG-C：在线 P0 spec 修订

**目标**：在编码前把在线主链契约写到足以实施。

- [ ] 修正 migration 事实：正式 Alembic 已存在
- [ ] 写清 `retrieval_id` 与 `parent_id` 分工
- [ ] 写清 seed/rule/conductor payload 保真表
- [ ] 写清 evidence/failure → Tutor 的微回合屏障
- [ ] 写清 visibility 最小矩阵和 PG/SQLite 强制点
- [ ] 写清 outcome 状态与安全摘要边界
- [ ] 写清 production pgvector composition 约束

**输出物**：
- RAG-C spec 修订稿
- `RAG-C.md` 回写

### 1D — RAG-D：只读 validator / adapter / gate / report

**目标**：在上游未完成前，先完成诚实的评测准备层。

- [ ] 题集/corpus/manifest/SHA validator
- [ ] `paragraph_id -> full paragraph text -> golden_chunks` adapter
- [ ] admission gate
- [ ] report envelope
- [ ] 单次 evaluate 路径约束

**输出物**：
- 只读工具代码与测试
- `RAG-D.md` 回写

### 并行关系

```text
A / B / C / D 可以并行推进
但：
- B 的正式 ID 编码必须等待主控冻结
- C 的正式编码必须等待 spec 复核
- D 不得在上游未解锁前跑 baseline
```

---

## Phase 2：共享基础能力实现（前置条件严格）

### 前置条件
必须同时满足：

- [ ] RAG-B bytes 协议与 range 规则通过主控复核
- [ ] RAG-C 在线 P0 spec 通过主控复核
- [ ] RAG-A extractor-only 已落地（至少 EPUB happy-path 可提取）

### 任务
- [ ] 实现 `ChunkingService`
- [ ] 实现 `KnowledgeIngestionService`
- [ ] 实现写前校验：`doc_id/chunk_id`、scope/owner、metadata 可序列化
- [ ] 修复 PgVector provenance round-trip
- [ ] 在 PG/SQLite 查询前执行 visibility 过滤
- [ ] 实现 `empty/degraded/failed/invalid-request`
- [ ] production online 显式要求 pgvector，禁止静默 fake fallback
- [ ] 测试/fixture 改为消费正式 migration/schema 契约

### 不允许混入
- 上传 API
- 幂等/replace/delete
- 图检索
- shared/course 完整模型
- query expansion

---

## Phase 3：在线 evidence 接线

### 前置条件
- [ ] Phase 2 完成
- [ ] retrieval payload 保真可测试
- [ ] visibility 与 outcome 在 Provider/Coordinator 层已生效

### 任务
- [ ] 默认 seeds 改为 Retriever 先行
- [ ] evidence/failure 进入 Orchestrator 微回合屏障
- [ ] 生成唯一 Tutor action
- [ ] Tutor 从 projection 中消费证据
- [ ] empty/failed/quality unavailable 统一走受控降级
- [ ] sentinel 证明 evidence 真进入 Tutor prompt
- [ ] 连续请求不串轮

### 完成定义
- 在线链能产生一次、唯一、受控的 grounded Tutor 回复
- 但此时仍未跑正式书籍 baseline

---

## Phase 4：首本书正式摄入与 attestation

### 前置条件
- [ ] A extractor-only 完成
- [ ] B/C 共享实现完成
- [ ] 正式 migration 路径通过

### 任务
- [ ] 在干净 PostgreSQL DB 上执行正式 Alembic migration
- [ ] 真实 EPUB 经产品链导入
- [ ] 产出 JSON attestation
- [ ] planned/written/DB 行数核对
- [ ] doc/chunk provenance 可回查
- [ ] visibility 过滤在正式环境验证通过

### 完成定义
- 这是第一个可以交给 RAG-D admission gate 消费的正式产品索引证明

---

## Phase 5：Retriever baseline

### 前置条件
- [ ] Phase 4 完成
- [ ] D 的 validator/adapter/gate/report 完成
- [ ] provider 集、DB dialect、corpus isolation 条件满足

### 任务
- [ ] 运行 20 题 baseline
- [ ] 每题只调用一次 evaluate
- [ ] 保存 raw metrics / sources_used / degraded 状态
- [ ] 若 RAGAS 可用，仅作为 enrichment
- [ ] 产出失败分类与人工复核结论

### 完成定义
- 可以诚实地产出“该书 Retriever baseline”
- 仍不能直接推出 Tutor 在线质量

---

## Phase 6：在线 grounded answer 端到端验证

### 前置条件
- [ ] Phase 3 完成
- [ ] Phase 4 完成
- [ ] Phase 5 至少获得正式 baseline 与失败分类

### 任务
- [ ] 用黄金题驱动真实 `/api/chat`
- [ ] 用黄金题驱动真实 `/api/chat/stream`
- [ ] 验证 Tutor prompt 的证据来自当前 retrieval_id
- [ ] 区分召回失败 / projection 失败 / 生成失败
- [ ] 验证无权限内容不进 Tutor prompt
- [ ] 在真实结果基础上再讨论在线质量阈值

### 完成定义
- 这是第一次可以讨论“在线 grounded answer 是否通过”的阶段

---

## 3. 阶段间依赖图

```text
Phase 0
  ↓
Phase 1A / 1B / 1C / 1D   (可并行)
  ↓
Phase 2                   (依赖 1A + 1B + 1C)
  ↓
Phase 3                   (依赖 2)
  ↓
Phase 4                   (依赖 2 + A 已实现)
  ↓
Phase 5                   (依赖 4 + 1D)
  ↓
Phase 6                   (依赖 3 + 4 + 5)
```

---

## 4. 当前允许并行 / 必须等待 / 禁止越权

### 当前允许并行

- RAG-A：实现 extractor-only
- RAG-B：补 bytes 协议与测试向量
- RAG-C：修订在线 P0 spec
- RAG-D：实现 validator / adapter / gate / report

### 必须等待

- B 正式 stable-ID 编码：等待主控冻结 bytes/range
- C 正式在线编码：等待修订后 spec 通过主控复核
- D 正式 baseline 运行：等待正式 ingestion attestation 与真实 PG admission
- 在线 Tutor 质量结论：等待 Phase 6

### 禁止越权

- A 不切块、不写库、不生成 attestation
- B 不自行冻结 paragraph_id/runtime ID，不建旁路 evaluator
- C 不让 Tutor 直连 Provider，不自行引入 query rewrite
- D 不自建 extractor/chunker/index/search，不把 RAGAS 写成 Tutor 质量

---

## 5. 每阶段完成时必须留下的产物

| 阶段 | 必留产物 |
|---|---|
| Phase 0 | 各窗口状态片段回执 |
| Phase 1A | EPUB 代码/测试/README 证据 |
| Phase 1B | bytes 协议稿 + 测试向量 |
| Phase 1C | 修订后的在线 P0 spec |
| Phase 1D | validator/adapter/gate/report 代码与测试 |
| Phase 2 | chunking/ingestion/provenance/visibility/outcome 实现与测试 |
| Phase 3 | 在线 evidence 消费 sentinel 证据 |
| Phase 4 | JSON attestation + DB 核验记录 |
| Phase 5 | baseline report + 失败分类 |
| Phase 6 | 在线 E2E 证据与 grounded answer 复核 |

---

## 6. 主控下一次复核触发条件

满足任一条件立即复核：

1. RAG-A 提交 extractor-only 实现证据；
2. RAG-B 提交 canonical bytes/range 与测试向量；
3. RAG-C 提交修订后 spec；
4. RAG-D 提交 validator/adapter/gate/report；
5. 有新的共享裁决请求；
6. 首次正式 ingestion run 完成；
7. baseline 首次实际跑出结果；
8. 在线 E2E 首次有 sentinel 证据可核验。
