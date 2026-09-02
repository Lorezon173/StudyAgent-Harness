# RAG Foundation：接续 RAG-B 第三轮修复与主控复核

## 1. 一句话接手说明
- RAG Foundation 的 P0 决策已冻结、RAG-A 已验收；RAG-B Phase 2 因七项已复现的 correctness/migration 缺陷被回退到第三轮最小修复。接手者应先安排并审核 RAG-B 对 B3-01～B3-07 的修复，随后独立复核，不能替 RAG-B 写其代码或状态片段。

## 2. 当前状态
- 已完成：DEC-001～012 已冻结；RAG-A EPUB extractor 前轮验收；RAG-B 问题入主控账本；B 第三轮派工已创建；C/D 的已有实现做过初步独立审查。
- 进行中：RAG-B 第三轮最小修复尚未收到回执；此前 EPUB/ingestion 的补充只读审查已结束，未扩大 B3 范围。
- 未开始但已确认要做：收到 B 回执后，以主控身份重新运行专项测试、对抗测试和干净 SQLite migration；PG 环境不可用时只能标 `infrastructure_inconclusive`。
- 当前卡点 / 待确认项：干净 DB migration 失败；B 的 chunk identity/splitter/write confirmation 未通过独立复核；正式 PG 与 embedding 环境尚未提供。

## 3. 接手后第一动作
1. 打开 `../2026-08-18-dispatch-rag-b-round3.md`，把它作为 RAG-B 的唯一第三轮执行要求。
2. 启动一个仅负责 RAG-B 范围的执行单元：只允许修改 B 负责的实现、测试、必要 spec 和 `status/RAG-B.md`；禁止修改主清单或其他窗口状态。
3. 并行启动两个只读复核单元：一个覆盖 chunking/ingestion/migration，一个覆盖 pgvector read/write identity；它们不得编辑文件，也不得替代 RAG-B 修复。
4. 等 B 回执后，主控独立运行派工文档列出的命令，并检查 B3 对抗用例；通过前不得写 `verified`。

## 4. 关键决策与边界
- 已确认决策：以 `plans/2026-07-27-rag-p0-confirmed-decisions.md` 的 DEC-001～012 为唯一决策源；尤其 DEC-005/006/012 约束可空顶层 `chunk_id`、range 表达和 canonical bytes/stable ID。
- 明确不要做的事：不重新设计共享契约；不引入上传 API、幂等/replace/delete、图检索、Tutor 接线或 benchmark 旁路；append-only 重复导入不是 bug；不将 `paragraph_id` 写入 production hash；主控不写 `status/RAG-A/B/C/D.md`。
- 仍未定论、不能当作事实的点：PostgreSQL 实际 migration 与 vector/embedding 完整链尚未在当前环境验证；D 的正式基线仍不成立；EPUB 提取器的 strict UTF-8、全书失败即空串是当前已验收边界，不能在 B 最小修复轮改变。

## 5. 必看材料索引
- 用途：B3-01～B3-07 的事实、验收命令与写入边界。  
  索引：`docs/rag-work/dispatch/2026-08-18-dispatch-rag-b-round3.md`
- 用途：blocker 状态与 Phase 2/4 解锁条件。  
  索引：`docs/rag-work/plans/2026-07-24-rag-foundation-parallel-todolist.md`（BLK-004、BLK-008、Phase 2）
- 用途：冻结协议和禁止扩张的契约边界。  
  索引：`docs/rag-work/plans/2026-07-27-rag-p0-confirmed-decisions.md`（DEC-005、DEC-006、DEC-012）
- 用途：Gate 0 chunk hard-limit 与 range 规范。  
  索引：`docs/rag-work/specs/2026-07-24-project-chunking-service-spec.md`
- 用途：B 的回执和后续唯一可写回位置。  
  索引：`docs/rag-work/status/RAG-B.md`

## 6. 代码 / 产物落点
- `app/harness/chunking_service.py`：B3-01～B3-04 的 canonical element、splitter、flush、atomic hard-limit 入口。
- `app/harness/knowledge_ingestion.py`：B3-04 warning/status 与 B3-06 可核验 write confirmation 入口。
- `app/infrastructure/rag/pgvector_provider.py`：B3-05 legacy metadata fallback 与写入确认链路。
- `alembic/versions/m3_unify_user_id_type.py`、`alembic/versions/20260729_add_vector_chunk_id.py`：B3-07 migration 链。
- `tests/unit/harness/test_chunking_service.py`、`tests/unit/harness/test_knowledge_ingestion.py`、`tests/unit/infrastructure/test_pgvector_provider.py`、`tests/unit/infrastructure/test_rag.py`：必须补/更新的对抗测试落点。
- `docs/rag-work/status/RAG-B.md`：只能由 RAG-B 写回本轮修复、命令和实际结果。

## 7. 待办清单
- P0 必须先做：RAG-B 按 B3-01～B3-07 修复并补对抗测试。
- P0 必须先做：主控重跑 chunking/ingestion、provider/rag 与 clean SQLite migration 验收；检查迁移是否已到 `20260729_add_vector_chunk_id`。
- P1 后做：若环境可用，执行 PostgreSQL clean migration；若不可用，记录 `infrastructure_inconclusive`，不得声称通过。
- P1 后做：向 RAG-C/RAG-D 发送各自状态片段链接/测试快照修订请求，不得由主控直接编辑。
- P2 后做：B 验收后才推进 C Phase 3、正式 EPUB ingestion/attestation 和 D baseline。

## 8. 风险与坑点
- 现有专项测试历史上可通过，不能替代 B3 对抗测试或 clean DB migration 实测。
- `index_documents()` 的无返回值/静默 no-op 是 B3-06 的核心风险；不得再用 planned count 推断写入成功。
- legacy SQL identity 的 NULL/空串必须与新写入的 SQL 顶层权威规则区分，不能反向让 metadata 覆盖合法新行。
- migration 不能靠 `create_all` 绕过；必须从干净 Alembic 链验证。
- EPUB 补充审查确认“摄取端到端 EPUB/provenance 断言不足”是 Phase 4 验收项，不应趁 B3 扩大范围。

## 9. 交接完成判据
- 新窗口无需回放会话，即能找到 B 第三轮派工、冻结协议、blocker、代码和测试入口。
- 新窗口能先派 B 修复、再派只读复核、最后独立执行验收，并明确知道不得编辑其他窗口状态或提前宣称 B 已验证。
