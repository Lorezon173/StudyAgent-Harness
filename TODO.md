# 项目总揽 Todolist

> **本文件定位**：项目级任务索引，持续维护。
> - 已有专门 todolist 的主题 → 以**引用**形式列于此（不复制内容，避免双份维护）
> - 未单独建 todolist 的工作 → 直接列于此处的清单 + 说明
> - 新增条目规则：新增工作项时，先查是否已有专门 spec/todolist；无则在本文新增并补「说明」段。
>
> **状态图例**：✅ 已完成 | 🚧 进行中 | ⏳ 未启动 | 💬 待讨论
>
> 创建：2026-07-08 ｜ 最近更新：2026-07-08

---

## 总揽清单

### 🔴 P0 — RAG 接线断点修复（本次梳理，⏳ 待启动）
- [ ] **P0-①** 检索结果接入 Tutor prompt + 新栈默认触发检索
- [ ] **P0-②** 修 `retriever_expand_query` 闭环（Orchestrator payload 带 query）
- [ ] **P0-③** `PgVectorProvider.search` 加 `scope/user_id` 过滤

### 🟡 P1 — RAG 小增强（本次建议，⏳ 待启动）
- [ ] **P1-①** 低分门禁（`retrieval_status` 接入 Tutor 决策）
- [ ] **P1-②** 教学阶段感知的 query 构造

### 💬 待讨论 — 设计路线分叉（⏳ 需先决策再排期）
- [ ] **T-①** 重排路线 vs 重检索路线（design doc 哲学确认）

### ⏳ P2/P3 — RAG 召回大增强
- [ ] **P2 / B-1** LightRAG 双层检索（local/global/hybrid）—— 详见专门 todolist
- [ ] **P3** BM25 混合检索（条件性，待单用户数据量评估）

### ⏳ 其他主题（引用专门 todolist / spec，不在本文展开）
- [ ] **B-2** 掌握度时序化 + 复习触发 —— 详见 RAG 升级 todolist
- [ ] **B-3** PDF 版面解析 —— 详见 RAG 升级 todolist
- [ ] **MIG** `app_old/` → `app/` 迁移残余 —— 详见迁移计划

---

## 工作说明 + spec 位置

> 每项给：问题/做法要点 + 对应 spec 文档位置。实现细节查 spec，不在此重复。

### P0-① 检索结果接入 Tutor prompt + 新栈默认触发检索

- **问题**：新栈 `TutorAgent` 不订阅 `RETRIEVED_EVIDENCE`，调 LLM 只用 `current_topic`；且种子事件只发 `TUTOR_ASK`、不含 `retriever_search`——检索在默认流程里缺席，结果即便产出也没人消费。
- **做法要点**：三选一或组合——(a) Tutor 增订 `RETRIEVED_EVIDENCE` 取 chunks 拼进 system_prompt；(b) Orchestrator 在教学 action 前先发 `retriever_search` 并把证据塞进 `ACTION_REQUESTED` payload；(c) 协作环把证据写进 `ws.evidence_pool` 供 Tutor 读。
- **spec/参考**：
  - `docs/designs/2026-07-07-rag-three-stage-enhancement-review.md` §3（P0-① 证据 + 修复方向）
  - `docs/superpowers/specs/2026-05-29-multi-agent-redesign-design.md` §3.6（设计源头的证据放行流程）

### P0-② 修 `retriever_expand_query` 闭环

- **问题**：design doc §3.6 设计了「Critic 评 RAG 质量低 → `RETRIEVER_EXPAND_QUERY` → 重检索」的闭环，但实现里 Orchestrator 发 `ACTION_REQUESTED` 时 payload 只含 `action`+`target`、**不带 query** → RetrieverAgent 取到空 query → `PgVectorProvider.search` 返回空。设计完整、实现断路。
- **做法要点**：Orchestrator 发 `retriever_*` action 时填 `query` 字段（从 `ws.current_topic` 或上轮用户回答提取）；RetrieverAgent 按 action 区分处理（search vs expand_query）。
- **spec/参考**：
  - `docs/designs/2026-07-07-rag-three-stage-enhancement-review.md` §2.1 / §3（P0-② 证据）
  - `docs/superpowers/specs/2026-05-29-multi-agent-redesign-design.md` §3.6（闭环设计原文）

### P0-③ `PgVectorProvider.search` 加 `scope/user_id` 过滤

- **问题**：`index` 写入了 `user_id`/`scope` 字段，`search` 的 SQL 却无 `WHERE`——全局检索所有用户 chunk，是召回精度缺口 + 越权风险。
- **做法要点**：`search` 签名加 `user_id`/`scope` 参数，SQL 加 `WHERE user_id = :uid AND scope IN (:scopes)`；上层 `RAGCoordinator.search` / `RetrieverAgent` 透传会话的 `ws.user_id`。
- **spec/参考**：
  - `docs/designs/2026-07-07-rag-three-stage-enhancement-review.md` §2.2 / §3（P0-③ 证据）

### P1-① 低分门禁

- **问题**：`retrieval_status` 当前是死字段——打了 `low_score` 标签但下游不消费，低质证据照常进 Tutor。教学容错低（教错比没教糟）。
- **做法要点**：`low_score` 时不把 chunks 送进 Tutor，改为触发 Tutor 坦白无把握 / 降级 Conductor / 跳过主题（fallback 形态待定，见待讨论项）。
- **spec/参考**：`docs/designs/2026-07-07-rag-three-stage-enhancement-review.md` §4.4（重排建议）

### P1-② 教学阶段感知的 query 构造

- **问题**：当前 query 裸透传，不区分教学阶段。
- **做法要点**：不同 action 配不同 query 模板——`regress_to_prereq` → 检索前置概念；`tutor_correct` → 检索易混淆点；`tutor_explain` → 当前主题。是 P0-② 的自然延伸（修闭环时顺手做）。
- **spec/参考**：`docs/designs/2026-07-07-rag-three-stage-enhancement-review.md` §4.2（Query 优化建议）

### T-① 重排路线 vs 重检索路线（待讨论）

- **问题**：design doc §3.6 用「重检索（expand_query）」替代了标准 RAG 的「重排（reranker）」——这是项目的设计选择，源于职能正交哲学（重排需语义判断，归 Critic；Critic 不重排 chunks，只决定「够不够/要不要重来」）。现若要引入 cross-encoder 重排，等于推翻这一设计选择。
- **需决策**：(A) 坚持「重检索」路线 → 只修 P0-② 兑现闭环即可；(B) 引入「重排」路线 → 需动 design doc 哲学，是设计分叉而非补实现。
- **判据**：教学场景下「素材给 LLM 容忍噪声」+「Critic 已做语义评估」→ 倾向 (A)；除非实测发现 top-5 常夹不相关 chunk。
- **spec/参考**：
  - `docs/designs/2026-07-07-rag-three-stage-enhancement-review.md` §4.4 + §六（design doc 设计源头视角）
  - `docs/superpowers/specs/2026-05-29-multi-agent-redesign-design.md` §3.6（重检索设计原文）

### P2 / B-1 LightRAG 双层检索

- **目标**：把知识内容建成「实体关系图 + 向量」双层，支持 local（实体邻居）+ global（全局关系）+ hybrid 融合检索，解决教学场景「概念脉络串联」核心痛点。
- **状态**：⏳ 0%，待启动。已有完整 spec。
- **spec/参考**：
  - `docs/designs/2026-07-03-phase-b1-lightrag-dual-retrieval-spec.md`（详细设计）
  - `docs/designs/2026-07-03-rag-upgrade-todolist.md`（在专门 todolist 里跟踪进度）

### P3 BM25 混合检索（条件性）

- **问题**：教学材料有大量术语/公式/定义，BM25 对精确术语匹配强于向量；但当前是纯向量单路。
- **前置条件**：先评估单用户平均文档量——量小则纯向量够用，量大才值得引入 BM25。
- **注**：B-1 spec 的 hybrid 是 local+global+vector 三路融合，**不含 BM25**；若要做 BM25 是 B-1 之外的新决策。
- **spec/参考**：`docs/designs/2026-07-07-rag-three-stage-enhancement-review.md` §4.3

### B-2 掌握度时序化 + 复习触发（引用）

- **目标**：MasteryGraph 加时序衰减 + 复习触发（MasteryDecayService / ReviewTriggerService）。
- **spec/参考**：
  - `docs/designs/2026-07-03-phase-b2-mastery-temporal-review-spec.md`
  - `docs/designs/2026-07-03-rag-upgrade-todolist.md`（进度跟踪）

### B-3 PDF 版面解析（引用）

- **目标**：版面感知的 PDF 提取 + 通用分块器（LayoutPDFExtractor / ChunkingService），补齐当前「无通用分块」缺口。
- **状态**：⏳ 优先级最低，技术选型待 spike。
- **spec/参考**：
  - `docs/designs/2026-07-03-phase-b3-pdf-layout-parsing-spec.md`
  - `docs/designs/2026-07-03-rag-upgrade-todolist.md`

### MIG `app_old/` → `app/` 迁移残余（引用）

- **spec/参考**：`docs/app_old_migration_plan.md`

---

## 维护记录

| 日期 | 变更 |
|---|---|
| 2026-07-08 | 初建。纳入本次会话梳理的 RAG 三段式（Query/召回/重排）相关工作：P0-①②③ 接线断点、P1-①② 小增强、T-① 路线分叉、P2/P3 召回增强；引用既有 B-1/B-2/B-3 与 app_old 迁移。 |
