# 检索系统升级 · 阶段 A 三层规划（真向量检索 + 统一 PG）

> 规划日期：2026-06-16
> 来源追溯：[`2026-06-16-current-vs-frameworks-decision-report.md`](../research/2026-06-16-current-vs-frameworks-decision-report.md) 路线 A
> 规范遵循：`.claude/rules/dev-standards.md`「模块开发三层详细规划」——本文档为**文字描述规划，不含代码**，待用户确认后方可编码。
> 用户决策（2026-06-16）：①先做 A；②知识内容侧（LightRAG）记录规划、下阶段做；③掌握度时序化+触发复习下阶段做、须用户可选可调；④存储统一 PG，为 LightRAG 铺垫。

---

## 第一层：模块总览

### 目标边界

**做什么**：把当前"假向量检索"接成"真语义向量检索"，存储统一到 PostgreSQL + pgvector。

**本阶段明确不做**（记录到第四节，下阶段做）：
- ❌ 知识内容图谱（LightRAG 双层检索）—— 仅做"铺垫"，不实现图谱。
- ❌ 掌握度图谱时序化、触发复习机制。
- ❌ PDF 版面级解析（ragflow DeepDoc）。

### "铺垫 LightRAG"在 A 阶段的具体含义（克制，不超范围）

LightRAG 落地需要三个基础设施前提，A 阶段顺手把这三件预埋好，但**不实现 LightRAG 本身**：

| LightRAG 未来需要 | A 阶段铺垫动作 |
|---|---|
| PostgreSQL 存图+向量 | 本阶段就把向量落到 pgvector，PG 连接/扩展跑通 |
| 统一的 embedding 入口 | 本阶段建一个 `EmbeddingService`，未来 LightRAG 复用同一个 |
| 文档→chunk 的摄入接口 | 本阶段 `IndexProvider.index` 保持文档级接口，未来图谱抽取从同一入口接 |

### 技术选型：向量存储用 pgvector，不用 chromadb

| | pgvector（选它） | chromadb（不选） |
|---|---|---|
| 做法 | 向量存进 PG 的 vector 列，与业务表同库 | 独立向量库，另起服务/文件 |
| 与现状契合 | docker-compose 已是 `pgvector/pgvector:pg16`；`database.py:41` 已自动建 vector 扩展 | pyproject 虽装了 chroma，但 docker 无 chroma 服务 |
| 为 LightRAG 铺垫 | ✅ LightRAG 原生支持 PG 存图+向量，一套库到底 | ❌ 未来上 LightRAG 还要再迁回 PG |
| 存储统一 | ✅ 符合"统一到 PG"决策 | ❌ 又多一个存储后端 |

**选择理由**：用户明确要"统一 PG + 铺垫 LightRAG"，而基础设施（docker 镜像、vector 扩展）已倒向 pgvector。选 chroma 等于和已有基础设施、和用户决策、和未来 LightRAG 三处对冲。chromadb 依赖暂留（不删，避免动 pyproject），仅不使用。

### 依赖关系与四层架构衔接

```
API → Orchestration → Harness(RetrieverAgent) → Infrastructure(RAGCoordinator → PgVectorProvider → EmbeddingService + PG)
```
全部改动落在 **Infrastructure 层**（`app/infrastructure/rag/`）+ 一条 alembic 迁移。RetrieverAgent（Harness）接口不变，符合四层单向依赖与"薄壳节点"。

---

## 第二层：子模块概述

### 子模块 1：EmbeddingService（新建）

- **职责**：统一的文本→向量入口。把文本（单条/批量）转成定长 float 向量。
- **接口契约**：`embed_one(text) -> list[float]`；`embed_many(texts) -> list[list[float]]`；暴露 `dim`（向量维度）。
- **数据流**：上游 = PgVectorProvider（索引时批量 embed、检索时 embed query）；下游 = OpenAI embedding API（复用 `llama-index-embeddings-openai` 或直接 langchain，与现有 LLMService 同源配置）。
- **状态管理**：无状态，懒加载 client（仿 `LLMService.llm` 的 lazy property）。
- **错误处理**：embedding 失败抛异常，由调用方（Provider）降级；A 阶段不静默吞。
- **配置**：embedding model 名 + api_key/base_url 从 settings 读，复用现有 OpenAI 配置。

### 子模块 2：PgVectorProvider（新建，实现 IndexProvider 协议）

- **职责**：真正的向量检索后端。替代当前空壳 `RAGStore`，作为 RAGCoordinator 的 "vector" provider。
- **接口契约**：实现既有 `IndexProvider`（`index(docs)` / `search(query, top_k) -> list[Chunk]` / `doc_count`）——**协议不变，测试契约不破**。
- **数据流**：`index` → EmbeddingService 批量 embed → 写入 PG 向量表；`search` → embed query → PG 做 `<=>`（余弦/L2）近邻查询 → 转成 `Chunk(content, score, source="vector", metadata)`。
- **状态管理**：向量持久化在 PG，Provider 本身无内存态。
- **错误处理**：PG 连接失败 / 无结果 → 返回空 list（RetrieverAgent 据此判 empty/timeout，机制已存在）。
- **score 语义**：pgvector 距离要转成"越大越相关"的 score，保持与现有 `retrieve()` 的 confidence 阈值（avg>2 high）语义兼容——这里需校准（见详细计划）。

### 子模块 3：向量表与 alembic 迁移（新建）

- **职责**：PG 中存放 chunk 文本 + 向量 + 元数据的表。
- **接口契约**：SQLAlchemy 表模型（注册进 `Base.metadata`，alembic 自动纳入）+ 一条新迁移。
- **数据流**：PgVectorProvider 读写此表。
- **状态管理**：表含 user_id/scope 维度，为多用户、global/personal 知识范围预留（呼应 `KnowledgeTable.scope`）。
- **错误处理**：迁移需 `CREATE EXTENSION vector`（`database.py:42` 已在 init_db 做，迁移内再确保一次）。

### 子模块 4：RAGCoordinator 接线（改动）

- **职责**：把默认 vector provider 从包装 `FakeRAGStore` 换成 `PgVectorProvider`。
- **接口契约**：`search()` / `retrieve()` / `index_documents()` 签名与返回**全部不变**。
- **状态管理**：保留把 `FakeRAGStore` 作为可注入 store 的能力（测试仍用 Fake，见下）。
- **错误处理**：单 provider 异常已被 `search()` 的 try/except 兜住（`coordinator.py:108`），机制不变。

### 子模块 5：测试兼容与新测试

- **保住旧契约**：`test_rag.py` 里依赖 `FakeRAGStore`、`Chunk/SearchResult/IndexProvider`、`retrieve()` dict 的用例**必须继续通过** → 保留 FakeRAGStore，PgVectorProvider 作为新增 provider，默认装配可通过开关切换（测试默认用 Fake，避免依赖真 PG/网络）。
- **新测试**：EmbeddingService（mock embedding）、PgVectorProvider（用 pytest 跑在 sqlite 跳过、PG 集成测试单独标记）。注意 harness 跑 pytest 必须 `< /dev/null`（见项目记忆 pytest-stdin-hang）。

---

## 第三层：子模块详细实施计划（文字描述，不含代码）

### 3.1 EmbeddingService

- **需要的函数**：
  - `__init__(config)`：接收 model 名、api_key、base_url；空字段从 settings 兜底（仿 `LLMService._apply_settings_fallback`，`llm.py:97`）。
  - `embed_many(texts: list[str]) -> list[list[float]]`：批量调用 embedding API，返回向量列表；输入空列表直接返回空。
  - `embed_one(text) -> list[float]`：调 `embed_many([text])[0]`。
  - `dim` 属性：返回所选模型维度（如 text-embedding-3-small = 1536），供建表时确定 vector 列维度。
- **字段/配置设计**：在 `settings`（`config.py`）新增 `embedding_model`（默认 text-embedding-3-small）、`embedding_dim`（默认 1536）。api_key/base_url 复用 `openai_*`。
- **关键数据结构**：无自定义结构，输入输出皆 list。
- **可观测**：复用 `observability` 记录 embedding 调用耗时（仿 LLMSpan，可选，A 阶段从简）。

### 3.2 向量表 + 迁移

- **表设计**（字段与变量）：
  - `id`（主键，自增）
  - `user_id`（int，nullable，呼应 KnowledgeTable）
  - `scope`（str，"global"/"personal"，知识范围）
  - `content`（Text，chunk 原文）
  - `embedding`（pgvector 的 Vector 类型，维度 = settings.embedding_dim）
  - `source`（str，"vector"/"ocr"/"code"，与 Chunk.source 对齐）
  - `doc_id` / `metadata`（JSON，存 file_path/page/chunk_idx 等，对齐 Chunk.metadata）
  - `created_at`
- **索引**：在 embedding 列建 pgvector 的 ivfflat / hnsw 索引（A 阶段可先不建索引，数据量小时顺序扫描即可，规划标注"数据量大后再加 hnsw"）。
- **迁移做什么**：新增一条 alembic 迁移，建上表；迁移头部确保 `CREATE EXTENSION IF NOT EXISTS vector`。`alembic/env.py` 已 import 所有表（`env.py:9`），新表模型加进 `tables.py` 后会被自动 autogenerate。
- **关键注意**：sqlite 下没有 vector 类型 → 表模型需对 sqlite 退化（vector 列在 sqlite 落为 JSON/Text），保证单测能在 sqlite 跑（不连 PG）。这点要在表定义里用 dialect 兼容处理。

### 3.3 PgVectorProvider

- **需要的函数**：
  - `__init__(embedding_service, session_factory)`：注入 embedding 与 DB 会话工厂（async_session）。
  - `index(docs: list[dict]) -> None`：取每条 `content`，批量 embed，连同 metadata 写入向量表。docs 结构沿用现有 `{"content": str, "metadata": dict}`（与 ocr.py/code_index.py 一致）。
  - `search(query, top_k) -> list[Chunk]`：embed query → PG 近邻查询取 top_k → 每行转 `Chunk`。
  - `doc_count` 属性：`SELECT count(*)`。
- **score 校准（关键设计点）**：pgvector `<=>` 返回的是**距离**（越小越近）。需转成"越大越相关"的 score。方案：`score = 1 / (1 + distance)` 或 `score = 1 - normalized_distance`。**必须校准到让现有阈值仍合理**——RetrieverAgent 的 `LOW_SCORE_THRESHOLD=0.3`（`retriever.py`）、`retrieve()` 的 `avg>2 high`（`coordinator.py:148`）。其中 `avg>2` 是为 FakeRAGStore 的整数计数设计的，转向量后这个阈值需重新定（规划标注：A 阶段把 confidence 判定改为基于归一化 score 的合理区间，并更新对应测试）。
- **async/sync 边界**：现有 `IndexProvider.search` 是同步方法，但 PG 访问是 async（`async_session`）。需处理：要么 Provider 内用同步 PG 驱动（psycopg）、要么在同步接口里跑 event loop。**这是 A 阶段最需要谨慎设计的点**——倾向给向量表单独用同步 psycopg 连接（不与业务 async_session 混用），避免 sync/async 缠绕。规划标注为"实施时第一个验证项"。
- **功能完成判据**：index 一批中文 chunk 后，search 语义相近的 query 能召回（即使字面不匹配），证明真语义检索生效。

### 3.4 RAGCoordinator 接线

- **改动点**：`_register_default_vector_provider`（`coordinator.py:54`）在"生产模式"下注册 `PgVectorProvider`，"测试/开发模式"下仍可用 FakeRAGStore。通过构造参数或 settings 开关区分（如 `settings.rag_backend = "pgvector" | "fake"`，默认 fake 以不破坏现有测试）。
- **不动**：`search` / `retrieve` / `index_documents` 主体逻辑。

### 3.5 验证目标（Goal-Driven）

```
1. EmbeddingService 能 embed 中文文本 → verify: 单测 mock 返回定长向量
2. 向量表迁移在 PG 跑通、sqlite 退化可建表 → verify: alembic upgrade + sqlite create_all
3. PgVectorProvider index+search 闭环 → verify: 集成测试，语义相近 query 命中
4. 旧 test_rag.py 全绿 → verify: pytest tests/unit/infrastructure/test_rag.py < /dev/null
5. score 阈值校准后 retrieve() 行为合理 → verify: 更新并通过相关断言
```

---

## 第四层：下阶段规划存档（本阶段不做，记录备查）

### 下阶段 ①：知识内容侧 —— 借鉴 LightRAG 双层检索

- **目标**：把知识内容建成"实体关系图 + 向量"双层，支持 local（实体邻居）+ global（全局关系）检索，解决"知识脉络串联"。
- **A 阶段已铺垫**：向量已在 pgvector（LightRAG 原生支持 PG 存图）；EmbeddingService 可复用；文档摄入接口 `IndexProvider.index` 可作为图谱抽取入口。
- **届时要做**：实体/关系抽取管线（LLM）、图存储（PG 边表）、双层检索查询、与现有 RAGCoordinator 融合（作为新 provider 或新 search mode）。
- **决策待定**：是否引 Neo4j（倾向不引，用 PG）；图抽取的 LLM 成本控制。

### 下阶段 ②：掌握度图谱时序化 + 触发复习（须用户可选可调）

- **目标**：让 `MasteryGraph` 的掌握度带时间维度，支持"随时间衰减 → 触发复习"。借鉴 graphiti 的"事实有效时间窗 + episode 溯源"。
- **用户可选可调的硬要求**（用户明确）：复习触发机制必须做成**用户可开关、参数可调、可主动调用**，不能强制自动触发。
- **届时要做**：mastery 衰减函数（基于 last_practiced_at，字段已存在 `mastery_graph.py:28`）、复习触发策略（阈值/间隔用户可配）、用户偏好存储（复用 user_profile_l3 的 preferences，`mastery_graph_store.py:49`）、触发入口（API/事件）。
- **后续讨论项**：衰减曲线形态（艾宾浩斯？线性？）、可调粒度（全局 vs 单知识点）、UI 呈现。

### 下阶段 ③：PDF 版面解析（更后）

- 教材 PDF 的版面级解析（ragflow DeepDoc 或 LightRAG-MinerU），届时按知识源实际质量需求再评估。

---

## 资产清单 + 三色（本阶段 A）

| 名字 | 归属 | 功能 | 位置 | 三色 |
|---|---|---|---|---|
| EmbeddingService | Infrastructure | 文本→向量统一入口 | `app/infrastructure/rag/embedding.py`（新） | 🔴 新建 |
| PgVectorProvider | Infrastructure | 真向量检索后端 | `app/infrastructure/rag/pgvector_provider.py`（新） | 🔴 新建 |
| 向量表模型 | Models | chunk+向量+元数据表 | `app/models/tables.py`（增表） | 🔴 新建 |
| alembic 迁移 | 迁移 | 建向量表+vector扩展 | `alembic/versions/`（新） | 🔴 新建 |
| RAGCoordinator | Infrastructure | 默认 provider 接线 | `app/infrastructure/rag/coordinator.py` | 🟡 改动 |
| settings | Core | 加 embedding/rag_backend 配置 | `app/core/config.py` | 🟡 改动 |
| FakeRAGStore | Infrastructure | 测试替身 | `app/infrastructure/rag/store.py` | 🟢 保持（测试仍用） |
| RetrieverAgent | Harness | 机械层检索 | `app/agents/retriever.py` | 🟢 保持（接口不变） |
| chromadb 依赖 | 依赖 | 暂留不用 | `pyproject.toml` | 🟢 保持（不删） |
