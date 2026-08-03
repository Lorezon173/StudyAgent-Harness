# Spec 修改建议：阶段 B-① 知识内容图谱（LightRAG 双层检索）

> **状态**：🟡 Review 进行中（草稿，持续追加）
> **来源 Spec**：[docs/designs/2026-07-03-phase-b1-lightrag-dual-retrieval-spec.md](../designs/2026-07-03-phase-b1-lightrag-dual-retrieval-spec.md)
> **来源 Spec 创建日期**：2026-07-03
> **Review 起始日期**：2026-07-16
> **Review 方式**：人工逐条提问 → Claude 检索事实回答 → 沉淀修改建议
> **用途**：辅助后续修改原 Spec；本文档**不直接改动**原 Spec，仅记录建议与依据。

---

## 使用说明

- 本文档**只记录修改建议与事实依据**，原 Spec 的实际修改在 review 完成后另行进行。
- 每条建议固定字段：
  - **编号**：M1、M2……（递增）
  - **严重程度**：🔴 严重（阻断/事实错误）/ 🟡 中等（设计瑕疵）/ 🟢 建议（优化）
  - **原 Spec 位置**：章节号或行号
  - **问题**：事实性的问题描述
  - **事实依据**：`file:line` 或文档链接（核实过的才写）
  - **建议改法**：具体怎么改
  - **状态**：⏳ 待讨论 / ✅ 已确认 / ❌ 否决
- 待原 Spec 修改落地后，本文档可归档到 `docs/designs/archive/` 或保留作回溯。

---

## 修改建议清单

> 以下条目随 review 进展逐条追加，按编号排序。

### M1：Curator 被错标为"教学层"，且 MasteryGraph 用途描述混入 Orchestrator 职责

- **严重程度**：🔴 严重（事实性错误 + 概念误导）
- **原 Spec 位置**：§1.2「知识内容图谱与 MasteryGraph 的关键区分」表格行 + 紧随其后的"两图关系"段落（约第 23-28 行）
- **问题**：
  1. 原 Spec 写"MasteryGraph 服务于 Curator（**教学层**）"——Curator 实际属于**结构层（图谱）**，不是教学层；教学主体是 Tutor（生成层）。
  2. 表格中 MasteryGraph 的"用途"列写"**教学决策**：判断'该复习什么'、'前置薄弱'"——把两件事混了：Curator 只产出"前置薄弱"这个**结构观察**（`GraphPrereqWeakDetected`），"该复习什么"的**教学路由决策**是 Orchestrator 做的。
  3. 该节本意是"区分两图分别服务于哪个子系统"，错标反而模糊了区分，并可能让读者误以为 Curator 与 Tutor 功能重叠。
- **事实依据**：
  - `app/specs/agents/curator.md:1-3`：Curator = "维护用户画像与掌握点知识图谱，只判结构层（前置薄弱），不判文本语义"
  - `app/specs/agents/tutor.md:1-3`：Tutor = "教学主体，只生成不评判"
  - `Learned/2026-07-14-StudyAgent多Agent协作架构.md:44-52`（七角色职能层表）：Curator=结构层，Tutor=生成层
  - `Learned/2026-07-14-StudyAgent多Agent协作架构.md:349-507`（Q6 Curator vs Critic 边界）：五职能正交，Curator 不调 LLM、不产教学内容
  - `Learned/2026-07-14-StudyAgent多Agent协作架构.md:175-186`（规则路由表）：`regress_to_prereq` 等教学路由动作由 Orchestrator 规则引擎决策，非 Curator
- **建议改法**：
  - "两图关系"句：把"MasteryGraph 服务于 Curator（教学层）"改为"MasteryGraph 服务于 Curator（**结构层·掌握度图谱维护**）"，与上句"知识内容图谱服务于 Retriever（检索层）"形成准确的"检索层 vs 结构层"对照。
  - 表格 MasteryGraph 用途列：从"教学决策：判断'该复习什么'、'前置薄弱'"改为"**结构层判断**：维护掌握度、检测前置薄弱（产出观察事件喂给 Orchestrator 做教学路由）"。
  - （可选）在表格的"图谱"列补一句点明 MasteryGraph 由 Curator 维护、Curator 不做教学内容生成，进一步消除与 Tutor 的重叠联想。
- **状态**：⏳ 待用户确认

### M2：knowledge_relationships 外键引用非唯一列 name，PG 无法建 FK

- **严重程度**：🔴 严重（表结构错误，不可实现）
- **原 Spec 位置**：§3.2 `knowledge_relationships` 表
- **问题**：spec 称 `from_entity`/`to_entity` 外键 → `knowledge_entities.name`，但 `name` 单独**不唯一**（唯一约束是 `(name, type)` 联合，主键是自增 `id`）。PG 不允许外键引用非唯一列，该 FK 无法创建。
- **事实依据**：spec §3.2 表设计 vs [tables.py:64-89](app/models/tables.py#L64-L89)（现有 `MasteryEdgeTable` 用 `from_topic`/`to_topic` 字符串引用、不建 FK）
- **建议改法**：外键改为引用主键 `id`（推荐），或参照 `MasteryEdgeTable` 用字符串引用不建 FK。若坚持按 name，须给 name 加单独唯一约束——但这与「同名不同 type 视为不同实体」的消歧设计冲突，不推荐。
- **状态**：⏳ 待用户确认

### M3：knowledge_entities 表缺 user_id/scope，未讨论多用户隔离

- **严重程度**：🔴 严重（方向性遗漏）
- **原 Spec 位置**：§3.2 `knowledge_entities` 表
- **问题**：表无 `user_id`/`scope`，spec 全文未讨论图谱的多用户隔离。但项目是多用户体系（`users` 表 + JWT + `user_id` 贯穿 mastery_nodes/vector_chunks/knowledge）。图谱若全局共享需显式声明理由，否则须按用户/范围隔离。
- **事实依据**：spec §3.2 vs [tables.py:104-105](app/models/tables.py#L104-L105)（`VectorChunkTable` 有 `user_id`+`scope`）、[tables.py:66](app/models/tables.py#L66)（`MasteryNodeTable.user_id` 为主键之一）
- **建议改法**：明确二选一——(a) 知识内容图谱**全局共享**（所有用户共用一张教材图谱），显式声明并说明 doc_id 如何区分来源；或 (b) 按用户隔离，加 `user_id`+`scope`（对齐 `VectorChunkTable`）。需结合产品语义决策。
- **状态**：⏳ 待用户确认

### M4：GraphStore 遗漏 sync/async 边界约束

- **严重程度**：🔴 严重（关键基础设施约束缺失，实现必踩坑）
- **原 Spec 位置**：§2.2 / §3.2 GraphStore
- **问题**：`IndexProvider.search` 是**同步**方法，GraphStore 的检索方法会被 DualRetriever 在同步链路调用，**必须用同步 psycopg 连接**，不能混用 asyncpg。A 阶段 `PgVectorProvider` 专门处理了这个坑，spec 对 GraphStore 只字未提。
- **事实依据**：[coordinator.py:35](app/infrastructure/rag/coordinator.py#L35)（search 同步）+ [pgvector_provider.py:8-10,39-58](app/infrastructure/rag/pgvector_provider.py#L8-L10)（`_make_sync_db_url` 把 asyncpg 转 psycopg + 同步 `_get_conn`）
- **建议改法**：§2.2/§3.2 显式声明 GraphStore 用同步 psycopg 连接（仿 `PgVectorProvider._make_sync_db_url` + `_get_conn`），禁止混用 asyncpg；在依赖里说明复用同步驱动。
- **状态**：⏳ 待用户确认

### M5：search(sources=None) 默认语义与 spec 设想相反

- **严重程度**：🟡 中等（与现有代码不符，"默认关闭"设计不成立）
- **原 Spec 位置**：§2.5 / §3.5
- **问题**：spec 称 `search(sources=None)` 默认用 `["vector"]`（向后兼容）；实际 coordinator 是**检索所有已注册 provider**。注册了 graph 后，默认检索会自动带上 graph，spec 设想的「默认关闭」不成立。
- **事实依据**：[coordinator.py:100-103](app/infrastructure/rag/coordinator.py#L100-L103)（`target = sources if sources else list(self._providers.keys())`）
- **建议改法**：二选一——(a) 改 coordinator 默认逻辑（sources=None → 只用 vector）；或 (b) spec 调整为"按需注册 graph provider"（不默认注册，启用时才 `register_provider`）。需与 M11 配置开关联动。
- **状态**：⏳ 待用户确认

### M6：§1.4「全部改动落 Infrastructure 层」与资产清单自相矛盾

- **严重程度**：🟡 中等（文档自洽性）
- **原 Spec 位置**：§1.4 vs §资产清单
- **问题**：§1.4 称全部改动落在 Infrastructure 层，但资产清单自列 `settings`（Core，🟡 改动）+ `RAGCoordinator`（🟡 改动）。
- **建议改法**：§1.4 改为"主要改动落 Infrastructure 层，另含 Core(config) 接线与 RAGCoordinator 注册"，与资产清单一致。
- **状态**：⏳ 待用户确认

### M7：RetrieverAgent 被标为 Harness 层，物理却在 app/agents/

- **严重程度**：🟡 中等（层级标注误导定位）
- **原 Spec 位置**：§1.4 架构图 + §资产清单 RetrieverAgent 行
- **问题**：spec 把 RetrieverAgent 标为 Harness 层，但它在 `app/agents/`（与 `app/harness/` 平级），读者会去 `app/harness/` 下找而扑空。
- **事实依据**：[retriever.py:24](app/agents/retriever.py#L24)（`app/agents/retriever.py`）
- **建议改法**：把 RetrieverAgent 归属改为"Agent 层（`app/agents/`）"；§1.4 图里若要体现，补上 Agent 层或在 Harness 层注解说明"Agent 类物理在 app/agents/"。资产清单"归属"列同步修正。
- **状态**：⏳ 待用户确认

### M8：GraphStore 调 LLM，持久化层职责越界

- **严重程度**：🟡 中等（分层纯净性）
- **原 Spec 位置**：§2.2 / §3.2 `get_global_summary`
- **问题**：GraphStore 的 `get_global_summary` 调 LLM 生成摘要，引入 LLM 依赖，破坏 §2.2 自述的「Store 无内存态、纯持久化层」定位。
- **建议改法**：把 LLM 摘要生成上移到 `DualRetriever._retrieve_global`；GraphStore 只保留纯数据查询（`get_relationships`/`find_similar_entities`/`get_neighbors`），不持有 LLMService。
- **状态**：⏳ 待用户确认

### M9：双重索引风险（graph provider 与独立 vector provider 重复写向量表）

- **严重程度**：🟡 中等
- **原 Spec 位置**：§2.4 / §3.4 GraphRetrievalProvider.index
- **问题**：GraphRetrievalProvider 注入 `pgvector_provider` 且 index 时调它写 `vector_chunks`；但 coordinator 默认还注册独立 `"vector"` provider。同一份文档可能被两条路径重复写入向量表。§2.5 又说"保留 PgVectorProvider 作默认"，三者冲突。
- **事实依据**：[coordinator.py:54-84](app/infrastructure/rag/coordinator.py#L54-L84)（默认注册 vector）vs spec §2.4/§3.4
- **建议改法**：明确关系——(a) graph provider 不再内部调 pgvector.index，hybrid 融合时由 DualRetriever 调独立 PgVectorProvider 实例；或 (b) 注册 graph 时移除默认 vector provider，由 graph 统一兜底向量索引。二选一。
- **状态**：⏳ 待用户确认

### M10：实体消歧职责分散在 EntityExtractor 与 GraphStore 两层

- **严重程度**：🟡 中等
- **原 Spec 位置**：§2.1 / §3.1 / §3.2
- **问题**：EntityExtractor 有 `_deduplicate(entities, existing)`（§3.1），GraphStore 又用 `INSERT OR UPDATE by name+type` 去重（§3.2）。两层都做消歧，主从未澄清，可能重复或打架。
- **建议改法**：明确 GraphStore 为消歧唯一权威（写入时 `INSERT OR UPDATE by name+type` 去重）；EntityExtractor 不做 `_deduplicate`，或只做轻量"明显重复"过滤。
- **状态**：⏳ 待用户确认

### M11：配置开关风格冲突（rag_backend 枚举 vs graph_retrieval_enabled bool）

- **严重程度**：🟡 中等
- **原 Spec 位置**：§2.5 / §3.5
- **问题**：现有 `rag_backend` 是单选枚举（`fake`/`pgvector`）；spec 新增 `graph_retrieval_enabled` 是叠加 bool。一个互斥一个叠加，未协调。
- **事实依据**：[config.py:21](app/core/config.py#L21)（`rag_backend: str = "fake"`）
- **建议改法**：二选一——(a) 扩 `rag_backend` 枚举（`fake`/`pgvector`/`graph`/`hybrid`），保持单选风格；或 (b) 保留 bool 但说明它与 `rag_backend` 的叠加关系。推荐 (a)，与现有风格一致。需与 M5 联动。
- **状态**：⏳ 待用户确认

### M12：embedding 维度硬编码 2048，建议对齐 settings.embedding_dim

- **严重程度**：🟢 建议
- **原 Spec 位置**：§3.2 `knowledge_entities.embedding Vector(2048)`
- **问题**：硬编码 2048 当前值正确，但换 embedding 模型时维度会漂移。
- **事实依据**：[config.py:23](app/core/config.py#L23)（`embedding_dim: int = 2048`）、[tables.py:107](app/models/tables.py#L107)（`VectorChunkTable` 也是 `Vector(2048)`）。另：README:297 写 `Vector(1536)` 与代码 `Vector(2048)` 不符（非本 spec，另记）。
- **建议改法**：建表/迁移时读取 `settings.embedding_dim`，不硬编码。
- **状态**：⏳ 待用户确认

### M13：Chunk.source 需扩展 "graph" 枚举值

- **严重程度**：🟢 建议
- **原 Spec 位置**：§3.3（返回 `source="graph"`）
- **问题**：`Chunk.source` 现有注释只列 `"vector"/"ocr"/"code"`，新值 `"graph"` 未同步。
- **事实依据**：[coordinator.py:12](app/infrastructure/rag/coordinator.py#L12)
- **建议改法**：扩展注释为 `"vector" | "ocr" | "code" | "graph"`。
- **状态**：⏳ 待用户确认

### M14：doc_count 语义不一致（DISTINCT doc_id vs COUNT(*)）

- **严重程度**：🟢 建议
- **原 Spec 位置**：§3.4 `doc_count`
- **问题**：graph 用 `COUNT(DISTINCT doc_id)`，现有 PgVectorProvider 用 `COUNT(*)`，两 provider 共存时 doc_count 含义不统一。
- **事实依据**：[pgvector_provider.py:186](app/infrastructure/rag/pgvector_provider.py#L186)
- **建议改法**：统一语义，或在 GraphRetrievalProvider 文档说明其 doc_count 与 vector 不同。
- **状态**：⏳ 待用户确认

### M15：注册 provider 应用公开方法 register_provider，勿操作私有字段

- **严重程度**：🟢 建议
- **原 Spec 位置**：§2.5 / §3.5
- **问题**：spec 直接 `self._providers["graph"] = ...`（私有字段）；coordinator 已有公开方法。
- **事实依据**：[coordinator.py:88-90](app/infrastructure/rag/coordinator.py#L88-L90)（`register_provider(provider)`）
- **建议改法**：用 `coordinator.register_provider(GraphRetrievalProvider(...))`。
- **状态**：⏳ 待用户确认

### M16：§2.1 称"抽取质量低→记日志"，但全文无"质量低"的判断标准

- **严重程度**：🟡 中等（可实施性缺口）
- **原 Spec 位置**：§2.1 错误处理 + §3.1
- **问题**：spec 说"抽取质量低 → 记录日志，不抛异常"，但全文未定义"质量低"的可执行判定标准，无法落地实现。
- **建议改法**：明确至少一个判定规则。候选（spec 未写）：抽取数量异常（0 或超阈值）、`Relationship.confidence < 阈值`（§3.1 已有该字段）、JSON 缺必填字段、关系端点不在实体表（悬挂关系）、实体描述空/过短。
- **状态**：⏳ 待用户确认

### M17：EntityExtractor 应复用 LLMService.invoke_json，删除自写 _parse_llm_output

- **严重程度**：🟢 建议（减少重复造轮子）
- **原 Spec 位置**：§3.1 `_parse_llm_output`
- **问题**：spec 设计 `_parse_llm_output(raw) -> ExtractResult` 自己 `json.loads` + 容错；但项目已有 `LLMService.invoke_json`（调 invoke + 去 ```` ``` ```` 包裹 + `json.loads`，返回 dict），是 Conductor/Critic 的标准方式，比自写解析更鲁棒。
- **事实依据**：[llm.py:168-178](app/infrastructure/llm.py#L168-L178)（`invoke_json`）+ [conductor.py:33](app/agents/conductor.py#L33)（Conductor 调用实例）
- **建议改法**：`extract` 改用 `llm.invoke_json` 得 dict，再用 `_to_extract_result(dict)` 做字段映射 + 缺字段容错（构造 Entity/Relationship）；删 `_parse_llm_output`。注意 `invoke_json` 失败抛异常，`extract` 需外层 try/except（见 M18）。
- **状态**：✅ 已确认（用户要求复用 `invoke_json`）

### M18：补全 LLM 调用失败的降级链（spec 仅笼统覆盖）

- **严重程度**：🟡 中等（可实施性）
- **原 Spec 位置**：§2.1 错误处理 + §3.1
- **问题**：spec 只笼统说"LLM 抽取失败→空 ExtractResult"，未区分"LLM 调用失败（网络/超时/API）"与"JSON 解析失败"，也没交代 LLMService 层已有的重试/fallback，降级链不完整。
- **事实依据**：[llm.py:140-166](app/infrastructure/llm.py#L140-L166)（`invoke` 的重试/fallback：`max_retries+1` 次指数退避 → 切 `fallback_model` → 都失败 `raise`）
- **建议改法**：spec 显式写三层降级——① LLM 调用失败由 `LLMService.invoke` 内部重试（默认 3 次指数退避）+ fallback_model 兜；② 仍失败 / JSON 解析失败（`invoke_json` 抛异常）由 `extract` 外层 try/except 捕获→返回空 `ExtractResult`；③ 不阻断向量索引（`PgVectorProvider` 照常 index）。复用 `invoke_json` 后 ①② 统一由 extract 一个 try/except 兜。
- **状态**：✅ 已确认（用户要求补全此降级链）

### M19：明确“两张图”不是同一图，B-① 内容图是教材知识结构资产

- **严重程度**：🔴 严重（概念与数据归属边界）
- **原 Spec 位置**：§1.1 / §1.2
- **问题**：现有 MasteryGraph 与 B-① 内容图都含“知识点/前置关系”，容易被误认为同一张图或前者已经覆盖后者。实际上 MasteryGraph 是按 `user_id` 隔离的学习者掌握状态图；B-① 计划的是教材/知识库级内容资产。两者写入源、状态、消费者、生命周期均不同。
- **事实依据**：
  - [mastery_graph.py:23-59](app/harness/mastery_graph.py#L23-L59)：MasteryNode 保存 mastery、练习次数、混淆、理由，MasteryGraph 持有 user_id。
  - [mastery_graph.py:82-156](app/harness/mastery_graph.py#L82-L156)：掌握度更新与前置薄弱检测。
  - 原 Spec §1.2：内容图服务 Retriever，MasteryGraph 服务 Curator，本阶段独立。
- **建议改法**：把 §1.2 扩成完整边界表，至少增加：数据归属（knowledge_base/document_version vs user_id）、写入源（教材摄入 vs 学习交互）、消费者（Retriever vs Curator）、节点动态状态、生命周期、权限/删除策略。明确禁止共表或把自动内容关系直接当作用户掌握关系。
- **状态**：⏳ 待用户确认

### M20：补齐“教材结构”的确定性层级，否则当前仅是概念实体关系图

- **严重程度**：🟡 中等（目标语义不完整）
- **原 Spec 位置**：§1.1 / §2.1 / §3.1-3.3
- **问题**：B-① 可以学习广义教材知识结构，但当前只定义 CONCEPT/PRINCIPLE/METHOD 与 IS_A/PART_OF/PREREQ_OF/RELATED_TO；未定义 Document/Chapter/Section/Chunk、标题路径、页码和章节顺序。因此它是“概念实体关系图”，不能自动等同于完整教材目录/章节结构图。
- **建议改法**：明确产品语义二选一：① MVP 只做概念关系图，并把名称/目标写准确；或 ② 同时保留确定性文档层级 Document→Chapter→Section→Chunk，记录 `title_path/page_range/order`，目录解析得到的 PART_OF 与 LLM 推断关系分开标来源。
- **状态**：⏳ 待用户确认

### M21：B-① 前必须设 Gate 0——先打通无图教材 RAG 闭环

- **严重程度**：🔴 严重（前置依赖缺失，当前实现图无法抵达用户价值）
- **原 Spec 位置**：§1.1 前置依赖 / §1.4 数据流 / §3.5 / §3.6
- **问题**：Spec 只写“阶段 A 真向量检索已完成”，但仓库当前没有完整生产教材链路：`/api/knowledge` 仅维护内存 name/description；没有上传→解析→切块→`index_documents`；在线 Orchestrator 发 Retriever 的 `ActionRequested` 只含 action/target，不含 query/scope/purpose，Retriever 会取空 query。此时先做图会形成“图建好但在线教学不用”的孤岛。
- **事实依据**：
  - [knowledge_store.py:4-24](app/infrastructure/storage/knowledge_store.py#L4-L24)：当前仅内存 CRUD 元数据。
  - [coordinator.py:135-139](app/infrastructure/rag/coordinator.py#L135-L139)：虽有 `index_documents`，但未形成 API 摄入调用链。
  - [orchestrator.py:149-154](app/harness/orchestrator.py#L149-L154)：ActionRequested 只有 action/target。
  - [retriever.py:44-47](app/agents/retriever.py#L44-L47)：缺失字段默认 query=""、sources=None、purpose=None。
- **建议改法**：将阶段重构为 Gate 0 无图闭环 → Gate 1 最小图 pilot → Gate 2 条件性生产化。Gate 0 验收：代表教材可导入/解析/结构切块/持久化索引；chat 传非空 query + knowledge_base_id/scope + purpose=teaching；RetrievedEvidence 真正进入教学生成/质量评估；provider 错误可观测。
- **状态**：⏳ 待用户确认

### M22：ROI 应标为“条件性”，先用强无图基线与最小图 pilot 验证

- **严重程度**：🔴 严重（立项判据缺失）
- **原 Spec 位置**：§1.1 目标、§1.3 技术选型、§3.6 验证目标、§4 待定项
- **问题**：Spec 直接选择完整自研图能力，但没有证明图相对强无图 RAG 的边际价值。图对跨章节、多跳前置、概念辨析、全局导航可能有中高 ROI；对局部定义、公式定位、短教材、频繁改版材料通常低。当前无法无条件判“高 ROI”。
- **建议改法**：A=强无图基线（混合召回+标题路径+章节 scope+父子/邻接 chunk+统一 reranker）；B=A+最小自动图（50–150 核心概念，仅 PREREQ_OF/PART_OF/RELATED_TO，每边绑定原文证据，最多 1–2 hop）；推荐加 B-oracle 人工校验图。固定同教材、chunk、embedding、生成模型、prompt、top-k、上下文 token 预算和运行顺序。只有 B 在结构型查询和教学结果上稳定胜 A，且收益覆盖摄入、延迟和维护成本，才完整生产化。
- **状态**：⏳ 待用户确认

### M23：现有评估只能复用骨架和部分检索指标，需新增图谱专项指标

- **严重程度**：🔴 严重（“质量低”与 ROI 均不可验证）
- **原 Spec 位置**：§2.1 错误处理、§2.6 测试、§3.1 完成判据、§3.6 验证目标
- **问题**：现有体系没有完整教材图谱专项评价。可复用 Component/System Bench、Retriever 的 recall@k/context_precision/redundancy/latency 和 RAGAS 回答指标，但不能直接评价实体/关系抽取正确性或图结构健康。
- **事实依据**：
  - [retriever.py:121-167](app/agents/retriever.py#L121-L167)：已有机械检索指标。
  - [retriever.py:169-265](app/agents/retriever.py#L169-L265)：RAGAS 三指标及 degraded 标记。
  - [system_bench.py:20-114](app/eval/system_bench.py#L20-L114)：能断言事件、掌握度和最大回合，但回合数目前是 `len(trace)//3` 启发式。
- **建议改法**：新增四层评价：①抽取层——实体/关系 P/R/F1、类型/方向、消歧、证据率；②结构层——重复/误合并、无证据边、孤立节点、PREREQ 环、方向冲突、陈旧边；③检索层——按 query_type 的 recall@k、precision、MRR/nDCG、图独占补回、无答案误召回、延迟/成本；④教学层——回答正确率/引用支持/unsupported claim、同 mastery 阈值下回合数、达成率、错误前置回退。降级 RAGAS 0.0 不得混入质量均值，须单列 degraded rate。
- **状态**：⏳ 待用户确认

### M24：将“抽取质量低”改为在线结构校验 + 离线质量门禁

- **严重程度**：🟡 中等（质量判据设计）
- **原 Spec 位置**：§2.1 / §3.1
- **问题**：`Relationship.confidence` 是 LLM 自评，只适合在线筛边信号，不能证明抽取质量；单次文档通常没有 gold，无法在线计算 precision/recall。
- **建议改法**：拆成两层：在线做 schema 必填、枚举合法、confidence 范围、端点存在、无自环/悬挂边、证据 span 存在等结构校验；离线用双人标注 gold entities/relations/evidence spans 计算实体/关系 P/R/F1、消歧和证据率，作为生产门禁。LLM confidence 不作为准确率。
- **状态**：⏳ 待用户确认

### M25：为 ROI 增加成本、统计可信度和止损机制

- **严重程度**：🟡 中等（决策完整性）
- **原 Spec 位置**：§3.6 / §4
- **问题**：现有验证仅写“能返回结果”，没有摄入 token/费用、人工复核、更新成本、p95 延迟、置信区间或停止投资条件；无法判断 ROI。
- **建议改法**：pilot 预注册主指标、query_type、paired_case_id、指标方向和置信区间；记录摄入 token/美元、人工分钟、每问额外 token/成本、p50/p95、增量更新/删除成本。阈值先标“待业务确认”；oracle 图不胜强 A 或自动图收益不稳定时立即止损。
- **状态**：⏳ 待用户确认

---

## Review 问答记录

> 记录关键问答，作为修改建议的事实依据。只沉淀**涉及原 Spec 事实核实/设计取舍**的问答，闲聊不记。

### RQ1：Curator 是"教学层"吗？与 Tutor 是否功能重叠？

**日期**：2026-07-16

**结论**：不是教学层；与 Tutor 职能正交、不重叠。原 Spec 1.2 节的标注会产生双重误解（详见 M1）。

**核实路径**：读 `app/specs/agents/curator.md`、`app/specs/agents/tutor.md`、`Learned/2026-07-14-StudyAgent多Agent协作架构.md`（七角色表 + Q6 边界节 + 规则路由表），均指向同一事实：Curator=结构层（图谱维护，不调 LLM），Tutor=生成层（教学主体），教学路由决策归 Orchestrator。

### RQ2：§2.1 是 LLM 抽取吗？失败有无降级？"质量低"如何判断？

**日期**：2026-07-17

**结论**：
1. **是 LLM 抽取**：§2.1 数据流"下游 = LLM API（复用 LLMService）"，§3.1 `extract`"调 LLM 抽取 + 解析 JSON"。
2. **已核实可复用 `invoke_json`**：[llm.py:168-178](app/infrastructure/llm.py#L168-L178) 会复用 `invoke`、清理代码围栏并 `json.loads`；改见 M17。
3. **降级链**：`LLMService.invoke` 先重试+fallback，仍失败或 JSON 解析失败由 extractor 捕获返空，向量索引继续；改见 M18。
4. **"质量低"原 spec 无判据**：应拆在线结构校验与离线质量门禁，见 M24。

### RQ3：现有 MasteryGraph 是否是用户画像？能否学习教材知识结构？ROI 如何？

**日期**：2026-07-22

**结论**：MasteryGraph 从数据归属看属于用户画像/学习者模型，但不是平面画像，而是带 PREREQ/RELATED/CONFLICT 结构与掌握状态的用户级图；B-① 计划的是另一张教材/知识库级内容图，能学习广义概念结构，但当前 spec 未完整表达目录章节结构。教材图 ROI 是**条件性**：在高复用教材的跨章节、多跳前置、概念辨析和全局导航查询上可能中高；在局部事实、短教材、频繁改版材料上通常低；且当前必须先完成无图 RAG 在线闭环。现有评估可复用骨架和检索/回答指标，但缺图抽取与结构质量专项指标。详见 M19-M25。
