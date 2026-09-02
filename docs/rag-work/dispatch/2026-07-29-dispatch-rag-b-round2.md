# RAG-B 第二轮提示词（直接复制到 RAG-B 窗口）

你是 StudyAgent Harness「RAG 基础能力建设」的 **RAG-B 任务窗口**。主控已完成 B-04 复核：**canonical bytes 协议正式冻结（DEC-012）**，你进入 Phase 2 编码。

## B-04 复核结果：✅ 通过并冻结

主控独立复核（2026-07-29）：
- **两套独立实现复算 V1~V3 全部 8 个哈希匹配**（参考脚本 + 仅按规范文字编写的第二套实现）
- canonical JSON 字节跨实现等价
- normalize 幂等性 3 例通过
- framing 抗字段边界歧义通过

**冻结协议（DEC-012，正式共享契约）：**
- 版本号：`doc-v1` / `doc-norm-1` / `chunk-v1`
- normalize_text 5 步：NFC -> `\r\n`->`\n` -> `\r`->`\n` -> 行尾 `rstrip(" \t")` -> 3+ `\n` 折叠为 `\n\n` -> `strip("\n")`
- framing：`name=<len>:<bytes>`，UTF-8 字节数，字段顺序固定
- doc_id = sha256(frames(protocol="doc-v1", import_namespace, normalizer_version, normalized_document_text))
- chunk_id = sha256(frames(protocol="chunk-v1", doc_id, chunking_spec_version, canonical_element_range, canonical_chunk_text))
- canonical_element_range：半开 `[start,end)`，canonical JSON `{"end":{...},"start":{...}}` 字典序无空白
- V1/V2/V3 测试向量为冻结回归基线

完整协议见 `docs/rag-work/plans/2026-07-27-rag-p0-confirmed-decisions.md` §13 与你的 `RAG-B.md`「Phase 1B 交付」。

## 配套裁决

- **EPUB 纳入 Gate 0 happy-path**：`ChunkingService` 预留 `source_format="epub"` 适配（RAG-A 的 `EpubExtractor` 已验收通过）
- **stable-ID 评测收敛**：方向冻结，扩展归 RAG-D 设计（BLK-013 前），你不建旁路评测

## 本轮任务（Phase 2：B-08~B-11）

- [ ] **B-08** 实现 `ChunkingService`（无状态纯服务；元素/文本 -> ChunkDocument；按 DEC-012 协议生成 `doc_id/chunk_id`；预留 `source_format="epub"`）
- [ ] **B-09** 实现 `KnowledgeIngestionService`（薄编排；extract/adapt/chunk/index；**写前校验 `import_namespace` 非空 fail-fast**；全有或全无事务）
- [ ] **B-10** 实现正式 `doc_id/chunk_id` 生成与 metadata 校验（严格按 DEC-012 协议；V1/V2/V3 作为回归测试）
- [ ] **B-11** 修复 provider provenance round-trip（`PgVectorProvider.search` 回填 SQL 顶层 `doc_id` 到 `Chunk.metadata`；`chunk_id` 原样保留；写前顶层与 metadata 一致性校验）
- [ ] 配合 DEC-005：新增 Alembic migration 添加 `vector_chunks.chunk_id` 可空列

## 回写要求

每完成一个 todo 即更新 `docs/rag-work/status/RAG-B.md`，附实现路径、测试命令与运行结果。

## 禁止

- 用临时 hash/row ID/`chunk_index` 填充 `chunk_id`（协议已生效，正式写入必须按 DEC-012）
- 把 benchmark `paragraph_id` 进入 `doc_id/chunk_id` hash
- 另建旁路 evaluator
- 宣称幂等/隔离（Gate 0 仍 append-only）

## 完成后

简要报告：实现清单、测试结果、provider round-trip 验证证据、待主控复核项。
