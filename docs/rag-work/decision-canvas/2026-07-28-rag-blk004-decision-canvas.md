# RAG Foundation · BLK-004 Decision Canvas

> ⛔ **已废弃（2026-07-29 用户裁定）**：本页为并行窗口旧版画布，与主事实源不一致（如测试向量门槛已改为三组）。BLK-004 的现行决策画布为 `docs/rag-work/decision-canvas/2026-07-27-rag-blk004-decision-dashboard.md`（含 DEC-005/006 已确认裁决），事实源以 `docs/rag-work/plans/2026-07-27-rag-p0-confirmed-decisions.md` 与主清单为准。本页仅留存历史，不得作为实施或裁决依据。

> **背景地图**：[RAG Foundation Program Cockpit](2026-07-28-rag-foundation-program-cockpit.html)（子框架结构、当前/目标数据流、Phase 进度、ID 分工与最小名词表）。  
> **本页只处理当前决策增量**：`chunk_id` 存储位置与 range 坐标基线。  
> **状态**：两项技术裁决待用户确认；本页不是已确认事实源。

---

## 0. 三分钟决策摘要

BLK-004 要让每条产品证据拥有可复算、可写入、可检索回传的“出生证明”。子框架全景与 BLK-004 的位置见 Program Cockpit；这里不重复背景。

当前只需判断两件事：

| 待确认 | 推荐 | 现在不决定的后果 |
|---|---|---|
| **D-004-1：`chunk_id` 放哪里** | `vector_chunks` 新增可空顶层列；暂不唯一 | provenance 继续藏在自由 JSON，数据库与 attestation 无法围绕同一 identity 核验 |
| **D-004-2：range 怎么计** | 0-based + Unicode code point + 半开 `[start,end)` | 相同文本可产生不同坐标和 ID，RAG-B 无法提交可靠测试向量 |

> ⚠️ 同意这两项不等于批准最终 hash 算法，也不等于承诺幂等。canonical bytes 与测试向量仍需 RAG-B 补证。

---

## 1. 本决策已核验的事实与约束

| 类型 | 事实 / 约束 | 证据 |
|---|---|---|
| 已实现 | `vector_chunks` 有顶层 `doc_id`，没有顶层 `chunk_id` | `app/models/tables.py:92-111` |
| 已实现·缺口 | Provider 写入 `doc_id/metadata_json`；检索 SQL 读出 `doc_id`，构造 `Chunk` 时未回填 | `app/infrastructure/rag/pgvector_provider.py:60-109,137-156` |
| 已实现 | `Chunk` 只有 `content/score/source/metadata`，无一等 `doc_id/chunk_id` | `app/infrastructure/rag/coordinator.py:7-14` |
| 已确认 | 生产 ID 与 benchmark `paragraph_id` 分离；顶层 `doc_id` 是读侧权威来源；Gate 0 append-only | `docs/rag-work/plans/2026-07-24-rag-foundation-parallel-todolist.md:222-230` |
| spec 冲突 | 旧 Chunking spec 把 `canonical_element_range` 写成闭区间 | `docs/rag-work/specs/2026-07-24-project-chunking-service-spec.md:312-320` |
| 未冻结 | canonical bytes serializer、stable-ID generator、公开复算测试向量 | 同上 `:312-353`；主账本 `:232-240` |

---

## 2. 两个决策对主链的具体影响

背景数据流见 [Program Cockpit §3](2026-07-28-rag-foundation-program-cockpit.html#3-当前链与目标链)。本轮只改变红色边界内的契约：

```text
ChunkingService 生成 ChunkDocument
  │ D-004-2 冻结 range 语义 → 未来 stable-ID 输入无坐标歧义
  ↓
KnowledgeIngestionService → PgVectorProvider → vector_chunks
  │ D-004-1 新增顶层 chunk_id → 写入/查询有权威槽位
  ↓
PgVectorProvider.search → Chunk.metadata
  │ 读侧必须回填顶层 doc_id/chunk_id → provenance round-trip 闭合
  ↓
Retriever / attestation / baseline / E2E 才能引用同一 evidence identity
```

| 决策 | 必须同步的模块/产物 | 明确不在本轮做 |
|---|---|---|
| D-004-1 顶层 `chunk_id` | migration、`app/models/tables.py`、Provider 写/读契约、PG/SQLite fixture 与契约测试 | 唯一约束、去重、replace/upsert/delete |
| D-004-2 半开 range | 待建 ChunkingService 的 range 数据结构、Chunking spec、测试向量 | Unicode normalization form、空白顺序、hash framing |

---

## 3. 决策一：`chunk_id` 放在哪里？

| | A：新增 SQL 顶层 `chunk_id`（推荐） | B：只放 `metadata_json` | C：暂不持久化 |
|---|---|---|---|
| 做法 | migration 增加可空列；正式协议通过后新摄入必填；暂不唯一 | JSON 内保存，Provider 校验 key | 只用 row ID / chunk_index |
| 收益 | DB、检索、attestation、评测共享同一 identity 面 | 能保存，schema 改动小 | 最快得到 prototype |
| 代价 / 风险 | bytes 协议冻结前不能填临时 production 值 | 易缺失、重命名、被 metadata 覆盖；查询/约束弱 | 无法可靠回查同一 chunk |
| 适用目标 | 正式产品链 | 过渡性内部实现 | 演示原型 |

**推荐 D-004-1：选择 A，分两步实施。**

1. 先批准独立、可空的顶层 provenance 列；不加唯一约束，不改变 append-only。
2. canonical bytes/range 和测试向量通过复核后，新摄入正式 chunk 才必须写稳定 `chunk_id`；此前禁止用临时 hash、row ID 或 `chunk_index` 冒充 production stable ID。

**判据**：可审计的存储槽位现在就能冻结，最终 hash 算法可以等证据充分后再冻结；两件事无需捆绑。

---

## 4. 决策二：range 使用什么基线？

| | A：0-based + Unicode code point + 半开 `[start,end)`（推荐） | B：1-based + 闭区间 `[start,end]` | C：只留 chunk_index / locator |
|---|---|---|---|
| 切片复算 | 直接 `text[start:end]` | 需 `+1/-1` 转换 | 无法精确复算 |
| 相邻 / 空范围 | `A.end == B.start`，语义统一 | 需额外边界规则 | 无统一规则 |
| 跨实现 | 明确单位，不依赖 UTF-8 byte/tokenizer | 仍需另约定计数单位 | 各格式自行解释 |
| 代价 | 修订旧 spec 的“闭区间”草案 | 与旧草案表面一致，但更易边界错 | 放弃可复算 stable ID |

**推荐 D-004-2：选择 A。**

```text
- element 序号：0-based
- element 内 offset：Unicode code point
- 区间：半开 [start, end)
- identity 输入：规范元素范围 + 规范 chunk 文本
- source_locator：仅作人类回查与审计，不作稳定主键
```

**判据**：与 Python 字符串切片直接对应；相邻范围和空范围无歧义；比闭区间少一层边界换算。

> ⚠️ 本裁决只冻结坐标，不冻结 Unicode normalization form、换行/空白顺序或 hash framing。

---

## 5. 影响传播与冻结边界

| 下游 | D-004-1 的影响 | D-004-2 的影响 |
|---|---|---|
| Phase 2 | migration、模型、Provider round-trip、fixture | ChunkingService range 类型与 ID 输入 |
| Phase 4 | attestation 可按 chunk identity 关联 DB | 相同输入可复算 chunk 边界 |
| Phase 5/6 | 检索证据可被评测和在线审计直接引用 | gold locator 可与产品 chunk 做可解释映射 |

**确认后仍保持 `blocked` 的事项**：

- canonical document/chunk bytes；
- UTF-8、Unicode normalization、换行与空白处理顺序；
- 无歧义 serialization / framing；
- 至少两组覆盖 Unicode、CRLF、空白与相邻 range 的测试向量；
- provider round-trip 的 PG/SQLite 运行证据。

---

## 6. 实施与验收门槛

### RAG-B 先补证

| 待补证 | 通过标准 |
|---|---|
| canonical document bytes | 不同运行环境对同一输入得到相同 `doc_id` |
| canonical chunk bytes | 字段边界不可碰撞，顺序可机械验证 |
| 测试向量 | 独立实现对 Unicode/CRLF/空白/相邻 range 得到相同 ID |
| Provider round-trip | `doc_id/chunk_id/source_locator` 写入后不丢失、不冲突 |

### Happy-path 与失败路径

| 路径 | 必须验证 |
|---|---|
| Happy-path | 同一规范输入重复生成相同 doc/chunk ID；PG 检索回传相同 identity；attestation 可关联 DB 行 |
| 冲突 | 顶层身份与 metadata 不一致时写前拒绝，不产生部分写入 |
| Unicode/换行 | 按冻结规则通过公开测试向量 |
| 授权 | 未授权高相似 chunk 在排序与 LIMIT 前过滤；identity 不泄露 |
| 基础设施 | migration/schema 不满足时诚实失败，不用 fake/手工 schema 冒充通过 |

---

## 7. 现在请确认

1. **D-004-1**：新增可空顶层 `chunk_id`；正式协议通过后新摄入必填；不加唯一约束、不承诺幂等。
2. **D-004-2**：range 采用 **0-based + Unicode code point + 半开 `[start,end)`**；格式 locator 只用于审计。

确认后才会：

- 将两项写入 `2026-07-27-rag-p0-confirmed-decisions.md` 和主账本；
- 修订 Chunking spec 中冲突的 range/存储提案；
- 分发 RAG-B 补证，**不会直接把 BLK-004 标成已解除**。

← [需要回看整体结构与进度时，返回 Program Cockpit](2026-07-28-rag-foundation-program-cockpit.html)
