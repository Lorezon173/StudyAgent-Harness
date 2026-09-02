# RAG-B 第三轮最小修复派工提示词

你是 StudyAgent Harness RAG Foundation 的 **RAG-B 窗口**。主控对 B-08~B-11 回执进行了独立复核：局部实现和测试存在，但发现阻断性 correctness / migration 问题。**DEC-012 协议仍然冻结有效；本轮只做最小修复，不重新设计共享契约。**

## 角色与单写者边界

- 你只修改 RAG-B 负责的代码、测试、spec（必要时）与 `docs/rag-work/status/RAG-B.md`。
- 禁止修改主清单 `docs/rag-work/plans/2026-07-24-rag-foundation-parallel-todolist.md`。
- 禁止修改 RAG-A/C/D 状态片段。
- 不扩大 Gate 0 范围：不做上传 API、幂等/replace/delete、图检索、Tutor 接线或旁路 evaluator。
- append-only 重复导入**不是 bug**，不要修成幂等。

## 必读

1. 主控账本：`docs/rag-work/plans/2026-07-24-rag-foundation-parallel-todolist.md`（BLK-004、BLK-008、Phase 2）
2. 已冻结协议：`docs/rag-work/plans/2026-07-27-rag-p0-confirmed-decisions.md`（DEC-005/006/012）
3. 你的状态片段：`docs/rag-work/status/RAG-B.md`
4. Gate 0 spec：`docs/rag-work/specs/2026-07-24-project-chunking-service-spec.md`
5. 当前实现：`app/harness/chunking_service.py`、`app/harness/knowledge_ingestion.py`、`app/infrastructure/rag/pgvector_provider.py`、`alembic/versions/m3_unify_user_id_type.py`、`alembic/versions/20260729_add_vector_chunk_id.py`

## 主控已独立复核确认的问题

### B3-01：canonical 元素流没有从 canonical 全文重建（🔴）

**证据**：`chunking_service.py:155-171, 233-236`

`chunk_elements()` 直接使用调用者传入的元素边界。以下等价输入：

```python
[ChunkElement("aa\n\nbb")]
[ChunkElement("aa"), ChunkElement("bb")]
```

具有相同 canonical 全文与相同 `doc_id`，却生成不同 element range / `chunk_id`。

**要求**：按 DEC-012，先从 canonical 全文按 `\n\n+` 重建 canonical 元素流，再计算 range/ID；补对抗测试证明上述两种等价表示产生相同 chunk 序列与 ID。

### B3-02：长文本切分越界、碎片、overlap 破坏（🔴）

**证据**：`chunking_service.py:276-285`

marker 位于 limit 时产生 `chunk_size+1`；overlap 回退可重复命中 marker 产生 2 字符碎片。

**要求**：
- 块长度绝不超过 `chunk_size`（除 atomic hard-limit 的受控失败路径外）；
- marker 搜索边界修正；
- overlap 回退不得重复生成退化碎片；
- 增加英文空格、中文句界、overlap=0、overlap>0 的对抗测试。

### B3-03：pending_size flush 后计算错误（🟡）

**证据**：`chunking_service.py:201-205`

flush 前计算的 separator_size 在 `emit_pending()` 清空后仍被累计，新 pending 组首元素多算 2 字符。

**要求**：flush 后重新计算 separator_size / pending_size；补跨 flush 边界测试，确保实际组合块按 policy 而非提前切断。

### B3-04：atomic/table/formula 无 hard limit / warning（🟡）

**证据**：`chunking_service.py:193-200, 227`；spec 要求超 hard limit 必须 warning 或失败。

**要求**：定义明确、可测试的 hard-limit 策略：atomic 块不可静默进入 embedding；超过 embedding 安全阈值时返回受控 warning 或失败。更新 `IngestResult.warnings` 或错误状态，使行为可观察。不得借此把 atomic 元素强行切裂。

### B3-05：legacy NULL SQL identity 覆盖 metadata provenance（🟡）

**证据**：`pgvector_provider.py` 读侧无条件以 SQL `doc_id/chunk_id` 覆盖 metadata；历史行 SQL 列 NULL/空串会抹掉 metadata 中合法 identity。

**要求**：
- 新写入仍以 SQL 顶层身份为权威；
- legacy SQL NULL/空串时，读侧必须回退保留 metadata 中合法 `doc_id/chunk_id`，并建立明确兼容策略；
- 补 PG/SQLite 读侧 legacy 对抗测试。

### B3-06：written_chunk_count 可能误报成功（🟡）

**证据**：`knowledge_ingestion.py:75-81`

`index_documents()` 返回 None，provider 缺失时可 no-op；当前直接把 `written=planned`。

**要求**：正式 IngestResult 不得仅以 planned 推断 written。最小方案：让 coordinator/provider 返回可核验的写入确认；若无法确认，返回明确非成功/未确认状态，不生成成功 attestation。补 provider 缺失/no-op 对抗测试。

### B3-07：干净 DB 迁移链阻断（🔴，BLK-008）

**主控复现命令**：

```bash
DATABASE_URL=sqlite+aiosqlite:///tmp/clean.db uv run alembic upgrade head
```

**结果**：历史 `m3_unify_user_id_type.py:26-31` 查询 `mastery_nodes/mastery_edges`，但干净迁移链未创建它们，报 `no such table: mastery_nodes`；因此 `20260729_chunk_id` 不可达。

**要求**：修复迁移链，使干净 SQLite **与 PostgreSQL** 均能 `alembic upgrade head`，并使 `20260729_chunk_id` 可达。优先修历史 parent migration 的表存在性/迁移顺序问题；不要绕过 Alembic、不要靠应用 `create_all` 冒充迁移成功。

## 必须保持

- DEC-012 canonical bytes 协议与 V1/V2/V3 回归基线不变；
- DEC-005 可空顶层 chunk_id、不加唯一约束、append-only 语义不变；
- DEC-001 scope/owner fail-closed 组合不放宽；
- 不把 benchmark `paragraph_id` 放进 production hash；
- 仍走 `KnowledgeIngestionService → RAGCoordinator.index_documents → PgVectorProvider` 主链。

## 验收最小命令

```bash
uv run pytest tests/unit/harness/test_chunking_service.py tests/unit/harness/test_knowledge_ingestion.py -q
uv run pytest tests/unit/infrastructure/test_pgvector_provider.py tests/unit/infrastructure/test_rag.py -q
DATABASE_URL=sqlite+aiosqlite:///tmp/clean.db uv run alembic upgrade head
```

并补充本提示词列出的所有对抗用例。PostgreSQL 实测若环境不可用，诚实标 `infrastructure_inconclusive`，不得伪称通过。

## 回写要求

只更新 `docs/rag-work/status/RAG-B.md`：
- 每项 B3-01~B3-07 的修复文件、测试名、命令、实际结果；
- migration clean DB 运行证据；
- 仍未完成的 PG/embedding 环境验证；
- 不得标 `verified`，直到主控独立复核通过。
