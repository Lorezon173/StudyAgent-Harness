# B-① 知识内容图谱：Spec 修订与交接 skill 收尾

## 1. 一句话接手说明

当前要继续两条相互关联但可分开收尾的工作：**按已确认的 Scope A 修订 B-① 知识内容图谱 spec**，以及**完成全局 handoff-document skill 的独立验证**；前者已完成事实核实和修订设计，尚未改写 spec，后者已迁入自进化项目并已成为软链接管理的全局 skill，但尚未完成独立验证任务。

## 2. 当前状态

- 已完成：
  - B-① 的现状核实、问题归类、修订设计收束。
  - 用户确认 Scope A：B-① spec 必须纳入 RAG 主链前置缺口，不只处理图谱内部。
  - 知识图谱工作交接文档已创建。
  - 全局 `handoff-document` skill 已设计、编写，并已迁入自进化项目的 skill 管理体系。
- 进行中：无。
- 未开始但已确认要做：
  - 修订 B-① spec。
  - 修订后开展隔离式 spec review。
  - 验证 `handoff-document` skill 的实际行为。
- 当前卡点 / 待确认项：
  - B-① 没有技术阻塞；下一步应直接启动 spec 修订，但保持“spec 先于实现”的 gate。
  - handoff skill 尚未以独立案例验证其命名、引用索引化与可立即接手能力。

## 3. 接手后第一动作

1. 先打开 B-① spec 索引，核对其仍处于未修改状态：
   - 用途：确认即将编辑的目标及当前基线。
   - 索引：`docs/designs/2026-07-03-phase-b1-lightrag-dual-retrieval-spec.md`
2. 打开 RAG 主链盘点索引，作为 Scope A 纳入边界的事实依据：
   - 用途：确认主链前置缺口与 B-① 的衔接边界。
   - 索引：`docs/designs/2026-07-07-rag-three-stage-enhancement-review.md`
3. 调用 `spec-plan-writer` 后，开始修订 B-① spec；完成后调用 `reviewing-plans-isolated` 做独立复核。
4. B-① spec 完成前，不进入实现计划或代码实现。

## 4. 关键决策与边界

### 已确认决策

- B-① 采用 **Scope A**：将 RAG 主链的启用前置条件纳入 B-① spec。
- B-① 仍不涵盖掌握度时序化、PDF 版面解析、Neo4j、以及未确认收益的检索增强能力。
- 内容图谱与 MasteryGraph 在业务职责上保持独立。
- 交接文档必须优先帮助新窗口接手，不是对话或源文档的重复摘要。
- `handoff-document` skill 的命名骨架为：
  - 目录：`(timestamp)-handoff/`
  - 文档：`(timestamp)-<具体工作内容>.md`
  - `<具体工作内容>` 必须随实际任务动态命名，不能使用泛化词。

### 明确不要做的事

- 不要把 B-① 的“图谱内部设计”与“主链前置条件”混成不分层的实现承诺。
- 不要在 spec 未修订、未复核前直接写 B-① 代码。
- 不要让 graph provider 隐式拥有 vector 写入或跨 provider 融合所有权。
- 不要把引用的 spec、review、README 或代码正文复制进新的交接文档；只保留用途与索引位置。

### 仍未定论、不能当作事实的点

- LightRAG 的具体 API、常量命名、数据模型映射必须通过版本锁定的 spike 后才能在 B-① spec 中作能力性断言。
- 图关系候选排序、跨 provider 分数校准、融合权重、来源字段映射需要 spike 后冻结。
- fresh SQLite Alembic 升级链存在既有基线问题；不能把该路径描述成 B-① 已具备的验收能力。

## 5. 必看材料索引

### B-① 任务主材料

- 用途：编辑 B-① 的目标 spec。
  - 索引：`docs/designs/2026-07-03-phase-b1-lightrag-dual-retrieval-spec.md`
- 用途：确认 B 阶段任务范围和阶段关系。
  - 索引：`docs/designs/2026-07-03-rag-upgrade-todolist.md`
- 用途：确认 RAG 主链断点、检索链路和 Scope A 的前置条件。
  - 索引：`docs/designs/2026-07-07-rag-three-stage-enhancement-review.md`
- 用途：回看本任务此前的交接状态。
  - 索引：`docs/claude-chat/2026-07-14-1503-handoff/2026-07-14-1503-B-①-知识内容图谱.md`

### B-① 实现事实依据

- 用途：确认多 provider 聚合、默认 source 行为、`IndexProvider` 现有签名和摄入入口。
  - 索引：`app/infrastructure/rag/coordinator.py`
- 用途：确认向量写入/检索、`user_id`/`scope` 现状与 score 行为。
  - 索引：`app/infrastructure/rag/pgvector_provider.py`
- 用途：确认 embedding 维度及调用契约。
  - 索引：`app/infrastructure/rag/embedding.py`
- 用途：确认检索事件 payload、sources 透传和状态输出。
  - 索引：`app/agents/retriever.py`
- 用途：确认 LLM JSON 解析与 token 相关实际行为。
  - 索引：`app/infrastructure/llm.py`
- 用途：确认现有表、用户隔离先例及向量表字段。
  - 索引：`app/models/tables.py`
- 用途：确认现有迁移与方言分支基线。
  - 索引：`alembic/versions/20260622_add_vector_chunks_table.py`
  - 索引：`alembic/versions/m3_unify_user_id_type.py`
  - 索引：`alembic/env.py`

### 全局交接 skill

- 用途：读取 handoff 的触发、目录命名、固定骨架、索引引用和自检规则。
  - 索引：`/Users/ywwl/.claude/skills/handoff-document/SKILL.md`
- 用途：确认该 skill 的真实受管位置。
  - 索引：`/Users/ywwl/Downloads/my/code/self-evolution/skills/handoff-document/SKILL.md`

## 6. 代码 / 产物落点

- B-① spec：未修改；当前 Git 路径无 diff。
  - 位置：`docs/designs/2026-07-03-phase-b1-lightrag-dual-retrieval-spec.md`
- B-① 旧交接文档：已存在。
  - 位置：`docs/claude-chat/2026-07-14-1503-handoff/2026-07-14-1503-B-①-知识内容图谱.md`
- 当前剩余工作交接：本文件。
  - 位置：`remain-work/2026-08-26-B-①知识内容图谱Spec修订与交接skill收尾.md`
- handoff skill：已迁入 self-evolution 项目，`~/.claude/skills/handoff-document` 当前为指向该位置的软链接。
  - 位置：`/Users/ywwl/Downloads/my/code/self-evolution/skills/handoff-document/SKILL.md`

## 7. 待办清单

### 必须先做

1. 修订 B-① spec，按已确认 Scope A 写入：
   - RAG 主链启用前置条件；
   - `user_id + scope` 图谱/向量数据域隔离；
   - 实体/关系稳定 ID 与外键设计；
   - 显式摄入 fan-out 与失败语义；
   - `sources` 和 `retrieval_mode` 分离；
   - Coordinator 作为跨 provider 唯一融合边界；
   - 降级路径与 happy-path 验收。
2. 复核修订后的 spec：
   - 使用 `reviewing-plans-isolated`；
   - 复查字段、签名、默认行为、迁移和数据流是否与源代码事实一致；
   - 仅在阻断项关闭后，才进入实现计划。

### 可后做

3. 用独立的新交接场景验证 `handoff-document` skill：
   - 检查能否生成任务特异文件名；
   - 检查引用是否只保留索引位置；
   - 检查新窗口是否能从“一句话接手说明 + 第一动作 + 索引”直接继续。
4. 如发现 handoff skill 验证失败，再在自进化项目实际文件中修订它，保留软链接管理方式。

## 8. 风险与坑点

- **范围膨胀风险**：Scope A 是“把主链前置条件写清并作为启用 gate”，不是在本轮直接实现所有 P0 修复。
- **重复向量路径风险**：graph provider 内部同时写/查 vector，再让 Coordinator 查 vector，会导致重复写入或重复召回。
- **隔离风险**：仅记录 `user_id/scope` 字段不构成隔离；查询 SQL 与 graph 查询接口都必须显式执行过滤。
- **外键风险**：关系端点不能引用非唯一的实体名称字段；需要稳定实体 ID 或完整复合唯一键方案。
- **事实漂移风险**：新的 handoff 不能复述既有文档正文，应回到上方索引位置读取实时来源。
- **未验证结论**：LightRAG 的精确实现对照、全局关系排序方式、融合分数可比性、SQLite migration baseline 都需要独立 spike/验证。

## 9. 交接完成判据

新窗口打开本文件后，能够：

1. 在不回放原会话的情况下，知道 B-① 当前仍停在 spec 修订前；
2. 知道 Scope A 已确认、哪些内容被纳入和哪些明确不纳入；
3. 先定位 B-① spec 与 RAG 主链事实依据；
4. 按“修订 spec → 隔离复核 → 实现计划”的顺序继续；
5. 知道 handoff skill 已进入 self-evolution 的软链接管理体系，但仍需独立行为验证。
