# RAG 进展提交与工作区现状交接

## 1. 一句话接手说明

RAG 四窗口（A/B/C/D）的 Phase 1A~1D 与 Phase 2 代码、测试、文档已全部合并为一个提交 `459f28d` 落在本地 `main`（ahead 2，未推送）；接手者应先推送或决定推送时机，再按主清单推进 Phase 3（C-12+ 在线 evidence 接线）与 Phase 4（F-01~F-06 真实 PG 摄入）。

## 2. 当前状态

- 已完成：
  - 提交 `459f28d`（80 文件，+7334/-1371）：EPUB extractor、ChunkingService/KnowledgeIngestionService（DEC-012 stable ID）、visibility/outcome 五态、在线 composition fail-fast、`20260729_chunk_id` 迁移、init migration 补 mastery 表、RAG-D 只读 gate/runner、`docs/rag-work/` 文档区整体迁入。
  - 提交 `e2b298b`：README 向量维度修正 `Vector(1536)`→`Vector(2048)`（与 `app/models/tables.py:107`、`config.py:23`、迁移 `:39` 对齐）。
  - 全量回归实测：`uv run pytest tests/ -q` → **597 passed / 1 skipped / 8 deselected**；RAG 定向 166 passed。
  - 主控 handoff 已记录 RAG-A（`remain-work/2026-08-27-RAG-A-EPUB提取器验收与Phase4接续-主控handoff.md`）。
- 进行中：无编码任务；等待主控复核。
- 未开始但已确认要做：Phase 3（C-12~C-17 在线 evidence→Tutor）、Phase 4（F-01~F-06 真实 PG 摄入与 attestation）、Phase 5（D-08+ 真实 baseline）。
- 当前卡点 / 待确认项：
  - `main` 相对 `origin/main` **ahead 2 未推送**。
  - RAG-C §F/§G 采用值（在线入口落点、六码错误码、top_k 上限 10、受限 payload 契约）待主控追认，见 `docs/rag-work/status/RAG-C.md` §10 追认表。
  - 真实 PostgreSQL + pgvector + embedding 环境验证未执行（B/C 线均 `infrastructure_inconclusive`）。

## 3. 接手后第一动作

1. `git status -sb` 确认仍为 ahead 2、工作区仅剩 `.claude/skills/` 与 `.evolve/local/` 两个本地未跟踪目录（勿提交、勿清理）。
2. 与用户确认后 `git push origin main`（推送前按纪律先 `git pull --no-rebase` 同步）。
3. 以主控身份复核 RAG-C §10 追认表（`docs/rag-work/status/RAG-C.md`），裁决后写入唯一主清单 `docs/rag-work/plans/2026-07-24-rag-foundation-parallel-todolist.md` 并分发第三轮派工。
4. 补齐 RAG-B/C/D 的主控 handoff（任务清单 #2/#3/#4 尚 pending；各权威状态见 `docs/rag-work/status/RAG-{B,C,D}.md`，B3 主控复核记录在 `RAG-B.md` §主控独立复核记录）。

## 4. 关键决策与边界

- 已确认决策：
  - 四窗口状态口径：A=Phase 1A 验收通过待命 Phase 4；B=B-08~B-11+B3-01~B3-07 verified（SQLite/单测维度），PG `infrastructure_inconclusive`；C=C-09~C-11 完成待追认，Phase 3 未开始；D=D-01~D-07 完成，真实 baseline 等 Phase 4。
  - 完成口径红线：不得把 SQLite/Fake/单测结果说成真实 PG 产品链；不得宣称在线 grounded answer 或产品 baseline 已完成。
  - Extractor 边界冻结 `file_path -> str`（DEC-002）；Gate 0 append-only（DEC-005）；visibility 仅 global/private 且歧义行 fail closed（DEC-001）；outcome 五态（DEC-008）；在线 composition 三条件 fail-fast（DEC-007）。
- 明确不要做的事：
  - 不提交/清理 `.claude/skills/`、`.evolve/local/`（本地 self-evolution 资产）。
  - 不用 `git add -A` / `git add .`；不改写已推送历史。
  - 不在窗口侧直接改主清单或他人状态片段（单写者约束，`docs/rag-work/status/README.md`）。
- 仍未定论、不能当作事实的点：
  - 状态文档中 RAG-B/C/D 仍混有「实施前历史快照」（如「ChunkingService 待建」「factory 未注册 .epub」等旧表述），接手时以各文件顶部「当前状态」行与 Phase 回报章节为准，旧段落视为历史。
  - 真实 EPUB 兼容性未验证（仅动态最小 fixture）；`li/blockquote/pre` 内容不提取；ZIP bomb 防护未做。
  - RAG-D 文档中 `test_rag_d.py` 计数存在 13/14/15 passed 的历史层级差异（随审阅补测递增），当前以全量 597 为准。

## 5. 必看材料索引

- 用途：RAG 工作区总入口、当前阶段与单写者协议。索引：`docs/rag-work/README.md`。
- 用途：唯一主清单（blocker 账本 BLK-001~013、Phase 0-6 TodoList、§9 回应包）。索引：`docs/rag-work/plans/2026-07-24-rag-foundation-parallel-todolist.md`。
- 用途：已冻结共享决策 DEC-001~012。索引：`docs/rag-work/plans/2026-07-27-rag-p0-confirmed-decisions.md`。
- 用途：四窗口权威状态与验证证据。索引：`docs/rag-work/status/RAG-{A,B,C,D}.md`。
- 用途：RAG-A 主控交接（Phase 4 接续路径与 F-01 前置）。索引：`remain-work/2026-08-27-RAG-A-EPUB提取器验收与Phase4接续-主控handoff.md`。
- 用途：本轮提交内容与范围。索引：`git show 459f28d --stat`、`git show e2b298b`。

## 6. 代码 / 产物落点

| 产物 | 用途 | 状态 |
|---|---|---|
| `app/harness/chunking_service.py` | 无状态切块 + DEC-012 stable ID | 本轮已提交（B 线） |
| `app/harness/knowledge_ingestion.py` | extract→chunk→index 薄编排 + 写入确认 | 本轮已提交（B 线） |
| `app/infrastructure/rag/extractors/epub_extractor.py` | EPUB→纯文本（标准库） | 本轮已提交（A 线） |
| `app/agents/retriever.py` / `coordinator.py` / `store.py` / `pgvector_provider.py` | visibility 过滤、五态 outcome、安全错误、provenance round-trip | 本轮已提交（C/B 线） |
| `app/orchestration/assembly.py` | `run_online_agent_session` 三条件 fail-fast | 本轮已提交（C 线） |
| `alembic/versions/20260729_add_vector_chunk_id.py` | vector_chunks 补 chunk_id 列 | 本轮已提交 |
| `alembic/versions/d48d7137f57f_*.py` | init 补建 mastery 两表（修迁移链可达性） | 本轮已提交（B3-07） |
| `benchmarks/rag/books/the-myth-of-sisyphus/rag_d.py` + `tests/eval/test_rag_d.py` | 只读 asset validator、六项 gate、单次 runner | 本轮已提交（D 线） |
| `docs/rag-work/` 全区 | plans/specs/decision-canvas/dispatch/status | 本轮已提交 |
| `README.md` | 在线 RAG 前置、Gate 0 服务、7 迁移、597 测试计数、Vector(2048) | 本轮已同步并提交 |

## 7. 待办清单

### 必须先做

1. 确认并推送 `main`（ahead 2：`459f28d` + `e2b298b`）。
2. 主控追认 RAG-C §10 采用值表，回写主清单，放行 Phase 3。
3. 补 RAG-B/C/D 主控 handoff（沿用 RAG-A handoff 模式，落 `remain-work/`）。

### 可后做

4. Phase 3 派工（C-12~C-17）；Phase 4 前置环境（Docker PG + pgvector + embedding key）就绪后跑 F-01。
5. 状态文档历史段落归一化（各窗口唯一写者执行；RAG-A 仅少量残留：`:96` 的 20 passed 旧值、`:4` 旧主清单链接、实施前核查表标题）。
6. 提醒各窗口修复状态文档内失效的 `../designs/` 相对链接（迁移后应指向 `../plans/`、`../specs/`）。

## 8. 风险与坑点

- **未推送风险**：本地领先 2 个提交，长时间不推送可能与他窗口/远程产生分叉；推送前先 `pull --no-rebase`。
- **本地资产误提交**：`.claude/skills/`（软链）与 `.evolve/local/` 是 self-evolution 本地资产，保持未跟踪，勿 `git add .`。
- **ruff 基线**：`uvx ruff check .`（CI 命令）当前对全仓报 344 项既有告警（多为历史测试的 import 排序/未用导入，非本轮引入）；本轮新增文件告警未单独清理，如 CI 因此红，需单独一次 lint 收敛提交。
- **状态文档历史残留**：B/C/D 文档前半段是实施前快照（见 §4），不要据此判断当前能力。
- **完成口径**：真实 PG/embedding 未验证前，一切「verified」仅限 SQLite/单测维度。

## 9. 交接完成判据

- 接手者读完第 1、3、7 节即知道：先进 `git status` 核对 ahead 2 → 推送 → 主控追认 C 线 §F/§G → 补 B/C/D handoff。
- 能从 §5 索引回到一手材料（主清单、状态片段、DEC 决策、RAG-A handoff），不依赖本文件转述。
- 明确哪些不能做（误提交本地资产、越权改单写者文档、宣称生产闭环）。
