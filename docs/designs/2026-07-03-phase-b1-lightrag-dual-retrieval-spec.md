# 阶段 B-①：知识内容图谱（LightRAG 双层检索）Spec

> 创建日期：2026-07-03  
> 前置依赖：阶段 A（真向量检索）已完成  
> 来源追溯：`2026-06-16-rag-phase-a-plan.md` 第四层"下阶段 ①"  
> 状态：⏳ 待用户确认

---

## 第一层：模块总览

### 1.1 目标边界

**做什么**：把知识内容建成"实体关系图 + 向量"双层，支持 local（实体邻居）+ global（全局关系）检索，解决"知识脉络串联"问题（如"帮我串一下这一章的脉络"）。

**本阶段明确不做**：
- ❌ 掌握度图谱时序化（B-② 独立阶段）
- ❌ PDF 版面级解析（B-③ 独立阶段）
- ❌ 与 MasteryGraph 打通（B-② 或 C 路线，本阶段保持两图独立）

### 1.2 "知识内容图谱"与"MasteryGraph"的关键区分

| 图谱 | 节点含义 | 边含义 | 用途 |
|------|---------|--------|------|
| **知识内容图谱（本阶段新建）** | 知识点/实体本身（如"二叉搜索树"、"递归"） | 知识点间的语义关系（IS_A、PART_OF、RELATED_TO） | **检索增强**：支持"串脉络"、"找前置概念" |
| **MasteryGraph（已有）** | 学习者对知识点的**掌握度**（0-100） | 学习路径依赖（PREREQ/RELATED/CONFLICT） + confidence | **教学决策**：判断"该复习什么"、"前置薄弱" |

**两图关系**：本阶段保持独立。知识内容图谱服务于 Retriever（检索层），MasteryGraph 服务于 Curator（教学层）。未来可选打通（C 路线），但不是本阶段范围。

### 1.3 技术选型：借鉴 LightRAG 设计，自研嫁接到现有架构

| | 本方案（选它） | 备选 1：直接引入 LightRAG 库 | 备选 2：引入 Neo4j + GraphRAG |
|---|---|---|---|
| 做法 | 借鉴 LightRAG 的双层检索设计（local + global），自研实体/关系抽取 + PG 图存储 + 双层检索查询，嫁接到现有 `IndexProvider` 协议 | `pip install lightrag`，作为新 provider 接入 `RAGCoordinator` | 部署 Neo4j，用 Microsoft GraphRAG 的社区摘要方案 |
| 代价 | 中（需自研抽取 prompt + 图存储 schema + 双层检索逻辑） | 低（依赖已封装） | 高（新增 Neo4j 依赖 + GraphRAG 索引成本高） |
| 收益 | 完全贴合现有四层架构；图存储复用 PG（A 阶段已铺垫）；抽取逻辑可针对学习场景定制 | 开箱即用双层检索 | 社区摘要对"全局概括"效果好 |
| 与现状契合 | ✅ PG 已就绪（`docker-compose.yml` + `pgvector`）；`EmbeddingService` 可复用；`IndexProvider` 协议已定 | ⚠️ LightRAG 的数据模型与现有 `Chunk`/`SearchResult` 不完全对齐，需适配层 | ❌ 违背"不引 Neo4j"决策（用户 2026-06-16 明确） |
| 风险 | 抽取质量依赖 prompt 调优；双层融合权重需实验 | 框架耦合（LightRAG 更新可能影响）；增量更新机制需验证 | 运维复杂；索引成本不可控 |

**选择理由**：
1. 用户已决策"存储统一 PG + 不引 Neo4j"（2026-06-16），Neo4j 方案直接排除。
2. LightRAG 库虽开箱即用，但其数据模型（entity/relationship 的字段设计）与现有 `Chunk`/`SearchResult` 不完全对齐，引入适配层反而增加复杂度。
3. 自研方案可针对学习场景定制抽取 prompt（如强调"知识点前置关系"、"概念层级"），而非通用实体抽取。
4. A 阶段已铺垫三个基础设施前提（pgvector + EmbeddingService + IndexProvider.index），自研方案的边际成本低。

### 1.4 依赖关系与四层架构衔接

```
API 层
  ↓
Orchestration 层 (RAGCoordinator)
  ↓
Harness 层 (RetrieverAgent)
  ↓
Infrastructure 层
  ├─ PgVectorProvider (A 阶段已有，向量检索)
  ├─ GraphRetrievalProvider (🔴 本阶段新建，双层检索)
  │   ├─ EntityExtractor (🔴 新建，LLM 抽取)
  │   ├─ GraphStore (🔴 新建，PG 图存储)
  │   └─ DualRetriever (🔴 新建，local + global 融合)
  └─ EmbeddingService (A 阶段已有，复用)
```

全部改动落在 **Infrastructure 层**（`app/infrastructure/rag/`），RetrieverAgent（Harness）接口不变，符合四层单向依赖与"薄壳节点"。

---

## 第二层：子模块概述

### 2.1 EntityExtractor（新建）

- **职责**：从文本 chunk 中抽取实体（entities）和关系（relationships），输出结构化图谱数据。
- **接口契约**：`extract(text: str) -> ExtractResult`，其中 `ExtractResult = {entities: list[Entity], relationships: list[Relationship]}`。
- **数据流**：上游 = `IndexProvider.index(docs)` 调用时触发；下游 = LLM API（复用 `LLMService`）+ `GraphStore`（写入图）。
- **状态管理**：无状态，每次抽取独立。
- **错误处理**：LLM 抽取失败 → 返回空 `ExtractResult`（不阻断向量索引）；抽取质量低 → 记录日志，不抛异常。
- **关键设计点**：
  - **抽取 prompt 设计**：针对学习场景定制，强调"知识点概念"（而非通用实体如人名/地名）、"前置关系"（IS_A、PART_OF、PREREQ_OF）、"相关关系"（RELATED_TO）。
  - **token 预算控制**：借鉴 LightRAG 的 `MAX_ENTITY_TOKENS` / `MAX_RELATION_TOKENS`，避免 LLM 输出过长。
  - **增量抽取**：新增 chunk 只抽取新实体/关系，与已有图合并（实体消歧：同名实体合并，关系去重）。

### 2.2 GraphStore（新建）

- **职责**：PG 中存储实体节点 + 关系边的持久化层。
- **接口契约**：`add_entities(entities) -> None`；`add_relationships(rels) -> None`；`get_neighbors(entity_id, hop=1) -> list[Entity]`；`get_global_summary(query) -> str`。
- **数据流**：上游 = `EntityExtractor`（写入）；下游 = `DualRetriever`（读取）。
- **状态管理**：图数据持久化在 PG，Store 本身无内存态。
- **错误处理**：PG 连接失败 → 抛异常（由 `GraphRetrievalProvider` 降级到纯向量检索）。
- **关键设计点**：
  - **表结构设计**：两张新表 `knowledge_entities`（实体节点）+ `knowledge_relationships`（关系边），字段设计见第三层。
  - **Alembic 迁移**：新增一条迁移，建两张表；复用 A 阶段的 PG 连接（`pgvector/pgvector:pg16`）。
  - **实体消歧策略**：按 `entity_name`（小写归一化）+ `entity_type` 去重；冲突时保留最新抽取的版本（timestamp 覆盖）。
  - **不引 Neo4j 的理由**：PG 的 `WITH RECURSIVE` 可做 1-2 跳邻居查询（满足 local 检索需求），无需 Neo4j 的重图遍历能力。

### 2.3 DualRetriever（新建）

- **职责**：实现 LightRAG 的双层检索逻辑（local + global），融合两路结果返回 `list[Chunk]`。
- **接口契约**：`retrieve(query: str, top_k: int, mode: str = "hybrid") -> list[Chunk]`，其中 `mode` 枚举：`"local"` / `"global"` / `"hybrid"`（默认）。
- **数据流**：上游 = `GraphRetrievalProvider.search()`；下游 = `GraphStore`（图查询）+ `EmbeddingService`（query embed）+ `PgVectorProvider`（可选，hybrid 模式下融合向量结果）。
- **状态管理**：无状态，每次检索独立。
- **错误处理**：图查询失败 → 降级到纯向量检索（委托 `PgVectorProvider`）；global 摘要生成失败 → 返回空摘要（不阻断 local 结果）。
- **关键设计点**：
  - **Local 检索**：embed query → 在 `knowledge_entities` 表中找最相似的 top_k 实体 → 对每个实体做 1 跳邻居扩展（`WITH RECURSIVE` 或 Python 循环） → 拼接实体 + 邻居的描述文本。
  - **Global 检索**：embed query → 在 `knowledge_relationships` 表中找最相关的 top_k 关系 → 对每个关系涉及的实体对生成"关系摘要"（LLM 调用） → 拼接摘要文本。
  - **Hybrid 融合**：local 结果 + global 结果 + （可选）向量检索结果，按 score 加权合并（权重可配：`local_weight=0.5`, `global_weight=0.3`, `vector_weight=0.2`）。
  - **token 预算**：借鉴 LightRAG 的 `MAX_TOTAL_TOKENS`，限制送入 LLM 的 entities/relationships/text chunks 总长度（默认 4096 tokens）。

### 2.4 GraphRetrievalProvider（新建，实现 IndexProvider 协议）

- **职责**：包装 `EntityExtractor` + `GraphStore` + `DualRetriever`，作为 `RAGCoordinator` 的新 provider（`name="graph"`）。
- **接口契约**：实现 `IndexProvider`（`index(docs)` / `search(query, top_k)` / `doc_count`）。
- **数据流**：`index` → `EntityExtractor.extract` → `GraphStore.add_*`；`search` → `DualRetriever.retrieve` → 转 `Chunk`。
- **状态管理**：无内存态，图数据在 PG。
- **错误处理**：抽取/检索异常 → 返回空结果（`RAGCoordinator.search` 的 try/except 已兜住）。
- **关键设计点**：
  - **`index` 实现**：对每条 doc 调 `EntityExtractor.extract` → 写入 `GraphStore`；同时调 `PgVectorProvider.index`（向量索引也建，支持 hybrid 融合）。
  - **`search` 实现**：调 `DualRetriever.retrieve` → 转 `Chunk(content, score, source="graph", metadata)`。
  - **`doc_count` 实现**：`SELECT COUNT(DISTINCT doc_id) FROM knowledge_entities`（按文档去重计数）。

### 2.5 RAGCoordinator 接线（改动）

- **职责**：注册 `GraphRetrievalProvider` 为新 source，支持 `search(query, sources=["graph"])` 或 `sources=["vector", "graph"]`（hybrid）。
- **接口契约**：`search()` / `retrieve()` 签名不变。
- **状态管理**：保留 `PgVectorProvider` 作为默认 vector provider。
- **错误处理**：单 provider 异常已被 `search()` 的 try/except 兜住，机制不变。
- **关键设计点**：
  - **注册逻辑**：`__init__` 中除注册 vector provider 外，新增 `self._providers["graph"] = GraphRetrievalProvider(...)`。
  - **默认 sources**：`search()` 的 `sources=None` 时，默认用 `["vector"]`（保持向后兼容）；新增 `sources="all"` 或 `sources=["vector", "graph"]` 支持 hybrid。
  - **配置开关**：`settings.graph_retrieval_enabled: bool = False`（默认关闭，用户显式开启）。

### 2.6 测试兼容与新测试

- **保住旧契约**：既有 `test_rag.py` 全绿（15 passed），`GraphRetrievalProvider` 作为新增 provider，不影响既有测试。
- **新测试**：
  - `EntityExtractor` 单测（mock LLM 返回固定 entities/relationships）
  - `GraphStore` 单测（内存 sqlite 或 PG 集成测试）
  - `DualRetriever` 单测（mock GraphStore + EmbeddingService）
  - `GraphRetrievalProvider` 集成测试（真实 PG + 真实 LLM，标记 `@pytest.mark.integration`）

---

## 第三层：子模块详细实施计划（文字描述，不含代码）

### 3.1 EntityExtractor

- **需要的函数**：
  - `__init__(llm_service: LLMService, max_entity_tokens: int = 1000, max_relation_tokens: int = 1000)`：注入 LLM 服务 + token 预算。
  - `extract(text: str) -> ExtractResult`：调 LLM 抽取实体/关系，解析 JSON 输出，返回 `ExtractResult`。
  - `_parse_llm_output(raw: str) -> ExtractResult`：解析 LLM 返回的 JSON（容错：JSON 解析失败返回空结果）。
  - `_deduplicate(entities: list[Entity], existing: list[Entity]) -> list[Entity]`：实体消歧（同名 + 同 type 合并）。
- **字段/配置设计**：
  - `Entity` dataclass：`name: str`, `type: str`（"CONCEPT"/"PRINCIPLE"/"METHOD"）, `description: str`, `doc_id: str`, `chunk_id: str`。
  - `Relationship` dataclass：`from_entity: str`, `to_entity: str`, `type: str`（"IS_A"/"PART_OF"/"PREREQ_OF"/"RELATED_TO"）, `description: str`, `confidence: float`（0-1，LLM 自评）。
  - `ExtractResult` dataclass：`entities: list[Entity]`, `relationships: list[Relationship]`。
- **抽取 prompt 设计**（关键设计点）：
  - **系统 prompt**：`"你是知识图谱抽取专家。从给定文本中抽取知识点实体及其关系。实体类型限定为 CONCEPT（概念）、PRINCIPLE（原理）、METHOD（方法）。关系类型限定为 IS_A（是一种）、PART_OF（属于）、PREREQ_OF（前置知识）、RELATED_TO（相关）。输出 JSON 格式：{entities: [...], relationships: [...]}。每个实体/关系必须包含 name/type/description 字段。"`
  - **few-shot 示例**：提供 2-3 个学习场景的抽取示例（如"二叉搜索树是一种自平衡二叉树" → entity: 二叉搜索树(CONCEPT), 自平衡二叉树(CONCEPT); relationship: IS_A）。
  - **token 预算**：`max_entity_tokens` / `max_relation_tokens` 作为 prompt 的一部分传入（`"最多抽取 N 个实体、M 个关系"`）。
- **功能完成判据**：给定一段教材文本（如"递归是函数调用自身的编程技巧，常用于分治算法"），能抽取出 `递归(METHOD)`、`分治算法(METHOD)`、`PREREQ_OF(递归→分治算法)`。

### 3.2 GraphStore（PG 图存储）

- **需要的函数**：
  - `__init__(db_url: str)`：注入 PG 连接 URL（复用 A 阶段的 `postgresql+psycopg://...`）。
  - `add_entities(entities: list[Entity]) -> None`：批量 INSERT OR UPDATE（按 `name + type` 去重）。
  - `add_relationships(rels: list[Relationship]) -> None`：批量 INSERT OR UPDATE（按 `from_entity + to_entity + type` 去重）。
  - `get_neighbors(entity_name: str, hop: int = 1) -> list[Entity]`：1-hop 邻居查询（`WITH RECURSIVE` 或 Python 循环）。
  - `get_global_summary(query: str, top_k: int = 5) -> str`：找最相关的 top_k 关系，生成摘要文本（LLM 调用）。
  - `find_similar_entities(query_embedding: list[float], top_k: int) -> list[Entity]`：向量近邻查询（复用 `pgvector` 的 `<=>` 操作符）。
- **表结构设计**（字段与变量）：
  - **`knowledge_entities` 表**：
    - `id`（主键，自增）
    - `name`（str，实体名称，如"二叉搜索树"）
    - `type`（str，实体类型，如"CONCEPT"）
    - `description`（Text，实体描述）
    - `embedding`（pgvector 的 Vector(2048)，用于向量近邻查询）
    - `doc_id`（str，来源文档 ID）
    - `chunk_id`（str，来源 chunk ID）
    - `created_at`（timestamp）
    - `updated_at`（timestamp）
    - **索引**：`(name, type)` 唯一约束（实体消歧）；`embedding` 列可选建 HNSW 索引（数据量大后）。
  - **`knowledge_relationships` 表**：
    - `id`（主键，自增）
    - `from_entity`（str，外键 → `knowledge_entities.name`）
    - `to_entity`（str，外键 → `knowledge_entities.name`）
    - `type`（str，关系类型，如"PREREQ_OF"）
    - `description`（Text，关系描述）
    - `confidence`（float，0-1，LLM 自评）
    - `doc_id`（str，来源文档 ID）
    - `created_at`（timestamp）
    - **索引**：`(from_entity, to_entity, type)` 唯一约束（关系去重）；`from_entity` / `to_entity` 各建普通索引（加速邻居查询）。
- **Alembic 迁移**：新增一条迁移 `202607XX_add_knowledge_graph_tables.py`，建两张表；迁移头部确保 `CREATE EXTENSION IF NOT EXISTS vector`（A 阶段已做过，幂等操作）。
- **SQLite 兼容**：`embedding` 列在 sqlite 下退化为 TEXT（存 JSON），与 A 阶段的 `VectorChunkTable` 策略一致。
- **功能完成判据**：`add_entities` + `get_neighbors` 闭环测试通过（插入 3 个实体 + 2 条关系，查询 1-hop 邻居返回正确结果）。

### 3.3 DualRetriever（双层检索）

- **需要的函数**：
  - `__init__(graph_store: GraphStore, embedding_service: EmbeddingService, llm_service: LLMService, local_weight: float = 0.5, global_weight: float = 0.3, vector_weight: float = 0.2, max_total_tokens: int = 4096)`：注入依赖 + 融合权重 + token 预算。
  - `retrieve(query: str, top_k: int, mode: str = "hybrid") -> list[Chunk]`：主入口，按 mode 分发到 `_retrieve_local` / `_retrieve_global` / `_retrieve_hybrid`。
  - `_retrieve_local(query: str, top_k: int) -> list[Chunk]`：embed query → `graph_store.find_similar_entities` → 对每个实体做 1-hop 扩展 → 拼接实体 + 邻居描述 → 返回 `Chunk`。
  - `_retrieve_global(query: str, top_k: int) -> list[Chunk]`：embed query → `graph_store.get_global_summary` → 返回 `Chunk`。
  - `_retrieve_hybrid(query: str, top_k: int) -> list[Chunk]`：调 `_retrieve_local` + `_retrieve_global` + （可选）`PgVectorProvider.search` → 按权重融合 → 去重 → 返回 top_k。
  - `_merge_results(local_chunks: list[Chunk], global_chunks: list[Chunk], vector_chunks: list[Chunk]) -> list[Chunk]`：融合逻辑（score 加权：`final_score = local_weight * local_score + global_weight * global_score + vector_weight * vector_score`）。
- **Local 检索详细流程**：
  1. `query_embedding = embedding_service.embed_one(query)`
  2. `similar_entities = graph_store.find_similar_entities(query_embedding, top_k=top_k)`
  3. 对每个 entity 调 `graph_store.get_neighbors(entity.name, hop=1)` → 收集邻居
  4. 拼接文本：`chunk_content = f"{entity.name}: {entity.description}\n邻居: {[n.name for n in neighbors]}"`
  5. 计算 score：`score = entity.embedding_similarity`（pgvector `<=>` 结果转 `1/(1+distance)`）
  6. 返回 `Chunk(content=chunk_content, score=score, source="graph", metadata={"entity": entity.name, "neighbors": [...]})`
- **Global 检索详细流程**：
  1. `summary_text = graph_store.get_global_summary(query, top_k=top_k)`（内部调 LLM 生成摘要）
  2. 计算 score：`score = llm_self_rated_relevance`（LLM 在生成摘要时自评相关度，0-1）
  3. 返回 `Chunk(content=summary_text, score=score, source="graph", metadata={"type": "global_summary"})`
- **Hybrid 融合详细流程**：
  1. `local_chunks = _retrieve_local(query, top_k)`
  2. `global_chunks = _retrieve_global(query, top_k)`
  3. `vector_chunks = PgVectorProvider.search(query, top_k)`（可选，仅当 `vector_weight > 0`）
  4. `_merge_results`：对每个 chunk 计算 `final_score`，按 score 降序排列，取 top_k。
  5. 去重：相同 `content` 只保留最高 `final_score` 的 chunk。
- **token 预算控制**：
  - `_retrieve_local`：限制 `len(entities) * avg_entity_tokens + len(neighbors) * avg_neighbor_tokens <= max_total_tokens * 0.5`（local 占 50% 预算）。
  - `_retrieve_global`：限制 `len(relationships) * avg_relation_tokens <= max_total_tokens * 0.3`（global 占 30% 预算）。
  - 剩余 20% 预算留给向量检索结果（hybrid 模式）。
- **功能完成判据**：给定 query "什么是二叉搜索树的前置知识"，local 检索能返回 `二叉搜索树` 实体 + 邻居 `二叉树`、`排序算法`；global 检索能返回"二叉搜索树是二叉树的一种特化，常用于高效查找"的摘要。

### 3.4 GraphRetrievalProvider（IndexProvider 实现）

- **需要的函数**：
  - `__init__(entity_extractor: EntityExtractor, graph_store: GraphStore, dual_retriever: DualRetriever, pgvector_provider: PgVectorProvider)`：注入依赖。
  - `index(docs: list[dict]) -> None`：对每条 doc 调 `entity_extractor.extract` → `graph_store.add_*`；同时调 `pgvector_provider.index(docs)`（向量索引也建）。
  - `search(query: str, top_k: int = 5) -> list[Chunk]`：调 `dual_retriever.retrieve(query, top_k, mode="hybrid")` → 返回 `Chunk`。
  - `doc_count` property：`SELECT COUNT(DISTINCT doc_id) FROM knowledge_entities`。
- **`name` 属性**：`"graph"`（与 `"vector"` / `"ocr"` / `"code"` 并列）。
- **错误处理**：
  - `index` 中 `entity_extractor.extract` 失败 → 跳过该 doc，不阻断后续；记录日志。
  - `search` 中 `dual_retriever.retrieve` 失败 → 降级到 `pgvector_provider.search(query, top_k)`（纯向量检索）。
- **功能完成判据**：`index` 一批教材 chunk 后，`search` "二叉搜索树的前置知识" 能召回相关实体 + 关系摘要。

### 3.5 RAGCoordinator 接线

- **改动点**：`__init__` 中新增 `self._providers["graph"] = GraphRetrievalProvider(...)`（仅当 `settings.graph_retrieval_enabled=True`）。
- **不动**：`search` / `retrieve` / `index_documents` 主体逻辑。
- **新增配置**：`settings.graph_retrieval_enabled: bool = False`（默认关闭）。
- **功能完成判据**：`RAGCoordinator.search(query, sources=["graph"])` 能返回 graph provider 的结果；`sources=["vector", "graph"]` 能融合两路结果。

### 3.6 验证目标（Goal-Driven）

```
1. EntityExtractor 能从教材文本抽取实体/关系 → verify: 单测 mock LLM 返回固定 JSON
2. GraphStore 能写入/读取 PG 图数据 → verify: alembic upgrade + sqlite create_all + 集成测试
3. DualRetriever local/global/hybrid 三路检索逻辑正确 → verify: 单测 mock GraphStore + EmbeddingService
4. GraphRetrievalProvider index+search 闭环 → verify: 集成测试，真实 PG + 真实 LLM
5. RAGCoordinator 注册 graph provider 后既有测试不破 → verify: pytest tests/unit/infrastructure/test_rag.py < /dev/null
6. 端到端：index 教材 → search "串一下这章脉络" → 返回 global 摘要 + local 实体邻居 → verify: 集成测试
```

---

## 第四层：决策待定项（本阶段不拍板，记录备查）

### 4.1 抽取 prompt 的 few-shot 示例数量

- **待定**：2-3 个示例 vs 5-10 个示例。
- **trade-off**：示例越多，抽取质量越稳定，但 prompt token 成本越高（每个示例约 200-300 tokens）。
- **建议**：先用 2-3 个示例做 MVP，根据抽取质量评估是否增加。

### 4.2 Local 检索的跳数（hop）

- **待定**：1-hop vs 2-hop。
- **trade-off**：1-hop 查询快（PG `JOIN` 一次），2-hop 能召回更远的前置知识（但查询慢，且可能引入噪声）。
- **建议**：MVP 用 1-hop，后续根据用户反馈决定是否扩展到 2-hop。

### 4.3 Hybrid 融合的权重配置

- **待定**：`local_weight=0.5, global_weight=0.3, vector_weight=0.2` 是否合理。
- **trade-off**：权重影响检索结果的偏向性（local 偏细节事实，global 偏概括摘要，vector 偏语义相似）。
- **建议**：MVP 用默认权重，后续做 A/B 测试或用户调研调优。

### 4.4 实体消歧的粒度

- **待定**：按 `name + type` 去重 vs 按 `name + type + description_embedding` 去重（embedding 相似度 > 0.9 视为同一实体）。
- **trade-off**：前者简单但可能漏消歧（如"二叉树"在不同上下文指代不同概念）；后者更准但计算成本高。
- **建议**：MVP 用 `name + type` 去重，后续根据消歧质量评估是否引入 embedding 相似度。

---

## 资产清单 + 三色（本阶段 B-①）

| 名字 | 归属 | 功能 | 位置 | 三色 |
|---|---|---|---|---|
| EntityExtractor | Infrastructure | 文本→实体/关系抽取 | `app/infrastructure/rag/entity_extractor.py`（新） | 🔴 新建 |
| GraphStore | Infrastructure | PG 图存储 | `app/infrastructure/rag/graph_store.py`（新） | 🔴 新建 |
| DualRetriever | Infrastructure | local + global 双层检索 | `app/infrastructure/rag/dual_retriever.py`（新） | 🔴 新建 |
| GraphRetrievalProvider | Infrastructure | IndexProvider 实现 | `app/infrastructure/rag/graph_provider.py`（新） | 🔴 新建 |
| knowledge_entities 表 | Models | 实体节点表 | `app/models/tables.py`（增表） | 🔴 新建 |
| knowledge_relationships 表 | Models | 关系边表 | `app/models/tables.py`（增表） | 🔴 新建 |
| alembic 迁移 | 迁移 | 建两张图表 | `alembic/versions/`（新） | 🔴 新建 |
| RAGCoordinator | Infrastructure | 注册 graph provider | `app/infrastructure/rag/coordinator.py` | 🟡 改动 |
| settings | Core | 加 graph_retrieval_enabled 配置 | `app/core/config.py` | 🟡 改动 |
| PgVectorProvider | Infrastructure | 向量检索（hybrid 融合时复用） | `app/infrastructure/rag/pgvector_provider.py` | 🟢 保持 |
| EmbeddingService | Infrastructure | 文本→向量（复用） | `app/infrastructure/rag/embedding.py` | 🟢 保持 |
| RetrieverAgent | Harness | 机械层检索 | `app/agents/retriever.py` | 🟢 保持（接口不变） |

---

## 附录：与 LightRAG 的设计对照

| LightRAG 设计 | 本方案实现 | 差异原因 |
|---|---|---|
| 双层检索（local + global） | ✅ 实现（`DualRetriever`） | 核心设计理念一致 |
| 四种查询模式（naive/local/global/hybrid/mix） | ⚠️ 简化为三种（local/global/hybrid） | `naive` 模式（纯向量）已由 `PgVectorProvider` 覆盖，无需重复 |
| 增量更新（无需全量重算） | ✅ 实现（`GraphStore.add_*` 用 INSERT OR UPDATE） | 实体/关系按 `name+type` / `from+to+type` 去重，新增只追加 |
| token 预算控制（MAX_ENTITY_TOKENS 等） | ✅ 实现（`max_entity_tokens` / `max_relation_tokens` / `max_total_tokens`） | 直接借鉴 |
| 多后端（PG/Neo4j/MongoDB） | ⚠️ 仅支持 PG | 用户已决策"存储统一 PG"，无需多后端 |
| 多模态解析（MinerU/Docling） | ❌ 本阶段不做 | 属于 B-③（PDF 版面解析）范围 |
| 社区摘要（GraphRAG 风格） | ❌ 本阶段不做 | global 检索用 LLM 生成关系摘要，不做预生成社区摘要（成本高） |
